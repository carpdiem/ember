# G1 Phase 2A: deterministic core checkpoint

**Verdict: `CORE_READY_BROWSER_PENDING`. This checkpoint is not Phase-3-ready.**

The current 3400K Light categorical bank remains byte-frozen at `c4c25e480912f8f54cbd8c992c0b6eb520dc0b8f`. No candidate search, candidate colours, `categorical_line` bank, production palette edit, or export edit is present.

## What is ready

- A complete **planned** raster matrix of 32,400 cases covering state × background × width × style × orientation × DPR × phase × all 15 categorical pairs.
- Explicit line-core selection: coverage ≥ 0.5, max-coverage pixel nearest the centreline, exclusions for endpoints/joins/markers/crossings/dash transitions, then per-channel median.
- Commanded solid identity in Oklab and transformed solid/composited-proxy reconnaissance in CAM16-UCS under pinned light-viewing engineering assumptions.
- Complete analytical category-vs-foreground, benchmark-neutral, and report-only terminal matrices (600 scenario rows).
- A named 45-sample asymmetric gain grid, a separate local-refinement protocol, and separate brightness uncertainty.
- A preregistered 15-pair 2AFC visibility protocol with no results.

## Metric ownership and viewing assumptions

Commanded solid minimum: **cat.three vs cat.six = 16.6381 ΔE_OK**.

Primary transformed solid CAM16-UCS minima are reported separately, never averaged:

| Surface | Pair | CAM16-UCS distance |
|---|---|---:|
| bg_0 | cat.one vs cat.five | 19.5185 |
| bg_1 | cat.one vs cat.five | 19.5293 |
| bg_2 | cat.one vs cat.five | 19.5303 |

The input is encoded sRGB in [0,1]. Coverage compositing occurs in encoded sRGB; gains `[1, .74, .53]` are applied **after** rasterization/compositing. `colour-science` receives XYZ on its 0–1 reference scale, D65 white normalized to Y=1 (mapped to Yw=100 cd/m²), and explicit CAM16 `L_A`, `Y_b`, and surround values. Primary conditions are Dim, flare 0, `L_A=14.2`, with per-surface `Y_b` 56.18/49.82/44.32. Sensitivity conditions are Average, flare 0.0075, `L_A` 9.5 and 19, with transformed-white-adapted `Y_b` 94.77/84.05/74.76. Flare is implemented as additive `flare_fraction × XYZ_D65_white` on the transformed stimulus before CAM16; it is an engineering sensitivity term, not measured device glare. Every scenario is reported separately and never averaged.

`compute_proxy_frontier(..., transformed_metric=callable)` routes every transformed solid and proxy distance through that callable. `proxy_acceptance` requires correlation ≥0.95 **and** maximum pair/background MAE ≤0.75; either bad polarity fails.

## Browser and human truth boundaries

`raster-baseline.json` is a planned-case ledger, **not observed browser measurements**. Every row is `PENDING_BROWSER_CALIBRATION`, with observed RGB and distances null. `proxy-calibration.json` contains the Phase 2B schema and acceptance thresholds but no samples, coordinates, observed RGB, correlation, MAE, or PASS. The browser release oracle remains mandatory.

Every width capacity is `UNKNOWN/UNPROVEN`. The 2AFC study has not run, so there is no visibility floor and no width PASS/FAIL. Analytical distances must not be relabelled as human capacity.

## Review

- [Commanded/transformed index](review/g1-index.html)
- [Commanded structural specimen](review/g1-commanded.svg)
- [Transformed engineering specimen](review/g1-transformed.svg)
- [Deterministic browser probe](review/g1-browser-probe.html)

The SVGs are structural review aids, not browser pixels. `bg_0` and `bg_1` are gate surfaces; `bg_2` remains report-only.

## Required Phase 2B work

1. Run the deterministic probe in real Chromium at the pinned DPRs/viewports and record renderer provenance.
2. Derive coverage and line-core coordinates from actual raster pixels; do not invent them.
3. Store predicted/observed RGB8 samples and evaluate pooled correlation plus every pair/background MAE gate.
4. Treat a missing browser binary as SKIP and every launch/probe/runtime failure as ERROR.
5. Run the preregistered multi-observer 2AFC study and held-out floor calibration before assigning any width capacity.
