"""
Tests for the Classification Agent.

Tests cover:
1. Score classification rules (hot, nurture, disqualify)
2. Edge cases (boundary values, None score)
3. State output structure
4. Database persistence
5. Audit log generation
6. Pipeline integration
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.classification_agent import (
    HOT_THRESHOLD,
    NURTURE_THRESHOLD,
    classification_agent,
    classify_score,
)


# ══════════════════════════════════════════════════════════════════════════
# Tests: classify_score (pure function)
# ══════════════════════════════════════════════════════════════════════════


class TestClassifyScore:
    """Test the core classification function."""

    # ── Hot (score >= 80) ────────────────────────────────────────────────

    def test_hot_boundary(self):
        """Score exactly at HOT_THRESHOLD should be 'hot'."""
        category, explanation = classify_score(HOT_THRESHOLD)
        assert category == "hot"
        assert "hot" in explanation

    def test_hot_above(self):
        """Score above HOT_THRESHOLD should be 'hot'."""
        category, explanation = classify_score(95)
        assert category == "hot"
        assert "95" in explanation

    def test_hot_maximum(self):
        """Maximum score (100) should be 'hot'."""
        category, explanation = classify_score(100)
        assert category == "hot"
        assert "100" in explanation

    def test_hot_one_below(self):
        """Score one below HOT_THRESHOLD should NOT be 'hot'."""
        category, explanation = classify_score(HOT_THRESHOLD - 1)
        assert category != "hot"

    # ── Nurture (50 <= score < 80) ───────────────────────────────────────

    def test_nurture_boundary_low(self):
        """Score exactly at NURTURE_THRESHOLD should be 'nurture'."""
        category, explanation = classify_score(NURTURE_THRESHOLD)
        assert category == "nurture"
        assert "nurture" in explanation

    def test_nurture_mid_range(self):
        """Score in the middle of nurture range should be 'nurture'."""
        category, explanation = classify_score(65)
        assert category == "nurture"
        assert "65" in explanation

    def test_nurture_boundary_high(self):
        """Score one below HOT_THRESHOLD should be 'nurture'."""
        category, explanation = classify_score(HOT_THRESHOLD - 1)
        assert category == "nurture"
        assert str(HOT_THRESHOLD - 1) in explanation

    def test_nurture_one_below_low(self):
        """Score one below NURTURE_THRESHOLD should NOT be 'nurture'."""
        category, explanation = classify_score(NURTURE_THRESHOLD - 1)
        assert category != "nurture"

    # ── Disqualify (score < 50) ──────────────────────────────────────────

    def test_disqualify_boundary(self):
        """Score one below NURTURE_THRESHOLD should be 'disqualify'."""
        category, explanation = classify_score(NURTURE_THRESHOLD - 1)
        assert category == "disqualify"
        assert "Disqualify:" in explanation
        assert str(NURTURE_THRESHOLD - 1) in explanation

    def test_disqualify_low_score(self):
        """Score of 0 should be 'disqualify'."""
        category, explanation = classify_score(0)
        assert category == "disqualify"
        assert "0" in explanation

    def test_disqualify_negative(self):
        """Negative score should be 'disqualify'."""
        category, explanation = classify_score(-10)
        assert category == "disqualify"

    # ── None / edge cases ─────────────────────────────────────────────────

    def test_none_score(self):
        """None score should be 'disqualify' with appropriate explanation."""
        category, explanation = classify_score(None)
        assert category == "disqualify"
        assert "No score available" in explanation

    def test_explanation_contains_thresholds(self):
        """Explanation should reference the relevant thresholds."""
        _, hot_explanation = classify_score(90)
        assert str(HOT_THRESHOLD) in hot_explanation

        _, nurture_explanation = classify_score(60)
        assert str(NURTURE_THRESHOLD) in nurture_explanation
        assert str(HOT_THRESHOLD) in nurture_explanation

        _, disqualify_explanation = classify_score(10)
        assert str(NURTURE_THRESHOLD) in disqualify_explanation


# ══════════════════════════════════════════════════════════════════════════
# Tests: classification_agent (async, with mocked DB)
# ══════════════════════════════════════════════════════════════════════════


class TestClassificationAgent:
    """Test the full classification agent with mocked database."""

    @pytest.fixture
    def base_state(self):
        """Base state with a valid lead and score."""
        return {
            "lead": {
                "id": "lead123",
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "company": "Acme Corp",
                "score": 85,
            },
            "score": {"score": 85, "confidence": 0.92, "reasons": ["Strong fit"]},
            "logs": [{"event_type": "previous", "message": "Existing log entry"}],
        }

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock async database session."""
        with patch("backend.agents.classification_agent.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session
            yield mock_session

    # ── Hot classification ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_hot_classification(self, base_state, mock_db_session):
        """Score >= 80 should classify as 'hot'."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await classification_agent(base_state)

        assert result["classification"]["category"] == "hot"
        assert "hot" in result["classification"]["explanation"]
        assert result["lead"]["classification"] == "hot"

    # ── Nurture classification ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_nurture_classification(self, base_state, mock_db_session):
        """Score between 50 and 79 should classify as 'nurture'."""
        state = dict(base_state)
        state["score"] = {"score": 65, "confidence": 0.7, "reasons": ["Medium fit"]}

        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await classification_agent(state)

        assert result["classification"]["category"] == "nurture"
        assert "nurture" in result["classification"]["explanation"]
        assert result["lead"]["classification"] == "nurture"

    # ── Disqualify classification ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_disqualify_classification(self, base_state, mock_db_session):
        """Score < 50 should classify as 'disqualify'."""
        state = dict(base_state)
        state["score"] = {"score": 30, "confidence": 0.5, "reasons": ["Low fit"]}

        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await classification_agent(state)

        assert result["classification"]["category"] == "disqualify"
        assert "disqualify" in result["classification"]["explanation"].lower()
        assert result["lead"]["classification"] == "disqualify"

    # ── None score → disqualify ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_score_disqualifies(self, base_state, mock_db_session):
        """Missing score should classify as 'disqualify'."""
        state = dict(base_state)
        state["score"] = None

        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await classification_agent(state)

        assert result["classification"]["category"] == "disqualify"
        assert "No score available" in result["classification"]["explanation"]

    @pytest.mark.asyncio
    async def test_empty_score_disqualifies(self, base_state, mock_db_session):
        """Empty score dict should classify as 'disqualify'."""
        state = dict(base_state)
        state["score"] = {}

        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await classification_agent(state)

        assert result["classification"]["category"] == "disqualify"
        assert "No score available" in result["classification"]["explanation"]

    # ── Output structure ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_output_has_classification_key(self, base_state, mock_db_session):
        """Output should contain 'classification' key."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await classification_agent(base_state)

        assert "classification" in result
        assert "category" in result["classification"]
        assert "explanation" in result["classification"]

    @pytest.mark.asyncio
    async def test_output_has_lead_key(self, base_state, mock_db_session):
        """Output should contain 'lead' key."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await classification_agent(base_state)

        assert "lead" in result
        assert result["lead"]["id"] == "lead123"

    @pytest.mark.asyncio
    async def test_output_has_logs_key(self, base_state, mock_db_session):
        """Output should contain 'logs' key."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await classification_agent(base_state)

        assert "logs" in result

    # ── Database persistence ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_persists_classification_record(self, base_state, mock_db_session):
        """Classification record should be added to the session."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        await classification_agent(base_state)

        # Check that Classification was added
        from backend.models.sqlalchemy_models import Classification

        calls = mock_db_session.add.call_args_list
        classification_calls = [
            c for c in calls if isinstance(c[0][0], Classification)
        ]
        assert len(classification_calls) >= 1
        assert classification_calls[0][0][0].lead_id == "lead123"
        assert classification_calls[0][0][0].category == "hot"

    @pytest.mark.asyncio
    async def test_persists_audit_log(self, base_state, mock_db_session):
        """Audit log entry should be added to the session."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        await classification_agent(base_state)

        from backend.models.sqlalchemy_models import AuditLog

        calls = mock_db_session.add.call_args_list
        audit_calls = [c for c in calls if isinstance(c[0][0], AuditLog)]
        assert len(audit_calls) >= 1
        assert audit_calls[0][0][0].event_type == "classification"
        assert "Jane Doe" in audit_calls[0][0][0].message

    @pytest.mark.asyncio
    async def test_commits_transaction(self, base_state, mock_db_session):
        """Session should be committed."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        await classification_agent(base_state)

        mock_db_session.commit.assert_called_once()

    # ── Logs ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_preserves_existing_logs(self, base_state, mock_db_session):
        """Existing logs should be preserved."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await classification_agent(base_state)

        assert len(result["logs"]) == 2  # 1 existing + 1 new
        assert result["logs"][0]["event_type"] == "previous"

    @pytest.mark.asyncio
    async def test_adds_classification_log(self, base_state, mock_db_session):
        """A new classification log entry should be added."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await classification_agent(base_state)

        assert result["logs"][-1]["event_type"] == "classification"
        assert "hot" in result["logs"][-1]["message"]

    # ── No lead_id ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_lead_id_does_not_crash(self, base_state):
        """Agent should not crash if lead has no ID."""
        state = dict(base_state)
        state["lead"] = {"name": "Jane Doe", "company": "Acme Corp"}
        # No 'id' in lead

        result = await classification_agent(state)
        assert result["classification"]["category"] == "hot"
        assert "logs" in result

    # ── Database error handling ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_db_error_does_not_crash(self, base_state, mock_db_session):
        """Database error should not crash the pipeline."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        mock_db_session.commit.side_effect = Exception("DB connection failed")

        result = await classification_agent(base_state)
        assert result["classification"]["category"] == "hot"
        assert len(result["logs"]) >= 1
        assert result["logs"][-1]["event_type"] == "classification_error"

    # ── Lead not found in DB ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_lead_not_found_in_db(self, base_state, mock_db_session):
        """If lead is not found in DB, agent should still return classification."""
        mock_db_session.get.return_value = None  # Lead not found

        result = await classification_agent(base_state)
        assert result["classification"]["category"] == "hot"
        # No database error should be logged since lead not found is not an error
        assert result["logs"][-1]["event_type"] == "classification"


# ══════════════════════════════════════════════════════════════════════════
# Tests: Threshold constants
# ══════════════════════════════════════════════════════════════════════════


class TestThresholds:
    """Test that threshold constants are defined correctly."""

    def test_hot_threshold(self):
        assert HOT_THRESHOLD == 80

    def test_nurture_threshold(self):
        assert NURTURE_THRESHOLD == 50

    def test_thresholds_in_order(self):
        """Hot threshold should be higher than nurture threshold."""
        assert HOT_THRESHOLD > NURTURE_THRESHOLD