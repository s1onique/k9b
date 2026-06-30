"""Persistent runtime state for the diagnosis loop.

This module provides the LoopRuntimeState dataclass that maintains state
across multiple diagnosis loop passes for:
- Check fingerprint tracking (duplicate detection)
- Pass indices and counts
- Model call and evidence hash tracking
- Budget limit enforcement across the entire loop
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Schema version for runtime state
RUNTIME_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class LoopRuntimeState:
    """Persistent state across multiple diagnosis loop passes.
    
    This state is maintained across passes to:
    - Track seen check fingerprints for duplicate detection
    - Maintain pass indices and counts
    - Track model calls and evidence hashes
    - Ensure budget limits are respected across the entire loop
    
    The state is immutable - each pass creates a new state with updates.
    """

    # Identifiers
    loop_run_id: str
    incident_id: str
    
    # Pass tracking
    pass_index: int = 1
    started_at: str = ""
    
    # Check fingerprint tracking (for duplicate detection across passes)
    seen_check_fingerprints: frozenset[str] = frozenset()
    
    # Execution counters
    total_checks_executed: int = 0
    total_checks_proposed: int = 0
    total_checks_rejected: int = 0
    total_mutating_executed: int = 0
    total_sensitive_executed: int = 0
    total_model_calls: int = 0
    
    # Evidence tracking
    evidence_hashes_seen: frozenset[str] = frozenset()
    
    # Case file tracking
    last_case_file_hash: str = ""
    
    # Schema version for compatibility
    schema_version: str = RUNTIME_SCHEMA_VERSION

    def with_updates(
        self,
        *,
        pass_index: int | None = None,
        seen_check_fingerprints: frozenset[str] | None = None,
        total_checks_executed: int | None = None,
        total_checks_proposed: int | None = None,
        total_checks_rejected: int | None = None,
        total_mutating_executed: int | None = None,
        total_sensitive_executed: int | None = None,
        total_model_calls: int | None = None,
        evidence_hashes_seen: frozenset[str] | None = None,
        last_case_file_hash: str | None = None,
    ) -> LoopRuntimeState:
        """Create a new state with the specified updates applied."""
        return LoopRuntimeState(
            loop_run_id=self.loop_run_id,
            incident_id=self.incident_id,
            pass_index=pass_index if pass_index is not None else self.pass_index,
            started_at=self.started_at,
            seen_check_fingerprints=(
                seen_check_fingerprints if seen_check_fingerprints is not None 
                else self.seen_check_fingerprints
            ),
            total_checks_executed=(
                total_checks_executed if total_checks_executed is not None 
                else self.total_checks_executed
            ),
            total_checks_proposed=(
                total_checks_proposed if total_checks_proposed is not None 
                else self.total_checks_proposed
            ),
            total_checks_rejected=(
                total_checks_rejected if total_checks_rejected is not None 
                else self.total_checks_rejected
            ),
            total_mutating_executed=(
                total_mutating_executed if total_mutating_executed is not None 
                else self.total_mutating_executed
            ),
            total_sensitive_executed=(
                total_sensitive_executed if total_sensitive_executed is not None 
                else self.total_sensitive_executed
            ),
            total_model_calls=(
                total_model_calls if total_model_calls is not None 
                else self.total_model_calls
            ),
            evidence_hashes_seen=(
                evidence_hashes_seen if evidence_hashes_seen is not None 
                else self.evidence_hashes_seen
            ),
            last_case_file_hash=(
                last_case_file_hash if last_case_file_hash is not None 
                else self.last_case_file_hash
            ),
            schema_version=self.schema_version,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "loop_run_id": self.loop_run_id,
            "incident_id": self.incident_id,
            "pass_index": self.pass_index,
            "started_at": self.started_at,
            "seen_check_fingerprints": list(self.seen_check_fingerprints),
            "total_checks_executed": self.total_checks_executed,
            "total_checks_proposed": self.total_checks_proposed,
            "total_checks_rejected": self.total_checks_rejected,
            "total_mutating_executed": self.total_mutating_executed,
            "total_sensitive_executed": self.total_sensitive_executed,
            "total_model_calls": self.total_model_calls,
            "evidence_hashes_seen": list(self.evidence_hashes_seen),
            "last_case_file_hash": self.last_case_file_hash,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopRuntimeState:
        """Create from dict."""
        return cls(
            loop_run_id=str(data.get("loop_run_id", "")),
            incident_id=str(data.get("incident_id", "")),
            pass_index=int(data.get("pass_index", 1)),
            started_at=str(data.get("started_at", "")),
            seen_check_fingerprints=frozenset(data.get("seen_check_fingerprints", [])),
            total_checks_executed=int(data.get("total_checks_executed", 0)),
            total_checks_proposed=int(data.get("total_checks_proposed", 0)),
            total_checks_rejected=int(data.get("total_checks_rejected", 0)),
            total_mutating_executed=int(data.get("total_mutating_executed", 0)),
            total_sensitive_executed=int(data.get("total_sensitive_executed", 0)),
            total_model_calls=int(data.get("total_model_calls", 0)),
            evidence_hashes_seen=frozenset(data.get("evidence_hashes_seen", [])),
            last_case_file_hash=str(data.get("last_case_file_hash", "")),
            schema_version=str(data.get("schema_version", RUNTIME_SCHEMA_VERSION)),
        )


__all__ = ["LoopRuntimeState"]
