# CSS Split Epic - Endgame Mode
## Current Task: Extract Shared UI Primitives Family

- [ ] Audit monolith for `.link` and `.text-button` complete families
- [ ] Identify all base selectors and theme variants
- [ ] Confirm family is self-contained (no hidden cross-dependencies)
- [ ] Create `frontend/src/styles/components/shared-ui.css` with full family
- [ ] Update `frontend/src/styles/index.css` import chain
- [ ] Replace moved sections in monolith with extraction markers
- [ ] Run frontend verification
- [ ] Report selector inventory, ownership model, and remaining coupling