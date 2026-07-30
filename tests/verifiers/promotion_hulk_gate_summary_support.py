"""Canonical gate-summary fixture helpers for promotion guards."""

from __future__ import annotations

import json
from pathlib import Path


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _minimal_passing_artifact() -> dict:
    return {
        "schema_version": 1,
        "profile": "act-local",
        "source_status": "present",
        "overall_status": "pass",
        "generated_at": "2026-07-29T17:00:00+00:00",
        "checks_total": 17,
        "checks_failed": 0,
        "checks": [
            {
                "name": name,
                "status": "pass",
                "duration_ms": 1,
                "error_message": None,
                "command": "echo",
                "exit_code": 0,
            }
            for name in (
                "canonical-verifier-self-test",
                "standalone-production-verifier",
                "production-mypy-positive",
                "production-mypy-negative",
                "full-gate-negative-proofs",
                "opaque-bearer-regression",
                "sanitizer-regression-matrix",
                "credential-matrix",
                "omission-boundary",
                "serializer-multi-return",
                "ruff",
                "mypy",
                "git-diff-check",
                "git-diff-cached-check",
                "llm-friendly",
                "no-new-llm-allowlist",
                "targeted-repository-gate",
            )
        ],
        "self_tests": {},
        "r10_definition_of_done": {},
        "extras": {
            "required_check_names": [
                "canonical-verifier-self-test",
                "standalone-production-verifier",
                "production-mypy-positive",
                "production-mypy-negative",
                "full-gate-negative-proofs",
                "opaque-bearer-regression",
                "sanitizer-regression-matrix",
                "credential-matrix",
                "omission-boundary",
                "serializer-multi-return",
                "ruff",
                "mypy",
                "git-diff-check",
                "git-diff-cached-check",
                "llm-friendly",
                "no-new-llm-allowlist",
                "targeted-repository-gate",
            ]
        },
    }
