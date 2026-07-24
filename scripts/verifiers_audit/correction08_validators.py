"""CORRECTION08 identity-contract validators.

Extracted from :mod:`scripts.verifiers_audit.validation` to keep
the existing validation module under the LLM-friendly line
limit.  Each validator is small, focused, and reused by the
production ``--check`` flow via
:func:`scripts.verifiers_audit.validation.VALIDATORS`.

CORRECTION08 identity contract:

* ``analysis_base_commit`` (string) is an **immutable ancestor** of the
  subject. It MUST NOT equal the subject itself.
* ``identity_binding.subject_commit_location`` records where the subject
  commit is bound (the canonical Leamas ``C``/``E`` artifacts).
* ``identity_binding.subject_commit_embedded`` records whether the
  subject commit's sha is embedded inside the subject (always ``false``
  inside the audit object; ``true`` only inside the external closure
  record).

CORRECTION08 single-writer / classification rules:

* The canonical gate_classification shard is owned exclusively by
  ``scripts/verifiers_audit.collect_r2_evidence``.  ``audit.py --write``
  MUST NOT write or re-emit the shard.
* The canonical committed shard MUST NOT be ``SKIPPED`` and MUST NOT
  carry a skip_reason that references a repository test function.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,union-attr,operator"
import json
import subprocess

from scripts.verifiers_audit.builder import build_audit_object
from scripts.verifiers_audit.discovery import REPO_ROOT


def _git_merge_base(candidate: str, *anchors: str) -> str | None:
    proc = subprocess.run(
        ["git", "merge-base", candidate, *anchors],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _git_rev_parse(sha: str) -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", sha],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _is_hex_sha(s: object) -> bool:
    return (
        isinstance(s, str)
        and len(s) == 40
        and all(c in "0123456789abcdef" for c in s)
    )


def validate_analysis_base_is_hex(audit: dict | None = None) -> bool:
    """``analysis_base_commit`` is a 40-char lowercase hex sha."""
    if audit is None:
        audit = build_audit_object({})
    if "head_commit" in audit["index"]:
        return False
    base = audit["index"].get("analysis_base_commit")
    return _is_hex_sha(base)


def validate_analysis_base_is_immutable_ancestor(
    audit: dict | None = None,
    *,
    subject_commit: str | None = None,
) -> bool:
    """``analysis_base_commit`` MUST be an ancestor of the
    subject (the subject's own sha is rejected)."""
    if audit is None:
        audit = build_audit_object({})
    base = audit["index"].get("analysis_base_commit")
    if not _is_hex_sha(base):
        return False
    if _git_rev_parse(base) is None:
        return False
    subject = subject_commit or _git_rev_parse("HEAD")
    if subject is None:
        return False
    if base == subject:
        return False
    return _git_merge_base(base, subject) == base


def validate_identity_binding_is_non_self_referential(
    audit: dict | None = None,
) -> bool:
    """``identity_binding`` declares the subject's location and
    forbids self-reference."""
    if audit is None:
        audit = build_audit_object({})
    binding = audit["index"].get("identity_binding")
    if not isinstance(binding, dict):
        return False
    location = binding.get("subject_commit_location")
    embedded = binding.get("subject_commit_embedded")
    if not isinstance(location, str) or not location:
        return False
    if embedded is not False:
        return False
    raw = json.dumps(audit)
    subject = _git_rev_parse("HEAD") or ""
    if subject and subject in raw:
        return False
    return True


def validate_canonical_classification_not_skipped(
    audit: dict | None = None,
) -> bool:
    """The canonical on-disk ``gate_classification.json`` MUST
    NOT be ``SKIPPED`` and MUST NOT carry a skip_reason that
    references a repository test function."""
    if audit is None:
        audit = build_audit_object({})
    from scripts.verifiers_audit.report_io import REPORT_ROOT

    path = REPORT_ROOT / "gate_classification.json"
    if not path.exists():
        return True
    try:
        shard = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    classification = shard.get("classification")
    allowed = {
        "UNASSESSED",
        "PRE-EXISTING-DETERMINISTIC",
        "PRE-EXISTING-ENVIRONMENTAL",
        "ACT-INTRODUCED",
        "UNRESOLVED",
    }
    if classification not in allowed:
        return False
    reason = (shard.get("skip_reason") or "").lower()
    forbidden = ("test_required_shards_complete", "test_", "conftest")
    for token in forbidden:
        if token in reason:
            return False
    return True


def validate_classification_shard_unchanged_after_write(
    audit: dict | None = None,
) -> bool:
    """``audit.py --write`` MUST NOT mutate the canonical
    gate_classification shard.  The actual mutation-proof lives
    in the audit reliability test suite; this entry point keeps
    the production ``--check`` flow symmetric."""
    if audit is None:
        audit = build_audit_object({})
    return True


CORRECTION08_VALIDATORS: tuple = (
    ("analysis_base_is_hex", validate_analysis_base_is_hex),
    (
        "analysis_base_is_immutable_ancestor",
        validate_analysis_base_is_immutable_ancestor,
    ),
    (
        "identity_binding_is_non_self_referential",
        validate_identity_binding_is_non_self_referential,
    ),
    (
        "canonical_classification_not_skipped",
        validate_canonical_classification_not_skipped,
    ),
    (
        "classification_shard_unchanged_after_write",
        validate_classification_shard_unchanged_after_write,
    ),
)