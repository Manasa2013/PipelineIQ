"""
Approval API endpoints for PipelineIQ.

Provides REST endpoints for the human-in-the-loop approval workflow:
- POST /approve/{lead_id} — Approve the draft email
- POST /reject/{lead_id} — Reject the draft email
- PUT /draft/{lead_id} — Edit the draft email

These endpoints persist the decision to the DB, then resume the paused
LangGraph execution so email_tool_node runs (or the graph terminates on
rejection).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.database.session import async_session_factory
from backend.models.sqlalchemy_models import AuditLog, DraftEmail, Lead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Approval"])


# ── Request schemas ──────────────────────────────────────────────────────


class ApproveRequest(BaseModel):
    """Payload for approving a draft email."""

    approved_by: str = Field(
        ..., min_length=1, max_length=255, examples=["manager@example.com"]
    )


class RejectRequest(BaseModel):
    """Payload for rejecting a draft email."""

    approved_by: str = Field(
        ..., min_length=1, max_length=255, examples=["manager@example.com"]
    )
    reason: Optional[str] = Field(
        None, max_length=500, examples=["Not a good fit at this time"]
    )


class EditDraftRequest(BaseModel):
    """Payload for editing a draft email."""

    approved_by: str = Field(
        ..., min_length=1, max_length=255, examples=["manager@example.com"]
    )
    subject: Optional[str] = Field(None, max_length=255)
    body: Optional[str] = None


# ── API endpoints ────────────────────────────────────────────────────────


@router.post("/approve/{lead_id}", summary="Approve draft email")
async def approve_draft(lead_id: str, payload: ApproveRequest):
    """
    Approve the draft email for a lead.

    Marks the draft email as "approved" and creates an audit log entry.
    The graph can then be resumed to send the email.

    Args:
        lead_id: The ID of the lead.
        payload: Approval details (who approved).

    Returns:
        Confirmation message with the approval status.
    """
    return await _process_approval(
        lead_id=lead_id,
        status="approved",
        approved_by=payload.approved_by,
        edited_subject=None,
        edited_body=None,
        reason=None,
    )


@router.post("/reject/{lead_id}", summary="Reject draft email")
async def reject_draft(lead_id: str, payload: RejectRequest):
    """
    Reject the draft email for a lead.

    Marks the draft email as "rejected" and creates an audit log entry.
    The graph terminates — no email will be sent.

    Args:
        lead_id: The ID of the lead.
        payload: Rejection details (who rejected, optional reason).

    Returns:
        Confirmation message with the rejection status.
    """
    return await _process_approval(
        lead_id=lead_id,
        status="rejected",
        approved_by=payload.approved_by,
        edited_subject=None,
        edited_body=None,
        reason=payload.reason,
    )


@router.put("/draft/{lead_id}", summary="Edit draft email")
async def edit_draft(lead_id: str, payload: EditDraftRequest):
    """
    Edit the draft email for a lead.

    Updates the subject and/or body of the draft email and marks it as
    "reviewed".  Preserves user edits.  The graph can then be resumed
    to send the edited email.

    Args:
        lead_id: The ID of the lead.
        payload: Edit details (who edited, optional new subject/body).

    Returns:
        Confirmation message with the updated draft.
    """
    return await _process_approval(
        lead_id=lead_id,
        status="edited",
        approved_by=payload.approved_by,
        edited_subject=payload.subject,
        edited_body=payload.body,
        reason=None,
    )


# ── Internal helper ──────────────────────────────────────────────────────


async def _process_approval(
    lead_id: str,
    status: str,
    approved_by: str,
    edited_subject: str | None = None,
    edited_body: str | None = None,
    reason: str | None = None,
) -> dict:
    """Process an approval decision, persist it to the database, then resume
    the paused LangGraph so email_tool_node can execute (or terminate on
    rejection).

    Args:
        lead_id: The ID of the lead.
        status: One of "approved", "rejected", "edited".
        approved_by: Who made the decision.
        edited_subject: New subject (only for "edited").
        edited_body: New body (only for "edited").
        reason: Rejection reason (only for "rejected").

    Returns:
        A dict with the result of the operation.

    Raises:
        HTTPException: If the lead is not found or the draft is not found.
    """
    # ── Lazy imports to avoid circular dependency ────────────────────────
    from backend.graph import pipeline_graph
    from langgraph.types import Command
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    async with async_session_factory() as session:
        try:
            # Load lead with draft_emails eagerly (async SQLAlchemy requires
            # explicit eager loading — lazy access raises greenlet_spawn error)
            stmt = (
                sa_select(Lead)
                .options(selectinload(Lead.draft_emails))
                .where(Lead.id == lead_id)
            )
            result = await session.execute(stmt)
            db_lead = result.scalar_one_or_none()
            if db_lead is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Lead {lead_id} not found",
                )

            # Check for existing draft emails
            existing_drafts = db_lead.draft_emails
            if not existing_drafts:
                raise HTTPException(
                    status_code=404,
                    detail=f"No draft email found for lead {lead_id}",
                )

            latest_draft = existing_drafts[-1]

            # ── Process the decision ─────────────────────────────────────
            status_label_map = {
                "approved": "APPROVED",
                "rejected": "REJECTED",
                "edited": "EDITED & APPROVED",
            }
            status_label = status_label_map.get(status, status.upper())

            draft_subject = latest_draft.subject
            draft_body = latest_draft.body

            if status == "approved":
                latest_draft.status = "approved"
            elif status == "rejected":
                latest_draft.status = "rejected"
            elif status == "edited":
                if edited_subject is not None:
                    latest_draft.subject = edited_subject
                    draft_subject = edited_subject
                if edited_body is not None:
                    latest_draft.body = edited_body
                    draft_body = edited_body
                latest_draft.status = "reviewed"

            # ── Create approval record ──────────────────────────────────
            from backend.models.sqlalchemy_models import Approval

            approval_record = Approval(
                lead_id=lead_id,
                approved=(status in ("approved", "edited")),
                approved_by=approved_by,
            )
            session.add(approval_record)

            # ── Create audit log ─────────────────────────────────────────
            message_parts = [
                f"Draft email for {db_lead.name} was {status_label} by {approved_by}"
            ]
            if status == "rejected" and reason:
                message_parts.append(f"Reason: {reason}")
            if status == "edited":
                message_parts.append("User edits preserved.")

            audit_entry = AuditLog(
                lead_id=lead_id,
                event_type="approval",
                message=". ".join(message_parts),
            )
            session.add(audit_entry)

            # Read the thread_id before committing (still in the same session)
            thread_id = db_lead.pipeline_thread_id

            await session.commit()

            logger.info(
                "Draft email for lead %s (%s) %s by %s",
                lead_id,
                db_lead.name,
                status_label,
                approved_by,
            )

        except HTTPException:
            raise
        except Exception as exc:
            await session.rollback()
            logger.error(
                "Failed to process approval for lead %s: %s",
                lead_id,
                exc,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process approval: {str(exc)}",
            )

    # ── Resume the paused LangGraph ──────────────────────────────────────
    # The graph was interrupted at human_approval_node. We resume it by
    # supplying the decision payload as the Command(resume=...) value.
    # This only runs when a thread_id was stored (i.e. the pipeline ran
    # through /pipeline/run at least once for this lead).
    #
    # IMPORTANT: We first check whether the graph actually has a pending
    # interrupt for this thread_id.  The MemorySaver is in-process only —
    # if the server restarted after /pipeline/run, the checkpoint is gone
    # and passing Command(resume=...) would raise "Must write to at least
    # one of [...]".  Checking aget_state().next prevents that warning.
    graph_resumed = False
    if thread_id:
        decision_payload = {
            "status": status,
            "approved_by": approved_by,
        }
        if status == "edited":
            if edited_subject is not None:
                decision_payload["edited_subject"] = edited_subject
            if edited_body is not None:
                decision_payload["edited_body"] = edited_body
        if status == "rejected" and reason:
            decision_payload["reason"] = reason

        try:
            config = {"configurable": {"thread_id": thread_id}}

            # Check whether the graph actually has a pending interrupt
            # for this thread before attempting to resume it.
            graph_state = await pipeline_graph.aget_state(config)
            has_pending_interrupt = bool(
                graph_state.next
                and any(
                    interrupt
                    for task in graph_state.tasks
                    for interrupt in task.interrupts
                )
            )

            if has_pending_interrupt:
                await pipeline_graph.ainvoke(
                    Command(resume=decision_payload),
                    config=config,
                )
                graph_resumed = True
                logger.info(
                    "Resumed graph thread %s for lead %s with status=%s",
                    thread_id,
                    lead_id,
                    status,
                )
            else:
                logger.info(
                    "Graph thread %s for lead %s has no pending interrupt "
                    "(checkpoint may have been cleared on server restart). "
                    "DB already updated — skipping graph resume.",
                    thread_id,
                    lead_id,
                )
        except Exception as exc:
            # Graph resume failure is logged but does not fail the HTTP response.
            # The DB has already been updated successfully.
            logger.warning(
                "Graph resume failed for lead %s (thread %s): %s",
                lead_id,
                thread_id,
                exc,
            )
    else:
        logger.warning(
            "No pipeline_thread_id on lead %s — graph not resumed. "
            "Run /pipeline/run first.",
            lead_id,
        )

    return {
        "success": True,
        "lead_id": lead_id,
        "status": status,
        "status_label": status_label,
        "approved_by": approved_by,
        "graph_resumed": graph_resumed,
        "draft": {
            "subject": draft_subject,
            "body": draft_body,
            "status": latest_draft.status,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }