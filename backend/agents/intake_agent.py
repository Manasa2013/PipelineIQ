"""
Intake Agent — validates, normalizes, and persists incoming lead data.

Responsibilities:
  1. Validate incoming lead data using Pydantic (LeadCreate schema).
  2. Normalize email, company name, and role.
  3. Persist the lead to the SQLite database.
  4. Update the graph state with the validated lead object.
  5. Create an audit log entry.
"""

from datetime import datetime, timezone

from pydantic import ValidationError

from backend.database.session import async_session_factory
from backend.models.schemas import LeadCreate, LeadResponse
from backend.models.sqlalchemy_models import AuditLog, Lead
from backend.utils.normalization import normalize_company_name, normalize_email, normalize_role
from backend.utils.security import process_lead_safely


async def intake_agent(state: dict) -> dict:
    """
    Process and validate incoming lead data.

    Args:
        state: Current PipelineState dict containing the raw lead data.

    Returns:
        Dict with updated lead, audit log, and (on failure) error info.
    """
    raw_lead = state.get("lead", {})
    logs = list(state.get("logs", []))

    # ── 1. Pydantic validation ─────────────────────────────────────────
    try:
        validated = LeadCreate(**raw_lead)
    except ValidationError as exc:
        error_msg = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in exc.errors())
        return {
            "lead": raw_lead,
            "logs": logs
            + [
                {
                    "event_type": "intake_error",
                    "message": f"Validation failed: {error_msg}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }

    # ── 1b. Prompt injection defense ───────────────────────────────────
    # Scan and sanitize lead data for prompt injection attempts.
    # Lead fields are treated as data, never as instructions.
    sanitized_lead, security_logs = process_lead_safely(
        validated.model_dump(),
        stage="intake",
    )

    # Merge security audit logs into the main log list
    logs.extend(security_logs)

    # ── 2. Normalization ───────────────────────────────────────────────
    normalized_email = normalize_email(sanitized_lead.get("email", validated.email))
    normalized_company = normalize_company_name(sanitized_lead.get("company", validated.company))
    normalized_role = normalize_role(sanitized_lead.get("role") or validated.role) if (sanitized_lead.get("role") or validated.role) else None

    # ── 3. Persist to database (or load existing record) ───────────────
    # If the lead already has an ID (created via POST /lead), load the
    # existing record from the DB instead of creating a duplicate.
    existing_id = raw_lead.get("id")

    async with async_session_factory() as session:
        try:
            if existing_id:
                # Lead already exists — load it; do NOT create a duplicate
                db_lead = await session.get(Lead, existing_id)
                if db_lead is None:
                    # Fallback: ID given but not found — create new
                    db_lead = Lead(
                        name=validated.name.strip(),
                        email=normalized_email,
                        company=normalized_company,
                        role=normalized_role,
                        industry=validated.industry.strip() if validated.industry else None,
                        buying_signals=validated.buying_signals or [],
                    )
                    session.add(db_lead)
                    await session.commit()
                    await session.refresh(db_lead)
            else:
                # No ID — check for duplicate email before inserting
                from sqlalchemy import select as sa_select
                existing_email_check = await session.execute(
                    sa_select(Lead).where(Lead.email == normalized_email)
                )
                existing_by_email = existing_email_check.scalar_one_or_none()
                if existing_by_email is not None:
                    db_lead = existing_by_email
                else:
                    db_lead = Lead(
                        name=validated.name.strip(),
                        email=normalized_email,
                        company=normalized_company,
                        role=normalized_role,
                        industry=validated.industry.strip() if validated.industry else None,
                        buying_signals=validated.buying_signals or [],
                    )
                    session.add(db_lead)
                    await session.commit()
                    await session.refresh(db_lead)

            # ── 4. Persist audit log ───────────────────────────────────
            audit_entry = AuditLog(
                lead_id=db_lead.id,
                event_type="intake",
                message=(
                    f"Lead ingested: {db_lead.name} <{db_lead.email}> "
                    f"from {db_lead.company}"
                ),
            )
            session.add(audit_entry)
            await session.commit()

        except Exception as exc:
            await session.rollback()
            return {
                "lead": raw_lead,
                "logs": logs
                + [
                    {
                        "event_type": "intake_error",
                        "message": f"Database error: {str(exc)}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
            }

    # ── 5. Build clean output state ────────────────────────────────────
    lead_out = LeadResponse(
        id=db_lead.id,
        name=db_lead.name,
        email=db_lead.email,
        company=db_lead.company,
        role=db_lead.role,
        industry=db_lead.industry,
        buying_signals=db_lead.buying_signals,
        created_at=db_lead.created_at,
    )

    log_entry = {
        "event_type": "intake",
        "message": f"Lead ingested: {db_lead.name} <{db_lead.email}> from {db_lead.company}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "lead": lead_out.model_dump(mode="json"),
        "logs": logs + [log_entry],
    }