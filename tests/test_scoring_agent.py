"""
Unit tests for the Scoring Agent.

Run with::

    pytest tests/test_scoring_agent.py -v

Run all tests::

    pytest tests/ -v
"""

from __future__ import annotations

import json
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.agents.scoring_agent import (
    _call_llm_with_fallback,
    _call_llm_with_retry,
    _heuristic_score,
    _parse_score_response,
    scoring_agent,
)
from backend.models.schemas import ScoreCreate
from backend.prompts.scoring_prompt import SCORING_SYSTEM_PROMPT, build_scoring_prompt


# ══════════════════════════════════════════════════════════════════════════
#  ScoreCreate schema tests
# ══════════════════════════════════════════════════════════════════════════


class TestScoreCreate:
    """Tests for the ScoreCreate Pydantic schema."""

    def test_valid_score(self):
        """Valid score data passes validation."""
        score = ScoreCreate(score=78, confidence=0.92, reasons=["Good fit", "Strong signals"])
        assert score.score == 78
        assert score.confidence == 0.92
        assert score.reasons == ["Good fit", "Strong signals"]

    def test_score_minimum(self):
        """Score of 0 is valid."""
        score = ScoreCreate(score=0, confidence=0.0)
        assert score.score == 0

    def test_score_maximum(self):
        """Score of 100 is valid."""
        score = ScoreCreate(score=100, confidence=1.0)
        assert score.score == 100

    def test_score_negative_raises(self):
        """Score below 0 raises validation error."""
        with pytest.raises(ValidationError, match="score"):
            ScoreCreate(score=-1, confidence=0.5)

    def test_score_above_100_raises(self):
        """Score above 100 raises validation error."""
        with pytest.raises(ValidationError, match="score"):
            ScoreCreate(score=101, confidence=0.5)

    def test_confidence_negative_raises(self):
        """Confidence below 0 raises validation error."""
        with pytest.raises(ValidationError, match="confidence"):
            ScoreCreate(score=50, confidence=-0.1)

    def test_confidence_above_1_raises(self):
        """Confidence above 1 raises validation error."""
        with pytest.raises(ValidationError, match="confidence"):
            ScoreCreate(score=50, confidence=1.5)

    def test_reasons_defaults_to_empty_list(self):
        """Reasons field defaults to empty list."""
        score = ScoreCreate(score=50, confidence=0.5)
        assert score.reasons == []


# ══════════════════════════════════════════════════════════════════════════
#  build_scoring_prompt tests
# ══════════════════════════════════════════════════════════════════════════


class TestBuildScoringPrompt:
    """Tests for the prompt builder function."""

    def test_basic_prompt_structure(self):
        """Prompt contains all required sections."""
        lead = {
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@acme.com",
            "industry": "Technology",
            "buying_signals": ["visited pricing page"],
        }
        enrichment = {
            "company_size": "1000-5000",
            "company_industry": "Enterprise Software",
            "employee_count": 2500,
            "company_location": "San Francisco, CA",
        }

        prompt = build_scoring_prompt(lead, enrichment)

        assert "Acme Corp" not in prompt  # Company name should NOT be in prompt
        assert "Enterprise Software" in prompt
        assert "1000-5000" in prompt
        assert "2500" in prompt
        assert "CTO" in prompt
        assert "acme.com" in prompt
        assert "Business" in prompt
        assert "visited pricing page" in prompt

    def test_enrichment_takes_precedence(self):
        """Enrichment data overrides lead data."""
        lead = {
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@acme.com",
            "industry": "Old Industry",
            "company_size": "1-50",
        }
        enrichment = {
            "company_size": "1000-5000",
            "company_industry": "Enterprise Software",
            "employee_count": 2500,
            "company_location": "San Francisco, CA",
        }

        prompt = build_scoring_prompt(lead, enrichment)

        assert "Enterprise Software" in prompt  # From enrichment
        assert "1000-5000" in prompt  # From enrichment
        assert "Old Industry" not in prompt  # Overridden by enrichment

    def test_no_enrichment_falls_back_to_lead(self):
        """Without enrichment, uses lead data."""
        lead = {
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@acme.com",
            "industry": "Technology",
            "company_size": "1-50",
            "employee_count": 10,
            "company_location": "Unknown",
        }

        prompt = build_scoring_prompt(lead, None)

        assert "Technology" in prompt
        assert "1-50" in prompt
        assert "10" in prompt

    def test_personal_email_detected(self):
        """Personal email domain is identified."""
        lead = {
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@gmail.com",
        }

        prompt = build_scoring_prompt(lead, None)

        assert "Personal" in prompt

    def test_business_email_detected(self):
        """Business email domain is identified."""
        lead = {
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@acme.com",
        }

        prompt = build_scoring_prompt(lead, None)

        assert "Business" in prompt

    def test_no_buying_signals(self):
        """No buying signals shows 'None'."""
        lead = {
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@acme.com",
        }

        prompt = build_scoring_prompt(lead, None)

        assert "Buying Signals: None" in prompt

    def test_name_not_in_prompt(self):
        """Lead name should NOT appear in the prompt."""
        lead = {
            "name": "Jane Doe",
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@acme.com",
        }

        prompt = build_scoring_prompt(lead, None)

        assert "Jane Doe" not in prompt
        assert "Jane" not in prompt

    def test_system_prompt_forbids_demographics(self):
        """System prompt explicitly forbids demographic factors."""
        assert "name" in SCORING_SYSTEM_PROMPT.lower()
        assert "gender" in SCORING_SYSTEM_PROMPT.lower()
        assert "religion" in SCORING_SYSTEM_PROMPT.lower()
        assert "nationality" in SCORING_SYSTEM_PROMPT.lower()
        assert "ethnicity" in SCORING_SYSTEM_PROMPT.lower()

    def test_system_prompt_allows_allowed_factors(self):
        """System prompt includes all allowed factors."""
        prompt = SCORING_SYSTEM_PROMPT.lower()
        assert "company size" in prompt
        assert "industry" in prompt
        assert "employee count" in prompt
        assert "role seniority" in prompt
        assert "business email" in prompt
        assert "buying signals" in prompt


# ══════════════════════════════════════════════════════════════════════════
#  _parse_score_response tests
# ══════════════════════════════════════════════════════════════════════════


class TestParseScoreResponse:
    """Tests for parsing LLM responses."""

    def test_parse_valid_json(self):
        """Valid JSON is parsed correctly."""
        raw = '{"score": 78, "confidence": 0.92, "reasons": ["Good fit", "Strong signals"]}'
        result = _parse_score_response(raw)
        assert result["score"] == 78
        assert result["confidence"] == 0.92
        assert result["reasons"] == ["Good fit", "Strong signals"]

    def test_parse_json_with_code_fence(self):
        """JSON inside markdown code fences is parsed."""
        raw = '```json\n{"score": 85, "confidence": 0.95, "reasons": ["Excellent match"]}\n```'
        result = _parse_score_response(raw)
        assert result["score"] == 85
        assert result["confidence"] == 0.95
        assert result["reasons"] == ["Excellent match"]

    def test_parse_json_with_code_fence_no_lang(self):
        """Code fence without language specifier is handled."""
        raw = '```\n{"score": 42, "confidence": 0.6, "reasons": ["Average"]}\n```'
        result = _parse_score_response(raw)
        assert result["score"] == 42

    def test_parse_float_score_rounds(self):
        """Float score is rounded to nearest int."""
        raw = '{"score": 78.7, "confidence": 0.92, "reasons": ["Good"]}'
        result = _parse_score_response(raw)
        assert result["score"] == 79  # round(78.7) = 79

    def test_parse_score_clamps_to_0_100(self):
        """Score is clamped to 0-100 range."""
        raw = '{"score": 150, "confidence": 0.9, "reasons": ["Too high"]}'
        result = _parse_score_response(raw)
        assert result["score"] == 100

        raw = '{"score": -50, "confidence": 0.9, "reasons": ["Too low"]}'
        result = _parse_score_response(raw)
        assert result["score"] == 0

    def test_parse_confidence_clamps(self):
        """Confidence is clamped to 0-1 range."""
        raw = '{"score": 50, "confidence": 2.5, "reasons": ["High confidence"]}'
        result = _parse_score_response(raw)
        assert result["confidence"] == 1.0

        raw = '{"score": 50, "confidence": -0.5, "reasons": ["Low confidence"]}'
        result = _parse_score_response(raw)
        assert result["confidence"] == 0.0

    def test_parse_reasons_as_string(self):
        """Single string reason is converted to list."""
        raw = '{"score": 50, "confidence": 0.5, "reasons": "Single reason"}'
        result = _parse_score_response(raw)
        assert result["reasons"] == ["Single reason"]

    def test_parse_reasons_as_none(self):
        """Missing reasons defaults to empty list."""
        raw = '{"score": 50, "confidence": 0.5}'
        result = _parse_score_response(raw)
        assert result["reasons"] == []

    def test_parse_missing_score_raises(self):
        """Missing 'score' field raises ValueError."""
        raw = '{"confidence": 0.5, "reasons": []}'
        with pytest.raises(ValueError, match="score"):
            _parse_score_response(raw)

    def test_parse_missing_confidence_raises(self):
        """Missing 'confidence' field raises ValueError."""
        raw = '{"score": 50, "reasons": []}'
        with pytest.raises(ValueError, match="confidence"):
            _parse_score_response(raw)

    def test_parse_invalid_json_raises(self):
        """Invalid JSON raises ValueError."""
        raw = "this is not json"
        with pytest.raises(ValueError, match="Failed to parse"):
            _parse_score_response(raw)

    def test_parse_extra_whitespace(self):
        """Extra whitespace is trimmed."""
        raw = '  \n  {"score": 60, "confidence": 0.7, "reasons": ["OK"]}  \n  '
        result = _parse_score_response(raw)
        assert result["score"] == 60


# ══════════════════════════════════════════════════════════════════════════
#  _heuristic_score tests
# ══════════════════════════════════════════════════════════════════════════


class TestHeuristicScore:
    """Tests for the heuristic scoring fallback."""

    def test_basic_scoring(self):
        """Basic heuristic scoring works."""
        lead = {
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@acme.com",
            "industry": "Technology",
            "buying_signals": ["requested demo"],
        }
        enrichment = {
            "company_size": "1000-5000",
            "company_industry": "Enterprise Software",
            "employee_count": 2500,
        }

        result = _heuristic_score(lead, enrichment)
        assert 0 <= result["score"] <= 100
        assert 0.0 <= result["confidence"] <= 1.0
        assert isinstance(result["reasons"], list)
        assert len(result["reasons"]) > 0

    def test_large_company_scores_high(self):
        """Large company with executive role scores high."""
        lead = {
            "company": "Wayne Enterprises",
            "role": "CTO",
            "email": "bruce@wayne.com",
            "industry": "Technology",
            "buying_signals": ["requested demo", "visited pricing page"],
        }
        enrichment = {
            "company_size": "10000+",
            "company_industry": "Technology",
            "employee_count": 50000,
        }

        result = _heuristic_score(lead, enrichment)
        assert result["score"] >= 80  # Should be high for large company
        assert result["confidence"] == 0.65

    def test_small_company_without_signals_scores_low(self):
        """Small company with no buying signals scores lower."""
        lead = {
            "company": "Small Startup",
            "role": "Engineer",
            "email": "dev@gmail.com",
            "industry": "Consulting",
        }
        enrichment = {
            "company_size": "1-50",
            "company_industry": "Consulting",
            "employee_count": 5,
        }

        result = _heuristic_score(lead, enrichment)
        assert result["score"] <= 40  # Should be low
        # Should have reasons about personal email, small company, no signals
        reason_text = " ".join(result["reasons"]).lower()
        assert "personal email" in reason_text or "small" in reason_text or "no buying signals" in reason_text

    def test_high_intent_buying_signals_boost(self):
        """High-intent buying signals boost score."""
        lead = {
            "company": "Acme Corp",
            "role": "VP Engineering",
            "email": "jane@acme.com",
            "industry": "Technology",
            "buying_signals": ["requested demo", "contact sales"],
        }

        result = _heuristic_score(lead, enrichment=None)
        reason_text = " ".join(result["reasons"]).lower()
        assert "high-intent" in reason_text or "demo" in reason_text

    def test_personal_email_penalty(self):
        """Personal email domain lowers score."""
        lead = {
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@gmail.com",
            "industry": "Technology",
        }

        result = _heuristic_score(lead, enrichment=None)
        reason_text = " ".join(result["reasons"]).lower()
        assert "personal email" in reason_text

    def test_enrichment_overrides_lead(self):
        """Enrichment data takes precedence over lead data."""
        lead = {
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@acme.com",
            "industry": "Old Industry",
            "company_size": "1-50",
        }
        enrichment = {
            "company_size": "1000-5000",
            "company_industry": "Enterprise Software",
            "employee_count": 2500,
        }

        result = _heuristic_score(lead, enrichment)
        reason_text = " ".join(result["reasons"]).lower()
        # Should use enrichment's company size and industry
        assert "enterprise software" in reason_text or "1000-5000" in reason_text

    def test_no_enrichment_uses_lead_data(self):
        """Without enrichment, uses lead data."""
        lead = {
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@acme.com",
            "industry": "Technology",
            "company_size": "51-200",
            "employee_count": 100,
        }

        result = _heuristic_score(lead, enrichment=None)
        assert result["score"] > 0
        assert len(result["reasons"]) > 0

    def test_empty_lead_returns_fallback_score(self):
        """Empty lead data returns a baseline score."""
        lead = {}
        result = _heuristic_score(lead, enrichment=None)
        # Starts at 50, subtracts 5 for no buying signals = 45
        # No industry, no role, no email, no employee count adjustments
        assert result["score"] == 45  # 50 - 5 (no buying signals) = 45
        assert result["confidence"] == 0.65

    def test_senior_role_boost(self):
        """Senior roles get a score boost."""
        lead = {
            "company": "Acme Corp",
            "role": "Chief Technology Officer",
            "email": "jane@acme.com",
            "industry": "Technology",
            "company_size": "201-1000",
        }

        result_with_senior = _heuristic_score(lead, enrichment=None)
        score_with_senior = result_with_senior["score"]

        lead["role"] = "Junior Developer"
        result_without_senior = _heuristic_score(lead, enrichment=None)

        # Senior role should score higher or equal
        assert score_with_senior >= result_without_senior["score"]

    def test_no_name_in_reasons(self):
        """Lead name should NOT appear in any reasons."""
        lead = {
            "name": "Jane Doe",
            "company": "Acme Corp",
            "role": "CTO",
            "email": "jane@acme.com",
            "industry": "Technology",
        }

        result = _heuristic_score(lead, enrichment=None)
        reason_text = " ".join(result["reasons"]).lower()
        assert "jane" not in reason_text
        assert "doe" not in reason_text


# ══════════════════════════════════════════════════════════════════════════
#  _call_llm_with_fallback tests (module-level async functions)
# ══════════════════════════════════════════════════════════════════════════


@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_call_llm_with_fallback_no_api_key_uses_heuristic(mock_get_settings):
    """Without API key, heuristic scoring is used."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = None
    mock_get_settings.return_value = settings

    lead = {
        "company": "Acme Corp",
        "role": "CTO",
        "email": "jane@acme.com",
        "industry": "Technology",
    }

    result = await _call_llm_with_fallback(lead, None)
    assert 0 <= result["score"] <= 100
    assert result["confidence"] == 0.65  # Heuristic confidence


@patch("backend.agents.scoring_agent._call_llm_with_retry")
@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_call_llm_with_fallback_llm_success(mock_get_settings, mock_retry):
    """Successful LLM call returns parsed score."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = "sk-test-key"
    settings.OPENROUTER_MODEL = "test-model"
    settings.OPENROUTER_TEMPERATURE = 0.7
    settings.OPENROUTER_MAX_TOKENS = 100
    settings.OPENROUTER_BASE_URL = "https://test.api"
    mock_get_settings.return_value = settings

    mock_retry.return_value = json.dumps({
        "score": 82,
        "confidence": 0.9,
        "reasons": ["Good fit", "Strong signals"],
    })

    lead = {
        "company": "Acme Corp",
        "role": "CTO",
        "email": "jane@acme.com",
        "industry": "Technology",
    }

    result = await _call_llm_with_fallback(lead, None)
    assert result["score"] == 82
    assert result["confidence"] == 0.9
    assert result["reasons"] == ["Good fit", "Strong signals"]


@patch("backend.agents.scoring_agent._call_llm_with_retry")
@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_call_llm_with_fallback_llm_failure_falls_back_to_heuristic(mock_get_settings, mock_retry):
    """LLM failure falls back to heuristic scoring."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = "sk-test-key"
    settings.OPENROUTER_MODEL = "test-model"
    settings.OPENROUTER_TEMPERATURE = 0.7
    settings.OPENROUTER_MAX_TOKENS = 100
    settings.OPENROUTER_BASE_URL = "https://test.api"
    mock_get_settings.return_value = settings

    mock_retry.side_effect = RuntimeError("LLM unavailable")

    lead = {
        "company": "Acme Corp",
        "role": "CTO",
        "email": "jane@acme.com",
        "industry": "Technology",
    }

    result = await _call_llm_with_fallback(lead, None)
    # Should fall back to heuristic
    assert 0 <= result["score"] <= 100
    assert result["confidence"] == 0.65


@patch("backend.agents.scoring_agent._call_llm_with_retry")
@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_call_llm_with_fallback_llm_invalid_json_falls_back(mock_get_settings, mock_retry):
    """Invalid JSON from LLM falls back to heuristic."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = "sk-test-key"
    settings.OPENROUTER_MODEL = "test-model"
    settings.OPENROUTER_TEMPERATURE = 0.7
    settings.OPENROUTER_MAX_TOKENS = 100
    settings.OPENROUTER_BASE_URL = "https://test.api"
    mock_get_settings.return_value = settings

    mock_retry.return_value = "not valid json"

    lead = {
        "company": "Acme Corp",
        "role": "CTO",
        "email": "jane@acme.com",
        "industry": "Technology",
    }

    result = await _call_llm_with_fallback(lead, None)
    # Should fall back to heuristic
    assert 0 <= result["score"] <= 100


# ══════════════════════════════════════════════════════════════════════════
#  _call_llm_with_retry tests (module-level async functions)
# ══════════════════════════════════════════════════════════════════════════


@patch("backend.agents.scoring_agent.ChatOpenAI")
@pytest.mark.asyncio
async def test_call_llm_with_retry_on_failure(mock_chat_openai):
    """Retries on failure and eventually succeeds."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = "sk-test-key"
    settings.OPENROUTER_MODEL = "test-model"
    settings.OPENROUTER_TEMPERATURE = 0.7
    settings.OPENROUTER_MAX_TOKENS = 100
    settings.OPENROUTER_BASE_URL = "https://test.api"

    # Mock LLM to fail twice then succeed
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock()
    mock_llm.ainvoke.side_effect = [
        Exception("Network error"),
        Exception("Rate limit"),
        MagicMock(content='{"score": 75, "confidence": 0.8, "reasons": ["Good"]}'),
    ]
    mock_chat_openai.return_value = mock_llm

    result = await _call_llm_with_retry(
        system_prompt="test system",
        user_prompt="test user",
        settings=settings,
    )

    assert json.loads(result)["score"] == 75
    assert mock_llm.ainvoke.call_count == 3


@patch("backend.agents.scoring_agent.ChatOpenAI")
@pytest.mark.asyncio
async def test_call_llm_with_retry_exhaustion_raises(mock_chat_openai):
    """Exhausted retries raise RuntimeError."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = "sk-test-key"
    settings.OPENROUTER_MODEL = "test-model"
    settings.OPENROUTER_TEMPERATURE = 0.7
    settings.OPENROUTER_MAX_TOKENS = 100
    settings.OPENROUTER_BASE_URL = "https://test.api"

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("Persistent error"))
    mock_chat_openai.return_value = mock_llm

    with pytest.raises(RuntimeError, match="LLM call failed after 3 attempts"):
        await _call_llm_with_retry(
            system_prompt="test system",
            user_prompt="test user",
            settings=settings,
        )

    assert mock_llm.ainvoke.call_count == 3


# ══════════════════════════════════════════════════════════════════════════
#  Scoring Agent (full integration) tests (module-level async functions)
# ══════════════════════════════════════════════════════════════════════════


@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_scoring_agent_heuristic_fallback(mock_get_settings):
    """Scoring agent uses heuristic fallback when no API key."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = None
    mock_get_settings.return_value = settings

    state = {
        "lead": {
            "id": "test_lead_001",
            "name": "Jane Doe",
            "email": "jane@acme.com",
            "company": "Acme Corp",
            "role": "CTO",
            "industry": "Technology",
            "buying_signals": ["requested demo"],
        },
        "enrichment": {
            "company_size": "1000-5000",
            "company_industry": "Enterprise Software",
            "employee_count": 2500,
            "company_location": "San Francisco, CA",
        },
        "logs": [],
    }

    result = await scoring_agent(state)

    # Score should be populated
    score = result.get("score", {})
    assert 0 <= score["score"] <= 100
    assert 0.0 <= score["confidence"] <= 1.0
    assert isinstance(score["reasons"], list)
    assert len(score["reasons"]) > 0

    # Lead should be enriched with score
    assert result["lead"]["score"] == score["score"]
    assert result["lead"]["score_confidence"] == score["confidence"]

    # Logs should have one entry
    assert len(result["logs"]) == 1
    assert result["logs"][0]["event_type"] == "scoring"


@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_scoring_agent_preserves_existing_logs(mock_get_settings):
    """Scoring agent appends to existing logs."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = None
    mock_get_settings.return_value = settings

    state = {
        "lead": {
            "id": "test_lead_002",
            "name": "Jane Doe",
            "email": "jane@acme.com",
            "company": "Acme Corp",
            "role": "CTO",
            "industry": "Technology",
        },
        "enrichment": None,
        "logs": [
            {"event_type": "intake", "message": "Lead ingested",
             "timestamp": "2026-01-01T00:00:00"},
        ],
    }

    result = await scoring_agent(state)

    assert len(result["logs"]) == 2
    assert result["logs"][0]["event_type"] == "intake"
    assert result["logs"][1]["event_type"] == "scoring"


@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_scoring_agent_no_lead_id(mock_get_settings):
    """Scoring agent works without a lead ID (no DB persistence)."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = None
    mock_get_settings.return_value = settings

    state = {
        "lead": {
            "name": "Jane Doe",
            "email": "jane@acme.com",
            "company": "Acme Corp",
            "role": "CTO",
            "industry": "Technology",
            "buying_signals": ["requested demo"],
        },
        "enrichment": None,
        "logs": [],
    }

    # Should not crash when no lead ID is present
    result = await scoring_agent(state)

    score = result.get("score", {})
    assert 0 <= score["score"] <= 100
    assert len(result["logs"]) == 1
    assert result["logs"][0]["event_type"] == "scoring"


@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_scoring_agent_without_enrichment(mock_get_settings):
    """Scoring agent works without enrichment data."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = None
    mock_get_settings.return_value = settings

    state = {
        "lead": {
            "id": "test_lead_003",
            "name": "Jane Doe",
            "email": "jane@acme.com",
            "company": "Acme Corp",
            "role": "CTO",
            "industry": "Technology",
        },
        "logs": [],
    }

    result = await scoring_agent(state)

    score = result.get("score", {})
    assert 0 <= score["score"] <= 100
    assert len(result["logs"]) == 1


@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_scoring_agent_empty_lead(mock_get_settings):
    """Scoring agent handles empty lead gracefully."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = None
    mock_get_settings.return_value = settings

    state = {
        "lead": {},
        "logs": [],
    }

    result = await scoring_agent(state)

    score = result.get("score", {})
    # Default starts at 50, minus 5 for no buying signals = 45
    assert score["score"] == 45
    assert len(result["logs"]) == 1


@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_scoring_agent_score_range(mock_get_settings):
    """Score is always within 0-100 range."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = None
    mock_get_settings.return_value = settings

    # Test with various inputs
    test_cases = [
        {"role": "CTO", "industry": "Technology", "company_size": "10000+",
         "email": "ceo@bigcorp.com", "buying_signals": ["requested demo"]},
        {"role": "Intern", "industry": "Unknown", "company_size": "Unknown",
         "email": "intern@gmail.com"},
        {"role": "", "industry": "", "company_size": "",
         "email": ""},
    ]

    for lead_data in test_cases:
        state = {
            "lead": {
                "id": "test_lead_range",
                "name": "Test User",
                **lead_data,
            },
            "logs": [],
        }

        result = await scoring_agent(state)
        score = result.get("score", {})
        assert 0 <= score["score"] <= 100, f"Score out of range for {lead_data}"
        assert 0.0 <= score["confidence"] <= 1.0


@patch("backend.agents.scoring_agent.get_settings")
@pytest.mark.asyncio
async def test_scoring_agent_reasons_are_strings(mock_get_settings):
    """All reasons are string values."""
    settings = MagicMock()
    settings.OPENROUTER_API_KEY = None
    mock_get_settings.return_value = settings

    state = {
        "lead": {
            "id": "test_lead_004",
            "name": "Jane Doe",
            "email": "jane@acme.com",
            "company": "Acme Corp",
            "role": "CTO",
            "industry": "Technology",
            "buying_signals": ["requested demo", "visited pricing page"],
        },
        "enrichment": {
            "company_size": "1000-5000",
            "company_industry": "Enterprise Software",
            "employee_count": 2500,
        },
        "logs": [],
    }

    result = await scoring_agent(state)
    for reason in result["score"]["reasons"]:
        assert isinstance(reason, str), f"Reason is not a string: {reason}"