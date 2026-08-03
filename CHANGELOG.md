# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-08-02

Initial release.

### Added

- Markdown to PDF rendering through Pandoc and Typst, with the PDF as the
  document of record: tagged, single column, US Letter or A4, with document
  metadata, keywords, language, region, and a selectable PDF standard
  including PDF/UA.
- Coordinated `modern`, `technical`, and `traditional` themes backed by
  bundled Source Sans 3, IBM Plex Sans, and Source Serif 4 typefaces, with
  `compact`, `balanced`, and `spacious` density settings and one-command
  theme and density overrides. Every dependency and bundled asset carries an
  MIT-compatible license.
- Semantic rendering components for contact details, logistics, role
  metadata, skill groups, records, and publication citations, which render as
  visually separated blocks with hanging structure.
- Plain-text companion output and Word output on demand: DOCX is generated,
  restyled to the theme, scrubbed of private metadata (custom properties and
  revision-session identifiers), reopened, and verified as linear OOXML with
  embedded links; `pressume refdoc` generates a matching Pandoc reference
  document.
- A document contract enforced at every render, with lint failures as render
  failures: one H1 name line, a contact paragraph, a section vocabulary in
  fixed order, scoped role headings, labeled skills lines, standardized role
  metadata and dated entries, fixed citation field labels, and the applicable
  markdownlint rules under their standard names. Built-in `standard`,
  `academic`, `international`, and `minimal` policies with per-rule warning
  and disable overlays.
- Verification of the delivered files: exact or ranged page targets,
  character policy with named offenders, required, protected, and forbidden
  strings, ATS parse-back of name, contact, section order, and date style,
  metadata and language checks, real hyperlink annotations, PDF/UA structure,
  geometric clearance after names and headings, and agreement between two
  independent text extractors (pypdf cross-checked against Poppler when
  installed, the bundled pdfminer.six otherwise).
- Transactional rendering: sources validate first, artifacts render and
  verify in staging, existing output is replaced only after every selected
  document passes, and a failed replacement restores every prior artifact.
- Automatic links for visible email, phone, profile, ORCID, and DOI text,
  preserving the displayed characters an extractor consumes.
- Zero-configuration operation: without a config file, every Markdown resume
  in the current folder renders to `renders/`, and contact and section
  checks derive their expected values from the documents themselves. The
  optional TOML overlay adds page targets, exact strings, per-document
  formats and metadata, custom vocabularies, and named profiles, and rejects
  unknown keys loudly with dotted paths.
- Commands: `render`, `preview` (with watch and open modes), `check`,
  `lint`, `inspect` for advisory readability and page-balance findings,
  `list` for the resolved document plan, manifest-aware `clean`, `init`,
  `new` with bundled lint-clean resume and CV templates, `refdoc`, and
  `doctor`; `--json` machine-readable reports and documented stable exit
  codes throughout.

[Unreleased]: https://github.com/sethstraw/pressume/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sethstraw/pressume/releases/tag/v0.1.0
