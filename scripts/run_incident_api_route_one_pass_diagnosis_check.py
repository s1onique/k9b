#!/usr/bin/env python3
"""ACT-local check for incident API route one-pass diagnosis wiring.

This script exercises the HTTP API route handler (handle_incident_one_pass_diagnosis_service_api)
for the incident diagnosis service using the pod-failure golden case with
fake stores, fake providers, and fake read-only handlers.

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
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

# Add src to path for imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from k8s_diag_agent.collect.api_incident_one_pass_diagnosis_provider import (
    reset_providers,
    set_artifact_writer,
    set_diagnosis_provider,
    set_fake_handlers,
    set_golden_case_context,
)
from k8s_diag_agent.collect.golden_case_evidence_provider import (
    GoldenCaseEvidenceProvider,
)
from k8s_diag_agent.collect.golden_case_fake_handlers import (
    create_golden_case_fake_handlers,
)
from k8s_diag_agent.collect.golden_case_one_pass_diagnosis_loop import (
    GoldenCaseDeterministicLLMProvider,
)
from k8s_diag_agent.collect.incident_lifecycle import Incident, IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store


class FakeHTTPHandler:
    """Fake HTTP request handler for testing server handlers without a real HTTP server.

    This class mocks the BaseHTTPRequestHandler interface used by HealthUIRequestHandler,
    specifically the attributes and methods used by handle_incident_one_pass_diagnosis_service_api().
    """

    def __init__(
        self,
        path: str,
        body: bytes | None = None,
        health_root: Path | None = None,
    ) -> None:
        self.path = path
        self._health_root = health_root or Path(tempfile.gettempdir())
        self._response_status: int = 200
        self._response_headers: dict[str, str] = {}
        self._response_body: bytes = b""

        # Setup request body as BytesIO
        self.rfile = BytesIO(body or b"")

        # Setup response capture
        self._response_buffer = BytesIO()

        # Mock headers dict
        self._headers: dict[str, str] = {}
        if body is not None:
            self._headers["Content-Length"] = str(len(body))

        # Required by BaseHTTPRequestHandler for send_response/send_header
        self.wfile = self._response_buffer

    @property
    def headers(self) -> dict[str, str]:
        """Return headers dict for handler code."""
        return self._headers

    def send_response(self, code: int) -> None:
        """Capture response status code."""
        self._response_status = code

    def send_header(self, key: str, value: str) -> None:
        """Capture response headers."""
        self._headers[key] = value

    def end_headers(self) -> None:
        """No-op for fake handler."""
        pass

    def get_response(self) -> tuple[int, dict[str, str], bytes]:
        """Get captured response data.

        Returns:
            Tuple of (status_code, headers, body_bytes)
        """
        return self._response_status, dict(self._headers), self._response_body

    def get_response_json(self) -> dict[str, Any]:
        """Get captured response body as JSON dict.

        Returns:
            Parsed JSON from response body

        Raises:
            json.JSONDecodeError: If response is not valid JSON
        """
        return json.loads(self._response_body.decode("utf-8"))  # type: ignore[no-any-return]


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
    print("ACT-LOCAL: Incident API Route One-Pass Diagnosis Check")
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

    # Build request body for the HTTP handler
    request_body = json.dumps({
        "incident_id": manifest["case_id"],
        "run_id": "act-local-check-001",
    }).encode("utf-8")

    try:
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

        # Inject providers via the provider registry (as the server handler does)
        # This proves the server handler retrieves providers from the registry
        set_diagnosis_provider(llm_provider)
        set_fake_handlers(fake_handlers)
        set_artifact_writer(None)

        # Set golden-case context for ACT-local verification
        # The server handler retrieves this via is_golden_case_mode() and related getters
        set_golden_case_context(
            enabled=True,
            manifest=manifest,
            case_dir=case_dir,
            evidence_provider=evidence_provider,
        )

        # Preflight: Test mismatch rejection (cheap route-contract test)
        print("Preflight: Testing URL/body mismatch rejection...")

        from k8s_diag_agent.ui.server_incident_one_pass_diagnosis_service import (
            handle_incident_one_pass_diagnosis_service_api,
        )

        mismatch_body = json.dumps({
            "incident_id": "wrong-incident",
            "run_id": "preflight-check",
        }).encode("utf-8")

        mismatch_handler = FakeHTTPHandler(
            path="/api/incidents/correct-incident/one-pass-diagnosis",
            body=mismatch_body,
            health_root=Path(tempfile.gettempdir()),
        )

        handle_incident_one_pass_diagnosis_service_api(
            handler=mismatch_handler,
            incident_id="correct-incident",
        )

        mismatch_status, _, mismatch_body_bytes = (
            mismatch_handler._response_status,
            mismatch_handler._headers,
            mismatch_handler._response_buffer.getvalue(),
        )

        if mismatch_status != 400:
            print(f"  ERROR: Mismatch should return 400, got {mismatch_status}", file=sys.stderr)
            return 1

        mismatch_response = json.loads(mismatch_body_bytes.decode("utf-8"))
        if "match" not in mismatch_response.get("error", "").lower():
            print(f"  ERROR: Mismatch error should mention 'match', got: {mismatch_response.get('error')}", file=sys.stderr)
            return 1

        print("  - Mismatch rejection: PASS (400 returned)")
        print()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            health_root = temp_path / "health"
            health_root.mkdir(parents=True, exist_ok=True)

            # Run diagnosis through HTTP server handler seam
            # This exercises: handle_incident_one_pass_diagnosis_service_api() ->
            #   handler.headers / handler.rfile -> provider registry -> handle_one_pass_diagnosis_service()
            print("Running diagnosis through HTTP server handler seam...")

            # Create fake HTTP handler with request data
            fake_handler = FakeHTTPHandler(
                path=f"/api/incidents/{manifest['case_id']}/one-pass-diagnosis",
                body=request_body,
                health_root=health_root,
            )

            # Import and call the actual server handler
            from k8s_diag_agent.ui.server_incident_one_pass_diagnosis_service import (
                handle_incident_one_pass_diagnosis_service_api,
            )

            handle_incident_one_pass_diagnosis_service_api(
                handler=fake_handler,
                incident_id=manifest["case_id"],
            )

            # Get the response that was written to the handler
            status, headers, body_bytes = fake_handler._response_status, fake_handler._headers, fake_handler._response_buffer.getvalue()

            print()
            print("HTTP Handler Response:")
            print(f"  - Status: {status}")
            print(f"  - Content-Type: {headers.get('Content-Type', 'N/A')}")

            # Parse response body
            try:
                response = json.loads(body_bytes.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                print(f"  - Body Parse Error: {exc}")
                response = {"error": f"Failed to parse response: {exc}"}

            print(f"  - Schema Version: {response.get('schema_version')}")
            print(f"  - Incident ID: {response.get('incident_id')}")
            print(f"  - Run ID: {response.get('run_id')}")
            print(f"  - Error: {response.get('error')}")
            print(f"  - Read-only: {response.get('read_only')}")
            print(f"  - Allowed Actions: {response.get('allowed_actions')}")
            print(f"  - Checks Run: {response.get('checks_run')}")
            print(f"  - Category: {response.get('category')}")
            print(f"  - Root Cause: {response.get('root_cause')}")
            print(f"  - Confidence: {response.get('confidence')}")
            print(f"  - Artifact Written: {response.get('artifact_written')}")
            print()

            # Collect all errors
            errors: list[str] = []

            # Check HTTP response
            if status != 200:
                errors.append(f"HTTP response status should be 200, got {status}")

            # Check for errors in response
            if response.get("error") is not None:
                errors.append(f"Diagnosis failed: {response.get('error')}")

            # Check safety contract
            if not response.get("read_only", True):
                errors.append("Safety violation: read_only must be True")

            if response.get("allowed_actions") != []:
                errors.append("Safety violation: allowed_actions must be []")

            if response.get("mutation_proposals_observed") != []:
                errors.append(f"Safety violation: mutation_proposals_observed must be []: {response.get('mutation_proposals_observed')}")

            if response.get("forbidden_actions_observed") != []:
                errors.append(f"Safety violation: forbidden_actions_observed must be []: {response.get('forbidden_actions_observed')}")

            # Check diagnosis content - root cause should match expected
            expected_root_cause = manifest.get("expected_root_cause", "")
            root_cause = response.get("root_cause", "")
            if expected_root_cause and expected_root_cause.lower() not in root_cause.lower():
                errors.append(f"Root cause mismatch: got {root_cause!r}, expected to contain {expected_root_cause!r}")

            # Check that checks_run > 0 (proves fake handlers are exercised)
            if response.get("checks_run", 0) <= 0:
                errors.append(
                    f"Fake-handler enforcement failed: checks_run={response.get('checks_run')}. "
                    "The ACT-local proof path requires checks_run > 0 to prove "
                    "fake handlers are actually exercised."
                )

            # Run the golden-case verifier on the diagnosis output
            print("Running golden-case diagnosis verifier...")
            diagnosis_path = temp_path / "diagnosis.json"
            with open(diagnosis_path, "w", encoding="utf-8") as f:
                json.dump(response, f, indent=2)

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
    finally:
        # Always reset provider registry, even on exception
        reset_providers()

    print()
    print("Proving HTTP/API route wiring to service seam...")
    print("  - HTTP Handler: FakeHTTPHandler exercises BaseHTTPRequestHandler interface")
    print("  - Server Handler: handle_incident_one_pass_diagnosis_service_api() parses headers/rfile")
    print("  - Provider Registry: handler retrieves providers via get_*_provider()")
    print("  - Service Layer: handle_one_pass_diagnosis_service() wires to run_incident_one_pass_diagnosis()")
    print("  - Golden-case verifier: PASS")
    print()
    print("ACT-LOCAL CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
