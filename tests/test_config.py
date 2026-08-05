"""Configuration validation tests."""

import dataclasses

import pytest

from pressume.config import (
    CHECK_SETTINGS,
    DOCUMENT_SETTINGS,
    PATH_SETTINGS,
    RULE_KEYS,
    STYLE_SETTINGS,
    Checks,
    Config,
    ConfigError,
    Document,
    Style,
    load_config,
)

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


@pytest.mark.parametrize(
    ("settings", "shape"),
    [
        (PATH_SETTINGS, Config),
        (STYLE_SETTINGS, Style),
        (DOCUMENT_SETTINGS, Document),
        (CHECK_SETTINGS, Checks),
    ],
)
def test_every_setting_writes_to_a_real_field(settings, shape):
    """The setting tables and the dataclasses name the same things.

    The tables are the only description of a configuration key. If one names
    an attribute the dataclass does not have, a valid file would silently
    create a new attribute nothing reads.
    """
    declared = {item.name for item in dataclasses.fields(shape)}
    assert {setting.attribute for setting in settings.values()} <= declared


def test_starter_configuration_parses_and_documents_every_key(tmp_path):
    """`pressume init` writes a file that loads, and mentions every setting.

    The starter is a third statement of the configuration vocabulary. Both
    directions matter: a key it forgets is undiscoverable, and a key it invents
    would be rejected the moment someone uncomments it.
    """
    from pressume.cli import STARTER_CONFIG

    config = load_config(write(tmp_path, STARTER_CONFIG))
    assert config.documents[0].file == "Resume.md"

    mentioned = {
        line.lstrip("# ").split("=", 1)[0].strip()
        for line in STARTER_CONFIG.splitlines()
        if "=" in line and not line.lstrip("# ").startswith("[")
    }
    documented = (
        set(PATH_SETTINGS)
        | set(STYLE_SETTINGS)
        | set(DOCUMENT_SETTINGS)
        | set(CHECK_SETTINGS)
        | set(RULE_KEYS)
        | {"formats"}
    )
    assert documented - mentioned == set()
    assert mentioned - documented == set()


def test_paper_is_limited_to_sizes_the_word_file_can_also_use(tmp_path):
    """A paper the DOCX pass cannot set is rejected, not silently downgraded."""
    with pytest.raises(ConfigError, match=r"style.paper: 'a5' must be one of"):
        load_config(write(tmp_path, '[style]\npaper = "a5"\n'))
    config = load_config(write(tmp_path, '[style]\npaper = "A4"\n'))
    assert config.style.paper == "a4"


def test_font_directories_resolve_against_the_configuration_file(tmp_path):
    config = load_config(write(tmp_path, '[paths]\nfonts = ["brand-fonts", "more"]\n'))
    assert [config.resolve(path) for path in config.font_dirs] == [
        (tmp_path / "brand-fonts").resolve(),
        (tmp_path / "more").resolve(),
    ]


def test_out_of_range_and_malformed_values_name_the_key_and_the_expectation(tmp_path):
    bad = """
[style]
size_pt = 40
margin_in = 9
accent = "blue"
language = "english"
region = "Canada"

[[documents]]
file = "Resume.md"
pages = 0
"""
    with pytest.raises(ConfigError) as error:
        load_config(write(tmp_path, bad))
    text = "\n".join(error.value.problems)
    assert "style.size_pt: 40 is outside the sensible range 6-14" in text
    assert "style.margin_in: 9 is outside the sensible range 0.3-1.5" in text
    assert "style.accent: 'blue' is not a #RRGGBB hex color" in text
    assert "style.language: 'english' is not a two- or three-letter ISO 639" in text
    assert "style.region: 'Canada' is not a two-letter ISO 3166-1 region code" in text
    assert "documents[0].pages: 0 is not a positive integer page target" in text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[style]\ntheme = 4\n", "style.theme: expected str, got int"),
        ('[style]\nfont = " "\n', "style.font: must not be empty"),
        ('[checks]\nascii_only = "yes"\n', "checks.ascii_only: expected bool, got str"),
        ('[checks]\nsection_order = "Summary"\n', "checks.section_order: expected list, got str"),
        ('[checks]\nsection_order = [""]\n', "every entry must be a non-empty string"),
        ('[document]\nmax_heading_level = "3"\n', "document.max_heading_level: expected int"),
        ('[style]\nsize_pt = "10"\n', "style.size_pt: expected number, got str"),
    ],
)
def test_wrong_types_are_named_by_key_and_expected_type(tmp_path, text, expected):
    with pytest.raises(ConfigError) as error:
        load_config(write(tmp_path, text))
    assert expected in "\n".join(error.value.problems)
