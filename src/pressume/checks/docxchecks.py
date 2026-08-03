"""Structural and text verification for Word deliverables."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from pressume.checks.ats import check_ats
from pressume.checks.pdfchecks import check_text_hygiene
from pressume.checks.report import CheckResult, Severity
from pressume.config import Checks
from pressume.links import linkify_markdown
from pressume.metadata import DocumentMetadata

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
TEXT = f"{{{WORD_NS}}}t"
PARAGRAPH = f"{{{WORD_NS}}}p"
TABLE = f"{{{WORD_NS}}}tbl"
TEXTBOX = f"{{{WORD_NS}}}txbxContent"
LINK_TARGET = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def extract_docx_text(path: Path) -> str:
    """Extract paragraph text from a DOCX body in document order."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs: list[str] = []
    for paragraph in root.iter(PARAGRAPH):
        text = "".join(node.text or "" for node in paragraph.iter(TEXT)).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def check_docx(
    name: str,
    path: Path,
    checks: Checks,
    metadata: DocumentMetadata,
    markdown: str,
) -> list[CheckResult]:
    """Reopen and verify DOCX text, structure, metadata, and hyperlinks."""
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                return [CheckResult(name, "docx: package", Severity.FAIL, f"corrupt member: {bad}")]
            document_xml = archive.read("word/document.xml")
            core_xml = archive.read("docProps/core.xml")
            relationships = (
                archive.read("word/_rels/document.xml.rels")
                if "word/_rels/document.xml.rels" in archive.namelist()
                else b""
            )
            custom_properties = "docProps/custom.xml" in archive.namelist()
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        return [CheckResult(name, "docx: package", Severity.FAIL, str(error))]

    results = [CheckResult(name, "docx: package", Severity.PASS, "valid OOXML package")]
    text = extract_docx_text(path)
    results.extend(check_text_hygiene(name, "docx", text, checks))
    results.extend(check_ats(name, text, checks))

    root = ET.fromstring(document_xml)
    tables = sum(1 for _ in root.iter(TABLE))
    textboxes = sum(1 for _ in root.iter(TEXTBOX))
    results.append(
        CheckResult(
            name,
            "docx: linear structure",
            Severity.FAIL if tables or textboxes else Severity.PASS,
            f"{tables} table(s), {textboxes} text box(es)" if tables or textboxes else "",
        )
    )

    core = ET.fromstring(core_xml)
    actual = {
        "title": core.findtext(f"{{{DC_NS}}}title", ""),
        "author": core.findtext(f"{{{DC_NS}}}creator", ""),
        "description": core.findtext(f"{{{DC_NS}}}subject", ""),
        "keywords": core.findtext(f"{{{CORE_NS}}}keywords", ""),
        "last modified by": core.findtext(f"{{{CORE_NS}}}lastModifiedBy", ""),
    }
    expected = {
        "title": metadata.title,
        "author": metadata.author,
        "description": metadata.description,
    }
    mismatches = [
        f"{key}={actual[key]!r}" for key, value in expected.items() if actual[key] != value
    ]
    private_metadata = custom_properties or bool(actual["last modified by"])
    if private_metadata:
        mismatches.append("private/custom authoring metadata remains")
    results.append(
        CheckResult(
            name,
            "docx: metadata",
            Severity.FAIL if mismatches else Severity.PASS,
            "; ".join(mismatches),
        )
    )

    expected_links = set(LINK_TARGET.findall(linkify_markdown(markdown)))
    actual_links: set[str] = set()
    if relationships:
        relation_root = ET.fromstring(relationships)
        for relation in relation_root.iter(f"{{{REL_NS}}}Relationship"):
            if relation.attrib.get("TargetMode") == "External":
                actual_links.add(relation.attrib.get("Target", ""))
    missing_links = sorted(expected_links - actual_links)
    results.append(
        CheckResult(
            name,
            "docx: hyperlinks",
            Severity.FAIL if missing_links else Severity.PASS,
            f"missing: {missing_links}"
            if missing_links
            else f"{len(actual_links)} embedded link(s)",
        )
    )
    return results
