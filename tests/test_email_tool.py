"""
Tests for the Email Tool Node.

Tests cover:
1. Email sender abstraction (SimulatedEmailSender)
2. Multi-layer safeguard enforcement
3. State-level approval check (Layer 2)
4. DB-level approval verification (Layer 3)
5. Email sending via configured provider (Layer 4)
6. Audit log generation
7. Bypass prevention — all safeguards must pass
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.email_tool_node import (
    _check_db_approval,
    _check_state_approval,
    email_tool_node,
)
from backend.services.email_sender import (
    EmailSender,
    SimulatedEmailSender,
    get_email_sender,
)


# ══════════════════════════════════════════════════════════════════════════
# Tests: EmailSender abstraction
# ══════════════════════════════════════════════════════════════════════════


class TestEmailSenderAbstraction:
    """Test the email sender abstract base class and implementations."""

    def test_email_sender_is_abstract(self):
        """EmailSender should not be instantiable directly."""
        with pytest.raises(TypeError):
            EmailSender()  # type: ignore

    def test_get_email_sender_defaults_to_simulated(self):
        """Default email sender should be SimulatedEmailSender."""
        with patch("backend.services.email_sender.get_settings") as mock_settings:
            mock_settings.return_value.EMAIL_PROVIDER = "simulated"
            sender = get_email_sender()
            assert isinstance(sender, SimulatedEmailSender)

    @pytest.mark.asyncio
    async def test_simulated_sender_returns_success(self):
        """SimulatedEmailSender should return a success response."""
        sender = SimulatedEmailSender()
        result = await sender.send(
            to_name="Jane Doe",
            to_email="jane@acme.com",
            subject="Test subject",
            body="Test body",
        )

        assert result["success"] is True
        assert result["provider"] == "simulated"
        assert result["message_id"] is not None
        assert result["message_id"].startswith("sim-")
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_simulated_sender_logs_content(self, caplog):
        """SimulatedEmailSender should log the email content."""
        import logging

        caplog.set_level(logging.INFO)

        sender = SimulatedEmailSender()
        await sender.send(
            to_name="Jane Doe",
            to_email="jane@acme.com",
            subject="Test subject",
            body="Test body content",
        )

        assert "SIMULATED EMAIL SEND" in caplog.text
        assert "Jane Doe" in caplog.text
        assert "jane@acme.com" in caplog.text
        assert "Test subject" in caplog.text
        assert "Test body content" in caplog.text


# ══════════════════════════════════════════════════════════════════════════
# Tests: Safeguard Layer 2 — State-level approval check
# ══════════════════════════════════════════════════════════════════════════


class TestCheckStateApproval:
    """Test the state-level approval validation."""

    def test_approved_passes(self):
        """Status 'approved' should pass state check."""
        ok, error = _check_state_approval({"status": "approved"})
        assert ok is True
        assert error == ""

    def test_edited_passes(self):
        """Status 'edited' should pass state check."""
        ok, error = _check_state_approval({"status": "edited"})
        assert ok is True
        assert error == ""

    def test_rejected_fails(self):
        """Status 'rejected' should fail state check."""
        ok, error = _check_state_approval({"status": "rejected"})
        assert ok is False
        assert "expected 'approved' or 'edited'" in error

    def test_pending_fails(self):
        """Status 'pending' should fail state check."""
        ok, error = _check_state_approval({"status": "pending"})
        assert ok is False

    def test_empty_status_fails(self):
        """Empty status should fail state check."""
        ok, error = _check_state_approval({})
        assert ok is False

    def test_none_fails(self):
        """None approval_status should fail state check."""
        ok, error = _check_state_approval(None)
        assert ok is False
        assert "missing" in error.lower()

    def test_non_dict_fails(self):
        """Non-dict approval_status should fail state check."""
        ok, error = _check_state_approval("not a dict")
        assert ok is False


# ══════════════════════════════════════════════════════════════════════════
# Tests: Safeguard Layer 3 — DB-level approval verification
# ══════════════════════════════════════════════════════════════════════════


class TestCheckDbApproval:
    """Test the database-level approval verification."""

    @pytest.mark.asyncio
    async def test_approval_record_exists_and_approved(self):
        """Approval record with approved=True should pass DB check."""
        with patch("backend.agents.email_tool_node.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            from unittest.mock import MagicMock
            mock_result = MagicMock()
            mock_record = MagicMock()
            mock_record.approved = True
            mock_record.approved_by = "manager@example.com"
            mock_result.scalar_one_or_none.return_value = mock_record
            mock_session.execute.return_value = mock_result

            ok, error = await _check_db_approval("lead123")
            assert ok is True
            assert error == ""

    @pytest.mark.asyncio
    async def test_no_approval_record_fails(self):
        """Missing approval record should fail DB check."""
        with patch("backend.agents.email_tool_node.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            from unittest.mock import MagicMock
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result

            ok, error = await _check_db_approval("lead123")
            assert ok is False
            assert "No approval record" in error

    @pytest.mark.asyncio
    async def test_approval_record_rejected_fails(self):
        """Approval record with approved=False should fail DB check."""
        with patch("backend.agents.email_tool_node.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            from unittest.mock import MagicMock
            mock_result = MagicMock()
            mock_record = MagicMock()
            mock_record.approved = False
            mock_record.approved_by = "manager@example.com"
            mock_result.scalar_one_or_none.return_value = mock_record
            mock_session.execute.return_value = mock_result

            ok, error = await _check_db_approval("lead123")
            assert ok is False
            assert "approved=False" in error


# ══════════════════════════════════════════════════════════════════════════
# Tests: email_tool_node — full integration with all safeguards
# ══════════════════════════════════════════════════════════════════════════


class TestEmailToolNode:
    """Test the full email tool node with all safeguards."""

    @pytest.fixture
    def approved_state(self):
        """State with valid approval."""
        return {
            "lead": {
                "id": "lead123",
                "name": "Jane Doe",
                "email": "jane@acme.com",
            },
            "draft_email": {
                "subject": "Test subject",
                "body": "Test body",
                "status": "approved",
            },
            "approval_status": {
                "status": "approved",
                "approved_by": "manager@example.com",
            },
            "logs": [],
        }

    @pytest.fixture
    def mock_db_with_approval(self):
        """Mock DB session that returns a valid approval record."""
        with patch("backend.agents.email_tool_node.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            from unittest.mock import MagicMock
            # Mock for DB approval check — use MagicMock for sync methods
            mock_result = MagicMock()
            mock_record = MagicMock()
            mock_record.approved = True
            mock_record.approved_by = "manager@example.com"
            mock_result.scalar_one_or_none.return_value = mock_record
            mock_session.execute.return_value = mock_result

            # Mock for lead fetch (for DB persistence after send)
            mock_lead = MagicMock()
            mock_lead.draft_emails = []
            mock_session.get.return_value = mock_lead

            yield mock_session

    # ── All safeguards pass → email sent ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_sends_email_when_all_safeguards_pass(self, approved_state, mock_db_with_approval):
        """Email should be sent when all safeguards pass."""
        result = await email_tool_node(approved_state)

        assert result["draft_email"]["status"] == "sent"
        assert result["logs"][-1]["event_type"] == "email_sent"
        assert result["lead"]["email_sent"] is True

    # ── Layer 2 failures (state check) ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_blocks_when_rejected(self, approved_state):
        """Email should NOT be sent when status is 'rejected'."""
        state = dict(approved_state)
        state["approval_status"]["status"] = "rejected"

        result = await email_tool_node(state)

        assert result["draft_email"]["status"] != "sent"
        assert result["logs"][-1]["event_type"] == "email_send_error"
        assert "BLOCKED" in result["logs"][-1]["message"]
        assert "Layer 2" in result["logs"][-1]["message"]

    @pytest.mark.asyncio
    async def test_blocks_when_pending(self, approved_state):
        """Email should NOT be sent when status is 'pending'."""
        state = dict(approved_state)
        state["approval_status"]["status"] = "pending"

        result = await email_tool_node(state)

        assert result["draft_email"]["status"] != "sent"
        assert "BLOCKED" in result["logs"][-1]["message"]

    @pytest.mark.asyncio
    async def test_blocks_when_missing_approval_status(self, approved_state):
        """Email should NOT be sent when approval_status is missing."""
        state = dict(approved_state)
        del state["approval_status"]

        result = await email_tool_node(state)

        assert result["draft_email"]["status"] != "sent"
        assert "BLOCKED" in result["logs"][-1]["message"]

    @pytest.mark.asyncio
    async def test_blocks_when_approval_status_none(self, approved_state):
        """Email should NOT be sent when approval_status is None."""
        state = dict(approved_state)
        state["approval_status"] = None

        result = await email_tool_node(state)

        assert result["draft_email"]["status"] != "sent"
        assert "BLOCKED" in result["logs"][-1]["message"]

    # ── Layer 3 failures (DB check) ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_blocks_when_no_db_approval_record(self, approved_state):
        """Email should NOT be sent when no approval record in DB."""
        with patch("backend.agents.email_tool_node.async_session_factory") as mock_factory:
            from unittest.mock import MagicMock
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            # No approval record in DB — use MagicMock for sync methods
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result

            result = await email_tool_node(approved_state)

            assert result["draft_email"]["status"] != "sent"
            assert "BLOCKED" in result["logs"][-1]["message"]
            assert "Layer 3" in result["logs"][-1]["message"]

    @pytest.mark.asyncio
    async def test_blocks_when_db_approval_rejected(self, approved_state):
        """Email should NOT be sent when DB approval record is rejected."""
        with patch("backend.agents.email_tool_node.async_session_factory") as mock_factory:
            from unittest.mock import MagicMock
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            # Rejected approval record in DB — use MagicMock for sync methods
            mock_result = MagicMock()
            mock_record = MagicMock()
            mock_record.approved = False
            mock_record.approved_by = "manager@example.com"
            mock_result.scalar_one_or_none.return_value = mock_record
            mock_session.execute.return_value = mock_result

            result = await email_tool_node(approved_state)

            assert result["draft_email"]["status"] != "sent"
            assert "BLOCKED" in result["logs"][-1]["message"]
            assert "Layer 3" in result["logs"][-1]["message"]

    @pytest.mark.asyncio
    async def test_blocks_when_no_lead_id(self, approved_state):
        """Email should NOT be sent when lead has no ID (DB check impossible)."""
        state = dict(approved_state)
        state["lead"] = {"name": "Jane Doe", "email": "jane@acme.com"}  # No 'id'

        result = await email_tool_node(state)

        assert result["draft_email"]["status"] != "sent"
        assert "BLOCKED" in result["logs"][-1]["message"]
        assert "no lead ID" in result["logs"][-1]["message"]

    # ── Governance: NEVER auto-send ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_never_sends_without_approval(self, approved_state):
        """Email must NEVER send without approval — all bypass attempts blocked."""
        bypass_attempts = [
            {"approval_status": {"status": "rejected"}},
            {"approval_status": {"status": "pending"}},
            {"approval_status": {}},
            {"approval_status": None},
            {},
        ]

        for attempt in bypass_attempts:
            state = dict(approved_state)
            state.update(attempt)

            result = await email_tool_node(state)
            assert result["draft_email"]["status"] != "sent", (
                f"Email was sent despite bypass attempt: {attempt}"
            )

    # ── Logs ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_preserves_existing_logs(self, approved_state, mock_db_with_approval):
        """Existing logs should be preserved."""
        state = dict(approved_state)
        state["logs"] = [{"event_type": "previous", "message": "Existing log"}]

        result = await email_tool_node(state)

        assert len(result["logs"]) == 2
        assert result["logs"][0]["event_type"] == "previous"

    @pytest.mark.asyncio
    async def test_adds_send_log_on_success(self, approved_state, mock_db_with_approval):
        """A send log entry should be added on success."""
        result = await email_tool_node(approved_state)

        assert result["logs"][-1]["event_type"] == "email_sent"
        assert "Jane Doe" in result["logs"][-1]["message"]
        assert "jane@acme.com" in result["logs"][-1]["message"]
        assert "simulated" in result["logs"][-1]["message"]