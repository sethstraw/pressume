"""Visual regression by text geometry: the corpus, and proof each check fails.

A check that cannot be shown to fail is not a check, so every detection below
has a test that perturbs one thing and asserts the comparison names what moved.
"""

from dataclasses import replace

import geometry_baseline as geometry
import pytest
import regenerate_geometry_baselines

from pressume import themes

FIXTURE = "short_resume"


def kinds(findings):
    return sorted({finding.kind for finding in findings})


def details(findings, kind):
    return " ".join(finding.detail for finding in findings if finding.kind == kind)


MODERN = themes.THEMES["modern"]


def use_theme(monkeypatch, **tokens):
    """Change theme tokens for one test.

    Each call overlays the shipped theme rather than whatever a previous call
    left behind, so two perturbations in one test stay independent.
    """
    monkeypatch.setitem(themes.THEMES, "modern", replace(MODERN, **tokens))


def render(directory, markdown, name, theme="modern", paper="us-letter"):
    pdf = geometry.render(markdown, theme, paper, directory / f"{name}.pdf")
    return pdf, geometry.measure(pdf, theme)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """Render every fixture under every theme and paper size, once.

    The rendered PDFs and the observed geometry stay in pytest's temporary
    directory, which keeps the last three runs, so a failure leaves something a
    person can open and diff rather than a number in a log.
    """
    artifacts = tmp_path_factory.mktemp("geometry")
    rendered = {}
    for fixture, theme, paper in geometry.configurations():
        markdown = geometry.read_fixture(fixture)
        stem = f"{fixture}-{theme}-{paper}"
        pdf = geometry.render(markdown, theme, paper, artifacts / f"{stem}.pdf")
        observed = geometry.measure(pdf, theme)
        (artifacts / f"{stem}.txt").write_text(
            "\n".join(geometry.format_geometry(observed)) + "\n", encoding="utf-8"
        )
        rendered[fixture, theme, paper] = (markdown, pdf, observed)
    return artifacts, rendered


@pytest.fixture(scope="module")
def recorded():
    return {
        fixture: geometry.parse_baseline(
            (geometry.BASELINE_DIR / f"{fixture}.txt").read_text(encoding="utf-8")
        )
        for fixture in geometry.FIXTURES
    }


def test_the_recorded_renderer_versions_are_the_running_ones():
    """One explicable failure, rather than a mass baseline failure.

    Typst and Pandoc are floor pinned, so an upgrade can move every line on
    every page. When that happens this test fails once and says so, and the
    baseline comparisons skip instead of reporting thirty unrelated diffs.
    """
    assert not geometry.renderer_drift(), geometry.renderer_drift()


@pytest.mark.parametrize(("fixture", "theme", "paper"), list(geometry.configurations()))
def test_every_configuration_matches_its_recorded_baseline(corpus, recorded, fixture, theme, paper):
    if drift := geometry.renderer_drift():
        pytest.skip(drift)
    artifacts, rendered = corpus
    _markdown, _pdf, observed = rendered[fixture, theme, paper]
    findings = geometry.compare(recorded[fixture][f"{theme} {paper}"], observed)
    assert not findings, "\n".join(
        [
            *geometry.describe(fixture, theme, paper, findings),
            f"recorded: tests/baselines/{fixture}.txt",
            f"observed: {artifacts}/{fixture}-{theme}-{paper}.txt (with the PDF beside it)",
            "If the change was intended, say what moved and run "
            "tests/regenerate_geometry_baselines.py.",
        ]
    )


@pytest.mark.parametrize(("fixture", "theme", "paper"), list(geometry.configurations()))
def test_every_configuration_satisfies_the_layout_invariants(corpus, fixture, theme, paper):
    """These need no baseline, so a renderer upgrade does not excuse them."""
    artifacts, rendered = corpus
    markdown, pdf, observed = rendered[fixture, theme, paper]
    findings = geometry.inspect(observed, markdown, pdf)
    assert not findings, "\n".join(
        [*geometry.describe(fixture, theme, paper, findings), f"artifacts: {artifacts}"]
    )


# ---------------------------------------------------------------------------
# Proof that each detection fails when something moves.
# ---------------------------------------------------------------------------


def test_overflow_past_the_text_region_is_detected(tmp_path):
    """An unbreakable token wider than the column has to be reported.

    Typst breaks the long URLs in the corpus at their slashes, so the fixture
    that carries them stays inside the margin. A token with no break
    opportunity at all does not, and that is the case this proves.
    """
    token = "ExampleUnbreakableIdentifier" + "X" * 82
    markdown = geometry.read_fixture(FIXTURE).replace(
        "- Cut nightly pipeline runtime from six hours to forty minutes.", f"- {token}"
    )
    pdf, observed = render(tmp_path, markdown, "overflow")
    findings = geometry.inspect(observed, markdown, pdf)
    assert "overflow" in kinds(findings)
    assert "clipping" not in kinds(findings)
    assert "past the right edge of the text region" in details(findings, "overflow")


def test_clipping_at_the_page_edge_is_detected(tmp_path):
    token = "ExampleUnbreakableIdentifier" + "X" * 112
    markdown = geometry.read_fixture(FIXTURE).replace(
        "- Cut nightly pipeline runtime from six hours to forty minutes.", f"- {token}"
    )
    pdf, observed = render(tmp_path, markdown, "clipping")
    findings = geometry.inspect(observed, markdown, pdf)
    assert "clipping" in kinds(findings)
    assert "past the right edge of the paper" in details(findings, "clipping")


def test_heading_collisions_are_detected(tmp_path, monkeypatch):
    """A density factor of zero removes the space below every block."""
    monkeypatch.setitem(themes.DENSITY_FACTORS, "balanced", 0.0)
    markdown = geometry.read_fixture(FIXTURE)
    pdf, observed = render(tmp_path, markdown, "collision")
    findings = geometry.inspect(observed, markdown, pdf)
    assert "heading-collision" in kinds(findings)
    assert "JANE DOE" in details(findings, "heading-collision")


def test_a_stranded_heading_is_detected(tmp_path):
    """A heading alone at the bottom of a page, with its content overleaf.

    Both document builders mark headings sticky, which is what stops Typst
    from stranding one, so no theme token, density, margin, or fixture edit
    produces this page. It is drawn directly instead, the same way the
    collision check in test_product_features.py is proved. The detector exists
    to catch the day stickiness stops working.
    """
    from reportlab.pdfgen import canvas

    markdown = "# JANE DOE\n\nToronto | jane@example.com\n\n## Publications\n\nDoe J. 2024.\n"
    pdf = tmp_path / "stranded.pdf"
    page = canvas.Canvas(str(pdf), pagesize=(612, 792))
    page.setFont("Helvetica", 18)
    page.drawString(39.6, 730, "JANE DOE")
    page.setFont("Helvetica", 10)
    page.drawString(39.6, 700, "Toronto | jane@example.com")
    page.setFont("Helvetica-Bold", 12)
    page.drawString(39.6, 60, "PUBLICATIONS")
    page.showPage()
    page.setFont("Helvetica", 10)
    page.drawString(39.6, 730, "Doe J. 2024.")
    page.save()

    findings = geometry.inspect(geometry.measure(pdf, "modern"), markdown, pdf)
    assert "stranded-heading" in kinds(findings)
    assert "page 1" in details(findings, "stranded-heading")
    assert "starts on page 2" in details(findings, "stranded-heading")


def test_an_unexpected_page_count_change_is_detected(tmp_path, monkeypatch):
    markdown = geometry.read_fixture(FIXTURE)
    _before_pdf, before = render(tmp_path, markdown, "pages-before")
    use_theme(monkeypatch, body_size_pt=20.0)
    _after_pdf, after = render(tmp_path, markdown, "pages-after")
    findings = geometry.compare(geometry.normalize(before), after)
    assert kinds(findings) == ["page-count"]
    assert "1 page(s) recorded, 2 rendered" in details(findings, "page-count")


def test_an_excessively_blank_ending_is_detected(tmp_path, monkeypatch):
    """Grow the body until the resume just spills, and read the last page.

    The smallest size that spills leaves one or two lines overleaf, which is
    the ending a reader takes for a mistake. Searching for that size rather
    than hard-coding it keeps the test honest across a renderer upgrade.
    """
    markdown = geometry.read_fixture(FIXTURE)
    for size in (16.0, 17.0, 18.0, 19.0, 20.0, 21.0):
        use_theme(monkeypatch, body_size_pt=size)
        pdf, observed = render(tmp_path, markdown, "blank")
        if observed.pages > 1:
            break
    else:
        # A one-page fixture that no body size will spill is a broken fixture.
        pytest.fail("no body size made the short resume spill onto a second page")
    findings = geometry.inspect(observed, markdown, pdf)
    assert "blank-ending" in kinds(findings)
    assert "of the text region" in details(findings, "blank-ending")


def test_broken_visual_hierarchy_is_detected(tmp_path, monkeypatch):
    """Shrink section headings below the text they introduce.

    Weight is set in the document builder rather than in a theme token, so the
    perturbation available here is the size half of the ordering. The check
    reads both.
    """
    use_theme(monkeypatch, section_scale=0.70)
    markdown = geometry.read_fixture(FIXTURE)
    pdf, observed = render(tmp_path, markdown, "hierarchy")
    findings = geometry.inspect(observed, markdown, pdf)
    assert "hierarchy" in kinds(findings)
    assert "no longer outranks" in details(findings, "hierarchy")


def test_material_spacing_typography_and_margin_changes_are_detected(tmp_path, monkeypatch):
    """One perturbation each, and the finding has to name what moved."""
    markdown = geometry.read_fixture(FIXTURE)
    _pdf, before = render(tmp_path, markdown, "material-before")
    recorded = geometry.normalize(before)

    monkeypatch.setitem(themes.DENSITY_FACTORS, "balanced", 1.25)
    _pdf, spaced = render(tmp_path, markdown, "material-spacing")
    monkeypatch.setitem(themes.DENSITY_FACTORS, "balanced", 1.0)
    spacing = geometry.compare(recorded, spaced)
    assert kinds(spacing) == ["spacing"]
    assert "SUMMARY" in details(spacing, "spacing")
    assert "pt)" in details(spacing, "spacing")

    use_theme(monkeypatch, font="IBM Plex Sans")
    _pdf, retyped = render(tmp_path, markdown, "material-typography")
    typography = geometry.compare(recorded, retyped)
    assert "typography" in kinds(typography)
    assert "SourceSans3-Semibold -> IBMPlexSans-Bold" in details(typography, "typography")

    use_theme(monkeypatch, margin_in=0.9)
    _pdf, remargined = render(tmp_path, markdown, "material-margins")
    margins = geometry.compare(recorded, remargined)
    assert "margins" in kinds(margins)
    assert "39.6 39.6 572.4 752.4 -> 64.8 64.8 547.2 727.2" in details(margins, "margins")


# ---------------------------------------------------------------------------
# The baselines are data, and a failure does not get to rewrite them.
# ---------------------------------------------------------------------------


def test_a_failing_comparison_cannot_rewrite_its_baseline(tmp_path, monkeypatch):
    before = {path: path.read_bytes() for path in sorted(geometry.BASELINE_DIR.glob("*.txt"))}
    recorded = geometry.parse_baseline(before[geometry.BASELINE_DIR / f"{FIXTURE}.txt"].decode())

    use_theme(monkeypatch, margin_in=0.9)
    _pdf, observed = render(tmp_path, geometry.read_fixture(FIXTURE), "unwritable")
    assert geometry.compare(recorded["modern us-letter"], observed)
    assert {path: path.read_bytes() for path in before} == before

    # The one place that writes a baseline refuses to run inside a test.
    assert regenerate_geometry_baselines.main() == 2
    assert {path: path.read_bytes() for path in before} == before


def test_every_configuration_is_recorded_in_an_ascii_file_that_round_trips(recorded):
    labels = sorted({f"{theme} {paper}" for _fixture, theme, paper in geometry.configurations()})
    for path in sorted(geometry.BASELINE_DIR.glob("*.txt")):
        path.read_text(encoding="ascii")
    for fixture in geometry.FIXTURES:
        assert sorted(recorded[fixture]) == labels
        for section in recorded[fixture].values():
            assert geometry.normalize(section) == section
