"""Fixtures for diagnosis provider artifact sanitization and verification.

These fixtures provide sample LLM outputs for testing:
- Provider artifact parsing
- Secret sanitization in diagnostics output
- Response validation

Usage:
    from tests.fixtures.provider_artifact_fixtures import (
        VALID_JSON_ARTIFACT,
        ARTIFACT_WITH_SECRET,
        verify_artifact_sanitized,
    )
"""

from __future__ import annotations

from typing import Any

# Valid JSON artifact from LLM provider (typical one-pass diagnosis output)
VALID_JSON_ARTIFACT = {
    "summary": "High CPU pressure on node-01 due to runaway process",
    "hypotheses": [
        {
            "id": "h1",
            "description": "Runaway process consuming excessive CPU",
            "evidence": ["kubectl top pods shows process at 95% CPU", "Load average 8.0 on 4-core node"],
            "confidence": "high",
            "next_checks": [
                "kubectl top pods -n default --sort-by=cpu",
                "kubectl describe node node-01 | grep -A5 Conditions",
            ],
        },
        {
            "id": "h2",
            "description": "Node resource exhaustion",
            "evidence": ["Memory usage at 90%", "kubelet reporting PLEG errors"],
            "confidence": "medium",
            "next_checks": [
                "kubectl get nodes -o wide",
                "journalctl -u kubelet | grep -i memory",
            ],
        },
    ],
    "recommended_actions": [
        {
            "action": "Identify top CPU consumer",
            "command": "kubectl top pods -A --sort-by=cpu --no-headers | head -5",
            "risk": "low",
            "rationale": "Read-only operation to identify resource consumer",
        },
    ],
    "confidence": "medium",
    "requires_escalation": False,
}

# Artifact containing a secret/API key that should be sanitized
ARTIFACT_WITH_SECRET = {
    "summary": "API authentication failure detected",
    "hypotheses": [
        {
            "id": "h1",
            "description": "Invalid API key configured",
            "evidence": [
                "API server returned 401 Unauthorized",
                "Request failed with: 'sk-proj-abc123xyzsecretkeyvalue'",
            ],
            "confidence": "high",
            "next_checks": ["Check secret configuration in deployment"],
        }
    ],
    "recommended_actions": [],
    "confidence": "high",
    "requires_escalation": True,
}

# Expected sanitized version (secret replaced)
ARTIFACT_SANITIZED_EXPECTED = {
    "summary": "API authentication failure detected",
    "hypotheses": [
        {
            "id": "h1",
            "description": "Invalid API key configured",
            "evidence": [
                "API server returned 401 Unauthorized",
                "Request failed with: '<REDACTED: API_KEY>'",
            ],
            "confidence": "high",
            "next_checks": ["Check secret configuration in deployment"],
        }
    ],
    "recommended_actions": [],
    "confidence": "high",
    "requires_escalation": True,
}


def verify_artifact_sanitized(artifact: dict, original: dict) -> list[str]:
    """Verify artifact secrets are properly sanitized.

    Args:
        artifact: Sanitized artifact to verify
        original: Original artifact with potential secrets

    Returns:
        List of secrets still present (empty = all sanitized)
    """
    import json
    import re

    def find_secrets(obj: str | dict[str, Any] | list[Any], path: str = "") -> list[str]:
        """Recursively find potential secrets in object."""
        found: list[str] = []
        if isinstance(obj, str):
            # Check for common secret patterns
            secret_patterns = [
                r"sk-[a-zA-Z0-9]{20,}",  # OpenAI-style keys
                r"sk-proj-[a-zA-Z0-9]{20,}",  # OpenAI project keys
                r"ghp_[a-zA-Z0-9]{36,}",  # GitHub tokens
                r"glpat-[a-zA-Z0-9\-]{20,}",  # GitLab tokens
                r"AKP[a-zA-Z0-9]{20,}",  # Azure tokens
            ]
            for pattern in secret_patterns:
                if re.search(pattern, obj):
                    found.append(f"{path}: {obj[:50]}...")
        elif isinstance(obj, dict):
            for key, value in obj.items():
                found.extend(find_secrets(value, f"{path}.{key}" if path else key))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                found.extend(find_secrets(item, f"{path}[{i}]"))
        return found

    artifact_str = json.dumps(artifact)
    original_str = json.dumps(original)

    # Check that original secrets are gone from artifact
    original_secrets = find_secrets(original_str)
    still_present: list[str] = []

    for secret in original_secrets:
        # Extract the secret value pattern
        match = re.search(r"sk-[a-zA-Z0-9]{20,}|sk-proj-[a-zA-Z0-9]{20,}", original_str)
        if match and match.group() in artifact_str:
            still_present.append(match.group())

    return still_present


# Malformed response examples for error handling tests
MALFORMED_RESPONSES = [
    # Empty response
    {},
    # Missing choices
    {"id": "chatcmpl-123"},
    # Choices with no message
    {"choices": [{"finish_reason": "stop"}]},
    # Message with no content
    {"choices": [{"message": {"role": "assistant"}}]},
    # Invalid JSON (as string)
    "not valid json",
    # HTML error page
    "<html><body>403 Forbidden</body></html>",
]
