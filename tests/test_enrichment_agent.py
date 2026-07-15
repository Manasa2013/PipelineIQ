"""
Unit tests for the Enrichment Agent and Company Intelligence Service.

Run with::

    pytest tests/test_enrichment_agent.py -v

Run all tests::

    pytest tests/ -v
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Optional

import pytest

from backend.agents.enrichment_agent import enrichment_agent
from backend.services.company_intelligence import (
    CompanyInfo,
    CompanyIntelligenceService,
    MockCompanyIntelligenceService,
    get_company_intelligence_service,
)


# ══════════════════════════════════════════════════════════════════════════
#  MockCompanyIntelligenceService tests
# ══════════════════════════════════════════════════════════════════════════


class TestMockCompanyIntelligenceService:
    """Tests for the mock company intelligence service."""

    def build_service(self, data: list[dict]) -> MockCompanyIntelligenceService:
        """Build a service from an in-memory JSON file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp_path = f.name
        service = MockCompanyIntelligenceService(data_path=tmp_path)
        # Schedule cleanup
        self._tmp_paths = getattr(self, "_tmp_paths", [])
        self._tmp_paths.append(tmp_path)
        return service

    def teardown_method(self) -> None:
        """Remove temporary files created during tests."""
        for path in getattr(self, "_tmp_paths", []):
            try:
                os.unlink(path)
            except OSError:
                pass

    # ── Lookup tests ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_lookup_exact_match(self):
        """Exact company name match returns correct data."""
        service = self.build_service([
            {"company_name": "Acme Corp", "industry": "Software",
             "employee_count": 100, "company_size": "51-200",
             "location": "SF"},
        ])
        result = await service.lookup("Acme Corp")
        assert result is not None
        assert result.company_name == "Acme Corp"
        assert result.industry == "Software"
        assert result.employee_count == 100

    @pytest.mark.asyncio
    async def test_lookup_case_insensitive(self):
        """Lookup is case-insensitive."""
        service = self.build_service([
            {"company_name": "Acme Corp", "industry": "Software",
             "employee_count": 100, "company_size": "51-200",
             "location": "SF"},
        ])
        result = await service.lookup("acme corp")
        assert result is not None
        assert result.company_name == "Acme Corp"

    @pytest.mark.asyncio
    async def test_lookup_partial_match_prefix(self):
        """Partial match by leading substring works."""
        service = self.build_service([
            {"company_name": "Acme Corp", "industry": "Software",
             "employee_count": 100, "company_size": "51-200",
             "location": "SF"},
        ])
        result = await service.lookup("Acme")
        assert result is not None
        assert result.company_name == "Acme Corp"

    @pytest.mark.asyncio
    async def test_lookup_token_match(self):
        """Token match — query word appears in stored name."""
        service = self.build_service([
            {"company_name": "Globex Inc", "industry": "Manufacturing",
             "employee_count": 500, "company_size": "201-1000",
             "location": "Detroit"},
        ])
        result = await service.lookup("Globex")
        assert result is not None
        assert result.company_name == "Globex Inc"

    @pytest.mark.asyncio
    async def test_lookup_no_match_returns_none(self):
        """No match returns None."""
        service = self.build_service([
            {"company_name": "Acme Corp", "industry": "Software",
             "employee_count": 100, "company_size": "51-200",
             "location": "SF"},
        ])
        result = await service.lookup("NonExistent Inc")
        assert result is None

    @pytest.mark.asyncio
    async def test_lookup_empty_string_returns_none(self):
        """Empty or whitespace-only input returns None."""
        service = self.build_service([
            {"company_name": "Acme Corp", "industry": "Software",
             "employee_count": 100, "company_size": "51-200",
             "location": "SF"},
        ])
        assert await service.lookup("") is None
        assert await service.lookup("   ") is None
        assert await service.lookup(None) is None  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_lookup_missing_data_file_raises(self):
        """Missing JSON file raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Failed to load company data"):
            MockCompanyIntelligenceService(
                data_path="/tmp/nonexistent_file_xyz.json"
            )

    @pytest.mark.asyncio
    async def test_lookup_invalid_json_raises(self):
        """Invalid JSON file raises RuntimeError."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("this is not json")
            tmp_path = f.name
        with pytest.raises(RuntimeError, match="Failed to load company data"):
            MockCompanyIntelligenceService(data_path=tmp_path)
        os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_reload_refreshes_data(self):
        """Calling reload() picks up changes from disk."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump([
                {"company_name": "Acme Corp", "industry": "Software",
                 "employee_count": 100, "company_size": "51-200",
                 "location": "SF"},
            ], f)
            tmp_path = f.name

        service = MockCompanyIntelligenceService(data_path=tmp_path)
        assert await service.lookup("Acme Corp") is not None
        assert await service.lookup("NewCo") is None

        # Update file on disk
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump([
                {"company_name": "NewCo", "industry": "AI",
                 "employee_count": 50, "company_size": "1-50",
                 "location": "NYC"},
            ], f)

        service.reload()
        assert await service.lookup("Acme Corp") is None
        result = await service.lookup("NewCo")
        assert result is not None
        assert result.industry == "AI"

        os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_multiple_companies_returns_first_match(self):
        """When multiple companies match, the first match is returned."""
        service = self.build_service([
            {"company_name": "Acme Corp", "industry": "Software",
             "employee_count": 100, "company_size": "51-200",
             "location": "SF"},
            {"company_name": "Acme Industries", "industry": "Manufacturing",
             "employee_count": 500, "company_size": "201-1000",
             "location": "Chicago"},
        ])
        # Exact match should return the first company
        result = await service.lookup("Acme Corp")
        assert result is not None
        assert result.industry == "Software"

    @pytest.mark.asyncio
    async def test_lookup_returns_company_info_with_all_fields(self):
        """All CompanyInfo fields are properly populated."""
        service = self.build_service([
            {"company_name": "Stark Industries",
             "industry": "Defense & Aerospace",
             "employee_count": 12000,
             "company_size": "10000+",
             "location": "Los Angeles, CA",
             "website": "https://starkindustries.com",
             "revenue": "$10B+",
             "founded_year": 1940,
             "description": "Advanced weapons technology"},
        ])
        result = await service.lookup("Stark Industries")
        assert result is not None
        assert result.website == "https://starkindustries.com"
        assert result.revenue == "$10B+"
        assert result.founded_year == 1940
        assert result.description == "Advanced weapons technology"

    # ── Singleton ───────────────────────────────────────────────────────

    def test_get_company_intelligence_service_returns_singleton(self):
        """get_company_intelligence_service() always returns same instance."""
        s1 = get_company_intelligence_service()
        s2 = get_company_intelligence_service()
        assert s1 is s2
        assert isinstance(s1, MockCompanyIntelligenceService)


# ══════════════════════════════════════════════════════════════════════════
#  Abstract interface tests
# ══════════════════════════════════════════════════════════════════════════


class TestCompanyIntelligenceServiceInterface:
    """Verify that the abstract interface is properly defined."""

    def test_abstract_class_cannot_be_instantiated(self):
        """CompanyIntelligenceService cannot be instantiated directly."""
        with pytest.raises(TypeError):
            CompanyIntelligenceService()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_lookup(self):
        """Subclass without lookup() raises TypeError."""
        with pytest.raises(TypeError):
            type(
                "BadService",
                (CompanyIntelligenceService,),
                {},
            )()

    def test_concrete_subclass_works(self):
        """A proper subclass can be instantiated and used."""
        class GoodService(CompanyIntelligenceService):
            async def lookup(self, company_name: str) -> Optional[CompanyInfo]:
                if company_name == "Test":
                    return CompanyInfo(
                        company_name="Test Corp",
                        industry="Testing",
                        employee_count=10,
                        company_size="1-50",
                        location="Testville",
                    )
                return None

        import asyncio
        service = GoodService()
        result = asyncio.run(service.lookup("Test"))
        assert result is not None
        assert result.company_name == "Test Corp"
        assert result.industry == "Testing"


# ══════════════════════════════════════════════════════════════════════════
#  Enrichment Agent tests
# ══════════════════════════════════════════════════════════════════════════


class TestEnrichmentAgent:
    """Tests for the enrichment_agent LangGraph node.

    These tests inject a mock company intelligence service to avoid
    depending on the real JSON file or database.
    """

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _make_mock_service(data: list[dict]) -> MockCompanyIntelligenceService:
        """Create a temporary MockCompanyIntelligenceService for testing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp_path = f.name
        service = MockCompanyIntelligenceService(data_path=tmp_path)
        # Store path for cleanup
        service._tmp_path = tmp_path
        return service

    @staticmethod
    def _cleanup_mock_service(service: MockCompanyIntelligenceService) -> None:
        """Remove the temporary file created for a mock service."""
        path = getattr(service, "_tmp_path", None)
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass

    # ── Successful enrichment ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_enrichment_agent_lookup_found(self):
        """Enrichment agent returns company data when lookup succeeds."""
        service = self._make_mock_service([
            {"company_name": "Acme Corp", "industry": "Enterprise Software",
             "employee_count": 2500, "company_size": "1000-5000",
             "location": "San Francisco, CA",
             "website": "https://acme.com", "revenue": "$500M-$1B",
             "founded_year": 2010,
             "description": "Leading provider of enterprise cloud solutions"},
        ])

        state = {
            "lead": {
                "id": "test_lead_001",
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "company": "Acme Corp",
                "industry": "Technology",
            },
            "logs": [],
        }

        result = await enrichment_agent(state, company_intelligence=service)

        # Enrichment data should be populated
        enrichment = result.get("enrichment", {})
        assert enrichment["company_name"] == "Acme Corp"
        assert enrichment["company_industry"] == "Enterprise Software"
        assert enrichment["employee_count"] == 2500
        assert enrichment["company_size"] == "1000-5000"
        assert enrichment["company_location"] == "San Francisco, CA"
        assert enrichment["website"] == "https://acme.com"
        assert enrichment["revenue"] == "$500M-$1B"
        assert enrichment["founded_year"] == 2010
        assert enrichment["description"] == "Leading provider of enterprise cloud solutions"

        # Lead should be enriched with company data
        assert result["lead"]["company_industry"] == "Enterprise Software"
        assert result["lead"]["employee_count"] == 2500

        # Logs should have one entry
        assert len(result["logs"]) == 1
        assert result["logs"][0]["event_type"] == "enrichment"

        self._cleanup_mock_service(service)

    @pytest.mark.asyncio
    async def test_enrichment_agent_lookup_not_found_fallback(self):
        """Enrichment agent falls back to lead data when company not found."""
        service = self._make_mock_service([])

        state = {
            "lead": {
                "id": "test_lead_002",
                "name": "John Smith",
                "email": "john@unknown.com",
                "company": "Unknown Inc",
                "industry": "Biotech",
                "company_size": "Unknown",
                "employee_count": 0,
                "company_location": "Unknown",
            },
            "logs": [],
        }

        result = await enrichment_agent(state, company_intelligence=service)

        enrichment = result.get("enrichment", {})
        assert enrichment["company_industry"] == "Biotech"
        assert enrichment["employee_count"] == 0
        assert enrichment["company_size"] == "Unknown"
        assert enrichment["company_location"] == "Unknown"
        assert enrichment["website"] is None

        self._cleanup_mock_service(service)

    @pytest.mark.asyncio
    async def test_enrichment_agent_preserves_existing_logs(self):
        """Enrichment agent appends to existing logs."""
        service = self._make_mock_service([
            {"company_name": "Acme Corp", "industry": "Software",
             "employee_count": 100, "company_size": "51-200",
             "location": "SF"},
        ])

        state = {
            "lead": {
                "id": "test_lead_003",
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "company": "Acme Corp",
            },
            "logs": [
                {"event_type": "intake", "message": "Lead ingested",
                 "timestamp": "2026-01-01T00:00:00"},
            ],
        }

        result = await enrichment_agent(state, company_intelligence=service)

        assert len(result["logs"]) == 2
        assert result["logs"][0]["event_type"] == "intake"
        assert result["logs"][1]["event_type"] == "enrichment"

        self._cleanup_mock_service(service)

    @pytest.mark.asyncio
    async def test_enrichment_agent_no_lead_id(self):
        """Enrichment agent works without a lead ID (no DB persistence)."""
        service = self._make_mock_service([
            {"company_name": "Acme Corp", "industry": "Software",
             "employee_count": 100, "company_size": "51-200",
             "location": "SF"},
        ])

        state = {
            "lead": {
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "company": "Acme Corp",
            },
            "logs": [],
        }

        # Should not crash when no lead ID is present
        result = await enrichment_agent(state, company_intelligence=service)

        enrichment = result.get("enrichment", {})
        assert enrichment["company_industry"] == "Software"
        assert len(result["logs"]) == 1
        assert result["logs"][0]["event_type"] == "enrichment"

        self._cleanup_mock_service(service)

    @pytest.mark.asyncio
    async def test_enrichment_agent_empty_company_name(self):
        """Enrichment agent handles empty company name gracefully."""
        service = self._make_mock_service([
            {"company_name": "Acme Corp", "industry": "Software",
             "employee_count": 100, "company_size": "51-200",
             "location": "SF"},
        ])

        state = {
            "lead": {
                "id": "test_lead_004",
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "company": "",
            },
            "logs": [],
        }

        result = await enrichment_agent(state, company_intelligence=service)

        enrichment = result.get("enrichment", {})
        assert enrichment["company_industry"] == "Unknown"
        assert enrichment["website"] is None

        self._cleanup_mock_service(service)

    @pytest.mark.asyncio
    async def test_enrichment_agent_uses_default_service(self):
        """Enrichment agent uses the default singleton when no service injected."""
        state = {
            "lead": {
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "company": "Acme Corp",
            },
            "logs": [],
        }

        # This should use the default MockCompanyIntelligenceService
        result = await enrichment_agent(state)

        # The default service has the full company_data.json loaded,
        # so "Acme Corp" should be found
        enrichment = result.get("enrichment", {})
        assert enrichment.get("company_industry") is not None
        assert "company_name" in enrichment

    @pytest.mark.asyncio
    async def test_enrichment_agent_company_name_substring(self):
        """Company name substring matching works (e.g. 'Acme' → 'Acme Corp')."""
        service = self._make_mock_service([
            {"company_name": "Acme Corp", "industry": "Enterprise Software",
             "employee_count": 2500, "company_size": "1000-5000",
             "location": "San Francisco, CA"},
        ])

        state = {
            "lead": {
                "id": "test_lead_005",
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "company": "Acme",
            },
            "logs": [],
        }

        result = await enrichment_agent(state, company_intelligence=service)

        enrichment = result.get("enrichment", {})
        assert enrichment["company_name"] == "Acme Corp"
        assert enrichment["company_industry"] == "Enterprise Software"

        self._cleanup_mock_service(service)

    @pytest.mark.asyncio
    async def test_enrichment_agent_replaces_existing_enrichment_data(self):
        """Enrichment overwrites any existing enrichment data on the lead."""
        service = self._make_mock_service([
            {"company_name": "Acme Corp", "industry": "Enterprise Software",
             "employee_count": 2500, "company_size": "1000-5000",
             "location": "San Francisco, CA"},
        ])

        state = {
            "lead": {
                "id": "test_lead_006",
                "name": "Jane Doe",
                "email": "jane@acme.com",
                "company": "Acme Corp",
                "company_industry": "Old Industry",
                "employee_count": 10,
            },
            "logs": [],
        }

        result = await enrichment_agent(state, company_intelligence=service)

        # Old values should be replaced
        assert result["lead"]["company_industry"] == "Enterprise Software"
        assert result["lead"]["employee_count"] == 2500

        self._cleanup_mock_service(service)