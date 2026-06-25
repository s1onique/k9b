"""Types for backend health gate."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthCheckResult:
    """Structured result from backend health check."""
    
    # Classification
    failure_class: str = ""
    passed: bool = False
    
    # HTTP details
    http_status: int = 0
    final_http_code: str = ""
    
    # Timing
    poll_count: int = 0
    total_elapsed_seconds: float = 0
    
    # Error details
    transport_error: str = ""
    
    # All HTTP statuses seen (for diagnostics)
    http_statuses_seen: list[str] = field(default_factory=list)
    
    # Diagnostics for JSON artifact
    diagnostics: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "failure_class": self.failure_class,
            "passed": self.passed,
            "http_status": self.http_status,
            "final_http_code": self.final_http_code,
            "poll_count": self.poll_count,
            "total_elapsed_seconds": self.total_elapsed_seconds,
            "transport_error": self.transport_error,
            "http_statuses_seen": self.http_statuses_seen,
            "diagnostics": self.diagnostics,
        }
