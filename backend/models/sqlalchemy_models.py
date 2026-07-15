"""
SQLAlchemy ORM models for PipelineIQ.

Each table maps to a domain concept in the lead qualification pipeline.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


# ── Lead ────────────────────────────────────────────────────────────────


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(
        String(12), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=True)
    industry: Mapped[str] = mapped_column(String(255), nullable=True)
    buying_signals: Mapped[list] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # Stores the LangGraph thread_id so the graph can be resumed after
    # the human-in-the-loop interrupt at the approval gate.
    pipeline_thread_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)

    # Relationships
    enrichment: Mapped["Enrichment"] = relationship(
        back_populates="lead", uselist=False, cascade="all, delete-orphan"
    )
    scores: Mapped[list["Score"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    classifications: Mapped[list["Classification"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    draft_emails: Mapped[list["DraftEmail"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Lead(id={self.id!r}, name={self.name!r}, email={self.email!r})>"


# ── Enrichment ──────────────────────────────────────────────────────────


class Enrichment(Base):
    __tablename__ = "enrichments"

    id: Mapped[str] = mapped_column(
        String(12), primary_key=True, default=_uuid
    )
    lead_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    company_size: Mapped[str] = mapped_column(String(50), nullable=True)
    employee_count: Mapped[int] = mapped_column(Integer, nullable=True)
    company_location: Mapped[str] = mapped_column(String(255), nullable=True)
    company_industry: Mapped[str] = mapped_column(String(255), nullable=True)

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="enrichment")

    def __repr__(self) -> str:
        return f"<Enrichment(id={self.id!r}, lead_id={self.lead_id!r})>"


# ── Score ───────────────────────────────────────────────────────────────


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(
        String(12), primary_key=True, default=_uuid
    )
    lead_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasons: Mapped[list] = mapped_column(JSON, nullable=True, default=list)

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="scores")

    def __repr__(self) -> str:
        return f"<Score(id={self.id!r}, lead_id={self.lead_id!r}, score={self.score})>"


# ── Classification ──────────────────────────────────────────────────────


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[str] = mapped_column(
        String(12), primary_key=True, default=_uuid
    )
    lead_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=True)

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="classifications")

    def __repr__(self) -> str:
        return f"<Classification(id={self.id!r}, lead_id={self.lead_id!r}, category={self.category!r})>"


# ── DraftEmail ──────────────────────────────────────────────────────────


class DraftEmail(Base):
    __tablename__ = "draft_emails"

    id: Mapped[str] = mapped_column(
        String(12), primary_key=True, default=_uuid
    )
    lead_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft"
    )

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="draft_emails")

    def __repr__(self) -> str:
        return f"<DraftEmail(id={self.id!r}, lead_id={self.lead_id!r}, status={self.status!r})>"


# ── Approval ────────────────────────────────────────────────────────────


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        String(12), primary_key=True, default=_uuid
    )
    lead_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    approved_by: Mapped[str] = mapped_column(String(255), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="approvals")

    def __repr__(self) -> str:
        return f"<Approval(id={self.id!r}, lead_id={self.lead_id!r}, approved={self.approved})>"


# ── AuditLog ────────────────────────────────────────────────────────────


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(12), primary_key=True, default=_uuid
    )
    lead_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    lead: Mapped["Lead"] = relationship(back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id!r}, lead_id={self.lead_id!r}, event={self.event_type!r})>"