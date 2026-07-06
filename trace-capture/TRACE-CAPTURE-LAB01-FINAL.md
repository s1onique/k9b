# ACT-K9B-TRACE-CAPTURE-LAB01: Final Report

**Status**: Scaffold Complete | Live Capture Blocked

**Date**: 2026-07-06  
**Branch**: feature/trace-capture-lab

---

## Executive Summary

The trace-capture scaffold is **fully implemented and verified** (44 unit tests pass, ruff/mypy clean). However, **live trace capture is blocked** by an image version mismatch between the running k9b-backend and the current source code.

## Deliverables (All Complete)

| File | Status | Purpose |
|------|--------|---------|
| `trace-capture/collector-config.yaml` | ✅ | OTel Collector with OTLP receiver |
| `trace-capture/trace_summary.py` | ✅ | Trace summary generator (k9b.trace_capture.v1) |
| `trace-capture/trace_capture_api.py` | ✅ | API exerciser for /api/health/details, /api/incidents |
| `trace-capture/verify_trace_capture.py` | ✅ | Artifact verifier |
| `trace-capture/run_trace_capture.py` | ✅ | Main orchestrator |
| `tests/unit/test_trace_capture_summary.py` | ✅ | 44 unit tests (all passing) |
| `trace-capture/TRACE-CAPTURE-LAB01.md` | ✅ | Initial documentation |

## Verification Results

```
✅ ruff-lint: PASS
✅ mypy: PASS  
✅ unit-tests: 44/44 passed
✅ Trace summary schema: k9b.trace_capture.v1
```

## Infrastructure Deployed

| Component | Status | Details |
|-----------|--------|---------|
| OTel Collector (k8s pod) | ✅ Running | `10.238.5.186:4317` |
| OTel Collector Service | ✅ Created | `otel-collector-svc.k9b.svc.cluster.local:4317` |
| k9b-backend | ✅ Running | `k9b-backend-b5f4d4975-hqqlt` |
| Port-forward | ✅ Established | localhost:8080 → k9b-backend |
| OTel env vars | ✅ Configured | K9B_OTEL_ENABLED=true, endpoint=otel-collector-svc |

## Gap Analysis

### Problem

The running k9b-backend image **does NOT contain** the `observability` module:

```
$ kubectl exec k9b-backend-b5f4d4975-hqqlt -- ls /app/src/k8s_diag_agent/observability/
ls: cannot access '/app/src/k8s_diag_agent/observability/': No such file or directory
```

**Image in use**: `harbor-pve1.spbnix.local/k9b/k9b-backend:otel-live-28713167640-1-ca39769a543bb8fa264f0569472e7ee8143c73e5`

### Root Cause

1. The `observability` module was added to the repository after this image was built
2. Podman cannot build locally due to TLS certificate issues with `harbor-pve1.spbnix.local`
3. Package installation in running pod fails due to permission issues

### Evidence

```bash
# OTel env vars ARE configured correctly:
$ kubectl get deployment k9b-backend -n k9b -o jsonpath='{.spec.template.spec.containers[0].env}' | jq '.[] | select(.name | startswith("K9B_OTEL"))'
{"name":"K9B_OTEL_EXPORTER_OTLP_ENDPOINT","value":"http://otel-collector-svc.k9b.svc.cluster.local:4317"}
{"name":"K9B_OTEL_ENABLED","value":"true"}
{"name":"K9B_OTEL_SERVICE_NAME","value":"k9b-backend"}
{"name":"K9B_OTEL_SAMPLE_RATIO","value":"1.0"}

# But observability module is missing:
$ kubectl exec -n k9b k9b-backend-b5f4d4975-hqqlt -- ls /app/src/k8s_diag_agent/observability/
ls: cannot access '/app/src/k8s_diag_agent/observability/': No such file or directory
```

## API Exercise Results

```
✓ GET /api/health/details -> 200
✓ GET /api/incidents -> 200
✗ GET /api/incidents/{incident_id} -> None (no incidents in DB)
✗ POST .../handoff -> None (requires incident_id)
```

## Current trace-summary.json

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
  "trace_ids": []
}
```

## Required to Complete

### Option 1: CI/CD Image Build (Recommended)

Push code to trigger CI image build:

```bash
git add tests/unit/test_trace_capture_summary.py trace-capture/
git add .gitignore
git commit -m "feat: add trace-capture lab scaffold (ACT-K9B-TRACE-CAPTURE-LAB01)"
git push origin feature/trace-capture-lab
```

Create a PR to `main` to trigger the image build workflow.

### Option 2: Manual Build (Requires Registry Access)

```bash
# Build image with buildx (requires authenticated access to harbor)
docker buildx build -f Dockerfile.python \
  -t harbor-pve1.spbnix.local/k9b/k9b-backend:trace-lab-$(date +%Y%m%d%H%M%S) \
  --push .

# Deploy
kubectl set image deployment/k9b-backend \
  k9b-backend=harbor-pve1.spbnix.local/k9b/k9b-backend:trace-lab-YYYYMMDDHHMMSS \
  -n k9b
```

### Option 3: Local Development

Run k9b-backend locally with OTel enabled:

```bash
# Terminal 1: Start OTel Collector
podman run -d --name otel-collector -p 4317:4317 \
  docker.io/otel/opentelemetry-collector-contrib:0.110.0

# Terminal 2: Start k9b-backend
cd /Users/chistyakov/Projects/SPbNIX/k9b
K9B_OTEL_ENABLED=true \
K9B_OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
.venv/bin/python -m k8s_diag_agent.ui

# Terminal 3: Run trace capture
.venv/bin/python trace-capture/run_trace_capture.py --verbose
```

## Files Modified/Created

```
trace-capture/
├── collector-config.yaml          # New: OTel Collector config
├── trace_summary.py               # New: Trace summary generator
├── trace_capture_api.py          # New: API exerciser
├── verify_trace_capture.py        # New: Artifact verifier
├── run_trace_capture.py           # New: Main orchestrator
├── TRACE-CAPTURE-LAB01.md         # New: Initial documentation
├── TRACE-CAPTURE-LAB01-FINAL.md   # New: This report
├── backend-api-traces.json        # Generated: API exercise results
└── trace-summary.json             # Generated: Empty (no traces yet)

tests/unit/
└── test_trace_capture_summary.py  # New: 44 unit tests

.gitignore                        # Modified: Added generated artifacts
```

## Conclusion

The **trace-capture scaffold is complete and verified**, but **live capture requires** either:

1. **CI/CD**: Push code to trigger image rebuild via GitHub Actions
2. **Manual**: Build image locally with authenticated Docker access to Harbor
3. **Local**: Use local Python environment instead of k8s deployment

**Next action for user**: Push the staged code to trigger CI image build, then verify the new image contains the observability module before re-running trace capture.
