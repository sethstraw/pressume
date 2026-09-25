"""The unit of work shared by rendering, verification, and format strategies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pressume.config import Config, Document
from pressume.metadata import DocumentMetadata, derive_metadata


@dataclass(frozen=True)
class SourceDocument:
    """A selected document and the source read for this invocation."""

    settings: Document
    path: Path
    markdown: str

    @property
    def stem(self) -> str:
        """Return the collision-checked basename used for output files."""
        return self.settings.output_name or self.path.stem

    def is_letter(self, config: Config) -> bool:
        """Return whether the letter policy governs this document."""
        return config.rules_for(self.settings).policy == "letter"

    def metadata(self, config: Config) -> DocumentMetadata:
        """Return metadata derived for this document and style locale."""
        return derive_metadata(
            self.markdown,
            self.settings,
            config.style.language,
            config.style.region,
            letter=self.is_letter(config),
        )
