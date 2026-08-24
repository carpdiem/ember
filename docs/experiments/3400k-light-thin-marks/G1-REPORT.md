# G1 Phase 2B: real-Chromium raster calibration checkpoint

**Verdict: `BROWSER_CALIBRATION_PASS`. Browser machinery is sufficient and `phase3_search_authorized=true`. Production promotion remains blocked.**

The current 3400K Light categorical bank remains byte-frozen at `c4c25e480912f8f54cbd8c992c0b6eb520dc0b8f`. The calibration used approved implementation input `922ba7faa45ccdb56e95356750d353c7602da78a`. No candidate search, candidate colours, `categorical_line` bank, production palette edit, or export edit is present.

## Capture and factoring

- Real Chromium via GStack: 22,320 exact 160×128 tiles in 176 chunks, comprising 720 monochrome masks and 21,600 role/lane colour observations.
- Each chunk used 128 eager same-origin `srcdoc` iframes and one chained `goto` + `screenshot`; each iframe rasterized at local `(0,0)`. DPR 1 and 2 were captured with screenshot scale equal to DPR.
- The 2,160 canonical bases and ten exact role/lane observations reconstruct all 32,400 `planned-N` pair rows. All IDs and dimension mappings independently replayed exactly.
- Browser time was 75.846 s at 294.282 tiles/s. Total capture, analysis, evidence serialization, and sentinels took 100.476 s (322.466 effective pair rows/s).
- Eight deterministic standalone-vs-batch observation tiles matched at every retained station.

Inline SVG atlases and canvas `drawImage` are not release oracles. The tracked evidence is compact and factored; raw screenshots were temporary and removed.

## Line-core policy and support

Chromium supplied SVG arc lengths, points, and tangents. Monochrome black-on-white masks define encoded-sRGB coverage as `1 - mean(mask_rgb8)/255`. Stations exclude endpoints and dash transitions; the supported paths contain no joins, markers, or crossings in the measured core. Each longitudinal normal slice chooses the highest-coverage pixel, then nearest centerline, then device `y/x`; coverage below 0.5 is unsupported. Aggregation is per-channel median.

All 720 masks, 21,600 observations, and 32,400 pair rows were supported. There were **0 unsupported** and **0 errored** rows. The factored artifacts preserve sample coordinates, coverage, observed RGB8, reconstructible predicted RGB8/residuals, and pair references:

- `raster-masks.json`
- `raster-observations.json`
- `raster-baseline.json`
- `raster-verification.json`

## Calibration acceptance

The calibration engineering metric is Oklab Euclidean distance ×100 (ΔE_OK). The 0.95 correlation floor applies only to the global pooled sample set. Local correlations are diagnostic and are not represented as individually meeting that floor.

| Gate | Limit | Observed | Result |
|---|---:|---:|---|
| Global pooled correlation | ≥0.95 | 0.99998140 | PASS |
| Global pooled MAE | ≤0.75 ΔE_OK | 0.00836871 | PASS |
| Global pooled p95 | report | 0.04308115 ΔE_OK | — |
| Global pooled max | report | 0.74498721 ΔE_OK | — |
| Worst gate pair/background MAE | ≤0.75 ΔE_OK | 0.01483597 | PASS |

Every one of the 30 `bg_0`/`bg_1` pair/background gates passed. All 15 `bg_2` report-only rows are disclosed separately. The worst individual planned row was `planned-21860` (tied by `planned-21875`): transformed `bg_1`, 1.5px solid diagonal_45, DPR1, `cat.one` vs `cat.six`, row MAE 0.38880236 ΔE_OK.

RGB8 residuals over 6,717,600 channel values: MAE 0.02664851, p95 0, max 1; channel MAEs were `[0.02892283, 0.02750759, 0.02351509]`.

## Transform-order structural pin

The transformed tile places source-coloured background and stroke beneath one ancestor SVG `feColorMatrix`, with `color-interpolation-filters="sRGB"` and exact diagonal gains `[1, .74, .53]`. There are no pre-transformed literals. That source/DOM structure is the normative transform-after-raster/compositing proof. The unclipped diagonal encoded-sRGB model is linear and commutes with alpha compositing, so pixel agreement alone cannot establish operation order.

## Current-bank numerical reconnaissance, not human capacity

| Width | Gate rows | Pairs observed | Worst observed pair | Minimum observed ΔE_OK | Human capacity |
|---:|---:|---:|---|---:|---|
| 1.5px | 7,200 / 7,200 | 15 / 15 | cat.five vs cat.six (`planned-17445`) | 8.45061119 | UNKNOWN/UNPROVEN |
| 2.0px | 7,200 / 7,200 | 15 / 15 | cat.five vs cat.six (`planned-19350`) | 11.72933559 | UNKNOWN/UNPROVEN |
| 3.0px | 7,200 / 7,200 | 15 / 15 | cat.five vs cat.six (`planned-19815`) | 12.07960554 | UNKNOWN/UNPROVEN |

These are exact browser/proxy feasibility observations for the current bank, not a visibility floor, forced-choice result, width PASS/FAIL, or human capacity claim.

## Authorization and remaining gates

Phase 3 candidate search is authorized because coverage support is complete and every declared browser calibration gate passed. This does not authorize a candidate, palette change, or promotion.

Before any production promotion:

1. Run the preregistered multi-observer 2AFC visibility study.
2. Calibrate the final visibility floor on held-out human responses.
3. Assign width capacity only from that human evidence.
4. Pass G2 and G3 promotion gates.

## Review

- [Commanded/transformed index](review/g1-index.html)
- [Commanded structural specimen](review/g1-commanded.svg)
- [Transformed engineering specimen](review/g1-transformed.svg)
- [Commanded 390×844 phone specimen](review/g1-phone-commanded.svg)
- [Transformed 390×844 phone specimen](review/g1-phone-transformed.svg)
- [Deterministic browser probe](review/g1-browser-probe.html)
- [Calibration summary](proxy-calibration.json)
- [Observed pair ledger](raster-baseline.json)
