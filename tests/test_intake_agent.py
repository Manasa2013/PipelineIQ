"""
Unit tests for the Intake Agent.

Run with:
    pytest tests/test_intake_agent.py -v
"""

import pytest
from pydantic import ValidationError

from backend.agents.intake_agent import intake_agent
from backend.models.schemas import LeadCreate
from backend.utils.normalization import normalize_email, normalize_company_name, normalize_role


# ── LeadCreate validation ───────────────────────────────────────────────


class TestLeadCreateValidation:
    def test_valid_lead(self):
        """Minimal valid lead data passes validation."""
        lead = LeadCreate(name="Jane Doe", email="jane@acme.com", company="Acme Corp")
        assert lead.name == "Jane Doe"
        assert lead.email == "jane@acme.com"
        assert lead.company == "Acme Corp"

    def test_valid_lead_with_all_fields(self):
        """All optional fields can be provided."""
        lead = LeadCreate(
            name="John Smith",
            email="john@example.com",
            company="Example Inc",
            role="CTO",
            industry="SaaS",
            buying_signals=["visited pricing", "requested demo"],
        )
        assert lead.role == "CTO"
        assert lead.industry == "SaaS"
        assert lead.buying_signals == ["visited pricing", "requested demo"]

    def test_missing_name_raises(self):
        """Name is required."""
        with pytest.raises(ValidationError):
            LeadCreate(email="jane@acme.com", company="Acme Corp")

    def test_missing_email_raises(self):
        """Email is required."""
        with pytest.raises(ValidationError):
            LeadCreate(name="Jane Doe", company="Acme Corp")

    def test_missing_company_raises(self):
        """Company is required."""
        with pytest.raises(ValidationError):
            LeadCreate(name="Jane Doe", email="jane@acme.com")

    def test_invalid_email_raises(self):
        """Invalid email format raises validation error."""
        with pytest.raises(ValidationError):
            LeadCreate(name="Jane Doe", email="not-an-email", company="Acme Corp")

    def test_name_too_long_raises(self):
        """Name exceeding max_length raises validation error."""
        with pytest.raises(ValidationError):
            LeadCreate(
                name="A" * 300,
                email="jane@acme.com",
                company="Acme Corp",
            )


# ── Intake Agent (async) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_intake_agent_valid_lead():
    """Intake agent processes a valid lead and returns enriched state."""
    import uuid
    unique = uuid.uuid4().hex[:8]
    state = {
        "lead": {
            "name": "Jane Doe",
            "email": f"jane.{unique}@acme.com",
            "company": "Acme Corp",
            "role": "CTO",
            "industry": "SaaS",
            "buying_signals": ["visited pricing page"],
        },
        "logs": [],
    }

    result = await intake_agent(state)

    # Lead should be returned with id and created_at
    assert result["lead"]["name"] == "Jane Doe"
    assert result["lead"]["email"] == f"jane.{unique}@acme.com"
    assert result["lead"]["company"] == "Acme"
    assert result["lead"]["role"] == "CTO"
    assert result["lead"]["industry"] == "SaaS"
    assert "id" in result["lead"]
    assert "created_at" in result["lead"]

    # Logs should have one entry
    assert len(result["logs"]) == 1
    assert result["logs"][0]["event_type"] == "intake"


@pytest.mark.asyncio
async def test_intake_agent_normalizes_fields():
    """Intake agent normalizes email, company, and role."""
    import uuid
    unique = uuid.uuid4().hex[:8]
    state = {
        "lead": {
            "name": "  Jane Doe  ",
            "email": f"  {unique.upper()}+TEST@GMAIL.COM  ",
            "company": "  Acme Corp Inc.  ",
            "role": "  vp engineering  ",
            "industry": "  SaaS  ",
        },
        "logs": [],
    }

    result = await intake_agent(state)

    assert result["lead"]["email"] == f"{unique.lower()}@gmail.com"
    assert result["lead"]["company"] == "Acme"
    assert result["lead"]["role"] == "VP Engineering"
    assert result["lead"]["industry"] == "SaaS"


@pytest.mark.asyncio
async def test_intake_agent_handles_validation_error():
    """Intake agent returns error log when validation fails."""
    state = {
        "lead": {
            "name": "Jane Doe",
            "email": "invalid-email",
            "company": "Acme Corp",
        },
        "logs": [],
    }

    result = await intake_agent(state)

    # Lead should be returned as-is (raw)
    assert result["lead"]["email"] == "invalid-email"

    # Logs should contain an error entry
    assert len(result["logs"]) == 1
    assert result["logs"][0]["event_type"] == "intake_error"
    assert "Validation failed" in result["logs"][0]["message"]


@pytest.mark.asyncio
async def test_intake_agent_missing_required_fields():
    """Intake agent returns error when required fields are missing."""
    state = {
        "lead": {
            "name": "Jane Doe",
            # missing email
            # missing company
        },
        "logs": [],
    }

    result = await intake_agent(state)

    assert len(result["logs"]) == 1
    assert result["logs"][0]["event_type"] == "intake_error"


@pytest.mark.asyncio
async def test_intake_agent_preserves_existing_logs():
    """Intake agent appends to existing logs rather than replacing them."""
    import uuid
    unique = uuid.uuid4().hex[:8]
    state = {
        "lead": {
            "name": "Jane Doe",
            "email": f"jane.{unique}@acme.com",
            "company": "Acme Corp",
        },
        "logs": [
            {"event_type": "previous", "message": "Existing log", "timestamp": "2026-01-01T00:00:00"}
        ],
    }

    result = await intake_agent(state)

    assert len(result["logs"]) == 2
    assert result["logs"][0]["event_type"] == "previous"
    assert result["logs"][1]["event_type"] == "intake"


# ── Normalization edge cases (via intake agent) ─────────────────────────


@pytest.mark.asyncio
async def test_intake_agent_empty_buying_signals():
    """Empty buying_signals should default to an empty list."""
    import uuid
    unique = uuid.uuid4().hex[:8]
    state = {
        "lead": {
            "name": "Jane Doe",
            "email": f"jane.{unique}@example.com",
            "company": "Acme Corp",
        },
        "logs": [],
    }

    result = await intake_agent(state)
    assert result["lead"].get("buying_signals") == []


@pytest.mark.asyncio
async def test_intake_agent_gmail_normalization():
    """Gmail addresses with dots and plus signs are normalized."""
    import uuid
    unique = uuid.uuid4().hex[:8]
    state = {
        "lead": {
            "name": "Jane Doe",
            "email": f"{unique}.test+alias@gmail.com",
            "company": "Acme Corp",
        },
        "logs": [],
    }

    result = await intake_agent(state)
    assert result["lead"]["email"] == f"{unique}test@gmail.com"
