# Unified specimen assets

Every raster on the Ember site is either an immutable source with recorded provenance or a deterministic generated artifact. Generated files are rebuilt by `tools/build_all.py`; do not edit them by hand.

## Mona Lisa — public-domain artwork

`mona-lisa-c2rmf-public-domain.jpg` is the source image for the photographic sequential-colormap specimen.

- Work: *Mona Lisa* by Leonardo da Vinci
- Digital source: C2RMF retouched image, via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Mona_Lisa,_by_Leonardo_da_Vinci,_from_C2RMF_retouched.jpg)
- Commons rights metadata: public domain; attribution not required
- Source SHA-256: `5f223c31ba0a477eb7cbe5e5f959d822cbfc46081b19b96498cbd5601d9ac81d`

The four `mona-lisa-<palette>.png` files resize the source to 640 pixels wide, map pixels by Oklab perceptual lightness, stretch the 1st–99th percentile range, and map it into each family's 256-sample sequential colors. If an authored scalar ramp runs from light to dark, generation reverses that ramp for this photographic mapping so dark source pixels remain dark and light source pixels remain light.

## Mars — NASA MGS MOLA topography

`megt90n000cb.img` and `megt90n000cb.lbl` are the unmodified image product and detached PDS3 label for the 4-pixels-per-degree MOLA Mission Experiment Gridded Data Record (MEGDR).

- Instrument: Mars Orbiter Laser Altimeter (MOLA), Mars Global Surveyor
- Product: `MEGT90N000CB.IMG`, version 2.0
- Dataset: `MGS-M-MOLA-5-MEGDR-L3-V1.0`
- Grid: 1440 × 720, simple cylindrical, 0.25° per pixel
- Pixel encoding: signed 16-bit MSB-first integer
- Quantity: median topography in meters, planetary radius minus areoid radius
- Observed product range: −8,068 m to +21,134 m
- Data source: [NASA Planetary Data System Geosciences Node](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg004/)
- Direct image: [megt90n000cb.img](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg004/megt90n000cb.img)
- Direct label: [megt90n000cb.lbl](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg004/megt90n000cb.lbl)
- Image SHA-256: `25f16fb7aaf857898dcf98bc4f841341a24f8b9f7e98453ca083bc45d897ca2c`
- Label SHA-256: `5a3fe60256afa1c35fea5d551fe0ab0a9198fb2bcd2c2e161d078aa69627ebac`
- NASA reuse guidance: NASA-led mission data are generally CC0 unless marked with a restriction; NASA should be acknowledged. See [NASA Data Use and Citation Guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance).

The four `mars-topography-<palette>.png` files preserve the complete 1440 × 720 grid and map measured elevation into each family's authored low-to-high 256-sample scalar ramp. To prevent Olympus Mons from compressing most terrain into a narrow visual band, the web rendering clips only the color scale—not the source data—at the 1st and 99th percentiles: −5,887 m and +6,013 m. Values outside that display window use the endpoint colors. The site labels both the display window and full source range.

Preferred dataset citation:

> Smith, D., G. Neumann, R. E. Arvidson, E. A. Guinness, and S. Slavney, “Mars Global Surveyor Laser Altimeter Mission Experiment Gridded Data Record,” NASA Planetary Data System, MGS-M-MOLA-5-MEGDR-L3-V1.0, 2003.

## Regenerate

```sh
uv run --extra dev python tools/build_all.py
```
