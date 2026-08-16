# Ember: Nightshift / Redshift safe color palettes

**Terminal, chart, heatmap, and UI palettes that remain usable before and after aggressive warm-screen filtering.**

[![CI](https://github.com/carpdiem/ember/actions/workflows/ci.yml/badge.svg)](https://github.com/carpdiem/ember/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-c7a76b.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-6f806a.svg)](pyproject.toml)

## Contents

- [Introduction](#introduction)
- [The four palettes](#the-four-palettes): [3400K Dark](#3400k-dark) · [3400K Light](#3400k-light) · [2000K Dark](#2000k-dark) · [1200K Dark](#1200k-dark)
- [With and without redshift](#with-and-without-redshift): [terminal](#in-a-terminal) · [charts and heatmaps](#in-charts-and-heatmaps) · [why identities disappear](#why-identities-disappear)
- [Choose a profile](#choose-a-profile)
- [Install and use Ember](#make-ember-work): [get the files](#1-get-the-files) · [terminal themes](#2-import-a-terminal-theme) · [UI roles](#3-use-the-ui-surface-roles) · [Matplotlib](#matplotlib) · [CSS](#css)
- [Science and validation](#what-is-the-science-behind-it): [measured properties](#measured-properties) · [reproduce the build](#reproduce-the-build)
- [References](#references) · [License](#license)

## Introduction

Ember was created to solve the problem of traditional color palettes having colors that appear indistinguishable once you turn on redshift. With Ember, the primary goal is distinctive colors under various color temperature filters. Only once that's satisfied do we further tweak the redshift-degenerate color channels to improve visual separation during daytime (aka - with no redshift applied).

Ember comes with 4 color palettes:
- [3400K Dark](#3400k-dark)
- [3400K Light](#3400k-light)
- [2000K Dark](#2000k-dark)
- [1200K Dark](#1200k-dark)

The 3400K palettes are good for general use, and approximately optimized for a Macbook's maximum Nightshift effect.

The 2000K and 1200K palettes are more specialized for true "deep redshift" fans (and astronomers).

> *One interesting consequence is that the 2000K and 1200K extreme redshift palettes have fewer distinct colors than the 3400K palettes. This is because such extreme redshifts dramatically reduce the size of the perceptual color space available to choose colors from! More on this below...*

Each palette is authored in commanded sRGB,
verified under its corresponding color temperature's modeled per-channel RGB gains, and exported as terminal
themes (Alacritty, iTerm2, Windows Terminal), UI surface roles, categorical chart
colors, a 256-sample sequential map, and Matplotlib/CSS/JSON/Python artifacts.
Ember does not apply the filter; keep using the one you already have.

## The four palettes

### 3400K Dark

![3400K Dark — six background surfaces, three foreground text roles, six categorical colors, six distinct terminal ANSI accents, and the 256-sample sequential map](docs/swatches/3400k-dark.svg)

### 3400K Light

![3400K Light — six background surfaces, three foreground text roles, six categorical colors, six distinct terminal ANSI accents, and the 256-sample sequential map](docs/swatches/3400k-light.svg)

### 2000K Dark

![2000K Dark — six background surfaces, three foreground text roles, four categorical colors, four terminal accent identities with magenta=red and cyan=green aliases, and the 256-sample sequential map](docs/swatches/2000k-dark.svg)

### 1200K Dark

![1200K Dark — six background surfaces, three foreground text roles, three categorical colors, three terminal accent identities with blue=yellow, magenta=red, and cyan=green aliases, and the 256-sample sequential map](docs/swatches/1200k-dark.svg)

These are the exact commanded sRGB values shipped in every export. The deeper the
target filter, the fewer color identities a family authors; aliased terminal slots
are labeled as aliases instead of posing as additional colors.

## With and without redshift

![Categorical colors and sequential maps of all four palettes, each shown as commanded and after that profile's modeled warm transform](docs/swatches/command-vs-simulated.png)

### In a terminal

![The same code and selection in all four palettes, rendered filter-off and with the modeled filter-on output](docs/samples/terminal-story.png)

### In charts and heatmaps

![The same heatmap, bar chart, and labeled line series in all four palettes, rendered filter-off and with the modeled filter-on output](docs/samples/data-story.png)

### Why identities disappear

![RGB channel survival under the 3400 K, 2000 K, and 1200 K warm-filter models](docs/diagrams/channel-collapse.svg)

A warm filter is not a tinted overlay: it multiplies red, green, and blue by
different gains. At Ember's 1200 K model the blue gain is zero, so colors that
differ only in blue produce identical output. The deeper palettes therefore author
fewer identities instead of pretending aliased colors remain distinct.

Filtered rows are deterministic signal simulations — commanded sRGB multiplied by
each profile's published gains. They are not photographs, calibrated physical color
temperatures, or predictions of every display pipeline. Turn off any active warm
filter before judging them, or your screen applies the transform a second time.

## Choose a profile

| Palette | Use it when | Distinct categories |
|---|---|---:|
| `3400k-dark` | you want a near-black general-purpose warm theme | 6 |
| `3400k-light` | you use a moderate warm shift on a light surface | 6 |
| `2000k-dark` | you run Redshift near 2000 K | 4 |
| `1200k-dark` | you want an extreme 1200 K stress profile | 3 |

Start with `3400k-dark` unless you deliberately run a deeper filter. The 2000 K
and 1200 K profiles are dark-only because a filtered light canvas becomes a large
orange-red field.

## Make Ember work

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
  cp themes/terminal/alacritty/2000k-dark.toml ~/.config/alacritty/themes/
  ```

  ```toml
  [general]
  import = ["~/.config/alacritty/themes/2000k-dark.toml"]
  ```

- **iTerm2:** open **Settings → Profiles → Colors → Color Presets… → Import…** and
  choose a file from [`themes/terminal/iterm2/`](themes/terminal/iterm2/).
- **macOS Terminal:** open a file from
  [`themes/terminal/apple-terminal/`](themes/terminal/apple-terminal/) to import it as a
  profile, then make it permanent under **Settings → Profiles → Default**:

  ```bash
  open themes/terminal/apple-terminal/3400k-dark.terminal
  ```

- **Windows Terminal:** open **Settings → Open JSON file**, copy one object from
  [`themes/terminal/windows-terminal/`](themes/terminal/windows-terminal/) into the root
  `schemes` array, then set your profile's `colorScheme` to its exact `name`.

The [terminal guide](themes/terminal/README.md) has the complete import steps and explains
how reduced ANSI banks behave under the deep profiles.

### 3. Use the UI surface roles

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

The six backgrounds form a monotonic ladder. `bg_0` is always the canvas and `bg_5` is
the strongest background state: dark families become lighter toward `bg_5`, while the
light family becomes darker toward `bg_5`.

### Matplotlib

```python
import matplotlib.pyplot as plt

from ember import categorical, categorical_norm, encode_categories, sequential, surfaces

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

## What is the science behind it?

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
At 2000 K, the same freedom is smaller because a weak blue residual remains. Generated
release checks keep every serialized accent within `0.15 ΔEOK` of its authored transformed
target.

Categorical colors must also clear the complete `fg_0` / `fg_1` / `fg_2` ladder in both
states, not merely remain distinct from one another. The 2000 K and 1200 K banks repeat their
category-spacing, foreground-clearance, and background-contrast checks at all four sampled
gain corners.

### 3. Keep frequent pixels neutral and reserve color for meaning

Human vision carries fine spatial detail more strongly through luminance than chromatic
channels. Dense saturated glyphs and opposing hues are therefore poor places to spend a
limited nighttime color gamut. The comparison below shows the practical consequence: pure
white becomes a brighter transformed orange than Ember's cream body text, while a daytime
dark gray becomes a much larger rust-colored signal than Ember's near-black canvas.

![Wrong palette choices compared with Ember under exact warm transforms](docs/diagrams/failure-modes.svg)

Ember puts most pixels in warm-neutral surfaces, uses cream rather than pure white for body
text, and reserves higher chroma for semantic accents. Every foreground-capable terminal
accent still clears 4.5:1 contrast against the terminal base background (`bg_0`) after its
target transform. `fg_1` and `fg_2` remain available for larger supporting text and
nonessential metadata.

### 4. Protect identity with both color and structure

Under the current release gates, Ember supports six categorical identities at 3400 K, four
at 2000 K, and three at 1200 K. Deep terminal themes repeat those supported capacities across
the sixteen ANSI slots; unsupported names alias deliberately instead of pretending to add
another color identity.

An accent may change apparent hue between states; it must remain distinguishable in both.
Every terminal bank is evaluated with all three foreground roles so an accent cannot pass by
colliding with ordinary, supporting, or muted text. Every foreground trio must remain one
ordered warm-neutral ladder rather than three unrelated colors.

Color is still not enough for critical identity. Charts should combine it with direct labels,
position, dash pattern, marker shape, or texture:

![Color-only series compared with redundant encoding](docs/diagrams/redundant-encoding.svg)

### 5. Space continuous maps in the transformed view

Each sequential map begins with a human-chosen earth-tone path. The generator smooths that
path in Oklab, measures cumulative distance after the target transform, and resamples it at
equal transformed-distance intervals. The 2000 K and 1200 K maps use restrained interior
blue-channel adjustments to improve commanded spacing without giving up transformed
equidistance, endpoints, or monotonic lightness.

The result is a 256-sample map with strictly monotonic transformed lightness and nearly equal
modeled transformed Oklab steps. Release checks also require monotonic daytime lightness and
bounded daytime step variation. CSS exposes eleven convenient 8-bit preview stops; JSON and
Python carry the complete float samples.

<details>
<summary><strong>Measured properties and exact release gates</strong></summary>

### Measured properties

`ΔEOK` below is Euclidean Oklab distance multiplied by 100. It is an engineering
measure used consistently by the generator and tests, not a standardized CIE ΔE
formula.

| Family | Categories | Day min ΔEOK | Transformed min ΔEOK | Mean / max raw chroma | Transformed L range | Min ANSI contrast |
|---|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 6 | 15.00 | 11.45 | 0.0971 / 0.1045 | 0.2206 | 5.29:1 |
| 3400K Light | 6 | 16.73 | 12.41 | 0.0988 / 0.1037 | 0.3068 | 4.65:1 |
| 2000K Dark | 4 | 17.00 | 12.91 | 0.0956 / 0.1082 | 0.1538 | 4.52:1 |
| 1200K Dark | 3 | 20.72 | 10.25 | 0.1047 / 0.1107 | 0.1268 | 4.55:1 |

Daytime hue breadth and transformed category/background contrast are separate release gates.
Contrast here is for graphical category marks, not small text.

| Family | Day minimum hue gap | Target | Transformed category / `bg_0` | Target |
|---|---:|---:|---:|---:|
| 3400K Dark | 20.23° | ≥ 20° | 3.01:1 | ≥ 3:1 |
| 3400K Light | 31.75° | ≥ 30° | 3.03:1 | ≥ 3:1 |
| 2000K Dark | 27.76° | ≥ 20° | 3.05:1 | ≥ 3:1 |
| 1200K Dark | 65.03° | ≥ 45° | 3.12:1 | ≥ 3:1 |

Terminal-bank separation includes the complete foreground ladder as well as accent-to-accent
comparisons:

| Family | Day accent min | Day → `fg_0` | Day → `fg_1` | Day → `fg_2` | Transformed accent min | Transformed → `fg_0` | Transformed → `fg_1` | Transformed → `fg_2` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 10.76 | 8.67 | 8.13 | 11.72 | 7.31 | 6.58 | 5.16 | 10.18 |
| 3400K Light | 15.64 | 9.25 | 9.47 | 9.22 | 11.07 | 6.47 | 6.70 | 7.13 |
| 2000K Dark | 12.62 | 13.73 | 10.86 | 8.25 | 7.75 | 7.64 | 5.03 | 4.75 |
| 1200K Dark | 12.35 | 9.69 | 8.96 | 14.68 | 4.13 | 4.49 | 4.13 | 11.29 |

Foreground coherence is independently gated rather than assumed:

| Family | `fg_0 / fg_1 / fg_2` | Day adjacent steps | Transformed adjacent steps | Day / transformed gap ratio | Day / transformed hue span | Max day chroma |
|---|---|---:|---:|---:|---:|---:|
| 3400K Dark | `#DDD0B2 / #BDAE93 / #908472` | 10.41 / 13.79 | 8.70 / 11.88 | 0.7568 / 0.7372 | 9.32° / 2.63° | 0.0426 |
| 3400K Light | `#342F2C / #4D4540 / #665C54` | 8.75 / 8.52 | 7.55 / 7.32 | 0.9734 / 0.9707 | 0.00° / 1.12° | 0.0181 |
| 2000K Dark | `#EED5AE / #D3BB99 / #AA9D8B` | 8.04 / 10.44 | 6.20 / 9.04 | 0.7886 / 0.7008 | 2.74° / 2.51° | 0.0584 |
| 1200K Dark | `#FFE5BD / #CBAF89 / #A18C73` | 16.43 / 11.79 | 11.07 / 9.16 | 0.7099 / 0.8177 | 6.73° / 0.71° | 0.0607 |

Dark-surface measurements use WCAG's sRGB relative-luminance calculation on the exact
serialized Hex values. The contrast range covers transformed `fg_0` on all six background
roles.

| Dark family | `bg_0` | Commanded luminance, `bg_0` → `bg_5` | Transformed `fg_0` contrast range |
|---|---:|---:|---:|
| 3400K Dark | `#090807` | 0.00247 → 0.02019 | 6.83–8.52:1 |
| 2000K Dark | `#070504` | 0.00162 → 0.01852 | 5.86–6.98:1 |
| 1200K Dark | `#060302` | 0.00108 → 0.01571 | 5.32–6.08:1 |

These are digital signal measurements, not physical display luminance. Actual black
level still depends on panel technology, brightness, calibration, ambient light, and the
display's behavior near black.

The build also checks `fg_0` against every declared background, verifies endpoint visibility,
parses every terminal format, and reproduces all generated artifacts from source.

### Reproduce the build

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
- categorical separation from every foreground role in both states, plus sampled-corner
  floors for deep-profile category spacing, foreground clearance, and background contrast;
- terminal day / night capacities `6 / 6`, `6 / 6`, `4 / 4`, `3 / 3`;
- no more than `0.15 ΔEOK` between each authored transformed accent target and the
  transformed serialized color that reproduces it;
- at least 4.5:1 transformed contrast for foreground-capable ANSI slots against the terminal
  base background (`bg_0`);
- transformed contrast floors of `4.5:1`, `3.5:1`, and `2.4:1` for `fg_0`, `fg_1`, and
  `fg_2` respectively on every background; `fg_1` is limited to larger supporting text or
  graphics, and `fg_2` to nonessential metadata or decoration—not body text;
- profile-specific accent-distance floors against each foreground role in commanded and
  transformed states, so an accent cannot hide a collision in the supporting or muted tier;
- connected foreground ladders with bounded adjacent distances, balanced adjacent lightness
  gaps, lightness-dominant steps, aligned chroma vectors, mode-aware chroma direction within a
  quantization tolerance, and narrow commanded/transformed hue spans;
- dark-mode commanded relative-luminance caps of `0.003`, `0.005`, `0.009`, `0.013`,
  `0.020`, and `0.021` across the six-step ladder;
- at least `1.8 ΔEOK` between adjacent transformed dark-surface ladder steps and `2.8 ΔEOK`
  between adjacent transformed light-surface steps;
- transformed primary-text floors of `6.8:1`, `5.65:1`, and `5.3:1` across every
  surface in the 3400 K, 2000 K, and 1200 K dark families, plus `5.0:1` for 3400 K
  Light;
- at least `6.0 ΔEOK` across each transformed background ladder from `bg_0` to `bg_5`,
  tightened to `15.0 ΔEOK` for 3400 K Light;
- 256 unique float samples per sequential map, with monotonic lightness in both display
  states, transformed step CV no greater than `0.0001`, transformed max:min step ratio no
  greater than `1.001`, and the deep commanded CV tightened
  to `0.11` at 2000 K and `0.15` at 1200 K;
- exact recomputation of the four ±5% green/blue sensitivity corners; and
- exact regeneration of JSON, CSS, themes, diagrams, specimens, and diagnostics.

</details>

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
