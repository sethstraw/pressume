"""Curated typography systems for predictable resume rendering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """Resolved visual tokens for one coordinated resume design."""

    name: str
    font: str
    body_size_pt: float
    margin_in: float
    accent: str
    name_scale: float
    section_scale: float
    role_scale: float
    contact_scale: float
    metadata_scale: float
    citation_scale: float
    body_leading_em: float
    paragraph_spacing_em: float
    list_spacing_em: float
    section_above_em: float
    role_above_em: float


THEMES = {
    "modern": Theme(
        name="modern",
        font="Source Sans 3",
        body_size_pt=10.0,
        margin_in=0.55,
        accent="#22304A",
        name_scale=1.72,
        section_scale=1.02,
        role_scale=1.03,
        contact_scale=0.88,
        metadata_scale=0.94,
        citation_scale=0.94,
        body_leading_em=0.64,
        paragraph_spacing_em=0.66,
        list_spacing_em=0.50,
        section_above_em=1.15,
        role_above_em=0.95,
    ),
    "technical": Theme(
        name="technical",
        font="IBM Plex Sans",
        body_size_pt=10.0,
        margin_in=0.55,
        accent="#173B57",
        name_scale=1.68,
        section_scale=1.02,
        role_scale=1.03,
        contact_scale=0.88,
        metadata_scale=0.94,
        citation_scale=0.94,
        body_leading_em=0.64,
        paragraph_spacing_em=0.66,
        list_spacing_em=0.50,
        section_above_em=1.15,
        role_above_em=0.95,
    ),
    "traditional": Theme(
        name="traditional",
        font="Source Serif 4",
        body_size_pt=10.0,
        margin_in=0.5,
        accent="#22304A",
        name_scale=1.8,
        section_scale=1.05,
        role_scale=1.05,
        contact_scale=1.0,
        metadata_scale=1.0,
        citation_scale=1.0,
        body_leading_em=0.44,
        paragraph_spacing_em=0.52,
        list_spacing_em=0.44,
        section_above_em=1.05,
        role_above_em=0.8,
    ),
}

DENSITY_FACTORS = {
    "compact": 0.9,
    "balanced": 1.0,
    "spacious": 1.12,
}


def theme_names() -> tuple[str, ...]:
    """Return theme names in stable user-facing order."""
    return tuple(THEMES)


def resolve_theme(name: str) -> Theme:
    """Return a named theme; configuration validation guards unknown names."""
    return THEMES[name]
