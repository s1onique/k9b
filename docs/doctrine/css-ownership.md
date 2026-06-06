# CSS Ownership

**Guidance, not a gate.** This document prevents future agents from putting theme tokens, raw theme colors, or large theme override blocks into component CSS.

## Ownership rules

**1. Global theme tokens → `frontend/src/themes.css`**

This file is intentionally allowlisted. It owns all global theme token declarations (`--color-*`, `--bg-*`, etc.). Do not split it.

**2. Theme-specific overrides → `frontend/src/styles/themes/<theme>/`**

Larger, theme-specific override blocks belong in the theme override tree (e.g., `frontend/src/styles/themes/solarized-light/`). Each file covers one component group (inputs, cards, tables, etc.).

**3. Component CSS → use tokens, not raw colors**

Component CSS should use existing tokens and classes. Do not define new theme tokens, raw theme colors, or repeated theme-specific blocks in component files.

**4. Tiny inline overrides → local and small only**

Short inline `[data-theme="..."]` overrides are allowed in component/shared CSS when they are:
- local to that component,
- readable (few selectors, clear intent),
- cheaper than creating or moving to a theme override file.

**5. Growth rule**

If an inline override grows beyond a few selectors or repeats across components, move it into the theme override tree under `frontend/src/styles/themes/<theme>/`.

## Summary

> Theme ownership rule: global theme tokens live in `frontend/src/themes.css`; larger theme-specific overrides live under `frontend/src/styles/themes/<theme>/`. Component CSS may contain tiny local `[data-theme="..."]` overrides when that is the clearest ownership boundary, but it must not define new theme tokens, raw theme colors, or repeated theme-specific blocks. If an override grows or repeats, move it into the theme override tree.

## Non-goals

- No splitting of `themes.css`.
- No migration of existing CSS.
- No new CI gate.