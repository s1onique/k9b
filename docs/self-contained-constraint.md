# Self-Contained k9b-Only Constraint

**Status**: Active constraint for incident investigation workflow  
**Last Updated**: 2026-06-16

---

## Constraint Statement

The complete incident investigation workflow must run inside k9b itself:

- **NOT REQUIRED:**
  - Cline or any external CLI tool
  - Manual kubectl commands
  - Operator shell access or pod exec
  - Local CLI required
  - Copy/paste to external tools
  - External artifact massaging required

- **REQUIRED:**
  - k9b backend for evidence capture
  - k9b UI for review packet generation
  - k9b reviewer pipeline for analysis

---

## Rationale

The "LLM packet for Cline" is only an intermediate scaffold, not final product behavior. External tools may be used during development, but the shipped operator workflow must be:

**UI → k9b backend → k9b evidence capture → k9b review/analysis → k9b incident report**

---

## Current Implementation Status

### Completed (This ACT)

- [x] Incident review packet generator (`incident_review_packet.py`)
- [x] API endpoint for packet generation (`/api/incidents/review-packet`)
- [x] Frontend API function (`generateIncidentReviewPacket`)
- [x] Unit tests for packet generator
- [x] Module docstring with self-contained constraint
- [x] UI "Generate review packet" button after successful bundle capture
- [x] UI "Copy review packet" and "Download review packet.md" buttons after packet generation
- [x] Error field in API response contract
- [x] Narrow exception handling (no broad `except Exception`)

### Deferred (Follow-up ACT)

- [ ] Replace kubectl subprocess collector with in-process Kubernetes API

---

## Temporary Scaffolding Notes

The current collector (`incident_collectors.py`) shells out to `kubectl` via subprocess. This is acceptable only as temporary scaffolding until replaced with in-process Kubernetes API access.

**Required for next ACT**: Replace `kubectl` subprocess calls with Kubernetes client library calls using the existing k9b Kubernetes access/client abstraction.

---

## Review Packet Contents

The generated review packet includes:
- Metadata (bundle ID, namespace, context)
- Evidence summary (pods, deployments, events, symptoms)
- Detected symptoms with severity classification
- Failing pods table
- Deployment health status
- Warning events
- Collection errors
- Known limitations
- Self-contained k9b-only constraint statement
- Reviewer constraints
- Questions for next evidence collection
- Raw evidence index

---

## Reviewer Constraints

CRITICAL constraints when reviewing packets:

1. **Evidence is NOT root cause** - Do NOT treat evidence as proven root cause
2. **Pod logs are NOT included** - Use k9b drilldown for log capture
3. **Separate facts, hypotheses, and unknowns**
4. **Do NOT invent missing evidence**
5. **Ask for next evidence before proposing fixes**
6. **No autonomous diagnosis** - All remediation requires operator confirmation

---

## Files Changed

| File | Change |
|------|--------|
| `src/k8s_diag_agent/collect/incident_review_packet.py` | New - Packet generator |
| `src/k8s_diag_agent/collect/api_incident_review_packet.py` | New - API handler |
| `src/k8s_diag_agent/ui/server_review_packet.py` | New - HTTP handler |
| `src/k8s_diag_agent/ui/server_routes.py` | Modified - Route dispatch |
| `src/k8s_diag_agent/collect/incident_snapshot.py` | Modified - Docstring update |
| `frontend/src/api.ts` | Modified - API client function |
| `tests/unit/test_incident_review_packet.py` | New - Unit tests |
| `tests/unit/test_api_incident_review_packet.py` | New - API tests |

---

## Verification

```bash
# Run packet-specific tests
.venv/bin/python -m pytest tests/unit/test_incident_review_packet.py tests/unit/test_api_incident_review_packet.py -v

# Run full gate
scripts/verify_all.sh --python-only
```

**Expected result**: All 35 packet tests pass, full gate passes
