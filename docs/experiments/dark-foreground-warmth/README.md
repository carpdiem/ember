# Dark foreground warmth exploration

> **Branch:** `exp/dark-foreground-warmth`<br>
> **Status:** isolated experiment; not a production palette update<br>
> **Live comparison:** [open `index.html`](index.html)

## Bottom line

Design the seen state first: even transformed distinctness binds before commanded warmth; leftover exact-Hex8 freedom buys the halfway hue step for ink and surfaces.

This fourth pass compares all three shipped dark profiles under two commanded philosophies: **current** (each shipped dark palette scored verbatim) and **halfway** (ink *and* surfaces moved 50% of the way toward the 3400K Light Mid-Depth warmth step). The optimizer scores every candidate only after exact Hex8 quantization, with transformed adjacent ΔE ≥ 2.5, a uniformity ratio ≤ 1.6, transformed span ≥ 6.0, and text contrast floors as hard gates. Warmth closeness, chroma, and movement compete only after usability, so there is **no single scalar winner**.

## Methodology

- **Transformed-first gating.** Even the *transformed* (warm-display simulated) appearance must keep distinct surfaces and readable text before any commanded-warmth objective is scored. This is the pass's central discipline: the seen state is designed first.
- **Variable surface count.** The halfway lane searches background counts 3–6 per profile; each count gets a bounded exact-Hex8 search with deterministic seeds. Leftover byte freedom inside the ±24-byte radius is what buys the hue step.
- **Fresh dependent banks.** Categorical (with a larger-count bonus), terminal, and sequential banks are re-searched against each lane's selected exact system — never copied across lanes.
- **Recomputed evidence.** The renderer recomputes every published metric and both badge families from the serialized Hex8 values; no upstream release-status field exists in this schema to trust.

## Chosen surface counts

| Profile | Current bg_count | Halfway bg_count | Halfway choice rule / note |
|---|:---:|:---:|---|
| 3400K Dark | 6 | 5 | shared dark anchor; floating warm light anchor; interiors refined to even CAM16-UCS steps >=3.84 |
| 2000K Dark | 6 | 4 | shared dark anchor; shared light anchor; interiors refined to even CAM16-UCS steps >=3.84 |
| 1200K Dark | 6 | 4 | shared dark anchor; shared light anchor; interiors refined to even CAM16-UCS steps >=3.84 |

## Categorical adoption notes

- **3400K Dark · Current:** shipped count retained; shipped count is 6 colors.
- **3400K Dark · Halfway:** no larger count passed all gates; shipped retained; shipped count is 6 colors.
- **2000K Dark · Current:** shipped count retained; shipped count is 4 colors.
- **2000K Dark · Halfway:** no larger count passed all gates; shipped retained; shipped count is 4 colors.
- **1200K Dark · Current:** shipped count retained; shipped count is 3 colors.
- **1200K Dark · Halfway:** no larger count passed all gates; shipped retained; shipped count is 3 colors.

## Distinctness vs universal text badges

The third pass serialized a strict release status per lane; this schema does not. Instead the renderer computes two lightweight lenses from the Hex8 values themselves:

- **Distinctness** — transformed adjacent ΔE ≥ 2.5 on every step, uniformity ratio ≤ 1.6, and span ≥ 6.0;
- **Universal text** — transformed worst-surface contrast floors of `4.5 / 3.5 / 2.4` for `fg_0 / fg_1 / fg_2`, with `fg_0` raised to each family's own primary-text floor when stricter.

| Profile | Lane | Distinctness | Universal text |
|---|---|:---:|:---:|
| 3400k-dark | Current | FAIL | PASS |
| 3400k-dark | Halfway | PASS | PASS |
| 2000k-dark | Current | FAIL | PASS |
| 2000k-dark | Halfway | PASS | PASS |
| 1200k-dark | Current | FAIL | PASS |
| 1200k-dark | Halfway | PASS | PASS |

## Combined metrics

Rows are Pareto-ranked: transformed usability first, then commanded warmth. Every value is recomputed from the serialized Hex8 records by the renderer. Underline marks only the best-performing lane(s) **within each profile for that metric** — shown underlined on the page and **bold** in this markdown. Values are not decorated merely for passing a floor. Directions compete; there is no aggregate winner.

| Metric | Direction | 3400K Dark Current | 3400K Dark Halfway | 2000K Dark Current | 2000K Dark Halfway | 1200K Dark Current | 1200K Dark Halfway |
|---|:---:|---:|---:|---:|---:|---:|---:|
| Background surface count | ↑ higher | **6** | 5 | **6** | 4 | **6** | 4 |
| Transformed adjacent ΔEOK minimum | ↑ higher | 2.31 | **3.15** | 2.10 | **4.31** | 2.34 | **4.46** |
| Transformed uniformity ratio, max:min step | ↓ lower | 2.143 | **1.596** | 1.816 | **1.179** | 1.679 | **1.181** |
| Transformed surface span ΔEOK | ↑ higher | 14.57 | **16.46** | **14.84** | 13.98 | **14.91** | 14.68 |
| Transformed fg-background clearance minimum | ↑ higher | **33.58** | 27.19 | **38.63** | 29.78 | 34.07 | **34.14** |
| FG-0 transformed worst-surface contrast | ↑ higher | **6.83** | 6.81 | **5.86** | 5.65 | **5.32** | 5.30 |
| FG-1 transformed worst-surface contrast | ↑ higher | **4.94** | 3.51 | **4.66** | 3.51 | **3.52** | 3.50 |
| FG-2 transformed worst-surface contrast | ↑ higher | **3.08** | 2.41 | **3.31** | 2.42 | **2.48** | 2.40 |
| Commanded foreground mean +b | ↓ lower | **0.0375** | 0.0690 | **0.0460** | 0.0861 | **0.0528** | 0.0996 |
| Commanded foreground mean chroma | ↓ lower | **0.0379** | 0.0698 | **0.0472** | 0.0862 | **0.0546** | 0.1009 |

## Reader-facing proof domains

The [live page](index.html) keeps both warmth lanes visible together by default for the selected profile and provides controls for:

- profile: 3400K / 2000K / 1200K;
- commanded vs exact signal simulation;
- optional single-lane focus (all / current / halfway).

It includes complete anatomy, a substantial editorial hierarchy, realistic code/terminal syntax and all semantic roles, a dense dashboard with categories/statuses/table/forms, sequential gradient and heatmap, real Mars MOLA scalar data, Mona Lisa photographic mapping, and a scientific propagation figure. Mars and Mona are candidate-specific commanded PNGs with separately generated exact-simulated PNGs; raster evidence is not a CSS-only transform.

## Static review captures

The interactive page is authoritative. These committed captures make the same comparison reviewable directly on GitHub:

- [`3400k-dark-anatomy-commanded.png`](review-captures/3400k-dark-anatomy-commanded.png)
- [`3400k-dark-anatomy-simulated.png`](review-captures/3400k-dark-anatomy-simulated.png)
- [`2000k-dark-anatomy-commanded.png`](review-captures/2000k-dark-anatomy-commanded.png)
- [`2000k-dark-anatomy-simulated.png`](review-captures/2000k-dark-anatomy-simulated.png)
- [`1200k-dark-anatomy-commanded.png`](review-captures/1200k-dark-anatomy-commanded.png)
- [`1200k-dark-anatomy-simulated.png`](review-captures/1200k-dark-anatomy-simulated.png)
- [`3400k-dark-terminal-commanded.png`](review-captures/3400k-dark-terminal-commanded.png)
- [`3400k-dark-terminal-simulated.png`](review-captures/3400k-dark-terminal-simulated.png)
- [`3400k-dark-dashboard-commanded.png`](review-captures/3400k-dark-dashboard-commanded.png)
- [`3400k-dark-dashboard-simulated.png`](review-captures/3400k-dark-dashboard-simulated.png)
- [`3400k-dark-science-commanded.png`](review-captures/3400k-dark-science-commanded.png)
- [`3400k-dark-science-simulated.png`](review-captures/3400k-dark-science-simulated.png)
- [`metrics-table.png`](review-captures/metrics-table.png)
- [`phone-metrics.png`](review-captures/phone-metrics.png)
- [`phone-2000k-halfway-simulated.png`](review-captures/phone-2000k-halfway-simulated.png)

![2000K Dark Halfway exact simulated at 390 px](review-captures/phone-2000k-halfway-simulated.png)

## Exact values

### 3400K Dark

#### Current (6 surfaces)

```text
Surfaces:    090807 100E0C 181612 201D19 29251F 32241B
Foregrounds: DDD0B2 BDAE93 908472
Categorical: 6E96D7 E2AA67 2E8B7E 67BE95 945D48 C4779A
Terminal:    F5AD9A 7FB798 C89145 B4C6F7 D795D2 62E1DA
Sequential:  282527 51404F 7F5E69 A17C6C C49D70 ECCD9F
```

#### Halfway (5 surfaces)

```text
Surfaces:    070403 100906 1C120D 291B15 38271F
Foregrounds: DED79A 9F9464 837147
Categorical: 6E96D5 DDAA69 2E8B7E 67BE95 945D48 C3779A
Terminal:    F5AD9A 8EBC9C CA9F4A B4C6F7 D792CD 60E2E2
Sequential:  282527 51404F 7F5E69 A17C6C C49D70 ECCD9F
```

### 2000K Dark

#### Current (6 surfaces)

```text
Surfaces:    070504 0D0A09 15110E 1E1814 271F1B 30221B
Foregrounds: EED5AE D3BB99 AA9D8B
Categorical: 66B0D4 E99096 A46449 A8E2AA
Terminal:    EC8B96 74E5C0 C39C49 A7D1FB
Sequential:  18110E 4B343E 785167 A27882 C59A8B FCD6AB
```

#### Halfway (4 surfaces)

```text
Surfaces:    070403 140C09 201510 2E1E18
Foregrounds: E7CF7C B19D62 8B7A49
Categorical: 66B0D4 E99096 A46449 A3DCA9
Terminal:    EB8B9E 76E6BF C4AA4B A1D1FF
Sequential:  18110E 4B343E 785167 A27882 C59A8B FCD6AB
```

### 1200K Dark

#### Current (6 surfaces)

```text
Surfaces:    060302 0C0806 130E0B 1C1511 251C17 2E1E17
Foregrounds: FFE5BD CBAF89 A18C73
Categorical: BB6572 8EF0FF E9B76C
Terminal:    F29298 C9FFB4 DDCD81
Sequential:  170B09 4B3042 6F4C6D 967186 BD9995 FFE3B7
```

#### Halfway (4 surfaces)

```text
Surfaces:    070403 140C09 201510 2E1E18
Foregrounds: FFE384 CAB16D A1773D
Categorical: BB6572 8FF0FF E9B76C
Terminal:    F39399 CAFFC2 DDC57D
Sequential:  170B09 4B3042 6F4C6D 967186 BD9995 FFE3B7
```

## Search provenance and reproducibility

- Exact selected data, per-count system searches with seeds, iterations, evaluated candidate counts, accepted moves, objectives, continuous float maps, Hex8 previews, categorical trials, and adoption notes: [`transformed-first-results.json`](transformed-first-results.json)
- Reproducible bounded search: [`search_transformed_first.py`](search_transformed_first.py)
- Deterministic renderer: [`../../../tools/render_dark_foreground_warmth_experiment.py`](../../../tools/render_dark_foreground_warmth_experiment.py)
- Independent verification: [`../../../tests/test_dark_foreground_warmth_experiment.py`](../../../tests/test_dark_foreground_warmth_experiment.py)

The simulated state applies each family's documented encoded-sRGB diagonal gain vector.

## Promotion boundary

Nothing here is canonical. If a warmth lane is chosen, promotion is a separate pass that must update authoritative definitions, transformed targets, generated exports, release invariants, public documentation, and downstream themes. Experimental prose, failed candidates, and comparison-only assets should not leak into the production reader path.
