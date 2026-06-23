# Image Preflight Render Mismatch Test Fixture

## Purpose

This fixture proves the old bug where preflight checks one image reference but Helm deploys another.

## Bug Scenario

**Before fix:**
- Workflow preflight validates: `harbor-pve1.spbnix.local/k9b/k9b-frontend:d9b4d2376d9497bba8be2a007da087ec6c1d2c1a`
- Helm deploys (from chart defaults): `registry.spbnix.com/gitinsky/k9b-frontend:ecacd81`
- Kubernetes reports: `ImagePullBackOff` (cannot pull the preflight-validated image)

**Root cause:**
1. Workflow correctly computed the frontend image ref from inputs
2. Workflow passed frontend image to preflight for validation
3. BUT workflow did NOT pass `--set image.frontend.repository` and `--set image.frontend.tag` to Helm
4. Helm used chart defaults (`values.yaml`) instead

## Test Structure

### Input: rendered-images.json (simulated Helm output with OLD defaults)

```json
{
  "timestamp": "2026-06-23T08:00:00+00:00",
  "helm_command": "helm template k9b ./charts/k9b --namespace k9b-cnpg-lab-123456 --values ./charts/k9b/values-live-lab.yaml ...",
  "success": true,
  "images": [
    {
      "image_ref": "registry.spbnix.com/gitinsky/k9b-backend:ecacd81",
      "component": "backend",
      "container_name": "backend",
      "resource_kind": "Deployment",
      "resource_name": "k9b-backend",
      "is_init_container": false
    },
    {
      "image_ref": "registry.spbnix.com/gitinsky/k9b-frontend:ecacd81",
      "component": "frontend",
      "container_name": "frontend",
      "resource_kind": "Deployment",
      "resource_name": "k9b-frontend",
      "is_init_container": false
    }
  ],
  "summary": {
    "total_images": 2,
    "backend_image": "registry.spbnix.com/gitinsky/k9b-backend:ecacd81",
    "frontend_image": "registry.spbnix.com/gitinsky/k9b-frontend:ecacd81"
  }
}
```

### Expected: image-preflight-compare.json (FAILURE)

The compare should FAIL with:
- `rendered_frontend`: `registry.spbnix.com/gitinsky/k9b-frontend:ecacd81`
- `expected_frontend`: `harbor-pve1.spbnix.local/k9b/k9b-frontend:d9b4d2376d9497bba8be2a007da087ec6c1d2c1a`
- `matches`: false
- `failure_class`: `image_preflight_render_mismatch`

## After Fix

The new `render-preflight` step catches this mismatch BEFORE registry preflight:

1. Renders Helm with ALL --set overrides (including frontend)
2. Extracts images from rendered manifests
3. Compares against expected image refs
4. **FAILS** with `image_preflight_render_mismatch` before any registry checks

This prevents the workflow from proceeding when the deployed image differs from the validated image.

## Verification

```bash
# Run the render preflight script
.venv/bin/python scripts/k9b_cnpg_image_preflight.py render-preflight \
  --chart ./charts/k9b \
  --release k9b \
  --namespace k9b-cnpg-lab-test \
  --values ./charts/k9b/values-live-lab.yaml \
  --set image.backend.repository=harbor-pve1.spbnix.local/k9b/k9b-backend \
  --set image.backend.tag=d9b4d2376d9497bba8be2a007da087ec6c1d2c1a \
  --set image.frontend.repository=harbor-pve1.spbnix.local/k9b/k9b-frontend \
  --set image.frontend.tag=d9b4d2376d9497bba8be2a007da087ec6c1d2c1a \
  --set backend.auth.enabled=false \
  --set kubernetes.auth.mode=inCluster \
  --expected-backend harbor-pve1.spbnix.local/k9b/k9b-backend:d9b4d2376d9497bba8be2a007da087ec6c1d2c1a \
  --expected-frontend harbor-pve1.spbnix.local/k9b/k9b-frontend:d9b4d2376d9497bba8be2a007da087ec6c1d2c1a \
  --artifact-dir ./lab-artifacts/test

# Should PASS (both images match when frontend overrides are passed)
echo $?  # 0

# Now simulate the OLD BUG: only backend override, no frontend override
.venv/bin/python scripts/k9b_cnpg_image_preflight.py render-preflight \
  --chart ./charts/k9b \
  --release k9b \
  --namespace k9b-cnpg-lab-test \
  --values ./charts/k9b/values-live-lab.yaml \
  --set image.backend.repository=harbor-pve1.spbnix.local/k9b/k9b-backend \
  --set image.backend.tag=d9b4d2376d9497bba8be2a007da087ec6c1d2c1a \
  --set backend.auth.enabled=false \
  --set kubernetes.auth.mode=inCluster \
  --expected-backend harbor-pve1.spbnix.local/k9b/k9b-backend:d9b4d2376d9497bba8be2a007da087ec6c1d2c1a \
  --expected-frontend harbor-pve1.spbnix.local/k9b/k9b-frontend:d9b4d2376d9497bba8be2a007da087ec6c1d2c1a \
  --artifact-dir ./lab-artifacts/test-bug

# Should FAIL with image_preflight_render_mismatch
echo $?  # 2
```

## Close Criteria

This fixture proves the close criteria:

- [x] Rendered manifest image extraction added (`k9b_cnpg_image_preflight_render.py`)
- [x] `rendered-images.json` artifact added
- [x] Mismatch between preflight image refs and rendered manifest images fails before Helm deploy
- [x] Registry/node preflight runs against rendered image refs (when frontend override is present)
- [x] Test fixture proves the old bug: preflight ref harbor...:sha + rendered ref registry.spbnix.com/...:ecacd81 => fail `image_preflight_render_mismatch`
- [x] Live workflow no longer reaches rollout monitor with wrong image unless intentionally configured
