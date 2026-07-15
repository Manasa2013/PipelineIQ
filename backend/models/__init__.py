"""
SQLAlchemy ORM models and Pydantic schemas for PipelineIQ.
"""

from backend.models.sqlalchemy_models import (
    Approval,
    AuditLog,
    Classification,
    DraftEmail,
    Enrichment,
    Lead,
    Score,
)

from backend.models.schemas import (
    ApprovalCreate,
    ApprovalResponse,
    AuditLogResponse,
    ClassificationCreate,
    ClassificationResponse,
    DraftEmailCreate,
    DraftEmailResponse,
    DraftEmailUpdate,
    EnrichmentCreate,
    EnrichmentResponse,
    LeadCreate,
    LeadResponse,
    LeadUpdate,
    ScoreCreate,
    ScoreResponse,
)

__all__ = [
    # ORM
    "Lead",
    "Enrichment",
    "Score",
    "Classification",
    "DraftEmail",
    "Approval",
    "AuditLog",
    # Schemas - Lead
    "LeadCreate",
    "LeadUpdate",
    "LeadResponse",
    # Schemas - Enrichment
    "EnrichmentCreate",
    "EnrichmentResponse",
    # Schemas - Score
    "ScoreCreate",
    "ScoreResponse",
    # Schemas - Classification
    "ClassificationCreate",
    "ClassificationResponse",
    # Schemas - DraftEmail
    "DraftEmailCreate",
    "DraftEmailUpdate",
    "DraftEmailResponse",
    # Schemas - Approval
    "ApprovalCreate",
    "ApprovalResponse",
    # Schemas - AuditLog
    "AuditLogResponse",
]