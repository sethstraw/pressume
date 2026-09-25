"""Derive portable document metadata from Markdown and optional overrides."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pressume.config import Document

H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
MARKUP = re.compile(r"[*_`]+")


@dataclass(frozen=True)
class DocumentMetadata:
    """Metadata embedded into PDF and DOCX deliverables."""

    title: str
    author: str
    description: str
    keywords: tuple[str, ...]
    language: str
    region: str | None


def derive_metadata(
    markdown: str, document: Document, language: str, region: str, letter: bool = False
) -> DocumentMetadata:
    """Combine document overrides with safe values derived from its H1 and profile."""
    match = H1.search(markdown)
    derived_author = MARKUP.sub("", match.group(1)).strip() if match else ""
    author = document.author or derived_author
    if letter:
        kind = "Letter"
    elif document.profile == "cv" or "cv" in document.file.casefold():
        kind = "CV"
    else:
        kind = "Resume"
    title = document.title or (f"{author} - {kind}" if author else kind)
    description = document.description or f"Professional {kind.lower()} for {author}".strip()
    return DocumentMetadata(
        title=title,
        author=author,
        description=description,
        keywords=tuple(document.keywords),
        language=language,
        region=region or None,
    )
