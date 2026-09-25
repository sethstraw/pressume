"""Producing and verifying one deliverable at a time.

Every format pairs the way to produce it with the way to reopen and check what
was produced. The format names live once, in ``config.KNOWN_FORMATS``; a test
renders and verifies each of them, so a name that gains configuration without
an implementation fails the suite rather than a user's render.
"""

from __future__ import annotations

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
from pressume.config import Checks, Config
from pressume.convert import render_docx, render_pdf, render_txt
from pressume.documents import SourceDocument
from pressume.errors import RenderError


def render_artifact(name: str, source: SourceDocument, destination: Path, config: Config) -> None:
    """Write ``source`` to ``destination`` in the named format."""
    if name == "pdf":
        render_pdf(
            source.markdown,
            destination,
            config,
            source.metadata(config),
            letter=source.is_letter(config),
        )
    elif name == "docx":
        render_docx(source.markdown, destination, config, source.metadata(config))
    elif name == "txt":
        render_txt(source.markdown, destination)
    else:
        raise RenderError(f"No renderer for format {name!r}")


def verify_artifact(
    name: str, source: SourceDocument, artifact: Path, checks: Checks, config: Config
) -> list[CheckResult]:
    """Reopen ``artifact`` and return every check the named format defines."""
    if name == "pdf":
        return _verify_pdf(source, artifact, checks, config)
    if name == "docx":
        return check_docx(source.stem, artifact, checks, source.metadata(config), source.markdown)
    if name == "txt":
        return _verify_txt(source, artifact, checks)
    raise RenderError(f"No verifier for format {name!r}")


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


def _verify_txt(source: SourceDocument, artifact: Path, checks: Checks) -> list[CheckResult]:
    try:
        text = artifact.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RenderError(f"Could not read generated {artifact.name}: {error}") from error
    return check_text_hygiene(source.stem, "txt", text, checks)
