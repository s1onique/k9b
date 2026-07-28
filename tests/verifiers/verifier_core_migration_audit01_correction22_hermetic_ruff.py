"""CORRECTION22: Single deterministic hermetic Ruff capability for tests.

This module provides one executable Python script that behaves like Ruff
for evidence tests. It:

1. Uses `sys.executable` + explicit script path (no shebang)
2. Records argv losslessly to a JSON file
3. Returns configurable exit status
4. Supports spaces, newlines, and Unicode arguments
5. Provides real SHA-256 of the script bytes

The capability is used via fixture-scoped monkeypatching of the resolver.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

# =============================================================================
# Hermetic Ruff Script (written to tmp_path and executed via sys.executable)
# =============================================================================


def generate_hermetic_ruff_script(tmp_dir: Path) -> tuple[Path, str]:
    """Generate the hermetic Ruff script and return (script_path, sha256).

    The script:
    - accepts Ruff-style arguments (check, format, etc.)
    - writes sys.argv and cwd to a JSON log
    - returns exit 0 by default, configurable via env var
    """
    tmp_dir.mkdir(parents=True, exist_ok=True)
    script_path = tmp_dir / "hermetic_ruff.py"
    sha256_hash = hashlib.sha256()

    content = '''\
"""Hermetic Ruff for testing: accepts arguments, logs argv, returns exit 0."""
import json
import os
import sys
from pathlib import Path

def main() -> int:
    """Simulate Ruff: log argv and return configured exit status."""
    log_path = Path(__file__).parent / "hermetic_ruff_argv.json"
    exit_override = os.environ.get("HERMETIC_RUFF_EXIT", "0")

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "argv": sys.argv,
            "cwd": str(Path.cwd()),
            "exit_override": exit_override,
        }, f)

    try:
        return int(exit_override)
    except ValueError as exc:
        raise SystemExit(
            f"invalid HERMETIC_RUFF_EXIT={exit_override!r}"
        ) from exc

if __name__ == "__main__":
    sys.exit(main())
'''

    script_path.write_text(content, encoding="utf-8")
    script_path.chmod(0o755)

    # Calculate real SHA-256
    sha256_hash.update(script_path.read_bytes())

    return script_path, sha256_hash.hexdigest()


# =============================================================================
# Hermetic Ruff Capability
# =============================================================================


class HermeticRuffCapability:
    """A deterministic Ruff-compatible capability for testing.

    Attributes:
        launcher_argv_prefix: (sys.executable, script_path) - the authority
        launcher_path: sys.executable
        launcher_sha256: SHA-256 of sys.executable
        ruff_version: "0.0.0 (hermetic)"
        ruff_invocation_mode: "hermetic_test_script"
        script_path: Path to the hermetic ruff script
        script_sha256: SHA-256 of the script bytes
        argv_log_path: Path where executed argv is recorded
    """

    def __init__(self, tmp_dir: Path) -> None:
        self.tmp_dir = tmp_dir
        self.script_path, self.script_sha256 = generate_hermetic_ruff_script(tmp_dir)

        # The launcher is the Python interpreter
        self.launcher_path = Path(sys.executable)
        self.launcher_sha256 = hashlib.sha256(self.launcher_path.read_bytes()).hexdigest()

        # The identity authority is (interpreter, script)
        self.launcher_argv_prefix = (sys.executable, str(self.script_path))
        self.ruff_version = "0.0.0 (hermetic)"
        self.ruff_invocation_mode = "hermetic_test_script"

        # Log file for recorded argv
        self.argv_log_path = self.tmp_dir / "hermetic_ruff_argv.json"

    def get_identity(self) -> dict[str, object]:
        """Return the RuffIdentity-compatible dict for this capability."""
        return {
            "launcher_argv_prefix": self.launcher_argv_prefix,
            "launcher_path": str(self.launcher_path),
            "launcher_sha256": self.launcher_sha256,
            "tool_payload_path": str(self.script_path),
            "tool_payload_sha256": self.script_sha256,
            "ruff_version": self.ruff_version,
            "ruff_invocation_mode": self.ruff_invocation_mode,
            "configuration_files": [],
            "configuration_file_sha256": {},
        }

    def get_recorded_argv(self) -> list[str]:
        """Return the argv recorded during the last execution."""
        if not self.argv_log_path.exists():
            return []
        with open(self.argv_log_path, encoding="utf-8") as f:
            data = json.load(f)
        return list(data.get("argv", []))

    def execute(self, extra_args: tuple[str, ...] = ()) -> subprocess.CompletedProcess[bytes]:
        """Execute the hermetic ruff via sys.executable."""
        import subprocess

        return subprocess.run(
            [sys.executable, str(self.script_path), *extra_args],
            capture_output=True,
        )


# =============================================================================
# Fixture
# =============================================================================


def build_hermetic_capability(tmp_path: Path) -> HermeticRuffCapability:
    """Build a hermetic Ruff capability for testing."""
    return HermeticRuffCapability(tmp_path)


# =============================================================================
# Standalone test
# =============================================================================


if __name__ == "__main__":
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        cap = build_hermetic_capability(Path(tmpdir))

        print(f"Script: {cap.script_path}")
        print(f"Script SHA-256: {cap.script_sha256}")
        print(f"Launcher: {cap.launcher_path}")
        print(f"Launcher SHA-256: {cap.launcher_sha256}")
        print(f"Argv prefix: {cap.launcher_argv_prefix}")

        # Execute
        result = cap.execute(("check", "src/", "tests/"))
        print(f"Exit code: {result.returncode}")

        recorded = cap.get_recorded_argv()
        print(f"Recorded argv: {recorded}")

        # When executed via subprocess.run([sys.executable, script_path, ...]),
        # argv[0] is set to script_path (Python's behavior)
        assert recorded[0] == str(cap.script_path)
        assert recorded[1:] == ["check", "src/", "tests/"]
        print("PASS: argv matches")


def install_hermetic_ruff_resolver(
    *,
    monkeypatch: pytest.MonkeyPatch,
    capability: HermeticRuffCapability,
) -> None:
    """Install hermetic Ruff resolver via monkeypatch.

    Patches resolve_ruff_identity at the identity module where it is defined.
    This is the single authoritative seam for resolver injection.
    The orchestrator also imports the function, so we patch both.
    """
    import scripts.verifiers_audit.range_evidence_identity as identity_module
    import scripts.verifiers_audit.range_evidence_orchestrator as orchestrator_module

    def hermetic_resolve(*, repo_root: Path, python_paths: tuple[str, ...] = ()):
        if not python_paths:
            return {
                "launcher_argv_prefix": (),
                "launcher_path": None,
                "launcher_sha256": None,
                "ruff_version": None,
                "ruff_invocation_mode": "skipped_no_python_paths",
                "configuration_files": [],
                "configuration_file_sha256": {},
            }
        return capability.get_identity()

    # Patch both the identity module (where it's defined) and orchestrator (local binding)
    monkeypatch.setattr(identity_module, "resolve_ruff_identity", hermetic_resolve)
    monkeypatch.setattr(orchestrator_module, "resolve_ruff_identity", hermetic_resolve)
