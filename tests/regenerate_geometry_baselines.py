"""Record the text-geometry baselines.

This script is the only thing in the repository that writes into
``tests/baselines``. The comparison code in ``geometry_baseline.py`` has no
write path at all, so a failing comparison cannot rewrite the file it failed
against; regenerating is a decision a person makes here, on purpose.

    uv run python tests/regenerate_geometry_baselines.py

Regenerate when a layout change was intended and you can say in the pull
request what moved and why. A baseline diff you cannot explain is a report
about the change you just made, not a file to overwrite.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import geometry_baseline as geometry


def record(scratch: Path) -> dict[str, dict[str, geometry.Geometry]]:
    """Render and measure every configuration, grouped by fixture."""
    recorded: dict[str, dict[str, geometry.Geometry]] = {}
    for fixture, theme, paper in geometry.configurations():
        markdown = geometry.read_fixture(fixture)
        pdf = geometry.render(markdown, theme, paper, scratch / f"{fixture}-{theme}-{paper}.pdf")
        recorded.setdefault(fixture, {})[f"{theme} {paper}"] = geometry.measure(pdf, theme)
    return recorded


def main() -> int:
    """Write every baseline file, and the renderer versions behind them."""
    if "pytest" in sys.modules:
        print(
            "regeneration is a deliberate command, not something a test run does",
            file=sys.stderr,
        )
        return 2

    geometry.BASELINE_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pressume-geometry-") as scratch:
        recorded = record(Path(scratch))
    for fixture, sections in recorded.items():
        path = geometry.BASELINE_DIR / f"{fixture}.txt"
        path.write_text(geometry.format_baseline(sections), encoding="utf-8")
        pages = sum(page.pages for page in sections.values())
        print(f"wrote {path.name}: {len(sections)} configuration(s), {pages} page(s)")

    versions = geometry.running_renderers()
    geometry.RENDERER_FILE.write_text(
        "# Renderer versions these baselines were produced with. Text geometry is\n"
        "# only comparable against the same versions; see geometry_baseline.py.\n"
        + "".join(f"{name} {value}\n" for name, value in sorted(versions.items())),
        encoding="utf-8",
    )
    named = ", ".join(f"{name} {value}" for name, value in sorted(versions.items()))
    print(f"wrote {geometry.RENDERER_FILE.name}: {named}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
