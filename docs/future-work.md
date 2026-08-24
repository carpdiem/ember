# Ember future work

## 1200K redundant encoding

**Status:** deferred. The production 1200K palette ships three distinct color identities. It does not yet ship an automatic non-color style cycle.

Build a profile-specific mapping for uses that need more than color alone:

- terminal roles: weight, underline, reverse video, or glyph cues for intentional ANSI aliases;
- charts: marker, dash, hatch, and direct-label assignments after the third series;
- documentation: examples that show the mapping in commanded and simulated 1200K states;
- APIs: deterministic helpers that preserve category identity when users switch profiles.

Do not add these cues to 3400K by default. Do not claim more than three 1200K color identities. Keep color selection frozen unless a concrete implementation failure requires a targeted correction.
