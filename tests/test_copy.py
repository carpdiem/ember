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
    assert (
        "<h1>Color palettes for Night Shift, Redshift, and other warm screen filters.</h1>"
        in landing
    )


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
    }
    assert not rejected.intersection(landing)


def test_headings_name_the_subject_instead_of_negating_an_alternative() -> None:
    parser = HeadingParser()
    parser.feed((ROOT / "index.html").read_text())

    assert parser.headings
    assert all(" not " not in f" {heading.lower()} " for heading in parser.headings)
    assert all(not heading.lower().startswith("scene ") for heading in parser.headings)
