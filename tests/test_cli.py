"""CLI behavior: the interface contract automation depends on.

Exit codes, stream discipline, JSON output, and strict configuration are
part of the API; these tests hold them steady.
"""

import json

import pytest

from pressume.cli import main
from pressume.config import ConfigError, load_config


def test_bare_invocation_prints_help_and_succeeds(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "render" in out and "exit codes" in out


def test_version_matches_package_metadata(capsys):
    from importlib.metadata import version

    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert version("pressume") in capsys.readouterr().out


def test_no_config_no_documents_says_how_to_start(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["render"]) == 1  # nothing to render, but not a config error
    assert "pressume new resume" in capsys.readouterr().out


def test_zero_config_render_verifies_green(tmp_path, monkeypatch, capsys):
    """The tool works with no configuration file at all: template in, PDF out,
    every contact and section check derived from the document itself."""
    monkeypatch.chdir(tmp_path)
    assert main(["new", "resume"]) == 0
    capsys.readouterr()
    assert main(["render", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["failed"] == 0
    assert (tmp_path / "renders" / "Resume.pdf").exists()
    checked = {item["check"] for item in payload["results"]}
    assert "ats: name leads document" in checked
    assert "ats: email near top" in checked


def test_explicitly_named_missing_config_is_still_an_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["--config", "elsewhere.toml", "render"]) == 2


def test_source_and_output_flags_point_anywhere(tmp_path, monkeypatch, capsys):
    source = tmp_path / "documents"
    output = tmp_path / "out"
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    assert main(["new", "resume", "--source", str(source)]) == 0
    assert (source / "Resume.md").exists()
    capsys.readouterr()
    assert main(["render", "--source", str(source), "--output", str(output), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["failed"] == 0
    assert (output / "Resume.pdf").exists()
    assert not (workdir / "renders").exists()


def test_missing_source_folder_names_itself_in_the_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["render", "--source", str(tmp_path / "nowhere")]) == 1
    assert "nowhere" in capsys.readouterr().out


def test_lint_json_goes_to_stdout_and_parses(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert main(["new", "resume"]) == 0
    capsys.readouterr()
    assert main(["lint", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["failed"] == 0
    assert all("result" in item for item in payload["results"])


def test_lint_failure_exit_code_and_json_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert main(["new", "resume"]) == 0
    resume = tmp_path / "Resume.md"
    resume.write_text(
        resume.read_text(encoding="utf-8").replace("## Summary", "## Life Story"),
        encoding="utf-8",
    )
    capsys.readouterr()
    assert main(["lint", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["failed"] >= 1


def test_unknown_config_key_fails_loudly(tmp_path):
    config = tmp_path / "pressume.toml"
    config.write_text(
        '[checks]\ndate_stile = "long"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="date_stile"):
        load_config(config)


def test_unknown_top_level_table_fails_loudly(tmp_path):
    config = tmp_path / "pressume.toml"
    config.write_text("[styles]\nfont = 'X'\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="styles"):
        load_config(config)


def test_invalid_cli_format_is_a_configuration_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "resume"]) == 0
    assert main(["render", "--formats", "html"]) == 2
    assert not (tmp_path / "renders").exists()


def test_init_respects_custom_config_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / "config" / "custom.toml"
    assert main(["--config", str(destination), "init"]) == 0
    assert destination.exists()
    assert not (tmp_path / "pressume.toml").exists()


def test_new_rejects_invalid_existing_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pressume.toml").write_text('style = "broken"\n', encoding="utf-8")
    assert main(["new", "resume"]) == 2
    assert not (tmp_path / "Resume.md").exists()


def test_source_failure_preserves_existing_deliverable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "resume"]) == 0
    output = tmp_path / "renders" / "Resume.pdf"
    output.parent.mkdir()
    output.write_bytes(b"last known good")
    resume = tmp_path / "Resume.md"
    resume.write_text(
        resume.read_text(encoding="utf-8").replace("## Summary", "## Life Story"),
        encoding="utf-8",
    )
    assert main(["render"]) == 1
    assert output.read_bytes() == b"last known good"


def test_verification_failure_after_rendering_leaves_deliverables_byte_identical(
    tmp_path, monkeypatch, capsys
):
    """The transactional promise, tested where it is hardest to keep.

    A source-lint failure returns before anything is rendered. This failure
    happens after every artifact exists, in the temporary directory, which is
    the branch that has to refuse to install them.
    """
    monkeypatch.chdir(tmp_path)
    assert main(["new", "resume"]) == 0
    assert main(["render"]) == 0
    renders = tmp_path / "renders"
    before = {path.name: path.read_bytes() for path in sorted(renders.iterdir())}
    assert "Resume.pdf" in before

    (tmp_path / "pressume.toml").write_text(
        '[[documents]]\nfile = "Resume.md"\npages = 9\n', encoding="utf-8"
    )
    capsys.readouterr()
    assert main(["render"]) == 1
    assert "left unchanged" in capsys.readouterr().err
    after = {path.name: path.read_bytes() for path in sorted(renders.iterdir())}
    assert after == before


def test_a_source_that_is_not_utf8_is_reported_as_such(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Resume.md").write_bytes(b"# JANE DOE\n\n\xff\xfe not text\n")
    assert main(["lint", "--json"]) == 1
    results = json.loads(capsys.readouterr().out)["results"]
    assert [item for item in results if item["check"] == "input is UTF-8"]


def test_an_unreadable_source_is_reported_without_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "resume"]) == 0

    def refuse(*_args, **_kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr("pathlib.Path.read_text", refuse)
    capsys.readouterr()
    assert main(["lint", "--json"]) == 1
    results = json.loads(capsys.readouterr().out)["results"]
    unreadable = [item for item in results if item["check"] == "input readable"]
    assert unreadable and "permission denied" in unreadable[0]["detail"]


def test_a_full_render_and_verification_opens_no_network_connection(tmp_path, monkeypatch, capsys):
    """The privacy claim, enforced rather than asserted.

    The guard replaces the socket constructors this process would have to call
    to reach a network, then runs the documented quick start. Pandoc and Typst
    are separate processes, so it cannot see inside them; what it proves is
    that pressume's own code, and every library it calls in-process to render,
    reopen, and check the files, never opens a connection.
    """
    import socket

    def refuse(*_args, **_kwargs):
        raise AssertionError("pressume attempted a network connection")

    monkeypatch.chdir(tmp_path)
    assert main(["new", "resume"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    assert main(["render", "--formats", "pdf,txt,docx", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["failed"] == 0
    assert main(["check", "--formats", "pdf,txt,docx", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["failed"] == 0


def test_txt_only_project_renders_and_checks_without_pdf(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pressume.toml").write_text(
        '[output]\nformats = ["txt"]\n\n[[documents]]\nfile = "Resume.md"\n',
        encoding="utf-8",
    )
    assert main(["new", "resume"]) == 0
    capsys.readouterr()
    assert main(["render", "--json"]) == 0
    capsys.readouterr()
    assert (tmp_path / "renders" / "Resume.txt").exists()
    assert not (tmp_path / "renders" / "Resume.pdf").exists()
    assert main(["check", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["failed"] == 0


def test_empty_project_json_is_machine_readable(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["render", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["failed"] == 1


def test_render_error_has_no_traceback(tmp_path, monkeypatch, capsys):
    import pressume.formats
    from pressume.errors import RenderError

    monkeypatch.chdir(tmp_path)
    assert main(["new", "resume"]) == 0
    monkeypatch.setattr(
        pressume.formats,
        "render_pdf",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RenderError("renderer unavailable")),
    )
    assert main(["render", "--formats", "pdf"]) == 3
    captured = capsys.readouterr()
    assert "renderer unavailable" in captured.err
    assert "Traceback" not in captured.err


def test_doctor_reports_versions_and_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "pressume" in output
    assert "Python" in output
    assert "Source:" in output
    assert tmp_path.name in output

    assert main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["pressume"]
    assert payload["source_found"] is True
    # pdfminer.six ships with the tool, so a second extractor always exists.
    assert any("pdfminer.six" in item for item in payload["independent_extractors"])


def test_doctor_fails_when_configured_source_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pressume.toml").write_text('[paths]\nsource_dir = "missing"\n', encoding="utf-8")
    assert main(["doctor"]) == 1
    assert "missing" in capsys.readouterr().out


def test_refdoc_creates_parent_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pressume.toml").write_text(
        '[paths]\nreference_docx = "styles/reference.docx"\n', encoding="utf-8"
    )
    assert main(["refdoc"]) == 0
    assert (tmp_path / "styles" / "reference.docx").exists()


def test_requested_document_cannot_escape_source_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["render", "../private.md"]) == 2
