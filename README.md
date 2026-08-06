# Ember: Redshift Safe Color Palettes

**Terminal and data-visualization palettes that stay distinct by day and under strong warm shifts at night.**

[![CI](https://github.com/carpdiem/ember-redshift-safe-palettes/actions/workflows/ci.yml/badge.svg)](https://github.com/carpdiem/ember-redshift-safe-palettes/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-c7a76b.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-6f806a.svg)](pyproject.toml)

![Ember palette overview](docs/swatches/overview.svg)

Ember provides coordinated color systems for terminals, charts, heatmaps, and user
interfaces that move between an ordinary daytime display and a software-filtered night
display. Each palette is measured in both states.

Warm filters do more than tint a screen. They attenuate green and blue by different
amounts, reducing the number of colors that remain distinct. Ember uses that same channel
compression as design room: colors meet nighttime contrast and separation floors, then
use the attenuated dimensions to improve daytime spacing. Moderate chroma keeps the
accents expressive within a controlled saturation range.

Dark-mode surfaces are genuinely near-black rather than merely warm dark gray. Every
family includes six ordered background roles and three foreground roles.
Commanded relative luminance is capped from `0.003` for `bg_0` through
`0.021` for `bg_5`, increasing modeled small-text
contrast before display-specific losses.

## Choose a palette

| Palette | Mode | Data categories | Terminal accents, day / night | Intended use |
|---|---|---:|---:|---|
| [`3400k-dark`](docs/swatches/3400k-dark.svg) | dark | 6 | 6 / 6 | near-black general terminal and data work |
| [`3400k-light`](docs/swatches/3400k-light.svg) | light | 6 | 6 / 6 | light-surface work under a moderate warm shift |
| [`2000k-dark`](docs/swatches/2000k-dark.svg) | dark | 4 | 4 / 4 | near-black deep Redshift work; reduced semantic color capacity |
| [`1200k-dark`](docs/swatches/1200k-dark.svg) | dark | 3 | 3 / 3 | near-black extreme stress case; rely on lightness and shape |

The deepest profiles are dark-only. Under the 2000 K and 1200 K gain vectors, a light
canvas becomes a large orange-red field, while a dark canvas preserves a subdued
working surface.

Terminal formats require sixteen ANSI slots. Ember repeats the available commanded
accents to fill those banks. At 2000 K and 1200 K, the four and three available accents
retain separate transformed identities through deliberate lightness and warm-chroma
structure. The reduced banks preserve recognizable red, green, yellow, and blue roles by
day; explicit aliases map magenta to red and cyan to green, plus blue to yellow at 1200 K.
Repeated ANSI names still do not create additional semantic colors.

## See the palettes in use

The commanded specimens show the sRGB colors an application requests. The simulated
specimens apply each target gain vector to the corresponding panel.

### Terminal text

![Commanded terminal specimen](docs/samples/terminal-commanded.png)

![Simulated warm-shift terminal specimen](docs/samples/terminal-simulated.png)

### Heatmaps, bars, and overlapping series

![Commanded data-visualization specimen](docs/samples/data-commanded.png)

![Simulated warm-shift data-visualization specimen](docs/samples/data-simulated.png)

The line charts combine color with dash pattern, marker shape, and direct labels. These
structural cues carry identity when hue differences become small or vanish entirely.

To inspect a simulated image, disable any active color-temperature filter first;
otherwise the transform is applied twice. The specimens are generated regression
artifacts rather than photographs or display-calibration measurements.

## Use Ember

### UI surface ladder

Every family exposes the same ordered roles in JSON, CSS, and the Python `surfaces()` API:

| Role | Intended use |
|---|---|
| `bg_0` | base application canvas |
| `bg_1` | low-emphasis adjacent region or sidebar |
| `bg_2` | ordinary panel or card |
| `bg_3` | nested panel, active control, or hover state |
| `bg_4` | floating panel, menu, or popover |
| `bg_5` | selected row, range, or focused region |
| `fg_0` | primary text and essential labels |
| `fg_1` | larger supporting text or graphics; not normal-size body text |
| `fg_2` | muted, nonessential metadata or decoration |

The six background roles form a monotonic ladder. `bg_0` is always the canvas and `bg_5`
is the strongest background state: dark families become lighter toward `bg_5`, while the
light family becomes darker toward `bg_5`. CSS also exposes the old-style
`--rs-background*`, `--rs-selection`, and `--rs-foreground*` names as generated migration
aliases; JSON and the Python API use only the numbered roles.

### Terminal themes

Ready-to-import themes are included for:

- [Alacritty](themes/terminal/alacritty/)
- [iTerm2](themes/terminal/iterm2/)
- [Windows Terminal](themes/terminal/windows-terminal/)

Choose the file whose temperature and polarity match your display profile. In each
theme, the normal and bright ANSI banks share the same semantic roles. Deep profiles
use extra commanded-channel variation to preserve daytime distinctions.
`bright_black` remains readable because terminals commonly use it for comments,
timestamps, and metadata.

### Matplotlib

```bash
python -m pip install "git+https://github.com/carpdiem/ember-redshift-safe-palettes.git"
```

```python
import matplotlib.pyplot as plt

from redshift_safe import categorical, categorical_norm, encode_categories, sequential, surfaces

palette = "2000k-dark"
ui = surfaces(palette)
labels = ["control", "alpha", "beta", "gamma"]
order = ["control", "alpha", "beta", "gamma"]
category_ids = encode_categories(labels, order, slug=palette)

fig, (points, image) = plt.subplots(1, 2)
fig.patch.set_facecolor(ui["bg_0"])
points.set_facecolor(ui["bg_2"])
image.set_facecolor(ui["bg_3"])
points.scatter(
    [1, 2, 3, 4],
    [1.2, 2.4, 1.8, 3.1],
    c=category_ids,
    cmap=categorical(palette),
    norm=categorical_norm(palette),
)
image.imshow([[0.0, 0.4], [0.7, 1.0]], cmap=sequential(palette))
plt.show()
```

Pass the palette slug to `categorical_norm()` and `encode_categories()` so their
capacity checks match the selected family. Sequential maps always expose 256 canonical
float samples, independent of the number of categorical colors.

### CSS

Load [`redshift-safe-palettes.css`](palettes/redshift-safe-palettes.css), then select a
family:

```html
<section data-redshift-palette="3400k-dark">
  <div class="panel">...</div>
</section>
```

```css
[data-redshift-palette] {
  color: var(--rs-fg-0);
  background: var(--rs-bg-0);
}

.panel {
  background: var(--rs-bg-2);
}

.panel:hover {
  background: var(--rs-bg-3);
}

.popover {
  background: var(--rs-bg-4);
}

.selected {
  background: var(--rs-bg-5);
}

.series-a {
  color: var(--rs-category-one);
}

.heatmap-key {
  background: var(--rs-sequential);
}
```

CSS exposes eleven representative 8-bit gradient stops. The
[JSON manifest](palettes/redshift-safe-palettes.json) and Python package preserve all
256 canonical float samples, along with surfaces, categorical colors, ANSI slots, gain
profiles, and measured results.

## Design and scientific basis

### Model the transformed color space

Ember models a warm display transform as an independent gain on each sRGB channel:

```text
display RGB ≈ commanded RGB × [red gain, green gain, blue gain]
```

| Profile | RGB gains | Source |
|---|---:|---|
| `3400k` | `[1.00, 0.74, 0.53]` | warm-white engineering surrogate |
| `2000k` | `[1.0000, 0.5436, 0.0868]` | pinned Redshift 2000 K signal LUT |
| `1200k` | `[1.0000, 0.3094, 0.0000]` | pinned Redshift 1200 K signal LUT |

![RGB channel collapse at 3400 K, 2000 K, and 1200 K](docs/diagrams/channel-collapse.svg)

At 1200 K, the modeled blue channel contributes nothing and green is heavily
attenuated. Colors that are far apart in ordinary sRGB can therefore converge after
the filter.

This creates a bi-state design problem. At 1200 K, many commanded blue values produce
the same transformed color. At 2000 K, blue differences survive only weakly. Accent
selection is therefore lexicographic rather than a weighted compromise:

1. Choose the desired transformed identities first, including their lightness/chroma
   geometry, contrast, and minimum Oklab separation.
2. Treat those outcomes as hard targets. Among commanded colors that reproduce them,
   choose the most coherent moderate-chroma daytime set with strong unshifted separation.

The manifest publishes both the commanded colors and their authored transformed targets;
release checks require each target to be reproduced within `0.15 ΔEOK`. At 1200 K, the
removed blue channel provides exact second-stage freedom. At 2000 K, its weak residual is
kept inside the target-fidelity tolerance.

These are software signal models, not calibrated physical color temperatures. Actual
output also depends on the display, operating system, calibration, brightness, and
ambient light.

### Keep high-frequency detail quiet and readable

Human vision resolves luminance detail more sharply than chromatic detail. Tiny
saturated glyphs and adjacent opposing hues can look unstable because chromatic
channels have lower spatial resolution and the eye focuses different wavelengths at
slightly different planes.

Ember therefore puts most pixels in warm neutral surfaces and reserves color for
meaning. Body text uses cream rather than pure white on dark themes, while every
foreground-capable ANSI slot still reaches a 4.5:1 contrast floor after its target
transform. Softer foreground roles remain available for larger or nonessential text.

The visual hierarchy draws on Gruvbox's warm-neutral foundation: grays carry the
interface, and accents remain distinguishable without becoming the brightest objects
on the screen.

### Optimize semantic color for day and night

Categorical palettes use six colors at 3400 K, four at 2000 K, and three at 1200 K. The
terminal palettes preserve those same transformed capacities while maintaining the higher
contrast required by small monospaced glyphs: `6 / 6`, `6 / 6`, `4 / 4`, and `3 / 3`
across the four families.

The 2000 K terminal targets preserve four widely separated warm identities while their
commanded colors retain conventional red, green, yellow, and blue meaning. The 1200 K
categorical targets are equally spaced along a warm trajectory; its three terminal targets
remain distinct after red, green, and yellow collapse into red-orange variants. Only after
those nighttime structures are fixed do the commanded colors resolve into coherent daytime
sets. Because lightness can imply order, categorical charts should still carry identity
through labels, position, texture, marker, or line style.

![Redundant line encoding under deep red](docs/diagrams/redundant-encoding.svg)

### Build continuous maps for the transformed view

Each sequential map starts with a human-chosen earth-tone path. The generator smooths
that path in Oklab, measures cumulative distance after the target transform, and
resamples it at equal transformed-distance intervals.

The result is a 256-sample float map with strictly monotonic transformed lightness and
nearly equal transformed Oklab-distance steps. Release checks also require monotonic
daytime lightness and bounded daytime step variation. The Hex8 and CSS exports are
convenient quantized previews; the JSON and Python float arrays carry the numerical
guarantee.

## Measured properties

`ΔEOK` below is Euclidean Oklab distance multiplied by 100. It is an engineering
measure used consistently by the generator and tests, not a standardized CIE ΔE
formula.

| Family | Categories | Day min ΔEOK | Transformed min ΔEOK | Mean / max raw chroma | Transformed L range | Min ANSI contrast |
|---|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 6 | 15.00 | 11.45 | 0.0969 / 0.1045 | 0.2227 | 6.06:1 |
| 3400K Light | 6 | 15.91 | 13.76 | 0.1016 / 0.1053 | 0.2584 | 4.76:1 |
| 2000K Dark | 4 | 14.84 | 9.01 | 0.0982 / 0.1104 | 0.1952 | 5.53:1 |
| 1200K Dark | 3 | 21.00 | 8.65 | 0.1050 / 0.1082 | 0.1616 | 5.17:1 |

Dark-surface measurements use WCAG's sRGB relative-luminance calculation on the exact
serialized Hex values. The contrast range covers transformed `fg_0` on all six background
roles.

| Dark family | `bg_0` | Commanded luminance, `bg_0` → `bg_5` | Transformed `fg_0` contrast range |
|---|---:|---:|---:|
| 3400K Dark | `#090807` | 0.00247 → 0.02019 | 6.83–8.52:1 |
| 2000K Dark | `#070504` | 0.00162 → 0.01852 | 5.68–6.77:1 |
| 1200K Dark | `#060302` | 0.00108 → 0.01571 | 5.32–6.08:1 |

These are digital signal measurements, not physical display luminance. Actual black
level still depends on panel technology, brightness, calibration, ambient light, and the
display's behavior near black.

The build also checks `fg_0` against every declared background, verifies endpoint visibility,
parses every terminal format, and reproduces all generated artifacts from source.

## Verification

```bash
uv sync --extra dev
uv run python tools/build_all.py --check
uv run pytest -q
uv run ruff check src tests tools examples
uv build
```

The release gates enforce:

- exactly four palette families with categorical capacities `6, 6, 4, 3`;
- categorical commanded mean Oklab chroma between `0.09` and `0.105`, with no color
  above `0.111`;
- categorical minimum-distance floors in both unshifted and transformed states;
- terminal day / night capacities `6 / 6`, `6 / 6`, `4 / 4`, `3 / 3`;
- no more than `0.15 ΔEOK` between each authored transformed accent target and the
  transformed serialized color that reproduces it;
- at least 4.5:1 transformed contrast for foreground-capable ANSI slots;
- transformed contrast floors of `4.5:1`, `3.5:1`, and `2.4:1` for `fg_0`, `fg_1`, and
  `fg_2` respectively on every background; `fg_1` is limited to larger supporting text or
  graphics, and `fg_2` to nonessential metadata or decoration—not body text;
- dark-mode commanded relative-luminance caps of `0.003`, `0.005`, `0.009`, `0.013`,
  `0.020`, and `0.021` across the six-step ladder;
- at least `1.8 ΔEOK` between adjacent transformed dark-surface ladder steps;
- transformed primary-text floors of `6.8:1`, `5.65:1`, and `5.3:1` across every
  surface in the 3400 K, 2000 K, and 1200 K dark families;
- at least `6.0 ΔEOK` across each transformed background ladder from `bg_0` to `bg_5`;
- 256 unique float samples per sequential map, with monotonic lightness in both display
  states and nearly even transformed steps; and
- exact regeneration of JSON, CSS, themes, diagrams, specimens, and diagnostics.

Version 0.3 retains the temperature-based palette IDs while replacing the dark surface
ladders with near-black values, expanding to six backgrounds and three foregrounds, and
exposing surfaces through the Python API. Existing users can consult the
[migration guide](MIGRATION.md) for changed
surfaces, legacy aliases, and removed deep-light themes.

## Sources and design lineage

- Gruvbox, [original project and palette](https://github.com/morhetz/gruvbox): warm
  neutrals, sufficient contrast, and restrained accents for sustained use.
- MIT 6.813, [Color](https://web.mit.edu/6.813/www/sp18/classes/15-color/): chromatic
  aberration, the lower spatial resolution of chromatic channels, sparse color, and
  restrained saturation.
- Fan et al. (2024), [The Effect of Ambient Illumination and Text Color on Visual
  Fatigue under Negative Polarity](https://doi.org/10.3390/s24113516): controlled
  evidence that text color and ambient illumination affect fatigue under dark polarity.
- EU Data Visualisation Guide,
  [Colour for categories](https://data.europa.eu/apps/data-visualisation-guide/colour-for-categories):
  limit categorical count and avoid overly saturated or bright colors.
- Datawrapper,
  [What to consider when choosing colors](https://www.datawrapper.de/academy/what-to-consider-when-choosing-colors-for-data-visualization):
  use neutral structure, protect small-text contrast, and add redundant cues.
- Redshift, [pinned color-ramp implementation](https://github.com/jonls/redshift/blob/490ba2aae9cfee097a88b6e2be98aeb1ce990050/src/colorramp.c)
  and [temperature table](https://github.com/jonls/redshift/blob/490ba2aae9cfee097a88b6e2be98aeb1ce990050/README-colorramp).
- Björn Ottosson,
  [A perceptual color space for image processing](https://bottosson.github.io/posts/oklab/).
- Matplotlib, [Choosing Colormaps](https://matplotlib.org/stable/users/explain/colors/colormaps.html).
- W3C WAI,
  [Understanding contrast minimum](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html).

## License

MIT © 2026 Michael Woods.