"""Apply semantic resume styling and clean metadata to Pandoc DOCX output."""

from __future__ import annotations

import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import docx
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from pressume.config import PAPER_SIZES, Style
from pressume.metadata import DocumentMetadata
from pressume.template import (
    CITATION_WORDS,
    RECORD_SECTIONS,
    SKILL_SECTIONS,
    ResolvedStyle,
    resolve_style,
)

# A DOCX travels to machines that do not carry the bundled typefaces, so the
# Word deliverable substitutes widely installed system families per theme
# unless the user pinned an explicit font. This mapping and the line-spacing
# table are the single source for every DOCX pass, including refdoc.
DOCX_THEME_FONTS = {"modern": "Arial", "technical": "Arial", "traditional": "Georgia"}
DOCX_LINE_SPACING = {"compact": 1.04, "balanced": 1.10, "spacious": 1.16}

# Paragraph styles that carry body text in Pandoc's DOCX output.
BODY_STYLES = (
    "Normal",
    "Body Text",
    "First Paragraph",
    "Compact",
    "List Bullet",
    "List Paragraph",
)
HEADING_STYLES = ("Heading 1", "Heading 2", "Heading 3")


def docx_font(style: Style) -> str:
    """Return the font the Word deliverable should carry for ``style``."""
    return style.font or DOCX_THEME_FONTS[style.theme]


def apply_base_style(document: Any, style: Style) -> ResolvedStyle:
    """Set page, font, and spacing for one DOCX and return the resolved style.

    Both DOCX paths call this: the reference document Pandoc converts against
    and the styling pass over Pandoc's output. Sharing it is what keeps a Word
    file made either way on the same page size, font, and leading.
    """
    resolved = resolve_style(style)
    font_name = docx_font(style)
    accent = RGBColor.from_string(resolved.accent.lstrip("#"))
    ink = RGBColor(0x1A, 0x1A, 0x1A)
    width, height = PAPER_SIZES[resolved.paper]

    for section in document.sections:
        margin = Inches(resolved.margin_in)
        section.page_width = Inches(width)
        section.page_height = Inches(height)
        section.top_margin = margin
        section.bottom_margin = margin
        section.left_margin = margin
        section.right_margin = margin

    for name in BODY_STYLES:
        set_style_font(document, name, font_name, resolved.size_pt, ink)
    for name, scale, color in (
        ("Heading 1", resolved.theme.name_scale, accent),
        ("Heading 2", resolved.theme.section_scale, accent),
        ("Heading 3", resolved.theme.role_scale, ink),
        ("Title", resolved.theme.name_scale, accent),
    ):
        set_style_font(document, name, font_name, resolved.size_pt * scale, color, bold=True)

    normal = document.styles["Normal"].paragraph_format
    normal.space_after = Pt(resolved.size_pt * resolved.theme.paragraph_spacing_em)
    normal.line_spacing = DOCX_LINE_SPACING[style.density]
    for name in HEADING_STYLES:
        paragraph = document.styles[name].paragraph_format
        paragraph.keep_with_next = True
        paragraph.keep_together = True
    return resolved


def style_docx(path: Path, style: Style, metadata: DocumentMetadata) -> None:
    """Make a generated DOCX visually consistent with the PDF theme."""
    document = docx.Document(str(path))
    resolved = apply_base_style(document, style)
    font_name = docx_font(style)
    muted = RGBColor(0x50, 0x54, 0x5A)
    ink = RGBColor(0x1A, 0x1A, 0x1A)

    current_section = ""
    front_paragraph = 0
    role_pending = False
    for paragraph in document.paragraphs:
        style_name = paragraph.style.name if paragraph.style is not None else ""
        if style_name == "Heading 1":
            continue
        if style_name == "Heading 2":
            current_section = paragraph.text.strip().casefold()
            role_pending = False
            paragraph.paragraph_format.space_before = Pt(8)
            paragraph.paragraph_format.space_after = Pt(3)
            continue
        if style_name == "Heading 3":
            role_pending = True
            paragraph.paragraph_format.space_before = Pt(5)
            paragraph.paragraph_format.space_after = Pt(0)
            continue
        if not paragraph.text.strip():
            continue
        if not current_section and front_paragraph < 2:
            _format_runs(
                paragraph, font_name, resolved.size_pt * resolved.theme.contact_scale, muted
            )
            paragraph.paragraph_format.space_after = Pt(1 if front_paragraph == 0 else 3)
            paragraph.paragraph_format.line_spacing = 1.0
            front_paragraph += 1
            continue
        if role_pending:
            _format_runs(
                paragraph, font_name, resolved.size_pt * resolved.theme.metadata_scale, ink
            )
            paragraph.paragraph_format.space_after = Pt(2)
            role_pending = False
            continue
        if current_section in SKILL_SECTIONS:
            paragraph.paragraph_format.space_after = Pt(2)
        elif any(word in current_section for word in CITATION_WORDS):
            paragraph.paragraph_format.left_indent = Inches(0.16)
            paragraph.paragraph_format.first_line_indent = Inches(-0.16)
            paragraph.paragraph_format.space_after = Pt(3)
            _format_runs(
                paragraph, font_name, resolved.size_pt * resolved.theme.citation_scale, ink
            )
        elif current_section in RECORD_SECTIONS:
            paragraph.paragraph_format.space_after = Pt(1.5)

    properties = document.core_properties
    properties.title = metadata.title
    properties.author = metadata.author
    properties.subject = metadata.description
    properties.keywords = ", ".join(metadata.keywords)
    properties.last_modified_by = ""
    document.save(str(path))
    _scrub_private_metadata(path)


def set_style_font(
    document: Any,
    name: str,
    font_name: str,
    size: float,
    color: RGBColor,
    *,
    bold: bool = False,
) -> None:
    """Apply one font treatment to a named style, creating the style if absent."""
    try:
        style = document.styles[name]
    except KeyError:
        style = document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    style.font.name = font_name
    style.font.size = Pt(size)
    style.font.color.rgb = color
    style.font.bold = bold
    fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
    for attribute in ("asciiTheme", "hAnsiTheme", "csTheme", "eastAsiaTheme"):
        fonts.attrib.pop(qn(f"w:{attribute}"), None)
    for attribute in ("ascii", "hAnsi", "cs", "eastAsia"):
        fonts.set(qn(f"w:{attribute}"), font_name)


def _format_runs(paragraph: Any, font_name: str, size: float, color: RGBColor) -> None:
    for run in paragraph.runs:
        run.font.name = font_name
        run.font.size = Pt(size)
        run.font.color.rgb = color
        fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
        for attribute in ("asciiTheme", "hAnsiTheme", "csTheme", "eastAsiaTheme"):
            fonts.attrib.pop(qn(f"w:{attribute}"), None)
        fonts.set(qn("w:ascii"), font_name)
        fonts.set(qn("w:hAnsi"), font_name)


def _scrub_private_metadata(path: Path) -> None:
    """Remove custom properties and Word revision-session identifiers."""
    descriptor, scratch_name = tempfile.mkstemp(suffix=".docx", dir=path.parent)
    os.close(descriptor)
    scratch = Path(scratch_name)
    try:
        with (
            zipfile.ZipFile(path) as source,
            zipfile.ZipFile(scratch, "w", compression=zipfile.ZIP_DEFLATED) as destination,
        ):
            for item in source.infolist():
                if item.filename == "docProps/custom.xml":
                    continue
                data = source.read(item.filename)
                if item.filename == "[Content_Types].xml":
                    data = _remove_custom_property_reference(
                        data, "PartName", "/docProps/custom.xml"
                    )
                elif item.filename == "_rels/.rels":
                    data = _remove_custom_property_reference(data, "Target", "docProps/custom.xml")
                elif item.filename.startswith("word/") and item.filename.endswith(".xml"):
                    data = _remove_revision_ids(data)
                destination.writestr(item, data)
        os.replace(scratch, path)
    finally:
        scratch.unlink(missing_ok=True)


def _remove_custom_property_reference(data: bytes, attribute: str, value: str) -> bytes:
    """Drop one self-closing package relationship while preserving XML bytes."""
    tag = b"Override" if attribute == "PartName" else b"Relationship"
    pattern = (
        rb"<"
        + tag
        + rb"\b(?=[^>]*\b"
        + re.escape(attribute.encode())
        + rb'="'
        + re.escape(value.encode())
        + rb'")[^>]*/>'
    )
    return re.sub(pattern, b"", data)


def _remove_revision_ids(data: bytes) -> bytes:
    """Remove revision-session identifiers without reserializing Word XML.

    WordprocessingML relies on stable namespace prefixes in attributes such as
    ``mc:Ignorable``. ElementTree is allowed to rename those prefixes, which
    can produce a package Python accepts but Word or LibreOffice rejects.
    Revision identifiers appear three ways: ``w:rsidR``-style attributes in
    the document body, ``<w:rsid/>`` elements in the styles part, and the
    ``<w:rsids>`` registry in settings. All are session fingerprints; all go.
    """
    data = re.sub(rb'\s+w:rsid[A-Za-z0-9]*="[^"]*"', b"", data)
    data = re.sub(rb"<w:rsids>.*?</w:rsids>", b"", data, flags=re.DOTALL)
    return re.sub(rb'<w:rsid(?:Root)? w:val="[^"]*"\s*/>', b"", data)
