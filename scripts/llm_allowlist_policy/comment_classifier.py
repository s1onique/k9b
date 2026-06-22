"""Comment-only change classification for allowlist files.

This module classifies changes to allowlist files as comment-only or effective.
It ensures that adding allowlist entries is properly rejected.

FAILS CLOSED:
- git show/base-content read failures produce errors, not None
- comparison is based on normalized effective entries, not line positions
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from .changed_files import ChangedFile
from .sources import AllowlistExtractor


def is_llm_allowlist_file(path: str) -> bool:
    """Check if a path is an LLM-friendly allowlist/ignore file.
    
    Matches files whose path/name clearly identifies them as LLM-friendly 
    allowlist/ignore policy. Excludes test files, __init__.py, and other policy files.
    """
    path_lower = path.lower()
    
    # Exclude __init__.py files (they're package metadata, not allowlists)
    if path_lower.endswith("__init__.py"):
        return False
    
    # Exclude test files (they contain test code, not policy)
    if "/test_" in path_lower or "_test.py" in path_lower:
        return False
    
    # Exclude policy implementation files (these are policy tools, not allowlists)
    if path_lower.endswith("_policy/verify.py"):
        return False
    if path_lower.endswith("_policy/changed_files.py"):
        return False
    if path_lower.endswith("_policy/sources.py"):
        return False
    if path_lower.endswith("_policy/baseline.py"):
        return False
    if path_lower.endswith("_policy/comment_classifier.py"):
        return False
    
    # Must have llm AND at least one of friendly/allowlist/ignore
    has_llm = "llm" in path_lower
    has_friendly = "friendly" in path_lower
    has_allowlist = "allowlist" in path_lower
    has_ignore = "ignore" in path_lower
    
    if has_llm:
        if has_friendly or has_allowlist or has_ignore:
            return True
    
    # Direct ignore file match (including .llm-friendly-ignore)
    if path.endswith(".llm-friendly-ignore"):
        return True
    
    return False


def get_effective_entries(content: str, file_type: str) -> set[str]:
    """Extract effective (non-comment, non-blank) lines from allowlist content.
    
    FAILS CLOSED: Returns normalized effective entries only.
    Does NOT include line numbers - comparison is by entry content only.
    
    NOTE: For Python files, prefer compare_python_allowlist_paths() which uses AST.
    
    Args:
        content: File content
        file_type: "python" or "ignore"
        
    Returns:
        Set of normalized effective entry strings
    """
    effective: set[str] = set()
    
    for line in content.split("\n"):
        stripped = line.strip()
        
        if not stripped:
            continue
            
        # Comment detection
        if stripped.startswith("#"):
            continue
        
        # For Python files, also skip docstrings and module-level comments
        if file_type == "python":
            # Skip lines that are only part of module docstrings
            if stripped.startswith('"""') or stripped.startswith("'''"):
                continue
        
        # Normalize and add (NO line numbers)
        effective.add(stripped)
    
    return effective


def compare_python_allowlist_paths(
    base_content: str,
    current_content: str,
) -> tuple[set[str], set[str], list[str]]:
    """Compare ALLOWLIST entries in two Python files using AST parsing.
    
    Uses AST parsing directly on content strings to avoid temp file encoding issues.
    This is the preferred method for Python allowlist files as it properly
    handles formatting changes and structural changes.
    
    Args:
        base_content: Content at base ref
        current_content: Current content
        
    Returns:
        (base_paths, current_paths, errors)
        - base_paths: Set of paths in base ALLOWLIST
        - current_paths: Set of paths in current ALLOWLIST
        - errors: List of errors (fail-closed on parse failures)
    """
    import ast
    
    base_paths: set[str] = set()
    current_paths: set[str] = set()
    errors: list[str] = []
    
    # Parse base content
    try:
        tree = ast.parse(base_content)
        extractor = _extract_allowlist_paths(tree)
        base_paths.update(extractor.paths)
        errors.extend([f"Base: {e}" for e in extractor.errors])
    except SyntaxError as e:
        errors.append(f"Base syntax error: {e}")
    
    # Parse current content
    try:
        tree = ast.parse(current_content)
        extractor = _extract_allowlist_paths(tree)
        current_paths.update(extractor.paths)
        errors.extend([f"Current: {e}" for e in extractor.errors])
    except SyntaxError as e:
        errors.append(f"Current syntax error: {e}")
    
    return base_paths, current_paths, errors


def _extract_allowlist_paths(tree: ast.AST) -> AllowlistExtractor:
    """Extract ALLOWLIST paths from an AST tree."""
    extractor = AllowlistExtractor()
    extractor.visit(tree)
    return extractor


def classify_python_allowlist_comment_only(
    base_content: str,
    current_content: str,
) -> tuple[bool, str, list[str]]:
    """Classify whether Python allowlist change is comment-only using AST.
    
    Compares the parsed ALLOWLIST entries from both versions.
    Formatting changes inside literals or comment additions don't count as effective.
    
    Args:
        base_content: Content at base ref
        current_content: Current content
        
    Returns:
        (is_comment_only, reason, errors)
    """
    base_paths, current_paths, errors = compare_python_allowlist_paths(
        base_content, current_content
    )
    
    # Fail closed if there were parse errors
    if errors:
        return False, f"Parse errors prevent classification: {errors}", errors
    
    # Compare the actual paths
    if base_paths == current_paths:
        return True, "No effective ALLOWLIST entry changes detected (AST comparison)", errors
    
    added = current_paths - base_paths
    removed = base_paths - current_paths
    
    if added or removed:
        reason = f"ALLOWLIST entries changed: added={len(added)}, removed={len(removed)}"
        return False, reason, errors
    
    return True, "No effective ALLOWLIST entry changes detected (AST comparison)", errors


def get_file_content_at_ref(
    repo_root: Path,
    file_path: str,
    ref: str = "HEAD",
) -> tuple[str | None, list[str]]:
    """Get file content at a specific git ref.
    
    FAILS CLOSED: Returns (None, errors) on subprocess failures.
    Does NOT return None as if the file simply did not exist.
    
    Returns:
        (content or None, errors)
        - content: File content or None if file doesn't exist at ref
        - errors: List of error messages (empty on success)
    """
    errors: list[str] = []
    
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{file_path}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout, errors
        elif "not in" in result.stderr or "does not exist" in result.stderr or "not found" in result.stderr:
            # File doesn't exist at this ref - return None without error
            return None, errors
        else:
            # Git command failed for other reasons - FAIL CLOSED
            errors.append(f"git show {ref}:{file_path} failed: {result.stderr.strip()}")
            return None, errors
    except subprocess.TimeoutExpired:
        errors.append(f"git show {ref}:{file_path} timed out")
        return None, errors
    except FileNotFoundError:
        errors.append("git not found")
        return None, errors
    except Exception as e:
        errors.append(f"git show {ref}:{file_path} error: {e}")
        return None, errors


def classify_change_as_comment_only(
    repo_root: Path,
    changed_file: ChangedFile,
    current_content: str | None,
    base_ref: str = "HEAD",
) -> tuple[bool, str, list[str]]:
    """Classify whether an allowlist file change is comment-only.
    
    FAILS CLOSED: git show failures produce errors that fail the check.
    
    Args:
        repo_root: Repository root
        changed_file: The changed file record
        current_content: Current file content (for new files, may be None)
        base_ref: Git ref to compare against (default: HEAD)
        
    Returns:
        (is_comment_only, reason, errors)
        - is_comment_only: True if change only affects comments/blanks
        - reason: Human-readable explanation of classification
        - errors: List of errors (fail-closed on subprocess failures)
    """
    errors: list[str] = []
    file_path = changed_file.path
    
    # Determine file type
    file_type = "ignore" if file_path.endswith(".llm-friendly-ignore") else "python"
    
    # For new files, check if it's empty or comment-only
    if changed_file.status == "A" or changed_file.status.startswith("A"):
        if current_content is None:
            try:
                with open(repo_root / file_path, encoding="utf-8") as f:
                    current_content = f.read()
            except OSError as e:
                errors.append(f"Cannot read new file {file_path}: {e}")
                return False, f"Cannot read file: {file_path}", errors
        
        effective = get_effective_entries(current_content, file_type)
        if not effective:
            return True, f"New file '{file_path}' is empty or comment-only", errors
        return False, f"New file '{file_path}' has effective entries", errors
    
    # For modified/deleted files, compare against base_ref
    base_content, base_errors = get_file_content_at_ref(repo_root, file_path, base_ref)
    errors.extend(base_errors)
    
    if base_errors:
        # FAIL CLOSED: git show failure
        return False, f"Failed to read {file_path} at {base_ref}", errors
    
    if base_content is None:
        # File didn't exist at base_ref - this is a new file effectively
        if current_content is None:
            try:
                with open(repo_root / file_path, encoding="utf-8") as f:
                    current_content = f.read()
            except OSError as e:
                errors.append(f"Cannot read file {file_path}: {e}")
                return False, f"Cannot read file: {file_path}", errors
        
        effective = get_effective_entries(current_content, file_type)
        if not effective:
            return True, f"File '{file_path}' is empty or comment-only", errors
        return False, f"File '{file_path}' has effective entries", errors
    
    # For Python files, use AST-based comparison via classify_python_allowlist_comment_only
    # Only for files ending in .py to avoid parsing non-Python files like .md
    if file_type == "python" and file_path.endswith(".py"):
        if current_content is None:
            try:
                with open(repo_root / file_path, encoding="utf-8") as f:
                    current_content = f.read()
            except OSError as e:
                errors.append(f"Cannot read file {file_path}: {e}")
                return False, f"Cannot read file: {file_path}", errors
        
        return classify_python_allowlist_comment_only(base_content, current_content)
    
    # For non-Python files (like .md, .llm-friendly-ignore), use line-based comparison
    base_effective = get_effective_entries(base_content, file_type)
    
    if current_content is None:
        try:
            with open(repo_root / file_path, encoding="utf-8") as f:
                current_content = f.read()
        except OSError as e:
            errors.append(f"Cannot read file {file_path}: {e}")
            return False, f"Cannot read file: {file_path}", errors
    
    current_effective = get_effective_entries(current_content, file_type)
    
    # Check if effective entries changed (by content, not position)
    added_entries = current_effective - base_effective
    removed_entries = base_effective - current_effective
    
    if added_entries or removed_entries:
        return False, f"File '{file_path}' has effective entry changes (added: {len(added_entries)}, removed: {len(removed_entries)})", errors
    
    return True, f"File '{file_path}' change classified as comment-only", errors


def check_allowlist_change_is_comment_only(
    repo_root: Path,
    changed_files: list[ChangedFile],
    base_ref: str = "HEAD",
) -> tuple[str | None, list[str], list[str]]:
    """Check if changes to allowlist files are comment-only.
    
    FAILS CLOSED: git show failures cause overall failure.
    
    Args:
        repo_root: Repository root
        changed_files: List of changed files
        base_ref: Git ref to compare against (default: HEAD)
        
    Returns:
        (classification_message, warnings, errors)
        - classification_message: None if no comment-only classification, 
          or message if classified as comment-only
        - warnings: List of classification messages
        - errors: List of errors (fail-closed on subprocess failures)
    """
    warnings: list[str] = []
    errors: list[str] = []
    
    # Filter to only LLM allowlist/ignore files
    allowlist_changes = [
        cf for cf in changed_files 
        if is_llm_allowlist_file(cf.path)
    ]
    
    if not allowlist_changes:
        return None, warnings, errors
    
    # For each allowlist file change, check if comment-only
    for cf in allowlist_changes:
        current_content: str | None = None
        if cf.status not in ("D",) and not cf.status.startswith("D"):
            try:
                file_path = repo_root / cf.path
                if file_path.exists():
                    with open(file_path, encoding="utf-8") as f:
                        current_content = f.read()
            except OSError:
                pass
        
        is_comment_only, reason, file_errors = classify_change_as_comment_only(
            repo_root, cf, current_content, base_ref
        )
        errors.extend(file_errors)
        
        if is_comment_only:
            warnings.append(f"COMMENT-ONLY: {reason}")
        else:
            warnings.append(f"EFFECTIVE CHANGE: {reason}")
    
    # If there were errors (e.g., git show failures), fail closed
    if errors:
        return None, warnings, errors
    
    # If all changes are comment-only, return a classification message
    all_comment_only = all(
        is_llm_allowlist_file(cf.path) and 
        classify_change_as_comment_only(repo_root, cf, None, base_ref)[0]
        for cf in changed_files
        if is_llm_allowlist_file(cf.path)
    )
    
    if all_comment_only:
        return "All allowlist file changes are comment-only (no effective entries added)", warnings, errors
    
    return None, warnings, errors
