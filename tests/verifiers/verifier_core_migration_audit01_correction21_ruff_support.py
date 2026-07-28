"""CORRECTION21: Hermetic Ruff evidence capability for tests.

This module provides a deterministic, hermetic Ruff capability
that can be injected into the range evidence tests. It:

1. Creates a temporary Python module that behaves like Ruff
2. Exposes deterministic executable identity and SHA-256
3. Executes through the production process runner
4. Records argv losslessly for identity verification
5. Supports unusual filename boundaries (spaces, Unicode, newlines)

The capability is designed to test the Ruff identity resolution
and evidence collection without depending on host-installed Ruff.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.verifiers_audit.range_evidence_identity import RuffIdentity

#: Known SHA-256 for the hermetic capability (all zeros for test fixture)
HERMETIC_CAPABILITY_SHA256 = "0" * 64


class HermeticRuffCapability:
    """A deterministic Ruff-compatible capability for testing.

    This capability creates a temporary Python module that:
    - Returns exit code 0 (success)
    - Writes argv to a JSON file for identity verification
    - Supports unusual path names
    """

    def __init__(
        self,
        tmp_path: Path,
        *,
        identity_kind: str = "hermetic_test",
    ) -> None:
        self.tmp_path = tmp_path
        self.identity_kind = identity_kind
        self._create_capability()

    def _create_capability(self) -> None:
        """Create the temporary Python module that behaves like Ruff."""
        # Create the hermetic ruff module
        module_dir = self.tmp_path / "hermetic_ruff"
        module_dir.mkdir(parents=True, exist_ok=True)

        # Create __init__.py
        init_path = module_dir / "__init__.py"
        init_path.write_text("# Hermetic Ruff capability\n", encoding="utf-8")

        # Create the ruff module
        ruff_module = module_dir / "ruff.py"
        argv_log = self.tmp_path / "hermetic_ruff_argv.json"

        ruff_module.write_text(
            f'''
"""Hermetic Ruff capability for testing.

This module simulates Ruff behavior for evidence tests.
It writes argv to {argv_log.name} for identity verification.
"""
import json
import sys

def main() -> int:
    """Simulate Ruff: write argv to log and exit 0."""
    argv_log = Path(__file__).parent.parent / "{argv_log.name}"
    with open(argv_log, "w", encoding="utf-8") as f:
        json.dump({{
            "argv": sys.argv,
            "cwd": str(Path.cwd()),
        }}, f)
    return 0

if __name__ == "__main__":
    sys.exit(main())
''',
            encoding="utf-8",
        )

        # Create the ruff binary wrapper
        ruff_binary = self.tmp_path / "hermetic_ruff"
        ruff_binary.write_text(
            '''#!/usr/bin/env python3
"""Hermetic Ruff binary wrapper for testing."""
import sys
import json
from pathlib import Path

argv_log = Path(__file__).parent / "hermetic_ruff_argv.json"

def main() -> int:
    """Simulate Ruff: write argv to log and exit 0."""
    with open(argv_log, "w", encoding="utf-8") as f:
        json.dump({
            "argv": sys.argv,
            "cwd": str(Path.cwd()),
        }, f)
    return 0

if __name__ == "__main__":
    sys.exit(main())
''',
            encoding="utf-8",
        )
        ruff_binary.chmod(0o755)

        # Create the module launcher
        module_launcher = self.tmp_path / "run_hermetic_ruff.py"
        module_launcher.write_text(
            '''#!/usr/bin/env python3
"""Launcher for hermetic ruff module."""
import sys
import json
from pathlib import Path

argv_log = Path(__file__).parent / "hermetic_ruff_argv.json"

def main() -> int:
    """Simulate 'python -m hermetic_ruff.ruff'."""
    with open(argv_log, "w", encoding="utf-8") as f:
        json.dump({
            "argv": sys.argv,
            "cwd": str(Path.cwd()),
        }, f)
    return 0

if __name__ == "__main__":
    sys.exit(main())
''',
            encoding="utf-8",
        )
        module_launcher.chmod(0o755)

        # Calculate SHA-256 of the capability
        self.executable = ruff_binary
        self.module_launcher = module_launcher
        self.argv_log = argv_log

        # Compute deterministic SHA-256 for the capability
        sha256 = hashlib.sha256()
        sha256.update(ruff_binary.read_bytes())
        self.sha256 = sha256.hexdigest()

    def get_module_identity(self) -> RuffIdentity:
        """Return the module-style identity for 'python -m hermetic_ruff.ruff'."""

        return {
            "launcher_argv_prefix": (sys.executable, "-m", "hermetic_ruff.ruff"),
            "launcher_path": sys.executable,
            "launcher_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            "ruff_version": "0.0.0 (hermetic)",
            "ruff_invocation_mode": "module",
        }

    def get_binary_identity(self) -> RuffIdentity:
        """Return the binary-style identity for the standalone ruff binary."""

        return {
            "launcher_argv_prefix": (str(self.executable),),
            "launcher_path": str(self.executable),
            "launcher_sha256": self.sha256,
            "ruff_version": "0.0.0 (hermetic)",
            "ruff_invocation_mode": "binary",
        }

    def get_recorded_argv(self) -> list[str]:
        """Return the argv that was recorded during execution."""
        if not self.argv_log.exists():
            return []
        with open(self.argv_log, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("argv", [])

    def execute_via_module(
        self,
        python_paths: tuple[str, ...],
        cwd: Path,
    ) -> subprocess.CompletedProcess[bytes]:
        """Execute via 'python -m hermetic_ruff.ruff'."""
        return subprocess.run(
            [sys.executable, "-m", "hermetic_ruff.ruff", "check", *python_paths],
            cwd=str(cwd),
            capture_output=True,
        )

    def execute_via_binary(
        self,
        python_paths: tuple[str, ...],
        cwd: Path,
    ) -> subprocess.CompletedProcess[bytes]:
        """Execute via the standalone binary."""
        return subprocess.run(
            [str(self.executable), "check", *python_paths],
            cwd=str(cwd),
            capture_output=True,
        )


def build_hermetic_ruff_capability(
    tmp_path: Path,
) -> HermeticRuffCapability:
    """Build a hermetic Ruff capability for testing."""
    return HermeticRuffCapability(tmp_path)


def inject_hermetic_resolver(
    orchestrator_module,
    capability: HermeticRuffCapability,
) -> None:
    """Inject a hermetic Ruff resolver into the orchestrator.

    This patches the orchestrator's resolve_ruff_identity function
    to return the hermetic capability's identity.
    """
    import scripts.verifiers_audit.range_evidence_identity as identity_module

    def hermetic_resolve(
        *,
        repo_root: Path,
        python_paths: tuple[str, ...] = (),
    ):
        if not python_paths:
            # Empty range: return skipped identity
            return {
                "launcher_argv_prefix": (),
                "launcher_path": None,
                "launcher_sha256": None,
                "ruff_version": None,
                "ruff_invocation_mode": "skipped_no_python_paths",
            }
        # Return the hermetic binary identity
        return capability.get_binary_identity()

    # Patch at module level
    identity_module.resolve_ruff_identity = hermetic_resolve
    orchestrator_module.resolve_ruff_identity = hermetic_resolve


def restore_original_resolver(
    orchestrator_module,
    original_resolver,
) -> None:
    """Restore the original Ruff resolver after patching."""
    import scripts.verifiers_audit.range_evidence_identity as identity_module

    identity_module.resolve_ruff_identity = original_resolver
    orchestrator_module.resolve_ruff_identity = original_resolver
