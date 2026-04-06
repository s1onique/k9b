"""Repo-root stub so ``python -m k8s_diag_agent.cli`` works without installing."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_PACKAGE = ROOT.parent / "src" / "k8s_diag_agent"

if str(SOURCE_PACKAGE) not in __path__:
    __path__.insert(0, str(SOURCE_PACKAGE))
