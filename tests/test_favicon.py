import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parents[1]
BG_0 = (5, 4, 4)
FG_0 = (220, 217, 191)


def test_landing_page_declares_the_ember_favicon_package() -> None:
    landing = (ROOT / "index.html").read_text()

    assert '<link rel="icon" href="favicon-32x32.png" type="image/png" sizes="32x32">' in landing
    assert '<link rel="icon" href="favicon.svg" type="image/svg+xml" sizes="any">' in landing
    assert '<link rel="apple-touch-icon" href="apple-touch-icon.png" sizes="180x180">' in landing


def test_favicon_uses_the_3400k_dark_bg_0_and_fg_0_contract() -> None:
    root = ET.parse(ROOT / "favicon.svg").getroot()
    assert root.attrib["viewBox"] == "0 0 64 64"

    fills = {element.attrib["fill"].lower() for element in root if "fill" in element.attrib}
    assert fills == {"#050404", "#dcd9bf"}

    for filename, expected_size in (
        ("favicon-32x32.png", (32, 32)),
        ("apple-touch-icon.png", (180, 180)),
    ):
        image = Image.open(ROOT / filename).convert("RGB")
        assert image.size == expected_size
        assert all(
            image.getpixel(point) == BG_0
            for point in (
                (0, 0),
                (image.width - 1, 0),
                (0, image.height - 1),
                (image.width - 1, image.height - 1),
            )
        )
        colors = image.getcolors(maxcolors=image.width * image.height)
        assert colors is not None
        assert any(color == FG_0 for _, color in colors)


def test_favicon_is_a_plain_text_e() -> None:
    root = ET.parse(ROOT / "favicon.svg").getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    text = root.find("svg:text", namespace)

    assert text is not None
    assert text.text == "E"
    assert text.attrib["font-family"] == "Arial, Helvetica, sans-serif"
    assert text.attrib["font-weight"] == "600"
    assert text.attrib["text-anchor"] == "middle"
