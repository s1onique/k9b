"""Unit tests for discovery logging hygiene verifier.

These tests verify the verify_discovery_logging_hygiene.py script
works correctly by importing its actual functions. This ensures tests
reflect real verifier behavior rather than a parallel implementation.

See: ACT: Add gate for unsafe discovery fallback logging
"""

from __future__ import annotations

import tempfile
from pathlib import Path

# Import actual functions from the verifier script - this is intentional
# to ensure tests reflect real behavior, not a parallel implementation
from scripts.verify_discovery_logging_hygiene import (
    _FORBIDDEN_PATTERNS,
    check_file_for_patterns,
)


class TestForbiddenPatternDetection:
    """Test detection of each forbidden pattern."""

    def test_detects_logger_warning(self) -> None:
        """Should detect _logger.warning() calls."""
        content = '''
_logger.warning("Something went wrong")
'''
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as f:
            f.write(content)
            path = Path(f.name)
        
        try:
            violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
            assert len(violations) == 1
            assert violations[0][1] == "_logger.warning(...)"
        finally:
            path.unlink(missing_ok=True)

    def test_detects_exc_info_true(self) -> None:
        """Should detect exc_info=True in logger calls."""
        content = '''
try:
    pass
except Exception:
    _logger.error("Error", exc_info=True)
'''
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as f:
            f.write(content)
            path = Path(f.name)
        
        try:
            violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
            assert len(violations) == 1
            assert violations[0][1] == "exc_info=True"
        finally:
            path.unlink(missing_ok=True)

    def test_detects_stderr_in_logger(self) -> None:
        """Should detect stderr interpolation in logger calls."""
        content = '''
_logger.debug("Failed: %s", result.stderr)
'''
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as f:
            f.write(content)
            path = Path(f.name)
        
        try:
            violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
            assert len(violations) == 1
            assert violations[0][1] == "stderr in logger call"
        finally:
            path.unlink(missing_ok=True)

    def test_detects_multiple_violations(self) -> None:
        """Should detect multiple violations in one file."""
        content = '''
_logger.warning("First violation")
_logger.info("OK - info is allowed")
try:
    pass
except Exception:
    _logger.error("Error", exc_info=True)
'''
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as f:
            f.write(content)
            path = Path(f.name)
        
        try:
            violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
            pattern_names = {v[1] for v in violations}
            assert "_logger.warning(...)" in pattern_names
            assert "exc_info=True" in pattern_names
            assert len(violations) == 2
        finally:
            path.unlink(missing_ok=True)

    def test_allows_debug_and_info(self) -> None:
        """Should allow _logger.debug() and _logger.info()."""
        content = '''
_logger.debug("Debug message is allowed")
_logger.info("Info message is allowed")
'''
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as f:
            f.write(content)
            path = Path(f.name)
        
        try:
            violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
            assert len(violations) == 0
        finally:
            path.unlink(missing_ok=True)

    def test_skips_commented_lines(self) -> None:
        """Should skip commented lines."""
        content = '''
# _logger.warning("This is commented")
'''
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as f:
            f.write(content)
            path = Path(f.name)
        
        try:
            violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
            assert len(violations) == 0
        finally:
            path.unlink(missing_ok=True)

    def test_provides_line_numbers(self) -> None:
        """Should report correct line numbers."""
        content = '''
# Line 2

# Line 4
_logger.warning("This is line 5")
'''
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as f:
            f.write(content)
            path = Path(f.name)
        
        try:
            violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
            assert len(violations) == 1
            assert violations[0][0] == 5  # Line 5
        finally:
            path.unlink(missing_ok=True)


class TestSentinelSelfTest:
    """Test the sentinel self-test mechanism."""

    def test_sentinel_detects_all_three_patterns(self) -> None:
        """Sentinel should create a file with all three patterns."""
        sentinel_content = '''"""Sentinel test file."""
import logging

_logger = logging.getLogger(__name__)


def test_function():
    _logger.warning("Raw warning")
    try:
        pass
    except Exception:
        _logger.error("Error", exc_info=True)
    _logger.debug("Failed: %s", result.stderr)
'''
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix="_sentinel_strategy.py",
            delete=False,
        ) as f:
            f.write(sentinel_content)
            path = Path(f.name)
        
        try:
            violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
            pattern_names = {v[1] for v in violations}
            
            assert "_logger.warning(...)" in pattern_names
            assert "exc_info=True" in pattern_names
            assert "stderr in logger call" in pattern_names
        finally:
            path.unlink(missing_ok=True)


class TestDiscoveryStrategyFiles:
    """Verify discovery strategy files pass hygiene checks."""

    def test_no_violations_in_alertmanager_crd_strategy(self) -> None:
        """Alertmanager CRD strategy should have no violations."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_crd_strategy import (
            __file__ as strategy_file,
        )
        
        path = Path(strategy_file)
        violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
        
        assert len(violations) == 0, (
            f"alertmanager_discovery_crd_strategy.py has violations: {violations}"
        )

    def test_no_violations_in_alertmanager_service_strategy(self) -> None:
        """Alertmanager service strategy should have no violations."""
        from k8s_diag_agent.external_analysis.alertmanager_discovery_service_strategy import (
            __file__ as strategy_file,
        )
        
        path = Path(strategy_file)
        violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
        
        assert len(violations) == 0, (
            f"alertmanager_discovery_service_strategy.py has violations: {violations}"
        )

    def test_no_violations_in_vmalert_crd_strategy(self) -> None:
        """VMAlert CRD strategy should have no violations."""
        from k8s_diag_agent.external_analysis.vmalert_discovery_crd_strategy import (
            __file__ as strategy_file,
        )
        
        path = Path(strategy_file)
        violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
        
        assert len(violations) == 0, (
            f"vmalert_discovery_crd_strategy.py has violations: {violations}"
        )

    def test_no_violations_in_vmalert_service_strategy(self) -> None:
        """VMAlert service strategy should have no violations."""
        from k8s_diag_agent.external_analysis.vmalert_discovery_service_strategy import (
            __file__ as strategy_file,
        )
        
        path = Path(strategy_file)
        violations = check_file_for_patterns(path, _FORBIDDEN_PATTERNS)
        
        assert len(violations) == 0, (
            f"vmalert_discovery_service_strategy.py has violations: {violations}"
        )
