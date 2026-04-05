"""Minimal correlate seam to keep layers explicit."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List

from ..models import Signal


def correlate_signals(signals: Iterable[Signal]) -> Dict[str, List[str]]:
    by_layer: Dict[str, List[str]] = defaultdict(list)
    for signal in signals:
        by_layer[signal.layer.value].append(signal.id)
    return dict(by_layer)
