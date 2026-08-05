# Security policy

## Supported version

Security fixes are made against the latest release. Please confirm the issue is
still present there before reporting it.

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/sethstraw/pressume/security/advisories/new).
Please do not open a public issue until there is a fix or the report has been
reviewed.

Include the affected version, operating system, steps to reproduce, expected
behavior, and observed impact. Use a synthetic Markdown file. Remove names,
contact information, credentials, and real resume content from logs, examples,
PDFs, and DOCX files.

Reports are especially useful when they involve:

- reading or writing files outside the paths the user selected;
- unsafe cleanup, overwrite, or rollback behavior;
- command or document injection;
- malicious PDF, DOCX, Markdown, TOML, or font input;
- an unexpected network request during normal runtime;
- sensitive metadata that should have been removed;
- a vulnerable or compromised dependency.

## Local data and generated files

pressume is intended to render and inspect local documents without uploading
them. Installation and dependency updates require network access, but normal
rendering, verification, preview watching, and cleanup make no intentional
network requests. Opening a preview delegates to the local system viewer.

PDF and DOCX output can contain configured or derived title, author,
description, keywords, and language metadata. DOCX cleanup removes selected
application metadata, but users should still review generated content and
metadata before sharing a file.
