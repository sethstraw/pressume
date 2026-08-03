"""Document contract tests.

One conforming fixture, then one test per way a document can break the
contract. The conforming fixture passing is itself the most important test:
a contract nothing can satisfy is a bug, not a standard.
"""

from pressume.checks.document import DocumentRules, lint_document
from pressume.checks.report import Severity

CONFORMING = """\
# JANE DOE

City, Country | jane@example.com | 555-123-4567

## Summary

A plain summary paragraph.

## Core Skills

**Product:** strategy, roadmaps, and delivery

**Technology:** Python, SQL, and Typst

## Professional Experience

### Senior Role, Example Corp

**Senior Role** | January 2020 to March 2022 | City, Country

- Delivered the first thing.
- Delivered the second thing.

## Education

Doctor of Things, Example University, 2016
"""

RULES = DocumentRules(
    section_vocabulary=["Summary", "Core Skills", "Professional Experience", "Education"],
    required_sections=["Summary", "Core Skills", "Professional Experience"],
    labeled_sections=["Core Skills"],
    subheading_sections=["Professional Experience"],
)


def findings(markdown, rules=RULES):
    results = lint_document("doc", markdown, rules)
    return [r.detail for r in results if r.severity is Severity.FAIL]


def test_conforming_document_passes():
    assert findings(CONFORMING) == []


def test_missing_h1_fails():
    found = findings(CONFORMING.replace("# JANE DOE", "JANE DOE"))
    assert any("MD025" in f or "MD041" in f for f in found)


def test_unknown_section_fails():
    found = findings(CONFORMING.replace("## Education", "## Learnings"))
    assert any("S2" in f and "Learnings" in f for f in found)


def test_sections_out_of_vocabulary_order_fail():
    reordered = (
        CONFORMING.replace("## Summary", "## TEMP")
        .replace("## Core Skills", "## Summary")
        .replace("## TEMP", "## Core Skills")
    )
    assert any("out of order" in f for f in findings(reordered))


def test_missing_required_section_fails():
    removed = CONFORMING.replace("## Summary\n\nA plain summary paragraph.\n\n", "")
    assert any("required section missing" in f.lower() for f in findings(removed))


def test_unlabeled_line_in_labeled_section_fails():
    broken = CONFORMING.replace("**Product:** strategy", "Product: strategy")
    assert any("S5" in f for f in findings(broken))


def test_h3_outside_subheading_section_fails():
    broken = CONFORMING.replace(
        "## Education\n\nDoctor of Things",
        "## Education\n\n### A Degree\n\nDoctor of Things",
    )
    assert any("S3" in f for f in findings(broken))


def test_contact_paragraph_must_carry_email():
    broken = CONFORMING.replace("City, Country | jane@example.com | 555-123-4567", "City, Country")
    assert any("S1" in f for f in findings(broken))


def test_table_fails():
    broken = CONFORMING + "\n| a | b |\n"
    assert any("S4 table" in f for f in findings(broken))


def test_inline_link_is_allowed_when_visible_text_remains():
    broken = CONFORMING.replace("A plain summary paragraph.", "See [my site](https://x.example).")
    assert not any("inline link" in f for f in findings(broken))


def test_asterisk_bullet_fails():
    broken = CONFORMING.replace("- Delivered the first thing.", "* Delivered the first thing.")
    assert any("MD004" in f for f in findings(broken))


def test_hard_tab_fails():
    broken = CONFORMING.replace("- Delivered the first thing.", "-\tDelivered the first thing.")
    assert any("MD010" in f for f in findings(broken))


def test_double_blank_lines_fail():
    broken = CONFORMING.replace("## Summary", "\n## Summary")
    assert any("MD012" in f for f in findings(broken))


def test_heading_needs_surrounding_blanks():
    broken = CONFORMING.replace("## Summary\n\nA plain", "## Summary\nA plain")
    assert any("MD022" in f for f in findings(broken))


def test_missing_final_newline_fails():
    assert any("MD047" in f for f in findings(CONFORMING.rstrip("\n")))


def test_hard_break_two_spaces_is_allowed():
    allowed = CONFORMING.replace(
        "### Senior Role, Example Corp",
        "### Senior Role, Example Corp\n\nRole context line.  \nSecond line of the same block.",
    )
    assert not any("MD009" in f for f in findings(allowed))


def test_single_trailing_space_fails():
    broken = CONFORMING.replace("A plain summary paragraph.", "A plain summary paragraph. ")
    assert any("MD009" in f for f in findings(broken))


ROLE_LINE = "**Senior Role** | January 2020 to March 2022 | City, Country"


def test_bold_date_fails():
    broken = CONFORMING.replace(ROLE_LINE, "**January 2020 to March 2022** | City, Country")
    assert any("bold marks titles" in f for f in findings(broken))


def test_abbreviated_month_fails():
    broken = CONFORMING.replace(
        ROLE_LINE, "**Senior Role** | Jan 2020 to Mar. 2022 | City, Country"
    )
    assert any("abbreviated month" in f for f in findings(broken))


def test_hyphen_date_range_fails():
    broken = CONFORMING.replace(
        ROLE_LINE, "**Senior Role** | January 2020 - March 2022 | City, Country"
    )
    assert any("own pipe-delimited field" in f for f in findings(broken))


def test_bad_location_field_fails():
    broken = CONFORMING.replace(ROLE_LINE, "**Senior Role** | January 2020 to March 2022 | remote")
    assert any("City, Region" in f for f in findings(broken))


def test_location_with_remote_parenthetical_passes():
    allowed = CONFORMING.replace(
        ROLE_LINE, "**Senior Role** | January 2020 to March 2022 | City, Country (Remote)"
    )
    assert findings(allowed) == []


def test_international_location_passes():
    allowed = CONFORMING.replace(
        ROLE_LINE,
        "**Senior Role** | January 2020 to March 2022 | Montr\u00e9al, Qu\u00e9bec",
    )
    assert findings(allowed) == []


def test_short_date_style_is_satisfiable():
    document = CONFORMING.replace(
        ROLE_LINE, "**Senior Role** | Jan 2020 to Mar 2022 | City, Country"
    )
    results = lint_document("doc", document, RULES, date_style="short")
    assert [result.detail for result in results if result.severity is Severity.FAIL] == []


def test_long_dates_fail_when_short_style_is_selected():
    results = lint_document("doc", CONFORMING, RULES, date_style="short")
    assert any(
        "full month" in result.detail for result in results if result.severity is Severity.FAIL
    )


def test_prose_dates_inside_role_block_pass():
    allowed = CONFORMING.replace(
        "- Delivered the first thing.",
        "Held the role from August 2020 through January 2022 across two teams.\n\n"
        "- Delivered the first thing.",
    )
    assert findings(allowed) == []


def test_free_form_role_first_line_fails():
    broken = CONFORMING.replace(ROLE_LINE, "A role that started at some point.")
    assert any("first line of a role block" in f for f in findings(broken))


def test_condensed_entry_with_date_field_passes():
    allowed = CONFORMING.replace(
        ROLE_LINE, "Earlier Role, Example Hospital | July 2013 to June 2014"
    )
    assert findings(allowed) == []


CV_RULES = DocumentRules(
    section_vocabulary=[
        "Summary",
        "Core Skills",
        "Professional Experience",
        "Education",
        "Publications",
    ],
    required_sections=["Summary", "Professional Experience"],
    labeled_sections=["Core Skills"],
    subheading_sections=["Professional Experience"],
    max_heading_level=4,
    ordered_list_sections=["Publications"],
    contact_after_name=False,
)


def test_h4_allowed_inside_role_sections_when_profile_permits():
    document = CONFORMING.replace(
        "- Delivered the first thing.",
        "#### Flagship Project\n\n- Delivered the first thing.",
    )
    assert findings(document, CV_RULES) == []
    assert any("S3" in f for f in findings(document))  # still fails the resume rules


def test_ordered_lists_allowed_only_in_configured_sections():
    document = CONFORMING + (
        "\n## Publications\n\n1. First citation, 2020.\n2. Second citation, 2021.\n"
    )
    assert findings(document, CV_RULES) == []
    assert any("S4 ordered list" in f for f in findings(document, RULES))


def test_undated_entry_in_dated_section_fails():
    document = CONFORMING.replace(
        "Doctor of Things, Example University, 2016",
        "Doctor of Things, Example University",
    )
    assert any("S7" in f for f in findings(document))


def test_year_in_labeled_sub_bullet_satisfies_the_entry():
    document = CONFORMING + (
        "\n## Publications\n\n"
        "- Author A. A Title. *Venue*.\n"
        "  - **Publication date:** 5 January 2024\n"
    )
    assert not any("S7" in f for f in findings(document, CV_RULES))


def test_unknown_citation_label_fails():
    document = CONFORMING + (
        "\n## Publications\n\n"
        "- Author A. A Title. *Venue*. 2024.\n"
        "  - **Published on:** 5 January 2024\n"
    )
    assert any("S8" in f and "Published on" in f for f in findings(document, CV_RULES))


def test_contact_block_before_first_section_satisfies_cv_profile():
    document = CONFORMING.replace(
        "City, Country | jane@example.com | 555-123-4567",
        "City, Country\n\nEmail: jane@example.com",
    )
    assert not any("S1" in f for f in findings(document, CV_RULES))
    assert any("S1" in f for f in findings(document, RULES))
