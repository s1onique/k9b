"""Tests for image preflight operations.

This module is a thin re-export wrapper that collects all image preflight tests
organized into focused modules for better maintainability.

Modules:
    - test_image_preflight_registry: Image ref parsing, HTTP error classification
    - test_image_preflight_node: Node pull operations
    - test_image_preflight_types: Type definitions

Run all tests with: pytest tests/test_image_preflight*.py
Run specific module: pytest tests/test_image_preflight_registry.py
"""

from __future__ import annotations

# Re-export all test modules for backwards compatibility
# Tests can be run from this module or from individual test modules
from tests.test_image_preflight_registry import *  # noqa: F401, F403
from tests.test_image_preflight_node import *  # noqa: F401, F403
from tests.test_image_preflight_types import *  # noqa: F401, F403

__all__ = [
    "test_image_preflight_registry",
    "test_image_preflight_node",
    "test_image_preflight_types",
]
