"""Format conversions: Markdown to Typst, plain text, DOCX, and Typst to PDF.

Pandoc is provided by the `pypandoc-binary` wheel and Typst by the `typst`
wheel, so no system installs are required.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, cast

import pypandoc
import typst

from pressume.config import Config, ConfigError, Document
from pressume.errors import RenderError
from pressume.links import linkify_markdown
from pressume.metadata import DocumentMetadata, derive_metadata
from pressume.template import build_document, strip_thematic_breaks

# `-smart` keeps straight ASCII quotes and dashes exactly as written.
MARKDOWN = "markdown-smart"


def markdown_to_typst_body(markdown: str) -> str:
    """Convert Markdown to a Typst body fragment (no preamble)."""
    try:
        return cast(
            str,
            pypandoc.convert_text(markdown, "typst", format=MARKDOWN, extra_args=["--wrap=none"]),
        )
    except Exception as error:  # external binary boundary
        raise RenderError(f"Pandoc could not convert Markdown to Typst: {error}") from error


def bundled_font_dirs() -> list[Path]:
    """Return every bundled OFL font directory.

    Bundling the default typeface means a fresh install renders identically
    on every machine with no font setup and no silent fallback; a document
    repo carries content and one configuration file, nothing else.
    """
    from importlib.resources import files

    root = Path(str(files("pressume") / "fonts"))
    return [root, *(path for path in sorted(root.iterdir()) if path.is_dir())]


def render_pdf(
    markdown: str,
    output_path: Path,
    config: Config,
    metadata: DocumentMetadata | None = None,
) -> None:
    """Render Markdown to a PDF via a generated Typst document."""
    metadata = metadata or derive_metadata(markdown, Document(file="Resume.md"), "en", "US")
    prepared = linkify_markdown(strip_thematic_breaks(markdown))
    body = markdown_to_typst_body(prepared)
    document = build_document(body, config.style, metadata)
    with tempfile.TemporaryDirectory(prefix="pressume-") as scratch:
        source = Path(scratch) / "resume.typ"
        source.write_text(document, encoding="utf-8")
        try:
            pdf_standards: Any = (
                None if config.style.pdf_standard == "default" else [config.style.pdf_standard]
            )
            typst.compile(
                str(source),
                output=str(output_path),
                font_paths=[
                    *(str(config.resolve(directory)) for directory in config.font_dirs),
                    *(str(directory) for directory in bundled_font_dirs()),
                ],
                pdf_standards=pdf_standards,
            )
        except Exception as error:  # external renderer boundary
            raise RenderError(f"Typst could not produce {output_path.name}: {error}") from error


def render_txt(markdown: str, output_path: Path) -> None:
    """Render Markdown to plain text, the format ATS keyword scanners index."""
    try:
        text = cast(
            str,
            pypandoc.convert_text(
                strip_thematic_breaks(markdown),
                "plain",
                format=MARKDOWN,
                extra_args=["--wrap=none"],
            ),
        )
    except Exception as error:  # external binary boundary
        raise RenderError(f"Pandoc could not produce {output_path.name}: {error}") from error
    output_path.write_text(text, encoding="utf-8")


def render_docx(
    markdown: str,
    output_path: Path,
    config: Config,
    metadata: DocumentMetadata,
) -> None:
    """Render Markdown to DOCX with Pandoc, styled by an optional reference DOCX.

    The DOCX is an on-demand convenience for portals that require Word uploads;
    the PDF is the document of record and their pagination may differ.
    """
    extra_args = []
    if config.reference_docx is not None:
        reference = config.resolve(config.reference_docx)
        if not reference.exists():
            # A configured-but-absent path is a configuration mistake, not a
            # rendering failure, and exits with the configuration error code.
            raise ConfigError(
                [
                    f"paths.reference_docx: {reference} does not exist; "
                    "create it with `pressume refdoc` or remove the setting"
                ]
            )
        extra_args += ["--reference-doc", str(reference)]
    try:
        # Passing title/author metadata to Pandoc also paints a title block in
        # the document body. Apply delivery metadata after conversion instead,
        # keeping the resume's H1 as its one and only visible name line.
        pypandoc.convert_text(
            linkify_markdown(strip_thematic_breaks(markdown)),
            "docx",
            format=MARKDOWN,
            outputfile=str(output_path),
            extra_args=extra_args,
        )
    except Exception as error:  # external binary boundary
        raise RenderError(f"Pandoc could not produce {output_path.name}: {error}") from error
    from pressume.docxstyle import style_docx

    style_docx(output_path, config.style, metadata)
