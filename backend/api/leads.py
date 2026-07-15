"""
Lead Management API endpoints for PipelineIQ.

Provides REST endpoints for lead CRUD operations and dashboard queries:
- POST /lead — Create a new lead
- GET /lead/{id} — Retrieve a single lead with full details
- GET /leads — List all leads with filtering, sorting, pagination
- GET /pending-approvals — List leads awaiting human approval
- GET /dashboard-stats — Dashboard statistics (counts, pipeline status)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from backend.database.session import async_session_factory
from backend.models.schemas import (
    AuditLogResponse,
    ClassificationResponse,
    DraftEmailResponse,
    EnrichmentResponse,
    LeadCreate,
    LeadResponse,
    ScoreResponse,
)
from backend.models.sqlalchemy_models import (
    Approval,
    AuditLog,
    Classification,
    DraftEmail,
    Enrichment,
    Lead,
    Score,
)
from backend.utils.audit_logger import log_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Leads"])


# ── Response schemas (additional) ────────────────────────────────────────


class LeadDetailResponse(LeadResponse):
    """Full lead detail including all related data."""

    enrichment: Optional[EnrichmentResponse] = None
    scores: list[ScoreResponse] = Field(default_factory=list)
    classifications: list[ClassificationResponse] = Field(default_factory=list)
    draft_emails: list[DraftEmailResponse] = Field(default_factory=list)
    audit_logs: list[AuditLogResponse] = Field(default_factory=list)


class LeadListResponse(BaseModel):
    """Paginated lead list response."""

    total: int
    filtered_count: int
    leads: list[LeadResponse]


class PendingApprovalResponse(BaseModel):
    """A lead awaiting human approval."""

    lead_id: str
    lead_name: str
    lead_email: str
    lead_company: str
    draft_subject: str
    draft_status: str
    draft_created: Optional[datetime] = None
    score: Optional[int] = None
    classification: Optional[str] = None


class PendingApprovalsResponse(BaseModel):
    """List of pending approvals."""

    total: int
    pending: list[PendingApprovalResponse]


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics."""

    total_leads: int
    leads_with_scores: int
    leads_classified: int
    leads_with_drafts: int
    pending_approvals: int
    approved: int
    rejected: int
    emails_sent: int
    avg_score: float
    hot_leads: int
    nurture_leads: int
    disqualify_leads: int


# ── POST /lead — Create a new lead ───────────────────────────────────────


@router.post(
    "/lead",
    summary="Create a new lead",
    response_model=LeadResponse,
    status_code=201,
)
async def create_lead(payload: LeadCreate):
    """
    Create a new lead in the pipeline.

    Validates the input and persists the lead to the database.
    Logs a ``lead_created`` audit event.

    Args:
        payload: Lead data (name, email, company, role, industry, buying_signals).

    Returns:
        The created lead with its generated ID and timestamp.
    """
    async with async_session_factory() as session:
        try:
            # Check for duplicate email
            from sqlalchemy import select

            existing = await session.execute(
                select(Lead).where(Lead.email == payload.email)
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Lead with email '{payload.email}' already exists",
                )

            db_lead = Lead(
                name=payload.name.strip(),
                email=payload.email.strip().lower(),
                company=payload.company.strip(),
                role=payload.role.strip() if payload.role else None,
                industry=payload.industry.strip() if payload.industry else None,
                buying_signals=payload.buying_signals or [],
            )
            session.add(db_lead)
            await session.flush()

            # Audit log
            await log_event(
                lead_id=db_lead.id,
                event_type="lead_created",
                message=(
                    f"Lead created: {db_lead.name} <{db_lead.email}> "
                    f"— {db_lead.company}"
                ),
                session=session,
            )

            await session.commit()
            await session.refresh(db_lead)

            logger.info(
                "Lead created: %s (%s) — %s [id=%s]",
                db_lead.name,
                db_lead.email,
                db_lead.company,
                db_lead.id,
            )

            return LeadResponse(
                id=db_lead.id,
                name=db_lead.name,
                email=db_lead.email,
                company=db_lead.company,
                role=db_lead.role,
                industry=db_lead.industry,
                buying_signals=db_lead.buying_signals,
                created_at=db_lead.created_at,
            )

        except HTTPException:
            await session.rollback()
            raise
        except Exception as exc:
            await session.rollback()
            logger.error("Failed to create lead: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create lead: {str(exc)}",
            )


# ── GET /lead/{id} — Retrieve a single lead ──────────────────────────────


@router.get(
    "/lead/{lead_id}",
    summary="Retrieve a lead with full details",
    response_model=LeadDetailResponse,
)
async def get_lead(lead_id: str):
    """
    Retrieve a single lead by ID, including all related data.

    Returns the lead with its enrichment, scores, classifications,
    draft emails, and audit logs.

    Args:
        lead_id: The ID of the lead.

    Returns:
        Full lead detail with all related data.
    """
    async with async_session_factory() as session:
        try:
            from sqlalchemy import select as sa_select
            from sqlalchemy.orm import selectinload

            stmt = (
                sa_select(Lead)
                .options(
                    selectinload(Lead.enrichment),
                    selectinload(Lead.scores),
                    selectinload(Lead.classifications),
                    selectinload(Lead.draft_emails),
                    selectinload(Lead.approvals),
                )
                .where(Lead.id == lead_id)
            )
            result = await session.execute(stmt)
            db_lead = result.scalar_one_or_none()
            if db_lead is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Lead {lead_id} not found",
                )

            # Build enrichment response
            enrichment = None
            if db_lead.enrichment:
                enrichment = EnrichmentResponse(
                    id=db_lead.enrichment.id,
                    lead_id=db_lead.enrichment.lead_id,
                    company_size=db_lead.enrichment.company_size,
                    employee_count=db_lead.enrichment.employee_count,
                    company_location=db_lead.enrichment.company_location,
                    company_industry=db_lead.enrichment.company_industry,
                )

            # Build scores
            scores = [
                ScoreResponse(
                    id=s.id,
                    lead_id=s.lead_id,
                    score=s.score,
                    confidence=s.confidence,
                    reasons=s.reasons or [],
                )
                for s in db_lead.scores
            ]

            # Build classifications
            classifications = [
                ClassificationResponse(
                    id=c.id,
                    lead_id=c.lead_id,
                    category=c.category,
                    explanation=c.explanation,
                )
                for c in db_lead.classifications
            ]

            # Build draft emails
            draft_emails = [
                DraftEmailResponse(
                    id=d.id,
                    lead_id=d.lead_id,
                    subject=d.subject,
                    body=d.body,
                    status=d.status,
                )
                for d in db_lead.draft_emails
            ]

            # Build audit logs
            from sqlalchemy import select as sa_select

            audit_logs_query = (
                sa_select(AuditLog)
                .where(AuditLog.lead_id == lead_id)
                .order_by(AuditLog.timestamp.desc())
            )
            audit_result = await session.execute(audit_logs_query)
            audit_logs = [
                AuditLogResponse(
                    id=log.id,
                    lead_id=log.lead_id,
                    event_type=log.event_type,
                    message=log.message,
                    timestamp=log.timestamp,
                )
                for log in audit_result.scalars().all()
            ]

            return LeadDetailResponse(
                id=db_lead.id,
                name=db_lead.name,
                email=db_lead.email,
                company=db_lead.company,
                role=db_lead.role,
                industry=db_lead.industry,
                buying_signals=db_lead.buying_signals,
                created_at=db_lead.created_at,
                enrichment=enrichment,
                scores=scores,
                classifications=classifications,
                draft_emails=draft_emails,
                audit_logs=audit_logs,
            )

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to retrieve lead %s: %s", lead_id, exc)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve lead: {str(exc)}",
            )


# ── GET /leads — List all leads ──────────────────────────────────────────


@router.get(
    "/leads",
    summary="List all leads",
    response_model=LeadListResponse,
)
async def list_leads(
    search: Optional[str] = Query(
        None,
        description="Search term for name, email, or company",
    ),
    industry: Optional[str] = Query(
        None,
        description="Filter by industry",
    ),
    sort_by: str = Query(
        "created_at",
        description="Field to sort by: 'created_at', 'name', 'email', 'company'",
    ),
    sort_order: str = Query(
        "desc",
        description="Sort order: 'desc' (default) or 'asc'",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Maximum number of leads to return (1-500)",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of leads to skip (for pagination)",
    ),
):
    """
    List all leads with optional search, filtering, sorting, and pagination.

    Args:
        search: Search term (matches name, email, or company).
        industry: Filter by industry.
        sort_by: Field to sort by (created_at, name, email, company).
        sort_order: 'asc' or 'desc' (default: 'desc').
        limit: Max entries (default 50, max 500).
        offset: Pagination offset.

    Returns:
        A paginated list of leads.
    """
    # Normalize Query-wrapped defaults when called directly (not via FastAPI)
    if not isinstance(search, str):
        search = None
    if not isinstance(industry, str):
        industry = None
    if not isinstance(sort_by, str):
        sort_by = "created_at"
    if not isinstance(sort_order, str):
        sort_order = "desc"
    if not isinstance(limit, int):
        limit = 50
    if not isinstance(offset, int):
        offset = 0

    from sqlalchemy import func, or_, select

    async with async_session_factory() as session:
        try:
            # Build base query
            base_query = select(Lead)

            # Apply search filter
            if search:
                search_term = f"%{search.strip()}%"
                base_query = base_query.where(
                    or_(
                        Lead.name.ilike(search_term),
                        Lead.email.ilike(search_term),
                        Lead.company.ilike(search_term),
                    )
                )

            # Apply industry filter
            if industry:
                base_query = base_query.where(Lead.industry == industry.strip())

            # Count total
            count_all_stmt = select(func.count()).select_from(Lead)
            total_result = await session.execute(count_all_stmt)
            total_count = total_result.scalar() or 0

            # Count filtered
            count_filtered_stmt = select(func.count()).select_from(base_query.subquery())
            filtered_result = await session.execute(count_filtered_stmt)
            filtered_count = filtered_result.scalar() or 0

            # Apply sorting
            valid_sort_fields = {"created_at", "name", "email", "company"}
            if sort_by not in valid_sort_fields:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid sort_by '{sort_by}'. "
                        f"Valid fields: {', '.join(valid_sort_fields)}"
                    ),
                )

            order_col = getattr(Lead, sort_by)
            if sort_order == "desc":
                order_col = order_col.desc()
            else:
                order_col = order_col.asc()

            base_query = base_query.order_by(order_col)

            # Apply pagination
            base_query = base_query.offset(offset).limit(limit)

            # Execute
            result = await session.execute(base_query)
            leads = result.scalars().all()

            return LeadListResponse(
                total=total_count,
                filtered_count=filtered_count,
                leads=[
                    LeadResponse(
                        id=lead.id,
                        name=lead.name,
                        email=lead.email,
                        company=lead.company,
                        role=lead.role,
                        industry=lead.industry,
                        buying_signals=lead.buying_signals,
                        created_at=lead.created_at,
                    )
                    for lead in leads
                ],
            )

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to list leads: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list leads: {str(exc)}",
            )


# ── GET /pending-approvals ────────────────────────────────────────────────


@router.get(
    "/pending-approvals",
    summary="List leads awaiting human approval",
    response_model=PendingApprovalsResponse,
)
async def list_pending_approvals():
    """
    List all leads with draft emails that are awaiting human approval.

    A lead is "pending approval" if it has a draft email with status
    "draft" or "reviewed" and no corresponding approval record exists.

    Returns:
        A list of pending approval items with lead and draft details.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async with async_session_factory() as session:
        try:
            # Find all leads with draft emails in "draft" or "reviewed" status
            # Use selectinload to eagerly fetch scores and classifications
            leads_stmt = (
                select(Lead)
                .join(DraftEmail, Lead.id == DraftEmail.lead_id)
                .where(DraftEmail.status.in_(["draft", "reviewed"]))
                .options(
                    selectinload(Lead.scores),
                    selectinload(Lead.classifications),
                    selectinload(Lead.draft_emails),
                    selectinload(Lead.approvals),
                )
                .order_by(Lead.created_at.desc())
            )
            leads_result = await session.execute(leads_stmt)
            loaded_leads = leads_result.scalars().all()

            pending = []
            for lead in loaded_leads:
                # Get the latest pending draft
                pending_drafts = [d for d in lead.draft_emails if d.status in ("draft", "reviewed")]
                if not pending_drafts:
                    continue
                draft = pending_drafts[-1]

                # Check if there's already an approval record
                existing_approval = None
                if lead.approvals:
                    latest_appr = sorted(lead.approvals, key=lambda a: a.timestamp, reverse=True)
                    existing_approval = latest_appr[0] if latest_appr else None

                # If already approved, skip
                if existing_approval and existing_approval.approved:
                    continue

                # Get latest score
                latest_score = None
                if lead.scores:
                    latest_score = lead.scores[-1].score

                # Get latest classification
                latest_classification = None
                if lead.classifications:
                    latest_classification = lead.classifications[-1].category

                pending.append(
                    PendingApprovalResponse(
                        lead_id=lead.id,
                        lead_name=lead.name,
                        lead_email=lead.email,
                        lead_company=lead.company,
                        draft_subject=draft.subject,
                        draft_status=draft.status,
                        draft_created=None,  # DraftEmail has no created_at column
                        score=latest_score,
                        classification=latest_classification,
                    )
                )

            return PendingApprovalsResponse(
                total=len(pending),
                pending=pending,
            )

        except Exception as exc:
            logger.error("Failed to list pending approvals: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list pending approvals: {str(exc)}",
            )


# ── GET /dashboard-stats ─────────────────────────────────────────────────


@router.get(
    "/dashboard-stats",
    summary="Get dashboard statistics",
    response_model=DashboardStatsResponse,
)
async def get_dashboard_stats():
    """
    Get aggregate statistics for the dashboard.

    Returns counts of leads, scores, classifications, drafts,
    approvals, rejections, sent emails, and average scores.

    Returns:
        Dashboard statistics object.
    """
    from sqlalchemy import func, select

    async with async_session_factory() as session:
        try:
            # Total leads
            total_stmt = select(func.count()).select_from(Lead)
            total_leads = (await session.execute(total_stmt)).scalar() or 0

            # Leads with scores
            scores_stmt = (
                select(func.count(func.distinct(Score.lead_id)))
                .select_from(Score)
            )
            leads_with_scores = (await session.execute(scores_stmt)).scalar() or 0

            # Leads classified
            class_stmt = (
                select(func.count(func.distinct(Classification.lead_id)))
                .select_from(Classification)
            )
            leads_classified = (await session.execute(class_stmt)).scalar() or 0

            # Leads with drafts
            drafts_stmt = (
                select(func.count(func.distinct(DraftEmail.lead_id)))
                .select_from(DraftEmail)
            )
            leads_with_drafts = (await session.execute(drafts_stmt)).scalar() or 0

            # Pending approvals (unique lead_ids with draft emails NOT yet approved)
            pending_stmt = (
                select(func.count(func.distinct(DraftEmail.lead_id)))
                .select_from(DraftEmail)
                .where(DraftEmail.status.in_(["draft", "reviewed"]))
            )
            pending_approvals = (await session.execute(pending_stmt)).scalar() or 0

            # Approved (approval records with approved=True)
            approved_stmt = (
                select(func.count())
                .select_from(Approval)
                .where(Approval.approved == True)
            )
            approved = (await session.execute(approved_stmt)).scalar() or 0

            # Rejected (approval records with approved=False)
            rejected_stmt = (
                select(func.count())
                .select_from(Approval)
                .where(Approval.approved == False)
            )
            rejected = (await session.execute(rejected_stmt)).scalar() or 0

            # Emails sent (audit logs with event_type='email_sent')
            sent_stmt = (
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.event_type == "email_sent")
            )
            emails_sent = (await session.execute(sent_stmt)).scalar() or 0

            # Average score
            avg_stmt = select(func.avg(Score.score)).select_from(Score)
            avg_result = await session.execute(avg_stmt)
            avg_score = avg_result.scalar() or 0.0

            # Classification counts
            hot_stmt = (
                select(func.count())
                .select_from(Classification)
                .where(Classification.category == "hot")
            )
            hot_leads = (await session.execute(hot_stmt)).scalar() or 0

            nurture_stmt = (
                select(func.count())
                .select_from(Classification)
                .where(Classification.category == "nurture")
            )
            nurture_leads = (await session.execute(nurture_stmt)).scalar() or 0

            disqualify_stmt = (
                select(func.count())
                .select_from(Classification)
                .where(Classification.category == "disqualify")
            )
            disqualify_leads = (await session.execute(disqualify_stmt)).scalar() or 0

            return DashboardStatsResponse(
                total_leads=total_leads,
                leads_with_scores=leads_with_scores,
                leads_classified=leads_classified,
                leads_with_drafts=leads_with_drafts,
                pending_approvals=pending_approvals,
                approved=approved,
                rejected=rejected,
                emails_sent=emails_sent,
                avg_score=round(avg_score, 1),
                hot_leads=hot_leads,
                nurture_leads=nurture_leads,
                disqualify_leads=disqualify_leads,
            )

        except Exception as exc:
            logger.error("Failed to get dashboard stats: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get dashboard stats: {str(exc)}",
            )