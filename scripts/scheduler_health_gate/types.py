"""Types for scheduler health gate."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SchedulerHealthResult:
    """Structured result from scheduler health check."""

    # Classification
    failure_class: str = ""
    passed: bool = False

    # Scheduler state
    deployment_found: bool = False
    deployment_name: str = ""
    pod_count: int = 0
    ready_replicas: int = 0
    available_replicas: int = 0

    # Failure details
    failure_reason: str = ""
    failure_details: str = ""

    # Evidence
    crash_loop_pods: list[dict[str, Any]] = field(default_factory=list)
    waiting_pods: list[dict[str, Any]] = field(default_factory=list)
    terminated_pods: list[dict[str, Any]] = field(default_factory=list)
    namespace_events: list[dict[str, Any]] = field(default_factory=list)

    # Diagnostics collected
    scheduler_pods_json: str = ""
    scheduler_diagnosis: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "failure_class": self.failure_class,
            "passed": self.passed,
            "deployment_found": self.deployment_found,
            "deployment_name": self.deployment_name,
            "pod_count": self.pod_count,
            "ready_replicas": self.ready_replicas,
            "available_replicas": self.available_replicas,
            "failure_reason": self.failure_reason,
            "failure_details": self.failure_details,
            "crash_loop_pods": self.crash_loop_pods,
            "waiting_pods": self.waiting_pods,
            "terminated_pods": self.terminated_pods,
            "namespace_events": self.namespace_events,
            "scheduler_pods_json": self.scheduler_pods_json,
            "scheduler_diagnosis": self.scheduler_diagnosis,
        }
