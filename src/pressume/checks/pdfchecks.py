"""Checks on the delivered PDF: page targets and extracted-text hygiene.

The text is extracted with pypdf, which reads the same content stream an ATS
parser reads. If something is wrong here, it is wrong for the recipient.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from difflib import SequenceMatcher
from functools import partial
from pathlib import Path
from typing import Any

from pdfminer.high_level import extract_pages
from pdfminer.high_level import extract_text as pdfminer_extract_text
from pdfminer.layout import LTTextContainer, LTTextLine
from pypdf import PdfReader

from pressume.checks.report import CheckResult, Severity, grader
from pressume.checks.textrules import (
    describe_character,
    smart_punctuation_found,
    unexpected_non_ascii,
)
from pressume.config import Checks
from pressume.links import linkify_markdown
from pressume.metadata import DocumentMetadata

LINK_TARGET = re.compile(r"\[[^]]+\]\(([^)]+)\)")
TOKEN = re.compile(r"\w+", re.UNICODE)
MARKDOWN_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF in content-stream reading order."""
    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def count_pages(pdf_path: Path) -> int:
    """Return the number of pages in ``pdf_path``."""
    return len(PdfReader(str(pdf_path)).pages)


def check_page_target(
    name: str,
    pdf_path: Path,
    target: int | None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> list[CheckResult]:
    """Compare a PDF's page count with its exact target or permitted range."""
    verdict = grader(name, "pdf: page count")
    pages = count_pages(pdf_path)
    if target is minimum is maximum is None:
        return [verdict(Severity.WARN, f"{pages} page(s), no target set")]
    low, high = (target, target) if target is not None else (minimum, maximum)
    if (low is None or pages >= low) and (high is None or pages <= high):
        bounds = "" if target is not None else f", range {minimum or 1}-{maximum or 'unbounded'}"
        return [verdict(Severity.PASS, f"{pages} page(s)" + bounds)]
    expected = (
        str(target) if target is not None else f"range {minimum or 1}-{maximum or 'unbounded'}"
    )
    return [verdict(Severity.FAIL, f"expected {expected} page(s), rendered {pages}")]


def check_pdf_delivery(
    name: str,
    pdf_path: Path,
    metadata: DocumentMetadata,
    markdown: str,
) -> list[CheckResult]:
    """Verify metadata, tags, real hyperlinks, and independent extraction."""
    reader = PdfReader(str(pdf_path))
    results: list[CheckResult] = []
    info: Any = reader.metadata or {}
    actual_metadata = {
        "title": str(info.get("/Title", "")),
        "author": str(info.get("/Author", "")),
        "description": str(info.get("/Subject", "")),
    }
    expected_metadata = {
        "title": metadata.title,
        "author": metadata.author,
        "description": metadata.description,
    }
    mismatches = [
        f"{key}={actual_metadata[key]!r}"
        for key, expected in expected_metadata.items()
        if actual_metadata[key] != expected
    ]
    results.append(
        CheckResult(
            name,
            "pdf: metadata",
            Severity.FAIL if mismatches else Severity.PASS,
            "; ".join(mismatches),
        )
    )

    root = reader.root_object
    tagged = "/StructTreeRoot" in root and bool(root.get("/MarkInfo", {}).get("/Marked"))
    language = str(root.get("/Lang", "")).strip("()")
    accessible = tagged and language.casefold().startswith(metadata.language.casefold())
    results.append(
        CheckResult(
            name,
            "pdf: accessibility structure",
            Severity.PASS if accessible else Severity.FAIL,
            f"tagged={tagged}, language={language or 'missing'}",
        )
    )

    expected_links = set(LINK_TARGET.findall(linkify_markdown(markdown)))
    actual_links: set[str] = set()
    for page in reader.pages:
        for annotation_ref in page.get("/Annots", []):
            annotation = annotation_ref.get_object()
            if annotation.get("/Subtype") == "/Link":
                action = annotation.get("/A", {})
                if action.get("/URI"):
                    actual_links.add(str(action["/URI"]))
    missing = sorted(expected_links - actual_links)
    results.append(
        CheckResult(
            name,
            "pdf: hyperlinks",
            Severity.FAIL if missing else Severity.PASS,
            f"missing: {missing}" if missing else f"{len(actual_links)} embedded link(s)",
        )
    )
    results.append(check_visual_relationships(name, pdf_path, markdown))
    results.append(_check_extractor_agreement(name, pdf_path, extract_pdf_text(pdf_path)))
    return results


def _extract_line_geometry(pdf_path: Path) -> list[tuple[str, float, float, int]]:
    """Return (text, top, bottom, page) for every text line, top to bottom.

    pdfminer.six reports layout in PDF coordinates, which grow upward, so a
    line's ``y1`` is its top edge. Sorting each page by descending top edge
    reconstructs visual order regardless of content-stream order.
    """
    lines: list[tuple[str, float, float, int]] = []
    for page_number, page_layout in enumerate(extract_pages(str(pdf_path))):
        page_lines: list[tuple[str, float, float, int]] = []
        for element in page_layout:
            if not isinstance(element, LTTextContainer):
                continue
            for line in element:
                if isinstance(line, LTTextLine):
                    text = line.get_text().strip()
                    if text:
                        page_lines.append((text, line.y1, line.y0, page_number))
        page_lines.sort(key=lambda entry: -entry[1])
        lines.extend(page_lines)
    return lines


def check_visual_relationships(name: str, pdf_path: Path, markdown: str) -> CheckResult:
    """Reject collisions immediately below names, sections, and role headings.

    Font bounding boxes routinely overlap slightly on ordinary consecutive
    body lines even when their glyphs do not. Heading transitions are different:
    they need deliberate white space and are stable semantic relationships we
    can verify without mistaking normal leading for a collision.
    """
    try:
        lines = _extract_line_geometry(pdf_path)
    except Exception as error:  # independent geometry-parser boundary
        return CheckResult(name, "pdf: visual relationships", Severity.WARN, str(error))

    collisions: list[str] = []
    checked = 0
    headings = [(len(marker), text.strip()) for marker, text in MARKDOWN_HEADING.findall(markdown)]
    for level, heading in headings:
        minimum_gap = 1.0 if level in {1, 2} else 0.5
        for index, (line_text, _top, bottom, page_number) in enumerate(lines[:-1]):
            if line_text.casefold() != heading.casefold():
                continue
            next_text, next_top, _next_bottom, next_page = lines[index + 1]
            if next_page != page_number:
                continue
            # PDF coordinates grow upward: the clearance below a heading is
            # its bottom edge minus the top edge of the line beneath it.
            gap = bottom - next_top
            checked += 1
            if gap < minimum_gap:
                collisions.append(
                    f"{heading!r} -> {next_text!r}: {gap:.2f}pt (minimum {minimum_gap:.1f}pt)"
                )
            break
    return CheckResult(
        name,
        "pdf: visual relationships",
        Severity.FAIL if collisions else Severity.PASS,
        "; ".join(collisions) if collisions else f"{checked} heading transition(s) clear",
    )


def independent_extractor() -> tuple[str, Callable[[Path], str]]:
    """Select the second text extractor: Poppler when installed, else pdfminer.six.

    The selection policy lives here alone; the agreement check compares
    whatever this returns, and doctor reports it, so neither carries its own
    copy of the environment knowledge.
    """
    if executable := shutil.which("pdftotext"):
        return "poppler", partial(_poppler_extract, executable)
    return "pdfminer.six", lambda path: pdfminer_extract_text(str(path))


def _poppler_extract(executable: str, pdf_path: Path) -> str:
    completed = subprocess.run(
        [executable, "-layout", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return str(completed.stdout)


def _check_extractor_agreement(name: str, pdf_path: Path, pypdf_text: str) -> CheckResult:
    """Compare pypdf's extraction with an independent implementation's."""
    extractor, extract = independent_extractor()
    try:
        independent_text = extract(pdf_path)
    except Exception as error:  # independent parser boundary
        return CheckResult(name, "pdf: independent extraction", Severity.WARN, str(error))
    pypdf_tokens = [token.casefold() for token in TOKEN.findall(pypdf_text)]
    independent_tokens = [token.casefold() for token in TOKEN.findall(independent_text)]
    token_agreement = SequenceMatcher(
        None, pypdf_tokens, independent_tokens, autojunk=False
    ).ratio()
    # Tagged-PDF block boundaries can make one parser return ``roleauthorized``
    # where another returns ``role`` and ``authorized``. Comparing the ordered
    # alphanumeric stream ignores that harmless boundary while still detecting
    # missing or reordered content.
    pypdf_characters = "".join(pypdf_tokens)
    independent_characters = "".join(independent_tokens)
    character_agreement = SequenceMatcher(
        None, pypdf_characters, independent_characters, autojunk=False
    ).ratio()
    longer = max(len(pypdf_characters), len(independent_characters), 1)
    coverage = min(len(pypdf_characters), len(independent_characters)) / longer
    same = character_agreement >= 0.995 and coverage >= 0.995
    return CheckResult(
        name,
        "pdf: independent extraction",
        Severity.PASS if same else Severity.FAIL,
        f"{character_agreement:.2%} character agreement, {coverage:.2%} coverage, "
        f"{token_agreement:.2%} token-boundary agreement; "
        f"pypdf={len(pypdf_tokens)} words, "
        f"{extractor}={len(independent_tokens)} words",
    )


def check_text_hygiene(name: str, surface: str, text: str, checks: Checks) -> list[CheckResult]:
    """Punctuation, character-set, and required/forbidden string checks."""
    results: list[CheckResult] = []

    character_rules = (
        (
            checks.ascii_only,
            "ASCII only",
            unexpected_non_ascii(text, set(checks.allowed_characters)),
        ),
        (checks.forbid_smart_punctuation, "no smart punctuation", smart_punctuation_found(text)),
    )
    for enabled, label, offenders in character_rules:
        if not enabled:
            continue
        verdict = grader(name, f"{surface}: {label}")
        if offenders:
            described = ", ".join(describe_character(c) for c in offenders)
            results.append(verdict(Severity.FAIL, f"Found {described}"))
        else:
            results.append(verdict(Severity.PASS))

    for required in checks.required_strings:
        verdict = grader(name, f"{surface}: exact string")
        if required in text:
            results.append(verdict(Severity.PASS, repr(required)))
        else:
            results.append(verdict(Severity.FAIL, f"required text not found: {required!r}"))

    for protected in checks.protected_strings:
        # Protected strings bind only when their topic appears: the first word
        # present without the full phrase means the exact value was mangled.
        verdict = grader(name, f"{surface}: protected string")
        probe = protected.split(maxsplit=1)[0]
        if protected in text:
            results.append(verdict(Severity.PASS, repr(protected)))
        elif probe and probe in text:
            results.append(
                verdict(
                    Severity.FAIL, f"text approaches but does not exactly contain {protected!r}"
                )
            )

    for forbidden in checks.forbidden_strings:
        severity = Severity.FAIL if forbidden in text else Severity.PASS
        results.append(CheckResult(name, f"{surface}: forbidden string", severity, repr(forbidden)))
    return results
