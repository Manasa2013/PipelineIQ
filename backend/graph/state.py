"""
LangGraph state definition for PipelineIQ.

The state carries all data produced by each agent node through the
pipeline graph.
"""

from typing import Optional

from typing_extensions import TypedDict


class PipelineState(TypedDict):
    """
    Shared state flowing through the LangGraph.

    Each key is populated by a specific agent node and consumed
    by downstream nodes.
    """

    # ── Raw input / Lead data ─────────────────────────────────────────
    lead: Optional[dict]  # e.g. {"name": "...", "email": "...", "company": "..."}

    # ── Enrichment output ─────────────────────────────────────────────
    enrichment: Optional[dict]  # e.g. {"company_size": "50-200", "employee_count": 150, ...}

    # ── Scoring output ────────────────────────────────────────────────
    score: Optional[dict]  # e.g. {"score": 0.87, "confidence": 0.92, "reason": "..."}

    # ── Classification output ─────────────────────────────────────────
    classification: Optional[dict]  # e.g. {"category": "hot", "explanation": "..."}

    # ── Outreach / email output ───────────────────────────────────────
    draft_email: Optional[dict]  # e.g. {"subject": "...", "body": "...", "status": "draft"}

    # ── Approval tracking ─────────────────────────────────────────────
    approval_status: Optional[dict]  # e.g. {"approved": True, "approved_by": "..."}

    # ── Audit trail ────────────────────────────────────────────────────
    logs: list[dict]  # e.g. [{"event_type": "intake", "message": "Lead received", ...}]