"""Text-geometry baselines for the rendered PDF corpus.

This is contributor tooling. A user of the installed CLI never runs it: it
renders a corpus of invented fixtures under every maintained theme and paper
size, reduces each PDF to the boxes its text lines occupy, and compares that
against a recorded baseline. It lives beside the tests rather than in
``src/pressume`` for that reason.

Nothing here writes a baseline. Recording is the only job of
``tests/regenerate_geometry_baselines.py``, so a comparison has no code path
that can rewrite the file it just failed against.

What these baselines are pinned to
----------------------------------
The theme fonts are bundled and ``fallback: false`` is set, so glyph metrics
are fixed and a missing glyph is an error rather than a substitution. Typst and
Pandoc are floor pinned (``typst>=0.14.0``, ``pypandoc-binary>=1.13``), so a
minor release of either can move every line on every page. The versions that
produced a baseline are recorded in ``baselines/renderer.txt``. When the
running versions differ, the baseline comparisons skip and name both versions,
and the layout invariants below still run: a comparison is never passed
silently against a renderer that did not produce the baseline.

DOCX is out of scope. ``docxstyle.py`` sets fonts by name and the reader's
machine resolves them, so a Word file is not visually reproducible off the
machine that opens it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from difflib import SequenceMatcher
from importlib.metadata import version
from itertools import pairwise
from pathlib import Path
from typing import Any

import pypandoc
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTPage, LTTextContainer, LTTextLine

from pressume.checks.pdfchecks import MARKDOWN_HEADING, check_visual_relationships
from pressume.config import Config, Document, Style
from pressume.convert import render_pdf
from pressume.metadata import derive_metadata
from pressume.themes import THEMES

FIXTURE_DIR = Path(__file__).parent / "fixtures"
BASELINE_DIR = Path(__file__).parent / "baselines"
RENDERER_FILE = BASELINE_DIR / "renderer.txt"

# Every fixture is invented. No real person, employer, school, or publication
# appears in this repository.
FIXTURES = (
    "short_resume",
    "dense_resume",
    "long_cv",
    "overflow_candidates",
    "page_boundary",
)
THEMES_UNDER_TEST = ("modern", "technical", "traditional")
PAPERS = ("us-letter", "a4")

# Coordinates are rounded to 0.1 pt, which is 1/720 inch. That is far below the
# smallest difference a reader could see and far below any layout change worth
# reporting, and it absorbs the last-digit float differences that the same
# Typst version can produce on a different CPU. A real move is points, not
# hundredths of one.
PRECISION = 1

# pdfminer reports a line's box from its glyph bounding boxes, which include
# side bearings and ascender or descender overshoot. Measured overshoot across
# this corpus stays under 2 pt, so a line has to clear an edge by more than
# this before it counts as overflow or clipping. A real overflow, such as an
# unbreakable URL, misses by tens of points.
EDGE_TOLERANCE = 4.0

# A final page carrying less than this fraction of the text region's height is
# an ending a reader reads as a mistake.
MINIMUM_FINAL_PAGE_FILL = 0.15

# Recorded line text is escaped to ASCII and cut to this many characters. It is
# there so a reviewer can read the diff; the coordinates are the measurement.
TEXT_WIDTH = 60

INCH = 72.0


@dataclass(frozen=True)
class Line:
    """One extracted text line and the box it occupies, in PDF points."""

    page: int
    top: float
    bottom: float
    left: float
    right: float
    size: float
    font: str
    text: str


@dataclass(frozen=True)
class Geometry:
    """Every text line in one rendered PDF, with its page and text region."""

    pages: int
    width: float
    height: float
    region: tuple[float, float, float, float]  # left, bottom, right, top
    lines: tuple[Line, ...]

    def page_lines(self, page: int) -> tuple[Line, ...]:
        """Return the lines on ``page``, top to bottom."""
        return tuple(line for line in self.lines if line.page == page)


@dataclass(frozen=True)
class Finding:
    """One thing wrong with a rendered page, named and quantified."""

    kind: str
    detail: str

    def __str__(self) -> str:
        """Render the finding as one readable line."""
        return f"{self.kind}: {self.detail}"


def describe(fixture: str, theme: str, paper: str, findings: list[Finding]) -> list[str]:
    """Prefix findings with the fixture and configuration that produced them."""
    return [f"{fixture} [{theme} {paper}] {finding}" for finding in findings]


def configurations() -> Iterator[tuple[str, str, str]]:
    """Yield every fixture crossed with every theme and paper size."""
    for fixture in FIXTURES:
        for theme in THEMES_UNDER_TEST:
            for paper in PAPERS:
                yield fixture, theme, paper


def read_fixture(fixture: str) -> str:
    """Return the Markdown source of one corpus fixture."""
    return (FIXTURE_DIR / f"{fixture}.md").read_text(encoding="utf-8")


def render(markdown: str, theme: str, paper: str, destination: Path) -> Path:
    """Render Markdown to PDF under one theme and paper size."""
    config = Config(config_dir=destination.parent, style=Style(theme=theme, paper=paper))
    metadata = derive_metadata(markdown, Document(file="Resume.md"), "en", "CA")
    render_pdf(markdown, destination, config, metadata)
    return destination


def text_region(width: float, height: float, theme: str) -> tuple[float, float, float, float]:
    """Return the text region Typst was given: left, bottom, right, top.

    The traditional theme sets its vertical margin separately, so this mirrors
    ``template._build_traditional_document``. If that rule changes, this has to
    change with it or the overflow check measures against the wrong box.
    """
    margin = THEMES[theme].margin_in
    vertical = max(0.25, margin - 0.04) if theme == "traditional" else margin
    return (
        _round(margin * INCH),
        _round(vertical * INCH),
        _round(width - margin * INCH),
        _round(height - vertical * INCH),
    )


def measure(pdf_path: Path, theme: str) -> Geometry:
    """Reduce a rendered PDF to its text lines and the region they sit in."""
    lines: list[Line] = []
    width = height = 0.0
    pages = 0
    for number, layout in enumerate(extract_pages(str(pdf_path)), start=1):
        pages = number
        width, height = _round(layout.width), _round(layout.height)
        lines.extend(_page_lines(layout, number))
    return Geometry(
        pages=pages,
        width=width,
        height=height,
        region=text_region(width, height, theme),
        lines=tuple(lines),
    )


def _page_lines(layout: LTPage, page: int) -> list[Line]:
    """Return one page's text lines in visual order, top to bottom."""
    lines: list[Line] = []
    for element in layout:
        if not isinstance(element, LTTextContainer):
            continue
        for item in element:
            if not isinstance(item, LTTextLine):
                continue
            text = item.get_text().strip()
            characters = [
                character
                for character in item
                if isinstance(character, LTChar) and character.get_text().strip()
            ]
            if not text or not characters:
                continue
            lines.append(
                Line(
                    page=page,
                    top=_round(item.y1),
                    bottom=_round(item.y0),
                    left=_round(item.x0),
                    right=_round(item.x1),
                    size=_round(max(character.size for character in characters)),
                    font=_font_name(characters),
                    text=text,
                )
            )
    # Ties are broken by the left edge so two lines sharing a baseline always
    # record in the same order.
    lines.sort(key=lambda line: (-line.top, line.left))
    return lines


def _font_name(characters: list[LTChar]) -> str:
    """Return the font most of a line is set in, without its subset prefix."""
    counts = Counter(character.fontname.split("+")[-1] for character in characters)
    return min(counts.items(), key=lambda item: (-item[1], item[0]))[0]


def _round(value: float) -> float:
    """Round to the recorded precision, without producing negative zero."""
    rounded = round(float(value), PRECISION)
    return rounded if rounded else 0.0


def _weight_rank(font: str) -> int:
    """Rank a font's weight coarsely enough to order headings against body."""
    name = font.casefold()
    if "semibold" in name or "medium" in name:
        return 1
    if "bold" in name or "black" in name:
        return 2
    return 0


# ---------------------------------------------------------------------------
# The baseline file format.
# ---------------------------------------------------------------------------

HEADER = """\
# pressume text-geometry baseline. Data, not code: read the diff.
#
# Regenerate every baseline with:
#     uv run python tests/regenerate_geometry_baselines.py
# Regenerate only when a layout change was intended and you can say what it
# was. A surprise here is a report, not a file to overwrite.
#
# One section per configuration. Coordinates are PDF points from the page's
# bottom-left corner, rounded to 0.1 pt. Columns are:
#     page top bottom left right size font text
# `region` is left bottom right top of the region Typst was given. Text is
# escaped to ASCII and cut to {width} characters; the numbers are the
# measurement.
"""


def format_geometry(geometry: Geometry) -> list[str]:
    """Render one configuration's geometry as baseline lines."""
    left, bottom, right, top = geometry.region
    out = [
        f"paper {geometry.width:.1f} {geometry.height:.1f}",
        f"region {left:.1f} {bottom:.1f} {right:.1f} {top:.1f}",
        f"pages {geometry.pages}",
    ]
    out.extend(
        f"{line.page} {line.top:.1f} {line.bottom:.1f} {line.left:.1f} {line.right:.1f} "
        f"{line.size:.1f} {line.font} {_ascii(line.text)}"
        for line in geometry.lines
    )
    return out


def format_baseline(sections: dict[str, Geometry]) -> str:
    """Render every configuration of one fixture as a complete baseline file."""
    out = [HEADER.format(width=TEXT_WIDTH)]
    for label, geometry in sections.items():
        out.append(f"[{label}]\n" + "\n".join(format_geometry(geometry)) + "\n")
    return "\n".join(out)


def parse_baseline(text: str) -> dict[str, Geometry]:
    """Parse a baseline file back into one Geometry per configuration."""
    sections: dict[str, Geometry] = {}
    label = ""
    header: dict[str, Any] = {}
    lines: list[Line] = []

    def store() -> None:
        if label:
            sections[label] = Geometry(
                pages=int(header["pages"][0]),
                width=float(header["paper"][0]),
                height=float(header["paper"][1]),
                region=(
                    float(header["region"][0]),
                    float(header["region"][1]),
                    float(header["region"][2]),
                    float(header["region"][3]),
                ),
                lines=tuple(lines),
            )

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            store()
            label, header, lines = line.strip("[]"), {}, []
            continue
        head, _, rest = line.partition(" ")
        if head in ("paper", "region", "pages"):
            header[head] = rest.split()
            continue
        fields = line.split(None, 7)
        lines.append(
            Line(
                page=int(fields[0]),
                top=float(fields[1]),
                bottom=float(fields[2]),
                left=float(fields[3]),
                right=float(fields[4]),
                size=float(fields[5]),
                font=fields[6],
                text=fields[7] if len(fields) > 7 else "",
            )
        )
    store()
    return sections


def normalize(geometry: Geometry) -> Geometry:
    """Round-trip a measurement through the file format.

    Recorded text is escaped and cut, so an observed measurement goes through
    the same reduction before it is compared. Otherwise every long line would
    diff against its own recorded, shortened self.
    """
    return parse_baseline("[x]\n" + "\n".join(format_geometry(geometry)))["x"]


def _ascii(text: str) -> str:
    """Escape text to ASCII and cut it to the recorded width.

    The list bullet is U+2022 and this repository is ASCII only, so the escape
    is what keeps a baseline file readable in every editor and every diff.
    Escaping happens before the cut, which makes this idempotent: reducing an
    already-recorded line returns that line rather than a shorter one.
    """
    escaped = text.encode("ascii", "backslashreplace").decode("ascii")
    return escaped[:TEXT_WIDTH].strip()


# ---------------------------------------------------------------------------
# What a comparison detects.
# ---------------------------------------------------------------------------


def inspect(geometry: Geometry, markdown: str, pdf_path: Path) -> list[Finding]:
    """Report the layout faults a page can have on its own evidence.

    These need no baseline: they are true or false of the rendered PDF in front
    of them, so a renderer upgrade does not excuse them.
    """
    findings: list[Finding] = []
    findings.extend(_check_edges(geometry))
    findings.extend(_check_collisions(pdf_path, markdown))
    findings.extend(_check_stranded_heading(geometry, markdown))
    findings.extend(_check_hierarchy(geometry, markdown))
    findings.extend(_check_final_page(geometry))
    return findings


def _check_edges(geometry: Geometry) -> list[Finding]:
    """Report text outside the text region, and text off the paper.

    Overflow and clipping are the same measurement against two different
    boxes: the region Typst was told to fill, and the paper itself.
    """
    left, bottom, right, top = geometry.region
    findings: list[Finding] = []
    for line in geometry.lines:
        misses = (
            ("overflow", "text region", "left", left - line.left),
            ("overflow", "text region", "right", line.right - right),
            ("overflow", "text region", "top", line.top - top),
            ("overflow", "text region", "bottom", bottom - line.bottom),
            ("clipping", "paper", "left", 0.0 - line.left),
            ("clipping", "paper", "right", line.right - geometry.width),
            ("clipping", "paper", "top", line.top - geometry.height),
            ("clipping", "paper", "bottom", 0.0 - line.bottom),
        )
        findings.extend(
            Finding(
                kind,
                f"page {line.page}: {line.text[:40]!r} runs {past:.1f}pt past the "
                f"{side} edge of the {box}",
            )
            for kind, box, side, past in misses
            if past > EDGE_TOLERANCE
        )
    return findings


def _check_collisions(pdf_path: Path, markdown: str) -> list[Finding]:
    """Report headings crowding the line beneath them.

    The rule and its clearances belong to ``check_visual_relationships``, which
    every rendered document is verified against. This calls it rather than
    keeping a second copy that could drift from it.
    """
    result = check_visual_relationships("geometry", pdf_path, markdown)
    if result.severity.value != "fail":
        return []
    return [Finding("heading-collision", result.detail)]


def _check_stranded_heading(geometry: Geometry, markdown: str) -> list[Finding]:
    """Report a heading left alone at the bottom of a page."""
    headings = {text for _level, text in _headings(markdown)}
    findings: list[Finding] = []
    for page in range(1, geometry.pages):
        lines = geometry.page_lines(page)
        if lines and lines[-1].text.casefold() in headings:
            findings.append(
                Finding(
                    "stranded-heading",
                    f"page {page}: {lines[-1].text!r} is the last line on the page and its "
                    f"content starts on page {page + 1}",
                )
            )
    return findings


def _check_hierarchy(geometry: Geometry, markdown: str) -> list[Finding]:
    """Report headings that stopped outranking the text beneath them.

    Headings are matched by their exact text, which is why no fixture heading
    is allowed to wrap. A line that is only part of a heading is left out of
    the body rather than counted as one, so a wrap degrades this check instead
    of failing it falsely.
    """
    headings = _headings(markdown)
    by_level: dict[int, list[Line]] = {1: [], 2: [], 3: []}
    body: list[Line] = []
    for line in geometry.lines:
        text = line.text.casefold()
        level = next((level for level, heading in headings if heading == text), 0)
        if level:
            by_level[level].append(line)
        elif not any(text in heading for _level, heading in headings):
            body.append(line)

    findings: list[Finding] = []
    ranks = [("name", by_level[1]), ("section heading", by_level[2]), ("role heading", by_level[3])]
    present = [(label, group) for label, group in ranks if group] + [("body text", body)]
    for (upper, above), (lower, below) in pairwise(present):
        if not below:
            continue
        smallest = min(line.size for line in above)
        largest = max(line.size for line in below)
        if smallest <= largest:
            findings.append(
                Finding(
                    "hierarchy",
                    f"{upper} is {smallest:.1f}pt and {lower} is {largest:.1f}pt: "
                    f"{upper} no longer outranks {lower}",
                )
            )
    if body:
        body_weight = Counter(_weight_rank(line.font) for line in body).most_common(1)[0][0]
        for label, group in ranks:
            weak = [line for line in group if _weight_rank(line.font) <= body_weight]
            if weak:
                findings.append(
                    Finding(
                        "hierarchy",
                        f"{label} {weak[0].text[:40]!r} is set in {weak[0].font}, which is no "
                        f"heavier than the body text around it",
                    )
                )
    return findings


def _check_final_page(geometry: Geometry) -> list[Finding]:
    """Report a last page too empty to justify itself."""
    if geometry.pages < 2:
        return []
    lines = geometry.page_lines(geometry.pages)
    if not lines:
        return [Finding("blank-ending", f"page {geometry.pages} carries no text at all")]
    _left, bottom, _right, top = geometry.region
    used = max(line.top for line in lines) - min(line.bottom for line in lines)
    fill = used / (top - bottom)
    if fill < MINIMUM_FINAL_PAGE_FILL:
        return [
            Finding(
                "blank-ending",
                f"page {geometry.pages} uses {fill:.0%} of the text region "
                f"({len(lines)} line(s)); the page reads as an accident",
            )
        ]
    return []


def compare(recorded: Geometry, observed: Geometry) -> list[Finding]:
    """Report every material difference from the recorded geometry."""
    observed = normalize(observed)
    findings: list[Finding] = []
    if (recorded.width, recorded.height) != (observed.width, observed.height):
        findings.append(
            Finding(
                "paper",
                f"page size {recorded.width:.1f}x{recorded.height:.1f} -> "
                f"{observed.width:.1f}x{observed.height:.1f} pt",
            )
        )
    if recorded.region != observed.region:
        findings.append(
            Finding(
                "margins",
                "text region (left bottom right top) "
                f"{_box(recorded.region)} -> {_box(observed.region)} pt",
            )
        )
    if recorded.pages != observed.pages:
        # Once the page count moves, every line below the break has moved with
        # it, and a line-by-line diff would bury the one fact that matters.
        findings.append(
            Finding("page-count", f"{recorded.pages} page(s) recorded, {observed.pages} rendered")
        )
        return findings
    for page in range(1, recorded.pages + 1):
        findings.extend(_diff_page(page, recorded.page_lines(page), observed.page_lines(page)))
    return findings


def _box(region: tuple[float, float, float, float]) -> str:
    """Format a text region for a message."""
    return " ".join(f"{value:.1f}" for value in region)


def _diff_page(page: int, recorded: tuple[Line, ...], observed: tuple[Line, ...]) -> list[Finding]:
    """Diff one page's lines, aligning them by their text."""
    findings: list[Finding] = []
    matcher = SequenceMatcher(
        None, [line.text for line in recorded], [line.text for line in observed], autojunk=False
    )
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                findings.extend(
                    _diff_line(page, i1 + offset, recorded[i1 + offset], observed[j1 + offset])
                )
        elif tag == "delete":
            findings.append(
                Finding("content", f"page {page}: {_texts(recorded[i1:i2])} no longer rendered")
            )
        elif tag == "insert":
            findings.append(Finding("content", f"page {page}: {_texts(observed[j1:j2])} is new"))
        else:
            findings.append(
                Finding(
                    "content",
                    f"page {page}: {_texts(recorded[i1:i2])} replaced by {_texts(observed[j1:j2])}",
                )
            )
    return _cap(page, findings)


def _diff_line(page: int, index: int, recorded: Line, observed: Line) -> list[Finding]:
    """Report how far one line moved, and whether it changed typeface."""
    where = f"page {page} line {index + 1} {recorded.text[:40]!r}"
    findings: list[Finding] = []
    moves = [
        (label, before, after)
        for label, before, after in (
            ("top", recorded.top, observed.top),
            ("bottom", recorded.bottom, observed.bottom),
            ("left", recorded.left, observed.left),
            ("right", recorded.right, observed.right),
        )
        if before != after
    ]
    if moves:
        detail = ", ".join(
            f"{label} {before:.1f} -> {after:.1f} ({after - before:+.1f}pt)"
            for label, before, after in moves
        )
        findings.append(Finding("spacing", f"{where}: {detail}"))
    if recorded.size != observed.size:
        findings.append(
            Finding(
                "typography",
                f"{where}: size {recorded.size:.1f} -> {observed.size:.1f}pt "
                f"({observed.size - recorded.size:+.1f}pt)",
            )
        )
    if recorded.font != observed.font:
        findings.append(Finding("typography", f"{where}: font {recorded.font} -> {observed.font}"))
    return findings


def _texts(lines: tuple[Line, ...]) -> str:
    """Name a run of lines in a message without printing a whole page."""
    shown = ", ".join(repr(line.text[:40]) for line in lines[:3])
    return shown if len(lines) <= 3 else f"{shown} and {len(lines) - 3} more line(s)"


def _cap(page: int, findings: list[Finding]) -> list[Finding]:
    """Keep a failure message readable when a whole page has moved."""
    limit = 6
    if len(findings) <= limit:
        return findings
    return [
        *findings[:limit],
        Finding("spacing", f"page {page}: {len(findings) - limit} further difference(s) not shown"),
    ]


def _headings(markdown: str) -> list[tuple[int, str]]:
    """Return (level, casefolded text) for every Markdown heading.

    Section headings are uppercased by both document builders, so the
    comparison folds case rather than carrying a second copy of that rule.
    """
    return [
        (len(marker), text.strip().casefold())
        for marker, text in MARKDOWN_HEADING.findall(markdown)
    ]


# ---------------------------------------------------------------------------
# Renderer versions.
# ---------------------------------------------------------------------------


def running_renderers() -> dict[str, str]:
    """Return the Typst and Pandoc versions this process would render with."""
    return {"typst": version("typst"), "pandoc": str(pypandoc.get_pandoc_version())}


def recorded_renderers() -> dict[str, str]:
    """Return the versions the recorded baselines were produced with."""
    recorded: dict[str, str] = {}
    for raw in RENDERER_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            name, _, value = line.partition(" ")
            recorded[name] = value.strip()
    return recorded


def renderer_drift() -> str:
    """Return an explanation when the renderers differ from the recorded ones.

    An empty string means the baselines and the running renderers agree.
    """
    recorded, running = recorded_renderers(), running_renderers()
    moved = [
        f"{name} {recorded.get(name, 'unrecorded')} -> {running[name]}"
        for name in sorted(running)
        if recorded.get(name) != running[name]
    ]
    if not moved:
        return ""
    return (
        "the recorded baselines were produced by a different renderer ("
        + "; ".join(moved)
        + "). Layout is not comparable across renderer versions. Confirm the change "
        + "is only the upgrade, then run tests/regenerate_geometry_baselines.py."
    )
