"""
Utility functions and helpers for PipelineIQ.

Includes:
- Normalization utilities (email, company name, role)
- Fairness validation module (score consistency checks)
- Security module (prompt injection defense)
"""

from backend.utils.fairness import (
    build_violation_audit_log,
    compare_scores,
    flag_lead_for_fairness,
    get_profile_key,
    validate_batch,
)
from backend.utils.normalization import (
    normalize_company_name,
    normalize_email,
    normalize_role,
)
from backend.utils.audit_logger import (
    EVENT_TYPES,
    log_event,
    log_events_batch,
)
from backend.utils.security import (
    build_injection_audit_log,
    build_system_prompt_guardrails,
    build_user_prompt_safe,
    detect_injection,
    process_lead_safely,
    sanitize_lead,
    sanitize_text,
    scan_lead_for_injections,
    validate_llm_output,
)

__all__ = [
    "normalize_email",
    "normalize_company_name",
    "normalize_role",
    "get_profile_key",
    "compare_scores",
    "build_violation_audit_log",
    "flag_lead_for_fairness",
    "validate_batch",
    "detect_injection",
    "sanitize_text",
    "sanitize_lead",
    "scan_lead_for_injections",
    "build_injection_audit_log",
    "validate_llm_output",
    "build_system_prompt_guardrails",
    "build_user_prompt_safe",
    "process_lead_safely",
    "log_event",
    "log_events_batch",
    "EVENT_TYPES",
]
