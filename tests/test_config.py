"""Configuration validation tests."""

import pytest

from pressume.config import ConfigError, load_config

VALID = """
[paths]
source_dir = "cv"
output_dir = "renders"

[output]
formats = ["pdf", "txt"]

[style]
font = "Source Serif 4"
size_pt = 10
margin_in = 0.5
accent = "#22304A"

[[documents]]
file = "Resume.md"
pages = 2

[checks]
contact_name = "Jane Doe"
contact_email = "jane@example.com"
section_order = ["Summary", "Experience"]
"""


def write(tmp_path, text):
    path = tmp_path / "pressume.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_config_loads(tmp_path):
    config = load_config(write(tmp_path, VALID))
    assert config.style.font == "Source Serif 4"
    assert config.documents[0].pages == 2
    assert config.checks.contact_email == "jane@example.com"


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.toml")


def test_all_problems_reported_together(tmp_path):
    bad = """
[style]
accent = "blue"
size_pt = 40

[output]
formats = ["pdf", "html"]

[[documents]]
file = "Resume.txt"
"""
    with pytest.raises(ConfigError) as error:
        load_config(write(tmp_path, bad))
    text = "\n".join(error.value.problems)
    assert "style.accent" in text
    assert "style.size_pt" in text
    assert "output.formats" in text
    assert "documents[0].file" in text


def test_invalid_toml_reports_parse_error(tmp_path):
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(write(tmp_path, "not = toml ["))


def test_relative_paths_resolve_against_config(tmp_path):
    config = load_config(write(tmp_path, VALID))
    assert config.resolve(config.source_dir) == (tmp_path / "cv").resolve()


WITH_PROFILE = (
    VALID
    + """
[profiles.cv]
# Overriding the vocabulary means re-scoping every list that draws from it;
# validation enforces this.
section_vocabulary = ["Summary", "Experience", "Publications"]
required_sections = ["Summary"]
labeled_sections = []
subheading_sections = ["Experience"]
ordered_list_sections = ["Publications"]
max_heading_level = 4

[[documents]]
file = "CV.md"
profile = "cv"
lint_only = true
"""
)


def test_profile_inherits_defaults_and_overrides(tmp_path):
    config = load_config(write(tmp_path, WITH_PROFILE))
    cv = config.profiles["cv"]
    assert cv.max_heading_level == 4
    assert cv.ordered_list_sections == ["Publications"]
    # Unset keys carry the default rules forward.
    assert cv.contact_after_name is True
    # The default profile is untouched by the override.
    assert config.document_rules.max_heading_level == 3


def test_document_profile_and_lint_only_parse(tmp_path):
    config = load_config(write(tmp_path, WITH_PROFILE))
    cv_doc = next(d for d in config.documents if d.file == "CV.md")
    assert cv_doc.profile == "cv"
    assert cv_doc.lint_only is True
    assert config.rules_for(cv_doc).max_heading_level == 4
    resume_doc = next(d for d in config.documents if d.file == "Resume.md")
    assert config.rules_for(resume_doc) is config.document_rules


def test_unknown_profile_reference_fails(tmp_path):
    bad = VALID + '\n[[documents]]\nfile = "CV.md"\nprofile = "missing"\n'
    with pytest.raises(ConfigError, match=r"no \[profiles\.missing\]"):
        load_config(write(tmp_path, bad))


def test_profile_scoped_list_outside_vocabulary_fails(tmp_path):
    bad = VALID + '\n[profiles.cv]\nordered_list_sections = ["Nonexistent"]\n'
    with pytest.raises(ConfigError, match=r"profiles\.cv\.ordered_list_sections"):
        load_config(write(tmp_path, bad))


@pytest.mark.parametrize("table", ["paths", "output", "style", "checks", "document", "profiles"])
def test_wrong_table_type_is_reported_without_crashing(tmp_path, table):
    with pytest.raises(ConfigError, match=rf"{table}: expected a table"):
        load_config(write(tmp_path, f'{table} = "not a table"\n'))


def test_format_lists_must_be_nonempty_known_and_unique(tmp_path):
    with pytest.raises(ConfigError) as error:
        load_config(write(tmp_path, '[output]\nformats = ["pdf", "PDF", "html"]\n'))
    message = str(error.value)
    assert "unknown formats" in message
    assert "duplicate formats" in message


def test_document_scoped_formats_and_strings(tmp_path):
    config = load_config(
        write(
            tmp_path,
            """
[[documents]]
file = "Resume.md"
formats = ["txt"]
required_strings = ["Required"]
protected_strings = ["Protected exact"]
forbidden_strings = ["Draft"]
""",
        )
    )
    document = config.documents[0]
    checks = config.checks_for(document)
    assert document.formats == ["txt"]
    assert checks.required_strings == ["Required"]
    assert checks.protected_strings == ["Protected exact"]
    assert checks.forbidden_strings == ["Draft"]


def test_document_path_cannot_escape_source_folder(tmp_path):
    with pytest.raises(ConfigError, match="relative Markdown path"):
        load_config(write(tmp_path, '[[documents]]\nfile = "../Resume.md"\n'))


def test_document_output_stems_must_be_unique(tmp_path):
    with pytest.raises(ConfigError, match="output name collides"):
        load_config(
            write(
                tmp_path,
                '[[documents]]\nfile = "one/Resume.md"\n[[documents]]\nfile = "two/Resume.md"\n',
            )
        )
