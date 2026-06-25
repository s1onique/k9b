# Diagnosis Provider Configuration

The diagnosis provider enables LLM-powered incident diagnosis for the k9b one-pass diagnosis service.

## Overview

The diagnosis provider is an OpenAI-compatible HTTP client that calls a configured LLM endpoint to generate structured incident diagnoses. It is wired into the UI server startup and can be configured via environment variables or Helm chart values.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    UI Server Startup                        │
│  _init_diagnosis_provider_at_startup()                      │
│         │                                                   │
│         ▼                                                   │
│  DiagnosisProviderConfig.from_env()                          │
│         │                                                   │
│         ▼                                                   │
│  build_diagnosis_provider_from_config()                     │
│         │                                                   │
│         ▼                                                   │
│  OpenAICompatibleDiagnosisProvider.complete()                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Incident One-Pass Diagnosis API                 │
│  POST /api/incidents/{incident_id}/one-pass-diagnosis       │
│         │                                                   │
│         ▼                                                   │
│  get_diagnosis_provider() → DiagnosisProvider.complete()    │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `K9B_DIAGNOSIS_PROVIDER_NAME` | Yes | Provider type: `openai_compatible`, `gigachat`, `qwen` |
| `K9B_DIAGNOSIS_MODEL` | Yes | Model identifier (e.g., `qwen/qwen2.5-7b-instruct`) |
| `K9B_DIAGNOSIS_BASE_URL` | Yes | Base URL for the LLM API (e.g., `http://llm-service:8080/v1`) |
| `K9B_DIAGNOSIS_API_KEY` | No | API key for authentication |
| `K9B_DIAGNOSIS_TIMEOUT_SECONDS` | No | Request timeout (1-300, default: 120) |
| `K9B_DIAGNOSIS_MAX_OUTPUT_CHARS` | No | Max response length (100-100000, default: 50000) |

### Helm Chart Configuration

```yaml
diagnosisProvider:
  enabled: true
  existingSecret: "k9b-diagnosis-credentials"
  apiKeyKey: K9B_DIAGNOSIS_API_KEY
  provider: "openai_compatible"
  baseUrl: "<provider-base-url>"
  model: "<model-name>"
  timeoutSeconds: 120
  maxOutputChars: 8000
```

## Secret Management

The API key should be stored in a Kubernetes Secret and injected via `secretKeyRef`:

```bash
kubectl create secret generic k9b-diagnosis-credentials \
  --from-literal=K9B_DIAGNOSIS_API_KEY='your-api-key'
```

```yaml
env:
  - name: K9B_DIAGNOSIS_API_KEY
    valueFrom:
      secretKeyRef:
        name: k9b-diagnosis-credentials
        key: K9B_DIAGNOSIS_API_KEY
```

## Live-Lab Integration

The live-lab workflow (`k9b-cnpg-incident-lab-live.yml`) handles provider smoke testing:

1. When `enable_provider_smoke=true`, creates the Kubernetes Secret
2. Passes `diagnosisProvider.*` values to Helm install
3. Calls the one-pass diagnosis API after deployment
4. Verifies `provider_configured` and `provider_invocation_attempted`
5. Runs artifact sanitizer on provider response

See [provider-smoke-test.md](provider-smoke-test.md) for details.

## Fail-Closed Behavior

When the diagnosis provider is not configured:
- Server starts without LLM diagnosis capability
- `POST /api/incidents/{incident_id}/one-pass-diagnosis` returns 503 if no provider is available

When the diagnosis provider is configured but fails:
- Authentication failures → RuntimeError with clear message
- Timeout → RuntimeError with timeout details
- Malformed response → RuntimeError with parsing error
- Non-200 HTTP status → Workflow fails immediately (live-lab)

## Supported Providers

| Provider | API Format | Notes |
|----------|------------|-------|
| `openai_compatible` | OpenAI chat completions | Generic OpenAI-compatible endpoints |
| `gigachat` | OpenAI-compatible | GigaChat API |
| `qwen` | OpenAI-compatible | Qwen/DashScope API |

## Monitoring

Provider initialization status is logged at server startup:

```
Diagnosis provider: not configured (set K9B_DIAGNOSIS_PROVIDER_NAME, K9B_DIAGNOSIS_MODEL, K9B_DIAGNOSIS_BASE_URL to enable)
Diagnosis provider: initializing (provider=openai_compatible, model=qwen/qwen2.5-7b-instruct, api_key_present=True)
Diagnosis provider: initialized successfully
```

## Safe Logging

The `to_safe_dict()` method returns configuration metadata without sensitive values:

```python
{
    "provider_name": "openai_compatible",
    "model": "qwen/qwen2.5-7b-instruct",
    "base_url_present": True,  # Only presence indicated, not value
    "api_key_present": True,   # Only presence indicated, not value
    "timeout_seconds": 120,
    "max_output_chars": 50000
}
```

Raw base URLs and API keys are never logged or included in artifacts.
