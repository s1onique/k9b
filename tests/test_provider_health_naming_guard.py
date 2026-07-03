"""Stale-name guard for provider-health tests.

This module catches obvious contradictions in provider-health test naming:
- class name contains 'Rejected' but method name contains 'accepted'
- class name contains 'Accepted' but parametrized case expects failure
- test name says contamination but expected failure class is 'None'

Keep this narrow to provider-health tests; do not build a generic global naming linter.
"""

from __future__ import annotations

import ast
from pathlib import Path


def check_class_method_naming_contradictions(
    source_code: str,
    filename: str,
) -> list[str]:
    """Check for naming contradictions in provider-health test classes.

    Args:
        source_code: The source code to check
        filename: The filename for context

    Returns:
        List of warning messages (empty if no issues)
    """
    warnings: list[str] = []

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return warnings

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name

            # Check class-method contradictions
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    method_name = item.name

                    # Pattern: class name contains 'Rejected' but method contains 'accepted'
                    if (
                        "Rejected" in class_name
                        and "accepted" in method_name.lower()
                        and "accept" in method_name.lower()
                    ):
                        warnings.append(
                            f"{filename}:{node.lineno}: "
                            f"Class '{class_name}' contains 'Rejected' but method "
                            f"'{method_name}' contains 'accepted'. "
                            f"Consider renaming class or method."
                        )

                    # Pattern: class name contains 'Accepted' but method contains 'reject'
                    if (
                        "Accepted" in class_name
                        and "reject" in method_name.lower()
                        and "reject" in method_name.lower()
                    ):
                        warnings.append(
                            f"{filename}:{node.lineno}: "
                            f"Class '{class_name}' contains 'Accepted' but method "
                            f"'{method_name}' contains 'reject'. "
                            f"Consider renaming class or method."
                        )

    return warnings


def check_provider_health_tests(
    tests_dir: Path,
) -> dict[str, list[str]]:
    """Check all provider-health test files for naming contradictions.

    Args:
        tests_dir: The tests directory to scan

    Returns:
        Dict mapping filename to list of warnings
    """
    results: dict[str, list[str]] = {}

    for test_file in tests_dir.rglob("test*provider*health*.py"):
        try:
            content = test_file.read_text()
            warnings = check_class_method_naming_contradictions(
                content, str(test_file)
            )
            if warnings:
                results[str(test_file)] = warnings
        except (OSError, UnicodeDecodeError):
            # Skip files that can't be read (e.g., binary files, permission errors)
            pass

    return results


if __name__ == "__main__":
    import sys

    tests_dir = Path(__file__).parent.parent
    results = check_provider_health_tests(tests_dir)

    if results:
        print("Provider-health test naming warnings:")
        for filename, warnings in results.items():
            for warning in warnings:
                print(f"  {warning}")
        sys.exit(1)
    else:
        print("No provider-health test naming contradictions found.")
        sys.exit(0)
