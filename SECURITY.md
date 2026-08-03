# Security policy

## Supported versions

Security fixes are applied to the latest minor release. Users should update to
the newest tagged version before reporting a problem that may already be fixed.

## Reporting a vulnerability

Please use [GitHub private vulnerability reporting](https://github.com/sethstraw/pressume/security/advisories/new).
Do not open a public issue for a vulnerability before a fix is available.

Include the affected version, operating system, minimal reproduction, expected
behavior, and observed impact. Remove names, contact information, credentials,
and resume content from every example. A synthetic Markdown document is enough
for almost every report.

pressume makes no intentional network requests at runtime. It processes local
Markdown, font, TOML, PDF, TXT, and DOCX files selected by the user and invokes
the bundled Pandoc and Typst components. Reports involving unexpected file
access, path traversal, generated-document injection, or dependency compromise
are particularly important.

Generated PDF and DOCX files contain configured or derived title, author,
description, keyword, and language metadata. DOCX output removes custom
properties, the last-modified author, and Word revision-session identifiers.
Users remain responsible for reviewing intentionally supplied document content
and metadata before sharing a deliverable.
