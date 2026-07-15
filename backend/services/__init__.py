"""
Business logic services for PipelineIQ.

Currently includes:
- Company Intelligence Service (mock + abstract interface)
"""

from backend.services.company_intelligence import (
    CompanyInfo,
    CompanyIntelligenceService,
    MockCompanyIntelligenceService,
    get_company_intelligence_service,
)

__all__ = [
    "CompanyInfo",
    "CompanyIntelligenceService",
    "MockCompanyIntelligenceService",
    "get_company_intelligence_service",
]
