from __future__ import annotations

import hashlib
import json
import plistlib
import re
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib.colors
import numpy as np
import pytest
from PIL import Image

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from ember import categorical, categorical_norm, encode_categories, sequential, surfaces
from ember.color import wcag_luminance

ROOT = Path(__file__).resolve().parents[1]
SLUGS = (
    "3400k-dark",
    "3400k-light",
    "2000k-dark",
    "1200k-dark",
)


def test_publication_chrome_is_the_3400k_dark_surface_ladder() -> None:
    manifest = json.loads((ROOT / "palettes/ember.json").read_text())
    style = runpy.run_path(str(ROOT / "tools/render_style.py"))
    chrome = style["publication_chrome"](manifest)
    surfaces = manifest["families"]["3400k-dark"]["surfaces"]
    assert style["PUBLICATION_FAMILY_SLUG"] == "3400k-dark"
    assert chrome == {
        "canvas": surfaces["bg_0"],
        "panel": surfaces["bg_2"],
        "raised_panel": surfaces["bg_3"],
        "rule": surfaces["bg_4"],
        "border": surfaces["bg_5"],
        "primary": surfaces["fg_0"],
        "secondary": surfaces["fg_1"],
        "metadata": surfaces["fg_2"],
    }


def test_generated_graphic_chrome_uses_publication_roles() -> None:
    manifest = json.loads((ROOT / "palettes/ember.json").read_text())
    style = runpy.run_path(str(ROOT / "tools/render_style.py"))
    chrome = style["publication_chrome"](manifest)
    expected_canvas = tuple(bytes.fromhex(chrome["canvas"].removeprefix("#")))

    png_paths = (
        "docs/swatches/command-vs-simulated.png",
        "docs/samples/terminal-story.png",
        "docs/samples/data-story.png",
        "docs/samples/terminal-commanded.png",
        "docs/samples/data-commanded.png",
        "docs/matplotlib-gallery.png",
    )
    for relative_path in png_paths:
        with Image.open(ROOT / relative_path) as image:
            assert image.convert("RGB").getpixel((0, 0)) == expected_canvas, relative_path

    namespace = {"svg": "http://www.w3.org/2000/svg"}
    svg_paths = (
        *(f"docs/swatches/{slug}.svg" for slug in SLUGS),
        "docs/diagrams/channel-collapse.svg",
        "docs/diagrams/failure-modes.svg",
        "docs/diagrams/redundant-encoding.svg",
    )
    for relative_path in svg_paths:
        root = ET.parse(ROOT / relative_path).getroot()
        outer = root.find("svg:rect", namespace)
        title = root.find(".//svg:text", namespace)
        assert outer is not None and outer.attrib["fill"] == chrome["canvas"], relative_path
        assert title is not None and title.attrib["fill"] == chrome["primary"], relative_path


def test_unofficial_publication_chrome_is_retired() -> None:
    renderer_source = "\n".join(
        (ROOT / relative_path).read_text()
        for relative_path in (
            "tools/build_all.py",
            "tools/render_gallery.py",
            "tools/render_samples.py",
            "tools/render_story.py",
        )
    )
    for stale_color in (
        "#171512",
        "#211E1A",
        "#F2E3C8",
        "#BFAF98",
        "#3B342C",
        "#D7C8AC",
        "#131009",
        "#F2E7CE",
        "#C7B79E",
        "#9C8F7B",
    ):
        assert stale_color not in renderer_source


def test_python_distribution_and_import_namespace_are_ember() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert metadata["project"]["name"] == "ember-palettes"
    assert metadata["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/ember"]
    assert (ROOT / "src/ember/__init__.py").is_file()
    assert not (ROOT / "src/redshift_safe").exists()


def test_obsolete_prelaunch_exports_are_absent() -> None:
    obsolete_slugs = ("ember-dark", "ember-light", "lowfire-dark", "safelight-dark")
    obsolete_paths = [
        "palettes/redshift-safe-palettes.css",
        "palettes/redshift-safe-palettes.json",
        *(f"docs/swatches/{slug}.svg" for slug in obsolete_slugs),
        *(
            f"themes/terminal/{terminal}/{slug}.{suffix}"
            for terminal, suffix in (
                ("alacritty", "toml"),
                ("iterm2", "itermcolors"),
                ("windows-terminal", "json"),
            )
            for slug in obsolete_slugs
        ),
    ]
    assert not [path for path in obsolete_paths if (ROOT / path).exists()]


def test_matplotlib_adapters() -> None:
    manifest = json.loads((ROOT / "palettes/ember.json").read_text())
    for slug in SLUGS:
        categorical_map = categorical(slug)
        sequential_map = sequential(slug)
        assert isinstance(categorical_map, matplotlib.colors.ListedColormap)
        assert isinstance(sequential_map, matplotlib.colors.ListedColormap)
        assert categorical_map.N == len(manifest["families"][slug]["categorical"])
        assert sequential_map.N == 256
        assert np.allclose(sequential_map.colors, manifest["families"][slug]["continuous_rgb"])


def test_surface_api_returns_an_independent_copy() -> None:
    manifest = json.loads((ROOT / "palettes/ember.json").read_text())
    for slug in SLUGS:
        result = surfaces(slug)
        assert result == manifest["families"][slug]["surfaces"]
        result["bg_0"] = "#FFFFFF"
        assert surfaces(slug)["bg_0"] != "#FFFFFF"


def test_ember_css_and_terminal_exports_are_canonical() -> None:
    css = (ROOT / "palettes/ember.css").read_text()
    for role in ("bg_0", "bg_1", "bg_2", "bg_3", "bg_4", "bg_5", "fg_0", "fg_1", "fg_2"):
        assert f"--ember-{role.replace('_', '-')}:" in css
    for slug in SLUGS:
        assert f'data-ember-palette="{slug}"' in css
        assert (ROOT / f"themes/terminal/alacritty/{slug}.toml").is_file()
        assert (ROOT / f"themes/terminal/iterm2/{slug}.itermcolors").is_file()
        assert (ROOT / f"themes/terminal/windows-terminal/{slug}.json").is_file()
    assert "--rs-" not in css
    assert "data-redshift-palette" not in css


def test_generated_swatch_rectangles_fit_their_canvas() -> None:
    for path in (ROOT / "docs/swatches").glob("*.svg"):
        root = ET.parse(path).getroot()
        width = float(root.attrib["width"])
        height = float(root.attrib["height"])
        for rectangle in root.findall("{http://www.w3.org/2000/svg}rect"):
            x = float(rectangle.attrib.get("x", 0.0))
            y = float(rectangle.attrib.get("y", 0.0))
            raw_width = rectangle.attrib.get("width", "0")
            raw_height = rectangle.attrib.get("height", "0")
            rectangle_width = width if raw_width.endswith("%") else float(raw_width)
            rectangle_height = height if raw_height.endswith("%") else float(raw_height)
            assert x + rectangle_width <= width + 0.01, path
            assert y + rectangle_height <= height + 0.01, path


def test_readme_visual_story_leads_before_setup() -> None:
    readme = (ROOT / "README.md").read_text()
    boards = [f"docs/swatches/{slug}.svg" for slug in SLUGS]
    hero = "docs/swatches/command-vs-simulated.png"
    terminal = "docs/samples/terminal-story.png"
    data = "docs/samples/data-story.png"
    mechanism = "docs/diagrams/channel-collapse.svg"
    setup = readme.index("## Make Ember work")
    positions = [readme.index(path) for path in (*boards, hero, terminal, data, mechanism)]
    assert positions == sorted(positions)
    assert positions[-1] < setup
    assert readme.count(hero) == 1
    assert all(readme.count(board) == 1 for board in boards)
    assert "<details>" not in readme[:setup]

    for relative_path in (hero, terminal, data):
        with Image.open(ROOT / relative_path) as image:
            assert image.width == 760
            assert image.height > image.width


def test_intro_palette_links_jump_to_their_overviews() -> None:
    readme = (ROOT / "README.md").read_text()
    for slug, title in zip(
        SLUGS,
        ("3400K Dark", "3400K Light", "2000K Dark", "1200K Dark"),
    ):
        link = f"- [{title}](#{slug})"
        heading = f"### {title}"
        image = f"docs/swatches/{slug}.svg"
        assert link in readme
        assert readme.index(link) < readme.index(heading) < readme.index(image)


def test_readme_presents_the_finished_product_without_branch_history() -> None:
    readme = (ROOT / "README.md").read_text()
    first_product_heading = readme.index("## The four palettes")
    setup = readme.index("## Make Ember work")
    assert first_product_heading < setup
    for stale_phrase in (
        "Experimental Pareto pass",
        "experiment/pareto-palette-pass",
        "main...experiment",
        "deep experimental anchors",
        "bi-state minimax trade",
    ):
        assert stale_phrase not in readme
    assert "four ±5% green/blue gain corners" in readme
    assert "not extrema over every point" in readme


def test_commanded_inventory_displays_every_palette_role() -> None:
    readme = (ROOT / "README.md").read_text()
    manifest = json.loads((ROOT / "palettes/ember.json").read_text())
    roles = (*manifest["quality_targets"]["bg_roles_low_to_high"], "fg_0", "fg_1", "fg_2")
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    expected_aliases = {
        "3400k-dark": set(),
        "3400k-light": set(),
        "2000k-dark": {"M=R", "C=G"},
        "1200k-dark": {"B=Y", "M=R", "C=G"},
    }

    for slug in SLUGS:
        board_path = f"docs/swatches/{slug}.svg"
        assert readme.count(board_path) == 1
        root = ET.parse(ROOT / board_path).getroot()
        text_nodes = root.findall(".//svg:text", namespace)
        labels = [node.text or "" for node in text_nodes]
        fills = [
            node.attrib["fill"]
            for node in root.findall(".//*[@fill]", namespace)
            if node.attrib["fill"].startswith("#")
        ]
        assert (float(root.attrib["width"]), float(root.attrib["height"])) == (760, 632)

        family = manifest["families"][slug]
        for role in roles:
            assert any(label.startswith(role) for label in labels), (slug, role)
            assert family["surfaces"][role] in fills, (family["slug"], role)
        for role in manifest["quality_targets"]["bg_roles_low_to_high"]:
            value = family["surfaces"][role]
            assert any(
                node.text == role and node.attrib.get("font-size") == "16" for node in text_nodes
            ), (slug, role)
            assert any(
                node.text == value and node.attrib.get("font-size") == "16" for node in text_nodes
            ), (slug, role, value)
        for value in family["categorical"].values():
            assert value in fills, (family["slug"], "categorical", value)
            assert any(
                node.text == value and node.attrib.get("font-size") == "16" for node in text_nodes
            ), (slug, "categorical-font", value)
        for value in family["continuous_hex8"]:
            assert value in fills, (family["slug"], "sequential", value)
        for role in ("red", "green", "yellow", "blue", "magenta", "cyan"):
            assert family["terminal"][role] in fills, (family["slug"], role)
        aliases = {label for label in labels if "=" in label and len(label) == 3}
        assert aliases == expected_aliases[slug]

        if slug == "3400k-light":
            uniform_labels = set(family["categorical"].values()) | {"R", "G", "Y", "B", "M", "C"}
            chrome = manifest["families"]["3400k-dark"]["surfaces"]
            uniform_nodes = [node for node in text_nodes if node.text in uniform_labels]
            assert len(uniform_nodes) == 12
            assert {node.attrib.get("fill") for node in uniform_nodes} == {chrome["fg_0"]}
            assert all("stroke" not in node.attrib for node in uniform_nodes)


def test_dense_overview_is_retired() -> None:
    assert "overview.svg" not in (ROOT / "README.md").read_text()
    assert not (ROOT / "docs/swatches/overview.svg").exists()
    assert "overview" not in (ROOT / "tools/build_all.py").read_text().lower()


def test_comparison_title_is_professional() -> None:
    story_module = runpy.run_path(str(ROOT / "tools/render_story.py"))
    readme = (ROOT / "README.md").read_text()
    assert (
        story_module["PALETTE_STORY_TITLE"] == "Ember palette appearance: with and without redshift"
    )
    assert "## With and without redshift" in readme
    assert story_module["STORY_SLUGS"] == SLUGS
    for path in (ROOT / "tools/render_story.py", ROOT / "README.md"):
        assert "You ask for these colors" not in path.read_text()


def test_story_figures_cover_all_families() -> None:
    story_module = runpy.run_path(str(ROOT / "tools/render_story.py"))
    assert story_module["STORY_SLUGS"] == SLUGS

    expected_heights = {
        "docs/samples/terminal-story.png": 112 + 384 * len(SLUGS) + 62,
        "docs/samples/data-story.png": 112 + 450 * len(SLUGS) + 62,
    }
    for relative_path, expected_height in expected_heights.items():
        with Image.open(ROOT / relative_path) as image:
            assert image.size == (760, expected_height)


def test_categorical_encoding_is_stable_for_strings_and_subsets() -> None:
    order = ["control", "alpha", "beta", "gamma"]
    assert encode_categories(["control", "beta", "gamma"], order).tolist() == [0, 2, 3]
    assert encode_categories(["beta", "gamma"], order).tolist() == [2, 3]
    assert categorical_norm("2000k-dark")(np.asarray([0, 2, 3])).tolist() == [0, 2, 3]
    with pytest.raises(ValueError, match="1 and 6"):
        encode_categories(["a"], list("abcdefg"))
    with pytest.raises(ValueError, match="1 and 4"):
        encode_categories(["a"], list("abcde"), slug="2000k-dark")


def test_alacritty_exports_parse() -> None:
    for slug in SLUGS:
        data = tomllib.loads((ROOT / f"themes/terminal/alacritty/{slug}.toml").read_text())
        assert len(data["colors"]["normal"]) == 8
        assert len(data["colors"]["bright"]) == 8


def test_windows_terminal_exports_parse() -> None:
    for slug in SLUGS:
        data = json.loads((ROOT / f"themes/terminal/windows-terminal/{slug}.json").read_text())
        assert data["name"]
        assert data["background"].startswith("#")


def test_iterm_exports_parse() -> None:
    for slug in SLUGS:
        data = plistlib.loads((ROOT / f"themes/terminal/iterm2/{slug}.itermcolors").read_bytes())
        assert "Background Color" in data
        assert all(f"Ansi {index} Color" in data for index in range(16))


def test_root_landing_page_uses_the_exported_css_palette_contract() -> None:
    landing = (ROOT / "index.html").read_text()

    assert 'data-ember-palette="3400k-dark"' in landing
    assert 'href="palettes/ember.css"' in landing
    assert "<title>Ember — color that survives the warm shift</title>" in landing
    assert 'data-src-template="assets/mars-topography-{slug}.png"' in landing
    assert 'data-src-template="assets/mona-lisa-{slug}.png"' in landing

    expected_capacities = {
        "3400k-dark": 6,
        "3400k-light": 6,
        "2000k-dark": 4,
        "1200k-dark": 3,
    }
    for slug, capacity in expected_capacities.items():
        assert f'data-palette="{slug}"' in landing
        assert f'data-ember-palette="{slug}"' in landing
        profile_pattern = rf'"{re.escape(slug)}":\s+\{{[^}}]*cats:\s*{capacity}\s*\}}'
        assert re.search(profile_pattern, landing)

    for section_id in ("editorial", "code", "console", "mars", "mona", "field", "use"):
        assert f'id="{section_id}"' in landing
        assert f'href="#{section_id}"' in landing

    assert 'class="burger"' in landing
    assert 'class="menu-panel"' in landing
    assert 'aria-controls="menu"' in landing
    assert 'if (e.key === "Escape" && !menu.hidden) closeMenu(true)' in landing
    assert 'history.replaceState(null, "", url)' in landing

    assert "Fictional telemetry — interface stress test" in landing
    assert "Real NASA data — MGS MOLA topography" in landing
    assert "Public-domain artwork + deterministic mapping" in landing
    assert "Physics figure — real geometry, live palette" in landing
    assert 'id="sparks"' in landing
    assert 'id="scope"' in landing
    assert 'id="em"' in landing
    assert 'role="img"' in landing
    assert "one series per available identity" in landing
    assert "field, not a particle riding the curve" in landing

    assert "@media (prefers-reduced-motion: reduce)" in landing
    assert "animation:none !important" in landing
    assert "if (reducedMQ.matches) return" in landing
    assert "emPhase = 0.6; scopeT = 0" in landing

    assert '--font-sans: "Avenir Next"' in landing
    assert ".field-scene" in landing
    assert ".console-intro" in landing
    assert ".mona-stage" in landing
    assert "min-height:44px" in landing
    assert ".hero > *{ min-width:0; }" in landing
    assert 'style="' not in landing
    assert 'role="img" aria-label="Animated spectral scope trace' in landing
    assert (
        'role="img"\n                aria-label="Projected three-dimensional animation' in landing
    )

    assert 'href="examples/"' not in landing
    assert "256" in landing
    assert "Lorem ipsum" not in landing

    for role in (
        "bg-0",
        "bg-1",
        "bg-2",
        "bg-3",
        "bg-4",
        "bg-5",
        "fg-0",
        "fg-1",
        "fg-2",
        "category-one",
        "category-two",
        "category-three",
        "sequential",
    ):
        assert f"var(--ember-{role})" in landing

    assert not any(
        token in landing for token in ("style.color", "style.background", "setProperty(")
    )
    assert not re.search(r"#[0-9a-fA-F]{3,8}(?:[;\"'])", landing)
    assert not re.search(r"(?:rgb|hsl|oklab|oklch)\(", landing, flags=re.IGNORECASE)


def test_legacy_live_example_redirects_to_the_unified_root() -> None:
    example = (ROOT / "examples/index.html").read_text()

    assert '<link rel="canonical" href="../">' in example
    assert 'target = new URL("../", window.location.href)' in example
    assert "target.search = window.location.search" in example
    assert 'target.hash = "editorial"' in example
    assert "window.location.replace(target)" in example
    assert 'href="../#editorial"' in example
    assert "palette-select" not in example
    assert "ember.css" not in example


def test_mona_lisa_example_colormaps_preserve_source_luminance_polarity() -> None:
    manifest = json.loads((ROOT / "palettes/ember.json").read_text())
    source_path = ROOT / "assets/mona-lisa-c2rmf-public-domain.jpg"
    with Image.open(source_path) as source:
        source = source.convert("RGB")
        height = round(source.height * 640 / source.width)
        source = source.resize((640, height), Image.Resampling.LANCZOS)
        source_luminance = wcag_luminance(np.asarray(source, dtype=float) / 255.0).ravel()

    dark_cutoff, light_cutoff = np.quantile(source_luminance, (0.1, 0.9))
    for slug in SLUGS:
        output_path = ROOT / f"assets/mona-lisa-{slug}.png"
        with Image.open(output_path) as output:
            output_rgb = np.asarray(output.convert("RGB"), dtype=float) / 255.0
            assert output.size == (640, height)

        output_luminance = wcag_luminance(output_rgb).ravel()
        correlation = float(np.corrcoef(source_luminance, output_luminance)[0, 1])
        assert correlation > 0.8, (slug, correlation)
        dark_source_output = float(output_luminance[source_luminance <= dark_cutoff].mean())
        light_source_output = float(output_luminance[source_luminance >= light_cutoff].mean())
        assert light_source_output > dark_source_output + 0.2, (
            slug,
            dark_source_output,
            light_source_output,
        )

        authored_colors = {
            tuple(round(channel * 255) for channel in color)
            for color in manifest["families"][slug]["continuous_rgb"]
        }
        rendered_colors = {
            tuple(color) for color in np.unique((output_rgb * 255).round().reshape(-1, 3), axis=0)
        }
        assert rendered_colors <= authored_colors


def test_mars_topography_colormaps_preserve_real_scalar_indices() -> None:
    manifest = json.loads((ROOT / "palettes/ember.json").read_text())
    source_path = ROOT / "assets/megt90n000cb.img"
    label_path = ROOT / "assets/megt90n000cb.lbl"
    source_bytes = source_path.read_bytes()
    label_bytes = label_path.read_bytes()

    assert hashlib.sha256(source_bytes).hexdigest() == (
        "25f16fb7aaf857898dcf98bc4f841341a24f8b9f7e98453ca083bc45d897ca2c"
    )
    assert hashlib.sha256(label_bytes).hexdigest() == (
        "5a3fe60256afa1c35fea5d551fe0ab0a9198fb2bcd2c2e161d078aa69627ebac"
    )
    label = label_bytes.decode("ascii")
    assert "LINES                        = 720" in label
    assert "LINE_SAMPLES                 = 1440" in label
    assert "SAMPLE_TYPE                  = MSB_INTEGER" in label
    assert "UNIT                         = METER" in label

    elevation = np.frombuffer(source_bytes, dtype=">i2").reshape(720, 1440)
    assert (int(elevation.min()), int(elevation.max())) == (-8068, 21134)
    low, high = np.quantile(elevation, (0.01, 0.99))
    assert (float(low), float(high)) == (-5887.0, 6013.0)
    normalized = np.clip((elevation - low) / (high - low), 0.0, 1.0)
    expected_indices = np.rint(normalized * 255).astype(np.uint8)

    for slug in SLUGS:
        output_path = ROOT / f"assets/mars-topography-{slug}.png"
        with Image.open(output_path) as output:
            assert output.mode == "P"
            assert output.size == (1440, 720)
            assert np.array_equal(np.asarray(output), expected_indices)
            rendered_palette = np.asarray(output.getpalette()[: 256 * 3], dtype=np.uint8).reshape(
                256, 3
            )

        authored_palette = np.rint(
            np.asarray(manifest["families"][slug]["continuous_rgb"]) * 255
        ).astype(np.uint8)
        assert np.array_equal(rendered_palette, authored_palette)
