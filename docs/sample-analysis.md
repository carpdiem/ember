# Sample-screen analysis

Generated from the exact README screenshots. These image-level diagnostics are
guardrails, not a model of eye strain: they detect saturation and abrupt luminance
edges but cannot substitute for long-duration viewing on real hardware.

## Palette-level bi-state gates

| Family | Categories | Day min ΔEOK | Day min hue gap | Shifted min ΔEOK | Min shifted category / bg contrast | Mean / max raw chroma | Terminal day / shifted min to fg_0 | Min shifted terminal contrast |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3400K Dark | 6 | 15.00 | 21.08° | 11.45 | 2.99:1 | 0.0969 / 0.1045 | 8.67 / 6.58 | 6.06:1 |
| 3400K Light | 6 | 15.91 | 7.16° | 13.76 | 3.31:1 | 0.1016 / 0.1053 | 9.25 / 6.47 | 4.76:1 |
| 2000K Dark | 4 | 16.50 | 27.75° | 12.59 | 3.01:1 | 0.0903 / 0.0907 | 13.39 / 7.79 | 4.54:1 |
| 1200K Dark | 3 | 20.03 | 54.05° | 10.05 | 3.01:1 | 0.1016 / 0.1086 | 9.63 / 4.46 | 4.54:1 |

Release gates: categorical commanded mean chroma 0.09–0.105 and maximum
chroma ≤ 0.111; family-specific daytime, hue-gap, transformed-separation, and
graphical category/background contrast floors; cross-state hue consistency is
intentionally not required;
authored transformed accent targets reproduced within 0.15 ΔEOK; transformed
terminal foreground-capable ANSI slots ≥ 4.5:1; deep terminal accents also clear
their day and transformed separation floors against fg_0; category and accent counts
must never increase as the target temperature falls.

## Screenshot-level diagnostics

| Screenshot | High-contrast edge fraction | High-chroma pixel fraction | Oklab chroma p99 |
|---|---:|---:|---:|
| `terminal-commanded.png` | 2.1443% | 0.0329% | 0.0890 |
| `terminal-simulated.png` | 1.0213% | 15.9162% | 0.1728 |
| `data-commanded.png` | 1.5267% | 0.0000% | 0.1041 |
| `data-simulated.png` | 0.7370% | 22.2983% | 0.1860 |

Interpretation: small high-contrast edge fractions are expected around glyphs,
axes, and markers. Commanded high-chroma area should remain scarce. A deep warm
transform itself makes most surviving pixels red, so transformed chroma is
descriptive rather than a release gate. Lines use dash, marker, and text-label
redundancy because no color metric can rescue information after the display
transform removes a channel.
