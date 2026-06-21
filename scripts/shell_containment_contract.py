"""Shell Containment Data Models.

Defines the core data structures for shell containment verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TypedDict


class Classification(StrEnum):
    SHIM = "shim"
    LEGACY_DEBT = "legacy-debt"
    BLOCKED = "blocked"


class MigrationStatus(StrEnum):
    REGISTERED = "registered"
    MIGRATED = "migrated"
    PENDING = "pending"
    DEFERRED = "deferred"
    DONE = "done"  # Alias for migrated, used for completed migrations


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class InventoryEntry:
    path: str
    classification: Classification
    owner: str
    reason: str
    target_language: str
    migration_status: MigrationStatus
    follow_up_act: str


@dataclass
class ShellScript:
    path: Path
    relative_path: str
    line_count: int
    detected_patterns: list[tuple[str, str, str]] = field(default_factory=list)
    is_complex: bool = False
    risk_score: int = 0
    risk_level: RiskLevel = RiskLevel.LOW


class FindingDict(TypedDict, total=False):
    path: str
    status: str
    line_count: int
    risk_level: str
    patterns: list[str]
    violations: list[str]
    risk_score: int
    classification: str
    migration_status: str
    owner: str


@dataclass
class VerificationResult:
    success: bool
    total_scripts: int
    registered_scripts: int
    unregistered_scripts: int
    complex_shims: int
    verify_all_violations: list[str] = field(default_factory=list)
    findings: list[FindingDict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
