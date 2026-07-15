"""
Scoring Agent — scores a lead using AI (OpenRouter / LLM).

Responsibilities
----------------
1. Extract lead and enrichment data from graph state.
2. Build a scoring prompt using only allowed factors.
3. Call the configured LLM via OpenRouter with retry logic.
4. Parse the structured JSON response (score, confidence, reasons).
5. Store the score record in the database.
6. Create an audit log entry.

Design
------
The agent uses langchain's ChatOpenAI to talk to any OpenAI-compatible
endpoint (OpenRouter by default).  The model, temperature, and max
tokens are all configurable via environment variables.

Allowed scoring factors: company size, industry, employee count,
role seniority, business email, buying signals.
Forbidden factors: name, gender, religion, nationality, ethnicity.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from backend.config import get_settings
from backend.database.session import async_session_factory
from backend.models.schemas import ScoreCreate
from backend.models.sqlalchemy_models import AuditLog, Lead, Score
from backend.prompts.scoring_prompt import SCORING_SYSTEM_PROMPT, build_scoring_prompt

logger = logging.getLogger(__name__)

# ── Retry configuration ─────────────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1.0  # Base delay, will be multiplied by attempt number


def _parse_score_response(raw: str) -> dict[str, Any]:
    """Parse the LLM response into a score dict.

    Handles:
      - Raw JSON (preferred)
      - JSON wrapped in markdown code fences (```json ... ```)
      - Trims whitespace and extracts JSON

    Args:
        raw: The raw text response from the LLM.

    Returns:
        A dict with keys ``score`` (int 0-100), ``confidence`` (float 0-1),
        and ``reasons`` (list[str]).

    Raises:
        ValueError: If the response cannot be parsed or validated.
    """
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        # Remove opening fence (```json, ```, etc.)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        # Remove closing fence
        if text.endswith("```"):
            text = text[:-3].strip()
        elif "```" in text:
            text = text[: text.rindex("```")].strip()

    # Parse JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse LLM response as JSON: {exc}\nRaw: {raw}"
        ) from exc

    # Validate required fields
    if "score" not in data:
        raise ValueError(f"LLM response missing 'score' field: {data}")
    if "confidence" not in data:
        raise ValueError(f"LLM response missing 'confidence' field: {data}")

    # Normalise score to int
    score = data["score"]
    if isinstance(score, float):
        score = round(score)
    score = int(score)

    # Clamp score to 0-100
    score = max(0, min(100, score))

    # Normalise confidence to float 0-1
    confidence = float(data["confidence"])
    confidence = max(0.0, min(1.0, confidence))

    # Normalise reasons to list of strings
    reasons = data.get("reasons", [])
    if isinstance(reasons, str):
        reasons = [reasons]
    if not isinstance(reasons, list):
        reasons = []
    reasons = [str(r) for r in reasons]

    return {
        "score": score,
        "confidence": confidence,
        "reasons": reasons,
    }


async def _call_llm_with_retry(
    system_prompt: str,
    user_prompt: str,
    settings: Any,
) -> str:
    """Call the LLM with retry logic.

    Args:
        system_prompt: The system-level prompt.
        user_prompt: The user / human message.
        settings: Application settings (from ``get_settings()``).

    Returns:
        The raw response text from the LLM.

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    import asyncio

    llm = ChatOpenAI(
        model=settings.OPENROUTER_MODEL,
        temperature=settings.OPENROUTER_TEMPERATURE,
        max_tokens=settings.OPENROUTER_MAX_TOKENS,
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )

    last_exception: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            response = await llm.ainvoke(messages)
            content = response.content
            if isinstance(content, list):
                # Handle list-of-blocks responses (e.g. multimodal)
                text_parts = [
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                ]
                content = " ".join(text_parts)
            return str(content)

        except Exception as exc:
            last_exception = exc
            logger.warning(
                "LLM call attempt %d/%d failed: %s",
                attempt,
                MAX_RETRIES,
                exc,
            )
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY_SECONDS * attempt
                await asyncio.sleep(delay)

    raise RuntimeError(
        f"LLM call failed after {MAX_RETRIES} attempts. "
        f"Last error: {last_exception}"
    ) from last_exception


async def _call_llm_with_fallback(
    lead: dict,
    enrichment: dict | None,
) -> dict[str, Any]:
    """Call the LLM and return parsed score data.

    Falls back to a heuristic-based score if the LLM is unavailable
    (e.g. no API key configured).

    Args:
        lead: Lead data from the pipeline state.
        enrichment: Enrichment data (may be None).

    Returns:
        A dict with ``score`` (int), ``confidence`` (float), ``reasons`` (list).
    """
    settings = get_settings()

    # If no API key is configured, use heuristic fallback
    if not settings.OPENROUTER_API_KEY:
        logger.info("No OPENROUTER_API_KEY configured — using heuristic scoring")
        return _heuristic_score(lead, enrichment)

    try:
        user_prompt = build_scoring_prompt(lead, enrichment)
        raw_response = await _call_llm_with_retry(
            system_prompt=SCORING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            settings=settings,
        )
        score_data = _parse_score_response(raw_response)
        logger.info(
            "LLM scored lead: score=%d, confidence=%.2f, reasons=%s",
            score_data["score"],
            score_data["confidence"],
            score_data["reasons"],
        )
        return score_data

    except Exception as exc:
        logger.error(
            "LLM scoring failed, falling back to heuristic: %s", exc
        )
        return _heuristic_score(lead, enrichment)


def _heuristic_score(lead: dict, enrichment: dict | None) -> dict[str, Any]:
    """Heuristic scoring fallback when the LLM is unavailable.

    This is a simple rule-based scorer that considers the same allowed
    factors as the LLM prompt.  It is intentionally less sophisticated
    than the AI scorer but provides a reasonable baseline.

    Args:
        lead: Lead data from the pipeline state.
        enrichment: Enrichment data (may be None).

    Returns:
        A dict with ``score`` (int), ``confidence`` (float), ``reasons`` (list).
    """
    score = 50  # Start at neutral
    reasons: list[str] = []

    # Determine which data source to use
    company_size = (
        enrichment.get("company_size")
        if enrichment
        else lead.get("company_size", "Unknown")
    )
    industry = (
        enrichment.get("company_industry")
        if enrichment
        else lead.get("industry", "Unknown")
    )
    employee_count = (
        enrichment.get("employee_count")
        if enrichment
        else lead.get("employee_count", 0)
    )

    # Company size scoring
    size_scores = {
        "1-50": 30,
        "51-200": 50,
        "201-1000": 65,
        "1000-5000": 75,
        "5001-10000": 80,
        "10000+": 85,
    }
    if company_size in size_scores:
        score = size_scores[company_size]
        reasons.append(f"Company size '{company_size}' indicates {'large' if score >= 70 else 'medium' if score >= 50 else 'small'} enterprise fit")

    # Industry scoring (preferred industries)
    preferred_industries = {
        "technology", "enterprise software", "saas", "information technology",
        "artificial intelligence", "cloud computing", "cybersecurity",
        "fintech", "healthtech", "biotech",
    }
    industry_lower = industry.lower() if isinstance(industry, str) else ""
    if industry_lower in preferred_industries:
        score = min(100, score + 15)
        reasons.append(f"Industry '{industry}' is in target vertical")
    elif industry_lower and industry_lower != "unknown":
        score = max(0, score - 5)
        reasons.append(f"Industry '{industry}' is outside primary target verticals")

    # Employee count scoring
    if isinstance(employee_count, (int, float)) and employee_count > 0:
        if employee_count >= 1000:
            score = min(100, score + 10)
            reasons.append(f"Large employee count ({employee_count}) suggests established company")
        elif employee_count <= 10:
            score = max(0, score - 10)
            reasons.append(f"Small employee count ({employee_count}) suggests early-stage company")

    # Role seniority scoring
    role = lead.get("role", "")
    if role:
        senior_roles = {"cto", "ceo", "cfo", "coo", "cmo", "cpo",
                        "vp", "svp", "evp", "director", "head"}
        role_lower = role.lower()
        # Check if any senior role word is in the role
        if any(sr in role_lower for sr in senior_roles):
            score = min(100, score + 10)
            reasons.append(f"Senior role '{role}' indicates decision-maker access")
        else:
            score = max(0, score - 5)
            reasons.append(f"Role '{role}' may not be a senior decision-maker")

    # Business email scoring
    email = lead.get("email", "")
    if "@" in email:
        personal_domains = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                            "aol.com", "icloud.com", "protonmail.com", "mail.com", "live.com"}
        domain = email.split("@")[-1].lower()
        if domain not in personal_domains:
            score = min(100, score + 5)
            reasons.append("Business email domain suggests legitimate company")
        else:
            score = max(0, score - 5)
            reasons.append("Personal email domain may indicate lower intent")

    # Buying signals scoring
    buying_signals = lead.get("buying_signals", [])
    if buying_signals:
        high_intent_signals = {"requested demo", "pricing page", "contact sales",
                               "free trial", "schedule call", "book meeting"}
        signal_text = " ".join(buying_signals).lower()
        if any(signal in signal_text for signal in high_intent_signals):
            score = min(100, score + 15)
            reasons.append("High-intent buying signals detected (demo/pricing request)")
        else:
            score = min(100, score + 5)
            reasons.append("Buying signals present")
    else:
        score = max(0, score - 5)
        reasons.append("No buying signals detected")

    # Confidence is lower for heuristic vs LLM
    confidence = 0.65

    return {
        "score": score,
        "confidence": confidence,
        "reasons": reasons,
    }


async def scoring_agent(state: dict) -> dict:
    """Score the lead based on enrichment and lead data using AI.

    This function is the LangGraph node for scoring.  It reads the
    lead and enrichment from the current graph state, calls the LLM
    (or falls back to heuristic), persists the score, and returns an
    updated state dict.

    Args:
        state: Current ``PipelineState`` dict containing at least
            ``lead`` and ``logs`` keys, and optionally ``enrichment``.

    Returns:
        Dict with updated ``score``, ``lead`` (with score merged in),
        and ``logs`` (appended audit entry).
    """
    lead = state.get("lead", {})
    enrichment = state.get("enrichment", None)
    logs = list(state.get("logs", []))

    # ── 1. & 2. Build prompt & call LLM ────────────────────────────────
    score_data = await _call_llm_with_fallback(lead, enrichment)

    # ── 3. Validate score data ─────────────────────────────────────────
    try:
        validated = ScoreCreate(
            score=score_data["score"],
            confidence=score_data["confidence"],
            reasons=score_data["reasons"],
        )
    except ValidationError as exc:
        error_msg = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in exc.errors())
        return {
            "score": {"score": 0, "confidence": 0.0, "reasons": [f"Validation error: {error_msg}"]},
            "lead": lead,
            "logs": logs
            + [
                {
                    "event_type": "scoring_error",
                    "message": f"Score validation failed: {error_msg}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }

    # ── 4. Persist score record & audit log in database ────────────────
    lead_id = lead.get("id")
    if lead_id:
        async with async_session_factory() as session:
            try:
                db_lead = await session.get(Lead, lead_id)
                if db_lead is not None:
                    score_record = Score(
                        lead_id=lead_id,
                        score=validated.score,
                        confidence=validated.confidence,
                        reasons=validated.reasons,
                    )
                    session.add(score_record)

                    audit_entry = AuditLog(
                        lead_id=lead_id,
                        event_type="scoring",
                        message=(
                            f"Scored lead {lead.get('name', 'unknown')} "
                            f"— {validated.score}/100 "
                            f"(confidence: {validated.confidence:.2f})"
                        ),
                    )
                    session.add(audit_entry)
                    await session.commit()

            except Exception:
                await session.rollback()
                log_entry = {
                    "event_type": "scoring_error",
                    "message": (
                        f"Failed to persist score for lead {lead_id}: "
                        f"database error"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                score_out = validated.model_dump(mode="json")
                return {
                    "score": score_out,
                    "lead": lead,
                    "logs": logs + [log_entry],
                }

    # ── 5. Build clean output state ────────────────────────────────────
    score_out = validated.model_dump(mode="json")

    # Merge score into lead for downstream nodes
    enriched_lead = dict(lead)
    enriched_lead["score"] = validated.score
    enriched_lead["score_confidence"] = validated.confidence

    log_entry = {
        "event_type": "scoring",
        "message": (
            f"Scored lead {lead.get('name', 'unknown')} "
            f"— {validated.score}/100 "
            f"(confidence: {validated.confidence:.2f})"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "score": score_out,
        "lead": enriched_lead,
        "logs": logs + [log_entry],
    }