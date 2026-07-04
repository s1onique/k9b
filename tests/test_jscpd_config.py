"""Regression tests for .jscpd.json configuration hygiene.

Ensures that:
1. Generated data files are narrowly excluded from duplicate detection
2. The scripts/ directory remains covered by duplicate detection
3. Duplicate check command includes scripts/ in the scan path
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class TestJscpdConfigGeneratedDataExclusion:
    """Regression tests for generated data exclusion in jscpd config."""

    def test_python_test_durations_is_narrowly_excluded(self) -> None:
        """python_test_durations.json is excluded but not entire scripts/ dir.

        This is a regression test ensuring we exclude only the generated
        timing manifest, not the entire scripts/ directory from duplicate detection.
        """
        config_path = Path(".jscpd.json")
        assert config_path.exists(), ".jscpd.json must exist"

        with open(config_path) as f:
            config = json.load(f)

        ignore_patterns = config.get("ignore", [])

        # The generated manifest should be excluded
        assert "**/scripts/python_test_durations.json" in ignore_patterns, (
            "python_test_durations.json must be in jscpd ignore list"
        )

        # The entire scripts/** pattern should NOT be present
        scripts_wildcard = "**/scripts/**"
        assert scripts_wildcard not in ignore_patterns, (
            f"Broad '{scripts_wildcard}' pattern found in jscpd ignore list. "
            "Only narrow exclusion for python_test_durations.json is allowed."
        )

    def test_other_scripts_files_not_excluded(self) -> None:
        """Verify we don't have overly broad script exclusions.

        Common scripts should NOT be in the ignore list since they should
        be checked for duplicate code patterns.
        """
        config_path = Path(".jscpd.json")
        with open(config_path) as f:
            config = json.load(f)

        ignore_patterns = config.get("ignore", [])

        # These patterns would be too broad
        forbidden_patterns = [
            "**/scripts/**",
            "scripts/**",
            "**/scripts/*.py",
        ]

        for pattern in forbidden_patterns:
            assert pattern not in ignore_patterns, (
                f"Overly broad exclusion '{pattern}' found in jscpd ignore list"
            )


class TestMakefileDuplicateCheck:
    """Regression tests for Makefile duplicate check command."""

    def test_check_duplicates_includes_scripts_path(self) -> None:
        """Duplicate check must include ../scripts in the scan path.

        This ensures scripts/ directory is covered by duplicate detection,
        except for generated data files (handled by .jscpd.json ignore list).
        """
        makefile_path = Path("Makefile")
        assert makefile_path.exists(), "Makefile must exist"

        with open(makefile_path) as f:
            content = f.read()

        # Find the check-duplicates target - capture from PHONY to next target or end
        check_duplicates_section = re.search(
            r"^(\.PHONY: check-duplicates\n.*?)"  # Capture from PHONY through content
            r"(?=^\.PHONY:|^[A-Z]|\Z)",  # Stop at next target or end of file
            content,
            re.MULTILINE | re.DOTALL,
        )
        assert check_duplicates_section, "check-duplicates target must exist"

        section = check_duplicates_section.group(1)

        # The command should include ../scripts in the paths being scanned
        # This is different from the ignore patterns - this is the actual scan paths
        assert "../scripts" in section, (
            "check-duplicates must include ../scripts in scan paths. "
            "Generated data should be excluded via .jscpd.json ignore list, "
            "not by removing scripts from scan paths."
        )

    def test_comment_accurately_describes_scanned_directories(self) -> None:
        """Makefile comment should list all scanned directories."""
        makefile_path = Path("Makefile")
        with open(makefile_path) as f:
            content = f.read()

        # Find the check-duplicates comment
        comment_match = re.search(
            r"# Scans: ([^\n]+)",
            content,
        )
        assert comment_match, "Scans comment must exist in check-duplicates section"

        scans_comment = comment_match.group(1)

        # The comment should mention scripts/
        assert "scripts/" in scans_comment, (
            f"Scans comment should list scripts/ but found: {scans_comment}"
        )

        # Should NOT mention that scripts is excluded via path removal
        assert "path removal" not in scans_comment.lower(), (
            "Scans comment should not mention path removal for scripts/"
        )
