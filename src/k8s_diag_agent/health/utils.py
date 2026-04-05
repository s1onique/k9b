"""Shared helpers for the health loop."""

from __future__ import annotations


def normalize_ref(value: str) -> str:
    if value is None:
        return ""
    return value.strip().lower()
