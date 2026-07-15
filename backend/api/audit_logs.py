"""
Audit Log API endpoints for PipelineIQ.

Provides endpoints for querying audit logs:
- GET /logs/{lead_id} — Retrieve all logs for a lead, with filtering and sorting
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.database.session import async_session_factory
from backend.models.sqlalchemy_models import AuditLog, Lead
from backend.utils.audit_logger import EVENT_TYPES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Audit Logs"])


# ── Response schema ─────────────────────────────────────────────────────


class AuditLogEntryResponse(BaseModel):
    """Schema for a single audit log entry in the response."""

    id: str
    lead_id: str
    event_type: str
    message: Optional[str] = None
    timestamp: datetime


class AuditLogListResponse(BaseModel):
    """Schema for the audit log list response."""

    total: int
    filtered_count: int
    entries: list[AuditLogEntryResponse]


# ── API endpoint ────────────────────────────────────────────────────────


@router.get(
    "/logs/{lead_id}",
    summary="Retrieve audit logs for a lead",
    response_model=AuditLogListResponse,
)
async def get_audit_logs(
    lead_id: str,
    event_type: Optional[str] = Query(
        None,
        description="Filter by event type (e.g. 'scoring', 'approval', 'email_sent')",
    ),
    sort_by: str = Query(
        "timestamp",
        description="Field to sort by: 'timestamp' (default) or 'event_type'",
    ),
    sort_order: str = Query(
        "desc",
        description="Sort order: 'desc' (default) or 'asc'",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of entries to return (1-1000)",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of entries to skip (for pagination)",
    ),
):
    """
    Retrieve audit log entries for a specific lead.

    Supports filtering by event type, sorting by timestamp or event type,
    and pagination via limit/offset.

    Args:
        lead_id: The ID of the lead to retrieve logs for.
        event_type: Optional filter — only return logs of this type.
        sort_by: Field to sort by (\"timestamp\" or \"event_type\").
        sort_order: \"asc\" or \"desc\" (default: \"desc\").
        limit: Max entries to return (default 100, max 1000).
        offset: Number of entries to skip (for pagination).

    Returns:
        An ``AuditLogListResponse`` with total count, filtered count, and entries.
    """
    # Normalize Query-wrapped defaults when called directly (not via FastAPI)
    if not isinstance(event_type, str):
        event_type = None
    if not isinstance(sort_by, str):
        sort_by = "timestamp"
    if not isinstance(sort_order, str):
        sort_order = "desc"
    if not isinstance(limit, int):
        limit = 100
    if not isinstance(offset, int):
        offset = 0

    # Validate event_type if provided
    if event_type is not None:
        event_type = event_type.strip().lower()
        if event_type not in EVENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid event_type '{event_type}'. "
                    f"Valid types: {', '.join(sorted(EVENT_TYPES))}"
                ),
            )

    # Validate sort fields
    valid_sort_fields = {"timestamp", "event_type"}
    if sort_by not in valid_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by '{sort_by}'. Valid fields: {', '.join(valid_sort_fields)}",
        )

    if sort_order not in ("asc", "desc"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_order '{sort_order}'. Use 'asc' or 'desc'.",
        )

    async with async_session_factory() as session:
        try:
            # Verify lead exists
            db_lead = await session.get(Lead, lead_id)
            if db_lead is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Lead {lead_id} not found",
                )

            from sqlalchemy import func, select

            # Build the base query
            base_query = select(AuditLog).where(AuditLog.lead_id == lead_id)

            # Count total logs for this lead
            count_all_stmt = select(func.count()).select_from(AuditLog).where(
                AuditLog.lead_id == lead_id
            )
            total_result = await session.execute(count_all_stmt)
            total_count = total_result.scalar() or 0

            # Apply event_type filter
            if event_type:
                base_query = base_query.where(AuditLog.event_type == event_type)

            # Count filtered results
            count_filtered_stmt = select(func.count()).select_from(base_query.subquery())
            filtered_result = await session.execute(count_filtered_stmt)
            filtered_count = filtered_result.scalar() or 0

            # Apply sorting
            if sort_by == "timestamp":
                order_col = AuditLog.timestamp
            else:
                order_col = AuditLog.event_type

            if sort_order == "desc":
                order_col = order_col.desc()
            else:
                order_col = order_col.asc()

            base_query = base_query.order_by(order_col)

            # Apply pagination
            base_query = base_query.offset(offset).limit(limit)

            # Execute
            result = await session.execute(base_query)
            entries = result.scalars().all()

            return AuditLogListResponse(
                total=total_count,
                filtered_count=filtered_count,
                entries=[
                    AuditLogEntryResponse(
                        id=entry.id,
                        lead_id=entry.lead_id,
                        event_type=entry.event_type,
                        message=entry.message,
                        timestamp=entry.timestamp,
                    )
                    for entry in entries
                ],
            )

        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "Failed to retrieve audit logs for lead %s: %s",
                lead_id,
                exc,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve audit logs: {str(exc)}",
            )