# Mona Lisa example assets

`mona-lisa-c2rmf-public-domain.jpg` is the source image for the sequential-colormap specimen.

- Work: *Mona Lisa* by Leonardo da Vinci
- Digital source: C2RMF retouched image, via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Mona_Lisa,_by_Leonardo_da_Vinci,_from_C2RMF_retouched.jpg)
- Commons license metadata: Public domain; attribution not required
- Source SHA-256: `5f223c31ba0a477eb7cbe5e5f959d822cbfc46081b19b96498cbd5601d9ac81d`

The four `mona-lisa-<palette>.png` files are deterministic generated artifacts. `tools/build_all.py` resizes the source, ranks pixels by WCAG relative luminance, stretches the 1st–99th percentile range, and maps it into each family's 256-sample sequential colors. If a family's authored low-to-high scalar ramp runs from light to dark, generation reverses the ramp for image mapping so dark source pixels remain dark and light source pixels remain light.

Do not edit the generated PNGs by hand. Regenerate them with:

```sh
uv run --extra dev python tools/build_all.py
```
