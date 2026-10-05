# Changelog

Notable user-visible changes are recorded here. This project uses
[Semantic Versioning](https://semver.org/) and follows the general structure of
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Changed

- `style.paper` accepts `us-letter` and `a4` only. Any other Typst paper name
  was accepted and applied to the PDF, while the Word file was silently left at
  US Letter. Both formats now come from one table, and a size the Word file
  cannot be given is rejected by name.
- The reference DOCX and the styling pass over Pandoc's output now share one
  function, so a Word file made either way carries the same page size, font,
  and spacing. The reference DOCX previously ignored the configured paper.
- `pressume init` documents the settings it had been leaving out: `profile`,
  `lint_only`, `ordered_list_sections`, `dated_sections`,
  `citation_field_labels`, `max_heading_level`, and `contact_after_name`.
- A resume or letter no longer needs an email address, and a resume may have
  no contact line at all, so a public copy can leave out personal contact
  details. A contact line that is present still carries no emphasis, and
  configured contact values are still checked in the output.

### Fixed

- CI installed no development tools at all on its fifteen-cell operating system
  and Python matrix. It asked for a `dev` extra that stopped existing when those
  dependencies moved to a PEP 735 group, so the tests ran without `reportlab`
  or a pinned pytest. The lockfile had drifted the same way and is regenerated.
- CI now verifies the lockfile against `pyproject.toml` instead of skipping the
  comparison, which is what its own comment claimed it did.

### Added

- A `letter` policy for cover letters, selected through a profile. It keeps
  the H1 name line and the contact paragraph after it, and allows no sections,
  so resume section rules no longer fail a letter. A letter's PDF sets its
  paragraphs apart in every theme and density, where they had run together as
  one block, and its metadata title reads `Name - Letter`. Resume and CV
  output is unchanged.
- `pressume new letter` writes a starter `Letter.md`.
- The PDF visual-relationship check measures the line above each section
  heading and its rule, failing under 2.0 pt of clearance and warning under
  3.0 pt. Every shipped template and fixture clears it in every theme, density,
  and paper size.
- `pressume inspect` reports a final page as lightly filled when the document
  has an exact `pages` target and the final page's text spans under 85% of the
  median height of the pages before it. The warning gives that ratio. Without
  an exact target the check is unchanged.
- A test that blocks this process's socket calls around a full render and
  verification, so the claim that pressume makes no network requests is
  enforced rather than stated.
- Visual regression by recorded text geometry. Five invented fixtures render
  under every theme and both paper sizes, and each of the thirty results is
  compared line by line against a recorded baseline: page count, text region,
  and the box, size, and font of every text line. The comparison reports
  overflow past the text region, clipping at the paper edge, heading
  collisions, a heading stranded at the bottom of a page, a page-count change,
  a nearly blank final page, headings that stopped outranking body text, and
  any material change in spacing, typography, or margins. Every one of those
  has a test that perturbs something and proves the comparison fails.
- The baselines are version-controlled data under `tests/baselines`, written
  only by `tests/regenerate_geometry_baselines.py`. The comparison has no code
  path that writes a file, so a failing check cannot rewrite what it failed
  against. The Typst and Pandoc versions behind the recorded files are stored
  with them; when the running versions differ, one test says so by name and the
  comparisons skip rather than passing against a renderer that did not produce
  them.
- Tests for the failure paths that protect delivered files: a document that
  renders and then fails verification leaves the previous files byte-identical,
  `clean --apply` leaves a file it did not create, and the DOCX and PDF checks
  fail on a table, leftover authoring metadata, a dropped hyperlink, missing
  accessibility tags, and wrong metadata.

## 0.2.0 - 2026-08-05

### Fixed

- A hard line break no longer ends the component it sits inside.
- An ORCID identifier is no longer read as a telephone number.

### Changed

- Rewrote the documentation and stated plainly that the project is AI-assisted.
- Held cryptography below 49 on Intel Macs, where the wheels pdfminer needs
  indirectly were removed upstream.

## 0.1.0 - 2026-08-02

Initial release.

### Added

- Markdown rendering to PDF, plain text, and DOCX through Pandoc and Typst.
- Verification of the rendered files against page targets, text, wording,
  structure, links, metadata, and accessibility.
- Bundled themes, a configurable document contract, and starter templates.
- Transactional output replacement and manifest-aware cleanup.
