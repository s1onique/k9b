#!/usr/bin/env python3
"""
ACT-local check for incident diagnosis API/service one-pass wiring.

This script exercises the API/service seam with the pod-failure golden case
using fake stores, fake providers, and fake read-only handlers.

Exit codes:
    0 - Check passed (golden case diagnosis matches expected)
    1 - Check failed (diagnosis mismatch, safety violation, etc.)
    2 - Invalid arguments or missing fixtures
    3 - Prerequisites failed (privacy, provenance) OR verifier scripts missing
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

# Add src to path for imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from k8s_diag_agent.collect.golden_case_evidence_provider import (
    GoldenCaseEvidenceProvider,
)
from k8s_diag_agent.collect.golden_case_fake_handlers import (
    create_golden_case_fake_handlers,
)
from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
    GoldenCaseDeterministicLLMProvider,
)
from k8s_diag_agent.collect.incident_diagnosis_service import (
    IncidentOnePassServiceRequest,
    run_incident_one_pass_diagnosis,
)
from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store


def run_verifier_script(script_path: Path, case_dir: Path) -> tuple[bool, str]:
    """Run a verifier script and return (success, error_message)."""
    try:
        script_name = script_path.name
        if "privacy" in script_name:
            cmd = [sys.executable, str(script_path), str(case_dir)]
        else:
            cmd = [sys.executable, str(script_path), "--case-dir", str(case_dir)]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return False, f"{script_path.name} failed: {result.stderr or result.stdout}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"{script_path.name} timed out"
    except Exception as e:
        return False, f"{script_path.name} error: {e}"


def run_golden_case_verifier(
    diagnosis_path: Path,
    expected_path: Path,
) -> tuple[bool, list[str]]:
    """Run the golden-case diagnosis verifier.

    Args:
        diagnosis_path: Path to diagnosis.json output
        expected_path: Path to expected.json

    Returns:
        Tuple of (success, list of failure messages)
    """
    try:
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "verify_diagnosis_golden_case.py"),
            "--expected", str(expected_path),
            "--diagnosis", str(diagnosis_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            # Parse failures from output
            failures = []
            for line in result.stdout.splitlines():
                if line.strip().startswith("FAIL"):
                    failures.append(line.strip())
            if not failures:
                failures = [result.stderr or result.stdout]
            return False, failures
        return True, []
    except subprocess.TimeoutExpired:
        return False, ["Golden-case verifier timed out"]
    except Exception as e:
        return False, [f"Golden-case verifier error: {e}"]


def main() -> int:
    print("=" * 60)
    print("ACT-LOCAL: Incident API/Service One-Pass Diagnosis Check")
    print("=" * 60)
    print()

    # Locate golden case fixture
    case_dir = REPO_ROOT / "fixtures" / "diagnosis-golden-cases" / "pod-failure-readiness"
    if not case_dir.exists():
        print(f"ERROR: Golden case fixture not found: {case_dir}", file=sys.stderr)
        return 2

    manifest_path = case_dir / "manifest.json"
    expected_path = case_dir / "expected.json"

    if not manifest_path.exists():
        print(f"ERROR: Manifest not found: {manifest_path}", file=sys.stderr)
        return 2
    if not expected_path.exists():
        print(f"ERROR: Expected not found: {expected_path}", file=sys.stderr)
        return 2

    with open(manifest_path) as f:
        manifest = json.load(f)
    with open(expected_path) as f:
        expected = json.load(f)

    print(f"Golden Case: {manifest.get('case_id')}")
    print(f"Scenario: {manifest.get('scenario')}")
    print()

    # Run prerequisite verifiers - FAIL CLOSED if scripts missing
    print("Running prerequisite verifiers (fail-closed)...")
    scripts_dir = REPO_ROOT / "scripts"

    privacy_script = scripts_dir / "verify_diagnosis_golden_case_privacy.py"
    if not privacy_script.exists():
        print(f"ERROR: Privacy verifier script not found: {privacy_script}", file=sys.stderr)
        print("This is a fail-closed check - missing verifiers are not acceptable.", file=sys.stderr)
        return 3
    privacy_valid, privacy_error = run_verifier_script(privacy_script, case_dir)
    if not privacy_valid:
        print(f"ERROR: Privacy verification failed: {privacy_error}", file=sys.stderr)
        return 3
    print("  - Privacy verification: PASS")

    provenance_script = scripts_dir / "verify_provenance_golden_case.py"
    if not provenance_script.exists():
        print(f"ERROR: Provenance verifier script not found: {provenance_script}", file=sys.stderr)
        print("This is a fail-closed check - missing verifiers are not acceptable.", file=sys.stderr)
        return 3
    provenance_valid, provenance_error = run_verifier_script(provenance_script, case_dir)
    if not provenance_valid:
        print(f"ERROR: Provenance verification failed: {provenance_error}", file=sys.stderr)
        return 3
    print("  - Provenance verification: PASS")

    print()

    # Create evidence provider
    evidence_provider = GoldenCaseEvidenceProvider(case_dir)

    # Create incident matching golden case
    print("Setting up incident store with golden-case incident...")
    store = IncidentStore()
    now = datetime.now(UTC)
    incident = Incident(
        incident_id=manifest["case_id"],
        source_candidate_id=manifest["case_id"],
        namespace=manifest["fixture_namespace"],
        object_kind="Pod",
        object_name=manifest["fixture_name"],
        raw_object_kind="Pod",
        candidate_class="readiness_probe_failure",
        severity="medium",
        status=IncidentStatus.OPEN,
        first_observed_at=now,
        last_observed_at=now,
    )
    store._incidents[manifest["case_id"]] = incident
    set_incident_store(store)
    print(f"  - Incident created: {incident.incident_id}")
    print()

    # Create fake providers
    fake_handlers = create_golden_case_fake_handlers(evidence_provider)
    llm_provider = GoldenCaseDeterministicLLMProvider(
        manifest=manifest,
        expected=expected,
        evidence_provider=evidence_provider,
    )

    print("Providers configured:")
    print("  - LLM Provider: GoldenCaseDeterministicLLMProvider")
    print(f"  - Fake Handlers: {len(fake_handlers)} handlers")
    print()

    # Run diagnosis through service seam with golden-case mode enabled
    print("Running diagnosis through service/API seam (golden-case mode)...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Enable golden_case_mode for the service request
        request = IncidentOnePassServiceRequest(
            incident_id=manifest["case_id"],
            external_analysis_dir=temp_path,
            diagnosis_provider=llm_provider,
            fake_handlers=fake_handlers,
            now=now,
            golden_case_mode=True,  # Enable golden-case enforcement
            golden_case_manifest=manifest,  # Required for golden-case case file builder
            golden_case_case_dir=case_dir,  # Required for golden-case case file builder
            golden_case_evidence_provider=evidence_provider,  # Required for golden-case case file builder
            enforce_fake_handlers=True,  # Require checks_run > 0
            use_live_command_guard=True,  # Block live-command fallback
        )

        result = run_incident_one_pass_diagnosis(request)

        print()
        print("Diagnosis Result:")
        print(f"  - Incident ID: {result.incident_id}")
        print(f"  - Run ID: {result.run_id}")
        print(f"  - Error: {result.error}")
        print(f"  - Read-only: {result.read_only}")
        print(f"  - Allowed Actions: {result.allowed_actions}")
        print(f"  - Checks Run: {result.checks_run}")
        print(f"  - Category: {result.category}")
        print(f"  - Root Cause: {result.root_cause}")
        print(f"  - Confidence: {result.confidence}")
        print(f"  - Artifact Written: {result.artifact_written}")
        print(f"  - Handler Invocations: {len(result.handler_invocations)}")
        print()

        # Collect all errors
        errors: list[str] = []

        # Check for errors
        if result.error is not None:
            errors.append(f"Diagnosis failed: {result.error}")

        # Check safety contract
        if not result.read_only:
            errors.append("Safety violation: read_only must be True")

        if result.allowed_actions != []:
            errors.append("Safety violation: allowed_actions must be []")

        if result.mutation_proposals_observed != []:
            errors.append(f"Safety violation: mutation_proposals_observed must be []: {result.mutation_proposals_observed}")

        if result.forbidden_actions_observed != []:
            errors.append(f"Safety violation: forbidden_actions_observed must be []: {result.forbidden_actions_observed}")

        # Check diagnosis content - root cause should match expected
        expected_root_cause = manifest.get("expected_root_cause", "")
        if expected_root_cause and expected_root_cause.lower() not in result.root_cause.lower():
            errors.append(f"Root cause mismatch: got {result.root_cause!r}, expected to contain {expected_root_cause!r}")

        # Check that checks_run > 0 (proves fake handlers are exercised)
        if result.checks_run <= 0:
            errors.append(
                f"Fake-handler enforcement failed: checks_run={result.checks_run}. "
                "The ACT-local proof path requires checks_run > 0 to prove "
                "fake handlers are actually exercised."
            )

        # Check that handler invocations are recorded
        if not result.handler_invocations:
            errors.append(
                "Fake-handler enforcement failed: handler_invocations is empty. "
                "When checks are run, the orchestrator must record handler invocations."
            )

        # Verify all invocations have required flags
        for invocation in result.handler_invocations:
            if not invocation.get("golden_case_handler"):
                errors.append(
                    f"Fake-handler enforcement failed: check_id={invocation.get('check_id')} "
                    "has golden_case_handler=false (expected true)."
                )
            if not invocation.get("no_kubernetes_call"):
                errors.append(
                    f"Fake-handler enforcement failed: check_id={invocation.get('check_id')} "
                    "has no_kubernetes_call=false (expected true)."
                )

        # Verify no unknown check IDs
        known_handler_ids = set(fake_handlers.keys())
        for invocation in result.handler_invocations:
            check_id = invocation.get("check_id", "")
            if check_id not in known_handler_ids:
                errors.append(
                    f"Fake-handler enforcement failed: unknown check_id='{check_id}'. "
                    "Only golden-case fake handlers are allowed."
                )

        # Run the golden-case verifier on the diagnosis output
        print("Running golden-case diagnosis verifier...")
        diagnosis_dto = result.to_dict()
        diagnosis_path = temp_path / "diagnosis.json"
        with open(diagnosis_path, "w", encoding="utf-8") as f:
            json.dump(diagnosis_dto, f, indent=2)

        verifier_passed, verifier_failures = run_golden_case_verifier(diagnosis_path, expected_path)
        if not verifier_passed:
            errors.extend(verifier_failures)
            print("  - Golden-case verifier: FAIL")
        else:
            print("  - Golden-case verifier: PASS")

        print()

        # Report results
        if errors:
            print("ERRORS:")
            for error in errors:
                print(f"  - {error}")
            print()
            print("ACT-LOCAL CHECK: FAIL")
            return 1

    print("All checks passed!")
    print()
    print("ACT-LOCAL CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
