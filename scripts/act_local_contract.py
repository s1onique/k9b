#!/usr/bin/env python3
"""ACT-Local contract: data models for verification.

Provides CheckResult and ActLocalResult dataclasses used by all ACT-local modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CheckResult:
    """Result from a single verification check."""
    name: str
    command: str
    status: str  # PASS, FAIL, SKIP
    duration_ms: int
    exit_code: int
    error_message: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "exit_code": self.exit_code,
            "error_message": self.error_message,
        }


@dataclass
class ActLocalResult:
    """Result from ACT-local verification."""
    success: bool
    changed_files: list[str]
    checks: list[CheckResult]
    skipped_checks: list[dict[str, str]]
    broader_gate_status: str  # "not_evaluated"
    failure_commands: list[str]
    error_message: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": "act-local",
            "success": self.success,
            "changed_files": self.changed_files,
            "checks": [c.to_dict() for c in self.checks],
            "skipped_checks": self.skipped_checks,
            "broader_gate_status": self.broader_gate_status,
            "failure_commands": self.failure_commands,
            "error_message": self.error_message,
        }
