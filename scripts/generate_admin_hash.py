#!/usr/bin/env python3
"""Generate a password hash for the admin account.

This script generates a PBKDF2-HMAC-SHA256 password hash suitable for
use with the K9B_ADMIN_PASSWORD_HASH environment variable.

Usage:
    python scripts/generate_admin_hash.py
    python scripts/generate_admin_hash.py --password "my-secret-password"
    python scripts/generate_admin_hash.py --iterations 300000

The generated hash should be set as K9B_ADMIN_PASSWORD_HASH in your
environment or deployment configuration.

Example:
    export K9B_ADMIN_PASSWORD_HASH='$pbkdf2-sha256$600000$...'
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from k8s_diag_agent.ui.auth_password import hash_password, generate_password


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a password hash for K9B admin authentication.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate hash for a random password (prints password and hash)
  python scripts/generate_admin_hash.py

  # Generate hash for a specific password
  python scripts/generate_admin_hash.py --password "my-secret-password"

  # Generate hash with custom iterations (lower = faster but less secure)
  python scripts/generate_admin_hash.py --password "test" --iterations 100000

Environment:
  Set K9B_ADMIN_PASSWORD_HASH to the generated hash value.
  Set K9B_AUTH_ENABLED=true for production use.
        """,
    )

    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="Password to hash. If not provided, a random password will be generated.",
    )

    parser.add_argument(
        "--iterations",
        type=int,
        default=600000,
        help="Number of PBKDF2 iterations (default: 600000, OWASP 2023 recommendation)",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only output the hash, no explanatory text",
    )

    args = parser.parse_args()

    if args.password:
        password = args.password
        if not args.quiet:
            print("# Password provided on command line. Ensure proper shell history handling.")
    else:
        password = generate_password()
        if not args.quiet:
            print("# Generated random password. Save this now - it will not be shown again!")
            print()

    # Generate hash
    hash_value = hash_password(password, iterations=args.iterations)

    if args.quiet:
        print(hash_value)
    else:
        print("#" + "=" * 70)
        print("# K9B Admin Password Hash")
        print("#" + "=" * 70)
        print()
        if not args.password:
            print(f"# Generated Password: {password}")
            print()
        print(f"# Password Hash: {hash_value}")
        print()
        print("# Environment variable to set:")
        print(f"#   export K9B_ADMIN_PASSWORD_HASH='{hash_value}'")
        print()
        print("# For docker-compose or Kubernetes, add to your configuration:")
        print("#   env:")
        print("#     - name: K9B_ADMIN_USERNAME")
        print("#       value: admin")
        print("#     - name: K9B_ADMIN_PASSWORD_HASH")
        print(f"#       value: '{hash_value}'")
        print("#     - name: K9B_AUTH_ENABLED")
        print("#       value: 'true'")
        print("#     - name: K9B_SECURE_COOKIE")
        print("#       value: 'true'  # Enable for HTTPS deployments")
        print()
        print("# Security notes:")
        print("#   - Store credentials securely, never commit to version control")
        print("#   - Use K9B_SECURE_COOKIE=true when deploying behind HTTPS")
        print("#   - Consider using a secrets manager in production")
        print()


if __name__ == "__main__":
    main()