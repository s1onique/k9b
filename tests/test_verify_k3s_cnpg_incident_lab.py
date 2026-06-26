"""Unit tests for the K3s CNPG incident lab artifact verifier and sanitizer.

This module is a thin re-export wrapper. Tests are organized into focused modules:
- test_verify_k3s_cnpg_incident_lab_fixtures: Shared constants and fixtures
- test_verify_k3s_cnpg_incident_lab_verifier: Verifier script tests
- test_verify_k3s_cnpg_incident_lab_sanitizer: Sanitizer script tests
"""

# Re-export all test classes from the split modules for backward compatibility
from tests.test_verify_k3s_cnpg_incident_lab_fixtures import (
    VERIFIER_SCRIPT,
    SANITIZER_SCRIPT,
    FIXTURES_DIR,
    PASS_FIXTURE,
    FAIL_NO_INCIDENT_FIXTURE,
    FAIL_SECRET_FIXTURE,
)

# Verifier tests
from tests.test_verify_k3s_cnpg_incident_lab_verifier import (
    TestVerifierScriptExists,
    TestVerifierPassFixture,
    TestVerifierFailNoIncident,
    TestVerifierFailSecret,
    TestVerifierMissingFiles,
    TestVerifierMalformedJSON,
    TestVerifierMissingRequiredFields,
    TestVerifierInconsistentState,
    TestVerifierNonExistentDirectory,
)

# Sanitizer tests
from tests.test_verify_k3s_cnpg_incident_lab_sanitizer import (
    TestSanitizerScriptExists,
    TestSanitizerSafeK8sFields,
    TestSanitizerActualSecrets,
    TestSanitizerFindings,
    TestSanitizerMultiDocumentYAML,
    TestSanitizerEndToEnd,
    TestSanitizerDeduplication,
    TestSanitizerDependencies,
)

__all__ = [
    # Fixtures
    "VERIFIER_SCRIPT",
    "SANITIZER_SCRIPT",
    "FIXTURES_DIR",
    "PASS_FIXTURE",
    "FAIL_NO_INCIDENT_FIXTURE",
    "FAIL_SECRET_FIXTURE",
    # Verifier tests
    "TestVerifierScriptExists",
    "TestVerifierPassFixture",
    "TestVerifierFailNoIncident",
    "TestVerifierFailSecret",
    "TestVerifierMissingFiles",
    "TestVerifierMalformedJSON",
    "TestVerifierMissingRequiredFields",
    "TestVerifierInconsistentState",
    "TestVerifierNonExistentDirectory",
    # Sanitizer tests
    "TestSanitizerScriptExists",
    "TestSanitizerSafeK8sFields",
    "TestSanitizerActualSecrets",
    "TestSanitizerFindings",
    "TestSanitizerMultiDocumentYAML",
    "TestSanitizerEndToEnd",
    "TestSanitizerDeduplication",
    "TestSanitizerDependencies",
]
