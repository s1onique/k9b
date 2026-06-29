"""Health loop public API.

Implementation is split across LLM-friendly modules. Import from this module
for backward compatibility. The actual implementation lives in:

- loop_runner: HealthLoopRunner, run_health_loop
- loop_run_config: HealthRunConfig, build_health_assessment
- loop_models: HealthLoopResult, HealthLoopStatus, ManualComparison
- loop_history: HealthAssessmentArtifact, HealthHistoryEntry, HealthRating
- loop_types: HealthTarget, HealthSnapshotRecord, ManualExternalAnalysisRequest
- loop_comparison_policy: BaselineRegistry, _policy_eligible_pair, _resolve_peer_role, _validate_suspicious_pairs
- loop_comparison_triggers: determine_pair_trigger_reasons
- loop_comparison_types: ComparisonDecision, ComparisonIntent, ComparisonPeer,
                         ComparisonTriggerArtifact, TriggerDetail, TriggerPolicy
- loop_scheduler: _HEALTH_ONLY_MESSAGE, HealthLoopScheduler
- loop_scheduler_locking: LockEvaluation, LockFileSnapshot, ProcessIdentity
"""

from __future__ import annotations

import subprocess  # noqa: F401 - re-exported for backward compatibility
from pathlib import Path  # noqa: F401 - re-exported for backward compatibility
from uuid import uuid4  # noqa: F401 - re-exported for backward compatibility

# Re-export from loop_comparison_policy
from .loop_comparison_policy import (  # noqa: F401
    BaselineRegistry,
    _policy_eligible_pair,
    _resolve_peer_role,
    _validate_suspicious_pairs,
)

# Re-export from loop_comparison_triggers
from .loop_comparison_triggers import determine_pair_trigger_reasons  # noqa: F401

# Re-export from loop_comparison_types
from .loop_comparison_types import (  # noqa: F401 - re-export for backward compatibility
    ComparisonDecision,
    ComparisonIntent,
    ComparisonPeer,
    ComparisonTriggerArtifact,
    TriggerDetail,
    TriggerPolicy,
)

# Re-export from loop_history (shared types)
from .loop_history import (
    HealthAssessmentArtifact,
    HealthAssessmentResult,
    HealthHistoryEntry,
    HealthRating,
    _build_runtime_run_id,
    _format_snapshot_filename,
    _safe_label,
    _str_or_none,
    _write_json,
)

# Re-export from loop_models
from .loop_models import (
    HealthLoopResult,
    HealthLoopStatus,
    ManualComparison,
)

# Re-export from loop_run_config (HealthRunConfig, build_health_assessment)
from .loop_run_config import HealthRunConfig, build_health_assessment

# Re-export from loop_runner (HealthLoopRunner, run_health_loop)
# Re-export _SCRIPTS_DIR for backward compatibility
from .loop_runner import (
    _SCRIPTS_DIR,  # noqa: F401
    HealthLoopRunner,
    run_health_loop,
)

# Re-export from loop_scheduler
from .loop_scheduler import (  # noqa: F401
    _HEALTH_ONLY_MESSAGE,
    HealthLoopScheduler,
)

# Re-export from loop_scheduler_locking
from .loop_scheduler_locking import (  # noqa: F401 - re-exported for backward compatibility
    LockEvaluation,
    LockFileSnapshot,
    ProcessIdentity,
)

# Re-export from loop_types (shared types)
from .loop_types import (
    HealthSnapshotRecord,
    HealthTarget,
    ManualExternalAnalysisRequest,
)

__all__ = [
    # From loop_runner
    "HealthLoopRunner",
    "HealthRunConfig",
    "build_health_assessment",
    "run_health_loop",
    # From loop_models
    "HealthLoopResult",
    "HealthLoopStatus",
    "ManualComparison",
    # From loop_history
    "HealthAssessmentArtifact",
    "HealthAssessmentResult",
    "HealthHistoryEntry",
    "HealthRating",
    "_build_runtime_run_id",
    "_format_snapshot_filename",
    "_safe_label",
    "_str_or_none",
    "_write_json",
    # From loop_types
    "HealthSnapshotRecord",
    "HealthTarget",
    "ManualExternalAnalysisRequest",
    # From loop_comparison_policy
    "BaselineRegistry",
    "_policy_eligible_pair",
    "_resolve_peer_role",
    "_validate_suspicious_pairs",
    # From loop_comparison_triggers
    "determine_pair_trigger_reasons",
    # From loop_comparison_types
    "ComparisonDecision",
    "ComparisonIntent",
    "ComparisonPeer",
    "ComparisonTriggerArtifact",
    "TriggerDetail",
    "TriggerPolicy",
    # From loop_scheduler
    "_HEALTH_ONLY_MESSAGE",
    "HealthLoopScheduler",
    # From loop_scheduler_locking
    "LockEvaluation",
    "LockFileSnapshot",
    "ProcessIdentity",
    # Utility re-exports
    "uuid4",
]
