from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parents[1]


class HeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current: list[str] | None = None
        self.headings: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "h3"}:
            self.current = []

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3"} and self.current is not None:
            self.headings.append(" ".join("".join(self.current).split()))
            self.current = None


def test_landing_page_leads_with_a_direct_description() -> None:
    landing = (ROOT / "index.html").read_text()
    normalized = " ".join(landing.split())
    assert (
        "<h1>Color palettes for Night Shift, Redshift, and other warm screen filters.</h1>"
        in landing
    )
    assert "Ember palettes are developed and tested under modeled" in landing
    assert "Ember palettes meet their minimum contrast" in landing
    assert (
        "Every theme assigns its accent colors to both the normal and bright ANSI slots."
        in normalized
    )
    assert "Each terminal accent color provides at least" in landing
    assert "<h2>Image mapped by perceptual lightness</h2>" in landing
    assert "This example with the Mona Lisa calculates the Oklab lightness" in landing


def test_descriptive_copy_does_not_restore_rejected_abstractions() -> None:
    landing = (ROOT / "index.html").read_text().lower()
    rejected = {
        "color that stays articulate",
        "live anatomy",
        "measured honesty",
        "not a defect",
        "not inverted",
        "not a scalar field",
        "not a decorative mars texture",
        "not a screenshot",
        "scene 01",
        "scene 02",
        "scene 03",
        "scene 04",
        "scene 05",
        "scene 06",
        "the night your grays turned to rust",
        "ember tests each palette",
        "ember tests the contrast",
        "foreground-capable terminal accent",
        "muted text",
        "photograph mapped by perceptual lightness",
        "the build calculates the oklab lightness",
    }
    assert not [phrase for phrase in rejected if phrase in landing]


def test_headings_name_the_subject_instead_of_negating_an_alternative() -> None:
    parser = HeadingParser()
    parser.feed((ROOT / "index.html").read_text())

    assert parser.headings
    assert all(" not " not in f" {heading.lower()} " for heading in parser.headings)
    assert all(not heading.lower().startswith("scene ") for heading in parser.headings)
