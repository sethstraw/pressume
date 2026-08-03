"""Regression tests from the pre-publication review.

Each test here pins a behavior the review found unguarded: contract state
leaks, date-family drift, policy presets, metadata scrubbing, and error
classification at the configuration boundary.
"""

import zipfile

import pytest

from pressume.checks.ats import check_ats, derive_checks
from pressume.checks.document import DocumentRules, lint_document
from pressume.checks.report import Severity
from pressume.config import Checks, Config, ConfigError, Document
from pressume.convert import render_docx
from pressume.metadata import derive_metadata


def failures(results):
    return [result.detail for result in results if result.severity is Severity.FAIL]


ROLE_THEN_NEW_SECTION = """\
# JANE DOE

Toronto, Ontario | jane@example.com

## Summary

A summary paragraph.

## Professional Experience

### Example Corp

**Senior Role** | January 2020 to Present | Toronto, Ontario

- Delivered the first thing.

## Research Experience

An introductory paragraph, not a role block, and valid where it stands.

### Example Lab

**Researcher** | January 2016 to December 2019 | Toronto, Ontario

- Investigated the second thing.
"""


def test_role_first_line_state_does_not_leak_into_the_next_section():
    results = lint_document("doc", ROLE_THEN_NEW_SECTION, DocumentRules())
    assert failures(results) == []


def test_role_block_opening_with_a_bullet_fails_the_first_line_rule():
    document = ROLE_THEN_NEW_SECTION.replace(
        "**Senior Role** | January 2020 to Present | Toronto, Ontario\n\n- Delivered",
        "- Delivered",
    )
    found = failures(lint_document("doc", document, DocumentRules()))
    assert any("not a bullet" in item for item in found)


def test_sept_abbreviation_is_visible_to_the_mixed_date_check():
    text = "SUMMARY\nJanuary 2020 to Present\nSept. 2020\n"
    results = check_ats("doc", text, Checks(date_style="long"))
    dates = next(result for result in results if result.check == "ats: consistent dates")
    assert dates.severity is Severity.FAIL
    assert "Sept. 2020" in dates.detail


def test_orcid_identifier_is_not_derived_as_a_phone():
    markdown = (
        "# JANE DOE\n\n"
        "Toronto | jane@example.com | 416-555-0199\n"
        "ORCID: orcid.org/0000-0002-1825-0097\n\n"
        "## Summary\n\nText.\n"
    )
    derived = derive_checks(markdown, Checks())
    assert derived.contact_phones == ["416-555-0199"]


def test_ats_phone_check_fails_on_mismatch_and_absence():
    checks = Checks(contact_phones=["416-555-0199"])
    mismatch = next(
        result
        for result in check_ats("doc", "call 905-555-0000 today", checks)
        if result.check == "ats: phone extracted"
    )
    assert mismatch.severity is Severity.FAIL
    absent = next(
        result
        for result in check_ats("doc", "no digits here", checks)
        if result.check == "ats: phone extracted"
    )
    assert absent.severity is Severity.FAIL


def test_ats_name_off_the_first_line_warns():
    checks = Checks(contact_name="Jane Doe")
    results = check_ats("doc", "Confidential\nJane Doe\nmore text", checks)
    name = next(result for result in results if result.check == "ats: name leads document")
    assert name.severity is Severity.WARN


@pytest.mark.parametrize(
    ("policy", "expectation"),
    [
        ("academic", lambda rules: rules.max_heading_level == 4),
        ("academic", lambda rules: "Publications" in rules.ordered_list_sections),
        ("international", lambda rules: rules.contact_after_name is False),
        ("minimal", lambda rules: "S6" in rules.disabled_rules),
    ],
)
def test_policies_apply_their_documented_shape(policy, expectation):
    rules = DocumentRules()
    rules.apply_policy(policy)
    assert expectation(rules)


def test_unknown_policy_error_names_the_choices():
    with pytest.raises(ValueError, match="standard"):
        DocumentRules().apply_policy("strict")


def test_docx_scrub_removes_word_revision_identifiers(tmp_path):
    markdown = (
        "# JANE DOE\n\n"
        "Toronto | jane@example.com\n\n"
        "## Summary\n\nA paragraph that produces revision-bearing runs.\n"
    )
    destination = tmp_path / "Resume.docx"
    metadata = derive_metadata(markdown, Document(file="Resume.md"), "en", "US")
    render_docx(markdown, destination, Config(config_dir=tmp_path), metadata)
    with zipfile.ZipFile(destination) as package:
        for member in package.namelist():
            if member.startswith("word/") and member.endswith(".xml"):
                assert b"w:rsid" not in package.read(member), member
        assert "docProps/custom.xml" not in package.namelist()


def test_layout_inspection_reports_density_edge_and_stranded_heading(tmp_path):
    from reportlab.pdfgen import canvas

    from pressume.diagnostics import inspect_pdf_layout

    pdf = tmp_path / "dense.pdf"
    page = canvas.Canvas(str(pdf), pagesize=(612, 792))
    page.setFont("Helvetica", 9)
    y = 780.0
    while y > 20:  # fill past the trim thresholds on purpose
        page.drawString(36, y, "A dense line of resume text for the fill measurement.")
        y -= 10.5
    page.drawString(36, 6, "EXPERIENCE")  # stranded heading at the bottom edge
    page.save()

    results = inspect_pdf_layout("doc", pdf, "# NAME\n\n## Experience\n\nText.\n")
    details = " | ".join(result.detail for result in results)
    assert all(result.severity is Severity.WARN for result in results)
    assert "dense vertical fill" in details
    assert "bottom edge" in details
    assert "stranded" in details


def test_extractor_agreement_uses_pdfminer_when_poppler_is_absent(tmp_path, monkeypatch):
    from reportlab.pdfgen import canvas

    from pressume.checks.pdfchecks import _check_extractor_agreement, extract_pdf_text

    pdf = tmp_path / "plain.pdf"
    page = canvas.Canvas(str(pdf), pagesize=(612, 792))
    page.setFont("Helvetica", 12)
    page.drawString(72, 720, "JANE DOE resume line one")
    page.drawString(72, 700, "and resume line two")
    page.save()

    monkeypatch.setattr("pressume.checks.pdfchecks.shutil.which", lambda _name: None)
    result = _check_extractor_agreement("doc", pdf, extract_pdf_text(pdf))
    assert result.severity is Severity.PASS, result.detail
    assert "pdfminer.six" in result.detail


def test_missing_configured_reference_docx_is_a_config_error(tmp_path):
    config = Config(config_dir=tmp_path)
    config.reference_docx = tmp_path / "missing-reference.docx"
    metadata = derive_metadata("# JANE DOE\n", Document(file="Resume.md"), "en", "US")
    with pytest.raises(ConfigError, match="refdoc"):
        render_docx("# JANE DOE\n\nText.\n", tmp_path / "out.docx", config, metadata)
