"""Load fixture files for scenarios."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ..schemas import FixtureValidator


def load_fixture(path: Path) -> dict[str, Any]:
    content = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    FixtureValidator.validate(content)
    return content


def load_fixture_from_str(json_str: str) -> dict[str, Any]:
    content = cast(dict[str, Any], json.loads(json_str))
    FixtureValidator.validate(content)
    return content
