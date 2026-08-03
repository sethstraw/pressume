"""Output formats as self-contained strategies.

Each deliverable pairs the way to produce it with the way to verify what was
produced. The pipeline iterates the registry without knowing any format's
name; adding a format is one new entry here, and the registry is asserted
against the configuration vocabulary so the two can never drift.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pressume.checks.ats import check_ats
from pressume.checks.docxchecks import check_docx
from pressume.checks.pdfchecks import (
    check_page_target,
    check_pdf_delivery,
    check_text_hygiene,
    extract_pdf_text,
)
from pressume.checks.report import CheckResult
from pressume.config import KNOWN_FORMATS, Checks, Config
from pressume.convert import render_docx, render_pdf, render_txt
from pressume.documents import SourceDocument
from pressume.errors import RenderError

Renderer = Callable[[SourceDocument, Path, Config], None]
Verifier = Callable[[SourceDocument, Path, Checks, Config], list[CheckResult]]


@dataclass(frozen=True)
class OutputFormat:
    """How one deliverable is produced and independently verified."""

    render: Renderer
    verify: Verifier


def _render_pdf(source: SourceDocument, destination: Path, config: Config) -> None:
    render_pdf(source.markdown, destination, config, source.metadata(config))


def _verify_pdf(
    source: SourceDocument, artifact: Path, checks: Checks, config: Config
) -> list[CheckResult]:
    results = check_page_target(
        source.stem,
        artifact,
        source.settings.pages,
        source.settings.min_pages,
        source.settings.max_pages,
    )
    try:
        text = extract_pdf_text(artifact)
    except Exception as error:  # PDF parser boundary
        raise RenderError(f"Could not read generated {artifact.name}: {error}") from error
    results.extend(check_text_hygiene(source.stem, "pdf", text, checks))
    results.extend(check_ats(source.stem, text, checks))
    results.extend(
        check_pdf_delivery(source.stem, artifact, source.metadata(config), source.markdown)
    )
    return results


def _render_txt(source: SourceDocument, destination: Path, config: Config) -> None:
    render_txt(source.markdown, destination)


def _verify_txt(
    source: SourceDocument, artifact: Path, checks: Checks, config: Config
) -> list[CheckResult]:
    try:
        text = artifact.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RenderError(f"Could not read generated {artifact.name}: {error}") from error
    return check_text_hygiene(source.stem, "txt", text, checks)


def _render_docx(source: SourceDocument, destination: Path, config: Config) -> None:
    render_docx(source.markdown, destination, config, source.metadata(config))


def _verify_docx(
    source: SourceDocument, artifact: Path, checks: Checks, config: Config
) -> list[CheckResult]:
    return check_docx(source.stem, artifact, checks, source.metadata(config), source.markdown)


FORMATS: dict[str, OutputFormat] = {
    "pdf": OutputFormat(_render_pdf, _verify_pdf),
    "txt": OutputFormat(_render_txt, _verify_txt),
    "docx": OutputFormat(_render_docx, _verify_docx),
}

# Configuration validates format names without importing this module; a new
# format that misses either side fails at import, not in a user's render.
assert tuple(FORMATS) == KNOWN_FORMATS
