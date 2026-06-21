#!/usr/bin/env python3
"""Shell Containment Verifier CLI.

Verifies shell containment policy by scanning and validating shell scripts
against the inventory. Delegates to modular components for logic.

Usage:
    python scripts/verify_shell_containment.py           # Run verification
    python scripts/verify_shell_containment.py --json    # JSON output
    python scripts/verify_shell_containment.py --self-test  # Self-test mode
    python scripts/verify_shell_containment.py --verbose # Detailed output
"""

from __future__ import annotations

import argparse
import sys

from shell_containment_inventory import verify_shell_containment
from shell_containment_output import format_results
from shell_containment_selftest import run_self_test


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Shell containment verification gate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--json', action='store_true', help='JSON output')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--self-test', action='store_true', help='Run self-test validation')
    
    args = parser.parse_args()
    
    if args.self_test:
        print("Running self-test validation...")
        success, errors = run_self_test()
        if success:
            print("SELF-TEST: PASSED")
            print("All fixtures validated successfully.")
            return 0
        else:
            print("SELF-TEST: FAILED")
            for error in errors:
                print(f"  - {error}")
            return 1
    
    # Run verification
    result = verify_shell_containment()
    
    # Format and print results
    output = format_results(result, json_output=args.json, verbose=args.verbose)
    print(output)
    
    return 0 if result.success else 1


if __name__ == '__main__':
    sys.exit(main())
