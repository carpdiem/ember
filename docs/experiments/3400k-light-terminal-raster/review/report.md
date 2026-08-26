# 3400K Light terminal accent rebuild

## Verdict

Only **A-raster-maximum** passes the declared nominal browser gate. It remains an experimental human-review candidate, not a production selection.

## Viewing model

- Commanded/day: CAM16 `L_A=64`, `Y_b=20`, 0.75% flare.
- Transformed/low-light: CAM16 `L_A=8`, `Y_b=3`, 0.75% flare.
- Exact 3400K encoded-sRGB gains: `[1.0, 0.74, 0.53]`.

## Eligible candidate

`#98074F #517304 #844601 #396EDB #8339A7 #0B7F8C`

The candidate removes the nominal accent→`fg_0` near-collision tail for every role and materially improves red, green, and blue active-pixel p10 at DPR1/2. Yellow is allowed at no worse than 85% of baseline p10; it retains zero nominal near-tail samples. Accent-pair browser p10 is nonregressive versus the current Light bank.

## Status

- Human selection: **none**
- Production promotion: **false**
- B/C: retained as rejected diagnostics
- Gain-corner browser rows: report-only sampled diagnostics
- Analytical contrast/pair gain-corner gates: hard
