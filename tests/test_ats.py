"""Unit tests for the ATS parse-back checks."""

from pressume.checks.ats import check_ats
from pressume.checks.report import Severity
from pressume.config import Checks

TEXT = """JANE DOE
City, Country | jane@example.com | 555-123-4567
SUMMARY
A summary paragraph.
EXPERIENCE
Role one
January 2020 - March 2022
EDUCATION
Degree, April 2016
"""

CHECKS = Checks(
    contact_name="Jane Doe",
    contact_email="jane@example.com",
    section_order=["Summary", "Experience", "Education"],
    date_style="long",
)


def by_check(results, check_name):
    return next(r for r in results if r.check == check_name)


def test_clean_document_passes_everything():
    results = check_ats("doc", TEXT, CHECKS)
    assert all(r.severity is Severity.PASS for r in results), [(r.check, r.detail) for r in results]


def test_missing_name_fails():
    results = check_ats("doc", TEXT.replace("JANE DOE", "resume"), CHECKS)
    assert by_check(results, "ats: name leads document").severity is Severity.FAIL


def test_sections_out_of_order_fail():
    reordered = TEXT.replace("SUMMARY", "ZZZ").replace("EDUCATION", "SUMMARY")
    results = check_ats("doc", reordered, CHECKS)
    assert by_check(results, "ats: section headings").severity is Severity.FAIL


def test_mixed_date_styles_fail():
    mixed = TEXT + "\nMar. 2023\n"
    results = check_ats("doc", mixed, CHECKS)
    result = by_check(results, "ats: consistent dates")
    assert result.severity is Severity.FAIL
    assert "Mar. 2023" in result.detail


def test_email_only_in_body_warns():
    moved = TEXT.replace(" | jane@example.com", "") + "\ncontact: jane@example.com\n"
    results = check_ats("doc", moved, CHECKS)
    assert by_check(results, "ats: email near top").severity is Severity.WARN


MARKDOWN = """\
# JANE DOE

City, Country | jane@example.com | 555-123-4567

## Summary

Text.

## Experience

### Role

**Role** | January 2020 to Present | City, Country

- Did things.
"""


def test_derive_checks_reads_the_document():
    from pressume.checks.ats import derive_checks
    from pressume.config import Checks

    derived = derive_checks(MARKDOWN, Checks())
    assert derived.contact_name == "JANE DOE"
    assert derived.contact_email == "jane@example.com"
    assert derived.contact_phones == ["555-123-4567"]
    assert derived.section_order == ["Summary", "Experience"]


def test_derive_checks_never_overrides_configuration():
    from pressume.checks.ats import derive_checks
    from pressume.config import Checks

    configured = Checks(
        contact_name="Configured Name",
        contact_email="configured@example.com",
        contact_phones=["111-222-3333"],
        section_order=["Summary"],
    )
    derived = derive_checks(MARKDOWN, configured)
    assert derived.contact_name == "Configured Name"
    assert derived.contact_email == "configured@example.com"
    assert derived.contact_phones == ["111-222-3333"]
    assert derived.section_order == ["Summary"]


def test_derived_checks_pass_against_own_extraction():
    from pressume.checks.ats import derive_checks
    from pressume.config import Checks

    derived = derive_checks(MARKDOWN, Checks())
    extracted = (
        "JANE DOE\nCity, Country | jane@example.com | 555-123-4567\n"
        "SUMMARY\nText.\nEXPERIENCE\nRole | January 2020 to Present | City, Country\nDid things.\n"
    )
    results = check_ats("doc", extracted, derived)
    assert all(r.severity is Severity.PASS for r in results), [(r.check, r.detail) for r in results]
