"""Advisory readability and page-balance diagnostics."""

from __future__ import annotations

import re
import statistics
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

from pressume.checks.report import CheckResult, Severity

HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
BULLET = re.compile(r"^\s*-\s+(.+)")
WORD = re.compile(r"\b[\w+.#/-]+\b")


def inspect_source(name: str, markdown: str) -> list[CheckResult]:
    """Report unusually dense source structures without rejecting valid content."""
    warnings: list[str] = []
    lines = markdown.splitlines()
    first_section = next(
        (index for index, line in enumerate(lines) if line.startswith("## ")), len(lines)
    )
    header = " ".join(
        line.strip() for line in lines[1:first_section] if line.strip() and line != "---"
    )
    if len(header) > 320:
        warnings.append(f"front matter is {len(header)} characters and may wrap heavily")

    bullet_openers: Counter[str] = Counter()
    for number, line in enumerate(lines, start=1):
        bullet = BULLET.match(line)
        if bullet:
            words = WORD.findall(bullet.group(1))
            if len(words) > 75:
                warnings.append(f"line {number}: bullet has {len(words)} words")
            if words:
                bullet_openers[words[0].casefold()] += 1
        elif line and not line.startswith(("#", "**", "---")):
            words = WORD.findall(line)
            if len(words) > 145:
                warnings.append(f"line {number}: paragraph has {len(words)} words")

    bullet_total = sum(bullet_openers.values())
    repeated = sorted(
        (verb, count)
        for verb, count in bullet_openers.items()
        if count >= 6 and count / max(bullet_total, 1) >= 0.12
    )
    if repeated:
        detail = ", ".join(f"{verb} ({count})" for verb, count in repeated)
        warnings.append(f"repeated bullet openers: {detail}")

    if not warnings:
        return [CheckResult(name, "readability: source density", Severity.PASS)]
    return [
        CheckResult(name, "readability: source density", Severity.WARN, warning)
        for warning in warnings
    ]


def inspect_pdf_layout(name: str, pdf_path: Path, markdown: str) -> list[CheckResult]:
    """Report dense pages, sparse endings, and headings stranded at page bottoms."""
    with pdf_path.open("rb") as stream:
        reader = PdfReader(stream)
        return _inspect_pages(name, reader, markdown)


def _inspect_pages(name: str, reader: PdfReader, markdown: str) -> list[CheckResult]:
    headings = {
        match.group(1).strip().casefold()
        for line in markdown.splitlines()
        if (match := HEADING.match(line))
    }
    warnings: list[str] = []
    word_counts: list[int] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        word_counts.append(len(WORD.findall(text)))
        positions: list[tuple[float, float]] = []
        height = float(page.mediabox.height)

        def visit(
            fragment: str,
            cm: list[float],
            tm: list[float],
            _font: object,
            size: float,
            positions: list[tuple[float, float]] = positions,
            height: float = height,
        ) -> None:
            if fragment.strip() and len(cm) >= 6 and len(tm) >= 6:
                y = float(cm[5]) + float(tm[5]) * float(cm[3])
                # Some PDF structure and link fragments expose a synthetic
                # origin at zero. They are not painted text and would make
                # every healthy page appear to touch its trim edge.
                if 1 < y < height:
                    positions.append((y, float(size)))

        page.extract_text(visitor_text=visit)
        if positions:
            top = max(y + size for y, size in positions)
            bottom = min(y for y, _ in positions)
            fill = (top - bottom) / height
            if fill > 0.91 or len(lines) > 72:
                warnings.append(
                    f"page {page_number}: dense vertical fill "
                    f"({fill:.0%}, {len(lines)} extracted lines)"
                )
            if bottom < 28:
                warnings.append(
                    f"page {page_number}: text approaches the bottom edge ({bottom:.0f} pt)"
                )
        if lines and lines[-1].casefold() in headings:
            warnings.append(
                f"page {page_number}: heading is stranded at the page bottom: {lines[-1]}"
            )

    if len(word_counts) > 1 and word_counts[-1] < statistics.median(word_counts[:-1]) * 0.28:
        warnings.append(
            f"final page is lightly filled ({word_counts[-1]} words versus "
            f"{statistics.median(word_counts[:-1]):.0f} on preceding pages)"
        )

    if not warnings:
        return [CheckResult(name, "readability: page balance", Severity.PASS)]
    return [
        CheckResult(name, "readability: page balance", Severity.WARN, warning)
        for warning in warnings
    ]
