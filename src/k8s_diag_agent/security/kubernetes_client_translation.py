"""Error translation helpers for Kubernetes API exceptions.

This module re-exports translate_api_exception from kubernetes_client_errors
for backward compatibility. The canonical location is kubernetes_client_errors.py.
"""

from __future__ import annotations

from .kubernetes_client_errors import translate_api_exception

__all__ = [
    "translate_api_exception",
]
