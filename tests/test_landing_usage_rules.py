from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RuleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rule_cards = 0
        self.good_examples = 0
        self.bad_examples = 0
        self.ids: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"] or "")
        classes = set((values.get("class") or "").split())
        if "rule-card" in classes:
            self.rule_cards += 1
        if "rule-example" in classes and "good" in classes:
            self.good_examples += 1
        if "rule-example" in classes and "bad" in classes:
            self.bad_examples += 1


def test_science_and_rules_are_first_class_live_page_sections() -> None:
    landing = (ROOT / "index.html").read_text(encoding="utf-8")
    parser = RuleParser()
    parser.feed(landing)

    assert parser.rule_cards == 6
    assert parser.good_examples == 6
    assert parser.bad_examples == 6
    assert len(parser.ids) == len(set(parser.ids))
    assert '<section class="science information-plane" id="science"' in landing
    assert '<section class="rules scene" id="rules"' in landing
    assert 'href="#science">How Ember works' in landing
    assert "href=\"#rules\">Do's and Don'ts" in landing
    assert "The science behind Ember." in landing
    assert "Ember Do's and Don'ts." in landing
    assert ">Do's and Don'ts</a>" in landing
    assert "quick-contract" not in landing


def test_rules_share_the_normal_profile_and_section_local_simulation_controls() -> None:
    landing = (ROOT / "index.html").read_text(encoding="utf-8")
    rules = landing.split('<section class="rules scene" id="rules"', 1)[1].split(
        "<!-- ================= ADOPTION", 1
    )[0]

    assert 'class="rules-demo demonstration-plane"' in rules
    assert "data-redshift-label=\"Do's and Don'ts examples\"" in rules
    assert "Simulate redshift" in landing
    assert 'document.querySelectorAll(".scene, #console")' in landing
    assert 'document.querySelectorAll("[data-rule-good-cat]")' in landing
    assert 'document.querySelectorAll("[data-rule-bad-cat]")' in landing
    for slug in ("3400k-dark", "3400k-light", "2000k-dark", "1200k-dark"):
        assert f'data-palette="{slug}"' in landing
    for profile in ("3400k", "2000k", "1200k"):
        assert f'id="redshift-{profile}"' in landing


def test_usage_contract_names_each_prohibited_failure_mode() -> None:
    landing = " ".join((ROOT / "index.html").read_text(encoding="utf-8").split())
    required = (
        "Use foreground roles by meaning.",
        "Keep text at full opacity.",
        "Mark aliased state boundaries.",
        "Stay within category capacity.",
        "Keep terminal colors out of charts.",
        "Map scalars and photographs differently.",
        "it does not automate a style cycle",
    )
    for phrase in required:
        assert phrase in landing


def test_public_reader_paths_do_not_reintroduce_experiment_narration() -> None:
    public = "\n".join(
        [
            (ROOT / "README.md").read_text(encoding="utf-8"),
            (ROOT / "index.html").read_text(encoding="utf-8"),
        ]
    ).lower()
    rejected = (
        "branch experiment",
        "not a production palette update",
        "halfway warmth",
        "candidate lane",
        "promotion requires",
    )
    assert not [phrase for phrase in rejected if phrase in public]
