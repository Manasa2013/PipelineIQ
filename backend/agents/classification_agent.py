"""
Classification Agent — classifies a lead as hot, nurture, or disqualify.

Classification Rules
--------------------
- score >= 80  →  "hot"          (high-fit lead, proceed to outreach)
- score >= 50  →  "nurture"      (medium-fit lead, add to nurture campaign)
- score < 50   →  "disqualify"   (low-fit lead, disqualified)

Output
------
- category: One of "hot", "nurture", "disqualify"
- explanation: Human-readable reason for the classification

Responsibilities
----------------
1. Read the score from pipeline state.
2. Apply classification rules to determine the category.
3. Build a detailed explanation.
4. Persist the classification record to the database.
5. Create an audit log entry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.database.session import async_session_factory
from backend.models.sqlalchemy_models import AuditLog, Classification, Lead


# ── Classification thresholds ────────────────────────────────────────────

HOT_THRESHOLD = 80
NURTURE_THRESHOLD = 50


def classify_score(score: int | None) -> tuple[str, str]:
    """Classify a numeric score into a category with explanation.

    Args:
        score: The lead score (0-100), or None if unavailable.

    Returns:
        A tuple of (category, explanation).
    """
    if score is None:
        return (
            "disqualify",
            "No score available — lead cannot be evaluated.",
        )

    if score >= HOT_THRESHOLD:
        return (
            "hot",
            f"Score {score}/100 is at or above the hot threshold of {HOT_THRESHOLD}. "
            f"Lead shows strong alignment with ideal customer profile and is ready for outreach.",
        )
    elif score >= NURTURE_THRESHOLD:
        return (
            "nurture",
            f"Score {score}/100 is at or above the nurture threshold of {NURTURE_THRESHOLD} "
            f"but below the hot threshold of {HOT_THRESHOLD}. "
            f"Lead shows moderate fit and should be added to a nurture campaign.",
        )
    else:
        return (
            "disqualify",
            f"Disqualify: Score {score}/100 is below the nurture threshold of {NURTURE_THRESHOLD}. "
            f"Lead does not meet minimum qualification criteria.",
        )


async def classification_agent(state: dict) -> dict:
    """
    Classify the lead based on the score.

    This function is the LangGraph node for classification.  It reads the
    score from the current graph state, applies the classification rules,
    persists the classification record, and returns an updated state dict.

    Args:
        state: Current ``PipelineState`` dict containing at least
            ``lead``, ``score``, and ``logs`` keys.

    Returns:
        Dict with updated ``classification``, ``lead`` (with classification
        merged in), and ``logs`` (appended audit entry).
    """
    lead = state.get("lead", {})
    score_data = state.get("score", {})
    logs = list(state.get("logs", []))

    # ── 1. Extract score value ──────────────────────────────────────────
    score_value = score_data.get("score") if score_data else None

    # ── 2. Apply classification rules ───────────────────────────────────
    category, explanation = classify_score(score_value)

    classification = {
        "category": category,
        "explanation": explanation,
    }

    # ── 3. Persist classification record in database ────────────────────
    lead_id = lead.get("id")
    if lead_id:
        async with async_session_factory() as session:
            try:
                # Verify lead exists
                db_lead = await session.get(Lead, lead_id)
                if db_lead is not None:
                    classification_record = Classification(
                        lead_id=lead_id,
                        category=category,
                        explanation=explanation,
                    )
                    session.add(classification_record)

                    # ── 4. Persist audit log ────────────────────────────
                    audit_entry = AuditLog(
                        lead_id=lead_id,
                        event_type="classification",
                        message=(
                            f"Classified lead {lead.get('name', 'unknown')} "
                            f"as '{category}' — {explanation}"
                        ),
                    )
                    session.add(audit_entry)
                    await session.commit()

            except Exception:
                await session.rollback()
                # Log the failure but don't crash the pipeline
                log_entry = {
                    "event_type": "classification_error",
                    "message": (
                        f"Failed to persist classification for lead {lead_id}: "
                        f"database error"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return {
                    "classification": classification,
                    "lead": lead,
                    "logs": logs + [log_entry],
                }

    # ── 5. Build clean output state ────────────────────────────────────
    # Merge classification into lead for downstream nodes
    enriched_lead = dict(lead)
    enriched_lead["classification"] = category

    log_entry = {
        "event_type": "classification",
        "message": (
            f"Classified lead {lead.get('name', 'unknown')} "
            f"as '{category}' — {explanation}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "classification": classification,
        "lead": enriched_lead,
        "logs": logs + [log_entry],
    }