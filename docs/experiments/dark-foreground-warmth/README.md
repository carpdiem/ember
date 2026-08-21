# Dark foreground warmth exploration

> **Branch:** `exp/dark-foreground-warmth`<br>
> **Status:** isolated experiment; not a production palette update<br>
> **Live comparison:** [open `index.html`](index.html)

## Bottom line

This experiment compares all three shipped dark profiles under three fixed foreground-warmth constraints: current, halfway, and a full step toward the corresponding **3400K Light Mid-Depth** foreground chroma vector. Every dark role keeps its current Oklab `L`; only `a/b` move, and every result is quantized to exact Hex8 before use.

The manipulation works: full-step mean foreground chroma falls by roughly 65–75%, and mean Oklab `+b` converges near the neutral Light Mid-Depth direction. The cost is not uniform. Small strict-margin misses appear in 3400K, 2000K loses ladder or primary margin as warmth falls, and 1200K loses several transformed text floors. Those failures are retained rather than “fixed,” because the fixed foreground constraint is the question being tested.

There is **no single scalar winner**. Lower warmth/chroma competes with transformed contrast, hierarchy, semantic clearance, and sequential regularity.

## What was held fixed

- Every `bg_0`…`bg_5` is byte-identical to its shipped family in all three lanes.
- Foreground Oklab lightness is inherited from the shipped dark role before Hex8 quantization.
- Semantic counts, `terminal_ansi_indices`, and `terminal_night_groups` are preserved per family.
- Canonical definitions, public manifests, CSS, package exports, and generated release themes are untouched.

## Fresh dependent searches

For **each profile × lane**, categorical and terminal accents were freshly searched with two deterministic seeds. Every lane within a profile uses the same controlled seed pair, so differences come from the fixed foreground constraint rather than random-seed assignment. Sequential anchors were freshly recomputed once per profile with two seeds and reused byte-identically across all three lanes because the sequential objective is invariant to foreground warmth. The search is a bounded stochastic hill-climb over exact Hex8 byte proposals, not a continuous-float optimization and not a global-optimum claim.

- categorical: each shipped byte ±18;
- terminal: each shipped byte ±16;
- sequential anchors: each shipped byte ±10;
- hard penalties: current pair-separation, hue-recognition, foreground-collision, transformed-background-contrast, sequential monotonicity/range/uniformity contracts;
- soft objective: separation, foreground clearance, realistic all-surface contrast, four sampled ±5% gain-corner evidence, and restrained movement from the mature shipped bank.

### Current-lane result

The current lane was not copied. It went through the same fresh two-seed searches. Exact outcomes:

- **3400K Dark:** categorical changed; terminal changed; sequential changed.
- **2000K Dark:** categorical changed; terminal reselected shipped exact values; sequential changed.
- **1200K Dark:** categorical changed; terminal reselected shipped exact values; sequential changed.

## Strict release status vs universal text usability

“Strict” means every current family-specific gate. “Universal text” isolates transformed `fg_0 / fg_1 / fg_2` floors of `4.5 / 3.5 / 2.4`. This prevents a small `6.78 < 6.80` family-margin miss from being narrated as a usability cliff while still recording the contract failure exactly.

| Profile | Lane | Strict contract | Universal text roles | Exact failed gates |
|---|---|:---:|:---:|---|
| 3400K Dark | Current warmth | PASS | PASS | None |
| 3400K Dark | Halfway | FAIL | PASS | `fg_0 transformed contrast 6.7820 < 6.8000` |
| 3400K Dark | Full step | FAIL | PASS | `fg_0 transformed contrast 6.7097 < 6.8000`<br>`foreground day chroma direction excess 0.0048 > 0.0030` |
| 2000K Dark | Current warmth | PASS | PASS | None |
| 2000K Dark | Halfway | FAIL | PASS | `foreground day adjacent min 7.9469 < 8.0000`<br>`foreground transformed adjacent min 5.9114 < 6.0000`<br>`terminal transformed fg_1 clearance 4.5290 < 5.0000` |
| 2000K Dark | Full step | FAIL | PASS | `fg_0 transformed contrast 5.4699 < 5.6500`<br>`foreground day adjacent min 7.9661 < 8.0000`<br>`foreground transformed adjacent min 5.7836 < 6.0000`<br>`foreground day chroma direction excess 0.0051 > 0.0030`<br>`terminal day fg_0 clearance 11.9557 < 12.5000`<br>`terminal transformed fg_1 clearance 4.1014 < 5.0000` |
| 1200K Dark | Current warmth | PASS | PASS | None |
| 1200K Dark | Halfway | FAIL | FAIL | `fg_0 transformed contrast 5.0675 < 5.3000`<br>`fg_1 transformed contrast 3.3399 < 3.5000`<br>`foreground transformed adjacent min 8.4133 < 9.0000`<br>`foreground day chroma direction excess 0.0033 > 0.0030`<br>`categorical sampled-corner foreground clearance 4.6431 < 4.7000`<br>`terminal transformed fg_0 clearance 3.6754 < 4.0000` |
| 1200K Dark | Full step | FAIL | FAIL | `fg_0 transformed contrast 4.7981 < 5.3000`<br>`fg_1 transformed contrast 3.1656 < 3.5000`<br>`fg_2 transformed contrast 2.3299 < 2.4000`<br>`foreground transformed adjacent min 7.8557 < 9.0000`<br>`foreground day chroma direction excess 0.0044 > 0.0030`<br>`categorical transformed fg_1 clearance 4.4367 < 4.8000`<br>`categorical sampled-corner foreground clearance 4.1799 < 4.7000`<br>`terminal transformed fg_0 clearance 3.7027 < 4.0000` |

## Combined metrics

Bold marks only the best-performing lane(s) **within each profile for that metric**. Values are not bold merely for passing. Directions compete; there is no aggregate winner. Gain-corner values are extrema observed at four sampled corners, not continuous-box guarantees.

| Metric | Direction | 3400K Dark Current warmth | 3400K Dark Halfway | 3400K Dark Full step | 2000K Dark Current warmth | 2000K Dark Halfway | 2000K Dark Full step | 1200K Dark Current warmth | 1200K Dark Halfway | 1200K Dark Full step |
|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Foreground mean chroma | ↓ lower | 0.0379 | 0.0250 | **0.0134** | 0.0472 | 0.0301 | **0.0137** | 0.0546 | 0.0338 | **0.0135** |
| Foreground mean +b | ↓ lower | 0.0375 | 0.0243 | **0.0115** | 0.0460 | 0.0286 | **0.0115** | 0.0528 | 0.0321 | **0.0115** |
| Foreground chroma reduction vs current | ↑ higher | 0.0% | 33.9% | **64.7%** | 0.0% | 36.2% | **71.0%** | 0.0% | 38.0% | **75.3%** |
| Foreground adjacent ΔEOK, day minimum | ↑ higher | 10.41 | 10.46 | **10.48** | **8.04** | 7.95 | 7.97 | **11.79** | 11.71 | 11.66 |
| Foreground adjacent ΔEOK, transformed minimum | ↑ higher | 8.70 | **8.72** | 8.62 | **6.20** | 5.91 | 5.78 | **9.16** | 8.41 | 7.86 |
| FG-0 worst-surface transformed contrast | ↑ higher | **6.83** | 6.78 | 6.71 | **5.86** | 5.66 | 5.47 | **5.32** | 5.07 | 4.80 |
| FG-1 worst-surface transformed contrast | ↑ higher | **4.94** | 4.90 | 4.85 | **4.66** | 4.53 | 4.39 | **3.52** | 3.34 | 3.17 |
| FG-2 worst-surface transformed contrast | ↑ higher | **3.08** | 3.07 | 3.06 | **3.31** | 3.29 | 3.27 | **2.48** | 2.41 | 2.33 |
| Categorical pair separation, day | ↑ higher | **15.18** | **15.18** | 15.00 | **18.59** | **18.59** | **18.59** | 20.75 | 20.84 | **21.38** |
| Categorical pair separation, transformed | ↑ higher | **11.61** | **11.61** | 11.45 | **14.15** | **14.15** | **14.15** | **10.41** | 9.79 | 9.41 |
| Categorical foreground clearance, day | ↑ higher | 7.03 | 8.14 | **9.03** | 9.48 | 9.49 | **10.12** | 6.32 | 7.86 | **9.88** |
| Categorical foreground clearance, transformed | ↑ higher | 6.41 | 6.67 | **6.85** | 5.50 | 6.34 | **6.67** | **4.89** | 4.85 | 4.44 |
| Categorical BG-0 transformed contrast | ↑ higher | **3.01** | **3.01** | **3.01** | **3.05** | **3.05** | **3.05** | **3.10** | **3.10** | 3.01 |
| Terminal pair separation, day | ↑ higher | 11.36 | 11.36 | **12.15** | 12.62 | **12.77** | 12.56 | 12.35 | **12.60** | 12.60 |
| Terminal group separation, transformed | ↑ higher | 7.80 | 7.80 | **8.58** | 7.75 | 7.56 | **8.07** | 4.13 | 4.07 | **4.37** |
| Terminal foreground clearance, day | ↑ higher | 8.13 | 8.11 | **8.19** | **8.25** | 7.45 | 8.00 | 8.96 | 9.78 | **10.95** |
| Terminal foreground clearance, transformed | ↑ higher | 5.16 | 5.56 | **5.94** | **4.75** | 4.53 | 4.10 | **4.13** | 3.68 | 3.70 |
| Terminal BG-0 transformed contrast | ↑ higher | 5.29 | 5.29 | **5.32** | **4.52** | 4.51 | 4.50 | **4.55** | **4.55** | 4.52 |
| Sequential day CV | ↓ lower | **0.0423** | **0.0423** | **0.0423** | **0.0485** | **0.0485** | **0.0485** | **0.0562** | **0.0562** | **0.0562** |
| Sequential day max:min | ↓ lower | **1.146** | **1.146** | **1.146** | **1.141** | **1.141** | **1.141** | **1.230** | **1.230** | **1.230** |
| Sequential transformed CV | ↓ lower | **0.0000** | **0.0000** | **0.0000** | **0.0000** | **0.0000** | **0.0000** | **0.0000** | **0.0000** | **0.0000** |
| Sequential transformed max:min | ↓ lower | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** | **1.000** |
| Sequential day lightness range | ↑ higher | **0.5940** | **0.5940** | **0.5940** | **0.7047** | **0.7047** | **0.7047** | **0.7595** | **0.7595** | **0.7595** |
| Sequential transformed lightness range | ↑ higher | **0.5128** | **0.5128** | **0.5128** | **0.5447** | **0.5447** | **0.5447** | **0.5218** | **0.5218** | **0.5218** |
| Sampled categorical gain-corner pair minimum | ↑ higher | **11.05** | **11.05** | 10.88 | **13.85** | **13.85** | **13.85** | **10.10** | 9.40 | 8.96 |
| Sampled terminal gain-corner pair minimum | ↑ higher | 7.26 | 7.26 | **7.86** | 7.42 | 7.52 | **7.86** | 4.08 | 3.96 | **4.28** |
| Sampled sequential gain-corner CV maximum | ↓ lower | **0.0082** | **0.0082** | **0.0082** | **0.0043** | **0.0043** | **0.0043** | **0.0015** | **0.0015** | **0.0015** |

## Reader-facing proof domains

The [live page](index.html) keeps all three warmth lanes visible together by default for the selected profile and provides controls for:

- profile: 3400K / 2000K / 1200K;
- commanded vs exact signal simulation;
- optional single-candidate focus.

It includes complete anatomy, a substantial editorial hierarchy, realistic code/terminal syntax and all semantic roles, a dense dashboard with categories/statuses/table/forms, sequential gradient and heatmap, real Mars MOLA scalar data, Mona Lisa photographic mapping, and a scientific propagation figure. Mars and Mona are candidate-specific commanded PNGs with separately generated exact-simulated PNGs; raster evidence is not a CSS-only transform.

## Static review captures

The interactive page is authoritative. These committed captures make the same comparison reviewable directly on GitHub.

### Complete anatomy across all dark profiles

| Profile | Commanded | Exact simulated |
|---|---|---|
| 3400K Dark | ![3400K Dark commanded anatomy](review-captures/3400k-dark-anatomy-commanded.png) | ![3400K Dark exact simulated anatomy](review-captures/3400k-dark-anatomy-simulated.png) |
| 2000K Dark | ![2000K Dark commanded anatomy](review-captures/2000k-dark-anatomy-commanded.png) | ![2000K Dark exact simulated anatomy](review-captures/2000k-dark-anatomy-simulated.png) |
| 1200K Dark | ![1200K Dark commanded anatomy](review-captures/1200k-dark-anatomy-commanded.png) | ![1200K Dark exact simulated anatomy](review-captures/1200k-dark-anatomy-simulated.png) |

### Full proof domains in 3400K Dark

| Domain | Commanded | Exact simulated |
|---|---|---|
| Terminal | ![Terminal commanded](review-captures/3400k-dark-terminal-commanded.png) | ![Terminal exact simulated](review-captures/3400k-dark-terminal-simulated.png) |
| Dashboard | ![Dashboard commanded](review-captures/3400k-dark-dashboard-commanded.png) | ![Dashboard exact simulated](review-captures/3400k-dark-dashboard-simulated.png) |
| Science and images | ![Science commanded](review-captures/3400k-dark-science-commanded.png) | ![Science exact simulated](review-captures/3400k-dark-science-simulated.png) |

### Phone-width focused state

![2000K Dark Full Step exact simulated at 390 px](review-captures/phone-2000k-full-simulated.png)

## Exact values

### 3400K Dark

#### Current warmth

```text
Surfaces:    090807 100E0C 181612 201D19 29251F 32241B
Foregrounds: DDD0B2 BDAE93 908472
Categorical: 6E96D7 E2AA67 2E8B7E 67BE95 945D48 C4779A
Terminal:    F5AD9A 7EB798 CA9246 B4C6F7 DA95C9 6ADDD8
Sequential:  282527 51404F 7F5E69 A17C6C C49D70 EBCD9F
```

#### Halfway

```text
Surfaces:    090807 100E0C 181612 201D19 29251F 32241B
Foregrounds: DAD0BF BAAE9E 8F8477
Categorical: 6E96D7 E0AA67 2E8B7E 67BE95 945D48 C4779A
Terminal:    F5AD9A 7EB798 CA9246 B4C6F7 DA95C9 6ADDD8
Sequential:  282527 51404F 7F5E69 A17C6C C49D70 EBCD9F
```

#### Full step

```text
Surfaces:    090807 100E0C 181612 201D19 29251F 32241B
Foregrounds: D6D0CC B7AEA8 8E847B
Categorical: 6E96D5 DDAA69 2E8B7E 67BE95 945D48 C3779A
Terminal:    F6AE9B 80B797 C89245 B5C6F9 D895D2 60E0DC
Sequential:  282527 51404F 7F5E69 A17C6C C49D70 EBCD9F
```

### 2000K Dark

#### Current warmth

```text
Surfaces:    070504 0D0A09 15110E 1E1814 271F1B 30221B
Foregrounds: EED5AE D3BB99 AA9D8B
Categorical: 66B0D4 E99096 A46449 A8E2AA
Terminal:    EC8B96 74E5C0 C39C49 A7D1FB
Sequential:  18110F 4B343E 795166 A27881 C39A8C FAD3AC
```

#### Halfway

```text
Surfaces:    070504 0D0A09 15110E 1E1814 271F1B 30221B
Foregrounds: E6D6C1 CDBCA8 A99D90
Categorical: 66B0D4 E99096 A46449 A8E2AA
Terminal:    EB8B9C 73E5C0 C39B59 A4CDFF
Sequential:  18110F 4B343E 795166 A27881 C39A8C FAD3AC
```

#### Full step

```text
Surfaces:    070504 0D0A09 15110E 1E1814 271F1B 30221B
Foregrounds: DED7D3 C6BDB7 A89D94
Categorical: 66B0D4 E99096 A46449 A8E2AA
Terminal:    EE8D9A 74E5C0 C39B59 9EC6FF
Sequential:  18110F 4B343E 795166 A27881 C39A8C FAD3AC
```

### 1200K Dark

#### Current warmth

```text
Surfaces:    060302 0C0806 130E0B 1C1511 251C17 2E1E17
Foregrounds: FFE5BD CBAF89 A18C73
Categorical: BB6572 8EF0FF E9B76C
Terminal:    F29298 C9FFB4 DDCD81
Sequential:  160B09 4B3042 6F4C6E 967387 BD9995 FFE1B7
```

#### Halfway

```text
Surfaces:    060302 0C0806 130E0B 1C1511 251C17 2E1E17
Foregrounds: F7E6D1 C3B19B 9D8D7C
Categorical: B5606F 8EF0FF E3B669
Terminal:    F19298 C9FFB4 DCCC80
Sequential:  160B09 4B3042 6F4C6E 967387 BD9995 FFE1B7
```

#### Full step

```text
Surfaces:    060302 0C0806 130E0B 1C1511 251C17 2E1E17
Foregrounds: EEE7E3 BBB2AC 988E85
Categorical: B15F6D 8EF0FF DBB363
Terminal:    FF9E9F C8FFB4 DDCC80
Sequential:  160B09 4B3042 6F4C6E 967387 BD9995 FFE1B7
```

## Search provenance and reproducibility

- Exact selected data, unrounded metrics, per-seed objectives, bounds, changed/reselected flags, continuous float maps, Hex8 previews, and sampled gain corners: [`search-results.json`](search-results.json)
- Reproducible bounded search: [`search_full_palette.py`](search_full_palette.py)
- Deterministic renderer: [`../../../tools/render_dark_foreground_warmth_experiment.py`](../../../tools/render_dark_foreground_warmth_experiment.py)
- Independent verification: [`../../../tests/test_dark_foreground_warmth_experiment.py`](../../../tests/test_dark_foreground_warmth_experiment.py)

The simulated state applies each family's documented encoded-sRGB diagonal gain vector. The ±5% samples scale nonzero G/B gains only; exact zero blue remains zero.

## Promotion boundary

Nothing here is canonical. If a warmth lane is chosen, promotion is a separate pass that must update authoritative definitions, transformed targets, generated exports, release invariants, public documentation, and downstream themes. Experimental prose, failed candidates, and comparison-only assets should not leak into the production reader path.
