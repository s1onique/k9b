# ACT-K9B-HULK-INCIDENT-PROMOTION-RUNTIME-TRUTH01

## Mission

Restore the production scheduler-to-backend incident-promotion seam using the
smallest progressive Hulkization boundary. The deployed cluster
(`harbor-pve1.spbnix.local/k9b/k9b-backend:otel-live-28815358316-2-16fa88be7cee1f21ea0cd34ab6aff6508480c78a`,
image-id `sha256:7ebcb6b8c2282a545cd2988bbd40705c6bfd28cca43cecea5c61fb2e02fcbc8b`)
predates the Hulkization work, and its scheduler pod runs without any
promotion env vars, so the runtime cannot even attempt a backend scoped
promotion.

## Source starting point

* Worktree: `/Users/chistyakov/Projects/SPbNIX/k9b-incident-promotion-runtime-truth01`
* Branch: `hotfix/incident-promotion-runtime-truth01`
* Source commit: `33a3c494839cf8ed2c04b4c7203e2adec2320ce8`
  (merge of PR #1, "hotfix/incident-promotion-ci-recovery01" into `main`).
* Tree is identical to `origin/main`; the typed persistence / workset /
  promotion-outcome / dispatch-outcome seam is already structurally
  complete on `origin/main`. No source edits are required.

## Primary failure category (Phase 2)

`STALE_DEPLOYED_IMAGE` — combined with `BACKEND_ROUTE_OR_AUTHORITY_DEFECT`
because the scheduler pod environment has no `K9B_BACKEND_INTERNAL_URL`,
no `K9B_INTERNAL_API_TOKEN`, no `K9B_INCIDENT_PROMOTION_MODE`, and no
`K9B_PROCESS_ROLE`. The backend pod likewise has no
`K9B_INCIDENT_STORE_BACKEND` env var, so the dispatcher's `auto` mode
resolves to `local` and is forbidden for `scheduler+sqlite`. There is no
runtime path that ever issues a backend scoped promotion request.

## Local gates (Phase 10)

* 127 tests passing on the focused promotion and diagnosis selection
  suites (see `Required report`).
* `ruff check` clean on every changed production file.
* `mypy` clean on every changed production file.
* `git diff --check` clean against `HEAD`.

## Build and deploy (Phase 11)

1. Commit this evidence note on the hotfix branch.
2. `gh workflow run harbor.yml --ref hotfix/incident-promotion-runtime-truth01`
   dispatches the canonical `Build and Push to Harbor` workflow which
   builds and pushes an immutable `k9b-backend` image tagged with the
   workflow's run ID and commit SHA.
3. Wait for `build-backend-publish` to complete and record the
   `image_ref` and `digest` outputs.
4. Render the helm chart with `--set image.backend.tag=<new-tag>`,
   `--set scheduler.incidentPromotion.existingSecret=k9b-internal-api`,
   and the previously-prepared values so both scheduler and backend
   pick up the new image and the promotion env vars at the same time.
5. Apply via `helm upgrade --install` and wait for the
   `k9b-scheduler` and `k9b-backend` rollouts.

## Live acceptance (Phase 12)

See `Required report` for the run id, scheduler/backend evidence, and
final status block once the build, deploy, and one health run with
identity-matching alert signals have completed.
