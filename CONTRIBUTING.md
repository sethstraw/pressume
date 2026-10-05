# Contributing

Contributions are welcome, including small fixes, documentation improvements,
and reports from people who are not professional software developers.

pressume began as a personal, heavily AI-assisted project. Claude and ChatGPT
have been used extensively in its implementation. AI-assisted contributions
are therefore not excluded or treated as unusual. If a tool produced a
substantial part of a change, say so in the pull request, make sure you
understand the behavior being changed, and verify the result yourself. The
author of a pull request remains responsible for what it contains.

## Set up the project

Install [uv](https://docs.astral.sh/uv/), then:

```bash
git clone https://github.com/sethstraw/pressume.git
cd pressume
uv sync --locked --all-groups
```

`--locked` fails if `uv.lock` and `pyproject.toml` have drifted. If you change
a dependency, run `uv lock` and commit the result with the change.

Run the verification gate, the same script CI runs. It covers the licence
audit, formatting, linting, strict typing, and the tests with coverage, and
reports every failing step at the end:

```bash
bash scripts/gate.sh
uv build
```

For rendering changes, also render the bundled templates and inspect the files:

```bash
uv run pressume render --source src/pressume/templates --output /tmp/pressume-smoke
```

## Layout baselines

Rendered PDFs are compared against recorded text geometry. Five invented
fixtures cross three themes and two paper sizes, thirty configurations in all,
and each one records its page count, its text region, and the box, size, and
font of every text line. Coordinates are rounded to 0.1 pt, which is below
anything a reader can see and above the last-digit differences two machines can
produce. The whole matrix runs in the ordinary test suite and costs about ten
seconds.

Each configuration is asserted twice. The recorded baseline still describes
what the renderer produces, and the page holds invariants that need no baseline
at all: nothing runs past the text region or off the paper, no heading collides
with the line beneath it, no line crowds within 2.0 pt of the section heading
beneath it, no heading is stranded at the bottom of a page, no
final page is nearly blank, and headings still outrank body text in size and
weight.

The baselines live in `tests/baselines` and are data, not code. Read them in a
diff. Nothing in the comparison can write them. Recording is one deliberate
command:

```bash
uv run python tests/regenerate_geometry_baselines.py
```

Run it when you changed a theme token, a document builder, or a fixture on
purpose and can say in the pull request what moved and why. Do not run it to
make a surprise go away: a baseline diff you cannot explain is the check
working. A failure names the fixture, the configuration, the page, the line,
and how far it moved, and leaves the rendered PDF and the observed geometry in
pytest's temporary directory so you can open them.

These baselines are pinned to a renderer. The theme fonts are bundled, so glyph
metrics are fixed, but `typst` and `pypandoc-binary` are floor pinned and a
minor release of either can move every line on every page. The versions behind
the recorded files are in `tests/baselines/renderer.txt`. When the running
versions differ, one test fails and names both, and the thirty comparisons
skip, so an upgrade arrives as a single explicable failure instead of a wall of
diffs. Confirm the difference is only the upgrade, then regenerate.

DOCX is not covered and cannot be. `docxstyle.py` names fonts and the reader's
machine resolves them, so a Word file is not visually reproducible off the
machine that opens it. The PDF is the document of record.

## What cannot change

- **Rendering without verification is not the product.** The checks on page
  targets, extracted text order, exact wording, links, metadata, accessibility
  structure, and layout relationships are the reason this exists. Do not weaken
  a check to make a document pass.
- **Builds are atomic.** Documents are built in a temporary location and replace
  existing output only on success, so one failure never leaves a partly updated
  set behind.
- **The manifest is how cleanup stays safe.** pressume deletes only files it
  recorded creating. Preserve that invariant.
- **pressume renders; it does not judge.** It does not score, tailor, or submit.

## What makes a useful change

- Solve a specific user problem or documented defect.
- Keep the change as small as the problem allows.
- Prefer straightforward code and explicit behavior over new layers or
  abstractions.
- Add a regression test when fixing a bug.
- Keep existing output safe when rendering or verification fails.
- Reject invalid configuration clearly instead of guessing what was intended.
- Update the README, help text, templates, and changelog when user-visible
  behavior changes.
- For visual changes, inspect the rendered PDF and DOCX rather than relying only
  on tests or page count.

The project is deliberately strict about the files it produces. Clear behavior,
readable code, and evidence that the result works are more useful than extra
abstraction.

## Pull requests and issues

Describe:

1. the problem a user sees;
2. what changed;
3. how you tested it;
4. any remaining limitation or uncertainty;
5. whether substantial AI assistance was used.

Do not include real resumes, personal contact information, credentials, API
keys, or generated application documents. Use small synthetic examples.

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report security issues
privately as described in [SECURITY.md](SECURITY.md).
