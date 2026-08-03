# Redshift Safe Palettes

**Six terminal, categorical, and sequential color systems engineered to remain useful after a display-wide warm/red shift.**

[![CI](https://github.com/carpdiem/redshift-safe-palettes/actions/workflows/ci.yml/badge.svg)](https://github.com/carpdiem/redshift-safe-palettes/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-c7a76b.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-6f806a.svg)](pyproject.toml)

![All six Redshift Safe palette families](docs/swatches/overview.svg)

The image above shows the **commanded sRGB colors**—the values a UI, terminal, or plot should request. They are intentionally sometimes odd in ordinary daylight. The design target is what remains *after* the named warm-display profile suppresses green and especially blue.

## The six defined schemes

| Warmth tier | Dark canvas | Light canvas | Intended target |
|---|---|---|---|
| Minimum | [**Ember Dark**](docs/swatches/ember-dark.svg) | [**Ember Light**](docs/swatches/ember-light.svg) | warmest macOS Night Shift surrogate (~3400 K) |
| Middle | [**Lowfire Dark**](docs/swatches/lowfire-dark.svg) | [**Lowfire Light**](docs/swatches/lowfire-light.svg) | pinned Redshift signal-LUT at 2000 K |
| Maximum | [**Safelight Dark**](docs/swatches/safelight-dark.svg) | [**Safelight Light**](docs/swatches/safelight-light.svg) | pinned Redshift signal-LUT at 1200 K; deep-red stress tier |

Each linked specification sheet contains:

- exact hex values for three backgrounds, three foregrounds, and a selection surface;
- exact hex values for eight categorical colors;
- swatches for ANSI 0–15 terminal colors; and
- an 8-bit preview of the full 256-sample sequential map.

Every exact terminal value and every canonical continuous sample is in the JSON manifest. `continuous_rgb` contains the 10-decimal sRGB floats used by Python and by the published metrics; `continuous_hex8` is the deliberately quantized preview/fallback used in SVG and CSS artifacts.

<details>
<summary><strong>Expand the exact specification sheets</strong></summary>

### Ember Dark
![Ember Dark exact swatches](docs/swatches/ember-dark.svg)

### Ember Light
![Ember Light exact swatches](docs/swatches/ember-light.svg)

### Lowfire Dark
![Lowfire Dark exact swatches](docs/swatches/lowfire-dark.svg)

### Lowfire Light
![Lowfire Light exact swatches](docs/swatches/lowfire-light.svg)

### Safelight Dark
![Safelight Dark exact swatches](docs/swatches/safelight-dark.svg)

### Safelight Light
![Safelight Light exact swatches](docs/swatches/safelight-light.svg)
</details>

- **Canonical machine-readable source:** [`palettes/redshift-safe-palettes.json`](palettes/redshift-safe-palettes.json)
- **CSS tokens:** [`palettes/redshift-safe-palettes.css`](palettes/redshift-safe-palettes.css)
- **Terminal imports:** [`themes/terminal/`](themes/terminal/)
- **Commanded versus simulated comparison:** [`docs/swatches/command-vs-simulated.png`](docs/swatches/command-vs-simulated.png)

---

## Use them

### Matplotlib

Install directly from GitHub:

```bash
python -m pip install "git+https://github.com/carpdiem/redshift-safe-palettes.git"
```

```python
import matplotlib.pyplot as plt
from redshift_safe import categorical, categorical_norm, encode_categories, sequential

# Define this once and reuse it for full-data and subset plots.
category_order = ["control", "alpha", "beta", "gamma"]
category_ids = encode_categories(labels, category_order)
plt.scatter(
    x,
    y,
    c=category_ids,
    cmap=categorical("lowfire-dark"),
    norm=categorical_norm(),
)
plt.imshow(data, cmap=sequential("lowfire-dark"))
```

The explicit order and fixed normalization matter: raw strings are not valid Matplotlib color values, and default normalization can silently remap a numeric subset to different colors.

Available slugs:

```text
ember-dark       ember-light
lowfire-dark     lowfire-light
safelight-dark   safelight-light
```

![Matplotlib gallery](docs/matplotlib-gallery.png)

### CSS

Load [`redshift-safe-palettes.css`](palettes/redshift-safe-palettes.css), then select a family on any container:

```html
<section data-redshift-palette="ember-dark">
  <div class="panel">...</div>
</section>
```

```css
.panel {
  color: var(--rs-foreground);
  background: var(--rs-background);
}
.series-a { color: var(--rs-category-one); }
.heatmap-key { background: var(--rs-sequential); }
```

CSS exposes eleven representative 8-bit gradient stops. JSON and Python preserve all 256 canonical float samples.

### Terminals

Ready-to-import themes are included for:

- [Alacritty](themes/terminal/alacritty/)
- [iTerm2](themes/terminal/iterm2/)
- [Windows Terminal](themes/terminal/windows-terminal/)

Each import uses the primary background and foreground. The JSON manifest also exposes alternate surfaces. `foreground` is the body-text role and is guaranteed at 4.5:1 against all three backgrounds after the target transform. `foreground_soft` is for larger supporting text or graphics; `foreground_muted` is for nonessential metadata and decoration. The latter two are intentionally quieter and are **not** universal body-text colors—consult `shifted_text_contrast` in the manifest for each exact pairing.

---

# How this works, from five-year-old to color nerd

## The five-year-old version: warm shift is colored sunglasses

Imagine putting orange sunglasses over a box of crayons. A blue crayon does not merely become a slightly warmer blue; much of its light is blocked. Two different crayons can look almost identical through the glasses.

Most palettes—including otherwise excellent ones such as Gruvbox or Viridis—choose colors for the *unfiltered* display. Redshift Safe Palettes instead asks:

> “After the orange glasses damage these colors, which original crayons still land far apart?”

The generator therefore does not optimize the requested RGB numbers. It transforms them first, measures the damaged result, and chooses from there.

## The Feynman version: the display channel has lost dimensions

An ordinary sRGB pixel has three controllable channels: red, green, and blue. A warm-display filter approximately multiplies those channels by three unequal gains:

```text
emitted RGB ≈ commanded RGB × [red gain, green gain, blue gain]
```

The profiles in this repository are explicit engineering stress tests:

| Profile | RGB gains | Interpretation |
|---|---:|---|
| `nightshift` | `[1.00, 0.74, 0.53]` | ~3400 K warm-white surrogate |
| `redshift` | `[1.0000, 0.5436, 0.0868]` | Redshift 2000 K with reset ramps, brightness 1, gamma 1 |
| `safelight` | `[1.0000, 0.3094, 0.0000]` | Redshift 1200 K with reset ramps, brightness 1, gamma 1 |

The last row removes blue and heavily attenuates green. No algorithm can create eight equally bright, wildly separated hues in that compressed output gamut. The honest strategy is:

1. preserve as much chromatic distance as the surviving gamut permits;
2. allow a **small, controlled lightness spread** when hue alone cannot carry eight categories;
3. keep text contrast high; and
4. require labels, shapes, dashes, or position for critical meaning.

That is why Safelight is robust engineering, not magic.

## Why these are surrogates, not device calibrations

Apple documents that Night Shift makes the display warmer—“more yellow and less blue”—and that behavior on external displays depends on the display. Apple does **not** publish a universal RGB matrix or Kelvin value for the slider.

The middle and maximum profiles are more concrete: their gains come from Redshift's pinned 2000 K and 1200 K ramp-table rows. They match `redshift -P -O 2000` and `redshift -P -O 1200` when the incoming ramps are identity and brightness/gamma are both 1. Physical output still varies with the display, calibration, operating system, and gamma-ramp precision.

So the repository makes the model inspectable instead of pretending to know every screen. The exact gains are versioned in JSON and code. If measured device data becomes available, a new profile can replace the surrogate and regenerate every artifact.

---

# Derivation, step by step

## 1. Start with colors the display can actually request

The categorical generator enumerates a deterministic grid inside sRGB. Every candidate is a legal command color—no imaginary out-of-gamut point survives to the final palette.

## 2. Damage every candidate on purpose

Each candidate passes through the profile’s RGB gain vector. All optimization and acceptance metrics then operate on the transformed result. The “before” color matters only as a secondary guard against two absurdly similar unshifted colors.

## 3. Measure perception, not RGB arithmetic

Transformed colors are converted to **Oklab**, where:

- `L` approximates perceived lightness;
- `a` roughly spans green ↔ red; and
- `b` roughly spans blue ↔ yellow.

Euclidean Oklab distance multiplied by 100 is used as a practical engineering separation score. It is called `delta_e_ok` in the manifest; it is **not** a standardized CIE ΔE claim.

Oklab was chosen because it is simple, D65/sRGB-native, numerically well behaved, and designed for smooth lightness, chroma, hue, and gradient operations. A full appearance model such as CAM16 would be a reasonable future calibration tier, especially with measured viewing conditions.

## 4. Choose categorical colors by farthest-point sampling

For each family:

1. keep candidates near a target transformed lightness;
2. reject candidates without enough contrast against the primary background;
3. pick a high-chroma seed; then
4. repeatedly choose the candidate farthest from everything already selected.

As the red shift becomes stronger, the allowed lightness budget expands from roughly 4–5 Oklab points to about 10. That trade is deliberate: at the Safelight tier, strict isoluminance would cause more actual category collisions.

## 5. Build sequential maps with no false brightness cliffs

Each sequential map starts from a small set of human-chosen sRGB/Oklab path anchors. The generator then:

1. rounds the hand-authored anchor corners into a smooth Oklab path;
2. interpolates that into a dense commanded-color path;
3. applies the target redshift to every dense sample;
4. measures cumulative distance in transformed Oklab; and
5. resamples 256 colors at equal transformed-distance intervals.

The canonical result is serialized as 10-decimal sRGB floats, then its metrics are recomputed from those exact serialized values. It has monotonic transformed lightness and nearly constant perceptual step size. Light families run light → dark so low values can merge quietly into a light canvas; dark families run dark → light.

The companion `continuous_hex8` arrays are convenient for previews and older consumers, but 8-bit quantization adds visible numerical jitter at 256 samples. The strict monotonicity and step-uniformity guarantees apply to `continuous_rgb`, which is also what the Matplotlib adapter consumes.

This follows the core lesson behind Viridis and other perceptual maps: ordered data should be carried by monotonic lightness, and equal data steps should not create fake visual boundaries.

## 6. Map the categorical system into ANSI terminal slots

ANSI color names are semantic slots, not promises that “blue” will still appear blue after a 1200 K filter. Slots 1–6 use the first six categorical colors; normal and bright variants move toward the family foreground in Oklab. Black/white slots come from the family surfaces.

At strong shifts, syntax color should be a fast cue—not the only cue. Good terminal grammars still use punctuation, indentation, weight, and text content.

---

# What the tests enforce

Current generated metrics:

| Family | Min shifted category ΔE<sub>OK</sub> | Shifted category L range | Sequential step CV | Min primary-text contrast |
|---|---:|---:|---:|---:|
| Ember Dark | 9.24 | 0.0372 | 0.0006 | 8.41:1 |
| Ember Light | 9.45 | 0.0450 | 0.0005 | 7.12:1 |
| Lowfire Dark | 5.80 | 0.0638 | 0.0024 | 7.05:1 |
| Lowfire Light | 5.14 | 0.0664 | 0.0004 | 5.37:1 |
| Safelight Dark | 4.39 | 0.1029 | 0.0000 | 5.63:1 |
| Safelight Light | 4.44 | 0.1034 | 0.0000 | 4.62:1 |

The test suite rejects a generated release unless:

- all six families contain 16 ANSI, 8 categorical, 256 canonical float sequential samples, and 256 matching 8-bit previews;
- categorical colors meet profile-specific transformed separation floors;
- transformed categorical lightness stays inside the declared budget;
- canonical serialized sequential lightness is strictly monotonic;
- canonical serialized transformed-step coefficient of variation is ≤ 0.08;
- primary and selected text remain at least 4.5:1 against their transformed surfaces;
- every non-background ANSI slot remains at least 3:1 against the primary background, and light-mode ANSI black remains at least 4.5:1; and
- JSON, CSS, Alacritty, iTerm2, Windows Terminal, Matplotlib, and rendered swatch artifacts agree with the generator.

Run the gates locally:

```bash
uv run --extra dev python tools/build_all.py --check
uv run --extra dev pytest -q
uv build
```

---

# Display brightness and astronomy safety

Turning down display brightness scales emitted energy, but a simple uniform linear-light multiplier is **not a meaningful palette robustness test**. Under this repository's Oklab math it merely multiplies every coordinate and pairwise distance by the same cube-root factor, regardless of palette quality. The generator therefore makes no low-brightness discrimination guarantee.

Useful low-light validation needs absolute screen luminance, black level and flare, ambient illumination, adaptation state, viewing duration, and ideally measured spectral output. Those inputs are display- and situation-specific, so this repository treats brightness as an operational constraint rather than manufacturing a universal score.

Three practical rules follow:

1. **Start dim, then add only enough luminance to read.** Bright red light can still damage dark adaptation.
2. **Do not encode critical state with color alone.** Use labels, markers, patterns, line styles, or spatial grouping.
3. **Treat Safelight as a palette stress profile, not certified astronomy equipment.** Actual dark-adaptation safety depends on the display’s spectral power distribution, absolute luminance, black leakage, ambient light, viewing time, and the observer.

For serious field astronomy, a measured dim display plus a physical deep-red filter remains more trustworthy than a software palette alone.

---

# Limits and non-claims

- **Not a macOS emulator.** The 3400 K profile is a documented approximation because Apple does not publish a universal maximum-Night-Shift transform.
- **Not a spectroradiometric model.** RGB gains cannot capture a display’s actual primaries, backlight spectrum, OLED leakage, ICC profile, True Tone, or gamma-ramp details.
- **Not a medical or sleep claim.** “Warmer” does not automatically mean safer or better for sleep.
- **Not color-vision-deficiency certification.** Redshift and CVD are different transforms. Critical interfaces must test both and retain redundant encoding.
- **Not isoluminant at the extreme tier.** Safelight uses up to about 0.104 Oklab lightness range across eight categories because the transformed hue gamut is too narrow for strict equal-lightness separation.
- **Not universally optimal.** A palette is a system component; font weight, line width, area, surrounding colors, ambient light, and data density still matter.
- **Hex8 gradients are previews, not the metric-bearing map.** Eight-bit channel quantization is too coarse to preserve strict 256-step monotonicity and uniformity under the severe transforms; use `continuous_rgb` or the Python adapter when those properties matter.

---

# Repository map

```text
palettes/                         canonical float JSON + quantized CSS exports
src/redshift_safe/               color math, definitions, generator, Matplotlib API
themes/terminal/                 Alacritty, iTerm2, Windows Terminal imports
docs/swatches/                   exact SVG specs and transform comparisons
examples/                         executable Matplotlib gallery
tests/                            numerical and export contracts
tools/build_all.py               deterministic artifact builder
```

Generated artifacts should not be hand-edited. Change [`definitions.py`](src/redshift_safe/definitions.py) or the generator, rebuild, inspect, and rerun the gates.

---

# Sources and intellectual lineage

- Apple, [Use Night Shift on your Mac](https://support.apple.com/en-us/102191) — behavior and display-dependence; no universal transform published.
- Redshift, [pinned color-ramp implementation](https://github.com/jonls/redshift/blob/490ba2aae9cfee097a88b6e2be98aeb1ce990050/src/colorramp.c) and [temperature ramp table](https://github.com/jonls/redshift/blob/490ba2aae9cfee097a88b6e2be98aeb1ce990050/README-colorramp) — exact 2000 K and 1200 K signal gains and gamma-LUT ordering.
- Matplotlib, [Choosing Colormaps](https://matplotlib.org/stable/users/explain/colors/colormaps.html) — monotonic lightness and perceptually uniform sequential maps.
- Smith & van der Walt, [A Better Default Colormap / Viridis design](https://bids.github.io/colormap/) — equal perceptual steps, gamut awareness, and transform-based evaluation.
- Björn Ottosson, [A perceptual color space for image processing](https://bottosson.github.io/posts/oklab/) — Oklab definition and matrices.
- HoloViz Colorcet, [Collection of perceptually accurate colormaps](https://colorcet.holoviz.org/) — Kovesi-style continuous maps and Glasbey-style categorical separation.
- CIE, [CIECAM16](https://cie.co.at/publications/cie-2016-colour-appearance-model-colour-management-systems-ciecam16) — viewing-condition-aware color appearance as the more complete scientific frame.
- Tanner Helland, [Temperature to RGB approximation](https://tannerhelland.com/2012/09/18/convert-temperature-rgb-algorithm-code.html) — useful engineering intuition and explicit warnings against scientific overclaiming.
- W3C WAI, [Understanding WCAG contrast minimum](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html) — 4.5:1 text and 3:1 large-text thresholds.
- U.S. National Park Service, [Dark adaptation and red flashlights](https://www.nps.gov/articles/dark-adaptation-of-the-human-eye-and-the-value-of-red-flashlights.htm) — dim red light is preferable; bright red light can still reduce dark adaptation.

## License

MIT © 2026 Michael Woods.
