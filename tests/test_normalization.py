"""
Unit tests for normalization utilities.

Run with:
    pytest tests/test_normalization.py -v
"""

import pytest

from backend.utils.normalization import (
    normalize_company_name,
    normalize_email,
    normalize_role,
)


# ── Email normalization ─────────────────────────────────────────────────


class TestNormalizeEmail:
    def test_lowercase(self):
        assert normalize_email("JANE@ACME.COM") == "jane@acme.com"

    def test_strips_whitespace(self):
        assert normalize_email("  jane@acme.com  ") == "jane@acme.com"

    def test_gmail_plus_strip(self):
        assert normalize_email("jane+test@gmail.com") == "jane@gmail.com"

    def test_gmail_dots_strip(self):
        assert normalize_email("j.a.n.e@gmail.com") == "jane@gmail.com"

    def test_googlemail_alias(self):
        assert normalize_email("jane+spam@googlemail.com") == "jane@gmail.com"

    def test_non_gmail_preserved(self):
        assert normalize_email("Jane.Doe@Outlook.com") == "jane.doe@outlook.com"

    def test_already_normalized(self):
        assert normalize_email("jane@acme.com") == "jane@acme.com"


# ── Company name normalization ──────────────────────────────────────────


class TestNormalizeCompanyName:
    def test_inc_suffix(self):
        assert normalize_company_name("Acme Inc") == "Acme"

    def test_corp_suffix(self):
        assert normalize_company_name("Globex Corp") == "Globex"

    def test_llc_suffix(self):
        assert normalize_company_name("Tech LLC") == "Tech"

    def test_ltd_suffix(self):
        assert normalize_company_name("Widgets Ltd") == "Widgets"

    def test_gmbh_suffix(self):
        assert normalize_company_name("Firma GmbH") == "Firma"

    def test_inc_with_dot(self):
        assert normalize_company_name("Acme Inc.") == "Acme"

    def test_technologies_suffix(self):
        assert normalize_company_name("Dataflow Technologies") == "Dataflow"

    def test_strips_whitespace(self):
        assert normalize_company_name("  Acme Corp  ") == "Acme"

    def test_title_case(self):
        assert normalize_company_name("acme corporation") == "Acme"

    def test_no_suffix(self):
        assert normalize_company_name("Acme") == "Acme"

    def test_multiple_suffixes(self):
        assert normalize_company_name("Acme Corp LLC") == "Acme"

    def test_company_word_suffix(self):
        assert normalize_company_name("Acme Company") == "Acme"


# ── Role normalization ──────────────────────────────────────────────────


class TestNormalizeRole:
    def test_ceo(self):
        assert normalize_role("ceo") == "CEO"

    def test_cto(self):
        assert normalize_role("cto") == "CTO"

    def test_vp_engineering(self):
        assert normalize_role("vp engineering") == "VP Engineering"

    def test_director_short(self):
        assert normalize_role("dir of sales") == "Director Of Sales"

    def test_head_of_product(self):
        assert normalize_role("head of product") == "Head Of Product"

    def test_engineer_short(self):
        assert normalize_role("senior eng") == "Senior Engineer"

    def test_strips_whitespace(self):
        assert normalize_role("  CTO  ") == "CTO"

    def test_already_normalized(self):
        assert normalize_role("Chief Technology Officer") == "Chief Technology Officer"

    def test_empty_string(self):
        assert normalize_role("") == ""

    def test_svp(self):
        assert normalize_role("svp sales") == "SVP Sales"

    def test_cfo(self):
        assert normalize_role("cfo") == "CFO"