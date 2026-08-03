"""Unit tests for source lint and text hygiene checks."""

from pressume.checks.pdfchecks import check_text_hygiene
from pressume.checks.report import Severity
from pressume.checks.source import check_source
from pressume.config import Checks


def failures(results):
    return [r for r in results if r.severity is Severity.FAIL]


def test_clean_source_passes():
    assert not failures(check_source("doc", "# Jane Doe\n\nPlain text.\n", Checks()))


def test_backticks_fail_with_line_numbers():
    results = check_source("doc", "fine\na `code` span\n", Checks())
    failed = failures(results)
    assert len(failed) == 1
    assert "2" in failed[0].detail


def test_em_dash_fails_and_is_named():
    failed = failures(check_source("doc", "text \u2014 more\n", Checks()))
    assert failed
    assert all("em dash" in result.detail for result in failed)


def test_hygiene_allows_configured_bullet():
    checks = Checks(allowed_characters=["\u2022"])
    assert not failures(check_text_hygiene("doc", "pdf", "\u2022 item one", checks))


def test_hygiene_rejects_unexpected_non_ascii():
    failed = failures(check_text_hygiene("doc", "pdf", "caf\u00e9", Checks()))
    assert len(failed) == 1
    assert "U+00E9" in failed[0].detail


def test_exact_string_near_miss_fails():
    checks = Checks(required_strings=["Data Specialist - US Pharma"])
    text = "Data Specialist, US Pharma"  # topic present, exact string mangled
    failed = failures(check_text_hygiene("doc", "pdf", text, checks))
    assert len(failed) == 1


def test_required_string_is_required_even_when_topic_is_absent():
    checks = Checks(required_strings=["Data Specialist - US Pharma"])
    assert failures(check_text_hygiene("doc", "pdf", "Unrelated resume", checks))


def test_protected_string_is_conditional_on_its_first_word():
    checks = Checks(protected_strings=["Data Specialist - US Pharma"])
    assert not failures(check_text_hygiene("doc", "pdf", "Unrelated resume", checks))
    assert failures(check_text_hygiene("doc", "pdf", "Data role", checks))


def test_forbidden_string_fails():
    checks = Checks(forbidden_strings=["CONFIDENTIAL"])
    failed = failures(check_text_hygiene("doc", "pdf", "CONFIDENTIAL draft", checks))
    assert len(failed) == 1


def test_unicode_and_smart_punctuation_can_be_allowed_independently():
    checks = Checks(ascii_only=False, forbid_smart_punctuation=False)
    assert not failures(check_source("doc", "# JOS\u00c9 O\u2019CONNOR\n", checks))
