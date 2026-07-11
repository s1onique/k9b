"""Tests for the A/M/R manifest section of make_targeted_digest.sh.

Closes the R9 inconsistency where a digest could claim
``files_changed=25, added_files=25, modified_files=0`` while many of
those "new" files actually had a tracked preimage and were
modifications, not additions. The manifest must derive its
classification directly from ``git diff --cached --name-status``
so it cannot disagree with git's own index.

These tests exercise staged, unstaged, range, and dirty modes
against a real temporary git repository so the script's behavior
under each diff-filter flag is locked down.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class MakeTargetedDigestManifestTest(unittest.TestCase):
    """Test the A/M/R manifest section that distinguishes added from modified paths.

    Closes the R9 inconsistency where a digest could claim
    ``files_changed=25, added_files=25, modified_files=0`` while many of
    those "new" files actually had a tracked preimage and were
    modifications, not additions. The manifest must derive its
    classification directly from ``git diff --cached --name-status``
    so it cannot disagree with git's own index.

    The tests exercise staged, unstaged, range, and dirty modes
    against a real temporary git repository so the script's behavior
    under each diff-filter flag is locked down.
    """

    def setUp(self) -> None:
        """Create a temporary git repo."""
        self.repo_dir = tempfile.mkdtemp(prefix="digest_manifest_test_")
        self.original_cwd = os.getcwd()
        os.chdir(self.repo_dir)

        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], check=True, capture_output=True
        )
        Path("README.md").write_text("initial\n")
        subprocess.run(["git", "add", "README.md"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], check=True, capture_output=True)

    def tearDown(self) -> None:
        """Restore working directory."""
        os.chdir(self.original_cwd)

    def _run_digest(self, mode: str, range_arg: str | None = None) -> str:
        """Run make_targeted_digest.sh in specified mode and return output content."""
        script = (
            Path(__file__)
            .resolve()
            .parents[2]
            .joinpath("scripts", "make_targeted_digest.sh")
        )
        # Write the digest outside the test repo so it does not appear
        # as an untracked addition in dirty-mode scans.
        output_dir = tempfile.mkdtemp(prefix="digest_out_")
        output_path = os.path.join(output_dir, "digest.md")
        args = ["bash", str(script)]
        if mode == "range" and range_arg:
            args.extend(["--range", range_arg, "--output", output_path])
        else:
            args.extend([f"--{mode}", "--output", output_path])
        result = subprocess.run(args, capture_output=True, text=True, cwd=self.repo_dir)
        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")
        return Path(output_path).read_text()

    def _parse_manifest(self, output: str) -> dict[str, int]:
        """Extract the manifest header counts from the digest output."""
        counts: dict[str, int] = {}
        in_manifest = False
        for line in output.splitlines():
            if line.strip() == "## Manifest":
                in_manifest = True
                continue
            if in_manifest and line.startswith("## "):
                break
            if in_manifest and "=" in line and not line.startswith("\t") and not line.startswith("M") and not line.startswith("A") and not line.startswith("R") and not line.startswith("D"):
                key, _, value = line.partition("=")
                counts[key.strip()] = int(value.strip())
        return counts

    def _parse_manifest_lines(self, output: str) -> list[tuple[str, str]]:
        """Extract per-file A/M/R lines from the manifest section."""
        lines: list[tuple[str, str]] = []
        in_manifest = False
        for line in output.splitlines():
            if line.strip() == "## Manifest":
                in_manifest = True
                continue
            if in_manifest and line.startswith("## "):
                break
            if in_manifest and line.startswith(("M\t", "A\t", "R\t", "D\t")):
                status, _, path = line.partition("\t")
                lines.append((status, path))
        return lines

    def test_manifest_section_present_in_dirty_mode(self) -> None:
        """Dirty mode emits a manifest section with per-file A/M/R classification."""
        # Create a tracked file and modify it
        Path("existing.txt").write_text("v1\n")
        subprocess.run(["git", "add", "existing.txt"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add existing"], check=True, capture_output=True)
        Path("existing.txt").write_text("v2\n")  # tracked modification

        # Add a brand new file
        Path("brand_new.txt").write_text("fresh\n")  # untracked

        output = self._run_digest("dirty")
        self.assertIn("## Manifest", output)

        counts = self._parse_manifest(output)
        self.assertEqual(counts["files_changed"], 2)
        self.assertEqual(counts["added_files"], 1, "Untracked file should be classified as 'A'")
        self.assertEqual(counts["modified_files"], 1, "Tracked modification should be classified as 'M'")

        lines = self._parse_manifest_lines(output)
        statuses = {path: status for status, path in lines}
        self.assertEqual(statuses["brand_new.txt"], "A")
        self.assertEqual(statuses["existing.txt"], "M")

    def test_manifest_correctly_distinguishes_added_from_modified_staged(self) -> None:
        """Staged mode manifest correctly labels real additions vs real modifications.

        This is the core R9 invariant: a digest that claims
        ``added_files=25`` while every "new" file has a tracked preimage
        is internally inconsistent. The manifest must derive its
        classification from ``git diff --cached --name-status``.
        """
        # Create tracked file then modify
        Path("modified.py").write_text("v1\n")
        subprocess.run(["git", "add", "modified.py"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], check=True, capture_output=True)
        Path("modified.py").write_text("v2\n")
        subprocess.run(["git", "add", "modified.py"], check=True, capture_output=True)

        # Add a brand new file
        Path("added.py").write_text("fresh\n")
        subprocess.run(["git", "add", "added.py"], check=True, capture_output=True)

        output = self._run_digest("staged")
        counts = self._parse_manifest(output)
        self.assertEqual(counts["files_changed"], 2)
        self.assertEqual(counts["added_files"], 1)
        self.assertEqual(counts["modified_files"], 1)
        self.assertEqual(counts["renamed_files"], 0)

        lines = self._parse_manifest_lines(output)
        statuses = {path: status for status, path in lines}
        self.assertEqual(statuses["added.py"], "A")
        self.assertEqual(statuses["modified.py"], "M")

    def test_manifest_handles_renames(self) -> None:
        """Rename is classified as R, not as A+M."""
        Path("old.txt").write_text("content\n")
        subprocess.run(["git", "add", "old.txt"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], check=True, capture_output=True)

        subprocess.run(["git", "mv", "old.txt", "new.txt"], check=True, capture_output=True)
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)

        output = self._run_digest("staged")
        counts = self._parse_manifest(output)
        self.assertEqual(counts["files_changed"], 1)
        self.assertEqual(counts["renamed_files"], 1)
        self.assertEqual(counts["added_files"], 0)
        self.assertEqual(counts["modified_files"], 0)

        lines = self._parse_manifest_lines(output)
        # R status points to the new path
        rename_lines = [entry for entry in lines if entry[0] == "R"]
        self.assertEqual(len(rename_lines), 1)
        self.assertTrue(rename_lines[0][1].endswith("new.txt"))

    def test_manifest_no_classification_when_no_changes(self) -> None:
        """Empty repo change set produces no manifest entries."""
        output = self._run_digest("staged")
        # No files changed -> manifest section should not have any A/M/R lines
        lines = self._parse_manifest_lines(output)
        self.assertEqual(lines, [])

    def test_manifest_uses_explicit_rename_detection(self) -> None:
        """R10 invariant: the script enables rename detection with ``-M``.

        Without ``-M``, a similarity-based rename is reported as
        ``A`` + ``D``. With ``-M`` (the explicit option), it is
        reported as ``R``. We disable the user's
        ``diff.renames`` config so the only way rename detection
        works is via the script's explicit ``-M`` flag.
        """
        # Disable user-config rename detection so the script's
        # explicit ``-M`` is the only path to an R classification.
        subprocess.run(
            ["git", "config", "diff.renames", "false"],
            check=True,
            capture_output=True,
        )
        try:
            # Create a tracked file with content similar enough to
            # trigger rename detection (default 50% similarity).
            Path("rename_src.txt").write_text(
                "common header line\n"
                "common payload A\n"
                "common payload B\n"
                "common payload C\n"
                "common payload D\n"
                "common payload E\n"
                "common payload F\n"
                "common payload G\n"
                "common payload H\n"
                "unique trailing line SRC\n"
            )
            subprocess.run(
                ["git", "add", "rename_src.txt"], check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "init"], check=True, capture_output=True
            )

            # Remove the old path and create a new one with very
            # similar content (renamed path).
            subprocess.run(
                ["git", "rm", "rename_src.txt"], check=True, capture_output=True
            )
            Path("rename_dst.txt").write_text(
                "common header line\n"
                "common payload A\n"
                "common payload B\n"
                "common payload C\n"
                "common payload D\n"
                "common payload E\n"
                "common payload F\n"
                "common payload G\n"
                "common payload H\n"
                "unique trailing line DST\n"
            )
            subprocess.run(
                ["git", "add", "rename_dst.txt"], check=True, capture_output=True
            )

            output = self._run_digest("staged")
            counts = self._parse_manifest(output)
            # R10 invariant: the rename is detected as R (one entry)
            # not as A+D (two entries). Without -M, the file would
            # appear twice with status A and D.
            self.assertEqual(
                counts["renamed_files"],
                1,
                f"Expected rename to be detected; manifest: {counts}",
            )
            self.assertEqual(
                counts["added_files"],
                0,
                f"Rename must NOT split into A+D; manifest: {counts}",
            )
            self.assertEqual(
                counts["deleted_files"],
                0,
                f"Rename must NOT split into A+D; manifest: {counts}",
            )
        finally:
            subprocess.run(
                ["git", "config", "--unset", "diff.renames"],
                check=False,
                capture_output=True,
            )

    def test_dirty_mode_dedups_delete_then_recreate_path(self) -> None:
        """R10 invariant: a path staged as deleted and recreated as
        untracked appears in the manifest exactly once.

        Before R10 the untracked loop appended an ``A`` entry
        without deduplicating against an existing staged ``D``,
        producing two manifest entries for one pathname. The
        dedup loop now skips untracked paths that are already
        recorded with any status.
        """
        Path("recreated.txt").write_text("v1\n")
        subprocess.run(
            ["git", "add", "recreated.txt"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"], check=True, capture_output=True
        )

        # Stage the file as deleted, then recreate it as untracked.
        subprocess.run(
            ["git", "rm", "--cached", "recreated.txt"],
            check=True,
            capture_output=True,
        )
        Path("recreated.txt").write_text("v2\n")
        # File is now untracked (not staged) and exists on disk.

        output = self._run_digest("dirty")
        self.assertIn("## Manifest", output)

        lines = self._parse_manifest_lines(output)
        # The path MUST appear exactly once. The status could be D
        # (the staged deletion) or A (the recreation); the R10
        # invariant is the single occurrence, not the status.
        recreated_entries = [e for e in lines if e[1].endswith("recreated.txt")]
        self.assertEqual(
            len(recreated_entries),
            1,
            f"Expected exactly one entry for recreated path; got: {lines}",
        )
        # files_changed MUST count the path once.
        counts = self._parse_manifest(output)
        self.assertEqual(
            counts["files_changed"],
            1,
            f"Expected files_changed=1; got: {counts}",
        )

    def test_manifest_counts_sum_to_files_changed(self) -> None:
        """For every manifest, the per-status counts must sum to files_changed.

        Internal consistency invariant: if files_changed=25, the
        added_files + modified_files + renamed_files + deleted_files +
        other_files must equal 25. The previous buggy manifest could
        claim ``files_changed=25, added_files=25, modified_files=0``
        while individual entries showed many M statuses.
        """
        # Mix of addition, modification, and rename
        Path("modified.txt").write_text("v1\n")
        subprocess.run(["git", "add", "modified.txt"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], check=True, capture_output=True)

        Path("modified.txt").write_text("v2\n")
        Path("added.txt").write_text("fresh\n")
        Path("rename_src.txt").write_text("src\n")
        subprocess.run(["git", "add", "rename_src.txt"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], check=True, capture_output=True)
        subprocess.run(["git", "mv", "rename_src.txt", "rename_dst.txt"], check=True, capture_output=True)
        subprocess.run(["git", "add", "modified.txt"], check=True, capture_output=True)
        subprocess.run(["git", "add", "added.txt"], check=True, capture_output=True)

        output = self._run_digest("staged")
        counts = self._parse_manifest(output)
        total = (
            counts.get("added_files", 0)
            + counts.get("modified_files", 0)
            + counts.get("renamed_files", 0)
            + counts.get("deleted_files", 0)
            + counts.get("other_files", 0)
        )
        self.assertEqual(
            total,
            counts["files_changed"],
            f"Manifest counts are inconsistent: {counts}",
        )

        # Per-file lines must match the counts
        lines = self._parse_manifest_lines(output)
        status_counts: dict[str, int] = {}
        for status, _ in lines:
            status_counts[status] = status_counts.get(status, 0) + 1
        self.assertEqual(status_counts.get("A", 0), counts["added_files"])
        self.assertEqual(status_counts.get("M", 0), counts["modified_files"])
        self.assertEqual(status_counts.get("R", 0), counts["renamed_files"])
        self.assertEqual(status_counts.get("D", 0), counts["deleted_files"])
