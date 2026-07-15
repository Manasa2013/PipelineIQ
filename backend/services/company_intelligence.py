"""
Company Intelligence Service — abstracts company data lookups.

Design
------
The abstract base class `CompanyIntelligenceService` defines the
interface for retrieving company enrichment data.  The concrete
`MockCompanyIntelligenceService` reads from a local JSON file,
making it easy to swap in a real API client (Clearbit, Zoominfo,
etc.) later without changing any agent code.

Usage::

    from backend.services.company_intelligence import (
        CompanyIntelligenceService,
        MockCompanyIntelligenceService,
    )

    service = MockCompanyIntelligenceService()
    info = await service.lookup("Acme Corp")
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field


# ── Schema for company intelligence data ──────────────────────────────────


class CompanyInfo(BaseModel):
    """Normalised company data returned by the intelligence service."""

    company_name: str = Field(..., examples=["Acme Corp"])
    industry: str = Field(..., examples=["Enterprise Software"])
    employee_count: int = Field(..., ge=1, examples=[2500])
    company_size: str = Field(..., examples=["1000-5000"])
    location: str = Field(..., examples=["San Francisco, CA"])
    website: Optional[str] = Field(None, examples=["https://acme.com"])
    revenue: Optional[str] = Field(None, examples=["$500M-$1B"])
    founded_year: Optional[int] = Field(None, ge=1600, examples=[2010])
    description: Optional[str] = Field(
        None, examples=["Leading provider of enterprise cloud solutions"]
    )


# ── Abstract interface ───────────────────────────────────────────────────


class CompanyIntelligenceService(ABC):
    """Abstract interface for company data enrichment.

    Subclasses must implement the ``lookup`` method, which accepts a
    company name (or domain) and returns a ``CompanyInfo`` instance
    or ``None`` when no match is found.
    """

    @abstractmethod
    async def lookup(self, company_name: str) -> Optional[CompanyInfo]:
        """Retrieve enrichment data for *company_name*.

        Args:
            company_name: Name of the company to look up (e.g. "Acme Corp").

        Returns:
            A ``CompanyInfo`` instance if found, otherwise ``None``.
        """
        ...


# ── Mock implementation (JSON file) ──────────────────────────────────────


class MockCompanyIntelligenceService(CompanyIntelligenceService):
    """Mock service that reads company data from a local JSON file.

    The JSON file is loaded once on construction and held in memory for
    fast lookups.  Company name matching is case-insensitive and
    tolerant of common suffixes (e.g. "Acme" matches "Acme Corp").
    """

    def __init__(self, data_path: Optional[str] = None) -> None:
        """Initialise the service with data from *data_path*.

        Args:
            data_path: Path to the JSON file.  Defaults to
                ``backend/services/company_data.json`` relative to
                this file's location.
        """
        if data_path is None:
            data_path = os.path.join(
                os.path.dirname(__file__), "company_data.json"
            )
        self._data_path = data_path
        self._companies: list[dict] = self._load_data()

    # ── Public API ───────────────────────────────────────────────────────

    async def lookup(self, company_name: str) -> Optional[CompanyInfo]:
        """Look up a company by name (case-insensitive, fuzzy match).

        Matching strategy:
          1. Exact match (case-insensitive).
          2. Partial match — the query is a leading substring of the
             stored company name (e.g. "Acme" → "Acme Corp").
          3. Token match — at least one word in the query appears in
             the stored company name.

        Returns ``None`` when no match is found.
        """
        if not company_name or not company_name.strip():
            return None

        query = company_name.strip()
        query_lower = query.lower()

        # 1. Exact match (case-insensitive)
        for company in self._companies:
            if company["company_name"].lower() == query_lower:
                return CompanyInfo(**company)

        # 2. Partial match — query is a leading substring of stored name
        for company in self._companies:
            if company["company_name"].lower().startswith(query_lower):
                return CompanyInfo(**company)

        # 3. Token match — any query word appears in stored name
        query_tokens = query_lower.split()
        for company in self._companies:
            stored_lower = company["company_name"].lower()
            if any(token in stored_lower for token in query_tokens):
                return CompanyInfo(**company)

        return None

    # ── Internal helpers ─────────────────────────────────────────────────

    def _load_data(self) -> list[dict]:
        """Load the JSON file and return the list of company records."""
        try:
            with open(self._data_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Failed to load company data from {self._data_path}: {exc}"
            ) from exc

    def reload(self) -> None:
        """Reload company data from disk (useful for testing)."""
        self._companies = self._load_data()


# Module-level singleton for convenience
_default_service: Optional[MockCompanyIntelligenceService] = None


def get_company_intelligence_service() -> CompanyIntelligenceService:
    """Return a singleton ``MockCompanyIntelligenceService`` instance."""
    global _default_service
    if _default_service is None:
        _default_service = MockCompanyIntelligenceService()
    return _default_service