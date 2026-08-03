"""Generate a styled Pandoc reference DOCX from the [style] configuration.

The generated file styles Pandoc's DOCX output so the on-demand Word document
shares the PDF's layout intent. Font selection and line spacing come from the
same rules as the post-conversion styling pass in ``docxstyle``, so the two
DOCX paths cannot drift apart. Pagination is Word's own and is not guaranteed
to match the PDF; the PDF remains the document of record.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import docx
import pypandoc
from docx.shared import Inches, Pt, RGBColor

from pressume.config import Style
from pressume.docxstyle import DOCX_LINE_SPACING, docx_font, set_style_font
from pressume.errors import RenderError
from pressume.template import resolve_style


def build_reference_docx(style: Style, output_path: Path) -> None:
    """Create a Pandoc reference DOCX matching the configured visual style."""
    resolved = resolve_style(style)
    font_name = docx_font(style)
    accent = RGBColor.from_string(resolved.accent.lstrip("#"))
    ink = RGBColor(0x1A, 0x1A, 0x1A)

    with tempfile.TemporaryDirectory(prefix="pressume-refdoc-") as scratch:
        base = Path(scratch) / "reference.docx"
        try:
            pypandoc.convert_text("placeholder", "docx", format="markdown", outputfile=str(base))
        except Exception as error:  # external binary boundary
            raise RenderError(f"Pandoc could not create a DOCX reference: {error}") from error
        document = docx.Document(str(base))

        for section in document.sections:
            margin = Inches(resolved.margin_in)
            section.top_margin = margin
            section.bottom_margin = margin
            section.left_margin = margin
            section.right_margin = margin

        base_size = resolved.size_pt
        for name in ("Normal", "Body Text", "First Paragraph", "Compact", "List Bullet"):
            set_style_font(document, name, font_name, base_size, ink)
        set_style_font(
            document,
            "Heading 1",
            font_name,
            base_size * resolved.theme.name_scale,
            accent,
            bold=True,
        )
        set_style_font(
            document,
            "Heading 2",
            font_name,
            base_size * resolved.theme.section_scale,
            accent,
            bold=True,
        )
        set_style_font(
            document, "Heading 3", font_name, base_size * resolved.theme.role_scale, ink, bold=True
        )
        set_style_font(
            document, "Title", font_name, base_size * resolved.theme.name_scale, accent, bold=True
        )

        normal = document.styles["Normal"].paragraph_format
        normal.space_after = Pt(base_size * resolved.theme.paragraph_spacing_em)
        normal.line_spacing = DOCX_LINE_SPACING[style.density]
        for name in ("Heading 1", "Heading 2", "Heading 3"):
            paragraph = document.styles[name].paragraph_format
            paragraph.keep_with_next = True
            paragraph.keep_together = True

        document.save(str(output_path))
