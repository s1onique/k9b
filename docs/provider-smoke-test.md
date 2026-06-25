# Diagnosis Provider Smoke Test

This document describes how to verify the diagnosis provider is functioning correctly in the live lab.

## Workflow-Owned Smoke Test

The live-lab workflow (`k9b-cnpg-incident-lab-live.yml`) owns the smoke test. When `enable_provider_smoke=true`:

1. Creates Kubernetes Secret `k9b-diagnosis-credentials` with API key
2. Injects provider config via Helm values
3. Calls POST `/api/incidents/{id}/one-pass-diagnosis` against live backend
4. Verifies `provider_configured=true` and `provider_invocation_attempted=true`
5. Runs provider artifact sanitizer (secrets, internal IPs checked)
6. Fails workflow if provider was not invoked when explicitly enabled

### Enabling Provider Smoke

1. Set `diagnosisProvider.enabled=true` in values
2. Add LLM endpoint and credentials to protected secrets
3. Add `enable_provider_smoke=true` to workflow trigger:

```yaml
on:
  workflow_dispatch:
    inputs:
      enable_provider_smoke:
        description: 'Enable provider smoke test'
        required: false
        type: boolean
        default: false
```

### Required Secrets

- `K9B_DIAGNOSIS_BASE_URL`: Provider API base URL (placeholder, not logged)
- `K9B_DIAGNOSIS_MODEL`: Model name
- `K9B_DIAGNOSIS_API_KEY`: API key for authentication

### Expected Response

The smoke test expects HTTP 200 with JSON response containing:

```json
{
  "provider_configured": true,
  "provider_invocation_attempted": true
}
```

Non-200 HTTP status causes immediate workflow failure.

## Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `provider_configured: false` | Missing env vars or secret | Verify secrets configured |
| `provider_invocation_attempted: false` | Provider configured but call failed | Check provider logs |
| HTTP 503 | Provider not initialized | Verify Helm values applied |
| HTTP 500 | Provider call failed | Check provider endpoint |
| Artifact verification failure | Secrets or topology in response | Check provider output |

## Artifact Verification

The `verify_diagnosis_provider_artifacts.py` script validates provider artifacts:

- **Directory mode**: `--directory` processes all files in a directory
- **Fail-closed**: Any artifact with secrets or internal patterns is rejected
- **No recursion**: Only top-level files are checked (subdirectories fail)

### Detected Patterns

- Bearer tokens and API keys (sk-, ghp_, etc.)
- AWS access keys (AKIA...)
- JWT tokens
- Internal IPs (10.x.x.x, 172.16-31.x.x, 192.168.x.x)
- Kubernetes internal DNS (*.cluster.local)
- Mutation commands (kubectl exec/run/delete, helm install/upgrade)

## Prerequisites for Local Testing

If you need to test the provider endpoint locally:

1. Set environment variables:
   ```bash
   export K9B_DIAGNOSIS_PROVIDER_NAME=openai_compatible
   export K9B_DIAGNOSIS_MODEL=<model>
   export K9B_DIAGNOSIS_BASE_URL=<url>
   export K9B_DIAGNOSIS_API_KEY=<key>
   ```

2. Verify connectivity with curl:
   ```bash
   curl -sS -o /dev/null -w "%{http_code}" \
     -H "Authorization: Bearer ${K9B_DIAGNOSIS_API_KEY}" \
     "${K9B_DIAGNOSIS_BASE_URL}/v1/models"
   ```

3. Run artifact verification on test output:
   ```bash
   python scripts/verify_diagnosis_provider_artifacts.py \
     --input ./test-artifacts \
     --directory
   ```
