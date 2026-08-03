# pressume

Render polished, verified resumes and CVs from portable Markdown.

![Resume template rendered with the default modern theme](docs/resume-example.png)

pressume turns plain Markdown into a single-column PDF, an ATS-friendly text
companion, and, when requested, a styled Word document. It then reopens what it
created and verifies the details document conversion is most likely to damage:
text order, contact details, headings, dates, protected wording, page targets,
metadata, language tags, links, and accessible PDF structure.

The verifier measures output structure and extracted text. It cannot certify
the undocumented behavior of every applicant-tracking system or predict how an
employer ranks a resume.

## Install

pressume is GitHub-distributed and does not require PyPI. [uv](https://docs.astral.sh/uv/)
installs the command in an isolated environment, which is the supported way to
use it with Homebrew's managed Python:

```bash
uv tool install git+https://github.com/sethstraw/pressume.git
```

For a local clone, including before the repository is hosted, use:

```bash
uv tool install --force --editable ~/Developer/pressume
```

Run `uv tool update-shell` once if `pressume` is not yet on your `PATH`.
Pandoc, Typst, two independent PDF text extractors, the layout-geometry
parser, Word support, and all three curated typefaces ship with the tool; a
document project does not need its own renderer or fonts, and every dependency
carries an MIT-compatible license.

## Quick start

```bash
mkdir my-resume && cd my-resume
pressume new resume
pressume preview Resume.md --open
```

Edit `Resume.md`, then create verified deliverables:

```bash
pressume render
```

The default source is the current directory and the default destination is
`./renders`. Point either location somewhere else for one invocation:

```bash
pressume render \
  --source ~/Documents/resumes \
  --output ~/Desktop/applications
```

Configuration is optional. Without it, pressume discovers Markdown files in
the current directory and derives each candidate's name, contact details, and
section order from the document itself.

## Commands

| Command | Purpose |
| --- | --- |
| `pressume new resume` | Create a conforming resume template. |
| `pressume new cv` | Create a longer-form CV template. |
| `pressume preview` | Render locally, optionally open the PDF and watch for edits. |
| `pressume lint` | Validate Markdown without rendering. |
| `pressume render` | Validate, render, independently verify, and commit outputs. |
| `pressume check` | Recheck existing deliverables without rendering. |
| `pressume inspect` | Report advisory density, readability, and page-balance findings. |
| `pressume list` | Show selected sources, output names, formats, profiles, and page targets. |
| `pressume clean` | Preview stale tracked outputs; add `--apply` to remove only those files. |
| `pressume init` | Create a documented optional configuration. |
| `pressume refdoc` | Generate a Word reference document from the selected theme. |
| `pressume doctor` | Show versions, paths, theme, extractors, and project health. |

Run `pressume COMMAND --help` for command-specific options. Document commands
accept individual filenames and `--json` for automation:

```bash
pressume render Resume.md --formats pdf
pressume inspect Resume.md --json
```

## Design system

The default `modern` theme uses Source Sans 3 with a restrained navy accent,
clear section hierarchy, compact contact metadata, readable role transitions,
and visually distinct publication blocks. Two additional coordinated themes
ship with the package:

- `technical`: IBM Plex Sans with a slightly tighter engineering-oriented feel;
- `traditional`: Source Serif 4 for academic and conservative settings.

Preview a theme or spacing density without changing configuration:

```bash
pressume preview Resume.md --theme technical --density spacious --open
```

`compact`, `balanced`, and `spacious` adjust the design as a system instead of
changing isolated margins or font sizes. Explicit font, size, margin, accent,
paper, language, and region overrides remain available when a project needs
them.

## Safe rendering

A verified render is transactional:

1. All selected sources pass the configured document contract.
2. Every requested artifact is built in a temporary directory.
3. PDF, TXT, and DOCX files are reopened and checked independently.
4. Existing outputs are replaced only after the complete selection passes.
5. If the final file or manifest update fails, every prior artifact is restored.

The output manifest remembers generated filenames so a later rename or format
change can be cleaned safely. `pressume clean` is a preview; only
`pressume clean --apply` removes files, and it never deletes untracked work.

## Configuration

Run `pressume init` for a fully commented starter file. The configuration is a
strict overlay: omitted values keep sensible defaults, while unknown keys and
wrong types fail with their exact TOML path.

```toml
[paths]
source_dir = "documents"
output_dir = "build"

[output]
formats = ["pdf", "txt"]

[style]
theme = "modern"
density = "balanced"
paper = "us-letter"
language = "en"
region = "US"
pdf_standard = "ua-1"

[[documents]]
file = "Resume.md"
min_pages = 1
max_pages = 2
output_name = "Jane_Doe_Resume"
title = "Jane Doe - Data Architect Resume"
author = "Jane Doe"
description = "Resume for senior data architecture roles"
keywords = ["data architecture", "healthcare"]

[[documents]]
file = "Academic-CV.md"
profile = "academic"
formats = ["pdf", "docx"]
required_strings = ["ORCID: 0000-0000-0000-0000"]
forbidden_strings = ["DRAFT"]

[document]
policy = "standard"
warning_rules = []
disabled_rules = []

[checks]
ascii_only = false
forbid_smart_punctuation = false
date_style = "long"
protected_strings = ["Senior Clinical Data Architect"]
```

### Paths, formats, and filenames

Relative configuration paths resolve from `pressume.toml`; command-line paths
resolve from the current directory and take precedence. Supported formats are
`pdf`, `txt`, and `docx`. Project formats can be overridden per document or for
one command. `output_name` changes a deliverable without renaming its source.

Use an exact `pages` target when pagination is part of the document contract,
or `min_pages` and `max_pages` when several lengths are acceptable.

### Policies and profiles

The default contract favors a conventional one-column resume. Built-in
`standard`, `academic`, `international`, and `minimal` policies tune common
expectations. A rule can be demoted to an advisory with `warning_rules` or
disabled explicitly when it does not fit the project.

Named profiles can further override section vocabulary, required sections,
labeled or dated sections, citation fields, heading depth, and contact-block
placement. Validation rejects contradictory profiles and colliding filenames.

### Exact wording and international content

- `required_strings` must always appear exactly.
- `forbidden_strings` must not appear.
- `protected_strings` require the complete configured phrase when its first
  word appears, which protects official titles without forcing every title into
  every tailored resume.

Character policy, smart punctuation, date style, paper, document language, and
region are independent. This allows accented names and international addresses
without weakening unrelated checks. For writing systems outside the bundled
font coverage, select an installed font or add font directories under `[paths]`.

## Delivery checks

PDF verification includes page targets, two independent text extractors
(pypdf always, cross-checked against Poppler when installed or the bundled
pdfminer.six otherwise), character policy, exact strings, contact placement,
section order, date style, metadata, language, real hyperlink annotations,
PDF/UA structure, and geometric clearance after names, section headings, and
organization headings. TXT uses the
same text and exact-string policy. DOCX is reopened as OOXML and checked for
linear structure, ATS text order, metadata privacy, and embedded links; its
pagination is intentionally not certified because Word-compatible applications
paginate independently.

Bare email addresses, phone numbers, LinkedIn/GitHub/ORCID profiles, and DOI
identifiers become clickable without changing their visible text. Metadata is
derived by default and can be overridden per document.

`pressume inspect` is intentionally advisory. It highlights long bullets,
dense front matter, repeated openers, crowded pages, stranded headings, and
sparse endings without blocking an otherwise valid deliverable.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Command completed and all required checks passed. |
| `1` | Verification or a safe refusal failed. |
| `2` | Arguments or configuration were invalid. |
| `3` | Rendering or file-system work failed. |
| `130` | Command was interrupted. |

Reports go to stdout and progress/errors go to stderr. JSON mode keeps stdout
machine-readable.

## Development

```bash
git clone https://github.com/sethstraw/pressume.git
cd pressume
uv sync --all-extras --dev
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy
uv run pytest --cov --cov-report=term-missing
```

The code favors explicit types, small composable functions, and PEP 257
Google-style docstrings. See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete
quality and documentation standards.

## Privacy and network behavior

pressume processes only the local files and paths you select. Rendering,
checking, preview watching, and cleanup make no network requests and do not
upload resume content. Opening a generated preview uses the local system viewer.

## License

[MIT](LICENSE). Source Sans 3, IBM Plex Sans, and Source Serif 4 are distributed
under their bundled SIL Open Font Licenses.
