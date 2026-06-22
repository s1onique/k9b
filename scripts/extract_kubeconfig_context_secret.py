#!/usr/bin/env python3
"""Extract a single kubeconfig context and encode it as base64 for GitHub secrets.

This script safely extracts only the specified context from a kubeconfig file,
validates that only one context is present, and outputs a single-line base64
string suitable for pasting into a GitHub environment secret.

Security posture:
- Never logs the extracted kubeconfig content.
- Never logs the base64 content unless --stdout is explicitly requested.
- Uses shell=False for all subprocess calls.
- Creates output files with mode 0600.
- Rejects repo-local output paths by default (fail-closed).
- Does not mutate kubeconfig or switch context.

Usage:
    scripts/extract_kubeconfig_context_secret.py \
        --context pve1-k3s-main \
        --kubeconfig ~/.kube/config

Exit codes:
    0 - Success
    1 - Error (validation failed, missing kubectl, missing source, etc.)
"""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Default values
DEFAULT_CONTEXT = "pve1-k3s-main"
DEFAULT_KUBECONFIG = Path.home() / ".kube" / "config"
KUBECTL = "kubectl"

# Required kubeconfig structural markers for cheap validation
REQUIRED_MARKERS = ["apiVersion:", "kind: Config", "clusters:", "contexts:", "users:"]


def build_extraction_argv(
    kubectl_path: str,
    kubeconfig_path: Path,
    context: str,
) -> list[str]:
    """Build kubectl extraction command as list (no shell).

    Args:
        kubectl_path: Path to kubectl binary.
        kubeconfig_path: Path to source kubeconfig.
        context: Kubernetes context name to extract.

    Returns:
        List of command arguments for subprocess.
    """
    return [
        kubectl_path,
        "config",
        "view",
        "--kubeconfig", str(kubeconfig_path),
        "--context", context,
        "--minify",
        "--flatten",
        "--raw",
        "-o", "yaml",
    ]


def encode_base64_one_line(data: bytes) -> str:
    """Encode bytes as single-line base64 string.

    Args:
        data: Bytes to encode.

    Returns:
        Base64-encoded string with no embedded newlines.
    """
    return base64.b64encode(data).decode("ascii")


def resolve_default_output_path(context: str) -> Path:
    """Resolve default output path for base64-encoded kubeconfig.

    Default path is outside the repo to prevent accidental commits.

    Args:
        context: Context name for filename.

    Returns:
        Path to output file under /tmp.
    """
    return Path(f"/tmp/k9b-admin-kubeconfig-{context}.b64")


def is_repo_path(path: Path) -> bool:
    """Check if path is inside the git repository.

    Args:
        path: Path to check.

    Returns:
        True if path is inside the repo tree.
    """
    try:
        repo_root = Path(__file__).parent.parent.resolve()
        path_resolved = path.resolve()
        path_resolved.relative_to(repo_root)
        return True
    except ValueError:
        return False


def validate_kubeconfig_content(content: str) -> bool:
    """Validate kubeconfig contains required structural markers.

    This is a cheap guard to catch obvious misconfiguration.
    Does not require PyYAML.

    Args:
        content: Raw kubeconfig content.

    Returns:
        True if all required markers are present.
    """
    for marker in REQUIRED_MARKERS:
        if marker not in content:
            return False
    return True


def validate_single_context(
    kubectl_path: str,
    kubeconfig_bytes: bytes,
    expected_context: str,
) -> tuple[bool, str]:
    """Validate extracted kubeconfig has exactly one context matching expected.

    Uses a secure temporary file to avoid leaking credentials.

    Args:
        kubectl_path: Path to kubectl binary.
        kubeconfig_bytes: Raw kubeconfig bytes.
        expected_context: Expected context name.

    Returns:
        Tuple of (success, error_message).
    """
    # Write to secure temp file
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".kubeconfig", delete=False) as f:
        f.write(kubeconfig_bytes)
        temp_path = f.name

    try:
        # Set restrictive permissions
        os.chmod(temp_path, 0o600)

        # Check get-contexts returns exactly one context
        try:
            result_get = subprocess.run(
                [kubectl_path, "--kubeconfig", temp_path, "config", "get-contexts", "-o", "name"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return False, f"kubectl not found: {kubectl_path}"
        if result_get.returncode != 0:
            return False, f"kubectl config get-contexts failed: {result_get.stderr}"

        contexts = [line.strip() for line in result_get.stdout.strip().split("\n") if line.strip()]
        if len(contexts) != 1:
            return False, f"Expected 1 context, got {len(contexts)}: {contexts}"

        if contexts[0] != expected_context:
            return False, f"Expected context '{expected_context}', got '{contexts[0]}'"

        # Check current-context matches
        try:
            result_current = subprocess.run(
                [kubectl_path, "--kubeconfig", temp_path, "config", "current-context"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return False, f"kubectl not found: {kubectl_path}"
        if result_current.returncode != 0:
            return False, f"kubectl config current-context failed: {result_current.stderr}"

        current = result_current.stdout.strip()
        if current != expected_context:
            return False, f"Current context mismatch: expected '{expected_context}', got '{current}'"

        return True, ""

    finally:
        # Clean up temp file
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def extract_kubeconfig(
    kubectl_path: str,
    kubeconfig_path: Path,
    context: str,
) -> tuple[bytes, str]:
    """Extract kubeconfig context using kubectl.

    Args:
        kubectl_path: Path to kubectl binary.
        kubeconfig_path: Path to source kubeconfig.
        context: Context name to extract.

    Returns:
        Tuple of (kubeconfig_bytes, error_message).
        On success, error_message is empty.
    """
    argv = build_extraction_argv(kubectl_path, kubeconfig_path, context)
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return b"", f"kubectl not found: {kubectl_path}"

    if result.returncode != 0:
        return b"", f"kubectl failed with exit code {result.returncode}: {result.stderr}"

    return result.stdout.encode("utf-8"), ""


def write_output_file(path: Path, content: str, force: bool = False) -> str:
    """Write base64 content to file with restrictive permissions.

    Args:
        path: Output file path.
        content: Content to write.
        force: Whether to overwrite existing file.

    Returns:
        Error message if failed, empty string on success.
    """
    if path.exists() and not force:
        return f"Output file exists: {path}. Use --force to overwrite."

    try:
        with open(path, "w") as f:
            f.write(content)
        os.chmod(path, 0o600)
        return ""
    except OSError as e:
        return f"Failed to write output file: {e}"


def run(
    *,
    context: str,
    kubeconfig: Path,
    output: Path | None,
    stdout: bool,
    dry_run: bool,
    force: bool,
    allow_repo_output: bool,
    kubectl_path: str,
) -> int:
    """Run the extraction workflow.

    Args:
        context: Kubernetes context name.
        kubeconfig: Source kubeconfig path.
        output: Explicit output path, or None for default.
        stdout: Print base64 to stdout instead of file.
        dry_run: Perform validation but don't write output.
        force: Allow overwriting existing output file.
        allow_repo_output: Allow output path inside repo.
        kubectl_path: Path to kubectl binary.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    # Validate source kubeconfig exists
    if not kubeconfig.exists():
        print(f"ERROR: Source kubeconfig not found: {kubeconfig}", file=sys.stderr)
        return 1

    # Resolve output path
    if output is None:
        output = resolve_default_output_path(context)

    # Check for repo-local output (fail closed)
    if is_repo_path(output) and not allow_repo_output:
        print(
            f"ERROR: Output path is inside the repository: {output}",
            file=sys.stderr,
        )
        print(
            "ERROR: Refusing to write potential secret to repo.",
            file=sys.stderr,
        )
        print(
            "ERROR: Use --allow-repo-output to override (not recommended).",
            file=sys.stderr,
        )
        return 1

    # Extract kubeconfig
    kubeconfig_bytes, error = extract_kubeconfig(kubectl_path, kubeconfig, context)
    if error:
        print(f"ERROR: Extraction failed: {error}", file=sys.stderr)
        return 1

    if not kubeconfig_bytes:
        print("ERROR: Extraction returned empty content", file=sys.stderr)
        return 1

    # Validate structural markers
    content_str = kubeconfig_bytes.decode("utf-8")
    if not validate_kubeconfig_content(content_str):
        print(
            "ERROR: Extracted content missing required kubeconfig markers",
            file=sys.stderr,
        )
        return 1

    # Validate single context
    valid, validation_error = validate_single_context(
        kubectl_path, kubeconfig_bytes, context
    )
    if not valid:
        print(f"ERROR: Validation failed: {validation_error}", file=sys.stderr)
        return 1

    # Encode to base64
    b64_content = encode_base64_one_line(kubeconfig_bytes)

    # Dry run - don't write anything
    if dry_run:
        print("=== Dry-run mode - no output written ===", file=sys.stderr)
        print(f"Source kubeconfig: {kubeconfig}", file=sys.stderr)
        print(f"Context: {context}", file=sys.stderr)
        print(f"Extracted kubeconfig bytes: {len(kubeconfig_bytes)}", file=sys.stderr)
        print(f"Base64 bytes: {len(b64_content)}", file=sys.stderr)
        print(f"Output would be: {output}", file=sys.stderr)
        return 0

    # Stdout mode - print only base64 to stdout
    if stdout:
        print(b64_content)
        return 0

    # File mode - write to output file
    error = write_output_file(output, b64_content, force=force)
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    # Print status to stderr (not stdout)
    print(f"Extracted kubeconfig context: {context}", file=sys.stderr)
    print(f"Source kubeconfig: {kubeconfig}", file=sys.stderr)
    print(f"Output file: {output}", file=sys.stderr)
    print(f"Extracted kubeconfig bytes: {len(kubeconfig_bytes)}", file=sys.stderr)
    print(f"Base64 bytes: {len(b64_content)}", file=sys.stderr)
    print("Output file permissions: 0600", file=sys.stderr)
    print("", file=sys.stderr)
    print("Paste the contents of the output file into:", file=sys.stderr)
    print(
        "GitHub -> Settings -> Environments -> k9b-live-lab-admin -> "
        "Environment secrets -> K9B_LIVE_LAB_ADMIN_KUBECONFIG_B64",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    print("REMINDER: the output is a secret. Do not commit it.", file=sys.stderr)

    return 0


def create_arg_parser() -> argparse.ArgumentParser:
    """Create argument parser.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Extract a single kubeconfig context and encode as base64 "
            "for GitHub environment secrets."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract with defaults (pve1-k3s-main from ~/.kube/config)
  scripts/extract_kubeconfig_context_secret.py

  # Extract specific context
  scripts/extract_kubeconfig_context_secret.py --context pve1-k3s-main

  # Custom kubeconfig source
  scripts/extract_kubeconfig_context_secret.py --kubeconfig /path/to/config

  # Dry-run mode (validate but don't write)
  scripts/extract_kubeconfig_context_secret.py --dry-run

  # Print base64 to stdout (for piping)
  scripts/extract_kubeconfig_context_secret.py --stdout

Security notes:
  - Output file is created with mode 0600.
  - Repo-local output paths are rejected by default.
  - No kubeconfig or base64 content is printed by default.
  - Use --stdout to print base64 for copy/paste workflows.
        """,
    )

    parser.add_argument(
        "--context",
        default=DEFAULT_CONTEXT,
        help=f"Kubernetes context name to extract (default: {DEFAULT_CONTEXT})",
    )
    parser.add_argument(
        "--kubeconfig",
        type=Path,
        default=DEFAULT_KUBECONFIG,
        help=f"Source kubeconfig path (default: {DEFAULT_KUBECONFIG})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: /tmp/k9b-admin-kubeconfig-<context>.b64)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print base64 string to stdout instead of writing to file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform extraction and validation, but do not write output",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting an existing output file",
    )
    parser.add_argument(
        "--allow-repo-output",
        action="store_true",
        help="Allow output path inside the repository (not recommended for secrets)",
    )
    parser.add_argument(
        "--kubectl",
        default=KUBECTL,
        help=f"Path to kubectl binary (default: {KUBECTL})",
    )

    return parser


def main() -> int:
    """Main entry point.

    Returns:
        Exit code.
    """
    parser = create_arg_parser()
    args = parser.parse_args()

    return run(
        context=args.context,
        kubeconfig=args.kubeconfig,
        output=args.output,
        stdout=args.stdout,
        dry_run=args.dry_run,
        force=args.force,
        allow_repo_output=args.allow_repo_output,
        kubectl_path=args.kubectl,
    )


if __name__ == "__main__":
    sys.exit(main())
