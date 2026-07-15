"""
Unit tests for the Fairness Validation Module.

Run with::

    pytest tests/test_fairness.py -v

Run all tests::

    pytest tests/ -v
"""

from __future__ import annotations

from backend.utils.fairness import (
    build_violation_audit_log,
    compare_scores,
    flag_lead_for_fairness,
    get_profile_key,
    validate_batch,
)


# ══════════════════════════════════════════════════════════════════════════
#  get_profile_key tests
# ══════════════════════════════════════════════════════════════════════════


class TestGetProfileKey:
    """Tests for extracting the non-demographic profile signature."""

    def test_excludes_name(self):
        """Lead name is NOT in the profile key."""
        lead = {"name": "Jane Doe", "company": "Acme Corp", "role": "CTO",
                "industry": "Technology", "email": "jane@acme.com"}
        key = get_profile_key(lead)
        assert "name" not in key
        assert "Jane" not in str(key)
        assert "Doe" not in str(key)

    def test_includes_company_role_industry(self):
        """Company, role, and industry are in the profile key."""
        lead = {"name": "Jane Doe", "company": "Acme Corp", "role": "CTO",
                "industry": "Technology", "email": "jane@acme.com"}
        key = get_profile_key(lead)
        assert key["company"] == "acme corp"
        assert key["role"] == "cto"
        assert key["industry"] == "technology"

    def test_includes_email_domain(self):
        """Email domain (not full email) is in the profile key."""
        lead = {"name": "Jane Doe", "company": "Acme Corp", "role": "CTO",
                "industry": "Technology", "email": "jane@acme.com"}
        key = get_profile_key(lead)
        assert key["email_domain"] == "acme.com"

    def test_includes_buying_signals_sorted(self):
        """Buying signals are included and sorted."""
        lead = {"name": "Jane Doe", "company": "Acme Corp", "role": "CTO",
                "industry": "Technology", "email": "jane@acme.com",
                "buying_signals": ["demo", "pricing"]}
        key = get_profile_key(lead)
        assert key["buying_signals"] == ["demo", "pricing"]

    def test_includes_enrichment_data(self):
        """Enrichment data is included when provided."""
        lead = {"name": "Jane Doe", "company": "Acme Corp", "role": "CTO",
                "industry": "Technology", "email": "jane@acme.com"}
        enrichment = {
            "company_size": "1000-5000",
            "company_industry": "Enterprise Software",
            "employee_count": 2500,
            "company_location": "San Francisco, CA",
        }
        key = get_profile_key(lead, enrichment)
        assert key["company_size"] == "1000-5000"
        assert key["company_industry"] == "enterprise software"
        assert key["employee_count"] == 2500
        assert key["company_location"] == "san francisco, ca"

    def test_empty_lead_returns_empty_fields(self):
        """Empty lead returns empty strings for all fields."""
        key = get_profile_key({})
        assert key["company"] == ""
        assert key["role"] == ""
        assert key["industry"] == ""
        assert key["email_domain"] == ""
        assert key["buying_signals"] == []

    def test_normalises_case_and_whitespace(self):
        """Profile key values are normalised (lowercase, stripped)."""
        lead = {"name": "  Jane Doe  ", "company": "  ACME CORP  ",
                "role": "  CTO  ", "industry": "  TECHNOLOGY  ",
                "email": "  JANE@ACME.COM  "}
        key = get_profile_key(lead)
        assert key["company"] == "acme corp"
        assert key["role"] == "cto"
        assert key["industry"] == "technology"
        assert key["email_domain"] == "acme.com"

    def test_different_names_same_profile(self):
        """Two leads with different names but same profile produce same key."""
        lead_a = {"name": "Alice Smith", "company": "Acme Corp", "role": "CTO",
                  "industry": "Technology", "email": "alice@acme.com"}
        lead_b = {"name": "Bob Jones", "company": "Acme Corp", "role": "CTO",
                  "industry": "Technology", "email": "bob@acme.com"}

        key_a = get_profile_key(lead_a)
        key_b = get_profile_key(lead_b)
        assert key_a == key_b


# ══════════════════════════════════════════════════════════════════════════
#  compare_scores tests
# ══════════════════════════════════════════════════════════════════════════


class TestCompareScores:
    """Tests for comparing scores between two leads."""

    def test_same_profile_same_score_no_violation(self):
        """Same profile with same score → no violation."""
        lead_a = {"id": "lead_001", "name": "Alice", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "alice@acme.com"}
        lead_b = {"id": "lead_002", "name": "Bob", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "bob@acme.com"}
        score_a = {"score": 85, "confidence": 0.9, "reasons": ["Good"]}
        score_b = {"score": 85, "confidence": 0.9, "reasons": ["Good"]}

        result = compare_scores(lead_a, score_a, lead_b, score_b)
        assert result["violation"] is False
        assert "No fairness violation" in result["reason"]

    def test_same_profile_different_score_violation(self):
        """Same profile with different score → violation."""
        lead_a = {"id": "lead_001", "name": "Alice", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "alice@acme.com"}
        lead_b = {"id": "lead_002", "name": "Bob", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "bob@acme.com"}
        score_a = {"score": 85, "confidence": 0.9, "reasons": ["Good"]}
        score_b = {"score": 42, "confidence": 0.6, "reasons": ["Bad"]}

        result = compare_scores(lead_a, score_a, lead_b, score_b)
        assert result["violation"] is True
        assert "Fairness violation" in result["reason"]
        assert "85" in result["reason"]
        assert "42" in result["reason"]

    def test_different_profile_no_violation(self):
        """Different profiles → no violation, even if scores differ."""
        lead_a = {"id": "lead_001", "name": "Alice", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "alice@acme.com"}
        lead_b = {"id": "lead_002", "name": "Bob", "company": "Globex Inc",
                  "role": "Engineer", "industry": "Manufacturing", "email": "bob@globex.com"}
        score_a = {"score": 85, "confidence": 0.9, "reasons": ["Good"]}
        score_b = {"score": 42, "confidence": 0.6, "reasons": ["Bad"]}

        result = compare_scores(lead_a, score_a, lead_b, score_b)
        assert result["violation"] is False
        assert "Profiles differ" in result["reason"]

    def test_violation_with_enrichment(self):
        """Same enrichment → same profile → violation on different scores."""
        enrichment = {"company_size": "1000-5000", "company_industry": "Software",
                      "employee_count": 2500, "company_location": "SF"}
        lead_a = {"id": "lead_001", "name": "Alice", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "alice@acme.com"}
        lead_b = {"id": "lead_002", "name": "Bob", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "bob@acme.com"}
        score_a = {"score": 90, "confidence": 0.9, "reasons": ["Good"]}
        score_b = {"score": 50, "confidence": 0.6, "reasons": ["Bad"]}

        result = compare_scores(lead_a, score_a, lead_b, score_b,
                                enrichment_a=enrichment, enrichment_b=enrichment)
        assert result["violation"] is True
        assert result["score_a"] == 90
        assert result["score_b"] == 50

    def test_both_scores_none_no_violation(self):
        """Both scores None → no violation possible."""
        lead_a = {"id": "lead_001", "name": "Alice", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "alice@acme.com"}
        lead_b = {"id": "lead_002", "name": "Bob", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "bob@acme.com"}
        score_a = {}
        score_b = {}

        result = compare_scores(lead_a, score_a, lead_b, score_b)
        assert result["violation"] is False

    def test_violation_returns_lead_ids(self):
        """Violation result includes lead IDs."""
        lead_a = {"id": "lead_001", "name": "Alice", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "alice@acme.com"}
        lead_b = {"id": "lead_002", "name": "Bob", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "bob@acme.com"}
        score_a = {"score": 85}
        score_b = {"score": 42}

        result = compare_scores(lead_a, score_a, lead_b, score_b)
        assert result["lead_a_id"] == "lead_001"
        assert result["lead_b_id"] == "lead_002"

    def test_violation_profile_key_matches(self):
        """Violation result includes the shared profile key."""
        lead_a = {"id": "lead_001", "name": "Alice", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "alice@acme.com"}
        lead_b = {"id": "lead_002", "name": "Bob", "company": "Acme Corp",
                  "role": "CTO", "industry": "Technology", "email": "bob@acme.com"}
        score_a = {"score": 85}
        score_b = {"score": 42}

        result = compare_scores(lead_a, score_a, lead_b, score_b)
        assert result["profile_key"] is not None
        assert result["profile_key"]["company"] == "acme corp"
        assert result["profile_key"]["role"] == "cto"


# ══════════════════════════════════════════════════════════════════════════
#  build_violation_audit_log tests
# ══════════════════════════════════════════════════════════════════════════


class TestBuildViolationAuditLog:
    """Tests for building audit log entries from fairness violations."""

    def test_returns_none_when_no_violation(self):
        """No violation → returns None."""
        result = {"violation": False, "reason": "OK",
                  "lead_a_id": "a", "lead_b_id": "b",
                  "score_a": 50, "score_b": 50, "profile_key": {}}
        log = build_violation_audit_log(result)
        assert log is None

    def test_returns_log_when_violation(self):
        """Violation → returns audit log entry."""
        result = {"violation": True, "reason": "Scores differ: 85 vs 42",
                  "lead_a_id": "lead_001", "lead_b_id": "lead_002",
                  "score_a": 85, "score_b": 42, "profile_key": {"company": "acme"}}
        log = build_violation_audit_log(result, lead_name_a="Alice", lead_name_b="Bob")
        assert log is not None
        assert log["event_type"] == "fairness_violation"
        assert "Alice" in log["message"]
        assert "Bob" in log["message"]
        assert "lead_001" in log["message"]
        assert "lead_002" in log["message"]

    def test_log_has_timestamp(self):
        """Audit log entry has a timestamp."""
        result = {"violation": True, "reason": "Scores differ: 85 vs 42",
                  "lead_a_id": "a", "lead_b_id": "b",
                  "score_a": 85, "score_b": 42, "profile_key": {}}
        log = build_violation_audit_log(result)
        assert "timestamp" in log
        assert log["timestamp"] is not None

    def test_log_has_metadata(self):
        """Audit log entry has metadata with score details."""
        result = {"violation": True, "reason": "Scores differ: 85 vs 42",
                  "lead_a_id": "a", "lead_b_id": "b",
                  "score_a": 85, "score_b": 42, "profile_key": {"company": "acme"}}
        log = build_violation_audit_log(result)
        assert log["metadata"]["score_a"] == 85
        assert log["metadata"]["score_b"] == 42
        assert log["metadata"]["profile_key"] == {"company": "acme"}


# ══════════════════════════════════════════════════════════════════════════
#  flag_lead_for_fairness tests
# ══════════════════════════════════════════════════════════════════════════


class TestFlagLeadForFairness:
    """Tests for flagging leads with fairness violations."""

    def test_adds_flag_on_violation(self):
        """Violation adds fairness_flag to lead."""
        lead = {"id": "lead_001", "name": "Alice"}
        result = {"violation": True, "reason": "Scores differ",
                  "lead_a_id": "lead_001", "lead_b_id": "lead_002",
                  "score_a": 85, "score_b": 42, "profile_key": {}}
        flagged = flag_lead_for_fairness(lead, result)
        assert flagged["fairness_flag"]["type"] == "fairness_violation"
        assert flagged["fairness_flag"]["compared_with"] == "lead_002"
        assert flagged["fairness_flag"]["score_difference"] == 43

    def test_removes_flag_on_no_violation(self):
        """No violation removes any existing fairness_flag."""
        lead = {"id": "lead_001", "name": "Alice", "fairness_flag": {"old": "data"}}
        result = {"violation": False, "reason": "OK",
                  "lead_a_id": "lead_001", "lead_b_id": "lead_002",
                  "score_a": 85, "score_b": 85, "profile_key": {}}
        flagged = flag_lead_for_fairness(lead, result)
        assert "fairness_flag" not in flagged

    def test_returns_lead_for_chaining(self):
        """Function returns the lead for chaining."""
        lead = {"id": "lead_001", "name": "Alice"}
        result = {"violation": False, "reason": "OK",
                  "lead_a_id": "lead_001", "lead_b_id": "lead_002",
                  "score_a": 85, "score_b": 85, "profile_key": {}}
        returned = flag_lead_for_fairness(lead, result)
        assert returned is lead  # Same object returned


# ══════════════════════════════════════════════════════════════════════════
#  validate_batch tests
# ══════════════════════════════════════════════════════════════════════════


class TestValidateBatch:
    """Tests for batch validation of scored leads."""

    def test_empty_batch(self):
        """Empty batch returns no violations."""
        violations = validate_batch([])
        assert violations == []

    def test_single_lead(self):
        """Single lead returns no violations."""
        leads = [
            {"lead": {"id": "1", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "a@acme.com"},
             "score": {"score": 85}},
        ]
        violations = validate_batch(leads)
        assert violations == []

    def test_same_profile_same_score_no_violations(self):
        """Same profile with same score → no violations."""
        leads = [
            {"lead": {"id": "1", "name": "Alice", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "a@acme.com"},
             "score": {"score": 85}},
            {"lead": {"id": "2", "name": "Bob", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "b@acme.com"},
             "score": {"score": 85}},
        ]
        violations = validate_batch(leads)
        assert violations == []

    def test_same_profile_different_score_violation(self):
        """Same profile with different score → violation detected."""
        leads = [
            {"lead": {"id": "1", "name": "Alice", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "a@acme.com"},
             "score": {"score": 85}},
            {"lead": {"id": "2", "name": "Bob", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "b@acme.com"},
             "score": {"score": 42}},
        ]
        violations = validate_batch(leads)
        assert len(violations) == 1
        assert violations[0]["violation"] is True

    def test_multiple_violations(self):
        """Multiple pairs with violations are all detected."""
        leads = [
            {"lead": {"id": "1", "name": "Alice", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "a@acme.com"},
             "score": {"score": 85}},
            {"lead": {"id": "2", "name": "Bob", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "b@acme.com"},
             "score": {"score": 42}},
            {"lead": {"id": "3", "name": "Charlie", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "c@acme.com"},
             "score": {"score": 60}},
        ]
        violations = validate_batch(leads)
        # 3 leads = 3 pairs (1-2, 1-3, 2-3) → all should be violations
        assert len(violations) == 3

    def test_different_profiles_no_violation(self):
        """Different profiles → no violations even if scores differ."""
        leads = [
            {"lead": {"id": "1", "name": "Alice", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "a@acme.com"},
             "score": {"score": 85}},
            {"lead": {"id": "2", "name": "Bob", "company": "Globex", "role": "Engineer",
                      "industry": "Manufacturing", "email": "b@globex.com"},
             "score": {"score": 42}},
        ]
        violations = validate_batch(leads)
        assert violations == []

    def test_mixed_profiles_only_violations_in_groups(self):
        """Only same-profile pairs with different scores trigger violations."""
        leads = [
            # Group 1: Acme CTOs → potential violation
            {"lead": {"id": "1", "name": "Alice", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "a@acme.com"},
             "score": {"score": 85}},
            {"lead": {"id": "2", "name": "Bob", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "b@acme.com"},
             "score": {"score": 42}},
            # Group 2: Globex Engineers → consistent scores, no violation
            {"lead": {"id": "3", "name": "Charlie", "company": "Globex", "role": "Engineer",
                      "industry": "Manufacturing", "email": "c@globex.com"},
             "score": {"score": 50}},
            {"lead": {"id": "4", "name": "Diana", "company": "Globex", "role": "Engineer",
                      "industry": "Manufacturing", "email": "d@globex.com"},
             "score": {"score": 50}},
        ]
        violations = validate_batch(leads)
        # Only the Acme pair should have a violation
        assert len(violations) == 1
        assert violations[0]["lead_a_id"] in ("1", "2")
        assert violations[0]["lead_b_id"] in ("1", "2")

    def test_enrichment_included_in_profile(self):
        """Enrichment data is used in the profile key."""
        enrichment = {"company_size": "1000-5000", "company_industry": "Software",
                      "employee_count": 2500, "company_location": "SF"}
        leads = [
            {"lead": {"id": "1", "name": "Alice", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "a@acme.com"},
             "score": {"score": 85},
             "enrichment": enrichment},
            {"lead": {"id": "2", "name": "Bob", "company": "Acme", "role": "CTO",
                      "industry": "Tech", "email": "b@acme.com"},
             "score": {"score": 42},
             "enrichment": enrichment},
        ]
        violations = validate_batch(leads)
        assert len(violations) == 1


# ══════════════════════════════════════════════════════════════════════════
#  Integration-style tests: fairness with scoring agent output
# ══════════════════════════════════════════════════════════════════════════


class TestFairnessIntegration:
    """Integration tests: simulate scoring agent output and validate."""

    def test_heuristic_scorer_is_fair_by_design(self):
        """Heuristic scorer produces same scores for same profiles."""
        from backend.agents.scoring_agent import _heuristic_score

        # Two leads with same profile but different names
        lead_a = {"company": "Acme Corp", "role": "CTO", "email": "jane@acme.com",
                  "industry": "Technology", "buying_signals": ["requested demo"]}
        lead_b = {"company": "Acme Corp", "role": "CTO", "email": "john@acme.com",
                  "industry": "Technology", "buying_signals": ["requested demo"]}
        enrichment = {"company_size": "1000-5000", "company_industry": "Enterprise Software",
                      "employee_count": 2500, "company_location": "San Francisco, CA"}

        score_a = _heuristic_score(lead_a, enrichment)
        score_b = _heuristic_score(lead_b, enrichment)

        assert score_a["score"] == score_b["score"]
        assert score_a["confidence"] == score_b["confidence"]

        # Verify fairness via compare_scores
        result = compare_scores(
            lead_a={**lead_a, "id": "a", "name": "Jane"},
            score_a=score_a,
            lead_b={**lead_b, "id": "b", "name": "John"},
            score_b=score_b,
            enrichment_a=enrichment,
            enrichment_b=enrichment,
        )
        assert result["violation"] is False

    def test_heuristic_scorer_same_email_domain(self):
        """Same email domain does not cause unfairness."""
        from backend.agents.scoring_agent import _heuristic_score

        lead_a = {"company": "Acme Corp", "role": "CTO", "email": "jane@acme.com",
                  "industry": "Technology", "buying_signals": ["requested demo"]}
        lead_b = {"company": "Acme Corp", "role": "CTO", "email": "john@acme.com",
                  "industry": "Technology", "buying_signals": ["requested demo"]}

        score_a = _heuristic_score(lead_a, None)
        score_b = _heuristic_score(lead_b, None)

        assert score_a["score"] == score_b["score"]

    def test_fairness_holds_with_different_emails_same_domain(self):
        """Different emails on same domain → same score."""
        from backend.agents.scoring_agent import _heuristic_score

        lead_a = {"company": "Acme Corp", "role": "CTO", "email": "alice@acme.com",
                  "industry": "Technology", "buying_signals": ["requested demo"]}
        lead_b = {"company": "Acme Corp", "role": "CTO", "email": "bob@acme.com",
                  "industry": "Technology", "buying_signals": ["requested demo"]}

        score_a = _heuristic_score(lead_a, None)
        score_b = _heuristic_score(lead_b, None)

        assert score_a["score"] == score_b["score"]

    def test_different_company_gets_different_score(self):
        """Different companies CAN get different scores (that's fair)."""
        from backend.agents.scoring_agent import _heuristic_score

        lead_a = {"company": "Acme Corp", "role": "CTO", "email": "jane@acme.com",
                  "industry": "Technology", "company_size": "1000-5000",
                  "employee_count": 2500, "buying_signals": ["requested demo"]}
        lead_b = {"company": "Small Startup", "role": "CTO", "email": "bob@startup.com",
                  "industry": "Technology", "company_size": "1-50",
                  "employee_count": 5, "buying_signals": []}

        score_a = _heuristic_score(lead_a, None)
        score_b = _heuristic_score(lead_b, None)

        # Different profiles → fairness check should pass
        result = compare_scores(
            lead_a={**lead_a, "id": "a", "name": "Jane"},
            score_a=score_a,
            lead_b={**lead_b, "id": "b", "name": "Bob"},
            score_b=score_b,
        )
        assert result["violation"] is False  # Different profiles, no violation

    def test_name_only_difference_does_not_affect_score(self):
        """Two leads differing ONLY by name get identical scores.

        This is the core fairness requirement: same company, same role,
        same enrichment, same email domain, same buying signals, but
        different names → scores must be identical.
        """
        from backend.agents.scoring_agent import _heuristic_score

        base = {
            "company": "Acme Corp", "role": "CTO", "industry": "Technology",
            "email_domain": "acme.com", "buying_signals": ["requested demo"],
        }
        enrichment = {"company_size": "1000-5000", "company_industry": "Enterprise Software",
                      "employee_count": 2500, "company_location": "San Francisco, CA"}

        # Different names, different email addresses (same domain),
        # but everything else identical
        lead_a = {**base, "name": "Alice Smith", "email": "alice@acme.com"}
        lead_b = {**base, "name": "Bob Jones", "email": "bob@acme.com"}
        lead_c = {**base, "name": "Charlie Brown", "email": "charlie@acme.com"}

        score_a = _heuristic_score(lead_a, enrichment)
        score_b = _heuristic_score(lead_b, enrichment)
        score_c = _heuristic_score(lead_c, enrichment)

        # All scores must be identical
        assert score_a["score"] == score_b["score"] == score_c["score"]

        # Batch validation should find no violations
        entries = [
            {"lead": {**lead_a, "id": "a"}, "score": score_a, "enrichment": enrichment},
            {"lead": {**lead_b, "id": "b"}, "score": score_b, "enrichment": enrichment},
            {"lead": {**lead_c, "id": "c"}, "score": score_c, "enrichment": enrichment},
        ]
        violations = validate_batch(entries)
        assert violations == []