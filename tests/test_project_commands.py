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
    assert opened[0].endswith("/renders/preview/Resume.pdf")


def test_preview_never_replaces_a_deliverable(tmp_path, monkeypatch, capsys):
    start_project(tmp_path, monkeypatch)
    assert main(["render"]) == 0
    renders = tmp_path / "renders"
    before = {path.name: path.read_bytes() for path in renders.iterdir() if path.is_file()}

    assert main(["preview", "--theme", "traditional"]) == 0
    capsys.readouterr()

    after = {path.name: path.read_bytes() for path in renders.iterdir() if path.is_file()}
    assert after == before
    assert (renders / "preview" / "Resume.pdf").is_file()


def test_colliding_output_names_are_refused_before_anything_is_written(
    tmp_path, monkeypatch, capsys
):
    start_project(tmp_path, monkeypatch)
    (tmp_path / "Jane_Doe_Resume.md").write_text(
        (tmp_path / "Resume.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "pressume.toml").write_text(
        '[[documents]]\nfile = "Resume.md"\noutput_name = "Jane_Doe_Resume"\n', encoding="utf-8"
    )
    prior = tmp_path / "renders" / "Jane_Doe_Resume.txt"
    prior.parent.mkdir()
    prior.write_text("prior deliverable", encoding="utf-8")
    capsys.readouterr()

    assert main(["render", "Resume.md", "jane_doe_resume.md"]) == 2
    assert "same output name" in capsys.readouterr().err
    assert prior.read_text(encoding="utf-8") == "prior deliverable"
    assert sorted(path.name for path in prior.parent.iterdir()) == ["Jane_Doe_Resume.txt"]


def test_clean_leaves_explicit_renders_outside_the_plan(tmp_path, monkeypatch, capsys):
    """An unconfigured document or an extra format rendered on request is not stale."""
    start_project(tmp_path, monkeypatch)
    (tmp_path / "Other.md").write_text(
        (tmp_path / "Resume.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "pressume.toml").write_text('[[documents]]\nfile = "Resume.md"\n', encoding="utf-8")
    assert main(["render"]) == 0
    assert main(["render", "Other.md"]) == 0
    assert main(["render", "--formats", "docx"]) == 0
    capsys.readouterr()

    assert main(["clean", "--json"]) == 0
    details = [item["detail"] for item in json.loads(capsys.readouterr().out)["results"]]
    assert details == ["no stale tracked output"]
    assert main(["check", "--json"]) == 0
    results = json.loads(capsys.readouterr().out)["results"]
    assert not [item for item in results if item["check"] == "output manifest"]

    assert main(["clean", "--apply", "--json"]) == 0
    renders = tmp_path / "renders"
    for name in ("Other.pdf", "Other.txt", "Resume.docx", "Resume.pdf", "Resume.txt"):
        assert (renders / name).is_file(), name


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


def test_clean_removes_only_what_the_manifest_recorded(tmp_path, monkeypatch, capsys):
    """`clean --apply` deletes generated files and nothing else.

    A user's own file living beside the output is the case that matters: the
    manifest is the only list pressume is allowed to delete from.
    """
    start_project(tmp_path, monkeypatch)
    capsys.readouterr()
    assert main(["render", "--json"]) == 0
    capsys.readouterr()

    renders = tmp_path / "renders"
    keepsake = renders / "cover-letter.pdf"
    keepsake.write_bytes(b"not pressume's file")
    (tmp_path / "pressume.toml").write_text(
        '[output]\nformats = ["pdf"]\n\n[[documents]]\nfile = "Resume.md"\n', encoding="utf-8"
    )

    assert main(["clean", "--apply", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    removed = [item["detail"] for item in payload["results"]]
    assert any("removed: Resume.txt" in detail for detail in removed)
    assert keepsake.read_bytes() == b"not pressume's file"
    assert (renders / "Resume.pdf").exists()
    assert not (renders / "Resume.txt").exists()


def test_check_warns_when_the_manifest_still_tracks_a_renamed_output(tmp_path, monkeypatch, capsys):
    start_project(tmp_path, monkeypatch)
    capsys.readouterr()
    assert main(["render", "--json"]) == 0
    capsys.readouterr()
    (tmp_path / "pressume.toml").write_text(
        '[output]\nformats = ["pdf"]\n\n[[documents]]\nfile = "Resume.md"\n', encoding="utf-8"
    )

    assert main(["check", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    stale = [item for item in payload["results"] if item["check"] == "output manifest"]
    assert stale and stale[0]["result"] == "warn"
    assert "Resume.txt" in stale[0]["detail"]


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
