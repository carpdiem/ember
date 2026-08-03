# Contributing

1. Create or adjust palette definitions through the generator; do not hand-edit generated exports.
2. Run `uv run --extra dev pytest` and `uv run --extra dev python tools/build_all.py --check`.
3. Include before/after warm-transform evidence for palette changes.
4. Keep claims tied to the explicit transform profiles in the repository.
