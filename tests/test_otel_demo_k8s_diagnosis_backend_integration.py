"""Compatibility placeholder for split backend integration tests.

Tests have been split by responsibility into:
- test_otel_demo_k8s_diagnosis_backend_integration_success.py: happy-path tests
- test_otel_demo_k8s_diagnosis_backend_integration_failures.py: failure-path tests
- helpers/otel_demo_k8s_diagnosis_backend_integration_helpers.py: shared fixtures

This file is kept as a compatibility stub to avoid import breakages in
consumers that reference the original module path.
"""

__test__ = False
