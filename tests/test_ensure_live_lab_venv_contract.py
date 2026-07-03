"""Regression tests for ensure_live_lab_venv.sh python_bin contract handling.

Ensures the script handles the Python path contract correctly:
- Receives a directory (toolcache-style .../x64/bin) OR an executable
- Normalizes directories to the actual python/python3 executable
- Fails with clear error when normalization is impossible

Split from test_k9b_live_lab_toolchain_action.py to keep files under 500 lines.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def subprocess_run(*args: Any, **kwargs: Any) -> Any:
    """Import and call subprocess.run (avoid __future__ annotation issues in this file)."""
    import subprocess  # pylint: disable=import-outside-toplevel
    return subprocess.run(*args, **kwargs)  # pylint: disable= subprocess-run-return-list


class TestEnsureLiveLabVenvContract:
    """Regression tests for ensure_live_lab_venv.sh python_bin contract handling."""

    def test_ensure_venv_script_handles_toolcache_bin_directory(
        self, tmp_path: Path
    ) -> None:
        """ensure_live_lab_venv.sh should normalize toolcache-style bin directory.

        This guards against GitHub Actions outputs that pass .../x64/bin (directory)
        instead of .../x64/bin/python (executable), which causes exit 126.
        """
        # tests/test_ensure_live_lab_venv_contract.py -> tests/ -> project root
        project_root = Path(__file__).parent.parent
        script = project_root / "scripts/ci/ensure_live_lab_venv.sh"
        assert script.exists(), f"ensure_live_lab_venv.sh not found at {script}"

        # Create a fake bin directory (simulating toolcache-style .../x64/bin)
        fake_bin = tmp_path / "Python" / "3.13.14" / "x64" / "bin"
        fake_bin.mkdir(parents=True)
        # Create a symlink to the real system python
        real_python = Path(sys.executable).parent
        system_python = real_python / "python3"
        if not system_python.exists():
            system_python = real_python / "python"
        fake_python = fake_bin / "python"
        if system_python.exists():
            fake_python.symlink_to(system_python)
        else:
            # Fallback: just create a wrapper
            fake_python.write_text(
                f"#!/usr/bin/env bash\nexec {sys.executable} \"$@\"\n"
            )
            fake_python.chmod(0o755)

        # Use the actual requirements-live-lab.txt
        requirements_live_lab = project_root / "requirements-live-lab.txt"
        requirements = tmp_path / "requirements.txt"
        requirements.write_text(requirements_live_lab.read_text())

        # Create mock sha256sum for macOS compatibility
        mock_bin = tmp_path / "mock_bin"
        mock_bin.mkdir()
        mock_sha256sum = mock_bin / "sha256sum"
        mock_sha256sum.write_text(
            "#!/usr/bin/env bash\n"
            "# Mock sha256sum for test - returns consistent hash\n"
            "cat | while read -r _; do :; done\n"
            "printf 'mockhash1234567890abcdef  -\n'\n"
        )
        mock_sha256sum.chmod(0o755)

        # Run script with K9B_LIVE_LAB_PYTHON set to the bin directory
        result = subprocess_run(
            [
                "bash",
                str(script),
            ],
            env={
                "PATH": f"{mock_bin}:{real_python}:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin",
                "K9B_LIVE_LAB_PYTHON": str(fake_bin),
                "K9B_LIVE_LAB_VENV_PATH": str(tmp_path / "test-venv"),
                "K9B_LIVE_LAB_REQUIREMENTS": str(requirements),
                "GITHUB_OUTPUT": str(tmp_path / "github_output"),
            },
            capture_output=True,
            text=True,
        )

        # Should succeed: script normalizes directory to executable
        assert result.returncode == 0, (
            f"ensure_live_lab_venv.sh should normalize {fake_bin} to {fake_bin}/python.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}\n"
            f"Got: exit {result.returncode}"
        )

        # Verify the script normalized the directory to executable path
        assert f"python_bin={fake_bin}/python" in result.stdout, (
            f"Script should normalize directory to executable path.\n"
            f"stdout: {result.stdout}"
        )

        # Verify venv was created
        venv_path = tmp_path / "test-venv"
        assert venv_path.exists(), f"venv should be created at {venv_path}"
        assert (venv_path / "bin" / "python").exists(), "venv should have bin/python"

    def test_ensure_venv_script_rejects_directory_without_python(
        self, tmp_path: Path
    ) -> None:
        """ensure_live_lab_venv.sh should fail clearly when bin dir lacks python."""
        project_root = Path(__file__).parent.parent
        script = project_root / "scripts/ci/ensure_live_lab_venv.sh"
        assert script.exists(), f"ensure_live_lab_venv.sh not found at {script}"

        # Create fake bin directory WITHOUT python executable
        fake_bin = tmp_path / "Python" / "3.13.14" / "x64" / "bin"
        fake_bin.mkdir(parents=True)
        # No python or python3 executable

        requirements = tmp_path / "requirements.txt"
        requirements.write_text("pytest\n")

        result = subprocess_run(
            [
                "bash",
                str(script),
            ],
            env={
                "K9B_LIVE_LAB_PYTHON": str(fake_bin),
                "K9B_LIVE_LAB_VENV_PATH": str(tmp_path / "test-venv"),
                "K9B_LIVE_LAB_REQUIREMENTS": str(requirements),
                "GITHUB_OUTPUT": str(tmp_path / "github_output"),
            },
            capture_output=True,
            text=True,
        )

        # Should fail with exit 2 and clear error message
        assert result.returncode == 2, (
            f"ensure_live_lab_venv.sh should exit 2 when bin dir has no python/python3.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "ERROR" in result.stderr or "ERROR" in result.stdout, (
            "Error output should contain 'ERROR' message"
        )
        assert "python" in (result.stderr + result.stdout).lower(), (
            "Error message should mention 'python' in the context of the failure"
        )
