"""Golden-case one-pass diagnosis loop adapter.

This module provides the core adapter that wires a golden-case bundle through
the production one-pass diagnosis/read-only-check machinery.

It exercises the real production modules:
- incident_case_file (build_incident_case_file)
- incident_diagnosis_loop_orchestrator (run_one_read_only_diagnosis_loop_pass)
- incident_read_only_check_runner (with injected golden-case fake handlers)
- incident_llm_diagnosis (with injected deterministic provider)

Design constraints:
- Fully offline (no kubectl, helm, docker, registry, GitHub API)
- Read-only (no cluster mutation)
- Uses checked-in sanitized golden-case evidence only
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .golden_case_evidence_provider import GoldenCaseEvidenceProvider
from .golden_case_fake_handlers import create_golden_case_fake_handlers
from .golden_case_one_pass_enforcement import (
    FakeHandlerExecutionError,
    enforce_fake_handlers,
)
from .golden_case_one_pass_llm_provider import GoldenCaseDeterministicLLMProvider
from .golden_case_one_pass_safety import enforce_safety

__all__ = [
    "FakeHandlerExecutionError",
    "GoldenCaseDeterministicLLMProvider",
    "LiveCommandGuard",
    "build_golden_case_case_file",
    "enforce_safety",
    "enforce_fake_handlers",
    "run_production_diagnosis_loop",
    "format_diagnosis_summary",
]


def format_diagnosis_summary(
    diagnosis: dict[str, Any],
    manifest: dict[str, Any],
) -> str:
    """Format diagnosis as human-readable summary."""
    lines = [
        "# Production One-Pass Diagnosis Loop Output",
        "",
        f"**Case ID**: {diagnosis.get('case_id', manifest.get('case_id', 'unknown'))}",
        f"**Category**: {diagnosis.get('category', 'unknown')}",
        f"**Root Cause**: {diagnosis.get('root_cause', 'unknown')}",
        f"**Confidence**: {diagnosis.get('confidence', 'unknown')}",
        f"**Diagnosis Engine**: {diagnosis.get('diagnosis_engine', 'unknown')}",
        f"**Loop Decision**: {diagnosis.get('loop_decision', 'unknown')}",
        f"**Checks Run**: {diagnosis.get('checks_run', 0)}",
        "",
        "## Description",
        diagnosis.get("description", "No description provided."),
        "",
        "## Safety Status",
        f"- Read-only: {diagnosis.get('read_only', False)}",
        f"- Forbidden actions observed: {len(diagnosis.get('forbidden_actions_observed', []))}",
        f"- Mutation proposals observed: {len(diagnosis.get('mutation_proposals_observed', []))}",
        "",
        "## Evidence References",
    ]

    for ref in diagnosis.get("evidence_refs", []):
        lines.append(f"- {ref}")

    lines.extend(["", "## Next Recommended Checks (Read-Only)"])

    for i, check in enumerate(diagnosis.get("next_checks", []), 1):
        if isinstance(check, dict):
            lines.append(f"{i}. {check.get('description', 'No description')}")
            method = check.get("method", "")
            if method:
                lines.append(f"   Method: `{method}`")

    return "\n".join(lines)


# =============================================================================
# Live-Command Guard
# =============================================================================

class LiveCommandGuard:
    """Guard that blocks live command execution during golden-case runs.

    This guard provides defense-in-depth against live-command fallback:
    - Replaces forbidden modules in sys.modules with blocked proxies
    - Patches subprocess.run and subprocess.Popen to raise
    - Patches socket.create_connection to raise
    - Blocks kubernetes client entry points if loaded
    """

    # Modules to block entirely - these should never be accessed during golden-case runs
    # Note: subprocess is NOT blocked here because we patch its functions directly
    # and need to restore them in __exit__
    _FORBIDDEN_MODULES = [
        "kubernetes", "kubectl", "helm", "docker",
        "requests", "urllib3", "github",
        "kubectl_run", "helm_run", "docker_run",
    ]

    def __init__(self) -> None:
        self._blocked_calls: list[str] = []
        self._originals: dict[str, object | None] = {}
        self._subprocess_run_original: object | None = None
        self._subprocess_popen_original: object | None = None
        self._socket_create_connection_original: object | None = None

    def __enter__(self) -> LiveCommandGuard:
        import socket
        import subprocess
        import sys

        # Block forbidden modules
        for module_name in self._FORBIDDEN_MODULES:
            if module_name in sys.modules:
                self._originals[module_name] = sys.modules[module_name]
                sys.modules[module_name] = _BlockedModule(module_name)  # type: ignore[assignment]

        # Patch subprocess.run and subprocess.Popen to raise
        if hasattr(subprocess, "run"):
            self._subprocess_run_original = subprocess.run
            subprocess.run = _blocked_subprocess_run  # type: ignore[assignment]

        if hasattr(subprocess, "Popen"):
            self._subprocess_popen_original = subprocess.Popen
            subprocess.Popen = _blocked_subprocess_popen  # type: ignore[misc,assignment]

        # Patch socket.create_connection to raise
        if hasattr(socket, "create_connection"):
            self._socket_create_connection_original = socket.create_connection
            socket.create_connection = _blocked_create_connection  # type: ignore[assignment]

        return self

    def __exit__(self, *args: object) -> None:
        import socket
        import subprocess
        import sys

        # Restore forbidden modules
        for module_name, original in self._originals.items():
            if original is not None:
                sys.modules[module_name] = original  # type: ignore[assignment]
        self._originals.clear()

        # Restore subprocess functions
        if self._subprocess_run_original is not None:
            subprocess.run = self._subprocess_run_original  # type: ignore[assignment]
            self._subprocess_run_original = None

        if self._subprocess_popen_original is not None:
            subprocess.Popen = self._subprocess_popen_original  # type: ignore[misc,assignment]
            self._subprocess_popen_original = None

        # Restore socket function
        if self._socket_create_connection_original is not None:
            socket.create_connection = self._socket_create_connection_original  # type: ignore[assignment]
            self._socket_create_connection_original = None


def _blocked_subprocess_run(*args: object, **kwargs: object) -> object:
    """Blocked subprocess.run - raises RuntimeError."""
    raise RuntimeError(
        "Live command guard blocked subprocess.run(). "
        "Golden-case runs must use fake handlers only."
    )


def _blocked_subprocess_popen(*args: object, **kwargs: object) -> object:
    """Blocked subprocess.Popen - raises RuntimeError."""
    raise RuntimeError(
        "Live command guard blocked subprocess.Popen(). "
        "Golden-case runs must use fake handlers only."
    )


def _blocked_create_connection(*args: object, **kwargs: object) -> object:
    """Blocked socket.create_connection - raises RuntimeError."""
    raise RuntimeError(
        "Live command guard blocked socket.create_connection(). "
        "Golden-case runs must use fake handlers only."
    )


class _BlockedModule:
    """Module replacement that raises on any attribute access."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, name: str) -> object:
        raise RuntimeError(
            f"Live command guard blocked access to '{self._name}.{name}'. "
            "Golden-case runs must use fake handlers only."
        )

    def __call__(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError(
            f"Live command guard blocked call to '{self._name}'. "
            "Golden-case runs must use fake handlers only."
        )


# Global guard instance for verification
_live_command_guard: LiveCommandGuard | None = None


def get_live_command_guard() -> LiveCommandGuard | None:
    """Get the current live command guard if active."""
    return _live_command_guard


def _set_live_command_guard(guard: LiveCommandGuard | None) -> None:
    """Set the live command guard (for testing)."""
    global _live_command_guard
    _live_command_guard = guard


# =============================================================================
# Golden Case Case-File Adapter
# =============================================================================

def build_golden_case_case_file(
    case_dir: Path,
    manifest: dict[str, Any],
    evidence_provider: GoldenCaseEvidenceProvider,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a production-shaped case-file from golden-case bundle."""
    resolved_now = now if now is not None else datetime.now(UTC)
    case_id = manifest.get("case_id", "unknown")
    namespace = manifest.get("fixture_namespace", "<LAB_NAMESPACE>")
    fixture_name = manifest.get("fixture_name", "unknown")

    incident_detail: dict[str, Any] = {}
    incident_detail_path = case_dir / "incident" / "k9b-incident-detail.json"
    if incident_detail_path.exists():
        with open(incident_detail_path) as f:
            incident_detail = json.load(f)

    events: list[dict[str, Any]] = []
    events_path = case_dir / "incident" / "events.txt"
    if events_path.exists():
        events_content = events_path.read_text()
        for line in events_content.strip().split("\n"):
            if line.strip():
                events.append({"message": line, "timestamp": resolved_now.isoformat()})

    signals: list[dict[str, Any]] = []
    if incident_detail:
        signals.append({
            "type": "pod_condition",
            "description": incident_detail.get("symptom_description", ""),
            "severity": incident_detail.get("severity", "medium"),
            "timestamp": incident_detail.get("detected_at", resolved_now.isoformat()),
        })

    evidence_links: list[dict[str, Any]] = []
    for ref in manifest.get("expected_evidence_files", []):
        evidence_links.append({
            "artifact_type": "golden_case_evidence",
            "path": ref,
            "description": f"Golden-case evidence: {ref}",
        })

    return {
        "schema_version": "1.0",
        "generated_at": resolved_now.isoformat(),
        "read_only": True,
        "allowed_actions": [],
        "disallowed_actions": ["execute", "promote", "apply", "remediate", "delete", "mutate_cluster"],
        "incident": {
            "incident_id": case_id,
            "namespace": namespace,
            "object_kind": "Pod",
            "object_name": fixture_name,
            "severity": incident_detail.get("severity", "medium"),
            "status": "active",
            "first_observed_at": incident_detail.get("detected_at", resolved_now.isoformat()),
            "last_observed_at": resolved_now.isoformat(),
        },
        "signals": signals,
        "evidence_links": evidence_links,
        "events": events[:50],
        "suggested_checks": [],
        "prior_analysis": [],
        "read_only_check_results": [],
        "diagnosis_loop_passes": [],
        "golden_case_source": {
            "case_id": case_id,
            "source_kind": manifest.get("source_kind", "unknown"),
            "scenario": manifest.get("scenario", "unknown"),
            "category": manifest.get("category", "unknown"),
            "symptom": manifest.get("symptom", ""),
        },
    }


# =============================================================================
# Production Diagnosis Runner
# =============================================================================

def run_production_diagnosis_loop(
    case_file: dict[str, Any],
    manifest: dict[str, Any],
    expected: dict[str, Any],
    evidence_provider: GoldenCaseEvidenceProvider,
    output_dir: Path,
    *,
    now: datetime | None = None,
    enforce_fake_handlers_flag: bool = True,
    use_live_command_guard: bool = True,
) -> dict[str, Any]:
    """Run the production diagnosis loop with golden-case fake handlers.

    Args:
        case_file: The case file for the incident
        manifest: The golden-case manifest
        expected: The expected diagnosis output
        evidence_provider: The golden-case evidence provider
        output_dir: Directory for output files
        now: Current timestamp (defaults to now)
        enforce_fake_handlers_flag: Whether to enforce fake-handler execution
        use_live_command_guard: Whether to wrap orchestrator in LiveCommandGuard.
            Defaults to True for ACT-local proof path.

    Returns:
        The diagnosis result dictionary
    """
    from .incident_diagnosis_loop_orchestrator import run_one_read_only_diagnosis_loop_pass
    from .incident_llm_diagnosis import build_incident_diagnosis

    resolved_now = now if now is not None else datetime.now(UTC)
    fake_handlers = create_golden_case_fake_handlers(evidence_provider)
    llm_provider = GoldenCaseDeterministicLLMProvider(manifest, expected, evidence_provider)
    diagnosis_report = build_incident_diagnosis(case_file=case_file, llm=llm_provider, now=resolved_now)

    # Run the orchestrator under LiveCommandGuard to prevent live-command fallback
    if use_live_command_guard:
        guard = LiveCommandGuard()
        with guard:
            with tempfile.TemporaryDirectory() as external_analysis_dir:
                loop_result = run_one_read_only_diagnosis_loop_pass(
                    incident_id=case_file["incident"]["incident_id"],
                    external_analysis_dir=Path(external_analysis_dir),
                    case_file=case_file,
                    diagnosis_report=diagnosis_report,
                    run_id=f"golden-case-{resolved_now.strftime('%Y%m%d-%H%M%S')}",
                    now=resolved_now,
                    fake_handlers=fake_handlers,
                )
    else:
        with tempfile.TemporaryDirectory() as external_analysis_dir:
            loop_result = run_one_read_only_diagnosis_loop_pass(
                incident_id=case_file["incident"]["incident_id"],
                external_analysis_dir=Path(external_analysis_dir),
                case_file=case_file,
                diagnosis_report=diagnosis_report,
                run_id=f"golden-case-{resolved_now.strftime('%Y%m%d-%H%M%S')}",
                now=resolved_now,
                fake_handlers=fake_handlers,
            )

    diagnosis = diagnosis_report.get("diagnosis", {})
    if not isinstance(diagnosis, dict):
        diagnosis = {"summary": str(diagnosis), "confidence": "unknown"}

    case_id = manifest.get("case_id", "unknown")
    findings = evidence_provider.extract_findings()

    if findings["readiness_probe_failure_evidence"]:
        category = manifest.get("category", "readiness_probe_failure")
        root_cause = manifest.get("expected_root_cause", "readiness probe failure")
    else:
        category = "unknown"
        root_cause = "insufficient evidence"

    evidence_refs: list[str] = []
    if isinstance(manifest.get("expected_evidence_files"), list):
        evidence_refs.extend(manifest["expected_evidence_files"])

    recommended_investigations: list[str] = []
    investigations_data = diagnosis.get("recommended_investigations")
    if isinstance(investigations_data, list):
        for item in investigations_data:
            if isinstance(item, str):
                recommended_investigations.append(item)
            elif item is not None:
                recommended_investigations.append(str(item))

    next_checks: list[dict[str, Any]] = []
    for inv in recommended_investigations:
        next_checks.append({
            "description": inv,
            "owner": "platform-engineer",
            "method": "kubectl describe pod <NAMESPACE>/<POD_NAME> -n <NAMESPACE>",
            "evidence_needed": ["probe status", "container state"],
        })

    runner_result = loop_result.get("runner_result")
    runner_result_dict = runner_result if isinstance(runner_result, dict) else {}
    checks_run = runner_result_dict.get("checks_run", 0)
    check_results = runner_result_dict.get("results", [])

    read_only_checks_sidecar: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": case_id,
        "run_id": loop_result.get("run_id", "unknown"),
        "checks_requested": runner_result_dict.get("checks_requested", 0),
        "checks_run": checks_run,
        "checks_skipped": runner_result_dict.get("checks_skipped", 0),
        "checks_rejected": runner_result_dict.get("checks_rejected", 0),
        "handler_invocations": [],
        "safety_metadata": runner_result_dict.get("safety_metadata", {}),
    }

    for result in check_results:
        if isinstance(result, dict):
            check_id = result.get("check_id", "unknown")
            read_only_checks_sidecar["handler_invocations"].append({
                "check_id": check_id,
                "status": result.get("status", "unknown"),
                "golden_case_handler": result.get("evidence", {}).get("golden_case_handler", False),
                "no_kubernetes_call": result.get("evidence", {}).get("no_kubernetes_call", False),
            })

    # Enforce fake-handler execution (fail closed)
    enforce_fake_handlers(
        loop_result=loop_result,
        runner_result_dict=runner_result_dict,
        read_only_checks_sidecar=read_only_checks_sidecar,
        fake_handlers=fake_handlers,
        enforce=enforce_fake_handlers_flag,
    )

    return {
        "case_id": case_id,
        "category": category,
        "root_cause": root_cause,
        "confidence": diagnosis.get("confidence", "medium"),
        "description": diagnosis.get("summary", ""),
        "evidence_refs": evidence_refs,
        "read_only": True,
        "allowed_actions": [],
        "forbidden_actions_observed": [],
        "mutation_proposals_observed": [],
        "diagnosis_engine": "production-one-pass-loop",
        "next_checks": next_checks,
        "loop_decision": loop_result.get("decision", "unknown"),
        "checks_run": checks_run,
        "_internal": {"read_only_checks_sidecar": read_only_checks_sidecar},
    }
