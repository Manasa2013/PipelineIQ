"""
Fairness Validation Module for PipelineIQ.

Ensures that scoring is consistent across leads with identical
non-demographic attributes.  Specifically, if two leads share the
same company, role, industry, and enrichment data, their scores MUST
be identical regardless of their names.

Responsibilities
----------------
1. Compare two leads with matching profiles → verify identical scores.
2. Flag leads where a fairness violation is detected.
3. Create audit-log entries for violations.
4. Batch-scan multiple leads to detect name-based bias.

Design
------
The module is designed to be called after the scoring agent completes,
either as a standalone validation step or integrated into the pipeline.
All core functions are pure (no side effects) and accept / return
plain dicts, making them easy to test.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Public API ───────────────────────────────────────────────────────────


def get_profile_key(lead: dict, enrichment: dict | None = None) -> dict[str, Any]:
    """Extract the non-demographic profile signature from a lead.

    The profile key includes only the fields that should legitimately
    influence scoring: company, role, industry, enrichment data, and
    buying signals.  The lead's **name** is explicitly excluded.

    Args:
        lead: Lead data dict from the pipeline state.
        enrichment: Optional enrichment data dict.

    Returns:
        A dict containing only the fairness-relevant fields.
    """
    key: dict[str, Any] = {}

    key["company"] = _normalise(lead.get("company", ""))
    key["role"] = _normalise(lead.get("role", ""))
    key["industry"] = _normalise(lead.get("industry", ""))
    key["email_domain"] = _extract_domain(lead.get("email", ""))
    key["buying_signals"] = sorted(
        str(s) for s in (lead.get("buying_signals") or [])
    )

    if enrichment:
        key["company_size"] = _normalise(enrichment.get("company_size", ""))
        key["company_industry"] = _normalise(enrichment.get("company_industry", ""))
        key["employee_count"] = enrichment.get("employee_count")
        key["company_location"] = _normalise(enrichment.get("company_location", ""))

    return key


def compare_scores(
    lead_a: dict,
    score_a: dict[str, Any],
    lead_b: dict,
    score_b: dict[str, Any],
    enrichment_a: dict | None = None,
    enrichment_b: dict | None = None,
) -> dict[str, Any]:
    """Compare two scored leads and detect fairness violations.

    If both leads have the same profile key (company, role, enrichment,
    etc.) but different scores, a fairness violation is reported.

    Args:
        lead_a: First lead's data.
        score_a: First lead's score dict (``{"score": …, "confidence": …, "reasons": […]}``).
        lead_b: Second lead's data.
        score_b: Second lead's score dict.
        enrichment_a: Optional enrichment data for lead A.
        enrichment_b: Optional enrichment data for lead B.

    Returns:
        A dict with:
        - ``"violation"``: ``True`` if a fairness violation was detected.
        - ``"reason"``: Human-readable explanation.
        - ``"lead_a_id"``, ``"lead_b_id"``: IDs of the compared leads.
        - ``"score_a"``, ``"score_b"``: The respective scores.
        - ``"profile_key"``: The shared profile key (if profiles match).
    """
    key_a = get_profile_key(lead_a, enrichment_a)
    key_b = get_profile_key(lead_b, enrichment_b)

    result: dict[str, Any] = {
        "violation": False,
        "reason": "",
        "lead_a_id": lead_a.get("id", "unknown"),
        "lead_b_id": lead_b.get("id", "unknown"),
        "score_a": score_a.get("score"),
        "score_b": score_b.get("score"),
        "profile_key": None,
    }

    # Profiles are different → no violation possible
    if key_a != key_b:
        result["reason"] = (
            f"Profiles differ: leads have different company/role/enrichment attributes. "
            f"No fairness comparison possible."
        )
        return result

    result["profile_key"] = key_a

    score_val_a = score_a.get("score")
    score_val_b = score_b.get("score")

    # Both scores should be identical (or both None)
    if score_val_a is not None and score_val_b is not None and score_val_a != score_val_b:
        result["violation"] = True
        result["reason"] = (
            f"Fairness violation: leads with identical profiles "
            f"(company={key_a.get('company')!r}, role={key_a.get('role')!r}, "
            f"industry={key_a.get('industry')!r}) "
            f"received different scores — {score_val_a} vs {score_val_b}. "
            f"This suggests name-based or demographic bias in scoring."
        )
        logger.warning(
            "FAIRNESS VIOLATION: lead %s (score=%s) vs lead %s (score=%s). "
            "Same profile key but different scores.",
            result["lead_a_id"],
            score_val_a,
            result["lead_b_id"],
            score_val_b,
        )
    else:
        result["reason"] = "No fairness violation: scores are consistent."

    return result


def build_violation_audit_log(
    comparison_result: dict[str, Any],
    lead_name_a: str = "unknown",
    lead_name_b: str = "unknown",
) -> dict[str, Any] | None:
    """Build an audit log entry for a fairness violation.

    Args:
        comparison_result: The dict returned by ``compare_scores()``.
        lead_name_a: Display name for lead A (for the log message).
        lead_name_b: Display name for lead B.

    Returns:
        An audit log entry dict, or ``None`` if no violation occurred.
    """
    if not comparison_result.get("violation"):
        return None

    return {
        "event_type": "fairness_violation",
        "message": (
            f"Fairness violation detected between lead "
            f"{comparison_result['lead_a_id']} ({lead_name_a}) and "
            f"{comparison_result['lead_b_id']} ({lead_name_b}): "
            f"{comparison_result['reason']}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "lead_a_id": comparison_result["lead_a_id"],
            "lead_b_id": comparison_result["lead_b_id"],
            "score_a": comparison_result["score_a"],
            "score_b": comparison_result["score_b"],
            "profile_key": comparison_result["profile_key"],
        },
    }


def flag_lead_for_fairness(
    lead: dict,
    comparison_result: dict[str, Any],
) -> dict[str, Any]:
    """Add a fairness flag to a lead's data.

    Mutates the lead dict *in place* and also returns it for convenience.

    Args:
        lead: The lead data dict to flag.
        comparison_result: The result from ``compare_scores()``.

    Returns:
        The lead dict with ``fairness_flag`` added.
    """
    if comparison_result.get("violation"):
        lead["fairness_flag"] = {
            "type": "fairness_violation",
            "details": comparison_result["reason"],
            "compared_with": comparison_result["lead_b_id"],
            "score_difference": (
                comparison_result["score_a"] - comparison_result["score_b"]
                if comparison_result["score_a"] is not None
                and comparison_result["score_b"] is not None
                else None
            ),
        }
    else:
        # Ensure clean state
        lead.pop("fairness_flag", None)

    return lead


def validate_batch(
    leads_with_scores: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate a batch of scored leads for fairness.

    Groups leads by their profile key and checks that all leads in
    each group have identical scores.

    Args:
        leads_with_scores: A list of dicts, each containing at least
            ``"lead"``, ``"score"``, and optionally ``"enrichment"`` keys.

    Returns:
        A list of violation result dicts (one per pair where a violation
        was detected).  The list is empty if no violations exist.
    """
    violations: list[dict[str, Any]] = []

    # Group by profile key
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in leads_with_scores:
        lead = entry.get("lead", {})
        enrichment = entry.get("enrichment")
        key = get_profile_key(lead, enrichment)
        # Use a stable string representation of the key as the group id
        group_id = str(sorted(key.items()))
        if group_id not in groups:
            groups[group_id] = []
        groups[group_id].append(entry)

    # Within each group, compare every pair
    for group_id, entries in groups.items():
        if len(entries) < 2:
            continue

        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                entry_a = entries[i]
                entry_b = entries[j]

                result = compare_scores(
                    lead_a=entry_a["lead"],
                    score_a=entry_a["score"],
                    lead_b=entry_b["lead"],
                    score_b=entry_b["score"],
                    enrichment_a=entry_a.get("enrichment"),
                    enrichment_b=entry_b.get("enrichment"),
                )

                if result.get("violation"):
                    violations.append(result)

    return violations


# ── Internal helpers ─────────────────────────────────────────────────────


def _normalise(value: Any) -> str:
    """Normalise a value for comparison (lowercase, stripped)."""
    if value is None:
        return ""
    return str(value).strip().lower()


def _extract_domain(email: str) -> str:
    """Extract the domain part of an email address, lowercased."""
    if not email or "@" not in email:
        return ""
    return email.split("@")[-1].strip().lower()