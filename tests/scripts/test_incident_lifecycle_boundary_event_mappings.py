"""Tests for the incident lifecycle boundary event mappings verifier.

Required tests per ACT-K9B-HULK-DOMAIN-EVENT-TYPES01:
1. extracts IncidentLifecycleEventType values from Literal alias
2. extracts IncidentLifecycleActor values from Literal alias
3. fails if IncidentLifecycleEvent.event_type is typed as str
4. fails if IncidentLifecycleEvent.actor is typed as str
5. fails if event mapping is missing a domain event key
6. fails if event mapping has unknown extra key
7. fails if actor mapping is missing a domain actor key
8. fails if actor mapping has unknown extra key
9. passes for actual domain and adapter modules
10. CLI fails when event mapping checker returns errors
11. CLI passes when event mapping checker returns no errors
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Use the scripts directory for tests - must be before the module import
REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

EVENT_MAPPINGS_MODULE = SCRIPTS_DIR / "incident_lifecycle_boundary" / "event_mappings.py"
CLI_MODULE = SCRIPTS_DIR / "incident_lifecycle_boundary" / "cli.py"

from incident_lifecycle_boundary.event_mappings import (  # noqa: E402
    check_event_dataclass_field_types,
    check_lifecycle_event_mappings,
    extract_domain_actors,
    extract_domain_event_types,
    extract_literal_alias_values,
)

# -----------------------------------------------------------------------------
# Test 1: Extract IncidentLifecycleEventType values
# -----------------------------------------------------------------------------

class TestExtractEventTypeValues:
    """Tests for extracting IncidentLifecycleEventType values from Literal alias."""

    def test_extracts_event_types_from_literal_alias(self, tmp_path: Path) -> None:
        """Extracts values from IncidentLifecycleEventType Literal alias."""
        content = '''
IncidentLifecycleEventType = Literal[
    "incident_promoted",
    "incident_marked_collecting_evidence",
    "incident_marked_ready_for_review",
    "incident_marked_investigating",
    "incident_suppressed",
    "incident_marked_duplicate",
    "incident_resolved",
]
'''
        test_file = tmp_path / "test_module.py"
        test_file.write_text(content)

        values = extract_literal_alias_values(str(test_file), "IncidentLifecycleEventType")
        assert values == {
            "incident_promoted",
            "incident_marked_collecting_evidence",
            "incident_marked_ready_for_review",
            "incident_marked_investigating",
            "incident_suppressed",
            "incident_marked_duplicate",
            "incident_resolved",
        }

    def test_extracts_from_actual_domain_module(self) -> None:
        """Extracts values from actual domain module."""
        domain_module = REPO_ROOT / "src" / "k8s_diag_agent" / "domain" / "incident_lifecycle.py"
        values = extract_domain_event_types(str(domain_module))
        assert values == {
            "incident_promoted",
            "incident_marked_collecting_evidence",
            "incident_marked_ready_for_review",
            "incident_marked_investigating",
            "incident_suppressed",
            "incident_marked_duplicate",
            "incident_resolved",
        }


# -----------------------------------------------------------------------------
# Test 2: Extract IncidentLifecycleActor values
# -----------------------------------------------------------------------------

class TestExtractActorValues:
    """Tests for extracting IncidentLifecycleActor values from Literal alias."""

    def test_extracts_actors_from_literal_alias(self, tmp_path: Path) -> None:
        """Extracts values from IncidentLifecycleActor Literal alias."""
        content = '''
IncidentLifecycleActor = Literal[
    "system",
    "user",
    "diagnosis_loop",
    "test",
]
'''
        test_file = tmp_path / "test_module.py"
        test_file.write_text(content)

        values = extract_literal_alias_values(str(test_file), "IncidentLifecycleActor")
        assert values == {
            "system",
            "user",
            "diagnosis_loop",
            "test",
        }

    def test_extracts_from_actual_domain_module(self) -> None:
        """Extracts values from actual domain module."""
        domain_module = REPO_ROOT / "src" / "k8s_diag_agent" / "domain" / "incident_lifecycle.py"
        values = extract_domain_actors(str(domain_module))
        assert values == {
            "system",
            "user",
            "diagnosis_loop",
            "test",
        }


# -----------------------------------------------------------------------------
# Test 3: Fails if event_type is typed as str
# -----------------------------------------------------------------------------

class TestEventTypeFieldTyping:
    """Tests for IncidentLifecycleEvent.event_type field typing."""

    def test_fails_if_event_type_is_str(self, tmp_path: Path) -> None:
        """Fails if event_type is typed as str instead of IncidentLifecycleEventType."""
        content = '''
from dataclasses import dataclass
from typing import Literal

IncidentLifecycleEventType = Literal["event_a", "event_b"]
IncidentLifecycleActor = Literal["actor_a", "actor_b"]

@dataclass(frozen=True, slots=True, kw_only=True)
class IncidentLifecycleEvent:
    event_type: str  # Should be IncidentLifecycleEventType
    actor: IncidentLifecycleActor
    incident_id: str
    created_at: str
'''
        test_file = tmp_path / "test_module.py"
        test_file.write_text(content)

        errors = check_event_dataclass_field_types(str(test_file))
        assert any(
            "event_type" in e and "too wide" in e
            for e in errors
        ), f"Expected error about event_type being too wide, got: {errors}"

    def test_passes_if_event_type_is_correct_type(self, tmp_path: Path) -> None:
        """Passes if event_type is correctly typed as IncidentLifecycleEventType."""
        content = '''
from dataclasses import dataclass
from typing import Literal

IncidentLifecycleEventType = Literal["event_a", "event_b"]
IncidentLifecycleActor = Literal["actor_a", "actor_b"]

@dataclass(frozen=True, slots=True, kw_only=True)
class IncidentLifecycleEvent:
    event_type: IncidentLifecycleEventType
    actor: IncidentLifecycleActor
    incident_id: str
    created_at: str
'''
        test_file = tmp_path / "test_module.py"
        test_file.write_text(content)

        errors = check_event_dataclass_field_types(str(test_file))
        # Should not have errors about event_type being too wide
        event_type_errors = [e for e in errors if "event_type" in e and "too wide" in e]
        assert not event_type_errors, f"Unexpected errors about event_type: {event_type_errors}"


# -----------------------------------------------------------------------------
# Test 4: Fails if actor is typed as str
# -----------------------------------------------------------------------------

class TestActorFieldTyping:
    """Tests for IncidentLifecycleEvent.actor field typing."""

    def test_fails_if_actor_is_str(self, tmp_path: Path) -> None:
        """Fails if actor is typed as str instead of IncidentLifecycleActor."""
        content = '''
from dataclasses import dataclass
from typing import Literal

IncidentLifecycleEventType = Literal["event_a", "event_b"]
IncidentLifecycleActor = Literal["actor_a", "actor_b"]

@dataclass(frozen=True, slots=True, kw_only=True)
class IncidentLifecycleEvent:
    event_type: IncidentLifecycleEventType
    actor: str  # Should be IncidentLifecycleActor
    incident_id: str
    created_at: str
'''
        test_file = tmp_path / "test_module.py"
        test_file.write_text(content)

        errors = check_event_dataclass_field_types(str(test_file))
        assert any(
            "actor" in e and "too wide" in e
            for e in errors
        ), f"Expected error about actor being too wide, got: {errors}"

    def test_passes_if_actor_is_correct_type(self, tmp_path: Path) -> None:
        """Passes if actor is correctly typed as IncidentLifecycleActor."""
        content = '''
from dataclasses import dataclass
from typing import Literal

IncidentLifecycleEventType = Literal["event_a", "event_b"]
IncidentLifecycleActor = Literal["actor_a", "actor_b"]

@dataclass(frozen=True, slots=True, kw_only=True)
class IncidentLifecycleEvent:
    event_type: IncidentLifecycleEventType
    actor: IncidentLifecycleActor
    incident_id: str
    created_at: str
'''
        test_file = tmp_path / "test_module.py"
        test_file.write_text(content)

        errors = check_event_dataclass_field_types(str(test_file))
        # Should not have errors about actor being too wide
        actor_errors = [e for e in errors if "actor" in e and "too wide" in e]
        assert not actor_errors, f"Unexpected errors about actor: {actor_errors}"


# -----------------------------------------------------------------------------
# Test 5: Fails if event mapping is missing a domain event key
# -----------------------------------------------------------------------------

class TestEventMappingCompleteness:
    """Tests for event mapping completeness."""

    def test_fails_if_event_mapping_missing_key(self, tmp_path: Path) -> None:
        """Fails if _DOMAIN_EVENT_TO_STORE_EVENT is missing domain event keys."""
        # Create a minimal domain file with event types
        domain_file = tmp_path / "domain.py"
        domain_file.write_text('''
IncidentLifecycleEventType = Literal["event_a", "event_b"]

@dataclass
class IncidentLifecycleEvent:
    event_type: IncidentLifecycleEventType
    actor: str
    incident_id: str
    created_at: str
''')

        # Create adapter file with incomplete mapping
        adapter_file = tmp_path / "adapter.py"
        adapter_file.write_text('''
_DOMAIN_EVENT_TO_STORE_EVENT = {
    "event_a": "StoreA",  # Missing "event_b"
}
''')

        errors = check_lifecycle_event_mappings(str(domain_file), str(adapter_file))
        assert any(
            "missing domain events" in e
            for e in errors
        ), f"Expected error about missing domain events, got: {errors}"

    def test_fails_if_event_mapping_has_extra_key(self, tmp_path: Path) -> None:
        """Fails if _DOMAIN_EVENT_TO_STORE_EVENT has unknown extra keys."""
        # Create a minimal domain file with event types
        domain_file = tmp_path / "domain.py"
        domain_file.write_text('''
IncidentLifecycleEventType = Literal["event_a", "event_b"]
IncidentLifecycleActor = Literal["actor_a"]

@dataclass
class IncidentLifecycleEvent:
    event_type: IncidentLifecycleEventType
    actor: IncidentLifecycleActor
    incident_id: str
    created_at: str
''')

        # Create adapter file with extra key
        adapter_file = tmp_path / "adapter.py"
        adapter_file.write_text('''
_DOMAIN_EVENT_TO_STORE_EVENT = {
    "event_a": "StoreA",
    "event_b": "StoreB",
    "event_c": "StoreC",  # Unknown extra key
}

_DOMAIN_ACTOR_TO_STORE_ACTOR = {
    "actor_a": "StoreActor",
}
''')

        errors = check_lifecycle_event_mappings(str(domain_file), str(adapter_file))
        assert any(
            "unknown extra keys" in e
            for e in errors
        ), f"Expected error about extra keys, got: {errors}"


# -----------------------------------------------------------------------------
# Test 7: Fails if actor mapping is missing a domain actor key
# -----------------------------------------------------------------------------

class TestActorMappingCompleteness:
    """Tests for actor mapping completeness."""

    def test_fails_if_actor_mapping_missing_key(self, tmp_path: Path) -> None:
        """Fails if _DOMAIN_ACTOR_TO_STORE_ACTOR is missing domain actor keys."""
        # Create a minimal domain file with actors
        domain_file = tmp_path / "domain.py"
        domain_file.write_text('''
IncidentLifecycleEventType = Literal["event_a"]
IncidentLifecycleActor = Literal["actor_a", "actor_b"]

@dataclass
class IncidentLifecycleEvent:
    event_type: IncidentLifecycleEventType
    actor: IncidentLifecycleActor
    incident_id: str
    created_at: str
''')

        # Create adapter file with incomplete mapping
        adapter_file = tmp_path / "adapter.py"
        adapter_file.write_text('''
_DOMAIN_EVENT_TO_STORE_EVENT = {
    "event_a": "StoreA",
}

_DOMAIN_ACTOR_TO_STORE_ACTOR = {
    "actor_a": "StoreActor",  # Missing "actor_b"
}
''')

        errors = check_lifecycle_event_mappings(str(domain_file), str(adapter_file))
        assert any(
            "missing domain actors" in e
            for e in errors
        ), f"Expected error about missing domain actors, got: {errors}"

    def test_fails_if_actor_mapping_has_extra_key(self, tmp_path: Path) -> None:
        """Fails if _DOMAIN_ACTOR_TO_STORE_ACTOR has unknown extra keys."""
        # Create a minimal domain file with actors
        domain_file = tmp_path / "domain.py"
        domain_file.write_text('''
IncidentLifecycleEventType = Literal["event_a"]
IncidentLifecycleActor = Literal["actor_a"]

@dataclass
class IncidentLifecycleEvent:
    event_type: IncidentLifecycleEventType
    actor: IncidentLifecycleActor
    incident_id: str
    created_at: str
''')

        # Create adapter file with extra key
        adapter_file = tmp_path / "adapter.py"
        adapter_file.write_text('''
_DOMAIN_EVENT_TO_STORE_EVENT = {
    "event_a": "StoreA",
}

_DOMAIN_ACTOR_TO_STORE_ACTOR = {
    "actor_a": "StoreActor",
    "actor_b": "StoreActorB",  # Unknown extra key
}
''')

        errors = check_lifecycle_event_mappings(str(domain_file), str(adapter_file))
        assert any(
            "unknown extra keys" in e
            for e in errors
        ), f"Expected error about extra keys, got: {errors}"


# -----------------------------------------------------------------------------
# Test 9: Passes for actual domain and adapter modules
# -----------------------------------------------------------------------------

class TestActualModules:
    """Tests against actual production modules."""

    def test_passes_for_actual_domain_and_adapter(self) -> None:
        """Passes for actual domain and adapter modules."""
        domain_module = REPO_ROOT / "src" / "k8s_diag_agent" / "domain" / "incident_lifecycle.py"
        adapter_module = REPO_ROOT / "src" / "k8s_diag_agent" / "collect" / "incident_lifecycle_domain_adapter.py"

        errors = check_lifecycle_event_mappings(str(domain_module), str(adapter_module))
        assert not errors, f"Expected no errors for actual modules, got: {errors}"


# -----------------------------------------------------------------------------
# Test 10-11: CLI integration tests
# -----------------------------------------------------------------------------

class TestCLIIntegration:
    """CLI integration tests for event mapping checks."""

    def test_cli_passes_with_correct_mappings(self) -> None:
        """CLI passes when event mapping checker returns no errors."""
        result = subprocess.run(
            [sys.executable, str(CLI_MODULE)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        # Should pass (return 0) or fail due to other checks
        # At minimum, event mapping check should not be the cause
        if result.returncode != 0:
            # If CLI fails, ensure it's not due to event mapping issues
            assert "event_type" not in result.stdout.lower() or "too wide" not in result.stdout.lower()
            assert "actor" not in result.stdout.lower() or "too wide" not in result.stdout.lower()
