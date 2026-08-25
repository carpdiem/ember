# Clean-sheet G2 palette review

**Status:** `AWAITING_MICHAEL_SELECTION`
**Selection:** `null`
**Human 1.5px capacity:** `UNKNOWN`
**Production promotion:** `false`

## Recommendation

**Recommend C; Michael decides.** C produces the largest category↔`fg_0` gains at all three widths and is the only finalist that improves 2px and 3px as well as 1.5px. Its teal / green / pink / red / olive / blue bank is the most visually mature. It accepts a smaller categorical-only gain than A/B while retaining a +1.70 ΔE_OK gated 1.5px categorical gain. A maximizes categorical-only separation but regresses category↔`fg_0` at 2px and 3px. B is the middle option and shares those regressions.

## Actual gated transformed minima

These are derived from the verified pair rows. Headline minima use `bg_0` and `bg_1` only. `bg_2` is report-only and cannot bind.

| Choice | Category 1.5 | Category 2 | Category 3 | fg_0 1.5 | fg_0 2 | fg_0 3 |
|---|---:|---:|---:|---:|---:|---:|
| REFERENCE | 8.45061119 | 11.72933559 | 12.07960554 | 5.34772026 | 8.46730718 | 8.75274293 |
| A | 10.71459562 | 14.72111734 | 15.42553568 | 6.19576033 | 8.29851824 | 8.34771635 |
| B | 10.32223006 | 13.85554683 | 14.23648775 | 6.69063841 | 8.29851824 | 8.34771635 |
| C | 10.15168599 | 13.29463249 | 13.58450059 | 7.30273837 | 9.19528305 | 9.41748066 |

## Methods and tradeoffs

- **REFERENCE — Current approved bank:** Frozen comparison only. It anchors gains and regressions; it is not a finalist.
- **A — Constructive cool-lighter / warm-darker:** Maximizes categorical-only raster separation. It accepts more purple/brown character and regresses category↔fg_0 at 2px and 3px.
- **B — Transformed-native targets inverted through exact gains:** The middle categorical option. It improves 1.5px category↔fg_0, but shares A’s 2px and 3px category↔fg_0 regressions.
- **C — Continuity compromise with zero-to-two broad anchors:** A mature teal / green / pink / red / olive / blue bank. It gives up some categorical-only gain versus A/B to improve category↔fg_0 at every width.

## Browser evidence

Reference and A/B/C each independently PASS with 30,240 observations and 58,320 pairs: 32,400 categorical pairs plus 25,920 category↔`fg_0` pairs. Both residual families PASS. Every evidence file is below 50 MB.

## Review surface

Open [`index.html`](index.html). Desktop shows reference and A/B/C simultaneously. Phone uses complete stacked cards, without a carousel or nested scrolling. Every card contains exact commanded/transformed Hex8, gated minima and report-only `bg_2`, 1.5px `bg_0` and 2px `bg_1` crossings, a weakest-three analog, luminance-only strip, exact category↔`fg_0` binding, fixed fake-finance/basket geometry, legends/fills, and worst sampled sensitivity.

## Boundary

This package records a recommendation, not a selection. It does not modify production, G0/G1/previous G2 history, or downstream consumers.
