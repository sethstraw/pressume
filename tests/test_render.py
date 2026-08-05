"""End-to-end render test: Markdown fixture through Pandoc and Typst to PDF.

Uses Typst's bundled default fonts so no font installation is required in CI.
"""

from pathlib import Path

import pytest

from pressume.checks.pdfchecks import count_pages, extract_pdf_text
from pressume.checks.report import Severity
from pressume.config import (
    KNOWN_FORMATS,
    PDF_STANDARDS,
    Checks,
    Config,
    Document,
    Style,
)
from pressume.convert import render_pdf, render_txt
from pressume.documents import SourceDocument
from pressume.errors import RenderError
from pressume.formats import render_artifact, verify_artifact
from pressume.template import keep_labels_with_lists, strip_thematic_breaks

FIXTURE = """\
# JANE DOE

City, Country | jane@example.com | 555-123-4567

---

## SUMMARY

A short professional summary with plain ASCII punctuation.

## EXPERIENCE

### Senior Role, Example Corp

January 2020 - March 2022

**Flagship project**

- Delivered the first thing.
- Delivered the second thing.
"""


def make_config(tmp_path: Path) -> Config:
    # Default style throughout: the default typeface ships with the package,
    # so the default configuration must render without any font setup.
    config = Config(config_dir=tmp_path)
    config.style = Style()
    return config


def test_bundled_fonts_ship_with_the_package():
    from pressume.convert import bundled_font_dirs

    root, *families = bundled_font_dirs()
    # Assert the shape rather than an exact file count so a font refresh does
    # not break the suite: every family ships glyphs and its OFL license.
    assert families, "expected at least one bundled font family directory"
    assert any(root.glob("*.ttf")) or all(any(f.glob("*.ttf")) for f in families)
    for family in families:
        assert any(family.glob("*.ttf")), family
        assert any(family.glob("OFL-LICENSE*")), family
    assert any(root.glob("OFL-LICENSE*"))


def test_renders_single_page_pdf(tmp_path):
    pdf = tmp_path / "out.pdf"
    render_pdf(FIXTURE, pdf, make_config(tmp_path))
    assert pdf.exists()
    assert count_pages(pdf) == 1


def test_pdf_text_extracts_in_reading_order(tmp_path):
    pdf = tmp_path / "out.pdf"
    render_pdf(FIXTURE, pdf, make_config(tmp_path))
    text = extract_pdf_text(pdf)
    assert "JANE DOE" in text
    assert "jane@example.com" in text
    assert text.index("SUMMARY") < text.index("EXPERIENCE")


def test_pdf_is_tagged_for_accessible_reading_order(tmp_path):
    from pypdf import PdfReader

    pdf = tmp_path / "out.pdf"
    render_pdf(FIXTURE, pdf, make_config(tmp_path))
    root = PdfReader(pdf).root_object
    assert "/StructTreeRoot" in root
    assert bool(root["/MarkInfo"]["/Marked"])


def test_txt_render_is_plain(tmp_path):
    txt = tmp_path / "out.txt"
    render_txt(FIXTURE, txt)
    content = txt.read_text(encoding="utf-8")
    assert "JANE DOE" in content
    assert "#" not in content


def test_thematic_breaks_removed():
    assert "---" not in strip_thematic_breaks(FIXTURE)


def test_bold_labels_become_sticky_blocks():
    body = "*Flagship project*\n\n- Delivered the first thing.\n"
    assert "#role-label[*Flagship project*]" in keep_labels_with_lists(body)


@pytest.mark.parametrize("standard", PDF_STANDARDS)
def test_every_offered_pdf_standard_compiles(tmp_path, standard):
    """A PDF standard configuration accepts is one Typst can actually emit."""
    config = make_config(tmp_path)
    config.style.pdf_standard = standard
    pdf = tmp_path / f"{standard}.pdf"
    render_pdf(FIXTURE, pdf, config)
    assert count_pages(pdf) == 1


def test_configured_font_directories_are_searched_before_the_bundled_ones(tmp_path, monkeypatch):
    """`[paths].fonts` reaches Typst, ahead of the fonts that ship here.

    Ordering is the whole behavior: a user font with a bundled family's name
    wins, which is how a licensed corporate typeface replaces the default.
    """
    import typst

    from pressume.convert import bundled_font_dirs

    brand = tmp_path / "brand-fonts"
    brand.mkdir()
    seen: dict[str, object] = {}
    monkeypatch.setattr(typst, "compile", lambda *args, **kwargs: seen.update(kwargs))

    config = make_config(tmp_path)
    config.font_dirs = [Path("brand-fonts")]
    render_pdf(FIXTURE, tmp_path / "out.pdf", config)

    paths = seen["font_paths"]
    assert paths[0] == str(brand.resolve())
    assert paths[1:] == [str(directory) for directory in bundled_font_dirs()]


@pytest.mark.parametrize("name", KNOWN_FORMATS)
def test_every_configured_format_renders_and_verifies(tmp_path, name):
    """Configuration and implementation offer the same set of formats.

    ``KNOWN_FORMATS`` is what configuration accepts. This renders and reopens
    each of those names, so a format that gains a configuration entry without
    an implementation fails here instead of in someone's render.
    """
    source_path = tmp_path / "Resume.md"
    source_path.write_text(FIXTURE, encoding="utf-8")
    config = make_config(tmp_path)
    source = SourceDocument(Document(file="Resume.md"), source_path, FIXTURE)
    artifact = tmp_path / f"Resume.{name}"

    render_artifact(name, source, artifact, config)
    assert artifact.stat().st_size > 0

    results = verify_artifact(name, source, artifact, Checks(date_style="off"), config)
    assert results, f"{name} produced no check results"
    assert {result.document for result in results} == {"Resume"}
    assert not [result for result in results if result.severity is Severity.FAIL]


def test_an_unknown_format_name_is_refused_rather_than_guessed(tmp_path):
    source_path = tmp_path / "Resume.md"
    source_path.write_text(FIXTURE, encoding="utf-8")
    source = SourceDocument(Document(file="Resume.md"), source_path, FIXTURE)
    config = make_config(tmp_path)
    with pytest.raises(RenderError, match="No renderer for format 'rtf'"):
        render_artifact("rtf", source, tmp_path / "out.rtf", config)
    with pytest.raises(RenderError, match="No verifier for format 'rtf'"):
        verify_artifact("rtf", source, source_path, Checks(), config)
