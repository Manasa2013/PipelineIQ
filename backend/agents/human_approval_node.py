"""
Human Approval Node — pauses the graph for human review of draft emails.

Critical Governance Requirement
-------------------------------
Email must NEVER send automatically.  The graph MUST pause at this node
and wait for an explicit human decision via an external API endpoint.

Workflow
--------
1. Outreach agent generates draft email → graph arrives at this node.
2. The graph pauses using LangGraph's ``interrupt()`` mechanism.
3. External API resumes the graph with one of three decisions:
   - **Approve** → email_tool_node sends the email.
   - **Reject** → graph terminates (email is discarded).
   - **Edit Draft** → user modifies the draft, then graph resumes
     for approval or automatic send.

State Transitions
-----------------
- ``approval_status.status``: "pending" | "approved" | "rejected" | "edited"
- ``approval_status.approved_by``: Email or name of the approver.
- ``approval_status.timestamp``: When the decision was made.
- ``draft_email.status``: "draft" | "reviewed" | "approved" | "rejected" | "sent"

Responsibilities
----------------
1. Pause graph execution with the draft email data for human review.
2. Return the approval status (populated by the resume API call).
3. Create an audit log entry for the approval decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from langgraph.types import interrupt

from backend.database.session import async_session_factory
from backend.models.sqlalchemy_models import AuditLog, DraftEmail, Lead


async def human_approval_node(state: dict) -> dict:
    """
    Pause the graph for human review of the draft email.

    This function is the LangGraph node for human approval.  It:
    1. Reads the draft email from the graph state.
    2. Pauses the graph with ``interrupt()``, waiting for a human decision.
    3. Processes the decision (approve, reject, or edit).
    4. Persists the decision to the database.
    5. Creates an audit log entry.

    ``interrupt()`` is called directly inside this async node (not in a
    helper) so that LangGraph can correctly associate the state write with
    this node's checkpoint and avoid the "Must write to at least one of
    [...]" resume warning.

    Args:
        state: Current ``PipelineState`` dict containing at least
            ``lead``, ``draft_email``, and ``logs`` keys.

    Returns:
        Dict with updated ``approval_status``, ``draft_email`` (if edited),
        and ``logs`` (appended audit entry).
    """
    lead = state.get("lead", {})
    draft_email = state.get("draft_email", {})
    logs = list(state.get("logs", []))

    # ── 1. Pause graph for human decision ────────────────────────────────
    # interrupt() MUST be called directly in the async node function, not
    # inside a sync helper, so that LangGraph's checkpointer can correctly
    # track which state keys this node will write on resume.
    decision = interrupt({
        "action_required": "human_approval",
        "available_actions": ["approve", "reject", "edit"],
        "description": (
            "A draft email has been generated for this lead. "
            "You must approve, reject, or edit it before the email can be sent."
        ),
    })

    status = decision.get("status", "rejected").lower()
    approved_by = decision.get("approved_by", "unknown")

    # ── 2. Process the decision ──────────────────────────────────────────
    approval_status = {
        "status": status,
        "approved_by": approved_by,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Handle edits — preserve user's changes
    updated_draft = dict(draft_email)
    if status == "edited":
        edited_subject = decision.get("edited_subject")
        edited_body = decision.get("edited_body")
        if edited_subject:
            updated_draft["subject"] = edited_subject
        if edited_body:
            updated_draft["body"] = edited_body
        updated_draft["status"] = "reviewed"
        approval_status["edited"] = True
    elif status == "approved":
        updated_draft["status"] = "approved"
        approval_status["edited"] = False
    elif status == "rejected":
        updated_draft["status"] = "rejected"
        approval_status["edited"] = False

    # ── 3. Persist decision to database ──────────────────────────────────
    lead_id = lead.get("id")
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
                    # Update or create approval record
                    from backend.models.sqlalchemy_models import Approval

                    approval_record = Approval(
                        lead_id=lead_id,
                        approved=(status == "approved" or status == "edited"),
                        approved_by=approved_by,
                    )
                    session.add(approval_record)

                    # Update draft email in DB if it was edited
                    if status == "edited":
                        # Find the existing draft email (already eagerly loaded)
                        existing_drafts = db_lead.draft_emails
                        if existing_drafts:
                            latest_draft = existing_drafts[-1]
                            latest_draft.body = updated_draft.get("body", latest_draft.body)
                            latest_draft.subject = updated_draft.get("subject", latest_draft.subject)
                            latest_draft.status = "reviewed"

                    # ── 4. Persist audit log ────────────────────────────
                    status_label = {
                        "approved": "APPROVED",
                        "rejected": "REJECTED",
                        "edited": "EDITED & APPROVED",
                    }.get(status, status.upper())

                    audit_entry = AuditLog(
                        lead_id=lead_id,
                        event_type="approval",
                        message=(
                            f"Draft email for {lead.get('name', 'unknown')} "
                            f"was {status_label} by {approved_by}"
                        ),
                    )
                    session.add(audit_entry)
                    await session.commit()

            except Exception:
                await session.rollback()
                log_entry = {
                    "event_type": "approval_error",
                    "message": (
                        f"Failed to persist approval for lead {lead_id}: "
                        f"database error"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return {
                    "approval_status": approval_status,
                    "draft_email": updated_draft,
                    "lead": lead,
                    "logs": logs + [log_entry],
                }

    # ── 5. Build clean output state ──────────────────────────────────────
    status_label = {
        "approved": "APPROVED",
        "rejected": "REJECTED",
        "edited": "EDITED & APPROVED",
    }.get(status, status.upper())

    log_entry = {
        "event_type": "approval",
        "message": (
            f"Draft email for {lead.get('name', 'unknown')} "
            f"was {status_label} by {approved_by}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "approval_status": approval_status,
        "draft_email": updated_draft,
        "lead": lead,
        "logs": logs + [log_entry],
    }