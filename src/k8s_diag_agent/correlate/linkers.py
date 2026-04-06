"""Minimal correlate seam to keep layers explicit."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from ..models import Signal


def correlate_signals(signals: Iterable[Signal]) -> dict[str, list[str]]:
    by_layer: dict[str, list[str]] = defaultdict(list)
    for signal in signals:
        by_layer[signal.layer.value].append(signal.id)
    return dict(by_layer)
