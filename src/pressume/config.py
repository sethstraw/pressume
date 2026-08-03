"""Load and validate pressume's optional TOML configuration.

Configuration is an overlay on useful defaults. Validation is deliberately
strict and cumulative: misspellings and wrong types are reported together,
with dotted paths that point back to the offending setting.
"""

from __future__ import annotations

import re
import sys
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePath
from typing import cast

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

from pressume.checks.document import DocumentRules
from pressume.errors import PressumeError
from pressume.themes import DENSITY_FACTORS, theme_names

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
PAPER_NAME = re.compile(r"^[a-z0-9-]+$")
KNOWN_FORMATS = ("pdf", "txt", "docx")
DATE_STYLES = ("long", "short", "off")
PDF_STANDARDS = ("default", "ua-1", "a-2a", "a-2u")

TomlTable = dict[str, object]


class ConfigError(PressumeError):
    """Raised when configuration is missing or invalid."""

    def __init__(self, problems: list[str]) -> None:
        """Collect all independently actionable configuration problems."""
        self.problems = problems
        super().__init__("\n".join(problems))


@dataclass
class Style:
    """Visual settings shared by PDF and optional DOCX output."""

    theme: str = "modern"
    density: str = "balanced"
    font: str | None = None
    size_pt: float | None = None
    margin_in: float | None = None
    accent: str | None = None
    paper: str = "us-letter"
    language: str = "en"
    region: str = "US"
    pdf_standard: str = "ua-1"


@dataclass
class Document:
    """Configuration that applies to one Markdown document."""

    file: str
    pages: int | None = None
    min_pages: int | None = None
    max_pages: int | None = None
    profile: str | None = None
    lint_only: bool = False
    formats: list[str] | None = None
    output_name: str | None = None
    title: str = ""
    author: str = ""
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    required_strings: list[str] = field(default_factory=list)
    protected_strings: list[str] = field(default_factory=list)
    forbidden_strings: list[str] = field(default_factory=list)


@dataclass
class Checks:
    """Character, exact-text, contact, section, and date checks."""

    ascii_only: bool = True
    allowed_characters: list[str] = field(default_factory=lambda: ["\u2022"])
    forbid_smart_punctuation: bool = True
    required_strings: list[str] = field(default_factory=list)
    # A protected string is conditional: when its first word appears, the full
    # exact value must appear. This preserves titles without forcing every
    # tailored resume to contain every title in a portfolio.
    protected_strings: list[str] = field(default_factory=list)
    forbidden_strings: list[str] = field(default_factory=list)
    section_order: list[str] = field(default_factory=list)
    contact_name: str = ""
    contact_email: str = ""
    contact_phones: list[str] = field(default_factory=list)
    date_style: str = "long"


@dataclass
class Config:
    """Resolved behavior for one pressume invocation."""

    source_dir: Path = Path(".")
    output_dir: Path = Path("renders")
    font_dirs: list[Path] = field(default_factory=list)
    formats: list[str] = field(default_factory=lambda: ["pdf", "txt"])
    reference_docx: Path | None = None
    style: Style = field(default_factory=Style)
    documents: list[Document] = field(default_factory=list)
    checks: Checks = field(default_factory=Checks)
    document_rules: DocumentRules = field(default_factory=DocumentRules)
    profiles: dict[str, DocumentRules] = field(default_factory=dict)
    config_dir: Path = Path(".")

    def resolve(self, path: Path) -> Path:
        """Resolve a configured path relative to its configuration file."""
        expanded = path.expanduser()
        return (
            expanded.resolve() if expanded.is_absolute() else (self.config_dir / expanded).resolve()
        )

    def rules_for(self, document: Document) -> DocumentRules:
        """Return the document-contract profile governing ``document``."""
        if document.profile is None:
            return self.document_rules
        return self.profiles[document.profile]

    def checks_for(self, document: Document) -> Checks:
        """Return global checks plus exact-text rules scoped to ``document``."""
        return replace(
            self.checks,
            allowed_characters=list(self.checks.allowed_characters),
            required_strings=[*self.checks.required_strings, *document.required_strings],
            protected_strings=[*self.checks.protected_strings, *document.protected_strings],
            forbidden_strings=[*self.checks.forbidden_strings, *document.forbidden_strings],
            section_order=list(self.checks.section_order),
            contact_phones=list(self.checks.contact_phones),
        )


KNOWN_KEYS = {
    "": ("paths", "output", "style", "documents", "checks", "document", "profiles"),
    "paths": ("source_dir", "output_dir", "fonts", "reference_docx"),
    "output": ("formats",),
    "style": (
        "theme",
        "density",
        "font",
        "size_pt",
        "margin_in",
        "accent",
        "paper",
        "language",
        "region",
        "pdf_standard",
    ),
    "documents[]": (
        "file",
        "pages",
        "min_pages",
        "max_pages",
        "profile",
        "lint_only",
        "formats",
        "output_name",
        "title",
        "author",
        "description",
        "keywords",
        "required_strings",
        "protected_strings",
        "forbidden_strings",
    ),
    "checks": (
        "ascii_only",
        "forbid_smart_punctuation",
        "allowed_characters",
        "required_strings",
        "protected_strings",
        "forbidden_strings",
        "section_order",
        "contact_name",
        "contact_email",
        "contact_phones",
        "date_style",
    ),
    "rules": (
        "section_vocabulary",
        "required_sections",
        "labeled_sections",
        "subheading_sections",
        "ordered_list_sections",
        "dated_sections",
        "citation_field_labels",
        "max_heading_level",
        "contact_after_name",
        "policy",
        "warning_rules",
        "disabled_rules",
    ),
}

RULE_LIST_KEYS = (
    "section_vocabulary",
    "required_sections",
    "labeled_sections",
    "subheading_sections",
    "ordered_list_sections",
    "dated_sections",
    "citation_field_labels",
    "warning_rules",
    "disabled_rules",
)


def validate_formats(formats: list[str], where: str = "formats") -> list[str]:
    """Normalize an output-format list or raise a user-facing error."""
    normalized = [item.strip().lower() for item in formats if item.strip()]
    problems: list[str] = []
    if not normalized:
        problems.append(f"{where}: choose at least one format from {list(KNOWN_FORMATS)}")
    unknown = sorted(set(normalized) - set(KNOWN_FORMATS))
    if unknown:
        problems.append(f"{where}: unknown formats {unknown}; choose from {list(KNOWN_FORMATS)}")
    duplicates = sorted({item for item in normalized if normalized.count(item) > 1})
    if duplicates:
        problems.append(f"{where}: duplicate formats {duplicates}")
    if problems:
        raise ConfigError(problems)
    return normalized


def load_config(path: Path) -> Config:
    """Load and validate the TOML file at ``path``."""
    if not path.exists():
        raise ConfigError(
            [
                f"Configuration file not found: {path}",
                "Run `pressume init` to create a starter configuration.",
            ]
        )
    try:
        raw = cast(TomlTable, tomllib.loads(path.read_text(encoding="utf-8")))
    except tomllib.TOMLDecodeError as error:
        raise ConfigError([f"{path.name} is not valid TOML: {error}"]) from error
    except OSError as error:
        raise ConfigError([f"Could not read configuration {path}: {error}"]) from error

    problems: list[str] = []
    config = Config(config_dir=path.expanduser().resolve().parent)
    _reject_unknown(raw, "", "", problems)

    paths = _table(raw, "paths", problems)
    output = _table(raw, "output", problems)
    style = _table(raw, "style", problems)
    checks = _table(raw, "checks", problems)
    document_rules = _table(raw, "document", problems)
    profiles = _table(raw, "profiles", problems)
    for name, table in (("paths", paths), ("output", output), ("style", style), ("checks", checks)):
        _reject_unknown(table, name, name, problems)

    _parse_paths(paths, config, problems)
    _parse_output(output, config, problems)
    _parse_style(style, config.style, problems)
    _parse_documents(raw.get("documents", []), config, problems)
    _parse_checks(checks, config.checks, problems)
    config.document_rules = _parse_rules(document_rules, DocumentRules(), "document", problems)
    _parse_profiles(profiles, config, problems)
    _validate_document_references(config, problems)

    if problems:
        raise ConfigError([f"{path.name}: configuration is invalid", *problems])
    return config


def _table(parent: TomlTable, key: str, problems: list[str]) -> TomlTable:
    """Read an optional TOML table, reporting a wrong type once."""
    value = parent.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        problems.append(f"{key}: expected a table, got {type(value).__name__}")
        return {}
    return cast(TomlTable, value)


def _reject_unknown(table: TomlTable, group: str, where: str, problems: list[str]) -> None:
    """Reject keys that would otherwise become dangerous silent no-ops."""
    allowed = KNOWN_KEYS[group]
    for key in table:
        if key not in allowed:
            label = f"{where}.{key}" if where else key
            problems.append(f"{label}: unknown key; valid keys are {sorted(allowed)}")


def _string(table: TomlTable, key: str, where: str, problems: list[str]) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        problems.append(f"{where}.{key}: expected str, got {type(value).__name__}")
        return None
    if not value.strip():
        problems.append(f"{where}.{key}: must not be empty")
        return None
    return value


def _boolean(table: TomlTable, key: str, where: str, problems: list[str]) -> bool | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        problems.append(f"{where}.{key}: expected bool, got {type(value).__name__}")
        return None
    return value


def _integer(table: TomlTable, key: str, where: str, problems: list[str]) -> int | None:
    value = table.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append(f"{where}.{key}: expected int, got {type(value).__name__}")
        return None
    return value


def _number(table: TomlTable, key: str, where: str, problems: list[str]) -> float | None:
    value = table.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        problems.append(f"{where}.{key}: expected number, got {type(value).__name__}")
        return None
    return float(value)


def _strings(table: TomlTable, key: str, where: str, problems: list[str]) -> list[str] | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        problems.append(f"{where}.{key}: expected list, got {type(value).__name__}")
        return None
    if not all(isinstance(item, str) and item for item in value):
        problems.append(f"{where}.{key}: every entry must be a non-empty string")
        return None
    return cast(list[str], value)


def _parse_paths(table: TomlTable, config: Config, problems: list[str]) -> None:
    if value := _string(table, "source_dir", "paths", problems):
        config.source_dir = Path(value)
    if value := _string(table, "output_dir", "paths", problems):
        config.output_dir = Path(value)
    if values := _strings(table, "fonts", "paths", problems):
        config.font_dirs = [Path(value) for value in values]
    if value := _string(table, "reference_docx", "paths", problems):
        config.reference_docx = Path(value)


def _parse_output(table: TomlTable, config: Config, problems: list[str]) -> None:
    values = _strings(table, "formats", "output", problems)
    if values is None:
        return
    try:
        config.formats = validate_formats(values, "output.formats")
    except ConfigError as error:
        problems.extend(error.problems)


def _parse_style(table: TomlTable, style: Style, problems: list[str]) -> None:
    if theme := _string(table, "theme", "style", problems):
        normalized = theme.casefold()
        if normalized in theme_names():
            style.theme = normalized
        else:
            problems.append(f"style.theme: {theme!r} must be one of {list(theme_names())}")
    if density := _string(table, "density", "style", problems):
        normalized = density.casefold()
        if normalized in DENSITY_FACTORS:
            style.density = normalized
        else:
            problems.append(f"style.density: {density!r} must be one of {list(DENSITY_FACTORS)}")
    if font := _string(table, "font", "style", problems):
        style.font = font
    if (size := _number(table, "size_pt", "style", problems)) is not None:
        if 6 <= size <= 14:
            style.size_pt = size
        else:
            problems.append(f"style.size_pt: {size:g} is outside the sensible range 6-14")
    if (margin := _number(table, "margin_in", "style", problems)) is not None:
        if 0.3 <= margin <= 1.5:
            style.margin_in = margin
        else:
            problems.append(f"style.margin_in: {margin:g} is outside the sensible range 0.3-1.5")
    if accent := _string(table, "accent", "style", problems):
        if HEX_COLOR.fullmatch(accent):
            style.accent = accent
        else:
            problems.append(f"style.accent: {accent!r} is not a #RRGGBB hex color")
    if paper := _string(table, "paper", "style", problems):
        normalized = paper.lower()
        if PAPER_NAME.fullmatch(normalized):
            style.paper = normalized
        else:
            problems.append("style.paper: use a Typst paper name such as 'us-letter' or 'a4'")
    if language := _string(table, "language", "style", problems):
        if re.fullmatch(r"[a-z]{2,3}", language.casefold()):
            style.language = language.casefold()
        else:
            problems.append("style.language: use a two- or three-letter ISO 639 language code")
    if region := _string(table, "region", "style", problems):
        if re.fullmatch(r"[A-Za-z]{2}", region):
            style.region = region.upper()
        else:
            problems.append("style.region: use a two-letter ISO 3166-1 region code")
    if standard := _string(table, "pdf_standard", "style", problems):
        normalized = standard.casefold()
        if normalized in PDF_STANDARDS:
            style.pdf_standard = normalized
        else:
            problems.append(
                f"style.pdf_standard: {standard!r} must be one of {list(PDF_STANDARDS)}"
            )


def _parse_documents(value: object, config: Config, problems: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        problems.append("documents: expected an array of tables ([[documents]])")
        return
    for index, raw_entry in enumerate(value):
        where = f"documents[{index}]"
        if not isinstance(raw_entry, dict):
            problems.append(f"{where}: expected a table")
            continue
        entry = cast(TomlTable, raw_entry)
        _reject_unknown(entry, "documents[]", where, problems)
        filename = _string(entry, "file", where, problems)
        if filename is None:
            if "file" not in entry:
                problems.append(f"{where}.file: required Markdown path is missing")
            continue
        if not _is_safe_markdown_path(filename):
            problems.append(f"{where}.file: expected a relative Markdown path ending in .md")
            continue
        pages = _integer(entry, "pages", where, problems)
        if pages is not None and pages < 1:
            problems.append(f"{where}.pages: expected a positive integer page target")
            pages = None
        min_pages = _integer(entry, "min_pages", where, problems)
        max_pages = _integer(entry, "max_pages", where, problems)
        for key, value in (("min_pages", min_pages), ("max_pages", max_pages)):
            if value is not None and value < 1:
                problems.append(f"{where}.{key}: expected a positive integer")
        if pages is not None and (min_pages is not None or max_pages is not None):
            problems.append(f"{where}: pages cannot be combined with min_pages or max_pages")
        if min_pages is not None and max_pages is not None and min_pages > max_pages:
            problems.append(f"{where}: min_pages cannot exceed max_pages")
        profile = _string(entry, "profile", where, problems)
        lint_only = _boolean(entry, "lint_only", where, problems)
        output_name = _string(entry, "output_name", where, problems)
        if output_name is not None and not _is_safe_output_name(output_name):
            problems.append(f"{where}.output_name: use a filename stem without a path or extension")
            output_name = None
        format_values = _strings(entry, "formats", where, problems)
        formats: list[str] | None = None
        if format_values is not None:
            try:
                formats = validate_formats(format_values, f"{where}.formats")
            except ConfigError as error:
                problems.extend(error.problems)
        scoped: dict[str, list[str]] = {}
        for key in ("required_strings", "protected_strings", "forbidden_strings"):
            scoped[key] = _strings(entry, key, where, problems) or []
        config.documents.append(
            Document(
                file=filename,
                pages=pages,
                min_pages=min_pages,
                max_pages=max_pages,
                profile=profile,
                lint_only=lint_only or False,
                formats=formats,
                output_name=output_name,
                title=_string(entry, "title", where, problems) or "",
                author=_string(entry, "author", where, problems) or "",
                description=_string(entry, "description", where, problems) or "",
                keywords=_strings(entry, "keywords", where, problems) or [],
                required_strings=scoped["required_strings"],
                protected_strings=scoped["protected_strings"],
                forbidden_strings=scoped["forbidden_strings"],
            )
        )


def _parse_checks(table: TomlTable, checks: Checks, problems: list[str]) -> None:
    for key in ("ascii_only", "forbid_smart_punctuation"):
        if (value := _boolean(table, key, "checks", problems)) is not None:
            setattr(checks, key, value)
    for key in (
        "allowed_characters",
        "required_strings",
        "protected_strings",
        "forbidden_strings",
        "section_order",
        "contact_phones",
    ):
        if (values := _strings(table, key, "checks", problems)) is not None:
            setattr(checks, key, list(values))
    if any(len(value) != 1 for value in checks.allowed_characters):
        problems.append("checks.allowed_characters: every entry must be exactly one character")
    for key in ("contact_name", "contact_email", "date_style"):
        if (text := _string(table, key, "checks", problems)) is not None:
            setattr(checks, key, text)
    if checks.date_style not in DATE_STYLES:
        problems.append(
            f"checks.date_style: {checks.date_style!r} must be one of {list(DATE_STYLES)}"
        )
    overlap = set(checks.required_strings) & set(checks.forbidden_strings)
    if overlap:
        problems.append(f"checks: strings cannot be both required and forbidden: {sorted(overlap)}")


def _parse_rules(
    table: TomlTable, base: DocumentRules, where: str, problems: list[str]
) -> DocumentRules:
    _reject_unknown(table, "rules", where, problems)
    if policy := _string(table, "policy", where, problems):
        try:
            base.apply_policy(policy.casefold())
        except ValueError:
            problems.append(
                f"{where}.policy: {policy!r} must be one of {list(DocumentRules.policy_names())}"
            )
    for key in RULE_LIST_KEYS:
        if (values := _strings(table, key, where, problems)) is not None:
            setattr(base, key, list(values))
            folded = [item.casefold() for item in values]
            if len(folded) != len(set(folded)):
                problems.append(f"{where}.{key}: duplicate values are not allowed")
    if (value := _integer(table, "max_heading_level", where, problems)) is not None:
        if 2 <= value <= 6:
            base.max_heading_level = value
        else:
            problems.append(f"{where}.max_heading_level: {value} is outside 2-6")
    if (value := _boolean(table, "contact_after_name", where, problems)) is not None:
        base.contact_after_name = value

    vocabulary = {entry.casefold() for entry in base.section_vocabulary}
    if "dated_sections" not in table:
        base.dated_sections = [
            entry for entry in base.dated_sections if entry.casefold() in vocabulary
        ]
    for key in RULE_LIST_KEYS[1:6]:
        for entry in getattr(base, key):
            if entry.casefold() not in vocabulary:
                problems.append(f"{where}.{key}: {entry!r} is not in the section vocabulary")
    return base


def _parse_profiles(table: TomlTable, config: Config, problems: list[str]) -> None:
    for name, raw_profile in table.items():
        where = f"profiles.{name}"
        if not isinstance(raw_profile, dict):
            problems.append(f"{where}: expected a table")
            continue
        config.profiles[name] = _parse_rules(
            cast(TomlTable, raw_profile), deepcopy(config.document_rules), where, problems
        )


def _validate_document_references(config: Config, problems: list[str]) -> None:
    stems: dict[str, str] = {}
    files: set[str] = set()
    for index, document in enumerate(config.documents):
        if document.file in files:
            problems.append(f"documents[{index}].file: duplicate document {document.file!r}")
        files.add(document.file)
        stem = (document.output_name or Path(document.file).stem).casefold()
        if previous := stems.get(stem):
            problems.append(
                f"documents[{index}].file: output name collides with {previous!r}; "
                "document output names must be unique"
            )
        stems[stem] = document.file
        if document.profile is not None and document.profile not in config.profiles:
            problems.append(
                f"documents[{index}].profile: no [profiles.{document.profile}] table exists"
            )
        checks = config.checks_for(document)
        overlap = set(checks.required_strings) & set(checks.forbidden_strings)
        if overlap:
            problems.append(
                f"documents[{index}]: strings cannot be both required and forbidden: "
                f"{sorted(overlap)}"
            )


def _is_safe_markdown_path(value: str) -> bool:
    path = PurePath(value)
    return (
        path.suffix.casefold() == ".md"
        and not path.is_absolute()
        and ".." not in path.parts
        and path.name not in ("", ".", "..")
    )


def _is_safe_output_name(value: str) -> bool:
    path = PurePath(value)
    return (
        not path.is_absolute()
        and len(path.parts) == 1
        and path.suffix == ""
        and path.name not in ("", ".", "..")
        and re.fullmatch(r"[\w .()-]+", value, re.UNICODE) is not None
    )
