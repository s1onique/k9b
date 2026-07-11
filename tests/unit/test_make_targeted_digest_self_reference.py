"""R11 self-reference regression tests for make_targeted_digest.sh.

Closes the R10 oversight where the digest, when generated into a
path inside the repository, included itself in its own manifest
and embedded thousands of lines of self-referential diff. That
also broke ``git diff --check`` (whitespace errors in the previous
artifact). The R11 output-path filter excludes the digest's own
target from both the FILES list and the manifest BEFORE writing.

This module lives separately from the main manifest test module so
the main module stays under the LLM-friendly file size threshold.
"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


class MakeTargetedDigestSelfReferenceTest(unittest.TestCase):
    """R11 invariant: the digest NEVER references itself in any section."""

    def setUp(self) -> None:
        """Create a temporary git repo."""
        self.repo_dir = tempfile.mkdtemp(prefix="digest_self_ref_test_")
        self.original_cwd = os.getcwd()
        os.chdir(self.repo_dir)

        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            check=True,
            capture_output=True,
        )
        Path("README.md").write_text("initial\n")
        subprocess.run(["git", "add", "README.md"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], check=True, capture_output=True)

    def tearDown(self) -> None:
        """Restore working directory."""
        os.chdir(self.original_cwd)

    def _script_path(self) -> Path:
        return (
            Path(__file__)
            .resolve()
            .parents[2]
            .joinpath("scripts", "make_targeted_digest.sh")
        )

    def _run(self, output_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self._script_path()), "--dirty", "--output", str(output_path)],
            capture_output=True,
            text=True,
            cwd=self.repo_dir,
            check=False,
        )

    def _setup_factory_anchor(self) -> tuple[Path, Path]:
        """Create a tracked ``existing.txt`` and stage a ``.factory/digest.md`` placeholder."""
        Path("existing.txt").write_text("v1\n")
        subprocess.run(
            ["git", "add", "existing.txt"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"], check=True, capture_output=True
        )
        Path("existing.txt").write_text("v2\n")

        factory_dir = Path(self.repo_dir) / ".factory"
        factory_dir.mkdir(exist_ok=True)
        output_path = factory_dir / "digest.md"
        output_path.write_text("placeholder\n")
        subprocess.run(
            ["git", "add", ".factory/digest.md"], check=True, capture_output=True
        )
        return factory_dir, output_path

    def test_digest_excludes_its_own_output_path(self) -> None:
        """R11 invariant: the digest NEVER references itself in any section.

        Generating to a path inside the repository previously caused
        the artifact to be appended to its own manifest (with
        thousands of lines of self-referential diff) and broke
        ``git diff --check``. The script filters the output path
        from both the FILES list and the manifest BEFORE writing.
        """
        _factory_dir, output_path = self._setup_factory_anchor()
        result = self._run(output_path)
        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")

        regenerated = output_path.read_text()

        # The manifest section MUST NOT contain the output path.
        manifest_section = regenerated.split("## Manifest", 1)[1].split(
            "## Changed files", 1
        )[0]
        self.assertNotIn(
            ".factory/digest.md",
            manifest_section,
            f"Digest self-references its output path in ## Manifest:\n{manifest_section}",
        )

        # The Changed files section MUST NOT contain the output path.
        changed_section = regenerated.split("## Changed files", 1)[1].split(
            "## Diffs", 1
        )[0]
        self.assertNotIn(
            ".factory/digest.md",
            changed_section,
            f"Digest self-references its output path in ## Changed files:\n{changed_section}",
        )

        # The diff section MUST NOT contain a diff of the output
        # path itself.
        if "## Diffs" in regenerated:
            diff_section = regenerated.split("## Diffs", 1)[1]
            self.assertNotIn(
                "diff --git a/.factory/digest.md",
                diff_section,
                "Digest embeds its own diff",
            )

    def test_digest_stable_against_self_reference_loop(self) -> None:
        """R11 invariant: regenerating the digest a second time
        produces a stable output.

        Before R11, the first run's output was staged as a new
        file, the second run included the previous output in its
        manifest, and the diff section contained the entire previous
        output. R11's output-path filter keeps both runs equal.
        """
        _factory_dir, output_path = self._setup_factory_anchor()

        result1 = self._run(output_path)
        self.assertEqual(result1.returncode, 0, f"First run failed: {result1.stderr}")
        first = output_path.read_text()

        subprocess.run(
            ["git", "add", ".factory/digest.md"], check=True, capture_output=True
        )

        result2 = self._run(output_path)
        self.assertEqual(result2.returncode, 0, f"Second run failed: {result2.stderr}")
        second = output_path.read_text()

        # The generated-at timestamp will differ, so strip it for
        # the comparison. Otherwise the two outputs MUST be
        # byte-for-byte identical.
        ts_pattern = re.compile(r"Generated at: [^\n]+\n")
        first_stable = ts_pattern.sub("", first)
        second_stable = ts_pattern.sub("", second)
        self.assertEqual(
            first_stable,
            second_stable,
            "Digest is not stable across two consecutive runs",
        )

    def test_git_diff_check_clean_after_digest_rewrite(self) -> None:
        """R11 invariant: ``git diff --check`` remains clean after the
        digest is regenerated.

        Before R11 the digest was 9000+ lines and contained trailing
        whitespace and CRLF artifacts that ``git diff --check``
        flagged as errors. With the self-reference filter the
        regenerated digest is a small file with no whitespace
        errors.
        """
        Path("clean.txt").write_text("clean\n")
        subprocess.run(
            ["git", "add", "clean.txt"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"], check=True, capture_output=True
        )
        Path("clean.txt").write_text("clean v2\n")

        factory_dir = Path(self.repo_dir) / ".factory"
        factory_dir.mkdir(exist_ok=True)
        output_path = factory_dir / "digest.md"
        output_path.write_text("placeholder\n")
        subprocess.run(
            ["git", "add", ".factory/digest.md"], check=True, capture_output=True
        )

        subprocess.run(
            ["bash", str(self._script_path()), "--dirty", "--output", str(output_path)],
            capture_output=True,
            text=True,
            cwd=self.repo_dir,
            check=True,
        )
        subprocess.run(
            ["git", "add", ".factory/digest.md"], check=True, capture_output=True
        )
        check = subprocess.run(
            ["git", "diff", "--check"],
            capture_output=True,
            text=True,
            cwd=self.repo_dir,
        )
        self.assertEqual(
            check.returncode,
            0,
            f"git diff --check failed after digest rewrite:\n"
            f"stdout: {check.stdout}\nstderr: {check.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
