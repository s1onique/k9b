#!/usr/bin/env python
"""Verify data model documentation hygiene.

This script checks that:
1. docs/data-model.md exists and is <= 220 lines
2. All subdocs are linked from docs/data-model.md
3. No closure-report markers in index
4. Required language in incidents.md
5. Required language in next-checks.md
6. Required language in review-packets.md
7. Required language in artifacts.md
8. Required language in alertmanager-sources.md

Usage:
    python scripts/verify_data_model_docs.py           # verify
    python scripts/verify_data_model_docs.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"
DATA_MODEL_DIR = DOCS_DIR / "data-model"
DATA_MODEL_MD = DOCS_DIR / "data-model.md"

# Required subdocs
REQUIRED_SUBDOCS = [
    "artifacts.md",
    "run-lifecycle.md",
    "incidents.md",
    "next-checks.md",
    "review-packets.md",
    "alertmanager-sources.md",
    "ui-model-boundaries.md",
    "incident-report-quality.md",
]

# Closure report markers to avoid
CLOSURE_MARKERS = [
    "Close report",
    "CLOSED",
    "Successfully completed",
    "ACT Close",
]

# Required language in each subdoc
REQUIRED_LANGUAGE: dict[str, list[str]] = {
    "incidents.md": [
        "Incident owns case lifecycle",
        "artifacts own evidence truth",
        "ReviewPacketState",
        "EvidenceLink",
        "IncidentEvent",
    ],
    "next-checks.md": [
        "IncidentSuggestedCheck",
        "IncidentCheckExecution",
        "manual promotion",
        "compatibility",
    ],
    "review-packets.md": [
        "latest",
        "mutable",
        "not authoritative",
        "ReviewPacketState",
    ],
    "artifacts.md": [
        "immutable source of truth",
        "runs/health",
        "derived",
    ],
    "alertmanager-sources.md": [
        "registry",
        "authoritative",
        "per-run overrides",
        "append-only audit trail",
    ],
}

# Self-test fixtures
SELF_TEST_CASES: list[dict[str, object]] = [
    {
        "name": "oversized index",
        "setup": "a\n" * 221,
        "should_fail": True,
    },
    {
        "name": "missing linked subdoc",
        "setup": "# Data model\n\n",
        "should_fail": True,
    },
    {
        "name": "closure report marker in index",
        "setup": "# Data model\n\nACT Close\n",
        "should_fail": True,
    },
    {
        "name": "missing Incident bridge language",
        "setup": "# Data model\n\n",
        "subdocs": {
            "incidents.md": "Some content without the required phrases",
        },
        "should_fail": True,
    },
    {
        "name": "missing next-check mapping language",
        "setup": "# Data model\n\n- [incidents.md](data-model/incidents.md)\n",
        "subdocs": {
            "next-checks.md": "Some content without IncidentSuggestedCheck",
        },
        "should_fail": True,
    },
    {
        "name": "missing latest mirror warning",
        "setup": "# Data model\n\n- [review-packets.md](data-model/review-packets.md)\n",
        "subdocs": {
            "review-packets.md": "Some content without mutable/not authoritative",
        },
        "should_fail": True,
    },
    {
        "name": "valid docs pass",
        "setup": (
            "# Data model\n\n"
            "- [artifacts.md](data-model/artifacts.md)\n"
            "- [run-lifecycle.md](data-model/run-lifecycle.md)\n"
            "- [incidents.md](data-model/incidents.md)\n"
            "- [next-checks.md](data-model/next-checks.md)\n"
            "- [review-packets.md](data-model/review-packets.md)\n"
            "- [alertmanager-sources.md](data-model/alertmanager-sources.md)\n"
            "- [ui-model-boundaries.md](data-model/ui-model-boundaries.md)\n"
            "- [incident-report-quality.md](data-model/incident-report-quality.md)\n\n"
            "Incident owns case lifecycle. Artifacts own evidence truth.\n"
        ),
        "subdocs": {
            "artifacts.md": "immutable source of truth. runs/health. derived.\n",
            "run-lifecycle.md": "run_label, run_id, ClusterSnapshot, Assessment.\n",
            "incidents.md": "Incident owns case lifecycle. Artifacts own evidence truth. ReviewPacketState. EvidenceLink. IncidentEvent.\n",
            "next-checks.md": "IncidentSuggestedCheck. IncidentCheckExecution. manual promotion. compatibility.\n",
            "review-packets.md": "latest. mutable. not authoritative. ReviewPacketState.\n",
            "alertmanager-sources.md": "registry. authoritative. per-run overrides. append-only audit trail.\n",
            "ui-model-boundaries.md": "UI/API payloads are derived read models.\n",
            "incident-report-quality.md": "claim taxonomy, quality gates.\n",
        },
        "should_fail": False,
    },
]


def count_lines(path: Path) -> int:
    """Count lines in a file."""
    if not path.exists():
        return 0
    with open(path) as f:
        return len(f.readlines())


def read_file(path: Path) -> str:
    """Read file contents."""
    if not path.exists():
        return ""
    with open(path) as f:
        return f.read()


def check_index_size() -> tuple[bool, str]:
    """Check that docs/data-model.md exists and is <= 220 lines."""
    if not DATA_MODEL_MD.exists():
        return False, "docs/data-model.md does not exist"

    line_count = count_lines(DATA_MODEL_MD)
    if line_count > 220:
        return False, f"docs/data-model.md has {line_count} lines (max 220)"
    return True, f"docs/data-model.md: {line_count} lines (OK)"


def check_subdocs_linked() -> tuple[bool, str]:
    """Check that all required subdocs are linked from docs/data-model.md."""
    content = read_file(DATA_MODEL_MD)
    missing = []
    for subdoc in REQUIRED_SUBDOCS:
        link = f"data-model/{subdoc}"
        if link not in content:
            missing.append(subdoc)

    if missing:
        return False, f"Missing links to: {', '.join(missing)}"
    return True, f"All {len(REQUIRED_SUBDOCS)} subdocs linked"


def check_closure_markers() -> tuple[bool, str]:
    """Check that no closure markers exist in docs/data-model.md."""
    content = read_file(DATA_MODEL_MD)
    found = []
    for marker in CLOSURE_MARKERS:
        if marker.lower() in content.lower():
            found.append(marker)

    if found:
        return False, f"Closure markers found: {', '.join(found)}"
    return True, "No closure markers in index"


def check_subdoc_language(subdoc: str, requirements: list[str]) -> tuple[bool, str]:
    """Check that required language exists in a subdoc."""
    path = DATA_MODEL_DIR / subdoc
    if not path.exists():
        return False, f"{subdoc} does not exist"

    content = read_file(path)
    missing = []
    for phrase in requirements:
        if phrase.lower() not in content.lower():
            missing.append(phrase)

    if missing:
        return False, f"{subdoc} missing: {', '.join(missing)}"
    return True, f"{subdoc}: all required phrases present"


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== Data Model Documentation Hygiene ===\n")

    checks: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
        ("Index size", check_index_size),
        ("Subdocs linked", check_subdocs_linked),
        ("No closure markers", check_closure_markers),
    ]

    # Add subdoc language checks
    for subdoc, requirements in REQUIRED_LANGUAGE.items():
        subdoc_local = subdoc
        requirements_local = requirements
        checks.append((f"{subdoc_local} language", lambda s=subdoc_local, r=requirements_local: check_subdoc_language(s, r)))  # type: ignore[misc]

    all_passed = True
    results = []

    for name, check_fn in checks:
        passed, message = check_fn()
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {message}")
        results.append((name, passed))
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")
        failed = [name for name, passed in results if not passed]
        print(f"Failed checks: {', '.join(failed)}")

    return all_passed


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== Data Model Documentation Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_data_model = tmp_path / "data-model.md"
            tmp_data_model_dir = tmp_path / "data-model"
            tmp_data_model_dir.mkdir()

            # Setup main index
            setup_content = str(case["setup"])
            tmp_data_model.write_text(setup_content)

            # Setup subdocs if specified
            subdocs = case.get("subdocs")
            if subdocs:
                for subdoc, content in subdocs.items():
                    (tmp_data_model_dir / subdoc).write_text(str(content))

            # Override paths for this test
            global DATA_MODEL_MD, DATA_MODEL_DIR
            old_index = DATA_MODEL_MD
            old_dir = DATA_MODEL_DIR
            DATA_MODEL_MD = tmp_data_model
            DATA_MODEL_DIR = tmp_data_model_dir

            try:
                # Run verification checks
                checks: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
                    ("Index size", check_index_size),
                    ("Subdocs linked", check_subdocs_linked),
                    ("No closure markers", check_closure_markers),
                ]
                # Add subdoc language checks
                for subdoc, requirements in REQUIRED_LANGUAGE.items():
                    subdoc_local = subdoc
                    requirements_local = requirements
                    checks.append((f"{subdoc_local} language", lambda s=subdoc_local, r=requirements_local: check_subdoc_language(s, r)))  # type: ignore[misc]

                results = []
                for name, check_fn in checks:
                    passed, _message = check_fn()
                    results.append((name, passed))

                # For self-test, we expect failure on checks that should_fail
                expected_fail = bool(case["should_fail"])

                if expected_fail:
                    # At least one check should fail
                    any_failed = any(not passed for _name, passed in results)
                    if any_failed:
                        print("  [OK] Failed as expected")
                    else:
                        print("  [UNEXPECTED PASS] No checks failed")
                        print("  Expected: At least one FAIL")
                        all_passed = False
                else:
                    # All checks should pass
                    all_check_passed = all(passed for _name, passed in results)
                    if all_check_passed:
                        print("  [OK] Passed as expected")
                    else:
                        failed = [name for name, passed in results if not passed]
                        print(f"  [UNEXPECTED FAIL] Failed: {', '.join(failed)}")
                        all_passed = False

            finally:
                DATA_MODEL_MD = old_index
                DATA_MODEL_DIR = old_dir

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify data model documentation hygiene")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode with inline fixture cases",
    )
    args = parser.parse_args()

    if args.self_test:
        success = run_self_test()
    else:
        success = run_verification()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
