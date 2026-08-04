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

## Choose a palette

| Palette | Mode | Data categories | Terminal accents | Intended use |
|---|---|---:|---:|---|
| [`3400k-dark`](docs/swatches/3400k-dark.svg) | dark | 6 | 6 | moderate warm shift; general terminal and data work |
| [`3400k-light`](docs/swatches/3400k-light.svg) | light | 6 | 6 | light-surface work under a moderate warm shift |
| [`2000k-dark`](docs/swatches/2000k-dark.svg) | dark | 4 | 2 | deep warm shift with limited green and blue |
| [`1200k-dark`](docs/swatches/1200k-dark.svg) | dark | 3 | 1 | extreme red shift; redundant encoding required |

The deepest profiles are dark-only. Under the 2000 K and 1200 K gain vectors, a light
canvas becomes a large orange-red field, while a dark canvas preserves a subdued
working surface.

Terminal formats require sixteen ANSI slots. The 2000 K and 1200 K themes fill those
slots by repeating the smaller semantic accent set rather than inventing distinctions
that disappear after transformation.

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

### Terminal themes

Ready-to-import themes are included for:

- [Alacritty](themes/terminal/alacritty/)
- [iTerm2](themes/terminal/iterm2/)
- [Windows Terminal](themes/terminal/windows-terminal/)

Choose the file whose temperature and polarity match your display profile. In each
theme, the normal and bright ANSI banks intentionally reuse a compact semantic set.
`bright_black` remains readable because terminals commonly use it for comments,
timestamps, and metadata.

### Matplotlib

```bash
python -m pip install "git+https://github.com/carpdiem/ember-redshift-safe-palettes.git"
```

```python
import matplotlib.pyplot as plt

from redshift_safe import categorical, categorical_norm, encode_categories, sequential

palette = "2000k-dark"
labels = ["control", "alpha", "beta", "gamma"]
order = ["control", "alpha", "beta", "gamma"]
category_ids = encode_categories(labels, order, slug=palette)

fig, (points, image) = plt.subplots(1, 2)
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
.panel {
  color: var(--rs-foreground);
  background: var(--rs-background);
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
the same transformed color. At 2000 K, blue differences survive only weakly. Ember first
requires each category set to clear its transformed separation floor, then uses those
compressed channel dimensions to increase unshifted daytime separation. The 3400 K
families have less free room, so their colors are composed to improve the minimum Oklab
distance in both states together.

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

Categorical palettes use six colors at 3400 K, four at 2000 K, and three at 1200 K.
Terminal accents contract faster because small monospaced glyphs need stronger
foreground contrast than large chart marks.

The category colors are authored as moderate-chroma compositions, then serialized and
measured in unshifted and transformed Oklab. Each family has independent minimum-distance
floors for daytime and nighttime use. Because lightness can imply order, categorical
charts should also carry identity through labels, position, texture, marker, or line
style.

![Redundant line encoding under deep red](docs/diagrams/redundant-encoding.svg)

### Build continuous maps for the transformed view

Each sequential map starts with a human-chosen earth-tone path. The generator smooths
that path in Oklab, measures cumulative distance after the target transform, and
resamples it at equal transformed-distance intervals.

The result is a 256-sample float map with strictly monotonic transformed lightness and
nearly equal transformed Oklab-distance steps. The Hex8 and CSS exports are convenient
quantized previews; the JSON and Python float arrays carry the numerical guarantee.

## Measured properties

`ΔEOK` below is Euclidean Oklab distance multiplied by 100. It is an engineering
measure used consistently by the generator and tests, not a standardized CIE ΔE
formula.

| Family | Categories | Day min ΔEOK | Transformed min ΔEOK | Mean / max raw chroma | Transformed L range | Min ANSI contrast |
|---|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 6 | 15.00 | 11.45 | 0.0969 / 0.1045 | 0.2227 | 4.55:1 |
| 3400K Light | 6 | 15.91 | 13.76 | 0.1016 / 0.1053 | 0.2584 | 4.53:1 |
| 2000K Dark | 4 | 13.62 | 6.26 | 0.0941 / 0.1099 | 0.1654 | 4.57:1 |
| 1200K Dark | 3 | 21.61 | 6.95 | 0.0990 / 0.1100 | 0.1616 | 4.54:1 |

The build also checks primary text against every declared background and selection
surface, verifies selection visibility, parses every terminal format, and reproduces
all generated artifacts from source.

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
- terminal semantic capacities `6, 6, 2, 1` with valid sixteen-slot exports;
- commanded categorical mean Oklab chroma between `0.09` and `0.105`, with no color
  above `0.111`;
- family-specific category-separation floors in both unshifted daylight and the target
  transform;
- at least 4.5:1 transformed contrast for foreground-capable ANSI slots;
- at least 4.5:1 primary-text contrast on every background and selection;
- visible selection surfaces after transformation;
- 256 unique, monotonic, evenly stepped float samples per sequential map; and
- exact regeneration of JSON, CSS, themes, diagrams, specimens, and diagnostics.

Version 0.2 uses temperature-based palette IDs. Existing users can consult the
[migration guide](MIGRATION.md) for legacy aliases and removed deep-light themes.

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