# Sample-screen analysis

Generated from the exact README screenshots. These image-level diagnostics are
guardrails, not a model of eye strain: they detect saturation and abrupt luminance
edges but cannot substitute for long-duration viewing on real hardware.

## Palette-level bi-state gates

| Family | Categories | Day min ΔEOK | Day min hue gap | Shifted min ΔEOK | Min shifted category / bg contrast | Mean / max raw chroma | Terminal day / shifted min to fg_0 | Terminal day / shifted min to fg_1 | Terminal day / shifted min to fg_2 | FG ladder day / shifted adjacent min | Min shifted terminal contrast |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 6 | 16.18 | 20.03° | 10.53 | 3.03:1 | 0.1009 / 0.1107 | 8.61 / 6.80 | 8.35 / 6.83 | 12.75 / 12.67 | 10.99 / 9.06 | 4.79:1 |
| 3400K Light | 6 | 16.37 | 44.96° | 11.58 | 3.35:1 | 0.1266 / 0.1408 | 18.19 / 17.89 | 11.53 / 11.35 | 9.36 / 6.63 | 8.52 / 7.32 | 4.51:1 |
| 2000K Dark | 4 | 20.47 | 21.04° | 14.52 | 3.01:1 | 0.1034 / 0.1109 | 12.62 / 7.70 | 8.72 / 2.77 | 13.30 / 10.78 | 12.14 / 9.45 | 4.55:1 |
| 1200K Dark | 3 | 22.00 | 48.12° | 10.05 | 3.07:1 | 0.1049 / 0.1103 | 9.51 / 4.89 | 11.86 / 3.14 | 13.80 / 10.75 | 14.22 / 9.73 | 4.52:1 |

Release gates: categorical commanded mean chroma 0.09–0.105 and maximum
chroma ≤ 0.111; family-specific daytime, hue-gap, transformed-separation, and
graphical category/background contrast floors; cross-state hue consistency is
intentionally not required;
authored transformed accent targets reproduced within 0.15 ΔEOK; transformed
terminal foreground-capable ANSI slots ≥ 4.5:1; deep terminal accents also clear
their day and transformed separation floors against every foreground role, while
the foreground ladder preserves bounded adjacent distances, balanced lightness gaps,
lightness-dominant steps, aligned chroma direction, and bounded hue/chroma; category
and accent counts
must never increase as the target temperature falls.

## Screenshot-level diagnostics

| Screenshot | High-contrast edge fraction | High-chroma pixel fraction | Oklab chroma p99 |
|---|---:|---:|---:|
| `terminal-commanded.png` | 1.9704% | 0.4838% | 0.0917 |
| `terminal-simulated.png` | 0.8434% | 1.7453% | 0.1575 |
| `data-commanded.png` | 1.5674% | 0.5332% | 0.1103 |
| `data-simulated.png` | 0.7928% | 5.2704% | 0.1858 |

Interpretation: small high-contrast edge fractions are expected around glyphs,
axes, and markers. Commanded high-chroma area should remain scarce. A deep warm
transform itself makes most surviving pixels red, so transformed chroma is
descriptive rather than a release gate. Lines use dash, marker, and text-label
redundancy because no color metric can rescue information after the display
transform removes a channel.
