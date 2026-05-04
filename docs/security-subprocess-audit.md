# Security Subprocess Audit

**Date**: 2026-04-05  
**Phase**: Phase 2 - subprocess stderr capture  
**Scope**: `src/k8s_diag_agent/`

## Audit Summary

Goal: Stop discarding diagnostic subprocess stderr in cluster/port-forward paths, preserve operational forensics while avoiding secret leakage.

## Subprocess Usages Found

| File | Pattern | stderr Handling | Status |
|------|---------|------------------|--------|
| `health/loop.py` | `subprocess.Popen` | `stderr=subprocess.PIPE` ✅ | **FIXED** |
| `health/loop_alertmanager_snapshot.py` | `subprocess.Popen` (reference) | N/A (callback only) | reviewed-safe |
| `external_analysis/adapter.py` | `subprocess.run(capture_output=True)` | captured ✅ | reviewed-safe |
| `external_analysis/alertmanager_discovery.py` | `subprocess.run(capture_output=True)` | captured ✅ | reviewed-safe |
| `external_analysis/manual_next_check.py` | `subprocess.run(capture_output=True)` | captured ✅ | reviewed-safe |
| `collect/live_snapshot.py` | `subprocess.run(capture_output=True)` | captured ✅ | reviewed-safe |
| `health/drilldown.py` | `subprocess.run(capture_output=True)` | captured ✅ | reviewed-safe |

## DEVNULL Usage

| File | Line | Usage | Classification |
|------|------|-------|----------------|
| `health/loop.py` | 3451 | `stdout=subprocess.DEVNULL` | **FIXED** - stdout only, not stderr |

**Finding**: Only one DEVNULL usage remains, and it discards stdout (not stderr), which is acceptable for port-forward where we don't need port output.

## Changes Made

### `src/k8s_diag_agent/security/subprocess_helpers.py` (CREATED)

New module providing security-conscious subprocess utilities:

- `_stderr_tail()`: Bounded stderr extraction to prevent log bloat
- `_safe_command_summary()`: Command summary with secret-bearing arguments redacted
- `_log_subprocess_failure()`: Structured failure logging with safe metadata

**Status**: ✅ USED - wired into health/loop.py port-forward failure path

### `src/k8s_diag_agent/health/loop.py` (MODIFIED)

Changed port-forward Popen from `stderr=subprocess.DEVNULL` to `stderr=subprocess.PIPE` and wired helpers for safe logging:

```python
port_forward_process: subprocess.Popen[str] = subprocess.Popen(
    cmd,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,  # Changed from DEVNULL
    text=True,
)

if not self._wait_for_port_ready("127.0.0.1", local_port, timeout_seconds=5.0):
    # Avoid communicate-before-kill hang: kill first if still running, then collect stderr
    stderr_output = ""
    if port_forward_process.poll() is None:
        port_forward_process.kill()
        try:
            _, stderr_output = port_forward_process.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            port_forward_process.kill()
            _, stderr_output = port_forward_process.communicate()
    else:
        try:
            _, stderr_output = port_forward_process.communicate(timeout=0.1)
        except subprocess.TimeoutExpired:
            stderr_output = ""

    # Log subprocess failure with safe metadata
    _log_subprocess_failure(
        operation="port_forward",
        command_args=cmd,
        return_code=port_forward_process.returncode,
        stderr=stderr_output,
        run_id=self.run_id,
        cluster_label=self.run_label,
    )
```

## Secret Protection Measures

1. **stderr tail bounded**: Limited to 4000 characters to prevent log bloat
2. **Secret pattern redaction**: Arguments matching patterns (`--token`, `--bearer`, `--password`, `--secret`, `--credentials`, `--kubeconfig`, `--auth`) are redacted in command summaries
3. **Structured logging**: Failure logging includes metadata for forensics without leaking secrets

## Tests

Added `tests/test_security_subprocess_helpers.py` with tests for:
- `_stderr_tail()`: None handling, bytes decoding, tail bounding, binary fallback
- `_safe_command_summary()`: Secret redaction for all patterns, safe args preserved

## Verification

```bash
# Verify no DEVNULL for stderr
rg 'stderr\s*=\s*(subprocess\.)?DEVNULL' src/k8s_diag_agent/
# Expected: no matches (only stdout=DEVNULL allowed)

# Run security baseline
scripts/check_security_baseline.sh

# Run subprocess helper tests
.venv/bin/python -m pytest tests/test_security_subprocess_helpers.py -v
```

## Next Steps

- [x] Add tests for subprocess stderr capture in `tests/`
- [x] Wire _log_subprocess_failure into port-forward failure path
- [x] Fix communicate-before-kill lifecycle bug
- [ ] Run security baseline check