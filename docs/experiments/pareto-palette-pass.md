# Experimental Pareto palette pass

**Branch:** [`experiment/pareto-palette-pass`](https://github.com/carpdiem/ember/tree/experiment/pareto-palette-pass)  
**Baseline:** [`main`](https://github.com/carpdiem/ember/tree/main)  
**Full diff:** [`main...experiment/pareto-palette-pass`](https://github.com/carpdiem/ember/compare/main...experiment/pareto-palette-pass)

## Bottom line

This branch tests three related changes against the exact serialized Hex8 output on `main`:

1. add categorical-to-foreground separation as a first-class metric and improve the 2000 K / 1200 K categorical banks;
2. publish worst-case sensitivity metrics over a documented ±5% green/blue gain box and optimize the deep categorical banks against its corners; and
3. resample the deep sequential maps against a commanded/transformed arc-length blend instead of transformed arc length alone.

The categorical changes are clean Pareto improvements across every compared nominal and sensitivity-corner metric. The sequential change is deliberately different: it is a **bi-state minimax trade**, not a strict Pareto improvement. Commanded spacing becomes substantially more even while transformed spacing moves from mathematical zero variation to nonzero variation that remains inside the unchanged `0.08` transformed-CV release gate.

**Recommendation:** the categorical and sensitivity work is strong enough to promote. Treat the blended sequential resampling as an independent product decision after comparing the generated heatmaps and deciding whether balanced two-state spacing is preferable to exact transformed-state spacing.

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

A second search proved that Oklab chroma alone was not a sufficient visual proxy: lower measured chroma could still produce a bright channel-clipped cyan. The selected 2000 K point therefore used an explicit commanded-red ceiling on the pink. The selected 1200 K point is the best feasible compromise found after local Hex8 searches over cyan red/green and rose coordinates.

At 1200 K, reducing commanded cyan green below 240 could not simultaneously preserve `main`'s category spacing, clear 3:1 at every sensitivity corner, and retain at least 4.75 / 4.60 nominal/corner foreground separation. The selected cyan remains bright because blue is the free daytime channel while green is required for filtered luminance and spacing.

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
| 2000K Dark | **12.91** | **5.25** | **3.00:1** | 7.42 | 4.71 | 4.27:1 | 5.68:1 | 0.0662 |
| 1200K Dark | **9.93** | **4.71** | **3.02:1** | 4.08 | 3.76 | 4.44:1 | 5.25:1 | 0.0767 |

The envelope is diagnostic for the complete system. Only the deep categorical banks and sequential maps changed in this experiment. Terminal banks, foreground ladders, surface ladders, and both 3400 K families remain byte-for-byte unchanged.

The 3400 K category/background and primary-text rows demonstrate why the envelope is not advertised as a new universal release promise: a ±5% corner can cross a nominal threshold even when the nominal profile is valid. A tiny strict local fix existed for 3400K Light categorical contrast, but no comparably small full-system fix existed for 3400K Dark without coordinated churn. The experiment therefore reports these sensitivities instead of opportunistically changing one established family.

## 3. Bi-state sequential resampling

The authored anchors, smoothing, 256-sample count, monotonicity requirements, endpoints, and transformed CV gate are unchanged. Only the arc-length measure used for deep-profile resampling changes:

- 3400 K families: 100% transformed arc length, preserving their exact existing samples;
- 2000K Dark: 50% commanded + 50% transformed normalized arc length;
- 1200K Dark: 45% commanded + 55% transformed normalized arc length.

### Exact `main` → experimental comparison

| Family | Commanded CV | Transformed CV | Commanded max:min step | Transformed max:min step | Worst-corner transformed CV |
|---|---:|---:|---:|---:|---:|
| 2000K Dark | 0.1182 → **0.0581** | 0.0000 → 0.0581 | 1.377 → **1.171** | 1.000 → 1.176 | 0.0084 → 0.0662 |
| 1200K Dark | 0.1663 → **0.0907** | 0.0000 → 0.0742 | 1.509 → **1.254** | 1.000 → 1.203 | 0.0027 → 0.0767 |

This is the branch's one deliberate tradeoff. The transformed maps remain monotonic, preserve at least the existing 0.50 Oklab lightness range, remain visually smooth in the generated heatmaps, and stay below the unchanged `0.08` transformed CV gate at nominal and sensitivity corners. But exact transformed equidistance is gone.

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
