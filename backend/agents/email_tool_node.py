"""
Email Tool Node — sends the approved draft email.

CRITICAL GOVERNANCE REQUIREMENT
--------------------------------
Email must NEVER send automatically.  This node enforces a multi-layer
safeguard system before any email is sent:

1. **State-level check** — Verifies ``approval_status.status`` is "approved" or "edited".
2. **DB-level check** — Queries the database for a valid Approval record.
3. **No bypass** — All three checks must pass.  Any single failure blocks the send.

Safeguards
----------
- Layer 1: Graph routing (only reaches this node after human_approval_node).
- Layer 2: State validation (approval_status in pipeline state).
- Layer 3: Database verification (Approval record exists and is approved).
- Layer 4: Sender abstraction (pluggable, defaults to simulated).

Future-Readiness
----------------
The email sender is abstracted via the ``EmailSender`` interface:
- ``SimulatedEmailSender`` — logs the email (current default, for dev/testing)
- SMTP, SendGrid, Gmail API — can be added by implementing ``EmailSender``

The provider is selected via the ``EMAIL_PROVIDER`` config setting.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.database.session import async_session_factory
from backend.models.sqlalchemy_models import Approval, AuditLog, DraftEmail, Lead
from backend.services.email_sender import get_email_sender

# ══════════════════════════════════════════════════════════════════════════
# Safeguard helpers
# ══════════════════════════════════════════════════════════════════════════


def _check_state_approval(approval_status: Any) -> tuple[bool, str]:
    """Safeguard Layer 2: Validate approval in graph state.

    Checks that the pipeline state contains a valid approval_status
    with status "approved" or "edited".

    Args:
        approval_status: The value of ``state["approval_status"]``.

    Returns:
        Tuple of (passed, error_message).  If passed is True, the
        state-level check succeeded.
    """
    if approval_status is None or not isinstance(approval_status, dict):
        return False, "approval_status is missing or None in pipeline state"

    status = approval_status.get("status", "").lower()
    if status not in ("approved", "edited"):
        return False, (
            f"approval_status.status is '{status}', "
            f"expected 'approved' or 'edited'"
        )

    return True, ""


async def _check_db_approval(lead_id: str) -> tuple[bool, str]:
    """Safeguard Layer 3: Verify approval record exists in the database.

    Queries the Approval table for the most recent record for this lead.
    The record must have ``approved=True``.

    Args:
        lead_id: The ID of the lead.

    Returns:
        Tuple of (passed, error_message).  If passed is True, the
        DB-level check succeeded.
    """
    async with async_session_factory() as session:
        try:
            # Query the most recent approval record for this lead
            from sqlalchemy import select

            stmt = (
                select(Approval)
                .where(Approval.lead_id == lead_id)
                .order_by(Approval.timestamp.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            approval_record = result.scalar_one_or_none()

            if approval_record is None:
                return False, (
                    f"No approval record found in database for lead {lead_id}"
                )

            if not approval_record.approved:
                return False, (
                    f"Approval record for lead {lead_id} exists but "
                    f"approved=False (rejected by {approval_record.approved_by})"
                )

            return True, ""

        except Exception as exc:
            return False, f"Database error checking approval: {str(exc)}"


# ══════════════════════════════════════════════════════════════════════════
# Main node
# ══════════════════════════════════════════════════════════════════════════


async def email_tool_node(state: dict) -> dict:
    """
    Send the approved draft email.

    This function is the LangGraph node for email sending.  It enforces
    multi-layer safeguards before any email is sent:

    1. State-level approval check (Layer 2).
    2. Database-level approval check (Layer 3).
    3. Sends the email via the configured provider (Layer 4).
    4. Persists the send status in the database.
    5. Creates an audit log entry.

    Args:
        state: Current ``PipelineState`` dict containing at least
            ``lead``, ``draft_email``, ``approval_status``, and ``logs`` keys.

    Returns:
        Dict with updated ``draft_email`` (status → "sent") and ``logs``.
    """
    lead = state.get("lead", {})
    draft_email = state.get("draft_email", {})
    approval_status = state.get("approval_status", {})
    logs = list(state.get("logs", []))

    lead_id = lead.get("id")
    lead_name = lead.get("name", "unknown")
    lead_email = lead.get("email", "unknown")
    subject = draft_email.get("subject", "No subject") if draft_email else "No subject"
    body = draft_email.get("body", "") if draft_email else ""

    # ══════════════════════════════════════════════════════════════════════
    # SAFEGUARD: Layer 2 — State-level approval check
    # ══════════════════════════════════════════════════════════════════════
    state_ok, state_error = _check_state_approval(approval_status)
    if not state_ok:
        log_entry = {
            "event_type": "email_send_error",
            "message": (
                f"🔒 BLOCKED: Email NOT sent to {lead_name} <{lead_email}>. "
                f"Safeguard Layer 2 (state) failed: {state_error}"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return {
            "draft_email": draft_email,
            "lead": lead,
            "logs": logs + [log_entry],
        }

    # ══════════════════════════════════════════════════════════════════════
    # SAFEGUARD: Layer 3 — Database-level approval verification
    # ══════════════════════════════════════════════════════════════════════
    if lead_id:
        db_ok, db_error = await _check_db_approval(lead_id)
        if not db_ok:
            log_entry = {
                "event_type": "email_send_error",
                "message": (
                    f"🔒 BLOCKED: Email NOT sent to {lead_name} <{lead_email}>. "
                    f"Safeguard Layer 3 (DB) failed: {db_error}"
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return {
                "draft_email": draft_email,
                "lead": lead,
                "logs": logs + [log_entry],
            }
    else:
        # Cannot verify in DB — this is a safety risk, so we block
        log_entry = {
            "event_type": "email_send_error",
            "message": (
                f"🔒 BLOCKED: Email NOT sent to {lead_name} (no lead ID). "
                f"Safeguard Layer 3 (DB) skipped — no lead ID available."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return {
            "draft_email": draft_email,
            "lead": lead,
            "logs": logs + [log_entry],
        }

    # ══════════════════════════════════════════════════════════════════════
    # SAFEGUARD: Layer 4 — Send the email via configured provider
    # ══════════════════════════════════════════════════════════════════════
    sender = get_email_sender()
    try:
        send_result = await sender.send(
            to_name=lead_name,
            to_email=lead_email,
            subject=subject,
            body=body,
        )
    except Exception as exc:
        send_result = {
            "success": False,
            "provider": "unknown",
            "message_id": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }

    # ══════════════════════════════════════════════════════════════════════
    # Process send result
    # ══════════════════════════════════════════════════════════════════════
    if send_result.get("success"):
        updated_email = {**(draft_email or {}), "status": "sent"}

        # Persist to database
        if lead_id:
            async with async_session_factory() as session:
                try:
                    from sqlalchemy import select as sa_select
                    from sqlalchemy.orm import selectinload

                    # Eagerly load draft_emails to avoid async lazy-load error
                    stmt = (
                        sa_select(Lead)
                        .options(selectinload(Lead.draft_emails))
                        .where(Lead.id == lead_id)
                    )
                    result = await session.execute(stmt)
                    db_lead = result.scalar_one_or_none()
                    if db_lead is not None:
                        existing_drafts = db_lead.draft_emails
                        if existing_drafts:
                            latest_draft = existing_drafts[-1]
                            latest_draft.status = "sent"

                        audit_entry = AuditLog(
                            lead_id=lead_id,
                            event_type="email_sent",
                            message=(
                                f"Email sent to {lead_name} <{lead_email}> "
                                f"— Subject: {subject[:80]}"
                                f"{'...' if len(subject) > 80 else ''} "
                                f"[Provider: {send_result.get('provider', 'unknown')}, "
                                f"MessageID: {send_result.get('message_id', 'N/A')}]"
                            ),
                        )
                        session.add(audit_entry)
                        await session.commit()

                except Exception:
                    await session.rollback()

        log_entry = {
            "event_type": "email_sent",
            "message": (
                f"Email sent to {lead_name} <{lead_email}> "
                f"— Subject: {subject[:80]}{'...' if len(subject) > 80 else ''} "
                f"[Provider: {send_result.get('provider', 'unknown')}, "
                f"MessageID: {send_result.get('message_id', 'N/A')}]"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Merge send metadata into lead for downstream
        enriched_lead = dict(lead)
        enriched_lead["email_sent"] = True
        enriched_lead["email_provider"] = send_result.get("provider")
        enriched_lead["email_message_id"] = send_result.get("message_id")

        return {
            "draft_email": updated_email,
            "lead": enriched_lead,
            "logs": logs + [log_entry],
        }

    else:
        # Send failed
        error_msg = send_result.get("error", "Unknown error")
        log_entry = {
            "event_type": "email_send_error",
            "message": (
                f"Email FAILED to send to {lead_name} <{lead_email}> "
                f"— Subject: {subject[:80]} — Error: {error_msg}"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return {
            "draft_email": draft_email,
            "lead": lead,
            "logs": logs + [log_entry],
        }