"""Typst document assembly and semantic resume styling."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pressume.config import Style
from pressume.metadata import DocumentMetadata
from pressume.themes import DENSITY_FACTORS, THEMES, Theme

# Pandoc 3 writes a bold paragraph as #strong[...]; earlier releases wrote *...*.
BOLD_LABEL = re.compile(r"^(\*[^*\n]+\*|#strong\[[^\]\n]+\])\s*\\?$")
THEMATIC_BREAK = re.compile(r"^-{3,}\s*$")
SECTION = re.compile(r"^==\s+(.+?)\s*$")
ROLE = re.compile(r"^===\s+(.+?)\s*$")
ANCHOR = re.compile(r"^<[^>]+>$")
# Pandoc writes a Markdown hard line break as a trailing backslash, so one
# paragraph can span several source lines.
CONTINUED = re.compile(r"\\\s*$")

RECORD_SECTIONS = {
    "education",
    "education and credentials",
    "education and licensure",
    "licensure",
    "licenses and certifications",
    "certifications",
    "training",
    "academic appointments",
    "professional organizations",
    "professional memberships",
    "affiliations",
    "honors and awards",
    "awards",
}
CITATION_WORDS = ("publication", "presentation", "writing", "patent", "grant")
SKILL_SECTIONS = {"core skills", "skills", "technical skills"}


@dataclass(frozen=True)
class ResolvedStyle:
    """Theme tokens after applying optional user overrides and density."""

    theme: Theme
    font: str
    size_pt: float
    margin_in: float
    accent: str
    paper: str
    density: float
    language: str
    region: str
    pdf_standard: str


def resolve_style(style: Style) -> ResolvedStyle:
    """Resolve a partial style overlay against a coordinated theme."""
    theme = THEMES[style.theme]
    return ResolvedStyle(
        theme=theme,
        font=style.font or theme.font,
        size_pt=style.size_pt if style.size_pt is not None else theme.body_size_pt,
        margin_in=style.margin_in if style.margin_in is not None else theme.margin_in,
        accent=style.accent or theme.accent,
        paper=style.paper,
        density=DENSITY_FACTORS[style.density],
        language=style.language,
        region=style.region,
        pdf_standard=style.pdf_standard,
    )


def strip_thematic_breaks(markdown: str) -> str:
    """Remove `---` separator lines; the theme supplies section separation."""
    lines = markdown.splitlines()
    kept = []
    for index, line in enumerate(lines):
        if THEMATIC_BREAK.match(line) and (index == 0 or lines[index - 1].strip() == ""):
            continue
        kept.append(line)
    return "\n".join(kept) + "\n"


def keep_labels_with_lists(typst_body: str) -> str:
    """Wrap bold label paragraphs in sticky blocks so they stay with their bullets."""
    lines = typst_body.splitlines()
    out: list[str] = []
    for index, line in enumerate(lines):
        label = BOLD_LABEL.match(line.strip())
        followed_by_list = False
        for later in lines[index + 1 :]:
            if later.strip() == "":
                continue
            followed_by_list = later.lstrip().startswith("- ")
            break
        if label and followed_by_list:
            out.append(f"#role-label[{label.group(1)}]")
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def keep_traditional_labels_with_lists(typst_body: str) -> str:
    """Apply proven sticky labels plus isolated publication treatment."""
    lines = typst_body.splitlines()
    output: list[str] = []
    current_section = ""
    for index, line in enumerate(lines):
        section = SECTION.match(line.strip())
        if section:
            current_section = section.group(1).casefold()
            output.append(line)
            continue
        followed_by_list = False
        for later in lines[index + 1 :]:
            if later.strip():
                followed_by_list = later.lstrip().startswith("- ")
                break
        label = BOLD_LABEL.match(line.strip())
        if label and followed_by_list:
            output.append(f"#block(sticky: true)[{label.group(1)}]")
        elif (
            line.strip()
            and not ANCHOR.match(line.strip())
            and any(word in current_section for word in CITATION_WORDS)
            and not line.lstrip().startswith(("- ", "+ "))
        ):
            output.append(f"#citation[{line}]")
        else:
            output.append(line)
    return "\n".join(output) + "\n"


def logical_paragraph(lines: list[str], start: int) -> tuple[str, int]:
    """Return the whole paragraph beginning at ``start`` and the index after it.

    A Markdown hard line break becomes a trailing backslash in Typst, which
    means a role header written across three lines arrives here as three source
    lines belonging to one paragraph. Anything that wraps content in a component
    has to take all of them or none: wrapping only the first puts that backslash
    immediately before the closing bracket, where it escapes the bracket instead
    of breaking the line and the document stops parsing.
    """
    collected = [lines[start]]
    index = start
    while (
        CONTINUED.search(lines[index])
        and index + 1 < len(lines)
        and lines[index + 1].strip()
        and not ANCHOR.match(lines[index + 1].strip())
    ):
        index += 1
        collected.append(lines[index])
    return "\n".join(collected), index + 1


def wrap(component: str, content: str) -> str:
    """Wrap content in a Typst component, without a dangling escape at the end.

    A trailing backslash is a line break with nothing after it, so it is dropped
    rather than left to escape the closing bracket.
    """
    return f"#{component}[{content.rstrip().rstrip(chr(92)).rstrip()}]"


def apply_semantic_blocks(typst_body: str, letter: bool = False) -> str:
    """Map conventional resume structures to purpose-built Typst components.

    A letter keeps its contact paragraph and leaves the prose after it as
    ordinary paragraphs.
    """
    lines = typst_body.splitlines()
    output: list[str] = []
    current_section = ""
    front_paragraph = 0
    role_pending = False
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        section = SECTION.match(stripped)
        role = ROLE.match(stripped)
        if section:
            current_section = section.group(1).casefold()
            role_pending = False
            output.append(line)
            index += 1
            continue
        if role:
            role_pending = True
            output.append(line)
            index += 1
            continue
        if not stripped or ANCHOR.match(stripped) or stripped.startswith("= "):
            output.append(line)
            index += 1
            continue

        paragraph, index = logical_paragraph(lines, index)
        if not current_section:
            if letter and front_paragraph:
                output.append(paragraph)
            else:
                component = "contact" if front_paragraph == 0 else "logistics"
                output.append(wrap(component, paragraph))
            front_paragraph += 1
            continue
        if role_pending:
            output.append(wrap("role-meta", paragraph))
            role_pending = False
            continue
        if current_section in SKILL_SECTIONS and not stripped.startswith(("- ", "+ ")):
            output.append(wrap("skill-line", paragraph))
            continue
        if any(word in current_section for word in CITATION_WORDS):
            if stripped.startswith(("- ", "+ ")):
                output.append(paragraph)
            else:
                output.append(wrap("citation", paragraph))
            continue
        if current_section in RECORD_SECTIONS and not stripped.startswith(("- ", "+ ")):
            output.append(wrap("record", paragraph))
            continue
        output.append(paragraph)
    return keep_labels_with_lists("\n".join(output))


def build_document(
    typst_body: str, style: Style, metadata: DocumentMetadata, letter: bool = False
) -> str:
    """Return a complete, metadata-rich Typst document."""
    resolved = resolve_style(style)
    theme = resolved.theme
    letter_gap = 1.3 * resolved.density
    # Follows the theme's own paragraph rule, which it overrides.
    letter_rules = f"#set par(spacing: {letter_gap:.3f}em)\n\n" if letter else ""
    if theme.name == "traditional":
        return _build_traditional_document(typst_body, resolved, metadata, letter_rules)
    accent = resolved.accent.lstrip("#")
    paper = json.dumps(resolved.paper, ensure_ascii=True)
    font = json.dumps(resolved.font, ensure_ascii=True)
    author = json.dumps(metadata.author, ensure_ascii=True)
    keywords = _typst_string_tuple(metadata.keywords)
    language = json.dumps(metadata.language, ensure_ascii=True)
    region = json.dumps(metadata.region or resolved.region, ensure_ascii=True)
    density = resolved.density
    # A block's own spacing below it outweighs the paragraph rule that follows.
    contact_below = letter_gap if letter else 0.16 * density

    preamble = f"""\
// Generated by pressume. Content remains in Markdown; design tokens live here.
#set document(
  title: [{_typst_text(metadata.title)}],
  author: ({author},),
  description: [{_typst_text(metadata.description)}],
  keywords: {keywords},
  date: none,
)
#let accent = rgb("{accent}")
#let ink = rgb("1a1a1a")
#let muted = rgb("50545a")

#set page(paper: {paper}, margin: {resolved.margin_in}in)
#set text(
  font: {font},
  size: {resolved.size_pt}pt,
  fill: ink,
  lang: {language},
  region: {region},
  fallback: false,
)
#set par(
  leading: {theme.body_leading_em * density:.3f}em,
  spacing: {theme.paragraph_spacing_em * density:.3f}em,
  justify: false,
)
#set list(
  indent: 0em,
  body-indent: 0.56em,
  spacing: {theme.list_spacing_em * density:.3f}em,
  marker: text(fill: accent)[\\u{{2022}}],
)

#let contact(body) = block(above: 0em, below: {contact_below:.3f}em)[
  #set par(leading: {0.48 * density:.3f}em, spacing: 0em)
  #text(size: {theme.contact_scale:.3f}em, fill: muted)[#body]
]
#let logistics(body) = block(above: 0em, below: {0.46 * density:.3f}em)[
  #set par(leading: {0.48 * density:.3f}em, spacing: 0em)
  #text(size: {theme.contact_scale:.3f}em, fill: muted)[#body]
]
#let role-meta(body) = block(above: 0em, below: {0.40 * density:.3f}em)[
  #set par(leading: {0.60 * density:.3f}em, spacing: 0em)
  #text(size: {theme.metadata_scale:.3f}em)[#body]
]
#let role-label(body) = block(
  sticky: true,
  above: {0.26 * density:.3f}em,
  below: {0.14 * density:.3f}em,
)[
  #text(weight: "semibold")[#body]
]
#let skill-line(body) = block(above: 0em, below: {0.44 * density:.3f}em)[
  #set par(leading: {theme.body_leading_em * density:.3f}em, spacing: 0em)
  #body
]
#let citation(body) = block(
  above: {0.04 * density:.3f}em,
  below: {0.34 * density:.3f}em,
  inset: (left: 0.65em),
  stroke: (left: 0.7pt + accent),
)[
  #set par(
    leading: {0.48 * density:.3f}em,
    spacing: 0em,
    hanging-indent: 0.9em,
  )
  #text(size: {theme.citation_scale:.3f}em)[#body]
]
#let record(body) = block(above: 0em, below: {0.56 * density:.3f}em)[
  #set par(leading: {0.42 * density:.3f}em, spacing: 0em)
  #text(size: 0.96em)[#body]
]

// Links retain their visible text and expose a real PDF destination.
#show link: it => it

// Name.
#show heading.where(level: 1): it => block(sticky: true, above: 0em, below: {1.35 * density:.3f}em)[
  #text(size: {theme.name_scale:.3f}em, weight: "semibold", fill: accent)[#it.body]
]

// Section headings.
#show heading.where(level: 2): it => block(
  sticky: true,
  above: {theme.section_above_em * density:.3f}em,
  below: {0.36 * density:.3f}em,
)[
  #text(
    size: {theme.section_scale:.3f}em,
    weight: "semibold",
    fill: accent,
    tracking: 0.045em,
  )[#upper(it.body)]
  #v(-0.44em)
  #pdf.artifact(line(length: 100%, stroke: 0.55pt + accent))
]

// Employer or role headings.
#show heading.where(level: 3): it => block(
  sticky: true,
  above: {theme.role_above_em * density:.3f}em,
  below: {0.80 * density:.3f}em,
)[
  #text(size: {theme.role_scale:.3f}em, weight: "semibold")[#it.body]
]

#let horizontalrule = none

"""
    return preamble + letter_rules + apply_semantic_blocks(typst_body, letter)


def _build_traditional_document(
    typst_body: str,
    style: ResolvedStyle,
    metadata: DocumentMetadata,
    letter_rules: str,
) -> str:
    """Preserve the established 3/3/2 line boxes with modern delivery metadata.

    This compatibility theme intentionally does not wrap ordinary paragraphs in
    semantic blocks. Its metrics are the visual baseline for existing resume
    portfolios whose page targets and flow are already approved.
    """
    accent = style.accent.lstrip("#")
    paper = json.dumps(style.paper, ensure_ascii=True)
    font = json.dumps(style.font, ensure_ascii=True)
    author = json.dumps(metadata.author, ensure_ascii=True)
    keywords = _typst_string_tuple(metadata.keywords)
    language = json.dumps(metadata.language, ensure_ascii=True)
    region = json.dumps(metadata.region or style.region, ensure_ascii=True)
    density = style.density
    vertical_margin = max(0.25, style.margin_in - 0.04)
    preamble = f"""\
// Generated by pressume. Traditional preserves its established layout metrics.
#set document(
  title: [{_typst_text(metadata.title)}],
  author: ({author},),
  description: [{_typst_text(metadata.description)}],
  keywords: {keywords},
  date: none,
)
#let accent = rgb("{accent}")
#let ink = rgb("1a1a1a")

#set page(
  paper: {paper},
  margin: (x: {style.margin_in}in, y: {vertical_margin}in),
)
#set text(
  font: {font},
  size: {style.size_pt}pt,
  fill: ink,
  lang: {language},
  region: {region},
  fallback: false,
)
#set par(leading: {0.44 * density:.3f}em, spacing: {0.52 * density:.3f}em, justify: false)
#set list(
  indent: 0em,
  body-indent: 0.5em,
  spacing: {0.44 * density:.3f}em,
  marker: text(fill: accent)[\\u{{2022}}],
)

#show link: it => it

#let citation(body) = block(
  above: 0em,
  below: {0.28 * density:.3f}em,
  inset: (left: 0.65em),
  stroke: (left: 0.7pt + accent),
)[
  #set par(leading: {0.44 * density:.3f}em, spacing: 0em)
  #body
]

#show heading.where(level: 1): it => block(
  sticky: true,
  above: 0em,
  below: {1.35 * density:.3f}em,
)[
  #text(size: 1.8em, weight: "bold", fill: accent)[#it.body]
]

#show heading.where(level: 2): it => block(
  sticky: true,
  above: {0.65 * density:.3f}em,
  below: {0.35 * density:.3f}em,
)[
  #text(size: 1.05em, weight: "bold", fill: accent, tracking: 0.05em)[#upper(it.body)]
  #v(-0.5em)
  #pdf.artifact(line(length: 100%, stroke: 0.6pt + accent))
]

#show heading.where(level: 3): it => block(
  sticky: true,
  above: {0.8 * density:.3f}em,
  below: {0.30 * density:.3f}em,
)[
  #text(size: 1.05em, weight: "bold")[#it.body]
  #v({0.65 * density:.3f}em)
]

#let horizontalrule = none

"""
    return preamble + letter_rules + keep_traditional_labels_with_lists(typst_body)


def _typst_text(value: str) -> str:
    """Escape plain metadata for insertion into Typst content brackets."""
    return value.replace("\\", "\\\\").replace("#", "\\#").replace("[", "\\[").replace("]", "\\]")


def _typst_string_tuple(values: tuple[str, ...]) -> str:
    """Return a Typst tuple of JSON-escaped strings."""
    if not values:
        return "()"
    return "(" + ", ".join(json.dumps(value, ensure_ascii=True) for value in values) + ",)"
