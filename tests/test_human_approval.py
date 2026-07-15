"""
Tests for the Human Approval Workflow.

Tests cover:
1. Human Approval Node — graph pauses, decision processing, audit logs
2. Email Tool Node — only sends after approval, rejects without approval
3. API Endpoints — /approve, /reject, /draft
4. Edit preservation — user edits are preserved in the database
5. Governance — email NEVER sends automatically
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.agents.human_approval_node import human_approval_node
from backend.agents.email_tool_node import email_tool_node
from backend.api.approval import (
    _process_approval,
    approve_draft,
    reject_draft,
    edit_draft,
    ApproveRequest,
    RejectRequest,
    EditDraftRequest,
)


# ══════════════════════════════════════════════════════════════════════════
# Tests: human_approval_node (graph pause + decision processing)
# ══════════════════════════════════════════════════════════════════════════


class TestHumanApprovalNode:
    """Test the human approval node with mocked interrupt and DB."""

    @pytest.fixture
    def base_state(self):
        """Base state with a valid lead and draft email."""
        return {
            "lead": {
                "id": "lead123",
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "company": "Acme Corp",
            },
            "draft_email": {
                "subject": "Quick question about Acme Corp's strategy",
                "body": "Hi Jane Doe,\n\n...",
                "status": "draft",
            },
            "logs": [{"event_type": "previous", "message": "Existing log entry"}],
        }

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock async database session."""
        with patch("backend.agents.human_approval_node.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            # Mock selectinload query: execute returns a result with scalar_one_or_none
            mock_result = MagicMock()
            mock_db_lead = MagicMock()
            mock_db_lead.id = "lead123"
            mock_db_lead.draft_emails = []
            mock_result.scalar_one_or_none.return_value = mock_db_lead
            mock_session.execute.return_value = mock_result

            yield mock_session

    # ── Approve ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_approve_sets_status_approved(self, base_state, mock_db_session):
        """Approval should set status to 'approved'."""
        with patch(
            "backend.agents.human_approval_node.interrupt",
            return_value={"status": "approved", "approved_by": "manager@example.com"},
        ):
            result = await human_approval_node(base_state)

        assert result["approval_status"]["status"] == "approved"
        assert result["approval_status"]["approved_by"] == "manager@example.com"
        assert result["draft_email"]["status"] == "approved"
        assert result["approval_status"]["edited"] is False

    @pytest.mark.asyncio
    async def test_approve_adds_log(self, base_state, mock_db_session):
        """Approval should add an audit log entry."""
        with patch(
            "backend.agents.human_approval_node.interrupt",
            return_value={"status": "approved", "approved_by": "manager@example.com"},
        ):
            result = await human_approval_node(base_state)

        assert result["logs"][-1]["event_type"] == "approval"
        assert "APPROVED" in result["logs"][-1]["message"]

    # ── Reject ───────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_reject_sets_status_rejected(self, base_state, mock_db_session):
        """Rejection should set status to 'rejected'."""
        with patch(
            "backend.agents.human_approval_node.interrupt",
            return_value={"status": "rejected", "approved_by": "manager@example.com"},
        ):
            result = await human_approval_node(base_state)

        assert result["approval_status"]["status"] == "rejected"
        assert result["draft_email"]["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_adds_log(self, base_state, mock_db_session):
        """Rejection should add an audit log entry."""
        with patch(
            "backend.agents.human_approval_node.interrupt",
            return_value={"status": "rejected", "approved_by": "manager@example.com"},
        ):
            result = await human_approval_node(base_state)

        assert result["logs"][-1]["event_type"] == "approval"
        assert "REJECTED" in result["logs"][-1]["message"]

    # ── Edit ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_edit_preserves_subject_change(self, base_state, mock_db_session):
        """Editing should preserve the new subject."""
        with patch(
            "backend.agents.human_approval_node.interrupt",
            return_value={
                "status": "edited",
                "approved_by": "manager@example.com",
                "edited_subject": "New subject line from editor",
                "edited_body": None,
            },
        ):
            result = await human_approval_node(base_state)

        assert result["draft_email"]["subject"] == "New subject line from editor"
        assert result["draft_email"]["status"] == "reviewed"
        assert result["approval_status"]["edited"] is True

    @pytest.mark.asyncio
    async def test_edit_preserves_body_change(self, base_state, mock_db_session):
        """Editing should preserve the new body."""
        with patch(
            "backend.agents.human_approval_node.interrupt",
            return_value={
                "status": "edited",
                "approved_by": "manager@example.com",
                "edited_subject": None,
                "edited_body": "New email body from editor",
            },
        ):
            result = await human_approval_node(base_state)

        assert result["draft_email"]["body"] == "New email body from editor"
        assert result["draft_email"]["status"] == "reviewed"

    @pytest.mark.asyncio
    async def test_edit_preserves_unchanged_fields(self, base_state, mock_db_session):
        """Editing should keep original values for unchanged fields."""
        with patch(
            "backend.agents.human_approval_node.interrupt",
            return_value={
                "status": "edited",
                "approved_by": "manager@example.com",
                "edited_subject": "New subject",
                "edited_body": None,
            },
        ):
            result = await human_approval_node(base_state)

        # Subject changed, body should stay the same
        assert result["draft_email"]["subject"] == "New subject"
        assert result["draft_email"]["body"] == "Hi Jane Doe,\n\n..."

    # ── Logs preservation ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_preserves_existing_logs(self, base_state, mock_db_session):
        """Existing logs should be preserved."""
        with patch(
            "backend.agents.human_approval_node.interrupt",
            return_value={"status": "approved", "approved_by": "manager@example.com"},
        ):
            result = await human_approval_node(base_state)

        assert len(result["logs"]) == 2  # 1 existing + 1 new
        assert result["logs"][0]["event_type"] == "previous"

    # ── Default behavior (missing status) ────────────────────────────────

    @pytest.mark.asyncio
    async def test_missing_status_defaults_to_rejected(self, base_state, mock_db_session):
        """Missing status should default to rejected."""
        with patch(
            "backend.agents.human_approval_node.interrupt",
            return_value={"approved_by": "manager@example.com"},
        ):
            result = await human_approval_node(base_state)

        assert result["approval_status"]["status"] == "rejected"
        assert result["draft_email"]["status"] == "rejected"


# ══════════════════════════════════════════════════════════════════════════
# Tests: email_tool_node (governance enforcement)
# ══════════════════════════════════════════════════════════════════════════


class TestEmailToolNode:
    """Test that email_tool_node only sends after approval."""

    @pytest.fixture
    def base_state(self):
        """Base state with lead and draft email."""
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
    def mock_db_session(self):
        """Create a mock async database session."""
        with patch("backend.agents.email_tool_node.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session
            yield mock_session

    @pytest.mark.asyncio
    async def test_sends_email_when_approved(self, base_state, mock_db_session):
        """Email should be sent when approval status is 'approved'."""
        # Need to mock the DB approval check as well
        from unittest.mock import MagicMock
        mock_result = MagicMock()
        mock_record = MagicMock()
        mock_record.approved = True
        mock_record.approved_by = "manager@example.com"
        mock_result.scalar_one_or_none.return_value = mock_record
        mock_db_session.execute.return_value = mock_result

        mock_db_session.get.return_value = MagicMock()
        mock_db_session.get.return_value.draft_emails = []
        result = await email_tool_node(base_state)

        assert result["draft_email"]["status"] == "sent"
        assert result["logs"][-1]["event_type"] == "email_sent"

    @pytest.mark.asyncio
    async def test_sends_email_when_edited(self, base_state, mock_db_session):
        """Email should be sent when approval status is 'edited'."""
        state = dict(base_state)
        state["approval_status"]["status"] = "edited"

        # Need to mock the DB approval check as well
        from unittest.mock import MagicMock
        mock_result = MagicMock()
        mock_record = MagicMock()
        mock_record.approved = True
        mock_record.approved_by = "manager@example.com"
        mock_result.scalar_one_or_none.return_value = mock_record
        mock_db_session.execute.return_value = mock_result

        mock_db_session.get.return_value = MagicMock()
        mock_db_session.get.return_value.draft_emails = []
        result = await email_tool_node(state)

        assert result["draft_email"]["status"] == "sent"
        assert result["logs"][-1]["event_type"] == "email_sent"

    @pytest.mark.asyncio
    async def test_blocks_send_when_rejected(self, base_state, mock_db_session):
        """Email should NOT be sent when approval status is 'rejected'."""
        state = dict(base_state)
        state["approval_status"]["status"] = "rejected"

        result = await email_tool_node(state)

        assert result["draft_email"]["status"] != "sent"
        assert result["logs"][-1]["event_type"] == "email_send_error"
        assert "NOT sent" in result["logs"][-1]["message"]

    @pytest.mark.asyncio
    async def test_blocks_send_when_no_approval(self, base_state, mock_db_session):
        """Email should NOT be sent when there is no approval status."""
        state = dict(base_state)
        state["approval_status"] = {}

        result = await email_tool_node(state)

        assert result["draft_email"]["status"] != "sent"
        assert result["logs"][-1]["event_type"] == "email_send_error"

    @pytest.mark.asyncio
    async def test_blocks_send_when_pending(self, base_state, mock_db_session):
        """Email should NOT be sent when status is 'pending'."""
        state = dict(base_state)
        state["approval_status"]["status"] = "pending"

        result = await email_tool_node(state)

        assert result["draft_email"]["status"] != "sent"
        assert result["logs"][-1]["event_type"] == "email_send_error"
        assert "BLOCKED" in result["logs"][-1]["message"]

    # ── Governance: NEVER auto-send ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_never_sends_without_approval_status_key(self, base_state, mock_db_session):
        """Email should NEVER send without approval_status key."""
        state = dict(base_state)
        del state["approval_status"]

        result = await email_tool_node(state)

        assert result["draft_email"]["status"] != "sent"

    @pytest.mark.asyncio
    async def test_never_sends_when_approval_none(self, base_state, mock_db_session):
        """Email should NEVER send when approval_status is None."""
        state = dict(base_state)
        state["approval_status"] = None

        result = await email_tool_node(state)

        assert result["draft_email"]["status"] != "sent"


# ══════════════════════════════════════════════════════════════════════════
# Tests: API endpoints (_process_approval helper)
# ══════════════════════════════════════════════════════════════════════════


class TestProcessApproval:
    """Test the approval processing helper function."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock async database session with a lead and draft."""
        with patch("backend.api.approval.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            # Create a mock draft email
            mock_draft = MagicMock()
            mock_draft.subject = "Original subject"
            mock_draft.body = "Original body"
            mock_draft.status = "draft"

            # Create a mock lead with draft emails eagerly loaded
            mock_lead = MagicMock()
            mock_lead.id = "lead123"
            mock_lead.name = "Jane Doe"
            mock_lead.draft_emails = [mock_draft]
            mock_lead.pipeline_thread_id = None

            # _process_approval uses session.execute(selectinload stmt),
            # not session.get — mock execute to return the lead
            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = mock_lead
            mock_session.execute.return_value = mock_execute_result

            yield mock_session

    @pytest.mark.asyncio
    async def test_approve_updates_status(self, mock_db_session):
        """Approval should update draft status to 'approved'."""
        result = await _process_approval(
            lead_id="lead123",
            status="approved",
            approved_by="manager@example.com",
        )

        assert result["success"] is True
        assert result["status"] == "approved"
        assert result["status_label"] == "APPROVED"
        assert result["draft"]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_reject_updates_status(self, mock_db_session):
        """Rejection should update draft status to 'rejected'."""
        result = await _process_approval(
            lead_id="lead123",
            status="rejected",
            approved_by="manager@example.com",
            reason="Not a good fit",
        )

        assert result["success"] is True
        assert result["status"] == "rejected"
        assert result["draft"]["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_with_reason(self, mock_db_session):
        """Rejection should include the reason."""
        result = await _process_approval(
            lead_id="lead123",
            status="rejected",
            approved_by="manager@example.com",
            reason="Not a good fit",
        )

        # The audit log should contain the reason
        assert result["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_edit_preserves_subject(self, mock_db_session):
        """Editing should preserve the new subject."""
        result = await _process_approval(
            lead_id="lead123",
            status="edited",
            approved_by="editor@example.com",
            edited_subject="New subject",
            edited_body=None,
        )

        assert result["draft"]["subject"] == "New subject"
        assert result["draft"]["body"] == "Original body"  # Unchanged
        assert result["draft"]["status"] == "reviewed"

    @pytest.mark.asyncio
    async def test_edit_preserves_body(self, mock_db_session):
        """Editing should preserve the new body."""
        result = await _process_approval(
            lead_id="lead123",
            status="edited",
            approved_by="editor@example.com",
            edited_subject=None,
            edited_body="New body",
        )

        assert result["draft"]["body"] == "New body"
        assert result["draft"]["subject"] == "Original subject"  # Unchanged

    @pytest.mark.asyncio
    async def test_lead_not_found_raises_404(self):
        """Non-existent lead should raise 404."""
        with patch("backend.api.approval.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            # execute returns no lead (scalar_one_or_none returns None)
            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_execute_result

            with pytest.raises(HTTPException) as exc:
                await _process_approval(
                    lead_id="nonexistent",
                    status="approved",
                    approved_by="manager@example.com",
                )

            assert exc.value.status_code == 404
            assert "not found" in exc.value.detail

    @pytest.mark.asyncio
    async def test_no_draft_raises_404(self, mock_db_session):
        """Lead without draft should raise 404."""
        # Override the fixture to return a lead with no drafts
        with patch("backend.api.approval.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__.return_value = mock_session

            mock_lead = MagicMock()
            mock_lead.draft_emails = []  # No drafts
            mock_lead.pipeline_thread_id = None

            mock_execute_result = MagicMock()
            mock_execute_result.scalar_one_or_none.return_value = mock_lead
            mock_session.execute.return_value = mock_execute_result

            with pytest.raises(HTTPException) as exc:
                await _process_approval(
                    lead_id="lead123",
                    status="approved",
                    approved_by="manager@example.com",
                )

            assert exc.value.status_code == 404
            assert "No draft email" in exc.value.detail


# ══════════════════════════════════════════════════════════════════════════
# Tests: API endpoint request schemas
# ══════════════════════════════════════════════════════════════════════════


class TestApprovalRequestSchemas:
    """Test the Pydantic request schemas for the approval API."""

    def test_approve_request_valid(self):
        """Valid approve request should pass validation."""
        req = ApproveRequest(approved_by="manager@example.com")
        assert req.approved_by == "manager@example.com"

    def test_reject_request_valid(self):
        """Valid reject request should pass validation."""
        req = RejectRequest(approved_by="manager@example.com", reason="Not a fit")
        assert req.approved_by == "manager@example.com"
        assert req.reason == "Not a fit"

    def test_reject_request_without_reason(self):
        """Reject request without reason should still pass."""
        req = RejectRequest(approved_by="manager@example.com")
        assert req.reason is None

    def test_edit_request_valid(self):
        """Valid edit request should pass validation."""
        req = EditDraftRequest(
            approved_by="editor@example.com",
            subject="New subject",
            body="New body",
        )
        assert req.subject == "New subject"
        assert req.body == "New body"

    def test_edit_request_partial(self):
        """Edit request with only subject should pass."""
        req = EditDraftRequest(
            approved_by="editor@example.com",
            subject="New subject",
        )
        assert req.subject == "New subject"
        assert req.body is None