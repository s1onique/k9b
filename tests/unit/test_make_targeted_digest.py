"""Tests for make_targeted_digest.sh script.

Uses a real temporary git repo to test digest output behavior.
"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


class MakeTargetedDigestTest(unittest.TestCase):
    """Tests for the make_targeted_digest.sh script in dirty mode."""

    def setUp(self) -> None:
        """Create a temporary git repo with controlled state."""
        self.repo_dir = tempfile.mkdtemp(prefix="digest_test_")
        self.original_cwd = os.getcwd()
        os.chdir(self.repo_dir)

        # Initialize git repo with a commit (required for staging)
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], check=True, capture_output=True
        )
        # Create initial commit
        Path("README.md").write_text("initial\n")
        subprocess.run(["git", "add", "README.md"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], check=True, capture_output=True)

    def tearDown(self) -> None:
        """Restore working directory."""
        os.chdir(self.original_cwd)

    def _run_digest(self) -> str:
        """Run make_targeted_digest.sh in dirty mode and return output content."""
        script = (
            Path(__file__)
            .resolve()
            .parents[2]
            / "scripts"
            / "make_targeted_digest.sh"
        )
        output_path = os.path.join(self.repo_dir, "digest.md")
        args = ["bash", str(script), "--dirty", "--output", output_path]
        result = subprocess.run(args, capture_output=True, text=True, cwd=self.repo_dir)
        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")
        return Path(output_path).read_text()

    def _create_file(self, path: str, content: str = "content\n") -> None:
        """Create a file in the repo."""
        full_path = Path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    def _parse_file_blocks(self, output: str) -> dict[str, str]:
        """Parse digest output into per-file blocks.

        Returns a dict mapping filename to the text block for that file.
        Each block includes the "=== filename ===" header through the next header or section.
        """
        blocks = {}
        # Pattern to match === filename === headers
        header_pattern = re.compile(r'^=== (.+?) ===\s*$', re.MULTILINE)
        matches = list(header_pattern.finditer(output))

        for i, match in enumerate(matches):
            filename = match.group(1)
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(output)
            blocks[filename] = output[start:end]

        return blocks


    def test_unified_changed_files_section_exists(self) -> None:
        """Output must have one unified 'Changed files' section."""
        self._create_file("file1.txt")
        subprocess.run(["git", "add", "file1.txt"], check=True, capture_output=True)
        output = self._run_digest()
        self.assertIn("## Changed files", output)
        # Should not have separate staged/unstaged sections
        self.assertNotIn("## Changed files (staged)", output)
        self.assertNotIn("## Changed files (unstaged)", output)

    def test_unified_diffs_section_exists(self) -> None:
        """Output must have one unified 'Diffs' section, not per-area."""
        self._create_file("file1.txt")
        subprocess.run(["git", "add", "file1.txt"], check=True, capture_output=True)
        output = self._run_digest()
        self.assertIn("## Diffs", output)
        # Should not have separate staged/unstaged diff sections
        self.assertNotIn("## Diffs (staged)", output)
        self.assertNotIn("## Diffs (unstaged)", output)

    def test_tracked_file_staged_only(self) -> None:
        """Tracked file with only staged changes shows metadata and diff correctly."""
        self._create_file("staged_only.txt", "staged content\n")
        subprocess.run(["git", "add", "staged_only.txt"], check=True, capture_output=True)

        output = self._run_digest()
        blocks = self._parse_file_blocks(output)

        # Should appear in Changed files with correct metadata
        self.assertRegex(
            output, r"staged_only\.txt\s+\[tracked, staged present: yes, unstaged present: no\]"
        )

        # Should have a file block
        self.assertIn("staged_only.txt", blocks)

        # Within the file block, should have staged diff but NOT unstaged diff
        block = blocks["staged_only.txt"]
        self.assertIn("--- staged diff ---", block)
        self.assertNotIn("--- unstaged diff ---", block)
        self.assertNotIn("--- untracked file preview ---", block)

    def test_tracked_file_unstaged_only(self) -> None:
        """Tracked file with only unstaged changes shows metadata and diff correctly."""
        self._create_file("unstaged_only.txt", "unstaged content\n")
        subprocess.run(["git", "add", "unstaged_only.txt"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add unstaged_only"], check=True, capture_output=True)
        # Now make unstaged changes (no staging)
        self._create_file("unstaged_only.txt", "modified content\n")

        output = self._run_digest()
        blocks = self._parse_file_blocks(output)

        # Should appear in Changed files with correct metadata
        self.assertRegex(
            output, r"unstaged_only\.txt\s+\[tracked, staged present: no, unstaged present: yes\]"
        )

        # Should have a file block
        self.assertIn("unstaged_only.txt", blocks)

        # Within the file block, should have unstaged diff but NOT staged diff
        block = blocks["unstaged_only.txt"]
        self.assertIn("--- unstaged diff ---", block)
        self.assertNotIn("--- staged diff ---", block)
        self.assertNotIn("--- untracked file preview ---", block)

    def test_tracked_file_both_staged_and_unstaged(self) -> None:
        """Tracked file with both staged and unstaged changes shows both diffs."""
        self._create_file("both.txt", "original\n")
        subprocess.run(["git", "add", "both.txt"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add both"], check=True, capture_output=True)
        # Stage a change
        self._create_file("both.txt", "staged change\n")
        subprocess.run(["git", "add", "both.txt"], check=True, capture_output=True)
        # Add unstaged change on top
        self._create_file("both.txt", "staged and unstaged\n")

        output = self._run_digest()
        blocks = self._parse_file_blocks(output)

        # Should appear in Changed files with both flags
        self.assertRegex(
            output, r"both\.txt\s+\[tracked, staged present: yes, unstaged present: yes\]"
        )

        # Should have a file block
        self.assertIn("both.txt", blocks)

        # Within the file block, should have both diffs
        block = blocks["both.txt"]
        self.assertIn("--- staged diff ---", block)
        self.assertIn("--- unstaged diff ---", block)
        self.assertNotIn("--- untracked file preview ---", block)

    def test_untracked_file(self) -> None:
        """Untracked file is listed with preview, marked as untracked with unstaged: yes."""
        self._create_file("untracked.txt", "brand new content\n")
        # Do not git add

        output = self._run_digest()
        blocks = self._parse_file_blocks(output)

        # Should appear in Changed files as untracked with unstaged: yes
        # (untracked files are "present" as unstaged because they exist but aren't staged)
        self.assertRegex(
            output, r"untracked\.txt\s+\[untracked, staged present: no, unstaged present: yes\]"
        )

        # Should have a file block
        self.assertIn("untracked.txt", blocks)

        # Within the file block, should have preview but no staged/unstaged diffs
        block = blocks["untracked.txt"]
        self.assertIn("--- untracked file preview ---", block)
        self.assertNotIn("--- staged diff ---", block)
        self.assertNotIn("--- unstaged diff ---", block)
        # Should contain the file content
        self.assertIn("brand new content", block)

    def test_files_preserve_git_truth(self) -> None:
        """Output preserves actual Git state without misrepresenting."""
        # Create scenario: tracked with unstaged changes and untracked file
        self._create_file("tracked.txt", "original\n")
        subprocess.run(["git", "add", "tracked.txt"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add tracked"], check=True, capture_output=True)
        # Make unstaged change
        self._create_file("tracked.txt", "modified\n")

        self._create_file("brandnew.txt", "new\n")
        # Do not add

        output = self._run_digest()
        blocks = self._parse_file_blocks(output)

        # Both files should appear with correct metadata
        self.assertRegex(
            output, r"tracked\.txt\s+\[tracked, staged present: no, unstaged present: yes\]"
        )
        self.assertRegex(
            output, r"brandnew\.txt\s+\[untracked, staged present: no, unstaged present: yes\]"
        )

        # Verify tracked.txt block has unstaged diff but no staged diff
        self.assertIn("tracked.txt", blocks)
        tracked_block = blocks["tracked.txt"]
        self.assertIn("--- unstaged diff ---", tracked_block)
        self.assertNotIn("--- staged diff ---", tracked_block)

        # Verify brandnew.txt block has preview
        self.assertIn("brandnew.txt", blocks)
        brandnew_block = blocks["brandnew.txt"]
        self.assertIn("--- untracked file preview ---", brandnew_block)

    def test_no_global_staged_vs_unstaged_separation(self) -> None:
        """Output should not globally separate content into staged vs unstaged sections."""
        self._create_file("staged.txt", "staged\n")
        subprocess.run(["git", "add", "staged.txt"], check=True, capture_output=True)

        self._create_file("unstaged.txt", "modified\n")
        subprocess.run(["git", "add", "unstaged.txt"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add unstaged"], check=True, capture_output=True)
        self._create_file("unstaged.txt", "unstaged\n")

        output = self._run_digest()

        # Should not have global staged files section
        self.assertNotIn("## Staged files", output)
        self.assertNotIn("## Unstaged files", output)
        # Should not have diff stat sections broken down by area
        self.assertNotIn("## Diff stat (staged)", output)
        self.assertNotIn("## Diff stat (unstaged)", output)

    def test_files_with_spaces_handled_correctly(self) -> None:
        """Filenames with spaces should be handled safely."""
        self._create_file("path with spaces/file.txt", "content\n")
        subprocess.run(["git", "add", "path with spaces/file.txt"], check=True, capture_output=True)

        output = self._run_digest()
        blocks = self._parse_file_blocks(output)

        # Should handle space in path correctly
        self.assertIn("path with spaces/file.txt", output)
        self.assertIn("path with spaces/file.txt", blocks)

        # Verify the block has correct diff type
        block = blocks["path with spaces/file.txt"]
        self.assertIn("--- staged diff ---", block)


class MakeTargetedDigestModesTest(unittest.TestCase):
    """Test other modes (staged, unstaged, range) still work."""

    def setUp(self) -> None:
        """Create a temporary git repo."""
        self.repo_dir = tempfile.mkdtemp(prefix="digest_mode_test_")
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
        output_path = os.path.join(self.repo_dir, "digest.md")
        args = ["bash", str(script)]
        if mode == "range" and range_arg:
            args.extend(["--range", range_arg, "--output", output_path])
        else:
            args.extend([f"--{mode}", "--output", output_path])
        result = subprocess.run(args, capture_output=True, text=True, cwd=self.repo_dir)
        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")
        return Path(output_path).read_text()

    def _create_and_commit(self, path: str, content: str) -> None:
        """Create a file and commit it."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
        subprocess.run(["git", "add", path], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"add {path}"], check=True, capture_output=True)

    def test_staged_mode(self) -> None:
        """Staged mode works and shows changed files."""
        self._create_and_commit("file.txt", "v1\n")
        Path("file.txt").write_text("v2\n")
        subprocess.run(["git", "add", "file.txt"], check=True, capture_output=True)

        output = self._run_digest("staged")

        self.assertIn("## Changed files", output)
        self.assertIn("file.txt", output)
        self.assertIn("## Diffs", output)

    def test_unstaged_mode(self) -> None:
        """Unstaged mode works and shows changed files."""
        self._create_and_commit("file.txt", "v1\n")
        Path("file.txt").write_text("v2\n")
        # No git add

        output = self._run_digest("unstaged")

        self.assertIn("## Changed files", output)
        self.assertIn("file.txt", output)
        self.assertIn("## Diffs", output)

    def test_range_mode(self) -> None:
        """Range mode works and shows changed files."""
        self._create_and_commit("file.txt", "v1\n")
        Path("file.txt").write_text("v2\n")
        subprocess.run(["git", "add", "file.txt"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "update"], check=True, capture_output=True)

        output = self._run_digest("range", "HEAD~1..HEAD")

        self.assertIn("## Changed files", output)
        self.assertIn("file.txt", output)
        self.assertIn("Range: HEAD~1..HEAD", output)