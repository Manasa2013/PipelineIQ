"""
Normalization utilities for PipelineIQ.

Handles consistent formatting of email addresses, company names,
and job roles across the pipeline.
"""

import re


def normalize_email(email: str) -> str:
    """
    Normalize an email address to lowercase and strip whitespace.

    Handles:
      - Leading/trailing whitespace
      - Mixed case → lowercase
      - Gmail + alias stripping (e.g. jane+test@gmail.com → jane@gmail.com)

    Args:
        email: Raw email address.

    Returns:
        Normalized, lowercased email address.
    """
    email = email.strip().lower()

    # Strip Gmail + aliases
    local, at, domain = email.partition("@")
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+")[0].replace(".", "")
        domain = "gmail.com"

    return f"{local}@{domain}"


def normalize_company_name(company: str) -> str:
    """
    Normalize a company name by stripping legal suffixes and extra whitespace.

    Removes common suffixes: Inc, Corp, LLC, Ltd, GmbH, Pty, Ltd, etc.

    Args:
        company: Raw company name.

    Returns:
        Cleaned, title-cased company name.
    """
    company = company.strip()

    # Remove common legal suffixes (case-insensitive)
    suffixes = [
        r"\binc\.?\b",
        r"\bcorp\.?\b",
        r"\bllc\.?\b",
        r"\bltd\.?\b",
        r"\bgmbh\b",
        r"\bpty\b",
        r"\blimited\b",
        r"\bco\.?\b",
        r"\bcompany\b",
        r"\bcorporation\b",
        r"\btechnologies\b",
        r"\btechnology\b",
        r"\bgroup\b",
        r"\bholdings\b",
        r"\bintl\b",
        r"\binternational\b",
    ]

    for suffix in suffixes:
        company = re.sub(suffix, "", company, flags=re.IGNORECASE)

    # Clean up any leftover punctuation or extra spaces
    company = re.sub(r"[.,;:]+", "", company)
    company = re.sub(r"\s+", " ", company).strip()

    # Title case for consistency
    return company.title() if company else company


def normalize_role(role: str) -> str:
    """
    Normalize a job title / role.

    Handles:
      - Leading/trailing whitespace
      - Common abbreviations (CEO, CTO, VP, Dir, Eng, etc.)
      - Title casing for non-abbreviated words

    Args:
        role: Raw job role string.

    Returns:
        Normalized role string.
    """
    role = role.strip()
    if not role:
        return role

    # Known acronyms that should remain uppercase
    acronyms = {"ceo", "cto", "cfo", "coo", "cmo", "cpo", "vp", "svp", "evp", "avp"}

    # Known expansions (abbreviation → full word, title-cased)
    expansions = {
        "dir": "Director",
        "dir.": "Director",
        "eng": "Engineer",
        "eng.": "Engineer",
        "dept": "Department",
        "mgmt": "Management",
        "head": "Head",
    }

    words = role.split()
    normalized_words = []

    for word in words:
        clean = word.strip(".,;:").lower()

        if clean in acronyms:
            # Keep the acronym uppercase
            normalized_words.append(clean.upper())
        elif clean in expansions:
            normalized_words.append(expansions[clean])
        else:
            # Title-case everything else
            normalized_words.append(word.title())

    return " ".join(normalized_words)