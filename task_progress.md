# Task Progress: Alertmanager Sources UX and Deduplication

## Analysis Complete ✓

### Current State:
- Frontend: `AlertmanagerSourcesPanel` at line 1957 in App.tsx
- Backend: `Alertmanager_discovery.py` handles source discovery with 3 strategies
- Each strategy generates strategy-specific `source_id` (e.g., `crd:monitoring/alertmanager-main`)
- Current `identity_key` equals `source_id`, causing duplicates when same AM discovered via multiple strategies

### Canonical Deduplication Rule:
Use normalized endpoint as canonical identity (not source_id which is strategy-specific):
- Normalize by stripping scheme, port, and trailing slashes
- Preserve namespace/name for display
- Merge provenance from all contributing origins
- Manual sources remain authoritative

---

## Implementation Checklist

### Backend: Deduplication and Provenance Merging
- [ ] 1. Add canonical identity to `AlertmanagerSource` (normalized endpoint)
- [ ] 2. Add `merged_provenances` field to track all contributing origins
- [ ] 3. Implement `merge_deduplicate_inventory()` function in alertmanager_discovery.py
- [ ] 4. Update `AlertmanagerSourceInventory` to use new canonical identity
- [ ] 5. Ensure manual sources are preserved (not deduplicated away)

### Backend: Serialization for UI
- [ ] 6. Update `_serialize_alertmanager_sources()` in health/ui.py to include merged provenance
- [ ] 7. Update UI API payload to expose merged origins field

### Frontend: UX Enhancements
- [ ] 8. Add title tooltip to endpoint cell showing full URL
- [ ] 9. Add click-to-copy for endpoint cell
- [ ] 10. Update provenance column to show merged origins (e.g., "CRD, Prometheus Config, Service")
- [ ] 11. Add CSS for copy button/tooltip

### Frontend: Type Updates
- [ ] 12. Add `merged_provenances` field to `AlertmanagerSource` type
- [ ] 13. Update `makeAlertmanagerSource` fixture

### Tests
- [ ] 14. Test backend: deduplication merges CRD + Prometheus + service discoveries
- [ ] 15. Test backend: manual precedence preserved after deduplication
- [ ] 16. Test frontend: endpoint tooltip shows full value
- [ ] 17. Test frontend: click-to-copy copies full endpoint
- [ ] 18. Test frontend: merged provenance rendering
- [ ] 19. Run `scripts/verify_all.sh` for verification gate

### Documentation
- [ ] 20. Update memory bank with deduplication behavior

---

# Task Progress: CSS Monolith Phase 9B Extraction ✓ COMPLETE

## Overview
Phase 9B of CSS monolith extraction: structural family audit for workflow lanes, panel shells, and related structural wrappers.

## Completed Work

### Workflow Lane Headers Extraction ✓
- **File Created**: `frontend/src/styles/layout/workflow-lanes.css`
- **Selectors Extracted**: 6 (.workflow-lane-header, + sibling, .workflow-lane-label, .workflow-lane-icon, .workflow-lane-title, .workflow-lane-description)
- **Model**: A (pure structural, CSS custom properties only)
- **Boundary**: Clean - isolated to workflow lane header regions
- **Verification**: Frontend build SUCCESS (66 modules, 468ms)

### Deferred Candidates (Per Task Constraints)

#### `.panel` Family - DEFERRED
**Reason**: Semantic ambiguity - unclear if panel is structural shell or semantic component
- Contains theme override coupling (var(--color-panel-*))
- Per task constraint: "No panel-heavy extraction"
- **Recommendation**: Defer until semantic boundary is clarified; may warrant component Model B extraction

#### `.recent-runs` / `.runs-table-*` Family - DEFERRED  
**Reason**: Per task explicit directive
- Task stated: "do not force `runs-table` extraction"
- High coupling to table structure, filtering state, and action handlers
- Adjacent selector coupling (.recent-runs-list, .recent-runs-item, .recent-runs-label, .recent-runs-time)
- **Recommendation**: Retain in monolith until table structure is componentized

#### `.runs-table-wrapper` - DEFERRED
**Reason**: Table infrastructure, not standalone structural family
- Couples to table semantics and scroll behavior
- **Recommendation**: Keep in monolith; extract when table component is isolated

## Extraction Audit Summary

| Family | Status | Reason |
|--------|--------|--------|
| `.workflow-lane-*` | ✅ Extracted | Clean boundary, pure structural, all CSS tokens |
| `.panel` | ❌ Deferred | Semantic ambiguity + theme override coupling |
| `.recent-runs-*` | ❌ Deferred | Per task directive |
| `.runs-table-*` | ❌ Deferred | Per task directive |

## Cascade Preservation
All extracted styles use CSS custom properties only - no hardcoded values, ensuring theme overrides propagate correctly.

## Files Modified
- `frontend/src/styles/layout/workflow-lanes.css` (created)
- `frontend/src/styles/index.css` (import added)
- `frontend/src/index.css` (extraction comment added)

## Verification
- Frontend build: ✅ SUCCESS
- Backend tests: ⚠️ 1333 tests, 1 pre-existing failure, 12 pre-existing errors (OSError: directory cleanup) - unrelated to CSS changes
