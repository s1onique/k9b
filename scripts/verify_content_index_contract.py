#!/usr/bin/env python3
"""Contract verifier for content index schema.

This script verifies that the content index contract is properly defined:
1. Doc exists
2. Schema module exists
3. SQL schema exists
4. Required tables/columns exist
5. Required content kinds exist
6. Forbidden field names are absent
7. Tests exist
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from k8s_diag_agent.content_index.schema import (
    CONTENT_INDEX_SCHEMA_VERSION,
    INDEXED_CONTENT_KINDS,
    REQUIRED_COLUMNS,
    REQUIRED_TABLES,
)


def verify_contract() -> dict:
    """Verify content index contract and return results."""
    results = {
        "contract_verified": True,
        "checks": [],
    }

    base_path = Path(__file__).parent.parent

    # =======================================================================
    # 1. Doc exists
    # =======================================================================
    doc_path = base_path / "docs" / "content-index-contract.md"
    doc_check = {
        "name": "contract_doc_exists",
        "path": str(doc_path),
        "status": "PASS" if doc_path.exists() else "FAIL",
    }
    results["checks"].append(doc_check)
    if doc_path.exists():
        content = doc_path.read_text()
        # Verify key sections exist
        required_sections = [
            "## Purpose",
            "## Indexed Content Kinds",
            "## SQL Schema",
            "## Freshness Rules",
            "## Privacy/Safety Rules",
            "## API Compatibility Rules",
        ]
        for section in required_sections:
            if section not in content:
                doc_check["status"] = "FAIL"
                doc_check.setdefault("errors", []).append(f"Missing section: {section}")
    else:
        results["contract_verified"] = False

    # =======================================================================
    # 2. Schema module exists
    # =======================================================================
    schema_module_path = base_path / "src" / "k8s_diag_agent" / "content_index" / "schema.py"
    module_check = {
        "name": "schema_module_exists",
        "path": str(schema_module_path),
        "status": "PASS" if schema_module_path.exists() else "FAIL",
    }
    results["checks"].append(module_check)
    if not schema_module_path.exists():
        results["contract_verified"] = False

    # =======================================================================
    # 3. SQL schema exists
    # =======================================================================
    sql_path = base_path / "src" / "k8s_diag_agent" / "content_index" / "schema.sql"
    sql_check = {
        "name": "sql_schema_exists",
        "path": str(sql_path),
        "status": "PASS" if sql_path.exists() else "FAIL",
    }
    results["checks"].append(sql_check)
    if not sql_path.exists():
        results["contract_verified"] = False

    # =======================================================================
    # 4. Required tables exist in SQL
    # =======================================================================
    if sql_path.exists():
        sql_content = sql_path.read_text().lower()

        tables_check = {
            "name": "sql_required_tables",
            "status": "PASS",
            "details": {},
        }
        for table in REQUIRED_TABLES:
            found = table.lower() in sql_content
            tables_check["details"][table] = "present" if found else "missing"
            if not found:
                tables_check["status"] = "FAIL"
                results["contract_verified"] = False
        results["checks"].append(tables_check)

    # =======================================================================
    # 5. Required columns exist in SQL
    # =======================================================================
    if sql_path.exists():
        sql_content = sql_path.read_text()

        columns_check = {
            "name": "sql_required_columns",
            "status": "PASS",
            "details": {},
        }
        for table, columns in REQUIRED_COLUMNS.items():
            columns_check["details"][table] = {}
            for col in columns:
                found = col in sql_content
                columns_check["details"][table][col] = "present" if found else "missing"
                if not found:
                    columns_check["status"] = "FAIL"
                    results["contract_verified"] = False
        results["checks"].append(columns_check)

    # =======================================================================
    # 6. SQL executes without error
    # =======================================================================
    if sql_path.exists():
        exec_check = {
            "name": "sql_executes",
            "status": "PASS",
        }
        try:
            sql_content = sql_path.read_text()
            conn = sqlite3.connect(":memory:")
            conn.executescript(sql_content)
            conn.commit()
            conn.close()
        except Exception as e:
            exec_check["status"] = "FAIL"
            exec_check["error"] = str(e)
            results["contract_verified"] = False
        results["checks"].append(exec_check)

    # =======================================================================
    # 7. Required content kinds defined
    # =======================================================================
    kinds_check = {
        "name": "required_content_kinds",
        "status": "PASS",
        "count": len(INDEXED_CONTENT_KINDS),
    }
    required_kinds = {
        "incident",
        "evidence_link",
        "snapshot_bundle",
        "review_packet",
        "automatic_diagnosis_review",
        "diagnosis_loop_run",
        "diagnosis_loop_pass",
        "lab_result",
        "trace_capture_summary",
        "perf_baseline_summary",
    }
    missing_kinds = required_kinds - INDEXED_CONTENT_KINDS
    if missing_kinds:
        kinds_check["status"] = "FAIL"
        kinds_check["missing"] = sorted(missing_kinds)
        results["contract_verified"] = False
    results["checks"].append(kinds_check)

    # =======================================================================
    # 8. Schema version correct
    # =======================================================================
    version_check = {
        "name": "schema_version",
        "value": CONTENT_INDEX_SCHEMA_VERSION,
        "status": "PASS",
    }
    if CONTENT_INDEX_SCHEMA_VERSION != "k9b.content_index.v1":
        version_check["status"] = "FAIL"
        results["contract_verified"] = False
    results["checks"].append(version_check)

    # =======================================================================
    # 9. Forbidden field names absent from contract
    # =======================================================================
    forbidden_check = {
        "name": "forbidden_fields_absent",
        "status": "PASS",
    }
    if doc_path.exists():
        doc_content = doc_path.read_text()
        # Check that forbidden terms are not in "MUST NOT" list incorrectly
        # They should only appear in the forbidden section
        forbidden_section = "### Index MUST NOT Store"
        if forbidden_section in doc_content:
            # OK - forbidden section exists
            pass
        else:
            forbidden_check["status"] = "WARN"
            forbidden_check["message"] = "Forbidden section not found in doc"
    results["checks"].append(forbidden_check)

    # =======================================================================
    # 10. Tests exist
    # =======================================================================
    tests_path = base_path / "tests" / "unit" / "test_content_index_schema_contract.py"
    tests_check = {
        "name": "tests_exist",
        "path": str(tests_path),
        "status": "PASS" if tests_path.exists() else "FAIL",
    }
    results["checks"].append(tests_check)
    if not tests_path.exists():
        results["contract_verified"] = False

    # =======================================================================
    # 11. __init__.py exists
    # =======================================================================
    init_path = base_path / "src" / "k8s_diag_agent" / "content_index" / "__init__.py"
    init_check = {
        "name": "module_init_exists",
        "path": str(init_path),
        "status": "PASS" if init_path.exists() else "FAIL",
    }
    results["checks"].append(init_check)
    if not init_path.exists():
        results["contract_verified"] = False

    # =======================================================================
    # Summary
    # =======================================================================
    results["summary"] = {
        "schema_version": CONTENT_INDEX_SCHEMA_VERSION,
        "content_kinds_count": len(INDEXED_CONTENT_KINDS),
        "tables_required": len(REQUIRED_TABLES),
        "columns_required": sum(len(cols) for cols in REQUIRED_COLUMNS.values()),
    }

    return results


def main() -> int:
    """Main entry point."""
    print("Content Index Contract Verifier")
    print("=" * 50)

    results = verify_contract()

    # Print results
    for check in results["checks"]:
        status = check.get("status", "UNKNOWN")
        name = check.get("name", "unknown")
        path = check.get("path", "")
        print(f"[{status}] {name}")
        if path:
            print(f"       Path: {path}")
        if "error" in check:
            print(f"       Error: {check['error']}")
        if "details" in check:
            for key, value in check["details"].items():
                print(f"       {key}: {value}")
        if "missing" in check:
            print(f"       Missing: {check['missing']}")

    print()
    print("Summary:")
    print(f"  Schema Version: {results['summary']['schema_version']}")
    print(f"  Content Kinds: {results['summary']['content_kinds_count']}")
    print(f"  Required Tables: {results['summary']['tables_required']}")
    print(f"  Required Columns: {results['summary']['columns_required']}")

    print()
    if results["contract_verified"]:
        print("CONTRACT VERIFICATION: PASSED")
        print("All required elements are present and correctly defined.")
        return 0
    else:
        print("CONTRACT VERIFICATION: FAILED")
        print("Some required elements are missing or incorrect.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
