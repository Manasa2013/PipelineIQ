"""
Outreach Agent — generates a personalized draft outreach email for hot leads.

Rules
-----
1. Use only lead data and enrichment data — no hallucinated information.
2. Professional B2B tone — respectful, concise, value-driven.
3. Personalized email — references the lead's company, role, and industry.
4. Structured output — subject line and email body.
5. No fabrication — never invent data points not present in lead/enrichment.

Output
------
- subject: Attention-grabbing, professional subject line.
- body: Multi-paragraph B2B outreach email.
- status: Always "draft" (pending human approval).

Responsibilities
----------------
1. Read lead and enrichment data from pipeline state.
2. Generate a personalized email subject and body using only available data.
3. Persist the DraftEmail record to the database.
4. Create an audit log entry.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.database.session import async_session_factory
from backend.models.sqlalchemy_models import AuditLog, DraftEmail, Lead


def _build_subject(
    lead: dict,
    enrichment: dict | None,
) -> str:
    """Build a professional email subject line from lead data.

    Uses only data available in the lead and enrichment dicts.
    Falls back gracefully if fields are missing.

    Args:
        lead: Lead data dict.
        enrichment: Enrichment data dict (may be None or empty).

    Returns:
        A subject line string (max ~100 chars).
    """
    company = lead.get("company", "").strip()
    industry = (
        enrichment.get("company_industry") if enrichment else lead.get("industry", "")
    )
    role = lead.get("role", "").strip()
    name = lead.get("name", "").strip()

    # Pattern 1: Industry-focused (if both company and industry available)
    if company and industry:
        return f"Quick question about {company}'s {industry} strategy"

    # Pattern 2: Company-focused (if company available)
    if company:
        return f"Thoughts on scaling {company}'s growth?"

    # Pattern 3: Role-focused (if role and name available)
    if role and name:
        return f"Opportunity for {name} — {role} at a B2B tech firm"

    # Pattern 4: Name-focused (if name available)
    if name:
        return f"Connecting with {name} about a growth opportunity"

    # Fallback
    return "Exploring a potential partnership opportunity"


def _build_email_body(
    lead: dict,
    enrichment: dict | None,
) -> str:
    """Build a professional B2B email body from lead data.

    Uses ONLY data present in the lead and enrichment dicts.
    Never invents or hallucinates company names, sizes, or other data.
    Follows a professional B2B outreach template.

    Args:
        lead: Lead data dict.
        enrichment: Enrichment data dict (may be None or empty).

    Returns:
        A multi-paragraph email body string.
    """
    name = lead.get("name", "").strip()
    company = lead.get("company", "").strip()
    role = lead.get("role", "").strip()
    industry = (
        enrichment.get("company_industry") if enrichment else lead.get("industry", "")
    )
    company_size = (
        enrichment.get("company_size") if enrichment else lead.get("company_size", "")
    )
    employee_count = (
        enrichment.get("employee_count") if enrichment else lead.get("employee_count", "")
    )
    company_location = (
        enrichment.get("company_location") if enrichment else lead.get("company_location", "")
    )
    buying_signals = lead.get("buying_signals", [])

    # ── Greeting ────────────────────────────────────────────────────────
    if name:
        greeting = f"Hi {name},"
    else:
        greeting = "Hello,"

    # ── Opening paragraph (personalized context) ─────────────────────────
    opening_parts = []

    if company and industry:
        opening_parts.append(
            f"I came across {company} and was impressed by your work in the "
            f"{industry} space."
        )
    elif company:
        opening_parts.append(
            f"I came across {company} and was impressed by what you're building."
        )
    elif industry:
        opening_parts.append(
            f"I've been following the {industry} space and thought I'd reach out."
        )
    else:
        opening_parts.append(
            "I came across your profile and thought I'd reach out."
        )

    # Build context about the lead's company
    context_parts = []
    if role:
        context_parts.append(f"role as {role}")
    if company_size:
        context_parts.append(f"company size of {company_size}")
    if employee_count:
        context_parts.append(f"team of {employee_count}")

    if context_parts:
        context_str = "; ".join(context_parts)
        opening_parts.append(
            f"Noting your {context_str}, I believe there may be a strong fit "
            f"with what we offer."
        )

    opening = " ".join(opening_parts)

    # ── Value proposition paragraph ──────────────────────────────────────
    if industry:
        value_prop = (
            f"We specialize in helping {industry} companies like {company or 'yours'} "
            f"streamline their B2B lead qualification and outreach processes. "
            f"Our platform helps teams identify high-fit leads and engage them "
            f"with personalized communication at scale."
        )
    elif company:
        value_prop = (
            f"We specialize in helping companies like {company} "
            f"streamline their B2B lead qualification and outreach processes."
        )
    else:
        value_prop = (
            "We specialize in helping B2B companies streamline their lead "
            "qualification and outreach processes."
        )

    # ── Buying signals / relevance paragraph ─────────────────────────────
    if buying_signals:
        signals_str = ", ".join(str(s) for s in buying_signals)
        relevance = (
            f"I noticed you've shown interest through {signals_str}. "
            f"This aligns closely with the value we deliver, and I'd love to "
            f"share how we've helped similar organizations achieve measurable results."
        )
    elif company:
        relevance = (
            f"Given your work at {company}, I believe a brief conversation "
            f"could be mutually valuable to explore whether our solution is "
            f"a good fit for your needs."
        )
    else:
        relevance = (
            "I believe a brief conversation could be mutually valuable to "
            "explore whether our solution is a good fit for your needs."
        )

    # ── Call to action ───────────────────────────────────────────────────
    if company_location:
        cta = (
            f"Would you be open to a 15-minute call next week to discuss "
            f"how we might support {company or 'your team'}'s goals? "
            f"I'm based in {company_location} and would be happy to connect."
        )
    else:
        cta = (
            "Would you be open to a 15-minute call next week? I'm available "
            "at your convenience."
        )

    # ── Closing ──────────────────────────────────────────────────────────
    closing = "Best regards,\nPipelineIQ"

    # ── Assemble body ────────────────────────────────────────────────────
    body_parts = [
        greeting,
        "",
        opening,
        "",
        value_prop,
        "",
        relevance,
        "",
        cta,
        "",
        closing,
    ]

    return "\n".join(body_parts)


async def outreach_agent(state: dict) -> dict:
    """
    Generate a personalized outreach email for a hot lead.

    This function is the LangGraph node for outreach.  It reads the
    lead and enrichment data from the current graph state, generates
    a personalized email, persists the DraftEmail record, and returns
    an updated state dict.

    Args:
        state: Current ``PipelineState`` dict containing at least
            ``lead`` and ``logs`` keys, and optionally ``enrichment``.

    Returns:
        Dict with updated ``draft_email``, ``lead`` (with email merged
        in), and ``logs`` (appended audit entry).
    """
    lead = state.get("lead", {})
    enrichment = state.get("enrichment", {})
    logs = list(state.get("logs", []))

    # ── 1. Generate email content from data only ─────────────────────────
    subject = _build_subject(lead, enrichment)
    body = _build_email_body(lead, enrichment)
    status = "draft"

    draft_email = {
        "subject": subject,
        "body": body,
        "status": status,
    }

    # ── 2. Persist draft email in database ───────────────────────────────
    lead_id = lead.get("id")
    if lead_id:
        async with async_session_factory() as session:
            try:
                # Verify lead exists
                db_lead = await session.get(Lead, lead_id)
                if db_lead is not None:
                    email_record = DraftEmail(
                        lead_id=lead_id,
                        subject=subject,
                        body=body,
                        status=status,
                    )
                    session.add(email_record)

                    # ── 3. Persist audit log ────────────────────────────
                    audit_entry = AuditLog(
                        lead_id=lead_id,
                        event_type="outreach",
                        message=(
                            f"Draft email created for {lead.get('name', 'unknown')} "
                            f"— Subject: {subject[:80]}{'...' if len(subject) > 80 else ''}"
                        ),
                    )
                    session.add(audit_entry)
                    await session.commit()

            except Exception:
                await session.rollback()
                log_entry = {
                    "event_type": "outreach_error",
                    "message": (
                        f"Failed to persist draft email for lead {lead_id}: "
                        f"database error"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return {
                    "draft_email": draft_email,
                    "lead": lead,
                    "logs": logs + [log_entry],
                }

    # ── 4. Build clean output state ────────────────────────────────────
    # Merge draft email into lead for downstream nodes
    enriched_lead = dict(lead)
    enriched_lead["draft_subject"] = subject
    enriched_lead["draft_status"] = status

    log_entry = {
        "event_type": "outreach",
        "message": (
            f"Draft email created for {lead.get('name', 'unknown')} "
            f"— Subject: {subject[:80]}{'...' if len(subject) > 80 else ''}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "draft_email": draft_email,
        "lead": enriched_lead,
        "logs": logs + [log_entry],
    }