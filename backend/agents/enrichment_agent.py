"""
Enrichment Agent — enriches lead data with company intelligence.

Responsibilities
----------------
1. Look up the company name from the lead.
2. Retrieve enrichment information from the company intelligence service.
3. Add enrichment data to the graph state.
4. Persist the enrichment record to the SQLite database.
5. Create an audit log entry.

Design
------
The agent depends on the abstract ``CompanyIntelligenceService``
interface, allowing the mock implementation to be swapped for a real
API client (Clearbit, Zoominfo, etc.) without changing agent code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.database.session import async_session_factory
from backend.models.sqlalchemy_models import AuditLog, Enrichment, Lead
from backend.services.company_intelligence import (
    CompanyIntelligenceService,
    get_company_intelligence_service,
)


async def enrichment_agent(
    state: dict,
    company_intelligence: Optional[CompanyIntelligenceService] = None,
) -> dict:
    """Enrich lead data with company information.

    This function is the LangGraph node for enrichment.  It reads the
    lead from the current graph state, looks up company data via the
    intelligence service, persists the enrichment, and returns an
    updated state dict.

    Args:
        state: Current ``PipelineState`` dict containing at least
            ``lead`` and ``logs`` keys.
        company_intelligence: Injected service for company lookups.
            Defaults to the module-level singleton
            ``MockCompanyIntelligenceService``.

    Returns:
        Dict with updated ``enrichment``, ``lead`` (with enrichment
        merged in), and ``logs`` (appended audit entry).
    """
    lead = state.get("lead", {})
    logs = list(state.get("logs", []))

    # Resolve the intelligence service (injectable for testing)
    service = company_intelligence or get_company_intelligence_service()

    company_name = lead.get("company", "")

    # ── 1. & 2. Lookup company & retrieve enrichment data ───────────────
    company_info = await service.lookup(company_name)

    if company_info is not None:
        enrichment_data = {
            "company_name": company_info.company_name,
            "company_size": company_info.company_size,
            "employee_count": company_info.employee_count,
            "company_location": company_info.location,
            "company_industry": company_info.industry,
            "website": company_info.website,
            "revenue": company_info.revenue,
            "founded_year": company_info.founded_year,
            "description": company_info.description,
        }
    else:
        # Fallback: derive minimal enrichment from lead data
        enrichment_data = {
            "company_name": lead.get("company", "Unknown"),
            "company_size": lead.get("company_size", "Unknown"),
            "employee_count": lead.get("employee_count", 0),
            "company_location": lead.get("company_location", "Unknown"),
            "company_industry": lead.get("industry", "Unknown"),
            "website": None,
            "revenue": None,
            "founded_year": None,
            "description": None,
        }

    # ── 3. Add enrichment data to graph state ───────────────────────────
    enriched_lead = dict(lead)
    enriched_lead.update(enrichment_data)

    # ── 4. Persist enrichment record in database ────────────────────────
    lead_id = lead.get("id")
    if lead_id:
        async with async_session_factory() as session:
            try:
                from sqlalchemy import select as sa_select
                from sqlalchemy.orm import selectinload

                # Eagerly load the enrichment relationship to avoid async lazy-load error
                stmt = (
                    sa_select(Lead)
                    .options(selectinload(Lead.enrichment))
                    .where(Lead.id == lead_id)
                )
                result = await session.execute(stmt)
                db_lead = result.scalar_one_or_none()
                if db_lead is not None:
                    # Check if enrichment already exists → update
                    existing = db_lead.enrichment
                    if existing:
                        existing.company_size = enrichment_data["company_size"]
                        existing.employee_count = enrichment_data["employee_count"]
                        existing.company_location = enrichment_data["company_location"]
                        existing.company_industry = enrichment_data["company_industry"]
                    else:
                        enrichment_record = Enrichment(
                            lead_id=lead_id,
                            company_size=enrichment_data["company_size"],
                            employee_count=enrichment_data["employee_count"],
                            company_location=enrichment_data["company_location"],
                            company_industry=enrichment_data["company_industry"],
                        )
                        session.add(enrichment_record)

                    # ── 5. Persist audit log ────────────────────────────
                    audit_entry = AuditLog(
                        lead_id=lead_id,
                        event_type="enrichment",
                        message=(
                            f"Enriched lead {lead.get('name', 'unknown')} "
                            f"— {enrichment_data['company_industry']}, "
                            f"{enrichment_data['employee_count']} employees"
                        ),
                    )
                    session.add(audit_entry)
                    await session.commit()

            except Exception:
                await session.rollback()
                # Log the failure but don't crash the pipeline —
                # enrichment data is still returned to the state.
                log_entry = {
                    "event_type": "enrichment_error",
                    "message": (
                        f"Failed to persist enrichment for lead {lead_id}: "
                        f"database error"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return {
                    "enrichment": enrichment_data,
                    "lead": enriched_lead,
                    "logs": logs + [log_entry],
                }

    # ── Build clean output state ────────────────────────────────────────
    log_entry = {
        "event_type": "enrichment",
        "message": (
            f"Enriched lead {lead.get('name', 'unknown')} "
            f"— {enrichment_data['company_industry']}, "
            f"{enrichment_data['employee_count']} employees"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "enrichment": enrichment_data,
        "lead": enriched_lead,
        "logs": logs + [log_entry],
    }