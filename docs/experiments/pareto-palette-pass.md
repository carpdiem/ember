# Experimental Pareto palette pass

**Branch:** [`experiment/pareto-palette-pass`](https://github.com/carpdiem/ember/tree/experiment/pareto-palette-pass)

**Baseline:** [`main`](https://github.com/carpdiem/ember/tree/main)

**Full diff:** [`main...experiment/pareto-palette-pass`](https://github.com/carpdiem/ember/compare/main...experiment/pareto-palette-pass)

## Bottom line

This branch tests three related changes against generated output on `main`: exact serialized
Hex8 values for categorical colors and canonical float samples for sequential maps.

1. add categorical-to-foreground separation as a first-class metric and improve the 2000 K / 1200 K categorical banks;
2. publish sensitivity metrics at the four corners of a documented ±5% green/blue gain box and optimize the deep categorical banks against those corners; and
3. refine only the deep sequential maps' interior blue anchor bytes while retaining transformed-equal-distance sampling.

The categorical changes are clean Pareto improvements across every compared nominal and sensitivity-corner metric. The sequential anchor changes also improve commanded spacing while preserving effectively exact transformed spacing, monotonicity, endpoints, lightness ranges, and corner sensitivity.

**Recommendation:** promote the categorical, sensitivity, and restrained sequential-anchor changes together.

## Compare visually

All links point to committed generated artifacts.

| View | `main` | experimental |
|---|---|---|
| Commanded data specimen | [open](https://github.com/carpdiem/ember/blob/main/docs/samples/data-commanded.png) | [open](../../docs/samples/data-commanded.png) |
| Simulated data specimen | [open](https://github.com/carpdiem/ember/blob/main/docs/samples/data-simulated.png) | [open](../../docs/samples/data-simulated.png) |
| Commanded vs simulated swatches | [open](https://github.com/carpdiem/ember/blob/main/docs/swatches/command-vs-simulated.png) | [open](../../docs/swatches/command-vs-simulated.png) |
| Terminal specimen | [open](https://github.com/carpdiem/ember/blob/main/docs/samples/terminal-story.png) | [open](../../docs/samples/terminal-story.png) |

Turn off any active warm-screen filter before comparing simulated images; otherwise the display applies another transform.

## 1. Deep categorical banks

### Exact commanded values

| Family | `main` | experimental |
|---|---|---|
| 2000K Dark | `#66B1D4` `#DB93A7` `#A46056` `#A3DBA9` | `#66B0D4` `#E99096` `#A46449` `#A3DCA9` |
| 1200K Dark | `#C26D76` `#92DBFF` `#EFB371` | `#BB6572` `#8FF0FF` `#E9B76C` |

The search optimized exact quantized Hex8 candidates. Every candidate had to retain the existing category count, commanded chroma budget, commanded hue-gap floor, category/category separation floor, category/background contrast floor, and transformed-target reproduction contract.

### Exact `main` → experimental comparison

`ΔEOK` is Euclidean Oklab distance multiplied by 100, matching Ember's generator and tests.

| Family | Day category min | Transformed category min | Day category↔foreground min | Transformed category↔foreground min | Worst-corner category min | Worst-corner category↔foreground min | Worst-corner category/`bg_0` |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2000K Dark | 16.50 → **17.00** | 12.59 → **12.91** | 9.52 → **9.75** | 4.34 → **5.50** | 12.25 → **12.91** | 3.99 → **5.25** | 2.97:1 → **3.00:1** |
| 1200K Dark | 20.03 → **20.72** | 10.05 → **10.25** | 6.28 → **6.32** | 3.51 → **4.89** | 9.91 → **9.93** | 3.32 → **4.71** | 2.93:1 → **3.02:1** |

Nominal transformed category/background contrast also improves:

- 2000K Dark: 3.01:1 → **3.05:1**
- 1200K Dark: 3.01:1 → **3.12:1**

### Candidate selection and rejected frontiers

The highest-separation search initially produced `#6AB0D4 #F096A5 #A7624E #A5DCA8` and `#BA6471 #8EF0FF #E9B76C`. They were numerically strong but pushed the 2000 K pink and 1200 K cyan too close to the visual chroma/lightness boundary.

A second search demonstrated within the tested candidates that Oklab chroma alone was not a sufficient visual proxy: lower measured chroma could still produce a bright channel-clipped cyan. The selected 2000 K point therefore used an explicit commanded-red ceiling on the pink. The selected 1200 K point is the best result from the bounded local Hex8 searches run for this pass, not a proof of a global optimum.

Within the final bounded local search, no candidate with commanded cyan green below 240 simultaneously preserved `main`'s category spacing, cleared 3:1 at every sensitivity corner, and retained at least 4.75 / 4.60 nominal/corner foreground separation. The selected cyan remains bright because blue is the free daytime channel while green is required for filtered luminance and spacing.

## 2. Gain-sensitivity envelope

The manifest now publishes a transparent engineering sensitivity box:

- red gain is held at the profile's nominal value;
- every nonzero green and blue gain is independently scaled by `0.95` and `1.05`;
- all four G/B corner vectors are serialized under each profile;
- exact zero blue at 1200 K remains zero, so its nominally four corners contain two duplicate vectors;
- family metrics report the worst observed value across the corners.

This is a local sensitivity diagnostic, **not** a claim that every display or warm-filter implementation lies inside the box. The nominal profile gains remain deterministic signal transforms, not physical display calibrations.

### Experimental worst-corner report

| Family | Category min ΔEOK | Category↔foreground min | Category/`bg_0` | Terminal group min | Terminal↔foreground min | Terminal/`bg_0` | Primary text contrast | Sequential max CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 10.88 | 5.42 | 2.82:1 | 6.69 | 4.86 | 4.93:1 | 6.50:1 | 0.0107 |
| 3400K Light | 11.61 | 5.13 | 2.92:1 | 10.69 | 6.17 | 4.45:1 | 4.88:1 | 0.0137 |
| 2000K Dark | **12.91** | **5.25** | **3.00:1** | 7.42 | 4.71 | 4.27:1 | 5.68:1 | 0.0084 |
| 1200K Dark | **9.93** | **4.71** | **3.02:1** | 4.08 | 3.76 | 4.44:1 | 5.25:1 | 0.0027 |

The envelope is diagnostic for the complete system. Only the deep categorical colors and sequential samples changed in this experiment. Terminal colors, foreground/surface colors, and both 3400 K color and sequential payloads remain unchanged. Their generated manifest records are not byte-identical because this branch adds target and sensitivity fields.

The 3400 K category/background and primary-text rows demonstrate why the envelope is not advertised as a new universal release promise: a ±5% corner can cross a nominal threshold even when the nominal profile is valid. A tiny strict local fix existed for 3400K Light categorical contrast, but no comparably small full-system fix existed for 3400K Dark without coordinated churn. The experiment therefore reports these sensitivities instead of opportunistically changing one established family.

## 3. Blue-channel sequential anchor refinement

The generator still smooths the authored Oklab path and samples it at equal transformed-distance intervals. The experiment changes only four interior blue bytes per deep map; red, green, endpoints, smoothing, sample count, and the transformed sampling objective remain unchanged.

| Family | `main` interior anchors | Experimental interior anchors |
|---|---|---|
| 2000K Dark | `#4B3438 #795052 #A8755F #C69A70` | `#4B343E #795066 #A87582 #C69A8B` |
| 1200K Dark | `#4B302D #754941 #9F6D58 #C09772` | `#4B3042 #754969 #9F6D86 #C09794` |

### Exact `main` → experimental comparison

| Family | Commanded CV | Transformed CV | Commanded max:min step | Transformed max:min step | Four-corner max CV |
|---|---:|---:|---:|---:|---:|
| 2000K Dark | 0.1182 → **0.1049** | 0.0000 → **0.0000** | 1.377 → **1.303** | 1.000 → **1.000** | 0.0084 → **0.0084** |
| 1200K Dark | 0.1663 → **0.1424** | 0.0000 → **0.0000** | 1.509 → **1.429** | 1.000 → **1.000** | 0.0027 → **0.0027** |

The full-strength blue-only search candidates—`#4B3444 #79507A #A875A5 #C69AA6` and `#4B3058 #754991 #9F6DB4 #C097B5`—improved commanded CV further, to 0.0967 and 0.1141. They also produced visibly purple commanded heatmaps that no longer matched Ember's restrained earth-tone identity. The selected anchors are the nearest-even quantized midpoints between `main` and those candidates. They preserve a muted mauve/earth-tone path, improve commanded uniformity, and leave transformed equidistance and sensitivity behavior effectively unchanged.

## Verification

The branch is generated and checked through the ordinary project pipeline:

```bash
uv run --python 3.13 --extra dev python tools/build_all.py --check
uv run --python 3.13 pytest -q
uv run --python 3.13 ruff check src tests tools examples
uv run --python 3.13 ruff format --check src tests tools examples
uv build
```

Additional tests recompute category-to-foreground and gain-sensitivity metrics from exact serialized values rather than trusting manifest summaries. Final commanded, simulated, and swatch artifacts were visually reviewed after the numerical search.
