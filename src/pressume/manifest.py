"""Track generated artifacts so stale output can be identified safely."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

MANIFEST_NAME = ".pressume-manifest.json"

# Generated filenames grouped by the Markdown source that produced them.
Manifest = dict[str, list[str]]


def load_manifest(output_dir: Path) -> Manifest:
    """Load a manifest; a missing file represents a project not rendered yet."""
    path = output_dir / MANIFEST_NAME
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    entries = raw.get("documents", {}) if isinstance(raw, dict) else {}
    if not isinstance(entries, dict):
        return {}
    safe: Manifest = {}
    for source, artifacts in entries.items():
        if (
            isinstance(source, str)
            and isinstance(artifacts, list)
            and all(isinstance(item, str) and Path(item).name == item for item in artifacts)
        ):
            safe[source] = artifacts
    return safe


def write_manifest(output_dir: Path, manifest: Manifest) -> None:
    """Atomically replace the generated-artifact manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            {"version": 1, "documents": manifest},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    descriptor, scratch_name = tempfile.mkstemp(prefix=".pressume-manifest-", dir=output_dir)
    scratch = Path(scratch_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(scratch, output_dir / MANIFEST_NAME)
    finally:
        scratch.unlink(missing_ok=True)


def stale_artifacts(output_dir: Path, expected: dict[str, list[str]]) -> list[Path]:
    """Return tracked artifacts no longer expected by current configuration."""
    manifest = load_manifest(output_dir)
    expected_names = {name for names in expected.values() for name in names}
    tracked_names = {name for names in manifest.values() for name in names}
    return [
        output_dir / name
        for name in sorted(tracked_names - expected_names)
        if (output_dir / name).is_file()
    ]
