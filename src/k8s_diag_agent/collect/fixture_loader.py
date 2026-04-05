"""Load fixture files for scenarios."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, cast

from ..schemas import FixtureValidator


def load_fixture(path: Path) -> Dict[str, Any]:
    content = cast(Dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    FixtureValidator.validate(content)
    return content


def load_fixture_from_str(json_str: str) -> Dict[str, Any]:
    content = cast(Dict[str, Any], json.loads(json_str))
    FixtureValidator.validate(content)
    return content
