"""Lint the Markdown source before rendering.

These catch constructs that render as visible defects: an inline code span
silently becomes a monospace run mid-sentence, and smart punctuation in the
source defeats the ASCII guarantee downstream.
"""

from __future__ import annotations

from pressume.checks.report import CheckResult, Severity
from pressume.checks.textrules import (
    describe_character,
    smart_punctuation_found,
    unexpected_non_ascii,
)
from pressume.config import Checks


def check_source(name: str, markdown: str, checks: Checks) -> list[CheckResult]:
    """Check Markdown characters and constructs that produce fragile output."""
    results: list[CheckResult] = []

    backtick_lines = [
        str(number) for number, line in enumerate(markdown.splitlines(), start=1) if "`" in line
    ]
    if backtick_lines:
        results.append(
            CheckResult(
                name,
                "source: no code spans",
                Severity.FAIL,
                "Backticks render as a mismatched monospace font. "
                f"Lines: {', '.join(backtick_lines)}",
            )
        )
    else:
        results.append(CheckResult(name, "source: no code spans", Severity.PASS))

    if checks.ascii_only:
        offending = unexpected_non_ascii(markdown, set(checks.allowed_characters))
        detail = ", ".join(describe_character(character) for character in offending)
        results.append(
            CheckResult(
                name,
                "source: ASCII only",
                Severity.FAIL if offending else Severity.PASS,
                f"Found {detail}" if offending else "",
            )
        )
    if checks.forbid_smart_punctuation:
        offending = smart_punctuation_found(markdown)
        detail = ", ".join(describe_character(character) for character in offending)
        results.append(
            CheckResult(
                name,
                "source: no smart punctuation",
                Severity.FAIL if offending else Severity.PASS,
                f"Found {detail}" if offending else "",
            )
        )
    return results
