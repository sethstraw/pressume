# Contributing

Thanks for helping make pressume more dependable or useful. Small, focused
changes with tests are easiest to review.

## Development setup

Install [uv](https://docs.astral.sh/uv/) and clone the repository:

```bash
git clone https://github.com/sethstraw/pressume.git
cd pressume
uv sync --all-extras --dev
```

Run the complete local gate before opening a pull request:

```bash
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy
uv run pytest --cov --cov-report=term-missing
uv build
uv run twine check dist/*
uv run check-wheel-contents dist/*.whl
uv run pressume render --source src/pressume/templates --output /tmp/pressume-smoke
```

CI repeats these checks and exercises supported Python versions on Linux,
macOS, and Windows.

## Design principles

- Prefer names, types, small functions, and explicit data flow over explanatory
  comments.
- Comments explain a decision, invariant, or external constraint, not what the
  next line already says.
- Public modules, classes, functions, and methods follow PEP 257 with
  Google-style docstrings. Document arguments, return values, and exceptions
  when the signature does not make them obvious.
- User-facing failures are actionable and never expose a traceback for an
  expected configuration, rendering, or file-system problem.
- Verified rendering is transactional. A failing run must not damage existing
  deliverables.
- Configuration is strict. Never turn a misspelling into a silent no-op.
- Defaults should serve a new user; specialized behavior belongs behind an
  explicit setting or profile.
- Visual behavior belongs in semantic components and coordinated theme tokens,
  not document-specific string checks or one-off layout adjustments.
- PDF and DOCX verification must use a reader or renderer independent from the
  component that created the artifact.
- Source and tests remain ASCII. Use Unicode escapes in tests that exercise
  international content.

## Tests and behavior changes

Add a regression test before fixing a reported defect. Changes to configuration
or command behavior should cover both success and failure paths, including exit
codes and stdout/stderr discipline. Changes to the document contract must keep
the bundled resume and CV templates valid.

Typography or spacing changes require three levels of evidence: semantic unit
tests, geometry assertions for hierarchy and page bounds, and rendered-page
inspection for PDF and DOCX. Test compact and spacious density extremes and at
least one non-default theme. Do not accept a page-count change as an incidental
side effect; make the new target explicit.

Update `CHANGELOG.md` under **Unreleased** for visible changes. Avoid weakening
a check merely to make one document pass; change the rule explicitly, make it
configurable where appropriate, and explain the reason.

## Pull requests

Keep each pull request centered on one problem. Describe the user impact, the
design choice, and how you verified it. Do not include real resumes, personal
contact details, credentials, or generated application documents in fixtures,
issues, or pull requests.
