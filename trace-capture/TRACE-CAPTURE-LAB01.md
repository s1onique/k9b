# ACT-K9B-TRACE-CAPTURE-LAB01: k9b Backend OpenTelemetry Trace Capture Lab

**Status**: Implementation Complete | Live Capture Pending Image Update

**Date**: 2026-07-06  
**Author**: Cline Agent  
**Branch**: feature/trace-capture-lab

---

## Objective

Implement a trace capture lab path that captures real k9b backend OpenTelemetry traces into lab artifacts for evidence-based diagnostic workflows.

## Deliverables

### Implemented Files

| File | Purpose |
|------|---------|
| `trace-capture/collector-config.yaml` | OTel Collector configuration with OTLP receiver |
| `trace-capture/trace_summary.py` | Trace summary generator with privacy validation |
| `trace-capture/trace_capture_api.py` | API exerciser for representative endpoints |
| `trace-capture/verify_trace_capture.py` | Artifact verifier |
| `trace-capture/run_trace_capture.py` | Main orchestrator script |
| `tests/unit/test_trace_capture_summary.py` | 44 unit tests (all passing) |

### Verification Results

```
✅ ruff-lint: PASS
✅ mypy: PASS  
✅ unit-tests: 44/44 passed
✅ Trace summary schema: k9b.trace_capture.v1
```

## Live Capture Attempt (2026-07-05 21:30-21:36 UTC)

### Infrastructure Deployed

| Component | Status | Details |
|-----------|--------|---------|
| OTel Collector (k8s) | ✅ Running | `otel-collector` pod in k9b namespace |
| OTel Collector (podman) | ✅ Running | Container on localhost:4317 |
| k9b-backend | ✅ Running | `k9b-backend-6c99ff5d76-s8tdm` |
| Port-forward | ✅ Established | localhost:8080 → k9b-backend |
| OTel env vars | ✅ Configured | K9B_OTEL_ENABLED=true, endpoint=otel-collector |

### API Exercise Results

```
✓ GET /api/health/details -> 200
✓ GET /api/incidents -> 200
✗ GET /api/incidents/{incident_id} -> None (no incidents in DB)
✗ POST .../handoff -> None (requires incident_id)
```

### Gap Identified

**Issue**: The running k9b-backend image (`otel-live-28713167640-1-ca39769a543bb8fa264f0569472e7ee8143c73e5`) does NOT include the `observability` module.

Evidence:
```bash
$ kubectl exec k9b-backend-6c99ff5d76-s8tdm -- ls /app/src/k8s_diag_agent/
# No observability/ folder present
```

The OTel instrumentation code exists in this repository's `src/k8s_diag_agent/observability/` but was added after the running image was built.

### Artifact Generated

```json
{
  "schema_version": "k9b.trace_capture.v1",
  "generated_at": "2026-07-05T21:36:32.604863+00:00",
  "otel_enabled": true,
  "service_name": "k9b-backend",
  "collector_received_traces": false,
  "trace_count": 0,
  "span_count": 0,
  "http_span_count": 0,
  "internal_span_count": 0,
  "trace_ids": [],
  "normalized_route_names_present": false,
  "http_and_internal_spans_share_trace_id": false,
  "raw_incident_ids_in_span_names": false,
  "raw_artifact_payload_detected": false
}
```

---

## Next Steps for Real Trace Capture

### Option 1: Build and Deploy New Image (Recommended)

```bash
# 1. Build new image with observability module
make docker-build TAG=trace-lab-$(date +%Y%m%d%H%M%S)

# 2. Push to registry
make docker-push TAG=trace-lab-$(date +%Y%m%d%H%M%S)

# 3. Update k9b-backend deployment
kubectl set image deployment/k9b-backend \
  k9b-backend=<registry>/k9b-backend:trace-lab-YYYYMMDDHHMMSS \
  -n k9b

# 4. Verify observability module present
kubectl exec -n k9b <pod-name> -- ls /app/src/k8s_diag_agent/observability/

# 5. Run trace capture
.venv/bin/python trace-capture/run_trace_capture.py \
  --artifact-dir trace-capture \
  --backend-url http://localhost:8080

# 6. Verify traces captured
cat trace-capture/trace-summary.json | jq '.trace_count'
```

### Option 2: Use Local Dev Environment

```bash
# Start k9b-backend locally with OTel enabled
K9B_OTEL_ENABLED=true \
K9B_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
.venv/bin/python -m k8s_diag_agent.ui

# In another terminal, run trace capture
.venv/bin/python trace-capture/run_trace_capture.py
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Trace Capture Flow                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────┐ │
│  │ k9b-backend  │────▶│  OTel        │────▶│  Artifact  │ │
│  │ (with OTel   │     │  Collector   │     │  Writer    │ │
│  │  enabled)    │     │  (k8s/podman)│     │            │ │
│  └──────────────┘     └──────────────┘     └────────────┘ │
│         │                     │                    │         │
│         │                     │                    ▼         │
│         │                     │            ┌────────────┐     │
│         │                     │            │ trace-     │     │
│         │                     │            │ summary.json    │
│         │                     │            └────────────┘     │
│         │                     │                    │         │
│         │                     ▼                    ▼         │
│         │              ┌────────────┐     ┌────────────┐   │
│         └─────────────▶│  API       │     │ verify_    │   │
│                        │  Exerciser │     │ trace_     │   │
│                        │            │     │ capture.py │   │
│                        └────────────┘     └────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Trace Summary Schema (k9b.trace_capture.v1)

```python
@dataclass(frozen=True)
class TraceSummary:
    schema_version: str                    # "k9b.trace_capture.v1"
    generated_at: str                      # ISO 8601 timestamp
    otel_enabled: bool                    # K9B_OTEL_ENABLED
    service_name: str                      # K9B_OTEL_SERVICE_NAME
    
    # Evidence of real traces
    collector_received_traces: bool         # Collector saw OTLP data
    trace_count: int                       # > 0 for success
    span_count: int                        # Total spans
    http_span_count: int                   # HTTP server spans
    internal_span_count: int               # Internal processing spans
    
    # Trace quality
    trace_ids: tuple[str, ...]             # Extracted trace IDs
    normalized_route_names_present: bool    # Routes properly normalized
    http_and_internal_spans_share_trace_id: bool  # Cross-domain traces
    
    # Privacy safety
    raw_incident_ids_in_span_names: bool    # PII risk
    raw_artifact_payload_detected: bool     # Sensitive data leak
```

---

## Privacy Safety Rules

1. **No raw incident IDs in span names** - Must use normalized routes like `/api/incidents/{id}` → `/api/incidents/{incident_id}`
2. **No artifact payloads in traces** - Raw incident/pod data must not appear in span attributes
3. **Bounded trace evidence** - Only trace IDs, span counts, and route names are extracted

---

## Exit Criteria (Not Yet Met)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| collector_received_traces=true | ❌ | 0 traces received |
| trace_count > 0 | ❌ | 0 |
| http_span_count > 0 | ❌ | 0 |
| internal_span_count > 0 | ❌ | 0 |
| Shared trace IDs | ❌ | N/A |
| Normalized routes | ❌ | No spans |

**Root Cause**: k9b-backend image lacks `observability` module.

---

## Files Modified/Created

```
trace-capture/
├── collector-config.yaml          # New: OTel Collector config
├── trace_summary.py               # New: Trace summary generator
├── trace_capture_api.py          # New: API exerciser
├── verify_trace_capture.py        # New: Artifact verifier
├── run_trace_capture.py           # New: Main orchestrator
└── backend-api-traces.json        # Generated: API exercise results

tests/unit/
└── test_trace_capture_summary.py # New: 44 unit tests

trace-capture/trace-summary.json   # Generated: Empty (no traces yet)
```

---

## Conclusion

The **scaffold is complete and verified** (44 tests pass, ruff/mypy clean), but **real trace capture requires** a k9b-backend image built from the current source code that includes the `observability` module.

**Next action**: Build and deploy new k9b-backend image, then re-run trace capture.
