"""The letter policy: a name line and contact paragraph, then prose.

A cover letter shares a resume's front matter and nothing else, so it is
selected per document through a profile and set with space between its
paragraphs.
"""

import json
from pathlib import Path

import pytest
from geometry_baseline import measure
from pypdf import PdfReader

from pressume.checks.document import DocumentRules, lint_document
from pressume.checks.report import Severity
from pressume.cli import main
from pressume.config import Config, Document, Style
from pressume.documents import SourceDocument
from pressume.formats import render_artifact
from pressume.themes import DENSITY_FACTORS, THEMES

LETTER = (Path(__file__).parent / "fixtures" / "cover_letter.md").read_text(encoding="utf-8")

CONFIG = """\
[[documents]]
file = "Cover_Letter.md"
profile = "letter"
pages = 1

[profiles.letter]
policy = "letter"
"""


def letter_rules() -> DocumentRules:
    rules = DocumentRules()
    rules.apply_policy("letter")
    return rules


def failures(markdown: str, rules: DocumentRules) -> list[str]:
    results = lint_document("letter", markdown, rules)
    return [result.detail for result in results if result.severity is Severity.FAIL]


def test_letter_policy_passes_a_conforming_letter():
    assert failures(LETTER, letter_rules()) == []


def test_resume_section_rules_do_not_fire_on_a_letter():
    assert any(
        "S2 required section missing" in detail for detail in failures(LETTER, DocumentRules())
    )
    assert not any("S2" in detail for detail in failures(LETTER, letter_rules()))


def test_letter_policy_requires_the_name_line_but_not_an_email():
    without_name = LETTER.split("\n", 2)[2]
    found = failures(without_name, letter_rules())
    assert any("MD025" in detail for detail in found)
    assert any("MD041" in detail for detail in found)

    without_email = LETTER.replace("jane@example.com | ", "")
    assert not any("S1" in detail for detail in failures(without_email, letter_rules()))


def test_a_letter_has_no_sections():
    with_section = LETTER.replace("Dear Hiring Team,", "## Summary\n\nDear Hiring Team,")
    assert any("S2" in detail for detail in failures(with_section, letter_rules()))


def _paragraph_gaps(pdf: Path, theme: str) -> tuple[float, float, float]:
    """Return the line pitch inside a paragraph, the pitch across a paragraph
    break, and the body text size, measured on the rendered page."""
    lines = measure(pdf, theme).page_lines(1)
    starts = [
        next(index for index, line in enumerate(lines) if line.text.startswith(opening))
        for opening in ("I am writing", "Dear Hiring", "At Example Health", "I would welcome")
    ]
    inside = lines[starts[0]].top - lines[starts[0] + 1].top
    across = min(lines[start - 1].top - lines[start].top for start in starts[1:])
    return inside, across, lines[starts[0]].size


@pytest.mark.parametrize("density", DENSITY_FACTORS)
@pytest.mark.parametrize("theme", THEMES)
def test_letter_paragraphs_are_set_apart_in_every_theme_and_density(tmp_path, theme, density):
    document = Document(file="Cover_Letter.md", profile="letter", pages=1)
    config = Config(
        config_dir=tmp_path,
        style=Style(theme=theme, density=density),
        documents=[document],
        profiles={"letter": letter_rules()},
    )
    source = SourceDocument(document, tmp_path / document.file, LETTER)
    pdf = tmp_path / "Cover_Letter.pdf"
    render_artifact("pdf", source, pdf, config)

    inside, across, size = _paragraph_gaps(pdf, theme)
    assert across - inside >= 0.45 * size, (inside, across)


def _render_with_caller_config(tmp_path: Path, markdown: str, capsys) -> tuple[int, dict]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "Cover_Letter.md").write_text(markdown, encoding="utf-8")
    config = tmp_path / "letter.toml"
    config.write_text(CONFIG, encoding="utf-8")
    capsys.readouterr()
    code = main(
        [
            "--config",
            str(config),
            "render",
            "Cover_Letter.md",
            "--source",
            str(source),
            "--output",
            str(tmp_path / "out"),
            "--formats",
            "pdf,txt",
            "--theme",
            "traditional",
            "--density",
            "spacious",
            "--json",
        ]
    )
    return code, json.loads(capsys.readouterr().out)


def test_the_documented_config_renders_a_letter(tmp_path, capsys):
    code, payload = _render_with_caller_config(tmp_path, LETTER, capsys)
    assert code == 0, [item for item in payload["results"] if item["result"] == "fail"]
    pdf = tmp_path / "out" / "Cover_Letter.pdf"
    assert (tmp_path / "out" / "Cover_Letter.txt").is_file()
    assert PdfReader(pdf).metadata.title == "JANE DOE - Letter"


def test_the_documented_config_holds_a_letter_to_one_page(tmp_path, capsys):
    opening = LETTER.split("Sincerely,")[0]
    too_long = opening + (opening.split("\n\n", 2)[2] * 8) + "Sincerely,\n\nJane Doe\n"
    code, payload = _render_with_caller_config(tmp_path, too_long, capsys)
    assert code == 1
    pages = [item for item in payload["results"] if item["check"] == "pdf: page count"]
    assert [item["result"] for item in pages] == ["fail"]
    assert not (tmp_path / "out" / "Cover_Letter.pdf").exists()
