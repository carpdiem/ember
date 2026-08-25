# G2 categorical palette finalists

**Status:** `AWAITING_MICHAEL_SELECTION`
**Selection:** `null`
**Production promotion:** not authorized

## Recommendation

**Recommend B** for the best target-improvement/churn/dual-state balance. It clears the deterministic +0.05 ΔE_OK shortlist delta, has the lowest maximum commanded deviation among target-improving frontier rows, and improves transformed-pair minimum. A is the aggressive 1.5px option; C is the transformed-pair option.

The +0.05 ΔE_OK value is a deterministic shortlist delta, not a human visibility floor. Human visibility and width capacity remain **UNKNOWN**.

## Exact finalists

| Choice | Candidate ID | Exact role Hex8 | 1.5px proxy | Δ vs baseline | Transformed pair | Max move | Chromium |
|---|---|---|---:|---:|---:|---:|---|
| A | `157e8462e3f11e0429d1d13cbdfbb2a288aa6036c8cdd2ecb29e2937eb5e0689` | `#289076 #2B1951 #A45E76 #692508 #045425 #3C5B95` | 8.225 | +0.598 | 14.174 | 3.220 | PASS |
| B | `d7173ca6fb71a573775b71276ff983028890079b5d90354c5d2831e09f088293` | `#39937C #2B1044 #A35C80 #692501 #125621 #3F5B99` | 7.712 | +0.084 | 15.167 | 1.800 | PASS |
| C | `19ac839f58c92bf94095e77b176389b5208fb34a1370676d7957c50f859de82a` | `#279284 #2A1045 #A25E76 #642505 #0A521E #395B93` | 7.685 | +0.057 | 15.986 | 2.403 | PASS |

## Browser evidence

Baseline and A/B/C each contain 25,920 ordered real-Chromium role observations and 32,400 reconstructed pair rows. Every observation replay and every browser residual gate passed. Evidence is split into separately hashed files below 50 MB. Full-image hashes are not used as perceptual evidence.

## Review surface

Open [`index.html`](index.html). It includes commanded and exact transformed desktop plots, true 390px phone compositions, uniform color-only lines, a separate style-stress panel, legends, crossings, endpoints, sparklines, Financial Cockpit, Thesis Baskets, exact role moves, and actual browser minima.

## Boundary

This package stops at Michael's G2 selection. It does not modify G0, G1, production palette values, exports, or downstream consumers.
