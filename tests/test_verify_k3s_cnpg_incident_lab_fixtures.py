"""Shared fixtures and constants for K3s CNPG incident lab tests."""

from pathlib import Path

# Path to the verifier script.
VERIFIER_SCRIPT = Path(__file__).parent.parent / "scripts" / "verify_k3s_cnpg_incident_lab_artifact.py"

# Path to the sanitizer script.
SANITIZER_SCRIPT = Path(__file__).parent.parent / "scripts" / "sanitize_live_lab_artifacts.py"

# Path to fixture directories.
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "lab"
PASS_FIXTURE = FIXTURES_DIR / "pass"
FAIL_NO_INCIDENT_FIXTURE = FIXTURES_DIR / "fail-no-incident"
FAIL_SECRET_FIXTURE = FIXTURES_DIR / "fail-secret"
