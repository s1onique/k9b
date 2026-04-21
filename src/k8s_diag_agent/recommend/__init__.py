"""Recommendation module for proposing next diagnostic steps.

Public API:
"""

from .next_steps import build_recommended_action, propose_next_steps

__all__ = [
    "propose_next_steps",
    "build_recommended_action",
]
