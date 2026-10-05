"""Shared test environment.

Rich resolves its console width from the environment, and in CI there is no
terminal, so tables fold long details at 80 columns. Where a fold lands
depends on content length, including the runner's temporary-path names, which
made substring assertions pass or fail by coincidence per platform. Pinning a
generous width makes every rendered message a single line everywhere, so
tests assert on content, never on wrapping luck.
"""

import geometry_baseline  # noqa: F401  pins the bundled pandoc before any test renders
import pytest


@pytest.fixture(autouse=True)
def wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a wide, deterministic console."""
    monkeypatch.setenv("COLUMNS", "400")
