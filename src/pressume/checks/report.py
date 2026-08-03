"""High-visibility check reporting.

Every check produces a CheckResult; the report prints all of them, pass and
fail alike, so a green run shows exactly what was verified rather than just
staying silent.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import partial

from rich.console import Console
from rich.table import Table


class Severity(str, Enum):
    """Outcome of one independently reportable verification check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    """One check result associated with a source document."""

    document: str
    check: str
    severity: Severity
    detail: str = ""


def grader(document: str, check: str) -> Callable[..., CheckResult]:
    """Bind a document and check name into a verdict constructor.

    Every check body then reads ``verdict(Severity.PASS, "detail")``, keeping
    the code about the decision instead of result plumbing.
    """
    return partial(CheckResult, document, check)


STYLE = {
    Severity.PASS: ("PASS", "green"),
    Severity.WARN: ("WARN", "yellow"),
    Severity.FAIL: ("FAIL", "bold red"),
}


def emit(results: list[CheckResult], as_json: bool = False) -> bool:
    """Report results and return True when nothing failed.

    Human output is the styled table on stdout. Machine output (--json) is a
    plain JSON document on stdout with no styling, fit for piping and CI.
    """
    if not as_json:
        return print_report(results)

    fails = sum(1 for item in results if item.severity is Severity.FAIL)
    warns = sum(1 for item in results if item.severity is Severity.WARN)
    payload = {
        "results": [
            {
                "document": item.document,
                "check": item.check,
                "result": item.severity.value,
                "detail": item.detail,
            }
            for item in results
        ],
        "summary": {
            "passed": len(results) - fails - warns,
            "warnings": warns,
            "failed": fails,
        },
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return fails == 0


def print_report(results: list[CheckResult], console: Console | None = None) -> bool:
    """Print the full check table; return True when nothing failed."""
    console = console or Console()
    table = Table(title="Verification report", show_lines=False, pad_edge=False)
    table.add_column("Document", style="cyan", no_wrap=True)
    table.add_column("Check", no_wrap=True)
    table.add_column("Result", no_wrap=True)
    table.add_column("Detail", overflow="fold")

    for result in results:
        label, style = STYLE[result.severity]
        table.add_row(result.document, result.check, f"[{style}]{label}[/{style}]", result.detail)
    console.print(table)

    fails = sum(1 for item in results if item.severity is Severity.FAIL)
    warns = sum(1 for item in results if item.severity is Severity.WARN)
    passes = len(results) - fails - warns
    summary_style = "bold red" if fails else ("yellow" if warns else "green")
    console.print(
        f"[{summary_style}]{passes} passed, {warns} warnings, {fails} failed[/{summary_style}]"
    )
    return fails == 0
