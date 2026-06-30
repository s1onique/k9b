"""Data models for OTel demo lab contract verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OtelTracesMode(Enum):
    """OTel trace verification mode."""

    AUTO = "auto"
    REQUIRE = "require"
    SKIP = "skip"


@dataclass
class ContractCheck:
    """Result of a single contract check."""

    name: str
    passed: bool
    phase: str
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationReport:
    """Complete verification report."""

    passed: bool
    checks: list[ContractCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_check(self, check: ContractCheck) -> None:
        self.checks.append(check)
        if not check.passed:
            self.passed = False

    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.passed = False

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)
