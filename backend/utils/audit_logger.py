"""
Centralized Audit Logger for PipelineIQ.

Provides a unified interface for creating audit log entries across all
pipeline stages.  Every log entry is persisted to the AuditLog table
in the database.

Logged Events
-------------
- lead_created       — Lead ingested into the pipeline
- enrichment         — Company enrichment data retrieved
- scoring            — Lead scored (AI or heuristic)
- fairness_check     — Fairness validation performed
- prompt_injection   — Prompt injection attempt detected
- classification     — Lead classified (hot/nurture/disqualify)
- draft_created      — Draft outreach email created
- approval           — Draft email approved
- rejection          — Draft email rejected
- email_sent         — Email sent to lead

Usage
-----
    from backend.utils.audit_logger import log_event

    # Inside any agent or service:
    await log_event(
        lead_id="abc123",
        event_type="scoring",
        message="Scored lead Jane Doe — 85/100 (confidence: 0.92)",
        session=db_session,  # Optional — uses new session if omitted
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from backend.database.session import async_session_factory
from backend.models.sqlalchemy_models import AuditLog

logger = logging.getLogger(__name__)

# ── All recognized event types ───────────────────────────────────────────

EVENT_TYPES = frozenset({
    "lead_created",
    "enrichment",
    "scoring",
    "fairness_check",
    "prompt_injection_detected",
    "classification",
    "draft_created",
    "approval",
    "rejection",
    "email_sent",
    "email_send_error",
    "intake_error",
    "scoring_error",
    "enrichment_error",
    "classification_error",
    "outreach_error",
    "approval_error",
})


# ── Public API ───────────────────────────────────────────────────────────


async def log_event(
    lead_id: str,
    event_type: str,
    message: str,
    *,
    session=None,
) -> AuditLog:
    """Log an audit event to the database.

    This is the single entry point for all audit logging in PipelineIQ.
    All pipeline stages use this function to record events.

    Args:
        lead_id: The ID of the lead this event relates to.
        event_type: The type of event (must be in EVENT_TYPES or a
            custom type starting with a letter).
        message: A human-readable description of the event.
        session: An optional async database session.  If omitted, a new
            session will be created and committed.  Provide a session
            when you need the log entry to be part of a larger transaction.

    Returns:
        The created ``AuditLog`` ORM instance.

    Raises:
        ValueError: If ``event_type`` is empty or ``lead_id`` is empty.
    """
    if not lead_id or not lead_id.strip():
        raise ValueError("lead_id is required and must not be empty")
    if not event_type or not event_type.strip():
        raise ValueError("event_type is required and must not be empty")
    if not message:
        message = ""

    entry = AuditLog(
        lead_id=lead_id.strip(),
        event_type=event_type.strip().lower(),
        message=message.strip(),
    )

    if session is not None:
        # Use provided session — caller is responsible for commit
        session.add(entry)
        return entry

    # Create a new session, persist, and commit
    async with async_session_factory() as new_session:
        try:
            new_session.add(entry)
            await new_session.commit()
            await new_session.refresh(entry)
        except Exception:
            await new_session.rollback()
            logger.error(
                "Failed to persist audit log for lead %s (event=%s): %s",
                lead_id,
                event_type,
                message[:100],
            )
            raise

    return entry


async def log_events_batch(
    entries: list[dict],
    *,
    session=None,
) -> list[AuditLog]:
    """Log multiple audit events in a single transaction.

    Args:
        entries: A list of dicts, each with keys ``lead_id``, ``event_type``,
            and ``message``.
        session: An optional async database session.

    Returns:
        A list of created ``AuditLog`` ORM instances.
    """
    logs: list[AuditLog] = []
    for entry_data in entries:
        lead_id = entry_data.get("lead_id", "")
        event_type = entry_data.get("event_type", "")
        message = entry_data.get("message", "")

        log_entry = AuditLog(
            lead_id=lead_id.strip() if lead_id else "",
            event_type=event_type.strip().lower() if event_type else "",
            message=message.strip() if message else "",
        )
        logs.append(log_entry)

    if session is not None:
        for log_entry in logs:
            session.add(log_entry)
        return logs

    async with async_session_factory() as new_session:
        try:
            for log_entry in logs:
                new_session.add(log_entry)
            await new_session.commit()
        except Exception:
            await new_session.rollback()
            logger.error("Failed to persist batch audit logs: %d entries", len(entries))
            raise

    return logs