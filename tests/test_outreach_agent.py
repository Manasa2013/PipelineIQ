"""
Tests for the Outreach Agent.

Tests cover:
1. Subject line generation (build_subject) with various data availability
2. Email body generation (build_email_body) with various data availability
3. No hallucination — only data present in lead/enrichment is used
4. Professional B2B tone and structure
5. Database persistence of DraftEmail
6. Audit log generation
7. Pipeline integration with mocked DB
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.outreach_agent import (
    _build_email_body,
    _build_subject,
    outreach_agent,
)


# ══════════════════════════════════════════════════════════════════════════
# Tests: _build_subject
# ══════════════════════════════════════════════════════════════════════════


class TestBuildSubject:
    """Test subject line generation from lead data."""

    def test_company_and_industry(self):
        """Subject should reference company and industry when both available."""
        lead = {"company": "Acme Corp", "industry": "Enterprise Software"}
        subject = _build_subject(lead, None)
        assert "Acme Corp" in subject
        assert "Enterprise Software" in subject
        assert "strategy" in subject.lower()

    def test_company_and_industry_from_enrichment(self):
        """Enrichment data should take precedence over lead data."""
        lead = {"company": "Acme Corp", "industry": "Old Industry"}
        enrichment = {"company_industry": "Enterprise Software"}
        subject = _build_subject(lead, enrichment)
        assert "Acme Corp" in subject
        assert "Enterprise Software" in subject
        assert "Old Industry" not in subject

    def test_company_only(self):
        """Subject should reference company when industry is unavailable."""
        lead = {"company": "Acme Corp"}
        subject = _build_subject(lead, None)
        assert "Acme Corp" in subject
        assert "growth" in subject.lower()

    def test_role_and_name(self):
        """Subject should reference role and name when company is unavailable."""
        lead = {"name": "Jane Doe", "role": "CTO"}
        subject = _build_subject(lead, None)
        assert "Jane Doe" in subject
        assert "CTO" in subject

    def test_name_only(self):
        """Subject should reference name when only name is available."""
        lead = {"name": "Jane Doe"}
        subject = _build_subject(lead, None)
        assert "Jane Doe" in subject
        assert "Connecting" in subject

    def test_no_data_fallback(self):
        """Subject should use fallback when no data is available."""
        subject = _build_subject({}, None)
        assert "partnership" in subject.lower()

    def test_whitespace_stripped(self):
        """Whitespace should be stripped from values."""
        lead = {"company": "  Acme Corp  ", "industry": "  SaaS  "}
        subject = _build_subject(lead, None)
        assert "Acme Corp" in subject
        assert "SaaS" in subject

    def test_no_hallucination(self):
        """Subject should not contain data not present in lead/enrichment."""
        lead = {"company": "Acme Corp"}
        subject = _build_subject(lead, None)
        # Should not reference a specific industry or role that wasn't provided
        assert "CTO" not in subject
        assert "SaaS" not in subject


# ══════════════════════════════════════════════════════════════════════════
# Tests: _build_email_body
# ══════════════════════════════════════════════════════════════════════════


class TestBuildEmailBody:
    """Test email body generation from lead data."""

    FULL_LEAD = {
        "name": "Jane Doe",
        "email": "jane@acme.com",
        "company": "Acme Corp",
        "role": "CTO",
        "industry": "Enterprise Software",
        "buying_signals": ["visited pricing page", "requested demo"],
    }

    FULL_ENRICHMENT = {
        "company_size": "201-1000",
        "employee_count": 500,
        "company_location": "San Francisco, CA",
        "company_industry": "Enterprise Software",
    }

    # ── Structure checks ──────────────────────────────────────────────────

    def test_greeting_with_name(self):
        """Email should greet the lead by name."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        assert "Hi Jane Doe," in body

    def test_greeting_without_name(self):
        """Email should use generic greeting when name is unavailable."""
        lead = {"company": "Acme Corp"}
        body = _build_email_body(lead, None)
        assert "Hello," in body

    def test_has_subject_and_body_separate(self):
        """Body should not contain subject line prefixes."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        # Body should not include subject-like patterns
        assert "Quick question" not in body

    def test_has_closing(self):
        """Email should end with a professional closing."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        assert "Best regards" in body
        assert "PipelineIQ" in body

    def test_has_call_to_action(self):
        """Email should have a call to action paragraph."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        assert "15-minute call" in body

    # ── Personalization ───────────────────────────────────────────────────

    def test_company_referenced(self):
        """Email should reference the lead's company."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        assert "Acme Corp" in body

    def test_industry_referenced(self):
        """Email should reference the lead's industry."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        assert "Enterprise Software" in body

    def test_role_referenced(self):
        """Email should reference the lead's role."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        assert "CTO" in body

    def test_company_size_referenced(self):
        """Email should reference company size from enrichment."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        assert "201-1000" in body

    def test_employee_count_referenced(self):
        """Email should reference employee count from enrichment."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        assert "500" in body or "500" in body

    def test_location_referenced(self):
        """Email should reference company location."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        assert "San Francisco" in body
        assert "based in" in body.lower()

    # ── Buying signals ────────────────────────────────────────────────────

    def test_buying_signals_referenced(self):
        """Email should reference buying signals when present."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        assert "visited pricing page" in body
        assert "requested demo" in body

    # ── No hallucination ──────────────────────────────────────────────────

    def test_no_hallucinated_company_name(self):
        """Email should not contain a company name not in the data."""
        lead = {"name": "John Smith", "role": "Engineer"}
        body = _build_email_body(lead, None)
        # Should not contain any specific company name
        assert "Acme" not in body
        assert "Google" not in body
        assert "Microsoft" not in body

    def test_no_hallucinated_industry(self):
        """Email should not contain an industry not in the data."""
        lead = {"name": "John Smith", "company": "TechStartup"}
        body = _build_email_body(lead, None)
        # Should not contain a specific industry that wasn't provided
        assert "Artificial Intelligence" not in body

    def test_no_hallucinated_statistics(self):
        """Email should not contain statistics or numbers not in the data."""
        lead = {"name": "John Smith", "company": "TechStartup"}
        body = _build_email_body(lead, None)
        # Should not contain made-up numbers
        assert "20%" not in body
        assert "3x" not in body

    # ── Professional tone ─────────────────────────────────────────────────

    def test_professional_tone(self):
        """Email should maintain a professional B2B tone."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        # Should not contain casual/informal language
        assert "hey" not in body.lower()
        assert "gonna" not in body.lower()
        assert "wanna" not in body.lower()

    def test_multi_paragraph_structure(self):
        """Email should have multiple paragraphs separated by blank lines."""
        body = _build_email_body(self.FULL_LEAD, self.FULL_ENRICHMENT)
        paragraphs = [p for p in body.split("\n\n") if p.strip()]
        assert len(paragraphs) >= 4  # greeting, opening, value prop, relevance, cta, closing

    # ── Edge cases ────────────────────────────────────────────────────────

    def test_minimal_lead(self):
        """Email should handle minimal lead data gracefully."""
        lead = {"name": "Jane Doe"}
        body = _build_email_body(lead, None)
        assert "Jane Doe" in body
        assert "Hello" not in body  # Should use "Hi Jane Doe" not "Hello,"
        assert "Best regards" in body

    def test_empty_lead(self):
        """Email should handle completely empty lead."""
        body = _build_email_body({}, None)
        assert "Hello," in body  # No name → generic greeting
        assert "Best regards" in body

    def test_enrichment_fallback_to_lead(self):
        """When enrichment is None, should fall back to lead data."""
        lead = {"company": "Acme Corp", "industry": "SaaS"}
        body = _build_email_body(lead, None)
        assert "SaaS" in body
        assert "Acme Corp" in body

    def test_lead_without_buying_signals(self):
        """Email should still work without buying signals."""
        lead = {"name": "Jane Doe", "company": "Acme Corp", "role": "CTO"}
        enrichment = {"company_industry": "SaaS"}
        body = _build_email_body(lead, enrichment)
        # Should reference company as context
        assert "Acme Corp" in body
        assert "conversation" in body


# ══════════════════════════════════════════════════════════════════════════
# Tests: outreach_agent (async, with mocked DB)
# ══════════════════════════════════════════════════════════════════════════


class TestOutreachAgent:
    """Test the full outreach agent with mocked database."""

    @pytest.fixture
    def base_state(self):
        """Base state with a valid lead and enrichment."""
        return {
            "lead": {
                "id": "lead123",
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "company": "Acme Corp",
                "role": "CTO",
                "industry": "Enterprise Software",
                "buying_signals": ["visited pricing page", "requested demo"],
            },
            "enrichment": {
                "company_size": "201-1000",
                "employee_count": 500,
                "company_location": "San Francisco, CA",
                "company_industry": "Enterprise Software",
            },
            "logs": [{"event_type": "previous", "message": "Existing log entry"}],
        }

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock async database session."""
        with patch("backend.agents.outreach_agent.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session
            yield mock_session

    # ── Output structure ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_output_has_draft_email_key(self, base_state, mock_db_session):
        """Output should contain 'draft_email' key."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await outreach_agent(base_state)

        assert "draft_email" in result
        assert "subject" in result["draft_email"]
        assert "body" in result["draft_email"]
        assert "status" in result["draft_email"]

    @pytest.mark.asyncio
    async def test_draft_email_status_is_draft(self, base_state, mock_db_session):
        """Draft email status should be 'draft'."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await outreach_agent(base_state)

        assert result["draft_email"]["status"] == "draft"

    @pytest.mark.asyncio
    async def test_output_has_lead_key(self, base_state, mock_db_session):
        """Output should contain 'lead' key."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await outreach_agent(base_state)

        assert "lead" in result
        assert result["lead"]["id"] == "lead123"

    @pytest.mark.asyncio
    async def test_output_has_logs_key(self, base_state, mock_db_session):
        """Output should contain 'logs' key."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await outreach_agent(base_state)

        assert "logs" in result

    # ── Email content ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_subject_contains_company_and_industry(self, base_state, mock_db_session):
        """Subject should reference lead's company and industry."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await outreach_agent(base_state)

        assert "Acme Corp" in result["draft_email"]["subject"]
        assert "Enterprise Software" in result["draft_email"]["subject"]

    @pytest.mark.asyncio
    async def test_body_contains_lead_data(self, base_state, mock_db_session):
        """Body should reference lead data."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await outreach_agent(base_state)

        body = result["draft_email"]["body"]
        assert "Jane Doe" in body
        assert "Acme Corp" in body
        assert "CTO" in body
        assert "Enterprise Software" in body
        assert "San Francisco" in body
        assert "based in" in body.lower()
        assert "visited pricing page" in body

    # ── Database persistence ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_persists_draft_email(self, base_state, mock_db_session):
        """DraftEmail record should be added to the session."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        await outreach_agent(base_state)

        from backend.models.sqlalchemy_models import DraftEmail

        calls = mock_db_session.add.call_args_list
        email_calls = [c for c in calls if isinstance(c[0][0], DraftEmail)]
        assert len(email_calls) >= 1
        assert email_calls[0][0][0].lead_id == "lead123"
        assert email_calls[0][0][0].status == "draft"
        assert "Acme Corp" in email_calls[0][0][0].subject

    @pytest.mark.asyncio
    async def test_persists_audit_log(self, base_state, mock_db_session):
        """Audit log entry should be added to the session."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        await outreach_agent(base_state)

        from backend.models.sqlalchemy_models import AuditLog

        calls = mock_db_session.add.call_args_list
        audit_calls = [c for c in calls if isinstance(c[0][0], AuditLog)]
        assert len(audit_calls) >= 1
        assert audit_calls[0][0][0].event_type == "outreach"
        assert "Jane Doe" in audit_calls[0][0][0].message
        assert "Acme Corp" in audit_calls[0][0][0].message

    @pytest.mark.asyncio
    async def test_commits_transaction(self, base_state, mock_db_session):
        """Session should be committed."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        await outreach_agent(base_state)

        mock_db_session.commit.assert_called_once()

    # ── Logs ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_preserves_existing_logs(self, base_state, mock_db_session):
        """Existing logs should be preserved."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await outreach_agent(base_state)

        assert len(result["logs"]) == 2  # 1 existing + 1 new
        assert result["logs"][0]["event_type"] == "previous"

    @pytest.mark.asyncio
    async def test_adds_outreach_log(self, base_state, mock_db_session):
        """A new outreach log entry should be added."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await outreach_agent(base_state)

        assert result["logs"][-1]["event_type"] == "outreach"
        assert "Acme Corp" in result["logs"][-1]["message"]

    # ── Error handling ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_no_lead_id_does_not_crash(self, base_state):
        """Agent should not crash if lead has no ID."""
        state = dict(base_state)
        state["lead"] = {"name": "Jane Doe", "company": "Acme Corp"}

        result = await outreach_agent(state)
        assert result["draft_email"]["status"] == "draft"
        assert "Acme Corp" in result["draft_email"]["subject"]
        assert "logs" in result

    @pytest.mark.asyncio
    async def test_db_error_does_not_crash(self, base_state, mock_db_session):
        """Database error should not crash the pipeline."""
        mock_db_session.get.return_value = AsyncMock(id="lead123")
        mock_db_session.commit.side_effect = Exception("DB connection failed")

        result = await outreach_agent(base_state)
        assert result["draft_email"]["status"] == "draft"
        assert "Acme Corp" in result["draft_email"]["subject"]
        assert result["logs"][-1]["event_type"] == "outreach_error"

    @pytest.mark.asyncio
    async def test_lead_not_found_in_db(self, base_state, mock_db_session):
        """If lead is not found in DB, agent should still return email."""
        mock_db_session.get.return_value = None

        result = await outreach_agent(base_state)
        assert result["draft_email"]["status"] == "draft"
        assert result["logs"][-1]["event_type"] == "outreach"

    # ── No enrichment ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_works_without_enrichment(self, base_state, mock_db_session):
        """Agent should work when enrichment is None."""
        state = dict(base_state)
        state["enrichment"] = None

        mock_db_session.get.return_value = AsyncMock(id="lead123")
        result = await outreach_agent(state)

        assert result["draft_email"]["status"] == "draft"
        # Should still reference lead data
        assert "Acme Corp" in result["draft_email"]["subject"]
        assert "Jane Doe" in result["draft_email"]["body"]