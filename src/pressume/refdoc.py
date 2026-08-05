"""Generate a styled Pandoc reference DOCX from the [style] configuration.

The generated file styles Pandoc's DOCX output so the on-demand Word document
shares the PDF's layout intent. Page size, font, and spacing come from
``docxstyle.apply_base_style``, the same call the post-conversion styling pass
makes. Pagination is Word's own and is not guaranteed to match the PDF; the
PDF remains the document of record.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import docx
import pypandoc

from pressume.config import Style
from pressume.docxstyle import apply_base_style
from pressume.errors import RenderError


def build_reference_docx(style: Style, output_path: Path) -> None:
    """Create a Pandoc reference DOCX matching the configured visual style."""
    with tempfile.TemporaryDirectory(prefix="pressume-refdoc-") as scratch:
        base = Path(scratch) / "reference.docx"
        try:
            pypandoc.convert_text("placeholder", "docx", format="markdown", outputfile=str(base))
        except Exception as error:  # external binary boundary
            raise RenderError(f"Pandoc could not create a DOCX reference: {error}") from error
        document = docx.Document(str(base))
        apply_base_style(document, style)
        document.save(str(output_path))
