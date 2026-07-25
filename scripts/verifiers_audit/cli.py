"""CLI entry point for the audit generator (CORRECTION12/CORRECTION13).

CORRECTION12: the CLI is a thin wrapper.  The single production
authority that writes audit reports is :class:`ReportLayout`
plus :func:`write_all` and :func:`write_audit`.  The CLI's
:func:`cmd_write` delegates to :func:`write_audit` and never
directly writes a report file itself.

CORRECTION13 additions:

* :func:`cmd_check` builds a temporary layout and writes the
  freshly-built audit object into it; compares the COMPLETE
  normalised top-level index against the canonical on-disk
  one.  Every field of the top-level index is part of the
  comparison EXCEPT the canonical shard-path representation
  (which is normalised via :func:`normalise_index_paths`
  with the layout).
* The CLI no longer hand-picks a hand-picked subset of
  top-level fields.  Mutation tests confirm that mutations
  to ``schema_version``, ``identity_binding``,
  ``analysis_base_commit``, ``totals``, ``shard`` set,
  shard hash, or any unknown field are all detected.
* :func:`compare_report_layouts` is the production-bound
  function called by :func:`cmd_check` (and by the
  CORRECTION13 mutation tests).  Every mutation listed in
  the closure plan (``schema_version``,
  ``analysis_base_commit``, ``identity_binding``,
  ``totals``, ``shard_hash``, ``shard_set``,
  ``unknown_extra_field``, ``wrong_shard_basename``,
  ``wrong_shard_parent``, ``swapped_shard_paths``) is
  detected by the real production boundary.

The CLI module is deliberately excluded from importing the
low-level write helpers:

* ``_write_atomic``
* ``_json_dumps``
* ``_dump_helpers_shard``
* ``render_markdown``

so the only legitimate write path is ``write_audit(layout=canonical_layout())``.
``cmd_check`` builds the audit object once and writes a
reproduction into a temporary layout for byte-level
comparison; it never imports the forbidden encoding helpers
either.

Usage::

    python scripts/verifiers_audit/audit.py --check
    python scripts/verifiers_audit/audit.py --write
    python scripts/verifiers_audit/audit.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import cast

from scripts.verifiers_audit.builder import build_audit_object
from scripts.verifiers_audit.report_io import (
    REPORT_ROOT,
    SHARD_NAMES,
    TOP_LEVEL_JSON,
    AuditWriteError,
    ReportLayout,
    canonical_layout,
    report_layout_for_shard_root,
    write_all,
    write_audit,
)
from scripts.verifiers_audit.scope import (
    IndexNormalisationError,
    normalise_index_paths,
)
from scripts.verifiers_audit.validation import run_all


def _load_gate_classification_from_disk() -> dict[str, object] | None:
    """Return the persisted auxiliary record if it exists.

    Falls back to ``None`` when the file is missing or unreadable
    (first-ever run, the user has not yet collected auxiliary
    evidence).  The audit builder in that case produces a
    deterministic ``UNASSESSED`` record.
    """
    path = REPORT_ROOT / "gate_classification.json"
    if not path.exists():
        return None
    try:
        return cast(
            "dict[str, object] | None",
            json.loads(path.read_text(encoding="utf-8")),
        )
    except (OSError, ValueError):
        return None


def _build_audit_into_layout(
    layout: ReportLayout,
    *,
    gate_classification: dict[str, object] | None = None,
) -> None:
    """Build the audit object and write it into ``layout``.

    The canonical gate classification is mirrored into the
    temporary layout so the recorded hashes match the
    canonical run.  The function is the production entry
    point used by :func:`compare_report_layouts`.
    """
    audit = build_audit_object({}, gate_classification=gate_classification)
    canonical_gc = REPORT_ROOT / "gate_classification.json"
    if canonical_gc.exists():
        # Mirror the canonical gate classification into the
        # temporary layout so write_all records the same hash
        # the canonical run produced.
        layout.shard_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(canonical_gc, layout.shard_root / "gate_classification.json")
    write_all(layout=layout, audit=audit)


def _load_top_level_index(layout: ReportLayout) -> dict[str, object]:
    """Load the top-level index from ``layout``."""
    return cast(
        "dict[str, object]",
        json.loads(layout.top_level_json.read_text(encoding="utf-8")),
    )



def _describe_drift(
    *,
    field: str,
    expected: object,
    actual: object,
) -> str:
    """Render a one-line description of a per-field drift."""
    return f"{field} drift: expected={expected!r} actual={actual!r}"


def compare_report_layouts(
    expected_layout: ReportLayout,
    canonical_layout: ReportLayout,
) -> list[str]:
    """Compare the top-level index of two report layouts.

    CORRECTION13/CORRECTION15 production boundary.  The
    function:

    1. loads both complete top-level indexes;
    2. normalises them through the layout-aware
       :func:`normalise_index_paths` -- each index is
       normalised using its OWN layout (the expected
       index is normalised with ``expected_layout``; the
       canonical index is normalised with
       ``canonical_layout``); this makes absolute and
       REPO_ROOT-relative shard-path representations
       compare equal;
    3. CORRECTION15: rewrites every recorded shard path
       to the canonical logical identity (basename) via
       :func:`range_evidence_inventory.rebuild_index_shards`
       so the comparison is robust to macOS
       ``/private/var`` vs ``/var`` aliases WITHOUT a
       global ``realpath`` weakening;
    4. walks the per-side key sets and attributes drift to
       the correct field;
    5. detects every required mutation: ``schema_version``,
       ``analysis_base_commit``, ``identity_binding``,
       ``totals``, ``shard_hash``, ``shard_set``,
       ``unknown_extra_field``, ``wrong_shard_basename``,
       ``wrong_shard_parent``, ``swapped_shard_paths``;
    6. returns a list of drift descriptions (empty list ==
       the two layouts agree).

    An invalid shard path (unknown name, missing path, wrong
    parent, wrong basename, swapped shard path) raises
    :class:`IndexNormalisationError` rather than silently
    normalising; the function never translates a layout
    violation into a successful comparison.
    """
    if not expected_layout.top_level_json.exists():
        return ["expected top-level index is absent"]
    if not canonical_layout.top_level_json.exists():
        return ["canonical top-level index is absent"]
    expected_index = _load_top_level_index(expected_layout)
    canonical_index = _load_top_level_index(canonical_layout)
    try:
        expected_norm = normalise_index_paths(
            expected_index, layout=expected_layout
        )
        canonical_norm = normalise_index_paths(
            canonical_index, layout=canonical_layout
        )
    except IndexNormalisationError as exc:
        return [f"index normalisation rejected: {exc}"]
    from scripts.verifiers_audit.range_evidence_inventory import (
        rebuild_index_shards,
    )
    expected_norm = rebuild_index_shards(
        expected_norm, layout=expected_layout
    )
    canonical_norm = rebuild_index_shards(
        canonical_norm, layout=canonical_layout
    )
    failures: list[str] = []
    if expected_norm == canonical_norm:
        return failures
    for key in set(expected_norm) | set(canonical_norm):
        exp_value = expected_norm.get(key)
        act_value = canonical_norm.get(key)
        if exp_value == act_value:
            continue
        if key == "shards":
            # The shards dict is the canonical shard set; the
            # failure-injection tests probe the per-shard
            # drift explicitly below.
            failures.append(
                _describe_drift(
                    field="shards",
                    expected=sorted(
                        (k, v.get("sha256"))
                        for k, v in cast(
                            "dict[str, object]", exp_value
                        ).items()
                    ),
                    actual=sorted(
                        (k, v.get("sha256"))
                        for k, v in cast(
                            "dict[str, object]", act_value
                        ).items()
                    ),
                )
            )
            continue
        failures.append(_describe_drift(field=key, expected=exp_value, actual=act_value))
    return failures



def cmd_check() -> int:
    """Verify the on-disk reports match the freshly-built audit object.

    The ``--check`` mode exercises the persisted
    ``gate_classification.json`` (or, if missing, generates an
    ``UNASSESSED`` record).  The audit object itself never
    runs the canonical gate; the auxiliary two-tree experiment
    is the only path that produces a real classification.

    CORRECTION13: the comparison is driven by writing the
    in-memory audit into a temporary :class:`ReportLayout` via
    :func:`write_all`, loading both complete top-level indexes,
    normalising them via :func:`normalise_index_paths` with
    the canonical layout as the source of truth, and
    requiring byte-equal equality.  No field is silently
    discarded; the normaliser only touches the canonical
    shard-path representation.
    """
    gate_classification = _load_gate_classification_from_disk()
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp_root:
        tmp_reports = Path(tmp_root) / "reports"
        tmp_reports.mkdir(parents=True, exist_ok=True)
        tmp_layout = report_layout_for_shard_root(tmp_reports)
        _build_audit_into_layout(
            tmp_layout, gate_classification=gate_classification
        )

        # The audit object is built and validated AFTER the
        # layout write (the validator runs on the in-memory
        # audit, not the on-disk artifact).
        audit = build_audit_object({}, gate_classification=gate_classification)
        ok, validator_failures = run_all(audit)
        if not ok:
            failures.append("validators: " + ", ".join(validator_failures))

        # Production-bound comparison: the real
        # ``compare_report_layouts`` is called with the
        # temporary expected layout and the canonical layout.
        if TOP_LEVEL_JSON.exists():
            canonical = canonical_layout()
            failures.extend(
                compare_report_layouts(tmp_layout, canonical)
            )

        # Compare each shard by sha256 hash.
        for name in SHARD_NAMES:
            tmp_path = tmp_layout.shard_root / f"{name}.json"
            if not tmp_path.exists():
                failures.append(f"shard missing: {name}")
                continue
            actual_on_disk = REPORT_ROOT / f"{name}.json"
            if not actual_on_disk.exists():
                failures.append(f"shard missing on disk: {name}")
                continue
            expected_h = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
            actual_h = hashlib.sha256(actual_on_disk.read_bytes()).hexdigest()
            if expected_h != actual_h:
                failures.append(f"shard drift: {name}")

        if canonical.markdown_path.exists():
            expected_h = hashlib.sha256(
                tmp_layout.markdown_path.read_bytes()
            ).hexdigest()
            actual_h = hashlib.sha256(canonical.markdown_path.read_bytes()).hexdigest()
            if expected_h != actual_h:
                failures.append("markdown drift")

    if failures:
        print("FAIL: " + "; ".join(failures), file=sys.stderr)
        return 2
    print("PASS: audit object matches on-disk reports")
    return 0


def cmd_write(
    gate_classification: dict[str, object] | None = None,
) -> int:
    """Write the audit set via the sole production writer.

    CORRECTION12: the CLI is a thin wrapper.  ``cmd_write``
    delegates to :func:`write_audit` (the sole production
    writer) and never directly writes a report file itself.

    When ``gate_classification`` is supplied the call is
    rejected BEFORE any side effect, with exit code 2.  At
    most one write_audit invocation is performed per call;
    a writer failure (``OSError``, ``ValueError``, or
    :class:`AuditWriteError`) is reported on stderr and exits 1.
    """
    if gate_classification is not None:
        print(
            "ERROR: caller-supplied gate_classification is forbidden",
            file=sys.stderr,
        )
        return 2

    try:
        write_audit(layout=canonical_layout())
    except (OSError, ValueError, AuditWriteError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--check", action="store_true", help="Verify reports are up to date.")
    grp.add_argument("--write", action="store_true", help="Write reports.")
    args = parser.parse_args(argv)
    if args.check:
        return cmd_check()
    if args.write:
        return cmd_write()
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
