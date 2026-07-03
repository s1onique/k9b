# Provider Health Envelope Contract

## Overview

This document defines the wire-format contract for provider preflight health responses in k9b live labs.

## Problem Statement

Live-lab provider preflight output from the curl wrapper includes diagnostic metadata around the provider-health JSON payload. This metadata must be distinguished from:

1. Provider-health JSON body content (the actual health payload)
2. Transport envelope metadata (curl wrapper diagnostics)
3. Output contamination (unexpected non-JSON data)

## Wire-Format Layers

The provider health response body is validated in layers:

1. **Transport envelope extraction**: Known successful curl metadata is extracted as transport layer metadata, not body content.
2. **JSON body classification**: Valid JSON body passes to semantic evaluation.
3. **Semantic provider-health evaluation**: Only proceeds after wire-format passes.

## Provider-Health JSON Body

The provider-health JSON body is the valid JSON document that contains:

- `healthy`: boolean
- `primary_failure_class`: string
- `provider_enabled`: boolean
- `provider_configured`: boolean
- `provider_status`: string
- `phase`: string
- `dependencies`: array of dependency status objects

## Curl Wrapper Envelope

The curl wrapper emits a known diagnostic envelope around provider health JSON:

```
{valid JSON}\n
STDERR_BLOCK\n          # Optional marker
<debug noise>\n        # Optional stderr content
CURL_EXIT=<code>\n
HTTP_CODE=<code>\n
```

Note: STDOUT_BLOCK prefix handling is separate from this boundary contract.
It is stripped at a higher layer before this classifier receives the body.

## Accepted Known Successful Envelope

The following envelope patterns are **ACCEPTED** as transport metadata:

| Pattern | Description |
|---------|-------------|
| `{JSON}\nCURL_EXIT=0\nHTTP_CODE=200` | Minimal envelope |
| `{JSON}\nSTDERR_BLOCK\nCURL_EXIT=0\nHTTP_CODE=200` | With STDERR_BLOCK marker |
| `{JSON}\nSTDERR_BLOCK\n<noise>\nCURL_EXIT=0\nHTTP_CODE=200` | With debug noise |

**Rule**: Only CURL_EXIT=0 AND HTTP_CODE=200 together constitute a successful envelope.

## Contamination

The following patterns are **CONTAMINATION** (rejected):

| Pattern | Reason |
|---------|--------|
| Non-whitespace prefix + JSON | Garbage before JSON (only whitespace or STDOUT_BLOCK allowed) |
| JSON + CURL_EXIT=N (N≠0) | Failed curl |
| JSON + HTTP_CODE=N (N≠200) | Failed HTTP |
| JSON + known envelope + extra | Unknown data after envelope |
| JSON + malformed envelope | Invalid envelope format |

## Invalid JSON

The following patterns are **INVALID JSON** (rejected):

| Pattern | Reason |
|---------|--------|
| JSON + concatenated JSON | Multiple adjacent JSON documents |
| Malformed JSON structure | Truncated/invalid JSON syntax |

Note: Concatenated JSON documents are classified as `provider_health_invalid_json`, NOT contamination.
This distinguishes between malformed JSON structure and valid JSON with unexpected non-JSON data.

## Why This Exists

Live-lab provider preflight uses a curl wrapper that writes diagnostic metadata (exit codes, HTTP codes, stderr content) after the provider-health JSON payload. This metadata is transport-layer information, not part of the provider-health body.

Without envelope acceptance, the curl metadata causes valid provider-health JSON to be rejected as contamination, breaking the preflight gate even when the provider is healthy.

## APF Contract Guard

> **Known successful curl wrapper metadata is accepted transport envelope metadata, not provider-health JSON contamination.**

Do not flip this boundary without changing the contract table and this doc. See `tests/contracts/provider_health_envelope_cases.py` for the executable contract matrix.

## References

- `scripts/lab_common/provider_preflight_health.py` - Implementation
- `scripts/lab_common/provider_preflight_curl_envelope.py` - Envelope parser
- `tests/contracts/provider_health_envelope_cases.py` - Executable contract
- `tests/test_provider_health_envelope_apf_contract.py` - APF regression tests
