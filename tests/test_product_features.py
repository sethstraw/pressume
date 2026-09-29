"""Design, delivery, and project-management product behavior."""

import json

import pytest
from pypdf import PdfReader, PdfWriter

from pressume.checks.document import DocumentRules, lint_document
from pressume.checks.docxchecks import check_docx, extract_docx_text
from pressume.checks.pdfchecks import (
    check_page_target,
    check_pdf_delivery,
    check_visual_relationships,
)
from pressume.cli import main
from pressume.config import Checks, Config, Document, Style, load_config
from pressume.convert import render_docx, render_pdf
from pressume.diagnostics import inspect_pdf_layout, inspect_source
from pressume.errors import RenderError
from pressume.links import linkify_markdown
from pressume.metadata import derive_metadata
from pressume.pipeline import SourceDocument, _commit_outputs
from pressume.template import apply_semantic_blocks

RESUME = """\
# JANE DOE

Toronto, Ontario | jane@example.com | 416-555-0199 | linkedin.com/in/janedoe

Authorized to work in Canada | Remote-first

## Summary

A concise professional summary.

## Core Skills

**Data:** Python, SQL, and data modeling

## Professional Experience

### Example Health

**Senior Data Architect** | January 2020 to Present | Toronto, Ontario (Remote)

- Delivered a production data platform.

## Education

Bachelor of Science, Example University, 2019

## Publications

Doe J. A useful article. Example Journal. 2024. doi:10.1000/example.
"""


def test_linkification_preserves_visible_text_and_adds_destinations():
    linked = linkify_markdown(RESUME)
    assert "[jane@example.com](mailto:jane@example.com)" in linked
    assert "[416-555-0199](tel:4165550199)" in linked
    assert "[linkedin.com/in/janedoe](https://linkedin.com/in/janedoe)" in linked
    assert "[doi:10.1000/example](https://doi.org/10.1000/example)" in linked


def test_linkification_does_not_treat_an_orcid_as_a_phone_number():
    linked = linkify_markdown(
        "# JANE DOE\n\n"
        "Toronto | jane@example.com | orcid.org/0000-0002-1825-0097\n\n"
        "## Summary\n\nText.\n"
    )
    assert "tel:000" not in linked
    assert "https://orcid.org/0000-0002-1825-0097" in linked


def test_semantic_blocks_distinguish_resume_components():
    body = """\
= JANE DOE
<jane-doe>
Toronto | jane@example.com

Remote-first

== CORE SKILLS
<core-skills>
#strong[Data:] Python

== PROFESSIONAL EXPERIENCE
<professional-experience>
=== Example Health
<example-health>
#strong[Architect] | January 2020 to Present | Toronto, Ontario

== PUBLICATIONS
<publications>
Doe J. Example. 2024.
"""
    styled = apply_semantic_blocks(body)
    assert "#contact[" in styled
    assert "#logistics[" in styled
    assert "#skill-line[" in styled
    assert "#role-meta[" in styled
    assert "#citation[" in styled


# Two trailing spaces are a Markdown hard line break. They are the whole point
# of this fixture, so they are spelled out rather than left invisible.
BREAK = "  "
MULTILINE_ROLE_RESUME = "\n".join(
    [
        "# JANE DOE",
        "",
        "Toronto, Ontario | jane@example.com",
        "",
        "## Summary",
        "",
        "A concise professional summary.",
        "",
        "## Professional Experience",
        "",
        "### Example Health",
        "",
        f"**Staff Architect**{BREAK}",
        f"(title of record: Staff Architect - Platform){BREAK}",
        "January 2020 to Present | Toronto, Ontario",
        "",
        "- Delivered the platform work that mattered.",
        "",
    ]
)


def test_role_metadata_written_across_lines_stays_one_component():
    """A hard line break must not escape the closing bracket of its component.

    Pandoc writes a Markdown hard break as a trailing backslash. Wrapping only
    the first line of such a paragraph leaves that backslash immediately before
    the component's closing bracket, where it escapes the bracket and the
    document no longer parses.
    """
    body = """\
= JANE DOE
<jane-doe>
Toronto | jane@example.com

== PROFESSIONAL EXPERIENCE
<professional-experience>
=== Example Health
<example-health>
#strong[Staff Architect] \\
(title of record: Staff Architect - Platform) \\
January 2020 to Present | Toronto, Ontario

- Delivered the platform work that mattered.
"""
    styled = apply_semantic_blocks(body)

    assert styled.count("#role-meta[") == 1
    assert "January 2020 to Present | Toronto, Ontario]" in styled
    assert "\\]" not in styled


@pytest.mark.parametrize("theme", ["modern", "technical", "traditional"])
def test_a_multiline_role_header_renders_under_every_theme(tmp_path, theme):
    """Every shipped theme has to render the same conforming document."""
    source = tmp_path / "Resume.md"
    source.write_text(MULTILINE_ROLE_RESUME, encoding="utf-8")
    config = Config(config_dir=tmp_path, style=Style(theme=theme))
    metadata = derive_metadata(MULTILINE_ROLE_RESUME, Document(file="Resume.md"), "en", "CA")
    pdf = tmp_path / f"resume-{theme}.pdf"

    render_pdf(MULTILINE_ROLE_RESUME, pdf, config, metadata)

    assert pdf.exists()
    assert pdf.stat().st_size > 0


def test_pdf_has_metadata_language_links_and_independent_delivery_checks(tmp_path):
    config = Config(config_dir=tmp_path)
    document = Document(file="Resume.md", title="Jane Doe - Data Resume", keywords=["data"])
    metadata = derive_metadata(RESUME, document, "en", "CA")
    pdf = tmp_path / "resume.pdf"
    render_pdf(RESUME, pdf, config, metadata)
    reader = PdfReader(pdf)
    assert reader.metadata.title == "Jane Doe - Data Resume"
    assert reader.metadata.author == "JANE DOE"
    assert str(reader.root_object["/Lang"]).startswith("en")
    results = check_pdf_delivery("resume", pdf, metadata, RESUME)
    assert not [result for result in results if result.severity.value == "fail"]


def test_docx_is_reopened_and_verified(tmp_path):
    config = Config(config_dir=tmp_path)
    document = Document(file="Resume.md", title="Jane Doe - Resume")
    metadata = derive_metadata(RESUME, document, "en", "CA")
    docx = tmp_path / "resume.docx"
    render_docx(RESUME, docx, config, metadata)
    checks = Checks(date_style="off")
    results = check_docx("resume", docx, checks, metadata, RESUME)
    assert not [result for result in results if result.severity.value == "fail"]
    assert extract_docx_text(docx).splitlines()[0] == "JANE DOE"


def failing_checks(results, name):
    return [
        result for result in results if result.check == name and result.severity.value == "fail"
    ]


def test_a_corrupt_docx_fails_the_package_check_instead_of_raising(tmp_path):
    not_a_docx = tmp_path / "resume.docx"
    not_a_docx.write_bytes(b"PK\x03\x04 truncated")
    metadata = derive_metadata(RESUME, Document(file="Resume.md"), "en", "CA")
    results = check_docx("resume", not_a_docx, Checks(), metadata, RESUME)
    assert failing_checks(results, "docx: package")


def test_docx_checks_catch_tables_metadata_residue_and_dropped_links(tmp_path):
    """The three DOCX failures a recipient would actually notice.

    A table breaks linear extraction, leftover authoring metadata travels with
    the file, and a hyperlink present in the source but absent from the package
    relationships is a link that no longer works.
    """
    import zipfile

    config = Config(config_dir=tmp_path)
    metadata = derive_metadata(RESUME, Document(file="Resume.md", title="Jane"), "en", "CA")
    original = tmp_path / "resume.docx"
    render_docx(RESUME, original, config, metadata)

    damaged = tmp_path / "damaged.docx"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(damaged, "w") as destination:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                data = data.replace(b"<w:body>", b"<w:body><w:tbl></w:tbl>", 1)
            elif item.filename == "docProps/core.xml":
                data = data.replace(b"<dc:title>", b"<dc:title>Someone Else ", 1)
            elif item.filename == "word/_rels/document.xml.rels":
                data = b'<?xml version="1.0"?><Relationships xmlns="http://schemas.'
                data += b'openxmlformats.org/package/2006/relationships"/>'
            destination.writestr(item, data)

    results = check_docx("resume", damaged, Checks(date_style="off"), metadata, RESUME)
    assert failing_checks(results, "docx: linear structure")
    assert failing_checks(results, "docx: metadata")
    assert failing_checks(results, "docx: hyperlinks")


def test_docx_metadata_check_rejects_leftover_custom_properties(tmp_path):
    import zipfile

    config = Config(config_dir=tmp_path)
    metadata = derive_metadata(RESUME, Document(file="Resume.md"), "en", "CA")
    original = tmp_path / "resume.docx"
    render_docx(RESUME, original, config, metadata)

    with_custom = tmp_path / "custom.docx"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(with_custom, "w") as destination:
        for item in source.infolist():
            destination.writestr(item, source.read(item.filename))
        destination.writestr("docProps/custom.xml", b"<Properties/>")

    results = check_docx("resume", with_custom, Checks(date_style="off"), metadata, RESUME)
    failures = failing_checks(results, "docx: metadata")
    assert failures and "custom authoring metadata" in failures[0].detail


def test_pdf_delivery_checks_catch_wrong_metadata_lost_tags_and_dropped_links(tmp_path):
    """The PDF failures that survive into the recipient's hands.

    Rewriting the PDF with pypdf drops the document catalogue's language and
    structure tree and the link annotations, and the expected metadata is
    supplied from a different document, so all three checks have to fail.
    """
    config = Config(config_dir=tmp_path)
    metadata = derive_metadata(RESUME, Document(file="Resume.md"), "en", "CA")
    original = tmp_path / "resume.pdf"
    render_pdf(RESUME, original, config, metadata)

    stripped = tmp_path / "stripped.pdf"
    writer = PdfWriter()
    for page in PdfReader(original).pages:
        writer.add_page(page)
    for page in writer.pages:
        if "/Annots" in page:
            del page["/Annots"]
    with stripped.open("wb") as stream:
        writer.write(stream)

    results = check_pdf_delivery("resume", stripped, metadata, RESUME)
    assert failing_checks(results, "pdf: metadata")
    assert failing_checks(results, "pdf: accessibility structure")
    assert failing_checks(results, "pdf: hyperlinks")


def test_modern_theme_preserves_visual_hierarchy_and_geometry(tmp_path):
    """Guard the key visual relationships without a brittle pixel snapshot."""
    pdf = tmp_path / "resume.pdf"
    render_pdf(RESUME, pdf, Config(config_dir=tmp_path))
    page = PdfReader(pdf).pages[0]
    fragments: dict[str, tuple[float, float, float]] = {}

    def visit(text, cm, _tm, _font, size):
        label = text.strip()
        if label in {"JANE DOE", "SUMMARY", "A concise professional summary."}:
            fragments[label] = (float(cm[4]), float(cm[5]), float(size))

    page.extract_text(visitor_text=visit)
    name = fragments["JANE DOE"]
    section = fragments["SUMMARY"]
    body = fragments["A concise professional summary."]
    assert float(page.mediabox.width) == pytest.approx(612, abs=1)
    assert float(page.mediabox.height) == pytest.approx(792, abs=1)
    assert name[2] > section[2] > body[2]
    assert name[1] > section[1] > body[1]
    assert name[0] == pytest.approx(39.6, abs=2)


def test_traditional_theme_preserves_compatibility_layout_and_publication_blocks(tmp_path):
    """Guard the established serif layout used by exact-page portfolios."""
    config = Config(config_dir=tmp_path, style=Style(theme="traditional"))
    pdf = tmp_path / "traditional.pdf"
    render_pdf(RESUME, pdf, config)

    reader = PdfReader(pdf)
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert "Doe J. A useful article." in text
    assert "JANE DOE" in text


def test_visual_relationship_check_rejects_heading_collisions(tmp_path):
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "collision.pdf"
    page = canvas.Canvas(str(pdf), pagesize=(612, 792))
    # ReportLab coordinates grow upward: place the contact line so its top
    # edge crowds the name's bottom edge with under a point of clearance.
    page.setFont("Helvetica", 18)
    page.drawString(36, 700, "JANE DOE")
    page.setFont("Helvetica", 10)
    page.drawString(36, 692, "Toronto | jane@example.com")
    page.save()

    result = check_visual_relationships("resume", pdf, RESUME)
    assert result.severity.value == "fail"
    assert "JANE DOE" in result.detail


@pytest.mark.parametrize(("clearance", "severity"), [(1.5, "fail"), (2.5, "warn"), (3.7, "pass")])
def test_visual_relationship_check_grades_text_crowding_a_section_rule(
    tmp_path, clearance, severity
):
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "above.pdf"
    page = canvas.Canvas(str(pdf), pagesize=(612, 792))
    page.setFont("Helvetica", 10)
    # pdfminer boxes 10 pt Helvetica from 2.07 pt below the baseline to 7.93
    # above it, so baselines 10 pt plus the clearance apart leave that clearance.
    page.drawString(36, 600 + 10 + clearance, "Authorized to work in Canada | Remote-first")
    page.drawString(36, 600, "SUMMARY")
    page.drawString(36, 580, "A concise professional summary.")
    page.save()

    result = check_visual_relationships("resume", pdf, RESUME)
    assert result.severity.value == severity, result.detail


def _draw_pages(pdf, line_counts):
    from reportlab.pdfgen import canvas

    page = canvas.Canvas(str(pdf), pagesize=(612, 792))
    page.setFont("Helvetica", 10)
    for count in line_counts:
        for line in range(count):
            page.drawString(36, 740 - 16 * line, "Delivered a production data platform on time")
        page.showPage()
    page.save()


def test_an_exact_page_target_flags_a_final_page_short_by_height(tmp_path):
    """Half a page of full lines carries enough words to pass the word ratio."""
    pdf = tmp_path / "short-final.pdf"
    _draw_pages(pdf, [42, 21])

    findings = inspect_pdf_layout("resume", pdf, RESUME, pages=2)
    sparse = [result for result in findings if "final page is lightly filled" in result.detail]
    assert [result.severity.value for result in sparse] == ["warn"]
    assert "50%" in sparse[0].detail

    untargeted = inspect_pdf_layout("resume", pdf, RESUME)
    assert [result.severity.value for result in untargeted] == ["pass"]


def test_inspect_applies_the_configured_page_target(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Resume.md").write_text(RESUME, encoding="utf-8")
    (tmp_path / "pressume.toml").write_text(
        '[[documents]]\nfile = "Resume.md"\npages = 2\n', encoding="utf-8"
    )
    (tmp_path / "renders").mkdir()
    _draw_pages(tmp_path / "renders" / "Resume.pdf", [42, 21])

    assert main(["inspect", "--json"]) == 0
    details = [item["detail"] for item in json.loads(capsys.readouterr().out)["results"]]
    assert any(detail.startswith("final page is lightly filled") for detail in details)


def test_readability_inspection_is_advisory_and_detects_sparse_endings(tmp_path):
    assert inspect_source("resume", RESUME)[0].severity.value == "pass"

    dense = (
        "# JANE DOE\n\n"
        + ("Long front matter " * 30)
        + "\n\n## Summary\n\n"
        + ("paragraph " * 150)
        + "\n\n"
        + ("- Built " + "detail " * 80 + "\n") * 6
    )
    source_findings = inspect_source("dense", dense)
    assert any("front matter" in result.detail for result in source_findings)
    assert any("paragraph" in result.detail for result in source_findings)
    assert any("repeated bullet openers" in result.detail for result in source_findings)

    pdf = tmp_path / "resume.pdf"
    render_pdf(RESUME, pdf, Config(config_dir=tmp_path))
    assert inspect_pdf_layout("resume", pdf, RESUME)[0].severity.value == "pass"

    reader = PdfReader(pdf)
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    writer.add_blank_page(width=612, height=792)
    sparse = tmp_path / "sparse.pdf"
    with sparse.open("wb") as stream:
        writer.write(stream)
    sparse_findings = inspect_pdf_layout("resume", sparse, RESUME)
    assert any("final page is lightly filled" in result.detail for result in sparse_findings)


def test_page_ranges_accept_inside_and_reject_outside(tmp_path):
    config = Config(config_dir=tmp_path)
    pdf = tmp_path / "resume.pdf"
    render_pdf(RESUME, pdf, config)
    assert check_page_target("resume", pdf, None, 1, 2)[0].severity.value == "pass"
    assert check_page_target("resume", pdf, None, 2, 3)[0].severity.value == "fail"


def test_config_supports_themes_metadata_ranges_names_and_policy(tmp_path):
    path = tmp_path / "pressume.toml"
    path.write_text(
        """\
[style]
theme = "technical"
density = "spacious"
language = "fr"
region = "CA"

[[documents]]
file = "Resume.md"
min_pages = 1
max_pages = 2
output_name = "Jane_Doe_Resume"
title = "Jane Doe - Resume"
keywords = ["health", "data"]

[document]
policy = "international"
warning_rules = ["S6"]
""",
        encoding="utf-8",
    )
    config = load_config(path)
    document = config.documents[0]
    assert config.style.theme == "technical"
    assert config.style.language == "fr"
    assert document.output_name == "Jane_Doe_Resume"
    assert document.max_pages == 2
    assert document.keywords == ["health", "data"]
    assert "S6" in config.document_rules.warning_rules


def test_policy_can_demote_structural_conventions_to_warnings():
    rules = DocumentRules()
    rules.apply_policy("international")
    broken = RESUME.replace(
        "**Senior Data Architect** | January 2020 to Present | Toronto, Ontario (Remote)",
        "Senior Data Architect, 2020-present, Toronto",
    )
    results = lint_document("resume", broken, rules)
    assert any(result.severity.value == "warn" and "S6" in result.detail for result in results)


def test_cli_lists_custom_output_tracks_manifest_and_cleans_stale(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Resume.md").write_text(RESUME, encoding="utf-8")
    config = tmp_path / "pressume.toml"
    config.write_text(
        """\
[output]
formats = ["pdf"]

[[documents]]
file = "Resume.md"
output_name = "Jane_Doe_Resume"
""",
        encoding="utf-8",
    )
    assert main(["list", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["documents"][0]["output_name"] == "Jane_Doe_Resume"
    assert main(["render", "--json"]) == 0
    capsys.readouterr()
    output = tmp_path / "renders"
    assert (output / "Jane_Doe_Resume.pdf").exists()
    assert (output / ".pressume-manifest.json").exists()

    config.write_text(
        config.read_text(encoding="utf-8").replace("Jane_Doe_Resume", "Jane_Doe_CV"),
        encoding="utf-8",
    )
    assert main(["clean", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["warnings"] == 1
    assert main(["clean", "--apply", "--json"]) == 0
    capsys.readouterr()
    assert not (output / "Jane_Doe_Resume.pdf").exists()


def test_commit_failure_restores_every_prior_artifact(tmp_path, monkeypatch):
    output = tmp_path / "renders"
    scratch = tmp_path / "scratch"
    output.mkdir()
    scratch.mkdir()
    old_pdf = output / "Resume.pdf"
    old_txt = output / "Resume.txt"
    old_pdf.write_bytes(b"old pdf")
    old_txt.write_bytes(b"old txt")
    new_pdf = scratch / "Resume.pdf"
    new_txt = scratch / "Resume.txt"
    new_pdf.write_bytes(b"new pdf")
    new_txt.write_bytes(b"new txt")
    source_path = tmp_path / "Resume.md"
    source_path.write_text(RESUME, encoding="utf-8")
    source = SourceDocument(Document(file="Resume.md"), source_path, RESUME)

    monkeypatch.setattr(
        "pressume.pipeline.write_manifest",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(RenderError, match="disk full"):
        _commit_outputs(
            [(new_pdf, old_pdf), (new_txt, old_txt)],
            scratch,
            output,
            [source],
            Config(config_dir=tmp_path),
            None,
        )
    assert old_pdf.read_bytes() == b"old pdf"
    assert old_txt.read_bytes() == b"old txt"


def test_partial_install_failure_restores_the_already_replaced_artifact(tmp_path, monkeypatch):
    """A mid-sequence os.replace failure must unwind the artifacts installed
    before it, which is the hardest path in the transactional commit."""
    import os as real_os

    output = tmp_path / "renders"
    scratch = tmp_path / "scratch"
    output.mkdir()
    scratch.mkdir()
    old_pdf = output / "Resume.pdf"
    old_txt = output / "Resume.txt"
    old_pdf.write_bytes(b"old pdf")
    old_txt.write_bytes(b"old txt")
    new_pdf = scratch / "Resume.pdf"
    new_txt = scratch / "Resume.txt"
    new_pdf.write_bytes(b"new pdf")
    new_txt.write_bytes(b"new txt")
    source_path = tmp_path / "Resume.md"
    source_path.write_text(RESUME, encoding="utf-8")
    source = SourceDocument(Document(file="Resume.md"), source_path, RESUME)

    calls = {"count": 0}
    original_replace = real_os.replace

    def failing_replace(src, dst, **kwargs):
        calls["count"] += 1
        # Call 1 backs up the old PDF, call 2 installs the new PDF; failing on
        # call 3 leaves the first artifact installed and the second untouched.
        if calls["count"] == 3:
            raise OSError("disk full")
        return original_replace(src, dst, **kwargs)

    monkeypatch.setattr("pressume.pipeline.os.replace", failing_replace)
    with pytest.raises(RenderError, match="disk full"):
        _commit_outputs(
            [(new_pdf, old_pdf), (new_txt, old_txt)],
            scratch,
            output,
            [source],
            Config(config_dir=tmp_path),
            None,
        )
    assert old_pdf.read_bytes() == b"old pdf"
    assert old_txt.read_bytes() == b"old txt"
