"""Add real link destinations without changing visible resume text."""

from __future__ import annotations

import re

EMAIL = re.compile(r"(?<![\w.\[])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w\]])")
BARE_PROFILE = re.compile(
    r"(?<![\w/(])((?:www\.)?(?:linkedin\.com|github\.com|orcid\.org)/[^\s|,)]+)"
)
DOI = re.compile(r"(?i)\bdoi:(10\.\d{4,9}/[-._;()/:A-Z0-9]+)(?=\s|$)")
# Slashes and hyphens at either boundary exclude numeric identifiers such as an
# ORCID. Without those guards, a profile URL in the contact block can acquire a
# nested ``tel:`` link even though it is not a telephone number.
PHONE = re.compile(r"(?<![\w/.\[-])\+?\d[\d ().-]{6,}\d(?![\w/\]-])")
EXPLICIT_LINK = re.compile(r"\[[^]]+\]\([^)]+\)")


def linkify_markdown(markdown: str) -> str:
    """Create mail, phone, profile, and DOI links while preserving display text.

    Explicit Markdown links are respected as authored. Automatic phone links are
    limited to the front matter so dates and quantities elsewhere are untouched.
    """
    lines = markdown.splitlines()
    first_section = next(
        (index for index, line in enumerate(lines) if line.startswith("## ")), len(lines)
    )
    linked: list[str] = []
    for index, line in enumerate(lines):
        if EXPLICIT_LINK.search(line):
            linked.append(line)
            continue
        updated = EMAIL.sub(lambda match: f"[{match.group(1)}](mailto:{match.group(1)})", line)
        updated = BARE_PROFILE.sub(
            lambda match: f"[{match.group(1)}](https://{match.group(1).removeprefix('www.')})",
            updated,
        )
        updated = DOI.sub(_doi_link, updated)
        if index < first_section:
            updated = PHONE.sub(_phone_link, updated)
        linked.append(updated)
    suffix = "\n" if markdown.endswith("\n") else ""
    return "\n".join(linked) + suffix


def _phone_link(match: re.Match[str]) -> str:
    display = match.group(0)
    destination = re.sub(r"\D", "", display)
    if display.startswith("+"):
        destination = "+" + destination
    return f"[{display}](tel:{destination})"


def _doi_link(match: re.Match[str]) -> str:
    captured = match.group(1)
    doi = captured.rstrip(".,;")
    punctuation = captured[len(doi) :]
    return f"[doi:{doi}](https://doi.org/{doi}){punctuation}"
