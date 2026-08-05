"""Load and validate pressume's optional TOML configuration.

Configuration is an overlay on useful defaults. Validation is deliberately
strict and cumulative: misspellings and wrong types are reported together,
with dotted paths that point back to the offending setting.

Every setting is described once, in the ``Setting`` tables below. Those tables
are what rejects an unknown key, what checks a type, a range, or a permitted
value, and what the starter configuration is tested against, so a new setting
is added in one place rather than four.
"""

from __future__ import annotations

import re
import sys
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePath
from typing import Any, cast

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib

from pressume.checks.document import DocumentRules
from pressume.errors import PressumeError
from pressume.themes import DENSITY_FACTORS, THEMES

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
LANGUAGE_CODE = re.compile(r"[a-z]{2,3}")
REGION_CODE = re.compile(r"[A-Z]{2}")
KNOWN_FORMATS = ("pdf", "txt", "docx")
DATE_STYLES = ("long", "short", "off")
# PDF/A is not offered. Every PDF/A level Typst emits requires a document
# date, and pressume writes `date: none` so two renders of one source are
# byte-comparable and no build timestamp travels with the file.
PDF_STANDARDS = ("default", "ua-1")

# Page size in inches. The Typst page and the Word deliverable are both set
# from this table, so every paper pressume accepts is one both can produce.
PAPER_SIZES = {
    "us-letter": (8.5, 11.0),
    "a4": (8.27, 11.69),
}

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


@dataclass(frozen=True)
class Setting:
    """One configurable value: its name, its type, and what it will accept.

    ``kind`` names the TOML type. ``target`` is the attribute the value lands
    on when it differs from the key. ``requirement`` completes the sentence
    "``key``: ``value`` ..." when a value is the right type but unacceptable.
    """

    name: str
    kind: str
    target: str = ""
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    pattern: re.Pattern[str] | None = None
    requirement: str = ""
    fold: str = ""

    @property
    def attribute(self) -> str:
        """Return the attribute this setting is stored under."""
        return self.target or self.name


def _settings(*items: Setting) -> dict[str, Setting]:
    """Index settings by their configuration key."""
    return {item.name: item for item in items}


TOP_LEVEL_KEYS = ("paths", "output", "style", "documents", "checks", "document", "profiles")

PATH_SETTINGS = _settings(
    Setting("source_dir", "path"),
    Setting("output_dir", "path"),
    Setting("fonts", "paths", target="font_dirs"),
    Setting("reference_docx", "path"),
)

OUTPUT_SETTINGS = _settings(Setting("formats", "strings"))

STYLE_SETTINGS = _settings(
    Setting("theme", "str", choices=tuple(THEMES), fold="casefold"),
    Setting("density", "str", choices=tuple(DENSITY_FACTORS), fold="casefold"),
    Setting("font", "str"),
    Setting("size_pt", "number", minimum=6, maximum=14),
    Setting("margin_in", "number", minimum=0.3, maximum=1.5),
    Setting("accent", "str", pattern=HEX_COLOR, requirement="is not a #RRGGBB hex color"),
    Setting("paper", "str", choices=tuple(PAPER_SIZES), fold="casefold"),
    Setting(
        "language",
        "str",
        pattern=LANGUAGE_CODE,
        fold="casefold",
        requirement="is not a two- or three-letter ISO 639 language code",
    ),
    Setting(
        "region",
        "str",
        pattern=REGION_CODE,
        fold="upper",
        requirement="is not a two-letter ISO 3166-1 region code",
    ),
    Setting("pdf_standard", "str", choices=PDF_STANDARDS, fold="casefold"),
)

DOCUMENT_SETTINGS = _settings(
    Setting("file", "str"),
    Setting("pages", "int", minimum=1, requirement="is not a positive integer page target"),
    Setting("min_pages", "int", minimum=1, requirement="is not a positive integer"),
    Setting("max_pages", "int", minimum=1, requirement="is not a positive integer"),
    Setting("profile", "str"),
    Setting("lint_only", "bool"),
    Setting("formats", "strings"),
    Setting("output_name", "str"),
    Setting("title", "str"),
    Setting("author", "str"),
    Setting("description", "str"),
    Setting("keywords", "strings"),
    Setting("required_strings", "strings"),
    Setting("protected_strings", "strings"),
    Setting("forbidden_strings", "strings"),
)

CHECK_SETTINGS = _settings(
    Setting("ascii_only", "bool"),
    Setting("forbid_smart_punctuation", "bool"),
    Setting("allowed_characters", "strings"),
    Setting("required_strings", "strings"),
    Setting("protected_strings", "strings"),
    Setting("forbidden_strings", "strings"),
    Setting("section_order", "strings"),
    Setting("contact_name", "str"),
    Setting("contact_email", "str"),
    Setting("contact_phones", "strings"),
    Setting("date_style", "str", choices=DATE_STYLES),
)

POLICY_SETTING = Setting("policy", "str", choices=DocumentRules.policy_names(), fold="casefold")

RULE_SETTINGS = _settings(
    Setting("section_vocabulary", "strings"),
    Setting("required_sections", "strings"),
    Setting("labeled_sections", "strings"),
    Setting("subheading_sections", "strings"),
    Setting("ordered_list_sections", "strings"),
    Setting("dated_sections", "strings"),
    Setting("citation_field_labels", "strings"),
    Setting("max_heading_level", "int", minimum=2, maximum=6),
    Setting("contact_after_name", "bool"),
    Setting("warning_rules", "strings"),
    Setting("disabled_rules", "strings"),
)

RULE_KEYS = (POLICY_SETTING.name, *RULE_SETTINGS)

# Rule lists whose entries must name a section the vocabulary declares.
SCOPED_RULE_LISTS = (
    "required_sections",
    "labeled_sections",
    "subheading_sections",
    "ordered_list_sections",
    "dated_sections",
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
    _reject_unknown(raw, TOP_LEVEL_KEYS, "", problems)

    paths = _table(raw, "paths", problems)
    output = _table(raw, "output", problems)
    style = _table(raw, "style", problems)
    checks = _table(raw, "checks", problems)
    document_rules = _table(raw, "document", problems)
    profiles = _table(raw, "profiles", problems)
    for name, table, known in (
        ("paths", paths, PATH_SETTINGS),
        ("output", output, OUTPUT_SETTINGS),
        ("style", style, STYLE_SETTINGS),
        ("checks", checks, CHECK_SETTINGS),
    ):
        _reject_unknown(table, tuple(known), name, problems)

    _apply(paths, PATH_SETTINGS, "paths", config, problems)
    _parse_output(output, config, problems)
    _apply(style, STYLE_SETTINGS, "style", config.style, problems)
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


def _reject_unknown(
    table: TomlTable, allowed: tuple[str, ...], where: str, problems: list[str]
) -> None:
    """Reject keys that would otherwise become dangerous silent no-ops."""
    for key in table:
        if key not in allowed:
            label = f"{where}.{key}" if where else key
            problems.append(f"{label}: unknown key; valid keys are {sorted(allowed)}")


def _show(value: object) -> str:
    """Render a value for an error message the way a user wrote it."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g}"
    return repr(value)


def _read(table: TomlTable, setting: Setting, where: str, problems: list[str]) -> Any:
    """Return one validated value, or None when it is absent or rejected."""
    value = table.get(setting.name)
    if value is None:
        return None
    label = f"{where}.{setting.name}" if where else setting.name

    if setting.kind == "bool":
        if not isinstance(value, bool):
            problems.append(f"{label}: expected bool, got {type(value).__name__}")
            return None
        return value

    if setting.kind in ("strings", "paths"):
        if not isinstance(value, list):
            problems.append(f"{label}: expected list, got {type(value).__name__}")
            return None
        if not all(isinstance(item, str) and item for item in value):
            problems.append(f"{label}: every entry must be a non-empty string")
            return None
        entries = cast(list[str], value)
        return [Path(entry) for entry in entries] if setting.kind == "paths" else list(entries)

    if setting.kind in ("int", "number"):
        return _read_number(value, setting, label, problems)
    return _read_text(value, setting, label, problems)


def _read_number(value: object, setting: Setting, label: str, problems: list[str]) -> Any:
    """Validate an integer or a real number against its permitted range."""
    if setting.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{label}: expected int, got {type(value).__name__}")
            return None
        number: float = value
    else:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"{label}: expected number, got {type(value).__name__}")
            return None
        number = float(value)
    below = setting.minimum is not None and number < setting.minimum
    above = setting.maximum is not None and number > setting.maximum
    if below or above:
        problems.append(f"{label}: {_show(number)} {_range_requirement(setting)}")
        return None
    return value if setting.kind == "int" else number


def _range_requirement(setting: Setting) -> str:
    """Say what an out-of-range number should have been."""
    if setting.requirement:
        return setting.requirement
    low = "" if setting.minimum is None else f"{setting.minimum:g}"
    high = "" if setting.maximum is None else f"{setting.maximum:g}"
    return f"is outside the sensible range {low}-{high}"


def _read_text(value: object, setting: Setting, label: str, problems: list[str]) -> Any:
    """Validate a string against emptiness, permitted values, and shape."""
    if not isinstance(value, str):
        problems.append(f"{label}: expected str, got {type(value).__name__}")
        return None
    if not value.strip():
        problems.append(f"{label}: must not be empty")
        return None
    text = value.casefold() if setting.fold == "casefold" else value
    text = text.upper() if setting.fold == "upper" else text
    if setting.choices and text not in setting.choices:
        problems.append(f"{label}: {value!r} must be one of {list(setting.choices)}")
        return None
    if setting.pattern is not None and not setting.pattern.fullmatch(text):
        problems.append(f"{label}: {value!r} {setting.requirement}")
        return None
    return Path(text) if setting.kind == "path" else text


def _apply(
    table: TomlTable,
    settings: dict[str, Setting],
    where: str,
    target: object,
    problems: list[str],
) -> None:
    """Store every present, valid setting on ``target``."""
    for setting in settings.values():
        value = _read(table, setting, where, problems)
        if value is not None:
            setattr(target, setting.attribute, value)


def _parse_output(table: TomlTable, config: Config, problems: list[str]) -> None:
    values = _read(table, OUTPUT_SETTINGS["formats"], "output", problems)
    if values is None:
        return
    try:
        config.formats = validate_formats(values, "output.formats")
    except ConfigError as error:
        problems.extend(error.problems)


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
        _reject_unknown(entry, tuple(DOCUMENT_SETTINGS), where, problems)
        document = _document(entry, where, problems)
        if document is not None:
            config.documents.append(document)


def _document(entry: TomlTable, where: str, problems: list[str]) -> Document | None:
    """Build one document entry, reporting everything wrong with it."""
    values: dict[str, Any] = {}
    for setting in DOCUMENT_SETTINGS.values():
        value = _read(entry, setting, where, problems)
        if value is not None:
            values[setting.name] = value

    filename = values.get("file")
    if filename is None:
        if "file" not in entry:
            problems.append(f"{where}.file: required Markdown path is missing")
        return None
    if not _is_safe_markdown_path(filename):
        problems.append(f"{where}.file: expected a relative Markdown path ending in .md")
        return None

    if "output_name" in values and not _is_safe_output_name(values["output_name"]):
        problems.append(f"{where}.output_name: use a filename stem without a path or extension")
        del values["output_name"]

    if "formats" in values:
        try:
            values["formats"] = validate_formats(values["formats"], f"{where}.formats")
        except ConfigError as error:
            problems.extend(error.problems)
            del values["formats"]

    pages, minimum, maximum = (values.get(key) for key in ("pages", "min_pages", "max_pages"))
    if pages is not None and (minimum is not None or maximum is not None):
        problems.append(f"{where}: pages cannot be combined with min_pages or max_pages")
    if minimum is not None and maximum is not None and minimum > maximum:
        problems.append(f"{where}: min_pages cannot exceed max_pages")
    return Document(**values)


def _parse_checks(table: TomlTable, checks: Checks, problems: list[str]) -> None:
    _apply(table, CHECK_SETTINGS, "checks", checks, problems)
    if any(len(value) != 1 for value in checks.allowed_characters):
        problems.append("checks.allowed_characters: every entry must be exactly one character")
    overlap = set(checks.required_strings) & set(checks.forbidden_strings)
    if overlap:
        problems.append(f"checks: strings cannot be both required and forbidden: {sorted(overlap)}")


def _parse_rules(
    table: TomlTable, base: DocumentRules, where: str, problems: list[str]
) -> DocumentRules:
    _reject_unknown(table, RULE_KEYS, where, problems)
    # A policy is a preset, so it lands before the explicit overrides that are
    # meant to refine it.
    if policy := _read(table, POLICY_SETTING, where, problems):
        base.apply_policy(policy)
    for key, setting in RULE_SETTINGS.items():
        value = _read(table, setting, where, problems)
        if value is None:
            continue
        if setting.kind == "strings":
            folded = [item.casefold() for item in value]
            if len(folded) != len(set(folded)):
                problems.append(f"{where}.{key}: duplicate values are not allowed")
        setattr(base, setting.attribute, value)

    vocabulary = {entry.casefold() for entry in base.section_vocabulary}
    if "dated_sections" not in table:
        base.dated_sections = [
            entry for entry in base.dated_sections if entry.casefold() in vocabulary
        ]
    for key in SCOPED_RULE_LISTS:
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
