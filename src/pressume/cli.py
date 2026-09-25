"""Command-line interface for pressume.

Reports go to stdout; progress and errors go to stderr. JSON mode emits only
machine-readable report data on stdout. Stable exit codes make every command
safe to use in scripts and continuous integration.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
import webbrowser
from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path

from rich.console import Console
from rich.table import Table

from pressume import __version__
from pressume.config import Config, ConfigError, load_config, validate_formats
from pressume.errors import PressumeError

DEFAULT_CONFIG = Path("pressume.toml")
NEW_FILENAMES = {"resume": "Resume.md", "cv": "CV.md", "letter": "Letter.md"}

EXIT_OK = 0
EXIT_VERIFICATION_FAILED = 1
EXIT_CONFIG_ERROR = 2
EXIT_RUNTIME_ERROR = 3
EXIT_INTERRUPTED = 130

EPILOG = """\
exit codes:
  0  success, all checks passed
  1  verification failed; existing deliverables remain unchanged
  2  command or configuration error
  3  rendering or file-system error

examples:
  pressume new resume && pressume render
  pressume render --source ~/documents/resumes --output ~/Desktop/renders
  pressume render Resume.md --formats pdf
  pressume preview Resume.md --watch
  pressume inspect
  pressume list
  pressume lint
  pressume check --json

Without configuration, sources are read from the current folder and output
lands in ./renders. Use --source and --output for one invocation, or persist
project-specific behavior in pressume.toml with `pressume init`.
"""

STARTER_CONFIG = """\
# Optional pressume configuration. Relative paths resolve from this file.
# Delete any setting you do not need; pressume's defaults remain active.

[paths]
source_dir = "."
output_dir = "renders"
# fonts = ["fonts"]
# reference_docx = "reference.docx"

[output]
formats = ["pdf", "txt"]

[style]
theme = "modern"          # modern, technical, or traditional
density = "balanced"      # compact, balanced, or spacious
paper = "us-letter"       # us-letter or a4
language = "en"
region = "US"
pdf_standard = "ua-1"     # accessible PDF/UA; use "default" if a portal rejects it
# font = "Source Sans 3"  # optional theme override
# size_pt = 10
# margin_in = 0.55
# accent = "#22304A"

[[documents]]
file = "Resume.md"
pages = 1
# min_pages = 1            # use a range instead of pages
# max_pages = 2
# profile = "cv"           # a [profiles.NAME] contract for this document
# lint_only = false        # true to check the source without rendering it
# output_name = "Your_Name_Resume"
# title = "Your Name - Resume"
# author = "Your Name"
# description = "Professional resume"
# keywords = ["data", "healthcare"]
# formats = ["pdf"]       # optional per-document override
# required_strings = []   # must appear in this document
# protected_strings = []  # exact when the string's first word appears
# forbidden_strings = []  # must not appear in this document

[document]
policy = "standard"       # standard, academic, international, minimal, or letter
section_vocabulary = [
    "Summary",
    "Core Skills",
    "Professional Experience",
    "Projects",
    "Education",
    "Certifications",
    "Publications",
]
required_sections = ["Summary", "Professional Experience"]
labeled_sections = ["Core Skills"]
subheading_sections = ["Professional Experience"]
# ordered_list_sections = ["Publications"]  # sections that may number entries
# dated_sections = ["Education"]            # sections whose entries need a year
# citation_field_labels = ["DOI"]           # labels a citation sub-bullet may use
# max_heading_level = 3    # 4 allows project headings inside a role
# contact_after_name = true                 # false accepts a CV contact block
# warning_rules = ["S6"]  # demote named rules to advisory findings
# disabled_rules = []      # disable only rules inappropriate for this project

[checks]
ascii_only = true         # set false for international names and locations
allowed_characters = ["\\u2022"]
forbid_smart_punctuation = true
date_style = "long"       # "long", "short", or "off"
required_strings = []
protected_strings = []
forbidden_strings = []
# Contact details and section order derive from each source unless overridden:
# contact_name = ""
# contact_email = ""
# contact_phones = []
# section_order = []
"""


def build_parser() -> argparse.ArgumentParser:
    """Build the complete argument parser without reading user state."""
    parser = argparse.ArgumentParser(
        prog="pressume",
        description="Render and verify resume PDFs from Markdown.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"pressume {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        help=f"TOML configuration path (default when present: {DEFAULT_CONFIG})",
    )
    commands = parser.add_subparsers(dest="command")

    source = argparse.ArgumentParser(add_help=False)
    source.add_argument(
        "--source", type=Path, help="folder containing Markdown sources (default: current folder)"
    )
    source_output = argparse.ArgumentParser(add_help=False, parents=[source])
    source_output.add_argument(
        "--output", type=Path, help="folder for rendered files (default: ./renders)"
    )

    render = commands.add_parser(
        "render", help="validate, render, and verify documents", parents=[source_output]
    )
    _add_document_arguments(render)
    render.add_argument(
        "--no-verify", action="store_true", help="render without checks; diagnostic use only"
    )
    _add_style_overrides(render)
    render.set_defaults(handler=_render)

    preview = commands.add_parser(
        "preview",
        help="render locally and optionally watch for source changes",
        parents=[source_output],
    )
    _add_document_arguments(preview)
    _add_style_overrides(preview)
    preview.add_argument(
        "--watch", action="store_true", help="re-render when a Markdown file changes"
    )
    preview.add_argument("--open", action="store_true", help="open the first rendered PDF")
    preview.set_defaults(handler=_preview)

    check = commands.add_parser(
        "check", help="verify existing output without rendering", parents=[source_output]
    )
    _add_document_arguments(check)
    check.set_defaults(handler=_check)

    lint = commands.add_parser(
        "lint", help="validate Markdown sources without rendering", parents=[source]
    )
    lint.add_argument("files", nargs="*", help="specific Markdown files; default: configured/all")
    lint.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    lint.set_defaults(handler=_lint)

    inspect = commands.add_parser(
        "inspect",
        help="report advisory readability and page-balance findings",
        parents=[source_output],
    )
    inspect.add_argument(
        "files", nargs="*", help="specific Markdown files; default: configured/all"
    )
    inspect.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    inspect.set_defaults(handler=_inspect)

    listing = commands.add_parser(
        "list", help="show which documents and artifacts Pressume selects", parents=[source_output]
    )
    listing.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    listing.set_defaults(handler=_list_documents)

    clean = commands.add_parser(
        "clean", help="find stale outputs tracked by Pressume", parents=[source_output]
    )
    clean.add_argument("--apply", action="store_true", help="remove the listed stale files")
    clean.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    clean.set_defaults(handler=_clean)

    commands.add_parser("init", help="write a documented starter configuration").set_defaults(
        handler=_init
    )

    new = commands.add_parser(
        "new", help="create a conforming document from a template", parents=[source]
    )
    new.add_argument("kind", choices=tuple(NEW_FILENAMES), help="template to use")
    new.add_argument("filename", nargs="?", help="default: Resume.md, CV.md, or Letter.md")
    new.set_defaults(handler=_new)

    commands.add_parser("refdoc", help="generate the configured DOCX style reference").set_defaults(
        handler=_refdoc
    )
    doctor = commands.add_parser("doctor", help="show installation and project diagnostics")
    doctor.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    doctor.set_defaults(handler=_doctor)
    return parser


def _add_document_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="*", help="specific Markdown files; default: configured/all")
    parser.add_argument("--formats", help="comma-separated output formats: pdf,txt,docx")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def _add_style_overrides(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--theme", choices=("modern", "technical", "traditional"))
    parser.add_argument("--density", choices=("compact", "balanced", "spacious"))


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and translate expected failures into stable exit codes."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    errors = Console(stderr=True)
    try:
        return _dispatch(parser, arguments, errors)
    except ConfigError as error:
        for problem in error.problems:
            errors.print(f"[red]{problem}[/red]")
        return EXIT_CONFIG_ERROR
    except PressumeError as error:
        errors.print(f"[red]{error}[/red]")
        return EXIT_RUNTIME_ERROR
    except OSError as error:
        errors.print(f"[red]File-system error: {error}[/red]")
        return EXIT_RUNTIME_ERROR
    except KeyboardInterrupt:
        errors.print("[red]Interrupted.[/red]")
        return EXIT_INTERRUPTED


def _dispatch(
    parser: argparse.ArgumentParser, arguments: argparse.Namespace, errors: Console
) -> int:
    if arguments.command is None:
        parser.print_help()
        return EXIT_OK
    handler: Callable[[argparse.Namespace, Console], int] = arguments.handler
    return handler(arguments, errors)


def _project(arguments: argparse.Namespace) -> Config:
    """Load the effective configuration with command-line overrides applied."""
    config = _effective_config(arguments.config)
    _apply_path_overrides(config, arguments)
    _apply_style_overrides(config, arguments)
    return config


def _clean(arguments: argparse.Namespace, errors: Console) -> int:
    from pressume.pipeline import clean_outputs

    return clean_outputs(_project(arguments), arguments.apply, as_json=arguments.json)


def _inspect(arguments: argparse.Namespace, errors: Console) -> int:
    from pressume.pipeline import inspect_existing

    return inspect_existing(_project(arguments), arguments.files, as_json=arguments.json)


def _refdoc(arguments: argparse.Namespace, errors: Console) -> int:
    from pressume.refdoc import build_reference_docx

    config = _project(arguments)
    destination = config.resolve(config.reference_docx or Path("reference.docx"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    build_reference_docx(config.style, destination)
    errors.print(f"Wrote [cyan]{destination}[/cyan]")
    return EXIT_OK


def _lint(arguments: argparse.Namespace, errors: Console) -> int:
    from pressume.pipeline import lint_only

    return lint_only(_project(arguments), arguments.files, as_json=arguments.json)


def _check(arguments: argparse.Namespace, errors: Console) -> int:
    from pressume.pipeline import verify_existing

    return verify_existing(
        _project(arguments),
        arguments.files,
        _format_override(arguments.formats),
        as_json=arguments.json,
    )


def _render(arguments: argparse.Namespace, errors: Console) -> int:
    from pressume.pipeline import run

    return run(
        _project(arguments),
        arguments.files,
        _format_override(arguments.formats),
        verify=not arguments.no_verify,
        as_json=arguments.json,
    )


def _effective_config(path: Path | None) -> Config:
    if path is not None:
        return load_config(path)
    if DEFAULT_CONFIG.exists():
        return load_config(DEFAULT_CONFIG)
    return Config(config_dir=Path.cwd())


def _apply_path_overrides(config: Config, arguments: argparse.Namespace) -> None:
    if getattr(arguments, "source", None) is not None:
        config.source_dir = arguments.source.expanduser().resolve()
    if getattr(arguments, "output", None) is not None:
        config.output_dir = arguments.output.expanduser().resolve()


def _apply_style_overrides(config: Config, arguments: argparse.Namespace) -> None:
    if getattr(arguments, "theme", None):
        config.style.theme = arguments.theme
    if getattr(arguments, "density", None):
        config.style.density = arguments.density


def _format_override(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return validate_formats(value.split(","), "--formats")


def _init(arguments: argparse.Namespace, errors: Console) -> int:
    destination = (arguments.config or DEFAULT_CONFIG).expanduser()
    if destination.exists():
        errors.print(f"[red]{destination} already exists; not overwriting.[/red]")
        return EXIT_VERIFICATION_FAILED
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(STARTER_CONFIG, encoding="utf-8")
    errors.print(f"Wrote [cyan]{destination}[/cyan]. Next: pressume new resume")
    return EXIT_OK


def _new(arguments: argparse.Namespace, errors: Console) -> int:
    from importlib.resources import files

    config = _project(arguments)
    # Chained single-segment joins: the 3.10 Traversable API accepts one
    # segment per call, and installed-package paths accept either form.
    template = files("pressume") / "templates" / f"{arguments.kind}.md"
    destination_dir = config.resolve(config.source_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    filename = arguments.filename or NEW_FILENAMES[arguments.kind]
    if Path(filename).suffix.casefold() != ".md" or Path(filename).name != filename:
        raise ConfigError(["New document filename must be a simple name ending in .md"])
    destination = destination_dir / filename
    if destination.exists():
        errors.print(f"[red]{destination} already exists; not overwriting.[/red]")
        return EXIT_VERIFICATION_FAILED
    destination.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    step = "pressume render"
    if arguments.kind == "letter":
        step = 'give it a profile with policy = "letter" in pressume.toml, then ' + step
    errors.print(f"Wrote [cyan]{destination}[/cyan]. Next: {step}")
    return EXIT_OK


@dataclass(frozen=True)
class Diagnostics:
    """What `pressume doctor` reports, in the order it reports it."""

    pressume: str
    python: str
    platform: str
    pandoc: str
    typst: str
    source: str
    source_found: bool
    output: str
    formats: list[str]
    theme: str
    font: str
    density: str
    pdf_standard: str
    independent_extractors: list[str]


def _diagnose(config: Config) -> Diagnostics:
    """Collect every fact `pressume doctor` reports, once."""
    import pypandoc

    from pressume.checks.pdfchecks import independent_extractor
    from pressume.template import resolve_style

    style = resolve_style(config.style)
    extractors = ["Poppler pdftotext"] if independent_extractor()[0] == "poppler" else []
    extractors.append(f"pdfminer.six {version('pdfminer.six')}")
    source = config.resolve(config.source_dir)
    return Diagnostics(
        pressume=__version__,
        python=platform.python_version(),
        platform=platform.system(),
        pandoc=str(pypandoc.get_pandoc_version()),
        typst=version("typst"),
        source=str(source),
        source_found=source.is_dir(),
        output=str(config.resolve(config.output_dir)),
        formats=config.formats,
        theme=style.theme.name,
        font=style.font,
        density=config.style.density,
        pdf_standard=style.pdf_standard,
        independent_extractors=extractors,
    )


def _doctor(arguments: argparse.Namespace, errors: Console) -> int:
    """Report environment and project diagnostics as JSON or as text."""
    report = _diagnose(_project(arguments))
    if arguments.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        console = Console()
        console.print(f"pressume {report.pressume}")
        console.print(f"Python {report.python} ({report.platform})")
        console.print(f"Pandoc {report.pandoc}")
        console.print(f"Typst {report.typst}")
        console.print(f"Source: {report.source} ({'found' if report.source_found else 'missing'})")
        console.print(f"Output: {report.output}")
        console.print(f"Formats: {', '.join(report.formats)}")
        console.print(f"Theme: {report.theme} ({report.font}, {report.density})")
        console.print(f"PDF standard: {report.pdf_standard}")
        console.print(f"Independent extractors: {', '.join(report.independent_extractors)}")
    return EXIT_OK if report.source_found else EXIT_VERIFICATION_FAILED


@dataclass(frozen=True)
class DocumentPlan:
    """What `pressume list` reports for one selected document."""

    source: str
    output_name: str
    profile: str | None
    lint_only: bool
    formats: list[str]
    pages: int | None
    min_pages: int | None
    max_pages: int | None

    @property
    def page_target(self) -> str:
        """Describe the page requirement as an exact count or a range."""
        if self.pages is not None:
            return str(self.pages)
        return f"{self.min_pages or 1}-{self.max_pages or 'any'}"


def _list_documents(arguments: argparse.Namespace, errors: Console) -> int:
    """Show document discovery and the resolved artifact plan."""
    from pressume.pipeline import select_documents

    config = _project(arguments)
    plan = [
        DocumentPlan(
            source=document.file,
            output_name=document.output_name or Path(document.file).stem,
            profile=document.profile,
            lint_only=document.lint_only,
            formats=document.formats or config.formats,
            pages=document.pages,
            min_pages=document.min_pages,
            max_pages=document.max_pages,
        )
        for document in select_documents(config, [])
    ]
    if arguments.json:
        print(json.dumps({"documents": [asdict(item) for item in plan]}, indent=2))
        return EXIT_OK
    table = Table(title="Pressume document plan")
    table.add_column("Source")
    table.add_column("Output")
    table.add_column("Formats")
    table.add_column("Pages")
    table.add_column("Profile")
    for item in plan:
        table.add_row(
            item.source,
            "lint only" if item.lint_only else item.output_name,
            ", ".join(item.formats),
            item.page_target,
            item.profile or "standard",
        )
    Console().print(table)
    return EXIT_OK


def _preview(arguments: argparse.Namespace, errors: Console) -> int:
    """Render once or poll Markdown modification times until interrupted."""
    from pressume.pipeline import run, select_documents

    config = _project(arguments)
    selected_formats = _format_override(arguments.formats) or ["pdf"]

    def render_once() -> int:
        result = run(config, arguments.files, selected_formats, verify=True, as_json=False)
        if result == EXIT_OK and arguments.open:
            documents = select_documents(config, arguments.files)
            first = next((item for item in documents if not item.lint_only), None)
            if first is not None:
                stem = first.output_name or Path(first.file).stem
                webbrowser.open((config.resolve(config.output_dir) / f"{stem}.pdf").as_uri())
        return result

    result = render_once()
    if not arguments.watch:
        return result
    source_dir = config.resolve(config.source_dir)
    errors.print("Watching Markdown sources. Press Ctrl-C to stop.")
    snapshot = _source_snapshot(source_dir)
    while True:
        time.sleep(0.75)
        current = _source_snapshot(source_dir)
        if current != snapshot:
            snapshot = current
            errors.print("Source changed; rendering preview...")
            result = render_once()


def _source_snapshot(source_dir: Path) -> tuple[tuple[str, int, int], ...]:
    """Snapshot Markdown sources, tolerating files that vanish mid-scan.

    Editors that save atomically replace files between ``glob`` and ``stat``;
    a vanished file simply drops out of the snapshot instead of killing the
    watch loop, and reappears on the next poll.
    """
    entries: list[tuple[str, int, int]] = []
    for path in sorted(source_dir.glob("*.md")):
        try:
            info = path.stat()
        except OSError:
            continue
        entries.append((str(path), info.st_mtime_ns, info.st_size))
    return tuple(entries)


if __name__ == "__main__":
    raise SystemExit(main())
