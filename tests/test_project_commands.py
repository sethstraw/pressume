"""Project-level commands end to end: list, preview, check, and clean.

These exercise the paths a working session actually uses: seeing the plan,
watching a render, re-verifying yesterday's output, and pruning renames.
"""

import json

from pressume.cli import main


def start_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "resume"]) == 0


def test_list_shows_the_document_plan_as_table_and_json(tmp_path, monkeypatch, capsys):
    start_project(tmp_path, monkeypatch)
    assert main(["list"]) == 0
    table = capsys.readouterr().out
    assert "Resume.md" in table and "pdf" in table

    assert main(["list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["documents"][0]["source"] == "Resume.md"
    assert payload["documents"][0]["lint_only"] is False


def test_preview_renders_once_and_opens_the_pdf(tmp_path, monkeypatch, capsys):
    start_project(tmp_path, monkeypatch)
    opened: list[str] = []
    monkeypatch.setattr("pressume.cli.webbrowser.open", lambda url: opened.append(url) or True)
    assert main(["preview", "--open"]) == 0
    capsys.readouterr()
    assert len(opened) == 1
    assert opened[0].endswith("Resume.pdf")


def test_check_reverifies_and_reports_a_missing_artifact(tmp_path, monkeypatch, capsys):
    start_project(tmp_path, monkeypatch)
    capsys.readouterr()
    assert main(["render", "--json"]) == 0
    capsys.readouterr()
    assert main(["check", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["failed"] == 0

    (tmp_path / "renders" / "Resume.txt").unlink()
    assert main(["check", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    missing = [item for item in payload["results"] if item["check"] == "txt: exists"]
    assert missing and missing[0]["result"] == "fail"


def test_clean_reports_nothing_stale_on_a_fresh_project(tmp_path, monkeypatch, capsys):
    start_project(tmp_path, monkeypatch)
    capsys.readouterr()
    assert main(["render", "--json"]) == 0
    capsys.readouterr()
    assert main(["clean", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["detail"] == "no stale tracked output"


def test_inspect_warns_when_the_pdf_has_not_been_rendered(tmp_path, monkeypatch, capsys):
    start_project(tmp_path, monkeypatch)
    capsys.readouterr()
    assert main(["inspect", "--json"]) == 0  # advisory findings never fail a run
    payload = json.loads(capsys.readouterr().out)
    balance = [item for item in payload["results"] if "page balance" in item["check"]]
    assert balance and balance[0]["result"] == "warn"
    assert "Resume.pdf" in balance[0]["detail"]


def test_source_snapshot_tolerates_files_vanishing_mid_scan(tmp_path):
    from pressume.cli import _source_snapshot

    (tmp_path / "Resume.md").write_text("# X\n", encoding="utf-8")
    snapshot = _source_snapshot(tmp_path)
    assert len(snapshot) == 1
    (tmp_path / "Resume.md").unlink()
    assert _source_snapshot(tmp_path) == ()
