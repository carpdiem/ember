# Sample-screen analysis

Generated from the exact README screenshots. These image-level diagnostics are
guardrails, not a model of eye strain: they detect saturation and abrupt luminance
edges but cannot substitute for long-duration viewing on real hardware.

## Palette-level bi-state gates

| Family | Categories | Day min ΔEOK | Day min hue gap | Shifted min ΔEOK | Min shifted category / bg contrast | Mean / max raw chroma | Terminal day / shifted min to fg_0 | Terminal day / shifted min to fg_1 | Terminal day / shifted min to fg_2 | FG ladder day / shifted adjacent min | Min shifted terminal contrast |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 6 | 15.00 | 20.23° | 11.45 | 3.01:1 | 0.0971 / 0.1045 | 8.67 / 6.58 | 8.13 / 5.16 | 11.72 / 10.18 | 10.41 / 8.70 | 5.29:1 |
| 3400K Light | 6 | 16.73 | 31.75° | 12.41 | 3.03:1 | 0.0988 / 0.1037 | 9.25 / 6.47 | 9.47 / 6.70 | 9.22 / 7.13 | 8.52 / 7.32 | 4.65:1 |
| 2000K Dark | 4 | 17.00 | 27.76° | 12.91 | 3.05:1 | 0.0956 / 0.1082 | 13.73 / 7.64 | 10.86 / 5.03 | 8.25 / 4.75 | 8.04 / 6.20 | 4.52:1 |
| 1200K Dark | 3 | 20.72 | 65.03° | 10.25 | 3.12:1 | 0.1047 / 0.1107 | 9.69 / 4.49 | 8.96 / 4.13 | 14.68 / 11.29 | 11.79 / 9.16 | 4.55:1 |

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
| `terminal-commanded.png` | 1.9799% | 0.0000% | 0.0890 |
| `terminal-simulated.png` | 0.8596% | 15.9101% | 0.1613 |
| `data-commanded.png` | 1.5670% | 0.0000% | 0.1037 |
| `data-simulated.png` | 0.7034% | 21.6386% | 0.1860 |

Interpretation: small high-contrast edge fractions are expected around glyphs,
axes, and markers. Commanded high-chroma area should remain scarce. A deep warm
transform itself makes most surviving pixels red, so transformed chroma is
descriptive rather than a release gate. Lines use dash, marker, and text-label
redundancy because no color metric can rescue information after the display
transform removes a channel.
