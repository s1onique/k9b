"""Provider proof helper for live-lab smoke testing.

Extracts provider configuration and invocation status for proving
that the diagnosis provider was actually invoked during smoke testing.
"""

from __future__ import annotations


class NoOpDiagnosisProvider:
    """No-op diagnosis provider marker class (duck-typed)."""

    def complete(self, prompt: str) -> str:
        raise RuntimeError("No diagnosis provider configured")


def get_provider_proof_fields(
    provider: object | None,
) -> tuple[bool, bool]:
    """Extract provider proof fields for live-lab smoke testing.

    Args:
        provider: The diagnosis provider instance

    Returns:
        Tuple of (provider_configured, provider_invocation_attempted)
        - provider_configured: True if a real (non-NoOp) provider was provided
        - provider_invocation_attempted: True if complete() was actually called
    """
    if provider is None:
        return False, False

    # Check if it's a real provider (not NoOp) - duck typed check
    provider_configured = not isinstance(provider, NoOpDiagnosisProvider)

    # Check if invocation was attempted via the tracking wrapper
    provider_invoked = bool(getattr(provider, 'invocation_attempted', False))

    return provider_configured, provider_invoked
