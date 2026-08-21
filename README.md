# Ember: Nightshift / Redshift safe color palettes

[See it live](https://www.usuallypragmatic.com/ember/)

**Color palettes for terminals, interfaces, charts, and heatmaps that keep text
readable and semantic colors distinct through aggressive warm-screen filtering.**

Warm-screen filters change each RGB channel by a different amount, causing ordinary
colors to collide. Ember provides four palettes with neutral or warm-neutral text and surfaces,
distinct categorical and terminal colors, and 256-sample sequential maps. Each palette
maintains its specified contrast, perceptual separation, and ordered lightness in
unfiltered output and after its modeled 3400 K, 2000 K, or 1200 K transform.

Ember supplies the colors; keep using Night Shift, Redshift, or the warm-screen filter
you already have.

[![CI](https://github.com/carpdiem/ember/actions/workflows/ci.yml/badge.svg)](https://github.com/carpdiem/ember/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-c7a76b.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-6f806a.svg)](pyproject.toml)

## The four palettes

### 3400K Dark

![3400K Dark — six background surfaces, three foreground text roles, six categorical colors, six distinct terminal ANSI accents, and the 256-sample sequential map](docs/swatches/3400k-dark.svg)

### 3400K Light

![3400K Light — six background surfaces, three foreground text roles, six categorical colors, six distinct terminal ANSI accents, and the 256-sample sequential map](docs/swatches/3400k-light.svg)

3400K Dark and 3400K Light use mode-specific 256-sample sequential maps while preserving
one scalar polarity: low values are dark and high values are bright in both modes. The light
map is tuned for even daytime progression against its neutral surface system.

### 2000K Dark

![2000K Dark — six background surfaces, three foreground text roles, four categorical colors, four terminal accent identities with magenta=red and cyan=green aliases, and the 256-sample sequential map](docs/swatches/2000k-dark.svg)

### 1200K Dark

![1200K Dark — six background surfaces, three foreground text roles, three categorical colors, three terminal accent identities with blue=yellow, magenta=red, and cyan=green aliases, and the 256-sample sequential map](docs/swatches/1200k-dark.svg)

These are the exact commanded sRGB values shipped in every export. Deeper filters
leave fewer color identities available, so unsupported ANSI names intentionally
share supported colors and are labeled as aliases.

## With and without redshift

![Categorical colors and sequential maps of all four palettes, each shown as commanded and after its modeled warm transform](docs/swatches/command-vs-simulated.png)

Each pair shows the colors sent to the display followed by a deterministic simulation
of the modeled filtered output.

### In a terminal

![The same code and selection in all four palettes, rendered filter-off and with the modeled filter-on output](docs/samples/terminal-story.png)

### In charts and heatmaps

![The same heatmap, bar chart, and labeled line series in all four palettes, rendered filter-off and with the modeled filter-on output](docs/samples/data-story.png)

### Why warm filters merge colors

![RGB channel survival under the 3400 K, 2000 K, and 1200 K warm-filter models](docs/diagrams/channel-collapse.svg)

A warm filter multiplies red, green, and blue by different gains. At Ember's 1200 K
model the blue gain is zero, so colors that differ only in blue produce identical
output. The deeper palettes therefore provide fewer semantic color identities, and
unsupported ANSI names intentionally share supported colors.

Filtered rows are deterministic signal simulations — commanded sRGB multiplied by
each transform's published gains. They are not photographs, calibrated physical color
temperatures, or predictions of every display pipeline. Turn off any active warm
filter before judging them, or your screen applies the transform a second time.

## Choose a palette

| Palette | Choose it for | Categories |
|---|---|---:|
| [`3400k-dark`](#3400k-dark) | general-purpose dark interfaces | 6 |
| [`3400k-light`](#3400k-light) | neutral daytime light interfaces | 6 |
| [`2000k-dark`](#2000k-dark) | Redshift near 2000 K | 4 |
| [`1200k-dark`](#1200k-dark) | extreme 1200 K filtering | 3 |

Start with `3400k-dark` for a dark interface or `3400k-light` for a light one. Choose
`2000k-dark` or `1200k-dark` only when your filter runs near those deeper settings.
Only dark palettes are provided at 2000 K and 1200 K because a deeply filtered light
canvas becomes a large orange-red field.

## Contents

- [The four palettes](#the-four-palettes): [3400K Dark](#3400k-dark) · [3400K Light](#3400k-light) · [2000K Dark](#2000k-dark) · [1200K Dark](#1200k-dark)
- [With and without redshift](#with-and-without-redshift): [terminal](#in-a-terminal) · [charts and heatmaps](#in-charts-and-heatmaps) · [why colors merge](#why-warm-filters-merge-colors)
- [Choose a palette](#choose-a-palette)
- [Install and use Ember](#install-and-use-ember): [get the files](#1-get-the-files) · [terminal themes](#2-import-a-terminal-theme) · [UI roles](#3-use-the-ui-surface-roles) · [Matplotlib](#matplotlib) · [CSS](#css)
- [The science behind Ember](#the-science-behind-ember)
- [Verification](#verification) · [References](#references) · [License](#license)

## Install and use Ember

### 1. Get the files

For terminal themes, CSS, and the JSON manifest:

```bash
git clone https://github.com/carpdiem/ember.git
cd ember
```

Python users can skip the clone and install directly from GitHub:

```bash
python -m pip install "ember-palettes @ git+https://github.com/carpdiem/ember.git"
```

### 2. Import a terminal theme

- **Alacritty:** copy one file from [`themes/terminal/alacritty/`](themes/terminal/alacritty/)
  into your config directory, then import it from `alacritty.toml`:

  ```bash
  mkdir -p ~/.config/alacritty/themes
  cp themes/terminal/alacritty/3400k-dark.toml ~/.config/alacritty/themes/
  ```

  ```toml
  [general]
  import = ["~/.config/alacritty/themes/3400k-dark.toml"]
  ```

- **iTerm2:** open **Settings → Profiles → Colors → Color Presets… → Import…** and
  choose a file from [`themes/terminal/iterm2/`](themes/terminal/iterm2/).
- **Windows Terminal:** open **Settings → Open JSON file**, copy one object from
  [`themes/terminal/windows-terminal/`](themes/terminal/windows-terminal/) into the root
  `schemes` array, then set your profile's `colorScheme` to its exact `name`.

The [terminal guide](themes/terminal/README.md) has the complete import steps and explains
how reduced ANSI banks behave under the deep palettes.

### 3. Use the UI surface roles

Every palette exposes the same ordered roles in JSON, CSS, and the Python `surfaces()` API:

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

The six backgrounds form a monotonic ladder. `bg_0` is always the canvas and `bg_5` is
the strongest background state: dark families become lighter toward `bg_5`, while the
light family becomes darker toward `bg_5`.

### Matplotlib

For a sequential map:

```python
import matplotlib.pyplot as plt

from ember import sequential

fig, ax = plt.subplots()
ax.imshow([[0.0, 0.4], [0.7, 1.0]], cmap=sequential("3400k-dark"))
plt.show()
```

For categorical data:

```python
import matplotlib.pyplot as plt

from ember import categorical, categorical_norm, encode_categories, surfaces

palette = "3400k-dark"
labels = ["control", "alpha", "beta", "gamma"]
category_ids = encode_categories(labels, labels, slug=palette)
ui = surfaces(palette)

fig, ax = plt.subplots()
fig.patch.set_facecolor(ui["bg_0"])
ax.set_facecolor(ui["bg_2"])
ax.scatter(
    [1, 2, 3, 4],
    [1.2, 2.4, 1.8, 3.1],
    c=category_ids,
    cmap=categorical(palette),
    norm=categorical_norm(palette),
)
plt.show()
```

Pass the palette slug to `categorical_norm()` and `encode_categories()` so their
capacity checks match the selected palette. Sequential maps always expose 256 canonical
float samples, independent of the number of categorical colors.

### CSS

Load [`ember.css`](palettes/ember.css), then select a family:

```html
<link rel="stylesheet" href="/path/to/ember.css">
```

```html
<section data-ember-palette="3400k-dark">
  <div class="panel">...</div>
</section>
```

```css
[data-ember-palette] {
  color: var(--ember-fg-0);
  background: var(--ember-bg-0);
}

.panel {
  background: var(--ember-bg-2);
}

.panel:hover {
  background: var(--ember-bg-3);
}

.popover {
  background: var(--ember-bg-4);
}

.selected {
  background: var(--ember-bg-5);
}

.series-a {
  color: var(--ember-category-one);
}

.heatmap-key {
  background: var(--ember-sequential);
}
```

CSS exposes eleven representative 8-bit gradient stops. The
[JSON manifest](palettes/ember.json) and Python package preserve all
256 canonical float samples, along with surfaces, categorical colors, ANSI slots, gain
profiles, and measured results.

## The science behind Ember

### 1. Model the signal that reaches the display

Ember approximates a warm display transform as an independent gain on each sRGB channel:

```text
display RGB ≈ commanded RGB × [red gain, green gain, blue gain]
```

| Profile | RGB gains | Basis |
|---|---:|---|
| `3400k` | `[1.00, 0.74, 0.53]` | warm-white engineering surrogate |
| `2000k` | `[1.0000, 0.5436, 0.0868]` | pinned Redshift 2000 K signal LUT |
| `1200k` | `[1.0000, 0.3094, 0.0000]` | pinned Redshift 1200 K signal LUT |

At 1200 K, blue contributes nothing to the modeled output. At 2000 K, only 9% survives.
Ordinary sRGB distance is therefore a bad proxy for nighttime distinction: two colors can
be far apart by day and converge after filtering.

These are software signal models, not calibrated physical color temperatures. A real result
also depends on the display, operating system, calibration, brightness, and ambient light.

The JSON manifest also reports sensitivity diagnostics at four ±5% green/blue gain corners
for categorical colors, terminal groups, foreground/surface contrast, and sequential spacing.
These sampled corners expose nearby model sensitivity; they are not extrema over every point
inside a continuous gain box and are not display calibration measurements.

### 2. Solve the constrained state first

Ember treats day and night as two views of the same commanded color. It does not average
their quality into one score, because excellent daytime spacing cannot compensate for a
nighttime collision.

1. Set hard transformed targets for contrast, lightness/chroma geometry, and minimum
   perceptual separation in Oklab.
2. Among the commanded colors that reproduce those targets, choose a moderate-chroma
   daytime set with strong unfiltered separation.

This reverses the usual workflow. At 1200 K, changing only blue cannot disturb the
transformed color, so Ember can use that otherwise lost channel to improve daytime identity.
At 2000 K, the same freedom is smaller because a weak blue residual remains. Every serialized
accent stays within `0.15 ΔEOK` of its authored transformed target.

Categorical colors also remain separated from `fg_0`, `fg_1`, and `fg_2` in both states,
not merely from one another. At all four sampled gain corners, the 2000 K and 1200 K
palettes retain their required category spacing, foreground clearance, and background
contrast.

### 3. Keep frequent pixels neutral and reserve color for meaning

Human vision carries fine spatial detail more strongly through luminance than chromatic
channels. Dense saturated glyphs and opposing hues are therefore poor places to spend a
limited nighttime color gamut. The comparison below shows the practical consequence: pure
white becomes a brighter transformed orange than Ember's cream body text, while a daytime
dark gray becomes a much larger rust-colored signal than Ember's near-black canvas.

![Wrong palette choices compared with Ember under exact warm transforms](docs/diagrams/failure-modes.svg)

Ember puts most pixels in neutral or warm-neutral surfaces, avoids unnecessary pure-white
body text, and reserves higher chroma for semantic accents. Every foreground-capable terminal
accent still clears 4.5:1 contrast against the terminal base background (`bg_0`) after its
target transform. `fg_1` and `fg_2` remain available for larger supporting text and
nonessential metadata.

### 4. Protect identity with both color and structure

Ember supports six categorical identities at 3400 K, four at 2000 K, and three at
1200 K. Deep terminal themes repeat those supported capacities across the sixteen ANSI
slots; unsupported names deliberately share one of the supported colors.

An accent may change apparent hue between states; it must remain distinguishable in both.
Each terminal accent remains distinct from ordinary, supporting, and muted text. Each
foreground trio forms one ordered warm-neutral ladder rather than three unrelated colors.

Color is still not enough for critical identity. Charts should combine it with direct labels,
position, dash pattern, marker shape, or texture:

![Color-only series compared with redundant encoding](docs/diagrams/redundant-encoding.svg)

### 5. Space continuous maps in the transformed view

Each sequential map begins with a human-chosen earth-tone path. The generator smooths that
path in Oklab, measures cumulative distance after the target transform, and resamples it at
equal transformed-distance intervals. The 3400 K Light map uses its own restrained path to
improve daytime progression on a neutral canvas. The 2000 K and 1200 K maps use restrained
interior blue-channel adjustments to improve commanded spacing without giving up transformed
equidistance, endpoints, or monotonic lightness.

The result is a 256-sample map with strictly monotonic transformed lightness and nearly equal
modeled transformed Oklab steps. The same map also maintains monotonic daytime lightness and
bounded daytime step variation. CSS exposes eleven convenient 8-bit preview stops; JSON and
Python carry the complete float samples.

## Verification

The generated manifest records the measured category spacing, terminal separation,
foreground coherence, surface contrast, sequential-map uniformity, and ±5% gain-corner
sensitivity for every palette. [Read the measured properties and exact release
gates](docs/validation.md).

Reproduce the release checks locally:

```bash
uv sync --extra dev
uv run python tools/build_all.py --check
uv run pytest -q
uv run ruff check src tests tools examples
uv build
```

## References

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