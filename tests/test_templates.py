"""The bundled templates must pass the contract they teach.

A template that fails its own lint would hand every new user a broken
starting point, so these tests hold the templates to the default rules
exactly as `pressume new` ships them.
"""

from importlib.resources import files

import pytest

from pressume.checks.document import DocumentRules, lint_document
from pressume.checks.report import Severity
from pressume.checks.source import check_source
from pressume.cli import main
from pressume.config import Checks


def template_text(kind: str) -> str:
    return files("pressume").joinpath("templates", f"{kind}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", ["resume", "cv"])
def test_template_passes_default_contract(kind):
    results = lint_document(kind, template_text(kind), DocumentRules())
    failures = [r.detail for r in results if r.severity is Severity.FAIL]
    assert failures == []


def test_letter_template_passes_the_letter_contract():
    rules = DocumentRules()
    rules.apply_policy("letter")
    results = lint_document("letter", template_text("letter"), rules)
    assert [r.detail for r in results if r.severity is Severity.FAIL] == []


@pytest.mark.parametrize("kind", ["resume", "cv", "letter"])
def test_template_is_ascii_clean(kind):
    results = check_source(kind, template_text(kind), Checks())
    assert all(r.severity is Severity.PASS for r in results)


def test_new_command_writes_template(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "resume"]) == 0
    written = (tmp_path / "Resume.md").read_text(encoding="utf-8")
    assert written == template_text("resume")


def test_new_letter_writes_the_letter_template(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "letter"]) == 0
    assert (tmp_path / "Letter.md").read_text(encoding="utf-8") == template_text("letter")


def test_new_command_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CV.md").write_text("existing", encoding="utf-8")
    assert main(["new", "cv"]) == 1
    assert (tmp_path / "CV.md").read_text(encoding="utf-8") == "existing"


def test_starter_config_and_template_cohere(tmp_path, monkeypatch):
    """The three-command quick start must hold together before any editing.

    init and new ship as a pair; if their placeholders, paths, or section
    names drift apart, the first thing a new user sees is a failing render.
    """
    from pathlib import Path

    from pressume.config import load_config

    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert main(["new", "resume"]) == 0
    config = load_config(Path("pressume.toml"))

    resume = template_text("resume")
    assert config.resolve(config.source_dir / "Resume.md").exists()
    # The starter leaves contact and section checks unset so they stay derived
    # from the document; pre-filled placeholders would drift from real content.
    assert config.checks.contact_name == ""
    assert config.checks.contact_email == ""
    assert config.checks.section_order == []
    results = lint_document("resume", resume, config.rules_for(config.documents[0]))
    assert [r for r in results if r.severity is Severity.FAIL] == []
