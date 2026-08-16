from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_adoption_code_blocks_have_progressive_copy_controls() -> None:
    landing = (ROOT / "index.html").read_text()
    section = landing.split('<section class="use information-plane" id="use"', 1)[1].split(
        "</section>", 1
    )[0]

    labels = [
        "clone commands",
        "direct pip install command",
        "Alacritty setup commands",
        "CSS example",
        "Python example",
    ]
    positions = [section.index(f'<pre data-copy-label="{label}"><code>') for label in labels]
    assert positions == sorted(positions)
    assert section.count("<pre data-copy-label=") == section.count("</code></pre>") == 5
    assert "…color:" not in section
    assert 'href="palettes/ember.css"' in section
    assert 'id="use-copy-feedback" aria-live="polite"' in section

    assert 'document.querySelectorAll("#use pre[data-copy-label]")' in landing
    assert "code.textContent.trim()" in landing
    assert 'button.setAttribute("aria-label", "Copy " + label)' in landing
    assert 'button.classList.toggle("is-copied", copied)' in landing
    assert 'button.classList.toggle("is-copy-error", !copied)' in landing
    assert "useCopyFeedback.textContent = message" in landing
    assert "background:var(--ember-bg-0)" in landing
    assert "color:var(--ember-terminal-green)" in landing
