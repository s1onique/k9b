#!/usr/bin/env python3
"""Thin entry-point shim that delegates to :mod:`scripts.verifiers_audit.cli`.

The shim keeps a stable command name (``audit.py``) while the
real CLI logic lives in :mod:`scripts.verifiers_audit.cli`.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import sys

from scripts.verifiers_audit.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
