"""Select, validate, render, and independently verify resume documents."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path, PurePath

from rich.console import Console

from pressume.checks.ats import derive_checks
from pressume.checks.document import lint_document
from pressume.checks.report import CheckResult, Severity, emit
from pressume.checks.source import check_source
from pressume.config import Config, ConfigError, Document, validate_formats
from pressume.diagnostics import inspect_pdf_layout, inspect_source
from pressume.documents import SourceDocument
from pressume.errors import RenderError
from pressume.formats import render_artifact, verify_artifact
from pressume.manifest import load_manifest, stale_artifacts, write_manifest


def lint_only(config: Config, names: list[str], as_json: bool = False) -> int:
    """Lint selected Markdown sources without rendering them."""
    sources, results = _load_sources(config, names, lint=True)
    if not sources and not results:
        results.append(_no_documents_result(config))
    return 0 if emit(results, as_json) else 1


def select_documents(config: Config, names: list[str]) -> list[Document]:
    """Select configured documents or discover Markdown in the source folder."""
    if not names:
        if config.documents:
            return config.documents
        source_dir = config.resolve(config.source_dir)
        repository_files = {
            "agents",
            "changelog",
            "code_of_conduct",
            "contributing",
            "license",
            "readme",
            "security",
        }
        return [
            Document(file=path.name)
            for path in sorted(source_dir.glob("*.md"))
            if path.stem.casefold() not in repository_files
        ]

    configured = {document.file: document for document in config.documents}
    selected: list[Document] = []
    stems: set[str] = set()
    for name in names:
        filename = name if name.casefold().endswith(".md") else f"{name}.md"
        path = PurePath(filename)
        if path.is_absolute() or ".." in path.parts:
            raise ConfigError([f"Document path must stay inside the source folder: {name}"])
        document = configured.get(filename, Document(file=filename))
        stem = Path(filename).stem.casefold()
        if stem in stems:
            raise ConfigError([f"Selected documents produce the same output name: {filename}"])
        stems.add(stem)
        selected.append(document)
    return selected


def run(
    config: Config,
    names: list[str],
    formats: list[str] | None = None,
    verify: bool = True,
    as_json: bool = False,
) -> int:
    """Render selected documents transactionally and return a process exit code.

    All requested artifacts are created and verified in a temporary directory.
    Existing deliverables are replaced only after the entire run passes.
    """
    console = Console(stderr=True)
    sources, results = _load_sources(config, names, lint=verify)
    if not sources and not results:
        results.append(_no_documents_result(config))
    if _failed(results):
        return 0 if emit(results, as_json) else 1

    renderable = [source for source in sources if not source.settings.lint_only]
    for source in sources:
        if source.settings.lint_only:
            console.print(f"  linted [cyan]{source.settings.file}[/cyan] (lint-only)")

    if not renderable:
        return 0 if emit(results, as_json) else 1

    output_dir = config.resolve(config.output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    pending: list[tuple[Path, Path]] = []
    rendered: list[Path] = []

    with tempfile.TemporaryDirectory(prefix=".pressume-", dir=output_dir.parent) as scratch_name:
        scratch = Path(scratch_name)
        for source in renderable:
            document_formats = _formats_for(config, source.settings, formats)
            checks = derive_checks(source.markdown, config.checks_for(source.settings))
            for name in document_formats:
                temporary = scratch / f"{source.stem}.{name}"
                final = output_dir / temporary.name
                render_artifact(name, source, temporary, config)
                if not temporary.is_file() or temporary.stat().st_size == 0:
                    raise RenderError(f"Renderer did not produce a usable {temporary.name}")
                pending.append((temporary, final))
                rendered.append(final)
                if verify:
                    results.extend(verify_artifact(name, source, temporary, checks, config))

        if verify and _failed(results):
            console.print(
                "[yellow]Verification failed; existing deliverables were left unchanged.[/yellow]"
            )
            return 0 if emit(results, as_json) else 1

        output_dir.mkdir(parents=True, exist_ok=True)
        _commit_outputs(pending, scratch, output_dir, sources, config, formats)

    for path in rendered:
        console.print(f"  rendered [cyan]{path}[/cyan]")
    if not verify:
        console.print("[yellow]Verification skipped (--no-verify); diagnostic use only.[/yellow]")
        return 0
    return 0 if emit(results, as_json) else 1


def verify_existing(
    config: Config,
    names: list[str],
    formats: list[str] | None = None,
    as_json: bool = False,
) -> int:
    """Verify existing artifacts independently of the render that made them."""
    output_dir = config.resolve(config.output_dir)
    sources, results = _load_sources(config, names, lint=True)
    if not sources and not results:
        results.append(_no_documents_result(config))

    for source in sources:
        if source.settings.lint_only:
            continue
        checks = derive_checks(source.markdown, config.checks_for(source.settings))
        for name in _formats_for(config, source.settings, formats):
            artifact = output_dir / f"{source.stem}.{name}"
            if not artifact.is_file() or artifact.stat().st_size == 0:
                results.append(
                    CheckResult(
                        source.stem,
                        f"{name}: exists",
                        Severity.FAIL,
                        f"missing or empty {artifact.name}",
                    )
                )
                continue
            results.extend(verify_artifact(name, source, artifact, checks, config))
    expected = expected_artifacts(config)
    stale = stale_artifacts(output_dir, expected)
    if stale:
        results.append(
            CheckResult(
                "project",
                "output manifest",
                Severity.WARN,
                "stale tracked output: " + ", ".join(path.name for path in stale),
            )
        )
    return 0 if emit(results, as_json) else 1


def _load_sources(
    config: Config, names: list[str], *, lint: bool
) -> tuple[list[SourceDocument], list[CheckResult]]:
    source_dir = config.resolve(config.source_dir)
    sources: list[SourceDocument] = []
    results: list[CheckResult] = []
    for document in select_documents(config, names):
        path = source_dir / document.file
        stem = Path(document.file).stem
        if not path.is_file():
            results.append(CheckResult(stem, "input exists", Severity.FAIL, f"missing {path}"))
            continue
        try:
            markdown = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            results.append(CheckResult(stem, "input is UTF-8", Severity.FAIL, f"{path}: {error}"))
            continue
        except OSError as error:
            results.append(CheckResult(stem, "input readable", Severity.FAIL, str(error)))
            continue
        source = SourceDocument(document, path, markdown)
        sources.append(source)
        if lint:
            checks = config.checks_for(document)
            results.extend(check_source(stem, markdown, checks))
            results.extend(
                lint_document(
                    stem,
                    markdown,
                    config.rules_for(document),
                    date_style=checks.date_style,
                )
            )
    return sources, results


def _formats_for(config: Config, document: Document, override: list[str] | None) -> list[str]:
    selected = override if override is not None else document.formats or config.formats
    return validate_formats(selected, "formats")


def expected_artifacts(config: Config) -> dict[str, list[str]]:
    """Return every artifact expected from the current project configuration."""
    expected: dict[str, list[str]] = {}
    for document in select_documents(config, []):
        if document.lint_only:
            continue
        stem = document.output_name or Path(document.file).stem
        expected[document.file] = [
            f"{stem}.{format_name}" for format_name in _formats_for(config, document, None)
        ]
    return expected


def inspect_existing(config: Config, names: list[str], as_json: bool = False) -> int:
    """Run advisory source and visual diagnostics against existing PDFs."""
    sources, results = _load_sources(config, names, lint=False)
    output_dir = config.resolve(config.output_dir)
    for source in sources:
        results.extend(inspect_source(source.stem, source.markdown))
        pdf = output_dir / f"{source.stem}.pdf"
        if pdf.is_file():
            results.extend(inspect_pdf_layout(source.stem, pdf, source.markdown))
        elif not source.settings.lint_only:
            results.append(
                CheckResult(
                    source.stem, "readability: page balance", Severity.WARN, f"missing {pdf.name}"
                )
            )
    return 0 if emit(results, as_json) else 1


def clean_outputs(config: Config, apply: bool, as_json: bool = False) -> int:
    """List or remove only stale files recorded in Pressume's manifest."""
    output_dir = config.resolve(config.output_dir)
    stale = stale_artifacts(output_dir, expected_artifacts(config))
    results: list[CheckResult] = []
    for path in stale:
        if apply:
            try:
                path.unlink()
            except OSError as error:
                results.append(
                    CheckResult("project", "clean", Severity.FAIL, f"{path.name}: {error}")
                )
                continue
        results.append(
            CheckResult(
                "project",
                "clean",
                Severity.PASS if apply else Severity.WARN,
                f"{'removed' if apply else 'stale'}: {path.name}",
            )
        )
    if not stale:
        results.append(CheckResult("project", "clean", Severity.PASS, "no stale tracked output"))
    if apply and not _failed(results):
        stale_names = {path.name for path in stale}
        manifest = {
            source: [name for name in names if name not in stale_names]
            for source, names in load_manifest(output_dir).items()
            if any(name not in stale_names for name in names)
        }
        write_manifest(output_dir, manifest)
    return 0 if emit(results, as_json) else 1


def _commit_outputs(
    pending: list[tuple[Path, Path]],
    scratch: Path,
    output_dir: Path,
    sources: list[SourceDocument],
    config: Config,
    format_override: list[str] | None,
) -> None:
    """Install staged artifacts and restore every prior file on commit failure."""
    backup_dir = scratch / "backups"
    backup_dir.mkdir()
    backups: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    try:
        for temporary, final in pending:
            if final.exists():
                backup = backup_dir / final.name
                os.replace(final, backup)
                backups.append((backup, final))
            os.replace(temporary, final)
            installed.append(final)

        manifest = load_manifest(output_dir)
        for source in sources:
            if source.settings.lint_only:
                continue
            produced = [
                f"{source.stem}.{name}"
                for name in _formats_for(config, source.settings, format_override)
            ]
            # Keep earlier generated names until `clean` can compare them with
            # the current project plan. Replacing this entry would forget a
            # renamed output and make the stale file impossible to identify.
            manifest[source.settings.file] = sorted(
                set(manifest.get(source.settings.file, [])) | set(produced)
            )
        write_manifest(output_dir, manifest)
    except OSError as error:
        for path in reversed(installed):
            path.unlink(missing_ok=True)
        for backup, final in reversed(backups):
            if backup.exists():
                os.replace(backup, final)
        raise RenderError(f"Could not commit rendered output: {error}") from error


def _failed(results: list[CheckResult]) -> bool:
    return any(result.severity is Severity.FAIL for result in results)


def _no_documents_result(config: Config) -> CheckResult:
    source_dir = config.resolve(config.source_dir)
    return CheckResult(
        "project",
        "input documents",
        Severity.FAIL,
        f"No Markdown documents found in {source_dir}. Run `pressume new resume` "
        "or point --source at their folder.",
    )
