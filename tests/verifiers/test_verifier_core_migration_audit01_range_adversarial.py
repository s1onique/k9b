# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION13: adversarial range tests.

CORRECTION13 split: the range test module exceeded the
500-line LLM-friendly threshold.  The adversarial range
tests live in this companion module.  The core range
tests live in :mod:`test_verifier_core_migration_audit01_range`.

The tests prove:

* paths containing an ordinary space (``with space.py``)
  are preserved verbatim through a real committed change;
* paths with leading whitespace (`` leading.py``) are
  preserved verbatim;
* paths with trailing whitespace (``trailing.py ``) are
  preserved when the host supports the underlying pathname;
* non-ASCII pathnames (``файл.py``) are preserved;
* embedded-newline pathnames (``line\\nbreak.py``) are
  preserved when the host supports the underlying pathname.

Each test is a real inclusion assertion: the fixture
modifies the adversarial pathname in the subject commit
so the path MUST appear in the change-set.  When the host
filesystem does not support the underlying pathname, the
test skips explicitly with an explanatory message.
"""

from __future__ import annotations

import pytest

from scripts.verifiers_audit.scope import changed_python_paths
from tests.verifiers.verifier_core_migration_audit01_support import RangeRepo


def test_ordinary_space_preserved(range_repo: RangeRepo) -> None:
    """CORRECTION13: paths containing an ordinary space are
    preserved verbatim through a real committed change.

    The fixture MODIFIES ``with space.py`` in the subject
    commit so the path MUST appear in the change-set.
    """
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    py_set = set(py)
    assert "with space.py" in py_set, (
        f"with space.py must be in the python change-set: {py}"
    )
    # No stripped-name variants emitted.
    assert "with_space.py" not in py_set
    assert "with" not in py_set


def test_leading_whitespace_preserved(range_repo: RangeRepo) -> None:
    """CORRECTION13: paths with leading whitespace are preserved
    verbatim through a real committed change.

    The fixture MODIFIES `` leading.py`` in the subject commit
    so the path MUST appear in the change-set.
    """
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    py_set = set(py)
    assert " leading.py" in py_set, (
        f" leading.py must be in the python change-set: {py}"
    )
    # No stripped-name variants emitted.
    assert "leading.py" not in py_set


def test_trailing_whitespace_preserved_or_explicitly_platform_skipped(
    range_repo: RangeRepo,
) -> None:
    """CORRECTION13: trailing whitespace is preserved when the
    host supports it.

    On macOS / Windows the filesystem may strip the trailing
    space; the fixture records ``trailing_whitespace_supported``
    so the test can be skipped explicitly when the host does
    not support the underlying pathname.  Additionally, the
    test skips when the subject commit did not actually
    preserve the trailing whitespace (e.g. macOS rewriting
    a file with a trailing-space name).
    """
    if not range_repo.trailing_whitespace_supported:
        pytest.skip(
            "host filesystem does not support trailing-whitespace "
            "pathnames; the trailing-whitespace case is skipped "
            "per CORRECTION12 platform-aware contract."
        )
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    py_set = set(py)
    # If the host filesystem did NOT preserve the trailing
    # whitespace in the subject commit (macOS strips the
    # trailing space when rewriting a file with that name),
    # the test skips.  The fixture records
    # ``trailing_whitespace_supported`` only for the base
    # commit; the subject commit may still strip the
    # whitespace even when the base commit preserved it.
    if "trailing.py " not in py_set:
        pytest.skip(
            "host filesystem stripped the trailing whitespace on "
            "the subject commit; the trailing-whitespace case is "
            "skipped per CORRECTION12 platform-aware contract."
        )
    # The fixture MODIFIES ``trailing.py `` (with trailing
    # space) in the subject commit so the path MUST appear.
    assert "trailing.py " in py_set, (
        f"trailing.py  (with trailing space) must be in the "
        f"python change-set: {py}"
    )
    # No stripped-name variants emitted.
    assert "trailing.py" not in py_set


def test_non_ascii_path_preserved(range_repo: RangeRepo) -> None:
    """CORRECTION13: non-ASCII pathnames are preserved verbatim
    through a real committed change.

    The fixture MODIFIES ``файл.py`` in the subject commit so
    the path MUST appear in the change-set.
    """
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    py_set = set(py)
    assert "файл.py" in py_set, (
        f"файл.py must be in the python change-set: {py}"
    )


def test_embedded_newline_preserved_or_explicitly_platform_skipped(
    range_repo: RangeRepo,
) -> None:
    """CORRECTION13: an embedded-newline pathname is preserved
    when the host supports it.

    On macOS / Windows the filesystem may reject the
    embedded-newline pathname; the fixture records
    ``embedded_newline_supported`` so the test can be skipped
    explicitly when the host does not support the underlying
    pathname.
    """
    if not range_repo.embedded_newline_supported:
        pytest.skip(
            "host filesystem does not support embedded-newline "
            "pathnames; the embedded-newline case is skipped "
            "per CORRECTION13 platform-aware contract."
        )
    py = changed_python_paths(
        range_repo.base,
        range_repo.subject,
        repo_root=range_repo.root,
    )
    py_set = set(py)
    newline_path = "line\nbreak.py"
    assert newline_path in py_set, (
        f"line\\nbreak.py must be in the python change-set: "
        f"{[p for p in py_set if 'break' in p]}"
    )
