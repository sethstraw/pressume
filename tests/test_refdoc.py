"""Reference-DOCX generation tests."""

from docx import Document

from pressume.config import Style
from pressume.refdoc import build_reference_docx


def test_reference_docx_uses_configured_style(tmp_path):
    output = tmp_path / "reference.docx"
    style = Style(font="Arial", size_pt=11, margin_in=0.75, accent="#123456")

    build_reference_docx(style, output)

    assert output.stat().st_size > 0
    document = Document(output)
    assert document.styles["Normal"].font.name == "Arial"
    assert document.styles["Normal"].font.size.pt == 11
    assert document.sections[0].top_margin.inches == 0.75
