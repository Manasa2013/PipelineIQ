"""
Scoring Agent prompt template for PipelineIQ.

The prompt instructs the LLM to evaluate a lead using only the
allowed scoring factors and return a structured JSON score.

Prompt injection protection is built in via:
- Hardened system prompt with guardrails
- Safe user prompt builder that demarcates lead data
- Sanitization of lead fields before prompt construction
"""

from backend.utils.security import build_system_prompt_guardrails, build_user_prompt_safe

# ── Base scoring prompt (without guardrails) ─────────────────────────────

_BASE_SCORING_SYSTEM_PROMPT = """You are a lead scoring expert for a B2B sales pipeline. Your task is to evaluate a lead based on the provided enrichment data and assign a score from 0 to 100.

## Allowed Scoring Factors
You MAY use the following factors to determine the score:
- Company size (e.g. "1-50", "51-200", "201-1000", "1000-5000", "10000+")
- Industry (e.g. "Technology", "Enterprise Software", "Manufacturing")
- Employee count
- Role seniority (e.g. "CTO", "VP Engineering", "Director", "Engineer")
- Business email domain (e.g. @acme.com is a corporate domain, @gmail.com is personal)
- Buying signals (e.g. "visited pricing page", "requested demo", "downloaded whitepaper")

## Forbidden Factors
You MUST NOT use the following factors under any circumstances:
- Name
- Gender
- Religion
- Nationality
- Ethnicity
- Any demographic or personal attributes

## Output Format
Return ONLY a valid JSON object with the following structure (no markdown, no code fences):
{
  "score": <integer 0-100>,
  "confidence": <float 0.0-1.0>,
  "reasons": ["<reason 1>", "<reason 2>", ...]
}

## Scoring Guidelines
- 0-20: Low fit — lead shows minimal alignment with ideal customer profile
- 21-40: Below average — some positive signals but significant gaps
- 41-60: Average — decent fit but no strong differentiators
- 61-80: Good — strong alignment with several positive signals
- 81-100: Excellent — ideal customer profile match with strong buying signals
- Confidence should reflect how much reliable data you have to base the score on
- Reasons should be specific, actionable, and reference the data provided
"""

# ── Hardened system prompt with injection guardrails ─────────────────────
# The guardrails instruct the LLM to treat lead data as data, never as
# instructions, and to ignore any injection attempts.

SCORING_SYSTEM_PROMPT = build_system_prompt_guardrails(_BASE_SCORING_SYSTEM_PROMPT)


def build_scoring_prompt(lead: dict, enrichment: dict | None) -> str:
    """Build a safe user message for the scoring LLM call.

    Uses the security module's ``build_user_prompt_safe`` to ensure
    lead data is properly sanitized and demarcated as data (not
    instructions).

    Args:
        lead: Lead data dict from the pipeline state.
        enrichment: Enrichment data dict (may be empty or None).

    Returns:
        A formatted, safe user prompt string.
    """
    return build_user_prompt_safe(lead, enrichment)
