# AU-02: kubectl/helm Subprocess Security Audit

**Audit ID:** AU-02  
**Date:** 2026-05-06  
**Status:** Complete  
**Scope:** Production Kubernetes command execution and subprocess safety  

---

## Scope

This audit examines all subprocess execution paths in the k9b codebase that invoke kubectl, helm, or external tools. The goal is to identify security gaps in:

- Command injection risks
- Unsafe shell usage
- Unbounded arguments
- Kube-context leakage
- Write-capable commands
- Missing timeouts
- Missing operator-approval boundaries
- Secret leakage in logs/artifacts

---

## Methodology

1. **Search patterns used:**
   - `subprocess.run`, `subprocess.Popen`, `asyncio.create_subprocess_exec`
   - `os.system`, `os.popen` (none found)
   - `shell=True` (none found in production paths)
   - `shlex` usage
   - `kubectl`, `helm` command construction

2. **Classification criteria:**
   - **Layer:** production, dev-only, test-only, CI-only
   - **Tool type:** kubectl, helm, filesystem/helper, Python/module runner
   - **Capability:** read-only, mutation-capable, unknown
   - **Trigger:** direct operator, background collection, LLM/proposal-derived, test fixture
   - **Argument source:** static, operator-configured, LLM-derived, user-input

3. **Security checks applied:**
   - shell=True usage (critical risk)
   - LLM/user input influence on args (injection risk)
   - Argument validation/allowlisting
   - Namespace/context argument validation
   - Timeout presence
   - stdout/stderr sanitization
   - Mutation-capable command gate
   - Operator approval requirement

---

## Command Inventory

### Production kubectl/helm Paths

| # | File | Function | Tool | Command Style | Timeout | Mutation? |
|---|------|----------|------|---------------|---------|-----------|
| 1 | `collect/live_snapshot.py` | `_run_command()` | kubectl, helm | list argv | **NONE** | Read-only |
| 2 | `identity/cluster.py` | `derive_cluster_uid()` | kubectl | list argv | 10s | Read-only |
| 3 | `external_analysis/adapter.py` | `_run_subprocess()` | k8sgpt, llamacpp | list argv | **NONE** | External tool |
| 4 | `external_analysis/alertmanager_discovery.py` | `CRDDiscoveryStrategy.discover()` | kubectl | list argv | 30s | Read-only |
| 5 | `external_analysis/alertmanager_discovery.py` | `PrometheusCRDConfigDiscoveryStrategy.discover()` | kubectl | list argv | 30s | Read-only |
| 6 | `external_analysis/alertmanager_discovery.py` | `ServiceHeuristicDiscoveryStrategy.discover()` | kubectl | list argv | 30s | Read-only |
| 7 | `external_analysis/manual_next_check.py` | `_default_runner()` | kubectl | list argv | 45s | Read-only (validated) |
| 8 | `health/image_pull_secret.py` | `_run_command()` | kubectl | list argv | **NONE** | Read-only |
| 9 | `health/drilldown.py` | `_run_command()` | kubectl | list argv | **NONE** | Read-only |
| 10 | `health/loop_alertmanager_port_forward.py` | `start_alertmanager_port_forward()` | kubectl (Popen) | list argv | **NONE** (Popen) | Read-only |
| 11 | `health/loop_scheduler.py` | `_maybe_build_diagnostic_pack()` | Python scripts | list argv | **NONE** | Build scripts |
| 12 | `ui/server.py` | `_refresh_latest_mirror()` | Python build | list argv | 120s | Build scripts |
| 13 | `external_analysis/k8sgpt_adapter.py` | `run()` | k8sgpt binary | list argv | **NONE** | External tool |
| 14 | `external_analysis/llamacpp_adapter.py` | `run()` | llamacpp binary | list argv | **NONE** | External tool |

### Test/CI-only Paths (excluded from production risk assessment)

| File | Function | Notes |
|------|----------|-------|
| `tests/test_parallel_failure.py` | Test fixtures | Test subprocess coordination |
| `tests/test_scripts.py` | verify_all.sh runners | CI verification |
| `tests/test_external_analysis.py` | Mock runners | Test monkeypatching |
| `tests/unit/test_manual_next_check.py` | Mock runners | Test subprocess mocks |
| `tests/unit/test_make_targeted_digest.py` | git operations | Test git fixture |
| `tests/unit/test_external_analysis_adapter.py` | Mock runners | Test subprocess mocking |
| `tests/unit/test_batch_next_checks.py` | Mock runners | Test command runners |

### Scripts (CLI helpers, not API-bound)

| File | Function | Notes |
|------|----------|-------|
| `scripts/run_health_scheduler.py` | subprocess.run for health loop | CLI entry point |
| `scripts/debug_runs_state.py` | subprocess.run for debug | Dev script |
| `scripts/review_latest_health.py` | subprocess.run for review | Dev script |

---

## Trust Boundaries

### Tier 1: Operator-Controlled Static Commands (Lowest Risk)
- `identity/cluster.py` - Static kubectl commands, context from config
- `external_analysis/alertmanager_discovery.py` - Static discovery commands

### Tier 2: Operator-Configured but External Tools (Medium Risk)
- `external_analysis/adapter.py` - Configured command, external tool execution
- `external_analysis/k8sgpt_adapter.py` - Command from config
- `external_analysis/llamacpp_adapter.py` - Command from config

### Tier 3: LLM-Derived kubectl Execution (Higher Risk)
- `external_analysis/manual_next_check.py` - LLM output parsed and executed
- `health/drilldown.py` - Template-based but context from evidence

### Tier 4: Background Collection (Operational Risk)
- `collect/live_snapshot.py` - No timeout, unbounded collection
- `health/image_pull_secret.py` - No timeout
- `health/loop_alertmanager_port_forward.py` - Popen without timeout

---

## Input-Source Analysis

| Path | Input Source | Influence on Args | Validation |
|------|-------------|-------------------|------------|
| `collect/live_snapshot.py` | config, cluster context | None - static args | N/A |
| `identity/cluster.py` | kube context from config | `--context` flag | Validated by kubectl |
| `external_analysis/adapter.py` | config command tuple | Full command from config | None |
| `alertmanager_discovery.py` | context parameter | `--context` flag | None explicit |
| `manual_next_check.py` | **LLM-derived description** | Parsed via shlex, validated | Family allowlist, mutation keywords |
| `image_pull_secret.py` | context, namespaces | `--context`, `-n` | None explicit |
| `drilldown.py` | context, patterns | `--context`, resource args | Template-based |
| `loop_alertmanager_port_forward.py` | namespace, context | `--context`, `-n` | None explicit |
| `loop_scheduler.py` | run_id from config | Script path and args | None |
| `ui/server.py` | Static paths | Script path | None |
| `k8sgpt_adapter.py` | config command | Full command from config | None |
| `llamacpp_adapter.py` | config command | Full command from config | None |

---

## Read-Only vs Mutation-Capable Classification

### Read-Only Commands (Safe by Default)
- All kubectl commands in `collect/`, `identity/`, `health/drilldown.py`
- kubectl discovery commands in `alertmanager_discovery.py`
- kubectl port-forward (network access, not mutation)

### Mutation-Capable Commands (Require Approval Gate)
**None found in current production paths.**

The `next_check_planner.py` module explicitly detects mutation keywords (`apply`, `delete`, `patch`, `scale`, `replace`, `create`, `edit`, `label`, `annotate`, `rollout`, `cordon`, `uncordon`, `drain`, `exec`, `set`, `upgrade`) but the actual mutation would only occur if:
1. An LLM suggests a mutation command
2. That command passes through `manual_next_check.py` validation

Currently `manual_next_check.py` explicitly blocks mutation keywords via `_DANGEROUS_CHARS` and `MUTATION_KEYWORDS`.

---

## Shell-Injection Analysis

### Findings: No Direct shell=True Usage

**Positive finding:** No production paths use `shell=True` in subprocess calls. All commands use list-argv form.

### shlex Usage in LLM Path

`manual_next_check.py` uses `shlex.split()` to parse LLM-derived command descriptions:

```python
tokens = shlex.split(description)
```

**Risk assessment:** Medium. shlex can still interpret some shell metacharacters (quotes, backslash escapes) but is safer than raw shell strings. Combined with `_DANGEROUS_CHARS` blocking (`;`, `&&`, `||`, `|`, `<`, `>`, `$`, `` ` ``), this provides defense-in-depth.

### Potential Injection Vectors

| Vector | Status | Notes |
|--------|--------|-------|
| shlex metacharacters | Mitigated | `_DANGEROUS_CHARS` blocks critical chars |
| Namespace injection | **Unknown** | No validation that namespace names are well-formed |
| Context injection | **Unknown** | No validation that context names are well-formed |
| Resource name injection | Low risk | Template-based, limited free-form input |

---

## LLM/Proposal-to-Command Boundary Analysis

### Manual Next Check Execution Path

```
LLM output → next_check_planner.py → NextCheckCandidate.description
    → manual_next_check.py._build_command() → shlex.split()
    → _validate_command_tokens() → mutation keyword check
    → _default_runner() → subprocess.run()
```

**Security controls:**
1. **Command family allowlist:** Only `kubectl-get`, `kubectl-describe`, `kubectl-logs`, `kubectl-get-crd`, `kubectl-top`
2. **Mutation keyword blocklist:** 17 patterns blocked (`apply`, `delete`, etc.)
3. **Dangerous character blocklist:** 8 characters blocked (`;`, `&&`, etc.)
4. **safeToAutomate gate:** Candidate must have `safeToAutomate=true`
5. **Approval gate:** Candidate must have `approvalStatus="approved"` if `requiresOperatorApproval=true`
6. **Output truncation:** 8KB limit on stdout/stderr captured

**Gaps identified:**
- Namespace names in LLM suggestions are not validated for well-formedness
- Context names in LLM suggestions are not validated for well-formedness
- shlex parsing could interpret quotes/escapes unexpectedly

---

## Timeout/Resource-Control Analysis

### Paths WITH Timeouts

| Path | Timeout | Notes |
|------|---------|-------|
| `identity/cluster.py` | 10s | kubectl get namespace |
| `alertmanager_discovery.py` | 30s | All discovery strategies |
| `manual_next_check.py` | 45s | kubectl execution |
| `ui/server.py` | 120s | Diagnostic pack build |
| `alertmanager_port_forward.py` | None on Popen, 5s on port ready check | Popen itself unterminated |

### Paths WITHOUT Timeouts (Risk)

| Path | Risk | Notes |
|------|------|-------|
| `collect/live_snapshot.py` | **HIGH** | No timeout on kubectl/helm commands |
| `external_analysis/adapter.py` | **HIGH** | No timeout on external tool execution |
| `health/image_pull_secret.py` | **HIGH** | No timeout on kubectl inspection |
| `health/drilldown.py` | **HIGH** | No timeout on drilldown commands |
| `health/loop_scheduler.py` | **HIGH** | No timeout on script execution |
| `k8sgpt_adapter.py` | **HIGH** | No timeout on k8sgpt execution |
| `llamacpp_adapter.py` | **HIGH** | No timeout on llamacpp execution (if subprocess path used) |
| `loop_alertmanager_port_forward.py` | **MEDIUM** | Popen without timeout, port-ready has 5s |

---

## Output Sanitization/Redaction Analysis

### Existing Controls

**`security/subprocess_helpers.py`:**
- `_safe_command_summary()`: Redacts secrets from command args before logging
- `_stderr_tail()`: Limits stderr capture to 4000 chars
- `_log_subprocess_failure()`: Safe metadata logging, no raw secrets

**Secret patterns redacted:**
- `--token`, `--bearer`, `--password`, `--secret`, `--credentials`, `--kubeconfig`, `--auth`

### Coverage Gaps

| Path | Sanitization | Notes |
|------|--------------|-------|
| `collect/live_snapshot.py` | **Unknown** | stderr captured in error messages |
| `external_analysis/adapter.py` | **Unknown** | stderr in exception messages |
| `alertmanager_discovery.py` | **Partial** | Uses `_logger.warning` with 200-char limit |
| `manual_next_check.py` | **Good** | Output truncated to 8192 bytes, combined stdout/stderr |
| `image_pull_secret.py` | **Unknown** | Error messages may contain kubectl output |
| `drilldown.py` | **Partial** | Uses `shorten()` for pod descriptions, not general stderr |
| `loop_alertmanager_port_forward.py` | **Good** | Uses `_log_subprocess_failure()` |
| `loop_scheduler.py` | **None** | Logs severity_reason which may include subprocess errors |

---

## Current Controls Summary

### Strengths

1. **No shell=True usage** - All subprocess calls use list-argv form
2. **Mutation detection** - `next_check_planner.py` blocks 17 mutation keywords
3. **Command family allowlist** - Only 5 kubectl command families allowed
4. **Output truncation** - Manual next check limits output to 8KB
5. **Secret redaction helpers** - `_safe_command_summary()` available
6. **Timeout on discovery** - 30s timeout on kubectl discovery calls
7. **Approval gating** - `requiresOperatorApproval` field respected

### Weaknesses

1. **Multiple paths lack timeouts** - 7 production paths have no timeout
2. **Namespace/context not validated** - No well-formedness checks
3. **LLM args not allowlisted** - Only family/mutation checks, not full arg allowlist
4. **Inconsistent sanitization** - Some paths log raw kubectl stderr
5. **External adapters unvalidated** - k8sgpt/llamacpp command args unchecked
6. **Port-forward Popen unbounded** - kubectl port-forward process has no timeout

---

## Gaps

### Gap 1: Missing Timeouts (SUBPROC-05)
**Severity:** High  
**Affected paths:** 8 production paths lack timeouts (now 7 mitigated by REM-S1 + REM-S1b)

**Status (as of REM-S1b):** Mitigated for 7 run-based paths. Port-forward Popen remains open as REM-S5.

**Mitigated paths (REM-S1):**
- `collect/live_snapshot.py` - 60s timeout added to `_run_command()`
- `external_analysis/adapter.py` - 120s timeout added to `_run_subprocess()`
- `external_analysis/k8sgpt_adapter.py` - inherits timeout via `_run_subprocess()`
- `external_analysis/llamacpp_adapter.py` - inherits timeout via `_run_subprocess()` when subprocess mode used

**Mitigated paths (REM-S1b):**
- `health/image_pull_secret.py` - 60s timeout (KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS) added to `_run_command()`
- `health/drilldown.py` - 60s timeout (KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS) added to `_run_command()`
- `health/loop_scheduler.py` - 120s timeout (DIAGNOSTIC_PACK_TIMEOUT_SECONDS) added to `_maybe_build_diagnostic_pack()`

**Mitigated path (REM-S5 - COMPLETED):**
- `health/loop_alertmanager_port_forward.py` - Popen lifecycle bounded:
  - `stop_alertmanager_port_forward()`: terminate-first, kill-after-grace (2s) pattern
  - Cleanup on readiness failure via `kill()` before error raising
  - All cleanup exceptions caught and logged (not raised)
  - Focus tests in `tests/unit/test_loop_alertmanager_port_forward.py`

### Gap 2: Namespace/Context Not Validated (SUBPROC-04)
**Severity:** Medium  
**Affected paths:** All kubectl execution paths

**Status (as of REM-S4):** Partially Mitigated.

**Mitigation (REM-S4):**
Added validation helpers in `security/path_validation.py`:
- `validate_kube_context_name()` - validates context names against shell metacharacters, path traversal, and length bounds
- `validate_kubernetes_namespace()` - validates namespace names against Kubernetes DNS label conventions
- `validate_kubernetes_resource_name()` - validates resource names against Kubernetes DNS name conventions

Validation integrated into:
- `health/image_pull_secret.py` - `_kubectl()`, `_kubectl_with_namespace()`, `_kubectl_with_resource()` helpers
- `health/drilldown.py` - `_kubectl()` method validates context
- `collect/live_snapshot.py` - `_kubectl()` and `_run_helm_command()` validate context
- `external_analysis/manual_next_check.py` - `_build_command()` validates context, namespace, and resource names from LLM output

**Remaining paths:**
- `identity/cluster.py` - Uses context from config, validated by kubectl itself
- `external_analysis/alertmanager_discovery.py` - Static discovery commands with context parameter; can be extended in future work

**Key validation checks applied:**
- Empty/whitespace-only rejection
- Null byte rejection
- Path traversal rejection (`..`, `/`, `\`)
- Shell metacharacter rejection (`;&|<>$`\`"'{}[]!#*?%~` and whitespace)
- Kubernetes DNS label pattern validation (namespace: lowercase alphanumerics + hyphens, max 63 chars)
- Kubernetes DNS name pattern validation (resource: lowercase alphanumerics + hyphens + dots, max 253 chars)
- Context length validation (max 500 chars)

### Gap 3: External Adapter Command Not Validated (SUBPROC-02)
**Severity:** Medium  
**Affected paths:** `k8sgpt_adapter.py`, `llamacpp_adapter.py`

**Status (as of REM-S3):** Mitigated.

**Mitigation (REM-S3):**
- `external_analysis/adapter.py` - Added `_validate_command_for_execution()` function
- Validates command is non-empty list argv
- Checks for shell metacharacters in command[0]
- Enforces allowlist: `k8sgpt`, `llamacpp`, `llama-cli`, `llama.cpp`
- Enforces blocklist: shell interpreters, scripting languages, network tools
- Called before `_run_subprocess()` execution
- Raises `ExternalAnalysisExecutionError` with safe error messages (no argv leakage)

### Gap 4: Inconsistent Sanitization (SUBPROC-06)
**Severity:** Medium  
**Affected paths:** `collect/live_snapshot.py`, `image_pull_secret.py`, `drilldown.py`

stderr output captured in error messages without sanitization. May leak sensitive information from cluster state.

### Gap 5: Port-Forward Popen Unbounded (SUBPROC-05)
**Severity:** Medium  
**Affected path:** `loop_alertmanager_port_forward.py`

**Status (as of REM-S5):** Mitigated.

The kubectl port-forward Popen process lifecycle is now bounded via `stop_alertmanager_port_forward()`.

---

## Risk Register

| ID | Risk | Severity | Likelihood | Impact | Status |
|----|------|----------|------------|--------|--------|
| SUBPROC-01 | shell=True or shell-string execution | **Critical** | Not found | N/A | Mitigated |
| SUBPROC-02 | LLM/proposal-derived args not allowlisted | **High** | Medium | LLM could suggest arbitrary kubectl args | Partially mitigated (mutation keywords) |
| SUBPROC-03 | Mutation-capable path lacks approval gate | **Low** | Low | No mutation paths in production | Mitigated by design |
| SUBPROC-04 | Namespace/context argument not validated | **Medium** | Low | Malformed names could cause issues | Gap identified |
| SUBPROC-05 | Missing timeout on subprocess | **High** | Medium | Resource exhaustion, hangs | Multiple gaps |
| SUBPROC-06 | stdout/stderr may leak secrets | **Medium** | Low | Sensitive cluster info in logs | Inconsistent coverage |
| SUBPROC-07 | Binary path/provenance not verified | **Low** | Low | Depends on PATH integrity | By design |
| SUBPROC-08 | Test/CI subprocess mixed with production | **Low** | Not found | Test helpers could affect production | Clean separation exists |

---

## Remediation Backlog

### Priority 1: Missing Timeouts (SUBPROC-05)

| Item | Description | Complexity |
|------|-------------|------------|
| R-01 | Add timeout to `collect/live_snapshot.py._run_command()` - suggest 60s | Low |
| R-02 | Add timeout to `external_analysis/adapter.py._run_subprocess()` - suggest 120s | Low |
| R-03 | Add timeout to `k8sgpt_adapter.py.run()` - suggest 120s | Low |
| R-04 | Add timeout to `llamacpp_adapter.py.run()` subprocess path - suggest 120s | Low |
| R-05 | Add timeout to `health/image_pull_secret.py._run_command()` - suggest 60s | Low |
| R-06 | Add timeout to `health/drilldown.py._run_command()` - suggest 60s | Low |
| R-07 | Add timeout to `health/loop_scheduler.py._maybe_build_diagnostic_pack()` - suggest 300s | Low |
| R-08 | Add Popen timeout to `loop_alertmanager_port_forward.py` - suggest 60s | Medium |

### Priority 2: Namespace/Context Validation (SUBPROC-04)

| Item | Description | Complexity |
|------|-------------|------------|
| R-09 | Add namespace name validation to `manual_next_check.py` | Medium |
| R-10 | Add context name validation to `manual_next_check.py` | Medium |
| R-11 | Document namespace/context validation requirements | Low |

### Priority 3: Output Sanitization (SUBPROC-06)

| Item | Description | Complexity |
|------|-------------|------------|
| R-12 | Audit stderr capture in `collect/live_snapshot.py` for secrets | Low |
| R-13 | Apply `_safe_command_summary()` to error logging in `image_pull_secret.py` | Low |
| R-14 | Apply truncation to stderr in `drilldown.py` error paths | Low |
| R-15 | Audit `loop_scheduler.py` error messages for secrets | Low |

### Priority 4: External Adapter Validation (SUBPROC-02)

| Item | Description | Complexity | Status |
|------|-------------|------------|--------|
| R-16 | Add command argument validation to `k8sgpt_adapter.py` | Medium | **Mitigated (REM-S3)** |
| R-17 | Add command argument validation to `llamacpp_adapter.py` | Medium | **Mitigated (REM-S3)** |
| R-18 | Document expected command format for external adapters | Low | **Mitigated (REM-S3)** |

---

## Verification Plan

1. **Confirm no shell=True:**
   ```bash
   grep -r "shell=True" src/k8s_diag_agent/
   ```
   Expected: No results in production code

2. **Confirm timeout coverage:**
   - Read `collect/live_snapshot.py` timeout implementation
   - Read `external_analysis/adapter.py` timeout implementation
   - Run test suite to verify behavior unchanged

3. **Confirm mutation detection:**
   ```bash
   grep -r "MUTATION_KEYWORDS" src/
   ```
   Verify all 17 keywords present

4. **Run security tests:**
   ```bash
   .venv/bin/python -m pytest tests/test_security_subprocess_helpers.py -v
   ```

---

## Open Questions

1. **What is the expected behavior if kubectl hangs for 10+ minutes in `collect/live_snapshot.py`?**
   - No timeout means unbounded wait on cluster API

2. **Should external adapter commands be validated against a schema?**
   - Currently only the binary existence is checked

3. **What is the blast radius if LLM suggests `kubectl delete pod -n kube-system`?**
   - Current mutation keyword detection should block this
   - But namespace name is not validated (could be anything)

4. **Should port-forward Popen processes be tracked and killed on health loop shutdown?**
   - Currently cleanup is best-effort (2s timeout)
   - Long-running health loops may accumulate zombie processes

5. **Is the 8KB output limit in `manual_next_check.py` sufficient for all kubectl outputs?**
   - Some kubectl outputs (events, logs) can be much larger
   - Truncation may lose diagnostic signal

---

## Files Inspected

| File | Lines | Subprocess Usage |
|------|-------|------------------|
| `src/k8s_diag_agent/collect/live_snapshot.py` | 375 | `_run_command()` |
| `src/k8s_diag_agent/identity/cluster.py` | 105 | `derive_cluster_uid()` |
| `src/k8s_diag_agent/external_analysis/adapter.py` | 104 | `_run_subprocess()` |
| `src/k8s_diag_agent/external_analysis/alertmanager_discovery.py` | 1391 | 3 discovery strategies |
| `src/k8s_diag_agent/external_analysis/manual_next_check.py` | 728 | `_default_runner()` |
| `src/k8s_diag_agent/external_analysis/k8sgpt_adapter.py` | 90 | via `_run_subprocess()` |
| `src/k8s_diag_agent/external_analysis/llamacpp_adapter.py` | 785 | via `_run_subprocess()` |
| `src/k8s_diag_agent/security/subprocess_helpers.py` | 166 | N/A (helpers only) |
| `src/k8s_diag_agent/health/image_pull_secret.py` | 388 | `_run_command()` |
| `src/k8s_diag_agent/health/drilldown.py` | 627 | `_run_command()` |
| `src/k8s_diag_agent/health/loop_alertmanager_port_forward.py` | 238 | `subprocess.Popen` |
| `src/k8s_diag_agent/health/loop_scheduler.py` | 1060 | `subprocess.run` |
| `src/k8s_diag_agent/ui/server.py` | 1851 | `subprocess.run` |
| `src/k8s_diag_agent/external_analysis/next_check_planner.py` | 1166 | N/A (validation only) |

---

## Conclusion

The codebase has a **reasonable security posture** for subprocess execution:

**Strengths:**
- No shell=True usage
- Mutation keyword detection
- Command family allowlisting
- Output truncation

**Critical gaps:**
- Multiple paths lack timeouts (8 paths)
- Namespace/context validation missing
- Inconsistent output sanitization

**Recommended immediate actions:**
1. Add timeouts to `collect/live_snapshot.py`, `adapter.py`, and adapters
2. Validate namespace/context names in `manual_next_check.py`
3. Audit stderr capture paths for secret leakage

This audit should be revisited after R-01 through R-08 (timeout additions) are implemented.
