"""End-to-end render test: Markdown fixture through Pandoc and Typst to PDF.

Uses Typst's bundled default fonts so no font installation is required in CI.
"""

from pathlib import Path

from pressume.checks.pdfchecks import count_pages, extract_pdf_text
from pressume.config import Config, Style
from pressume.convert import render_pdf, render_txt
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
