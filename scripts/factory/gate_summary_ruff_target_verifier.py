"""Production target-set verifier for the gate-summary Ruff command.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION11-
RANGE-BOUND-EVIDENCE-TRUTH-AND-LLM-CAP01:

The :func:`verify_recorded_ruff_targets` function in this module is
the **production** implementation of the recorded-target-set check.
The producer hands the canonical authoritative manifest
(``git diff --name-only -z --diff-filter=ACMRT <base>..<head>``) and
the recorded Ruff argv to this function; the function MUST fail closed
on any of the following:

* one omitted target (recorded_argv is missing a path that the
  manifest lists);
* one invented target (recorded_argv carries a path the manifest
  does not list);
* one duplicate target (recorded_argv lists the same path twice);
* no Ruff targets (recorded_argv contains no targets after the
  ``check`` keyword);
* malformed ``python -m ruff check`` grammar (an argv that does not
  parse as a Ruff invocation);
* a non-``check`` Ruff command (``python -m ruff format ...`` is
  rejected);
* a target outside the repository (absolute path, ``..`` traversal,
  backslash separator);
* a non-Python target;
* an unstable duplicate-normalisation trick (e.g. sorting the
  recorded argv so the unequal set comparison silently passes).

The function is the single source of truth.  Tests that build a
"smaller" argv and assert ``smaller != full`` MUST also call this
function with the mutated argv and assert it raises the typed
omission failure -- the negation is meaningless otherwise.

The verifier NEVER consults the manifest of any other range or any
caller-supplied path.  The authoritative manifest is bound by
positional argument; the recorded argv is bound by positional
argument.  Equality is checked on **exact** sorted-path strings
(``==``) with no normalisation beyond sorting, so the comparison
cannot be tricked by silently-renamed paths.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# Python source extension is the only accepted Ruff target.
_PY_SUFFIX = ".py"

# ``..`` segment rejected outright, including within larger segments.
_TRAVERSAL_RE = re.compile(r"(^|/)\.\.($|/)")

# Windows separators detected on any platform.
_WINDOWS_SEPARATOR = "\\"

# Recognized Ruff subcommands; ``check`` is the only one producers use.
_ALLOWED_RUFF_SUBCOMMANDS = frozenset({"check"})


class RuffTargetSetError(ValueError):
    """Bounded, machine-parseable exception type for verifier failures.

    The ``code`` attribute carries a stable identifier for the failure
    mode so callers (CI, tests, the producer's own post-check) can
    localise the regression without parsing the error message string.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _validate_authoritative_path(path: str) -> None:
    """Reject every shape that is NOT a portable POSitory-relative Python file."""
    if not isinstance(path, str) or not path:
        raise RuffTargetSetError(
            "authoritative_path_invalid",
            f"authoritative path MUST be a non-empty string; got {path!r}",
        )
    if path.startswith("/") or path.startswith(_WINDOWS_SEPARATOR):
        raise RuffTargetSetError(
            "authoritative_path_absolute",
            f"authoritative path MUST be repository-relative; got {path!r}",
        )
    if _WINDOWS_SEPARATOR in path:
        raise RuffTargetSetError(
            "authoritative_path_backslash",
            f"authoritative path MUST not contain backslashes; got {path!r}",
        )
    if _TRAVERSAL_RE.search(path):
        raise RuffTargetSetError(
            "authoritative_path_traversal",
            f"authoritative path MUST not contain '..' traversal; got {path!r}",
        )
    if not path.endswith(_PY_SUFFIX):
        raise RuffTargetSetError(
            "authoritative_path_non_python",
            f"authoritative path MUST end with {_PY_SUFFIX!r}; got {path!r}",
        )


def _parse_ruff_targets_from_argv(argv: Sequence[str]) -> tuple[str, list[str]]:
    """Extract the canonical Ruff grammar from a recorded argv.

    Returns ``(subcommand, targets)`` where ``subcommand`` is the token
    immediately after ``ruff`` and ``targets`` is the trailing list of
    path arguments.

    Raises :class:`RuffTargetSetError` on any malformed grammar.
    """
    if not isinstance(argv, (list, tuple)) or not argv:
        raise RuffTargetSetError(
            "argv_empty",
            "recorded Ruff argv MUST be a non-empty sequence",
        )
    argv_list = list(argv)
    # The canonical producer argv is
    # ``[python_executable, "-m", "ruff", "check", *targets]``.
    # We do NOT require the leading interpreter token to be ``python``
    # because tests may invoke the producer with a custom interpreter.
    # We DO require the ``-m ruff`` pair to appear before ``check``.
    try:
        m_index = argv_list.index("-m")
    except ValueError as exc:
        raise RuffTargetSetError(
            "argv_missing_-m",
            "recorded Ruff argv MUST contain '-m' before 'ruff'",
        ) from exc
    if m_index + 1 >= len(argv_list) or argv_list[m_index + 1] != "ruff":
        raise RuffTargetSetError(
            "argv_missing_ruff",
            "recorded Ruff argv MUST contain 'ruff' immediately after '-m'",
        )
    subcommand_index = m_index + 2
    if subcommand_index >= len(argv_list):
        raise RuffTargetSetError(
            "argv_missing_subcommand",
            "recorded Ruff argv MUST carry a subcommand after 'ruff'",
        )
    subcommand = argv_list[subcommand_index]
    if subcommand not in _ALLOWED_RUFF_SUBCOMMANDS:
        raise RuffTargetSetError(
            "argv_subcommand_unsupported",
            f"recorded Ruff argv MUST use 'check' subcommand; got {subcommand!r}",
        )
    targets = argv_list[subcommand_index + 1 :]
    return subcommand, targets


def _validate_recorded_target(target: str) -> None:
    """Reject every shape that is NOT a portable repository-relative Python target."""
    if not isinstance(target, str) or not target:
        raise RuffTargetSetError(
            "recorded_target_invalid",
            f"recorded Ruff target MUST be a non-empty string; got {target!r}",
        )
    if target.startswith("/") or target.startswith(_WINDOWS_SEPARATOR):
        raise RuffTargetSetError(
            "recorded_target_absolute",
            f"recorded Ruff target MUST be repository-relative; got {target!r}",
        )
    if _WINDOWS_SEPARATOR in target:
        raise RuffTargetSetError(
            "recorded_target_backslash",
            f"recorded Ruff target MUST not contain backslashes; got {target!r}",
        )
    if _TRAVERSAL_RE.search(target):
        raise RuffTargetSetError(
            "recorded_target_traversal",
            f"recorded Ruff target MUST not contain '..' traversal; got {target!r}",
        )
    if not target.endswith(_PY_SUFFIX):
        raise RuffTargetSetError(
            "recorded_target_non_python",
            f"recorded Ruff target MUST end with {_PY_SUFFIX!r}; got {target!r}",
        )


def verify_recorded_ruff_targets(
    *,
    authoritative_paths: Sequence[str],
    recorded_argv: Sequence[str],
) -> list[str]:
    """Fail closed on every recorded-vs-authoritative mismatch.

    Returns the sorted list of recorded targets on success.  Raises
    :class:`RuffTargetSetError` on any of the failure modes documented
    in the module docstring.  The function is the single source of
    truth for the recorded-target-set invariant; tests that previously
    asserted set inequalities now invoke this function instead.
    """
    # 1. Validate every authoritative path.  The verifier MUST refuse
    #    to silently accept a malformed authoritative manifest.
    if not isinstance(authoritative_paths, (list, tuple)):
        raise RuffTargetSetError(
            "authoritative_paths_invalid",
            "authoritative_paths MUST be a sequence",
        )
    validated_authoritative: list[str] = []
    for path in authoritative_paths:
        _validate_authoritative_path(path)
        validated_authoritative.append(path)
    authoritative_sorted = sorted(set(validated_authoritative))
    if len(validated_authoritative) != len(set(validated_authoritative)):
        # Duplicate manifests defeat the contract; reject them.
        seen: set[str] = set()
        duplicates: list[str] = []
        for path in validated_authoritative:
            if path in seen and path not in duplicates:
                duplicates.append(path)
            seen.add(path)
        raise RuffTargetSetError(
            "authoritative_paths_duplicate",
            f"authoritative manifest MUST NOT contain duplicates; got {duplicates}",
        )
    if not authoritative_sorted:
        raise RuffTargetSetError(
            "authoritative_paths_empty",
            "authoritative manifest MUST NOT be empty; the producer refuses an empty range",
        )

    # 2. Parse the recorded argv into a Ruff grammar.
    subcommand, targets = _parse_ruff_targets_from_argv(recorded_argv)

    # 3. Validate every recorded target shape.
    if not targets:
        raise RuffTargetSetError(
            "recorded_targets_empty",
            "recorded Ruff argv MUST carry at least one target",
        )
    seen_recorded: set[str] = set()
    duplicates: list[str] = []
    for target in targets:
        _validate_recorded_target(target)
        if target in seen_recorded and target not in duplicates:
            duplicates.append(target)
        seen_recorded.add(target)
    if duplicates:
        raise RuffTargetSetError(
            "recorded_targets_duplicate",
            f"recorded Ruff argv MUST NOT contain duplicates; got {duplicates}",
        )
    recorded_sorted = sorted(seen_recorded)

    # 4. Compare exactly.  Unstable duplicate-normalisation tricks
    #    cannot short-circuit this comparison because both sides are
    #    sorted and de-duplicated with set semantics.
    if recorded_sorted != authoritative_sorted:
        authoritative_set = set(authoritative_sorted)
        recorded_set = set(recorded_sorted)
        omitted = sorted(authoritative_set - recorded_set)
        invented = sorted(recorded_set - authoritative_set)
        if omitted:
            raise RuffTargetSetError(
                "recorded_targets_omit",
                (
                    f"recorded Ruff argv OMITS {len(omitted)} authoritative target(s); "
                    f"first=omitted:{omitted[0]!r} omitted_count={len(omitted)} "
                    f"recorded_count={len(recorded_sorted)} "
                    f"authoritative_count={len(authoritative_sorted)}"
                ),
            )
        # omitted was empty -> invented must be non-empty by symmetric diff.
        raise RuffTargetSetError(
            "recorded_targets_invent",
            (
                f"recorded Ruff argv INVENTS {len(invented)} target(s); "
                f"first=invented:{invented[0]!r} invented_count={len(invented)} "
                f"recorded_count={len(recorded_sorted)} "
                f"authoritative_count={len(authoritative_sorted)}"
            ),
        )

    # 5. Final cross-check: the subcommand grammar must be ``check``.
    if subcommand != "check":
        raise RuffTargetSetError(
            "argv_subcommand_unsupported",
            f"recorded Ruff subcommand MUST be 'check'; got {subcommand!r}",
        )

    return recorded_sorted


__all__ = [
    "RuffTargetSetError",
    "verify_recorded_ruff_targets",
]
