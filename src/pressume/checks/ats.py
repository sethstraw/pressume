"""ATS parse-back checks.

An applicant tracking system's first stage is linear text extraction; every
later stage (field parsing, keyword matching, LLM ranking) consumes that
output. These checks replay stage one against the delivered PDF and assert
that what a parser reconstructs matches what the resume intends:

- the candidate's name leads the document;
- contact details survive extraction and sit near the top;
- section headings appear, in the intended order, on their own lines;
- dates use one consistent style.
"""

from __future__ import annotations

import re
from dataclasses import replace
from itertools import pairwise

from pressume.checks.report import CheckResult, Severity, grader
from pressume.checks.textrules import LONG_MONTH_NAMES, SHORT_MONTH_NAMES
from pressume.config import Checks

# "May" never signals a mixed style because it is identical in both, so the
# shared short list deliberately omits it.
LONG_DATE = re.compile(rf"\b(?:{LONG_MONTH_NAMES})\s+\d{{4}}\b")
SHORT_DATE = re.compile(rf"\b(?:{SHORT_MONTH_NAMES})\.?\s+\d{{4}}\b")
NUMERIC_DATE = re.compile(r"\b\d{1,2}/\d{4}\b")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Generic enough for international numbers; the check that matters compares
# against the configured numbers literally, this only detects "some phone".
PHONE = re.compile(r"\+?\d[\d ().-]{6,}\d")
# An ORCID iD is four groups of four digits; it matches the loose phone
# pattern but is an identifier, not a way to call someone.
ORCID_ID = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")

TOP_OF_DOCUMENT_LINES = 8

H1_LINE = re.compile(r"^# (?P<text>\S.*)$", re.MULTILINE)
H2_LINE = re.compile(r"^## (?P<text>\S.*)$", re.MULTILINE)


def derive_checks(markdown: str, configured: Checks) -> Checks:
    """Fill unset contact and section checks from the document itself.

    The document already states its name (the H1), its contact details (the
    front matter), and its section order (the H2s); configuration exists to
    override or add to that, never as a precondition. Deriving the expected
    values from the source and verifying they survive into the delivered PDF
    is the point of the parse-back check.
    """
    front_matter = markdown.split("\n## ", 1)[0]
    derived = replace(
        configured,
        allowed_characters=list(configured.allowed_characters),
        required_strings=list(configured.required_strings),
        protected_strings=list(configured.protected_strings),
        forbidden_strings=list(configured.forbidden_strings),
        section_order=list(configured.section_order),
        contact_phones=list(configured.contact_phones),
    )
    if not derived.contact_name and (match := H1_LINE.search(markdown)):
        derived.contact_name = match.group("text").strip()
    if not derived.contact_email and (match := EMAIL.search(front_matter)):
        derived.contact_email = match.group(0)
    if not derived.contact_phones:
        derived.contact_phones = [
            phone.strip()
            for phone in PHONE.findall(front_matter)
            if not ORCID_ID.fullmatch(phone.strip())
        ]
    if not derived.section_order:
        derived.section_order = [
            match.group("text").strip() for match in H2_LINE.finditer(markdown)
        ]
    return derived


def check_ats(name: str, text: str, checks: Checks) -> list[CheckResult]:
    """Verify the structure recovered from one rendered document."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    top = "\n".join(lines[:TOP_OF_DOCUMENT_LINES])
    candidates = (
        _check_name(name, lines, top, checks),
        _check_email(name, text, top, checks),
        _check_phones(name, text, checks),
        _check_section_order(name, text, checks),
        _check_date_consistency(name, text, checks),
    )
    return [result for result in candidates if result is not None]


def _check_name(name: str, lines: list[str], top: str, checks: Checks) -> CheckResult | None:
    if not checks.contact_name:
        return None
    verdict = grader(name, "ats: name leads document")
    wanted = checks.contact_name.casefold()
    if lines and wanted in lines[0].casefold():
        return verdict(Severity.PASS)
    if wanted in top.casefold():
        return verdict(Severity.WARN, "name found near the top but not on the first extracted line")
    return verdict(
        Severity.FAIL,
        f"{checks.contact_name!r} not found in the first {TOP_OF_DOCUMENT_LINES} extracted lines",
    )


def _check_email(name: str, text: str, top: str, checks: Checks) -> CheckResult | None:
    if not checks.contact_email:
        return None
    verdict = grader(name, "ats: email near top")
    if checks.contact_email in EMAIL.findall(top):
        return verdict(Severity.PASS)
    if checks.contact_email in text:
        return verdict(Severity.WARN, "email present but not in the top contact block")
    return verdict(
        Severity.FAIL, f"configured email {checks.contact_email!r} not found in extracted text"
    )


def _check_phones(name: str, text: str, checks: Checks) -> CheckResult | None:
    if not checks.contact_phones:
        return None
    verdict = grader(name, "ats: phone extracted")
    if found := [phone for phone in checks.contact_phones if phone in text]:
        return verdict(Severity.PASS, ", ".join(found))
    if PHONE.search(text):
        return verdict(
            Severity.FAIL, "a phone number was extracted but it is none of the configured numbers"
        )
    return verdict(Severity.FAIL, "no phone number found")


def _check_section_order(name: str, text: str, checks: Checks) -> CheckResult | None:
    if not checks.section_order:
        return None
    verdict = grader(name, "ats: section headings")
    positions: list[int] = []
    missing: list[str] = []
    for section in checks.section_order:
        pattern = re.compile(rf"^\s*{re.escape(section)}\s*$", re.IGNORECASE | re.MULTILINE)
        if match := pattern.search(text):
            positions.append(match.start())
        else:
            missing.append(section)
    if missing:
        return verdict(Severity.FAIL, f"not found as standalone lines: {', '.join(missing)}")
    if any(earlier >= later for earlier, later in pairwise(positions)):
        return verdict(Severity.FAIL, "sections extracted out of the configured order")
    return verdict(Severity.PASS, f"{len(positions)} sections in order")


def _check_date_consistency(name: str, text: str, checks: Checks) -> CheckResult | None:
    if checks.date_style == "off":
        return None
    verdict = grader(name, "ats: consistent dates")
    long_dates = LONG_DATE.findall(text)
    short_dates = SHORT_DATE.findall(text)
    numeric_dates = NUMERIC_DATE.findall(text)
    wanted, other = (
        (long_dates, short_dates) if checks.date_style == "long" else (short_dates, long_dates)
    )
    if unexpected := other + numeric_dates:
        return verdict(Severity.FAIL, f"mixed date styles; unexpected: {', '.join(unexpected[:4])}")
    if not wanted:
        return verdict(Severity.WARN, "no dates detected at all")
    return verdict(Severity.PASS, f"{len(wanted)} {checks.date_style}-style dates")
