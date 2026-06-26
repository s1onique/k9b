"""Tests for incident one-pass diagnosis service.

This module is a thin re-export of the incident diagnosis service tests,
organized into focused test modules for better maintainability.

Modules:
    - test_incident_diagnosis_service_fixtures: Shared fixtures and helpers
    - test_incident_diagnosis_service_validation: Service request validation tests
    - test_incident_diagnosis_service_artifacts: Artifact persistence and DTO tests
    - test_incident_diagnosis_service_safety: Safety enforcement tests
    - test_incident_diagnosis_service_components: Component-specific tests
    - test_incident_diagnosis_service_golden_case: Golden-case integration tests

Run all tests with: pytest tests/test_incident_diagnosis_service*.py
Run specific module: pytest tests/test_incident_diagnosis_service_validation.py
"""

from __future__ import annotations

from tests.test_incident_diagnosis_service_artifacts import *  # noqa: F401, F403
from tests.test_incident_diagnosis_service_components import *  # noqa: F401, F403

# Re-export all test modules for backwards compatibility
# Tests can be run from this module or from individual test modules
from tests.test_incident_diagnosis_service_fixtures import *  # noqa: F401, F403
from tests.test_incident_diagnosis_service_golden_case import *  # noqa: F401, F403
from tests.test_incident_diagnosis_service_safety import *  # noqa: F401, F403
from tests.test_incident_diagnosis_service_validation import *  # noqa: F401, F403

__all__ = [  # noqa: RUF012, F405
    "test_incident_diagnosis_service_fixtures",  # noqa: F405
    "test_incident_diagnosis_service_golden_case",  # noqa: F405
    "test_incident_diagnosis_service_artifacts",  # noqa: F405
    "test_incident_diagnosis_service_safety",  # noqa: F405
    "test_incident_diagnosis_service_components",  # noqa: F405
    "test_incident_diagnosis_service_validation",  # noqa: F405
]
