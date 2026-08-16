from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_hero_palette_board_has_a_local_redshift_control() -> None:
    landing = (ROOT / "index.html").read_text()

    assert 'data-redshift-label="selected palette contents"' in landing
    assert 'class="hero-board-control-host" data-redshift-control-host' in landing
    assert 'class="hero-board-demo demonstration-plane"' in landing
    assert 'var heroRedshiftSection = document.getElementById("top")' in landing
    assert "redshiftSections.unshift(heroRedshiftSection)" in landing
    assert 'section.querySelector("[data-redshift-control-host]")' in landing
    assert "if (controlHost) controlHost.appendChild(control)" in landing
    assert ".hero-board-control-host .redshift-control" in landing
    assert ".hero-board-control-host .redshift-toggle{ transform:none; }" in landing
