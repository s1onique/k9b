"""Compatibility placeholder for split backend helper tests.

Tests moved to:
- tests/test_otel_demo_k8s_diagnosis_backend_contracts.py
- tests/test_otel_demo_k8s_diagnosis_backend_http.py
- tests/test_otel_demo_k8s_diagnosis_backend_artifacts.py
- tests/test_otel_demo_k8s_diagnosis_backend_integration.py

This file is kept for path compatibility but is marked non-collecting
to prevent pytest from collecting the re-exported test classes twice.
"""

from __future__ import annotations

__test__ = False
