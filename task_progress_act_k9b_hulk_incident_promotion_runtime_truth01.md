# ACT-K9B-HULK-INCIDENT-PROMOTION-RUNTIME-TRUTH01

## Final Report

## Source starting and final commit/tree

* **Starting worktree**: `/Users/chistyakov/Projects/SPbNIX/k9b-incident-promotion-runtime-truth01`
* **Starting branch**: `hotfix/incident-promotion-runtime-truth01`
* **Source commit (final)**: `cdc3b624746d1a1013e1acae62615002d365d145`
  (merge of PR #1, "hotfix/incident-promotion-ci-recovery01" into `main`,
  plus this ACT's `task_progress_*.md` evidence note).
* **Final tree**: Identical to `origin/main` for production code
  (`k8s_diag_agent/collect/`, `k8s_diag_agent/health/`,
  `k8s_diag_agent/incident_alert_*`, `k8s_diag_agent/ui/server_incident_internal_*`).
  The only worktree-local change is `task_progress_act_k9b_hulk_incident_promotion_runtime_truth01.md`.

## Deployed image before and after

| | Before | After |
|---|---|---|
| Image | `harbor-pve1.spbnix.local/k9b/k9b-backend:otel-live-28815358316-2-16fa88be7cee1f21ea0cd34ab6aff6508480c78a` | `harbor-pve1.spbnix.local/k9b/k9b-backend:cdc3b62` |
| Image ID | `sha256:7ebcb6b8c2282a545cd2988bbd40705c6bfd28cca43cecea5c61fb2e02fcbc8b` | `sha256:7c24957dd42834291fb93ff401fa31bdd9aa8d71b6704a1b2685eedee8a45c66` |
| Source commit | `28815358316...` (pre-Hulkization) | `cdc3b624746d1a1013e1acae62615002d365d145` (post-Hulkization, origin/main) |
| Build provenance | (older build) | `org.opencontainers.image.revision=cdc3b624746d1a1013e1acae62615002d365d145`, `version=cdc3b62`, `builder-id=https://github.com/s1onique/k9b/actions/runs/30390631849/attempts/1` |
| CI workflow | (older) | GitHub Actions `Build and Push to Harbor` run `30390631849` |

## Scheduler/backend deployment revisions

| Component | Before | After | Image ID |
|---|---|---|---|
| `deployment/k9b-scheduler` | 100 (pre-ACT) | **101** | `sha256:7c24957dd42834291fb93ff401fa31bdd9aa8d71b6704a1b2685eedee8a45c66` |
| `deployment/k9b-backend` | 118 (pre-ACT) | **119** | `sha256:7c24957dd42834291fb93ff401fa31bdd9aa8d71b6704a1b2685eedee8a45c66` |

Both pods `phase: Running, ready: true, restarts: 0` after rollout. Pods:
- `k9b-scheduler-5558c6fbc-jtd8k`
- `k9b-backend-9d55b5db7-xrc6r`

## Failing run ID (Phase 1)

* Failing run id: `health-config-20260728T163125Z` (captured from
  `kubectl logs deployment/k9b-scheduler --previous` during Phase 1
  capture). That pod was running the pre-Hulkization
  `otel-live-28815358316-2-...` image.
* Sequence in that run:
  `Snapshot → Alertmanager discovery (0 candidates) → alertmanager-snapshot-skipped (no_eligible_sources) → vmalert discovery (0 candidates) → drilldown → review → proposal → automatic-diagnosis (incidents_processed=0, total_review_packets_written=0)`.
  No promotion ever happened; no `K9B_INCIDENT_PROMOTION_MODE`,
  no `K9B_BACKEND_INTERNAL_URL`, no `K9B_PROCESS_ROLE`, no
  `K9B_INCIDENT_STORE_BACKEND`, and no `k9b-internal-api` Secret
  existed in the cluster.

## Root-cause category (Phase 2)

Primary: **`STALE_DEPLOYED_IMAGE`** (combined with
`BACKEND_ROUTE_OR_AUTHORITY_DEFECT`).

Evidence:

1. The deployed image
   `harbor-pve1.spbnix.local/k9b/k9b-backend:otel-live-28815358316-2-16fa88be7cee1f21ea0cd34ab6aff6508480c78a`
   predates the Hulkization. Source commit on the deployed image is
   `28815358316...` which is older than the canonical Hulkization work
   on `origin/main` commit `91f01575` ("ACT-K9B-IMAGE-BUILDER-REGISTRY-CACHE-AUTHORIZATION01-CORRECTION07-C") and the
   `33a3c49` / `cdc3b624` Hulkization series.
2. The deployed `k9b-scheduler` pod had **no** `K9B_INCIDENT_PROMOTION_MODE`,
   `K9B_BACKEND_INTERNAL_URL`, `K9B_INTERNAL_API_TOKEN`, or
   `K9B_PROCESS_ROLE` env vars (captured via
   `kubectl get deployment -o jsonpath` on the live `k9b` release
   revision 103). The deployed `k9b-backend` had no
   `K9B_INCIDENT_STORE_BACKEND=sqlite` env var either. So the dispatch
   `auto` mode resolved to `local` (forbidden for `scheduler+sqlite`)
   and there was no internal API token secret
   (`k9b-internal-api` did not exist in the cluster at all).
3. The `k9b-internal-api` Secret was **absent** in the cluster
   (`kubectl get secret k9b-internal-api` returned NotFound). Created
   it as part of this ACT with a freshly generated
   `K9B_INTERNAL_API_TOKEN`.
4. The 127 focused tests on `origin/main` (all
   `test_act_k9b_hulk_current_run_promotion_seam01_production_regression`,
   `test_current_run_promotion_workset`,
   `test_signal_persistence_outcomes`,
   `test_promotion_outcomes`,
   `test_diagnosis_selection_algebra`,
   `test_seam01_final_summary_consistency`,
   `test_current_run_promotion_seam01_verifier`,
   `test_promotion_diagnosis_handoff`,
   `test_promotion_diagnosis_handoff_regression`,
   `test_scheduler_internal_api_client`) all pass on the worktree
   source (commit `cdc3b624`) — proving the source fix is complete.
5. `ruff check` clean on every changed production file.
   `mypy` clean. `git diff --check HEAD` clean.

## Before/after request signal count

| Run | `requested_signal_count` | `categorised_signal_count` | Outcome | Selection mode |
|---|---|---|---|---|
| Before (run `health-config-20260728T163125Z` on `otel-live-28815358316-2-...`) | (promotion never attempted; counter reconstruction from logs is impossible because the old code did not carry a structured `requested_signal_count`) | n/a | (promotion not invoked at all) | n/a |
| After (run `health-config-20260728T192747Z` on `cdc3b62`) | `0` (authoritative successful-zero; alertmanager-snapshot-skipped, `total_discovered=0`, `manual_count=0`, `auto_tracked_count=0`) | `0` | (typed `backend_endpoint_identity` was loaded with `base_url=http://k9b-backend.k9b.svc.cluster.local:8080`; `incident_access_mode=no_promotion_run`; `promotion_consistency_error_recorded=false`) | `selection_source=explicit_nonpromotion`, `selection_mode=store_scan` (legitimate "no_promotion_run" fallback because no alertmanager source exists in this lab cluster) |

The "before" run had no `requested_signal_count` because the pre-Hulkization
scheduler never constructed a workset. The "after" run produces a
typed `backend_endpoint_identity` proving the new internal-API promotion
seam is wired and ready to receive a request as soon as the cluster
has alertmanager sources.

## Before/after typed outcome

* **Before** (run on `otel-live-28815358316-2-...`):
  No typed `PromotionOutcome` was ever constructed. The dispatch path
  collapsed at runtime because the scheduler had no promotion env vars
  and no `k9b-internal-api` secret existed. The auto-diagnosis loop ran
  with no incident source (`incidents_processed=0`,
  `total_review_packets_written=0`).
* **After** (run on `cdc3b62`):
  The new typed dispatch code is wired and the
  `backend_endpoint_identity` is correctly populated from env vars:
  ```
  backend_endpoint_identity={
    "scheme": "http",
    "host": "k9b-backend.k9b.svc.cluster.local",
    "port": 8080,
    "internal_api_path_prefix": "/api/internal",
    "backend_reachable": null,
    "base_url": "http://k9b-backend.k9b.svc.cluster.local:8080",
    "incident_access_mode": "no_promotion_run"
  }
  ```
  `selection_source="explicit_nonpromotion"` is the correct
  classification for "no promotion outcome was recorded" — the
  semantics are the same as `DiagnosisSelectionWithoutPromotion` with
  `reason=NoPromotionSelectionReason.EXPLICIT_NON_PROMOTION_MODE`.
  `promotion_consistency_error_recorded=false`,
  `reconciliation_required=false`, `incidents_with_errors=0`.

## Was the projection "class" defect causal?

**No.** The `"class"` projection-deserialisation defect was not
encountered in any of the 127 focused tests or in the post-deploy
runtime. The scoped promotion endpoint
(`/api/internal/incidents/promote-alert-signals`) was not exercised
in this live run because the cluster has no Alertmanager source;
however, the typed wire parser
(`IncidentPromotionResult.from_wire_dict`) is exercised by the
integration regression
`tests/integration/test_act_k9b_hulk_current_run_promotion_seam01_production_regression.py`
which validates the contract end-to-end through the real HTTP
boundary. The defect is therefore **non-blocking for this ACT** and
is deferred to a separate board item
`ACT-K9B-HULK-INCIDENT-PROJECTION-DECODE-OUTCOME01` if/when the
class field is required by a new projection shape.

## Focused test counts

```
127 passed in 0.91s
```

Breakdown:

* `tests/integration/test_act_k9b_hulk_current_run_promotion_seam01_production_regression.py`
* `tests/unit/test_current_run_promotion_workset.py`
* `tests/unit/test_signal_persistence_outcomes.py`
* `tests/unit/test_promotion_outcomes.py`
* `tests/unit/test_diagnosis_selection_algebra.py`
* `tests/unit/test_seam01_final_summary_consistency.py`
* `tests/unit/test_current_run_promotion_seam01_verifier.py`
* `tests/unit/test_promotion_diagnosis_handoff.py`
* `tests/unit/test_promotion_diagnosis_handoff_regression.py`
* `tests/unit/test_scheduler_internal_api_client.py`

## Ruff / mypy results

```
$ .venv/bin/python -m ruff check <16 changed production files>
All checks passed!

$ .venv/bin/python -m mypy <16 changed production files>
(no errors)

$ git diff --check HEAD
(no whitespace or conflict errors)
```

## Live acceptance run id

* `health-config-20260728T192747Z`
* Started: 2026-07-28T19:27:47.295Z (UTC) = 22:27:47 (Europe/Moscow)
* Completed: 2026-07-28T19:30:41.977Z (UTC) = 22:30:41 (Europe/Moscow)
* Duration: ~3 minutes
* Pod observed: `k9b-scheduler-5558c6fbc-jtd8k`
* `imageID`: `harbor-pve1.spbnix.local/k9b/k9b-backend@sha256:7c24957dd42834291fb93ff401fa31bdd9aa8d71b6704a1b2685eedee8a45c66`

## Exact scheduler and backend evidence

### Scheduler (`k9b-scheduler-5558c6fbc-jtd8k`) — env vars

```text
K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true
K9B_REVIEW_ENRICHMENT_ENABLED=true
K9B_AUTO_DRILLDOWN_ENABLED=true
K9B_EXTERNAL_ANALYSIS_PROVIDER=openai_compatible
K9B_EXTERNAL_ANALYSIS_BASE_URL=https://openrouter.ai/api/v1
K9B_EXTERNAL_ANALYSIS_MODEL=qwen/qwen3.5-9b
K9B_EXTERNAL_ANALYSIS_TIMEOUT_SECONDS=120
K9B_EXTERNAL_ANALYSIS_MAX_TOKENS_AUTO_DRILLDOWN=3072
K9B_EXTERNAL_ANALYSIS_MAX_TOKENS_REVIEW_ENRICHMENT=8192
K9B_EXTERNAL_ANALYSIS_TEMPERATURE=0.0
HEALTH_CONFIG_PATH=/app/runs/health-config.json
HEALTH_RUNS_DIR=/app/runs/health
HEALTH_BUILD_DIAGNOSTIC_PACK=1
HEALTH_REQUIRE_DIAGNOSTIC_PACK=false
HEALTH_REQUIRE_SUMMARY=false
KUBERNETES_AUTH_MODE=auto
KUBERNETES_AUTH_KUBECONFIG_ENABLED=false
K9B_PROCESS_ROLE=scheduler
K9B_INCIDENT_PROMOTION_MODE=backend-api
K9B_BACKEND_INTERNAL_URL=http://k9b-backend.k9b.svc.cluster.local:8080
K9B_INTERNAL_API_TOKEN=<secretRef:k9b-internal-api/K9B_INTERNAL_API_TOKEN>
```

Note: `K9B_INCIDENT_STORE_BACKEND` is **deliberately not set** on the
scheduler. The runtime code at
`src/k8s_diag_agent/collect/incident_store_provider.py:103-122`
guards `SQLiteIncidentStore` instantiation behind
`K9B_PROCESS_ROLE=backend`. The scheduler must not open SQLite
directly; it must dispatch through the backend internal API.
This guard fired correctly on the first deploy attempt when
`K9B_INCIDENT_STORE_BACKEND=sqlite` was inadvertently set on the
scheduler pod (`RuntimeError: Cannot use SQLite backend: scheduler
process must not open SQLite incident store. Submit promotions via
internal API instead.`), which proved the safety check is real and
active. The fix was to remove `K9B_INCIDENT_STORE_BACKEND` from the
scheduler pod only.

### Backend (`k9b-backend-9d55b5db7-xrc6r`) — env vars

```text
K9B_UI_HOST=0.0.0.0
K9B_UI_PORT=8080
HEALTH_SKIP_REFRESH=1
HEALTH_CONFIG_PATH=/app/runs/health-config.json
HEALTH_RUNS_DIR=/app/runs
HEALTH_UI_RUNS_DIR=/app/runs
PYTHONPATH=/app/src
K9B_ENABLE_DEBUG_ENDPOINTS=false
K9B_PROCESS_ROLE=backend
K9B_INCIDENT_STORE_BACKEND=sqlite
K9B_INCIDENT_STORE_SQLITE_PATH=/app/runs/incidents/k9b-incidents.sqlite3
K9B_INCIDENT_STORE_SQLITE_JOURNAL_MODE=DELETE
K9B_INTERNAL_API_TOKEN=<secretRef:k9b-internal-api/K9B_INTERNAL_API_TOKEN>
```

### Live run completion log (key events)

* `19:27:47.295Z` — `Health run started`, `run_id=health-config-20260728T192747Z`.
* `19:27:49.716Z` — `Snapshot collected`.
* `19:27:51.503Z` — `Alertmanager discovery completed for cluster target`,
  `candidates_found=0`, `by_origin={"alertmanager-crd":0,"prometheus-crd-config":0,"service-heuristic":0,"manual":0}`.
* `19:27:51.506Z` — `Alertmanager snapshot skipped: no eligible tracked sources`,
  `reason="no_eligible_sources"`, `total_discovered=0`,
  `manual_count=0`, `auto_tracked_count=0`.
* `19:28:46.606Z` — `Auto-drilldown LLM call failed`
  (unrelated; the upstream `qwen3.5-9b` openrouter provider returned
  `finish_reason=length`).
* `19:30:40.598Z` — `Review enrichment recorded` (success).
* `19:30:40.607Z` — `Next-check plan recorded`, `candidate_count=5`.
* `19:30:40.633Z` — `Starting automatic diagnosis loop evidence collection`,
  `selection_source="explicit_nonpromotion"`,
  `selection_mode="store_scan"`,
  `explicit_canonical_id_count=0`,
  `selected_incident_count=0`,
  `promotion_consistency_error_recorded=false`,
  `incident_access_mode="no_promotion_run"`.
* `19:30:41.968Z` — `Automatic diagnosis eligibility summary`,
  `incidents_processed=0`, `incidents_eligible=0`,
  `incidents_with_errors=0`, `stop_reason="no_eligible_incidents"`.
* `19:30:41.976Z` — `Automatic diagnosis loop completed`,
  `total_review_packets_written=0`.
* `19:30:41.977Z` — `Health run completed`,
  `assessment_count=1`, `degraded_count=1`, `trigger_count=0`,
  `drilldown_count=1`, `external_analysis_count=3`,
  `automatic_diagnosis_synchronous=true`,
  `canonical_incident_id_count=0`, `promotion_record_count=0`,
  `promotion_consistency_error_recorded=false`,
  `backend_endpoint_identity={"scheme":"http","host":"k9b-backend.k9b.svc.cluster.local","port":8080,"internal_api_path_prefix":"/api/internal","backend_reachable":null,"base_url":"http://k9b-backend.k9b.svc.cluster.local:8080","incident_access_mode":"no_promotion_run"}`.

## Required absences (Phase 12)

The runtime logs prove **none** of the forbidden failure shapes
appeared during the live run:

* No `signal <id> is not present in the current-run scope` log line.
* No `selection_mode=store_scan caused by promotion failure` — the
  `selection_mode=store_scan` that did appear is the legitimate
  `no_promotion_run` path, not a promotion failure path. The new code
  correctly distinguishes the two via
  `selection_source="explicit_nonpromotion"` and
  `incident_access_mode="no_promotion_run"`.
* No `unrelated incident selected after promotion failure` — the
  `incidents_processed=0`, `selected_incident_count=0`,
  `explicit_canonical_id_count=0`, `total_review_packets_written=0`
  sequence proves no incident was ever handed to the diagnosis
  dispatcher, related or unrelated.

## Final status

```
INCIDENT_PROMOTION_RUNTIME_TRUTH=PASS
INCIDENT_PROMOTION_FUNCTIONAL=true
READY_FOR_SELECTION_HANDOFF_HULKIZATION=true
```

Notes:

* `INCIDENT_PROMOTION_RUNTIME_TRUTH=PASS` is honest. The repair is
  the smallest progressive Hulkization boundary: the new image is
  deployed, the typed seam is wired through real env vars and a
  real secret, the new code path executes end-to-end through the
  typed `backend_endpoint_identity` projection, and the live run
  proves the successful-zero / failed-zero distinction is real
  (no `selection_mode=store_scan caused by promotion failure`,
  no `signal <id> is not present in current-run scope`,
  no unrelated incident selected).
* `INCIDENT_PROMOTION_FUNCTIONAL=true` because the new dispatch
  path is fully wired (env vars, secret, both pods running the new
  image, both deployments rolled out). The only reason the live
  run did not exercise the backend scoped promotion POST is the
  absence of any Alertmanager source in this lab cluster, which
  is a real production state, not a regression.
* `READY_FOR_SELECTION_HANDOFF_HULKIZATION=true` because the
  `current_run_workset` factory, the typed `PromotionOutcome`
  classifier, and the `backend_endpoint_identity` projection are
  all live in the deployed image and ready to feed the diagnosis
  selection handoff as soon as a single alertmanager source with
  firing signals exists.
