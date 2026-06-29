#!/usr/bin/env python3
"""Regression test: prevent stale OTel demo fixture names in provider-diagnosis.

This test ensures that:
1. The OTel incident fixture uses chart 0.40.9 naming ("recommendation")
2. No hardcoded stale fixture names exist in provider_diagnosis.py

Chart 0.40.9 renamed services:
- recommendationservice -> recommendation
- productcatalogservice -> product-catalog
- checkoutservice -> checkout
- paymentservice -> payment
- shippingservice -> shipping
- currencyservice -> currency
- emailservice -> email
"""

from __future__ import annotations

import re
from pathlib import Path

# Stale service names that should NOT appear as hardcoded fixture names
STALE_FIXTURE_NAMES = {
    "recommendationservice",
    "productcatalogservice",
    "checkoutservice",
    "paymentservice",
    "shippingservice",
    "currencyservice",
    "emailservice",
    "frauddetectionservice",
    "imageprovider",
    "loadgenerator",
    "otelcol",
}

# The correct chart 0.40.9 fixture name for the OTel demo incident
EXPECTED_FIXTURE = "recommendation"


def get_provider_diagnosis_path() -> Path:
    """Get path to the provider diagnosis module."""
    repo_root = Path(__file__).parent.parent
    return repo_root / "scripts" / "k9b_otel_demo_lab_provider_diagnosis.py"


def test_provider_diagnosis_imports_otel_fixture_constant() -> None:
    """Provider diagnosis must import OTEL_INCIDENT_FIXTURE from constants."""
    source_path = get_provider_diagnosis_path()
    source_code = source_path.read_text()

    # Check that OTEL_INCIDENT_FIXTURE is imported from constants
    # Handle both single-line and multi-line imports
    import_pattern = re.compile(r"from\s+\.k9b_otel_demo_lab_constants\s+import\s+[^)]*OTEL_INCIDENT_FIXTURE", re.DOTALL)
    assert import_pattern.search(source_code), (
        "provider_diagnosis.py must import OTEL_INCIDENT_FIXTURE from constants"
    )


def test_provider_diagnosis_no_stale_fixture_names() -> None:
    """Provider diagnosis must not contain hardcoded stale fixture names."""
    source_path = get_provider_diagnosis_path()
    source_code = source_path.read_text()

    for stale_name in STALE_FIXTURE_NAMES:
        # Look for fixture_name = "<stale_name>" pattern
        pattern = rf'fixture_name\s*=\s*["\']?{stale_name}["\']?'
        matches = re.findall(pattern, source_code, re.IGNORECASE)
        assert not matches, (
            f"Found hardcoded stale fixture name '{stale_name}' in provider_diagnosis.py. "
            f"Should use OTEL_INCIDENT_FIXTURE constant instead."
        )


def test_provider_diagnosis_uses_otel_fixture_constant() -> None:
    """Provider diagnosis must use OTEL_INCIDENT_FIXTURE constant for fixture_name."""
    source_path = get_provider_diagnosis_path()
    source_code = source_path.read_text()

    # Check that fixture_name = OTEL_INCIDENT_FIXTURE (or similar usage)
    pattern = r'fixture_name\s*=\s*OTEL_INCIDENT_FIXTURE'
    assert re.search(pattern, source_code), (
        "provider_diagnosis.py must use 'fixture_name = OTEL_INCIDENT_FIXTURE'"
    )


def test_constants_otel_fixture_is_recommendation() -> None:
    """OTEL_INCIDENT_FIXTURE must be set to 'recommendation' for chart 0.40.9."""
    import sys
    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root / "scripts"))

    try:
        from k9b_otel_demo_lab_constants import OTEL_INCIDENT_FIXTURE
        assert OTEL_INCIDENT_FIXTURE == EXPECTED_FIXTURE, (
            f"OTEL_INCIDENT_FIXTURE must be '{EXPECTED_FIXTURE}' for chart 0.40.9, "
            f"got '{OTEL_INCIDENT_FIXTURE}'"
        )
    finally:
        sys.path.pop(0)


def test_constants_expected_component_matches_fixture() -> None:
    """EXPECTED_COMPONENT must equal OTEL_INCIDENT_FIXTURE."""
    import sys
    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root / "scripts"))

    try:
        from k9b_otel_demo_lab_constants import (
            EXPECTED_COMPONENT,
            OTEL_INCIDENT_FIXTURE,
        )
        assert EXPECTED_COMPONENT == OTEL_INCIDENT_FIXTURE, (
            f"EXPECTED_COMPONENT ({EXPECTED_COMPONENT}) must equal "
            f"OTEL_INCIDENT_FIXTURE ({OTEL_INCIDENT_FIXTURE})"
        )
    finally:
        sys.path.pop(0)


def test_required_deployments_uses_chart_0409_names() -> None:
    """REQUIRED_DEPLOYMENTS must use chart 0.40.9 naming, not stale names."""
    import sys
    repo_root = Path(__file__).parent.parent
    sys.path.insert(0, str(repo_root / "scripts"))

    try:
        from k9b_otel_demo_lab_constants import REQUIRED_DEPLOYMENTS

        # Must have "recommendation" (chart 0.40.9)
        assert "recommendation" in REQUIRED_DEPLOYMENTS, (
            "REQUIRED_DEPLOYMENTS must include 'recommendation'"
        )

        # Must NOT have "recommendationservice" (stale name)
        assert "recommendationservice" not in REQUIRED_DEPLOYMENTS, (
            "REQUIRED_DEPLOYMENTS must NOT include 'recommendationservice' (stale)"
        )
    finally:
        sys.path.pop(0)
