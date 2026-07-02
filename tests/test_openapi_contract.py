"""OpenAPI contract smoke tests.

This module provides a quick sanity check that the OpenAPI spec loads and has
basic structure. Detailed OpenAPI contract assertions live in focused shards:
- test_openapi_contract_paths.py - path normalization + required route coverage
- test_openapi_contract_schemas.py - schema/component assertions
- test_openapi_contract_operations.py - method/status/operationId/content-type checks

Run with: .venv/bin/python -m pytest tests/test_openapi_contract*.py -v

CI gate: The detailed test modules above MUST pass before merge.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.ui.api_contract import build_openapi_schema


def test_openapi_spec_loads() -> None:
    """The OpenAPI spec should load and have basic structure."""
    spec = build_openapi_schema()

    assert isinstance(spec, dict)
    assert "openapi" in spec
    assert spec["openapi"].startswith("3.")
    assert "paths" in spec
    assert len(spec["paths"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
