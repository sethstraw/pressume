"""The document contract: what a resume Markdown file is allowed to be.

Conformity is the point. Rendering accepts exactly one shape of document, so
every resume that passes lint renders the same way, no matter who wrote it.
A loose input contract is how a pipeline ends up with six documents in five
formats and a render that works for only one of them.

Two families of rules run here. The M rules are the standard markdownlint
checks that matter for this document class, kept under their markdownlint
names so the failure is searchable. The S rules are structural: they define
the resume itself, not the Markdown dialect.

The contract:

- One H1, first line of the file: the candidate's name.
- Immediately after it, an optional contact paragraph without emphasis. Email
  and phone are optional, so a public copy can leave them out.
- Every section is an H2 drawn from the configured vocabulary, in the
  vocabulary's order.
- H3 headings exist only inside sections that declare them (roles inside
  Professional Experience).
- Sections configured as labeled (Core Skills) carry lines of the form
  **Label:** content, nothing else.
- Role metadata is standardized. Dates use long months joined by "to"
  (July 2020 to May 2022, or to Present), sit in their own pipe-delimited
  field, and are never bold; bold marks titles. A location field reads
  City, Region, with an optional parenthetical such as (Remote). The first
  line of every role block is either a bold title or a pipe line carrying
  the date field.
- No tables, HTML, images, code, blockquotes, or footnotes in the standard
  policy. Visible Markdown links are allowed because the rendered label still
  carries the text an extractor consumes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pressume.checks.report import CheckResult, Severity
from pressume.checks.textrules import LONG_MONTH_NAMES, SHORT_MONTH_NAMES

H1 = re.compile(r"^# (?P<text>\S.*)$")
H2 = re.compile(r"^## (?P<text>\S.*)$")
HEADING = re.compile(r"^(?P<hashes>#{1,6})(?P<gap>\s*)(?P<text>.*)$")
BULLET = re.compile(r"^(?P<indent>\s*)(?P<marker>[-*+])(?P<gap>\s+)")
LABELED_LINE = re.compile(r"^\*\*[^*:]+:\*\* \S.*$")
ORDERED_ITEM = re.compile(r"^\s*\d+[.)] ")
HTML_TAG = re.compile(r"<[A-Za-z/!][^>]*>")
SETEXT_UNDERLINE = re.compile(r"^\s*(=+|-+)\s*$")
THEMATIC_BREAK = re.compile(r"^-{3,}\s*$")

LONG_DATE_RANGE = re.compile(
    rf"(?:{LONG_MONTH_NAMES}) \d{{4}}(?: to (?:(?:{LONG_MONTH_NAMES}) \d{{4}}|Present))?"
    r"(?: \([^)]{1,80}\))?"
)
SHORT_MONTH = re.compile(rf"\b(?:{SHORT_MONTH_NAMES})\.? \d{{4}}")
SHORT_DATE_RANGE = re.compile(
    rf"(?:{SHORT_MONTH_NAMES})\.? \d{{4}}"
    rf"(?: to (?:(?:{SHORT_MONTH_NAMES})\.? \d{{4}}|Present))?"
    r"(?: \([^)]{1,80}\))?"
)
LONG_MONTH_DATE = re.compile(rf"\b(?:{LONG_MONTH_NAMES}) \d{{4}}")
BOLD_SPAN = re.compile(r"\*\*[^*]+\*\*")
# City, Region is the standard; the region is optional so that city-states
# (Singapore), country-only entries, and a bare Remote remain valid.
LOCATION = re.compile(r"^[^\W\d_][\w .'-]*(?:, [^\W\d_][\w .'-]+)*(?: \([\w /-]+\))?$")


@dataclass
class DocumentRules:
    """The configurable half of the contract. Defaults are the strict resume case.

    A named profile in configuration starts from these defaults and overrides
    only what it declares.
    """

    # Every standard resume and CV section, in canonical order. A document
    # never needs them all; the vocabulary is what it may draw from, and its
    # order is the order sections must appear in. Someone who calls a section
    # something nonstandard adds their name here rather than fighting the lint.
    section_vocabulary: list[str] = field(
        default_factory=lambda: [
            "Summary",
            "Objective",
            "Core Skills",
            "Skills",
            "Technical Skills",
            "Security Clearance",
            "Professional Experience",
            "Work Experience",
            "Experience",
            "Clinical Experience",
            "Research Experience",
            "Teaching Experience",
            "Leadership Experience",
            "Military Service",
            "Projects",
            "Portfolio",
            "Education",
            "Relevant Coursework",
            "Licensure",
            "Licenses and Certifications",
            "Certifications",
            "Bar Admissions",
            "Training",
            "Academic Appointments",
            "Fellowships",
            "Grants and Funding",
            "Patents",
            "Publications",
            "Presentations",
            "Posters",
            "Exhibitions",
            "Writing",
            "Professional Organizations",
            "Professional Memberships",
            "Affiliations",
            "Service",
            "Volunteer Experience",
            "Languages",
            "Honors and Awards",
            "Awards",
            "Interests",
            "References",
        ]
    )
    # Only Summary is required by default, because the experience section
    # legitimately goes by several names; a real configuration tightens this.
    required_sections: list[str] = field(default_factory=lambda: ["Summary"])
    labeled_sections: list[str] = field(
        default_factory=lambda: ["Core Skills", "Skills", "Technical Skills"]
    )
    subheading_sections: list[str] = field(
        default_factory=lambda: [
            "Professional Experience",
            "Work Experience",
            "Experience",
            "Clinical Experience",
            "Research Experience",
            "Teaching Experience",
            "Leadership Experience",
            "Military Service",
        ]
    )
    # Headings deeper than H2 live only inside subheading sections; this caps
    # how deep they go. Resumes stop at H3 roles; a CV may take H4 projects.
    max_heading_level: int = 3
    # Sections where ordered lists are allowed. Empty for resumes; a CV numbers
    # its citations.
    ordered_list_sections: list[str] = field(default_factory=list)
    # True reads the paragraph directly after the name as the contact line and
    # keeps emphasis out of it. False accepts a contact block of any shape
    # before the first section, which is how a full CV lays out its front matter.
    contact_after_name: bool = True
    # Sections whose entries are records: every entry must carry a year, on its
    # own line or in a labeled sub-bullet. An undated credential, publication,
    # or award is an incomplete record.
    dated_sections: list[str] = field(
        default_factory=lambda: [
            "Education",
            "Licensure",
            "Licenses and Certifications",
            "Certifications",
            "Bar Admissions",
            "Training",
            "Academic Appointments",
            "Fellowships",
            "Grants and Funding",
            "Patents",
            "Publications",
            "Presentations",
            "Posters",
            "Exhibitions",
            "Writing",
            "Professional Organizations",
            "Professional Memberships",
            "Honors and Awards",
            "Awards",
        ]
    )
    # The only labels a structured citation sub-bullet may carry. One fixed
    # spelling per field is what makes the fields machine-readable later.
    citation_field_labels: list[str] = field(
        default_factory=lambda: [
            "Publication date",
            "Publication/Publisher",
            "Publisher",
            "Venue",
            "URL",
            "DOI",
            "PMID",
            "Authorship/status",
            "Description",
        ]
    )
    warning_rules: list[str] = field(default_factory=list)
    disabled_rules: list[str] = field(default_factory=list)
    # The preset applied last; rendering sets a letter's body apart by it.
    policy: str = "standard"

    @staticmethod
    def policy_names() -> tuple[str, ...]:
        """Return the supported contract presets."""
        return ("standard", "academic", "international", "minimal", "letter")

    def apply_policy(self, policy: str) -> None:
        """Apply a named policy before explicit configuration overrides."""
        if policy not in self.policy_names():
            raise ValueError(
                f"unknown policy {policy!r}; choose from {', '.join(self.policy_names())}"
            )
        self.policy = policy
        if policy == "standard":
            return
        if policy == "letter":
            # An empty vocabulary makes any section heading an S2 failure, so a
            # letter is its name line, its contact paragraph, and prose.
            self.section_vocabulary = []
            self.required_sections = []
            self.labeled_sections = []
            self.subheading_sections = []
            self.dated_sections = []
            return
        if policy == "academic":
            self.contact_after_name = False
            self.max_heading_level = 4
            self.ordered_list_sections = [
                "Publications",
                "Presentations",
                "Patents",
                "Grants and Funding",
            ]
            self.warning_rules = ["S5", "S6"]
            return
        if policy == "international":
            self.contact_after_name = False
            self.warning_rules = ["S5", "S6"]
            return
        self.contact_after_name = False
        self.disabled_rules = ["S2", "S3", "S4", "S5", "S6", "S7", "S8"]


def lint_document(
    name: str,
    markdown: str,
    rules: DocumentRules,
    date_style: str = "long",
) -> list[CheckResult]:
    """Run the full contract against one Markdown source. Every finding is a FAIL."""
    findings: list[str] = []
    lines = markdown.splitlines()

    _markdown_rules(lines, markdown, findings)
    _structure_rules(lines, rules, date_style, findings)
    _item_rules(lines, rules, findings)

    disabled = {rule.casefold() for rule in rules.disabled_rules}
    warnings = {rule.casefold() for rule in rules.warning_rules}
    reported: list[CheckResult] = []
    for finding in findings:
        match = re.search(r"\b(?:MD\d+|S\d+)\b", finding)
        rule = match.group(0).casefold() if match else ""
        if rule in disabled:
            continue
        severity = Severity.WARN if rule in warnings else Severity.FAIL
        reported.append(CheckResult(name, "document contract", severity, finding))
    if reported:
        return reported
    return [CheckResult(name, "document contract", Severity.PASS)]


def _markdown_rules(lines: list[str], markdown: str, findings: list[str]) -> None:
    """The markdownlint subset this document class must satisfy."""
    blank_run = 0
    for number, line in enumerate(lines, start=1):
        if "\t" in line:
            findings.append(f"line {number}: MD010 hard tab")
        trailing = len(line) - len(line.rstrip(" "))
        if trailing not in (0, 2):
            findings.append(
                f"line {number}: MD009 trailing whitespace "
                "(exactly two spaces marks a hard break; anything else is noise)"
            )

        if line.strip() == "":
            blank_run += 1
            if blank_run == 2:
                findings.append(f"line {number}: MD012 multiple consecutive blank lines")
            continue
        blank_run = 0

        heading = HEADING.match(line)
        if heading and heading.group("text"):
            if heading.group("gap") == "":
                findings.append(f"line {number}: MD018 no space after hash in heading")
            else:
                before_blank = number == 1 or lines[number - 2].strip() == ""
                after_blank = number == len(lines) or lines[number].strip() == ""
                if not (before_blank and after_blank):
                    findings.append(f"line {number}: MD022 heading not surrounded by blank lines")

        if (
            SETEXT_UNDERLINE.match(line)
            and not THEMATIC_BREAK.match(line)
            and number > 1
            and lines[number - 2].strip() != ""
            and not lines[number - 2].lstrip().startswith(("-", "#"))
        ):
            findings.append(f"line {number}: MD003 setext heading; this contract is ATX-only")

        bullet = BULLET.match(line)
        if bullet:
            if bullet.group("marker") != "-":
                findings.append(
                    f"line {number}: MD004 list marker must be a hyphen, "
                    f"found {bullet.group('marker')!r}"
                )
            if bullet.group("gap") != " ":
                findings.append(f"line {number}: MD030 one space after the list marker")

    if markdown and not markdown.endswith("\n"):
        findings.append("end of file: MD047 file must end with a single newline")
    if markdown.endswith("\n\n"):
        findings.append("end of file: MD047 file ends with blank lines")


def _structure_rules(
    lines: list[str], rules: DocumentRules, date_style: str, findings: list[str]
) -> None:
    """The resume shape itself."""
    vocabulary = {entry.lower(): index for index, entry in enumerate(rules.section_vocabulary)}
    labeled = {entry.lower() for entry in rules.labeled_sections}
    subheadings = {entry.lower() for entry in rules.subheading_sections}
    ordered_allowed = {entry.lower() for entry in rules.ordered_list_sections}

    h1_lines = [n for n, line in enumerate(lines, start=1) if H1.match(line)]
    first_content = next((n for n, line in enumerate(lines, start=1) if line.strip()), None)
    if len(h1_lines) != 1:
        findings.append(f"MD025 exactly one H1 required, found {len(h1_lines)}")
    if first_content is not None and (not h1_lines or h1_lines[0] != first_content):
        findings.append("MD041 the first line of the file must be the H1 name line")

    if h1_lines and rules.contact_after_name:
        contact_line = next(
            (line for line in lines[h1_lines[0] :] if line.strip()),
            "",
        )
        if not contact_line.startswith("#") and (
            "**" in contact_line or "*" in contact_line.replace("**", "")
        ):
            findings.append("S1 the contact paragraph carries no emphasis markup")

    seen_sections: list[tuple[str, int]] = []
    current_section = ""
    expect_role_first_line = False
    for number, line in enumerate(lines, start=1):
        h2 = H2.match(line)
        if h2:
            title = h2.group("text").strip()
            current_section = title.lower()
            # A new section always ends any role block, even one that closed
            # with bullets; otherwise the first-line rule leaks across sections.
            expect_role_first_line = False
            if current_section not in vocabulary:
                findings.append(
                    f"line {number}: S2 section {title!r} is not in the configured "
                    "vocabulary; add it to [document].section_vocabulary or rename it"
                )
            else:
                seen_sections.append((title, vocabulary[current_section]))
            continue
        heading = HEADING.match(line)
        if heading and heading.group("text") and len(heading.group("hashes")) >= 3:
            level = len(heading.group("hashes"))
            if level > rules.max_heading_level:
                findings.append(f"line {number}: S3 heading deeper than H{rules.max_heading_level}")
            elif not current_section:
                findings.append(f"line {number}: S3 H{level} heading before any section")
            elif current_section not in subheadings:
                findings.append(
                    f"line {number}: S3 H{level} headings are only allowed inside "
                    f"{sorted(rules.subheading_sections)}"
                )
            expect_role_first_line = level == 3 and current_section in subheadings
            continue

        if ORDERED_ITEM.match(line) and current_section not in ordered_allowed:
            findings.append(f"line {number}: S4 ordered list; use hyphen bullets")

        # A blank line matches no branch below, so it never closes a role block:
        # the gap between a role heading and its first line is normal.
        stripped = line.strip()
        if stripped.startswith("-") or ORDERED_ITEM.match(line):
            if expect_role_first_line and current_section in subheadings:
                findings.append(
                    f"line {number}: S6 the first line of a role block is a bold title "
                    "or a pipe-delimited metadata line, not a bullet"
                )
                expect_role_first_line = False
        elif stripped and current_section in labeled and not THEMATIC_BREAK.match(line):
            if not LABELED_LINE.match(line.rstrip()):
                findings.append(
                    f"line {number}: S5 lines in a labeled section must read '**Label:** content'"
                )
        elif stripped and current_section in subheadings and not THEMATIC_BREAK.match(line):
            _role_line_rules(number, line, expect_role_first_line, date_style, findings)
            expect_role_first_line = False

        _forbidden_constructs(number, line, findings)

    order_positions = [position for _, position in seen_sections]
    if order_positions != sorted(order_positions):
        findings.append("S2 sections are out of order; the configured vocabulary defines the order")
    seen_titles = {title.lower() for title, _ in seen_sections}
    for required in rules.required_sections:
        if required.lower() not in seen_titles:
            findings.append(f"S2 required section missing: {required!r}")


def _role_line_rules(
    number: int,
    line: str,
    is_role_first_line: bool,
    date_style: str,
    findings: list[str],
) -> None:
    """The date, title, and location standard for lines inside role sections.

    The field-structure rules apply only to pipe-delimited metadata lines.
    Prose inside a role block may mention dates freely; the abbreviation and
    bold rules still bind everywhere, because a shortened or bolded date is
    wrong wherever it appears.
    """
    text = line.rstrip()

    if date_style == "long" and SHORT_MONTH.search(text):
        findings.append(f"line {number}: S6 abbreviated month; dates are written out in full")
    elif date_style == "short" and LONG_MONTH_DATE.search(text):
        findings.append(f"line {number}: S6 full month; dates use three-letter month abbreviations")

    date_range = {
        "long": LONG_DATE_RANGE,
        "short": SHORT_DATE_RANGE,
        "off": None,
    }[date_style]

    for span in BOLD_SPAN.findall(text):
        if date_range is not None and date_range.search(span):
            findings.append(
                f"line {number}: S6 date range inside bold; bold marks titles, not dates"
            )

    if "|" in text:
        fields = [field.strip() for field in text.split("|")]
        date_fields = (
            [field for field in fields if date_range.fullmatch(field)]
            if date_range is not None
            else []
        )
        if date_range is not None and date_range.search(text) and not date_fields:
            findings.append(
                f"line {number}: S6 the date range must be its own pipe-delimited field, "
                f"written in the configured {date_style} style with 'to' as the separator"
            )
        elif date_fields:
            date_index = fields.index(date_fields[0])
            trailing = fields[date_index + 1 :]
            if trailing and not _valid_location(trailing[-1]):
                findings.append(
                    f"line {number}: S6 the field after the date is the location and "
                    f"must read 'City, Region', found {trailing[-1]!r}"
                )

    if is_role_first_line and not text.startswith("**") and "|" not in text:
        findings.append(
            f"line {number}: S6 the first line of a role block is a bold title "
            "or a pipe-delimited metadata line"
        )


def _valid_location(value: str) -> bool:
    """Accept Unicode place names while retaining the documented title case."""
    if not LOCATION.fullmatch(value):
        return False
    base = value.split(" (", 1)[0]
    return all(part and part[0].isupper() for part in base.split(", "))


YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
CITATION_LABEL = re.compile(r"^-\s+\*\*([^*]+?):\*\*")


def _item_rules(lines: list[str], rules: DocumentRules, findings: list[str]) -> None:
    """Entry standards inside dated sections.

    An entry is a top-level bullet with its indented sub-bullets, or a
    paragraph. Each entry must carry a year somewhere in its block (S7), and
    any labeled sub-bullet inside these sections must use a configured
    citation field label, one fixed spelling per field (S8). A line ending
    with a colon introduces what follows and is not itself an entry.
    """
    dated = {entry.lower() for entry in rules.dated_sections}
    labels = {label.lower() for label in rules.citation_field_labels}

    current_section = ""
    item_start: int | None = None
    item_text: list[str] = []

    def close_item() -> None:
        nonlocal item_start, item_text
        if item_start is not None:
            block = " ".join(item_text)
            if not block.rstrip().endswith(":") and not YEAR.search(block):
                findings.append(
                    f"line {item_start}: S7 every entry in a dated section carries a year"
                )
        item_start, item_text = None, []

    for number, line in enumerate(lines, start=1):
        h2 = H2.match(line)
        if h2:
            close_item()
            current_section = h2.group("text").strip().lower()
            continue
        if current_section not in dated:
            continue
        stripped = line.strip()
        if not stripped or line.startswith("#") or THEMATIC_BREAK.match(line):
            close_item()
            continue

        indented = len(line) > len(line.lstrip())
        label_match = CITATION_LABEL.match(stripped)
        if indented and label_match:
            label = label_match.group(1).strip()
            if label.lower() not in labels:
                findings.append(
                    f"line {number}: S8 unknown citation field label {label!r}; "
                    f"configured labels: {rules.citation_field_labels}"
                )

        if not indented and item_start is None:
            item_start = number
            item_text = [stripped]
        elif not indented and stripped.startswith("- "):
            close_item()
            item_start = number
            item_text = [stripped]
        else:
            item_text.append(stripped)
    close_item()


def _forbidden_constructs(number: int, line: str, findings: list[str]) -> None:
    stripped = line.lstrip()
    if stripped.startswith("|"):
        findings.append(f"line {number}: S4 table row; tables break ATS extraction")
    if stripped.startswith(">"):
        findings.append(f"line {number}: S4 blockquote")
    if stripped.startswith(("```", "~~~")):
        findings.append(f"line {number}: S4 code fence")
    if "![" in line:
        findings.append(f"line {number}: S4 image")
    if HTML_TAG.search(line):
        findings.append(f"line {number}: S4 raw HTML")
    if "[^" in line:
        findings.append(f"line {number}: S4 footnote")
