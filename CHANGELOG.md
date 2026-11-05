# Changelog

Notable user-visible changes are recorded here. This project uses
[Semantic Versioning](https://semver.org/) and follows the general structure of
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

Fixes land on `main` until a release is tagged.

### Added

- A `letter` policy for cover letters, chosen through a profile. It keeps the
  name and contact line and allows no sections. Letter paragraphs are spaced
  apart, and the PDF title reads `Name - Letter`.
- `pressume new letter` writes a starter `Letter.md`.
- The visual check measures the line above each section heading. It fails
  under 2.0 pt of clearance and warns under 3.0 pt.
- With an exact `pages` target, `pressume inspect` flags a final page whose
  text spans under 85% of the median height of earlier pages.
- Theme screenshots in the README.
- A GitHub Pages landing page, built from `docs/site`.
- A test blocks this process's socket calls around a full render and check.
- Visual regression by recorded text geometry. Five fixtures render in every
  theme and both paper sizes, and each of the thirty results is compared line
  by line against a baseline under `tests/baselines`. It catches overflow,
  clipping, heading collisions, stranded headings, page-count changes, blank
  final pages, and spacing or font drift.
- Baselines are written only by `tests/regenerate_geometry_baselines.py`. When
  the Typst or Pandoc version differs from the recorded one, one test fails by
  name and the comparisons skip.
- Tests for the paths that protect delivered files: a failed check leaves the
  old files byte-identical, and `clean --apply` leaves files it did not create.

### Changed

- `style.paper` accepts only `us-letter` and `a4`, and applies to both PDF and
  Word. Other sizes had reached the PDF but left Word at US Letter.
- The reference DOCX and the DOCX styling pass share one function, so both
  carry the same page size, font, and spacing.
- `pressume init` documents `profile`, `lint_only`, `ordered_list_sections`,
  `dated_sections`, `citation_field_labels`, `max_heading_level`, and
  `contact_after_name`.

- A resume or letter no longer needs an email address, and a resume may skip
  the contact line, so a public copy can leave out contact details.
- The visual check measures every pair of body lines, not only lines in
  record sections. Two lines closer than 0.25 pt fail.
- `preview` writes to a preview folder apart from the deliverables.
- `clean` keeps files from an explicit render.
- The DOCX conversion runs Pandoc with `--sandbox`, so a local image no longer
  reaches a Word file. The PDF never loaded local images.
- The community files moved under `.github/`.
- The README no longer claims a ClearScout integration.

### Fixed

- cryptography is held at 50 or later everywhere except Intel Macs, which keep
  the final release that ships an Intel wheel.
- Bold labels and the contact line no longer overlap the line below in the
  modern and technical themes, nor citations in any theme.
- PDF metadata keeps non-ASCII and special characters.
- Two documents that would write the same output name are rejected.
- A corrupt PDF is reported as a failed check instead of a crash.
- A config file that is not UTF-8 is reported clearly.
- An unknown rule ID in config is rejected.
- H2 headings parse correctly.
- Images are no longer counted as links.
- A Windows path in config is guarded.
- CI installs the development tools again. It had asked for a `dev` extra
  that no longer existed after the move to a PEP 735 group. The lockfile is
  regenerated.
- CI verifies the lockfile against `pyproject.toml` instead of skipping it.

## 0.2.0 - 2026-08-05

### Changed

- Rewrote the documentation and stated plainly that the project is AI-assisted.
- Held cryptography below 49 on Intel Macs, where the wheels pdfminer needs
  were removed upstream.

### Fixed

- A hard line break no longer ends the component it sits inside.
- An ORCID identifier is no longer read as a telephone number.

## 0.1.0 - 2026-08-02

Initial release.

### Added

- Markdown rendering to PDF, plain text, and DOCX through Pandoc and Typst.
- Verification of the rendered files against page targets, text, wording,
  structure, links, metadata, and accessibility.
- Bundled themes, a configurable document contract, and starter templates.
- Transactional output replacement and manifest-aware cleanup.
