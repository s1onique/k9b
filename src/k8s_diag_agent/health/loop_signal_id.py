"""Signal ID generation for health assessment loop."""

from __future__ import annotations

from .loop_history import _safe_label


class _SignalIdGenerator:
    """Generates deterministic signal IDs for health assessment findings.

    IDs are formatted as: health-{label}-sig-{counter:02d}
    where counter starts at 0 and increments with each call to next_id().
    """

    def __init__(self, label: str) -> None:
        self._label = _safe_label(label)
        self._counter = 0

    def next_id(self) -> str:
        self._counter += 1
        return f"health-{self._label}-sig-{self._counter:02d}"