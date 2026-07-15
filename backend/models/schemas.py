"""
Pydantic schemas for PipelineIQ.

Defines request / response shapes for the API layer.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ── Lead ────────────────────────────────────────────────────────────────


class LeadCreate(BaseModel):
    """Schema for creating a new lead."""

    name: str = Field(..., max_length=255, examples=["Jane Doe"])
    email: EmailStr = Field(..., examples=["jane@acme.com"])
    company: str = Field(..., max_length=255, examples=["Acme Corp"])
    role: Optional[str] = Field(None, max_length=255, examples=["CTO"])
    industry: Optional[str] = Field(None, max_length=255, examples=["SaaS"])
    buying_signals: Optional[list[str]] = Field(
        None, examples=[["visited pricing page", "requested demo"]]
    )


class LeadUpdate(BaseModel):
    """Schema for updating an existing lead (all fields optional)."""

    name: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None
    company: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=255)
    buying_signals: Optional[list[str]] = None


class LeadResponse(BaseModel):
    """Schema returned when reading a lead."""

    id: str
    name: str
    email: str
    company: str
    role: Optional[str] = None
    industry: Optional[str] = None
    buying_signals: Optional[list[str]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Enrichment ──────────────────────────────────────────────────────────


class EnrichmentCreate(BaseModel):
    """Schema for enriching a lead with company data."""

    company_size: Optional[str] = Field(None, max_length=50, examples=["50-200"])
    employee_count: Optional[int] = Field(None, ge=1, examples=[150])
    company_location: Optional[str] = Field(None, max_length=255, examples=["San Francisco, CA"])
    company_industry: Optional[str] = Field(None, max_length=255, examples=["Enterprise Software"])


class EnrichmentResponse(BaseModel):
    """Schema returned when reading enrichment data."""

    id: str
    lead_id: str
    company_size: Optional[str] = None
    employee_count: Optional[int] = None
    company_location: Optional[str] = None
    company_industry: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Score ───────────────────────────────────────────────────────────────


class ScoreCreate(BaseModel):
    """Schema for scoring a lead."""

    score: int = Field(..., ge=0, le=100, examples=[78])
    confidence: float = Field(..., ge=0.0, le=1.0, examples=[0.92])
    reasons: list[str] = Field(
        default_factory=list,
        examples=[["Strong company size fit", "Executive role", "Business email domain"]],
    )


class ScoreResponse(BaseModel):
    """Schema returned when reading a lead score."""

    id: str
    lead_id: str
    score: int
    confidence: float
    reasons: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ── Classification ──────────────────────────────────────────────────────


class ClassificationCreate(BaseModel):
    """Schema for classifying a lead."""

    category: str = Field(..., max_length=100, examples=["hot", "warm", "cold"])
    explanation: Optional[str] = Field(None, examples=["Matched all ICP criteria"])


class ClassificationResponse(BaseModel):
    """Schema returned when reading a classification."""

    id: str
    lead_id: str
    category: str
    explanation: Optional[str] = None

    model_config = {"from_attributes": True}


# ── DraftEmail ──────────────────────────────────────────────────────────


class DraftEmailCreate(BaseModel):
    """Schema for creating a draft email."""

    subject: str = Field(..., max_length=255, examples=["Personalized outreach – Acme Corp"])
    body: str = Field(..., examples=["Hi Jane,\n\nI noticed Acme Corp ..."])
    status: str = Field("draft", max_length=50, examples=["draft", "reviewed", "sent"])


class DraftEmailUpdate(BaseModel):
    """Schema for updating a draft email."""

    subject: Optional[str] = Field(None, max_length=255)
    body: Optional[str] = None
    status: Optional[str] = Field(None, max_length=50)


class DraftEmailResponse(BaseModel):
    """Schema returned when reading a draft email."""

    id: str
    lead_id: str
    subject: str
    body: str
    status: str

    model_config = {"from_attributes": True}


# ── Approval ────────────────────────────────────────────────────────────


class ApprovalCreate(BaseModel):
    """Schema for recording an approval decision."""

    approved: bool = Field(..., examples=[True])
    approved_by: Optional[str] = Field(None, max_length=255, examples=["manager@example.com"])


class ApprovalResponse(BaseModel):
    """Schema returned when reading an approval record."""

    id: str
    lead_id: str
    approved: bool
    approved_by: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}


# ── AuditLog ────────────────────────────────────────────────────────────


class AuditLogResponse(BaseModel):
    """Schema returned when reading audit log entries."""

    id: str
    lead_id: str
    event_type: str
    message: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}