"""LLM-safe evidence boundary orchestrator.

This module is the public entrypoint for the LLM-safe verifier. It is a
thin orchestrator: each contract check lives in a dedicated sibling
module so the file stays small enough for the LLM-friendly policy.

The verifier enforces three independent contracts:

1. **Canonical privacy-state definitions** (see
   :mod:`llm_safe_alias_contract`) — every expected alias in
   ``incident_evidence_redaction.py`` must be a ``NewType`` with the
   exact expected direct supertype. Reshuffling the branded chain is
   rejected even when the chain still terminates at ``str``.

2. **Facade re-export contract** (see
   :mod:`llm_safe_facade_contract`) — ``incident_evidence_llm_safe.py``
   must re-export the canonical identities via top-level
   ``from <canonical> import <name>`` statements and must NOT redefine
   them locally with ``NewType(...)``. A facade with no canonical
   imports, a facade whose ``NewType`` provenance is untrusted
   (e.g. ``from fake import NewType``), or a facade that rebinds a
   protected canonical name (e.g. ``RawEvidenceText = str``) is
   rejected.

3. **Strengthened dataclass + helper-signature contract** (see
   :mod:`llm_safe_dataclass_contract`) — ``RedactedEvidenceSummary.summary``
   must be ``LLMSafeEvidenceText``, ``safe_ref`` must be a closed union
   of ``LLMSafeArtifactRef | ReviewPacketStorageRef | None``, and
   ``evidence_artifact_to_llm_safe_summary`` must declare a ``summary``
   parameter typed as ``LLMSafeEvidenceText``. A missing ``summary``
   parameter is rejected.

4. **LLM-boundary review scan** (see :mod:`llm_safe_review_boundary`)
   — case-file, review-packet, and LLM diagnosis modules must not
   leak raw artifact content via direct ``.storage_ref`` access or
   absolute ``artifact_path`` literals.

All four checks are aggregated by :func:`check_llm_safe_evidence_contract`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.incident_lifecycle_boundary._llm_safe_constants import (
    CANONICAL_NEWTYPE_SUPERTYPES,
    LLM_REVIEW_MODULES,
    LLM_SAFE_TYPES,
    REQUIRED_DATACLASS,
    REQUIRED_HELPERS,
)
from scripts.incident_lifecycle_boundary._llm_safe_extract import (
    extract_dataclass_names,
    extract_function_definitions,
    extract_newtype_aliases,
    extract_union_members,
    is_pure_llm_safe_evidence_text_annotation,
    is_safe_ref_shape,
)
from scripts.incident_lifecycle_boundary._llm_safe_provenance import (
    build_newtype_bindings,
    check_newtype_provenance,
)
from scripts.incident_lifecycle_boundary._llm_safe_traversal import (
    collect_module_scope_rebindings,
    iter_module_scope_statements,
)
from scripts.incident_lifecycle_boundary.llm_safe_alias_contract import (
    check_canonical_redaction_aliases,
    resolve_alias_base,
)
from scripts.incident_lifecycle_boundary.llm_safe_dataclass_contract import (
    SUMMARY_REQUIRED_TYPE,
    check_llm_safe_dataclass,
    check_llm_safe_helper_signatures,
    check_llm_safe_helpers,
)
from scripts.incident_lifecycle_boundary.llm_safe_facade_contract import (
    check_llm_safe_canonical_imports,
    check_llm_safe_type_aliases,
)
from scripts.incident_lifecycle_boundary.llm_safe_review_boundary import (
    check_llm_review_unsafe_access,
)


def _resolve_source_root(path: Path) -> Path:
    """Resolve whether ``path`` is the repository root or the source root.

    The negative-proofs harness creates a Python source-root-shaped temp
    tree directly under ``<temp>/k8s_diag_agent/...`` and passes
    ``<temp>`` as ``--repo-root``. The production CLI invokes this
    function with ``Path("src")`` (the source root). Tests in this
    codebase pass the actual repository root (containing ``.git`` and
    ``src/``). All three contract forms must resolve to the same
    canonical privacy-state module path.
    """
    if (path / "src" / "k8s_diag_agent").exists():
        # Repository root layout: ``<root>/src/k8s_diag_agent/...``.
        return path / "src"
    if (path / "k8s_diag_agent").exists():
        # Source-root layout: ``<root>/k8s_diag_agent/...``.
        return path
    # Fall back to the path unchanged so callers at least see a
    # predictable diagnostic rather than a hidden resolution.
    return path


def check_llm_safe_evidence_contract(
    evidence_filepath: str,
    repo_root: Path,
    *,
    canonical_filepath: str | None = None,
) -> list[str]:
    """Run all LLM-safe evidence contract checks.

    R14 invariant: ``repo_root`` may be either the repository root
    (containing ``.git`` and ``src/``) or the Python source root
    (``<repo>/src``, where ``k8s_diag_agent/`` lives). The function
    resolves both forms to the canonical privacy-state module path
    via :func:`_resolve_source_root` so the negative-proofs harness
    (which constructs a temp tree at source-root shape) and the
    production CLI (which passes ``Path("src")``) and unit tests
    (which pass the repository root) all locate the same canonical
    file. ``canonical_filepath``, when provided, is interpreted
    relative to the resolved source root.

    Args:
        evidence_filepath: Path to the facade module (re-exports).
        repo_root: Repository root OR Python source root for module
            scanning. The function auto-detects which form was
            supplied via :func:`_resolve_source_root`.
        canonical_filepath: Optional override for the canonical privacy-
            state module path. When omitted, the path is computed as
            ``<source_root>/k8s_diag_agent/collect/incident_evidence_redaction.py``.

    Returns:
        Combined list of error messages from all contract checks.
    """
    errors: list[str] = []

    source_root = _resolve_source_root(repo_root)

    if canonical_filepath is None:
        canonical_path = str(
            source_root
            / "k8s_diag_agent"
            / "collect"
            / "incident_evidence_redaction.py"
        )
    else:
        canonical_path = canonical_filepath

    # 1. Canonical privacy-state hierarchy must be declared correctly.
    canonical_errors = check_canonical_redaction_aliases(canonical_path)
    errors.extend(canonical_errors)

    # 2. Facade must re-export, not redefine.
    facade_errors = check_llm_safe_type_aliases(evidence_filepath)
    errors.extend(facade_errors)

    # 3. Facade must import every canonical alias from the canonical module.
    canonical_import_errors = check_llm_safe_canonical_imports(
        evidence_filepath,
        canonical_module="k8s_diag_agent.collect.incident_evidence_redaction",
    )
    errors.extend(canonical_import_errors)

    # 4. Dataclass summary field must be LLMSafeEvidenceText (not merely redacted).
    dataclass_errors = check_llm_safe_dataclass(evidence_filepath)
    errors.extend(dataclass_errors)

    # 5. Required helpers must exist.
    helper_errors = check_llm_safe_helpers(evidence_filepath)
    errors.extend(helper_errors)

    # 6. Helper signatures must declare the LLM-safe contract.
    helper_sig_errors = check_llm_safe_helper_signatures(evidence_filepath)
    errors.extend(helper_sig_errors)

    # 7. LLM/review modules must not expose unsafe types. The review-
    #    boundary paths in ``LLM_REVIEW_MODULES`` are written relative
    #    to the source root, so the resolved source root is passed in.
    unsafe_errors = check_llm_review_unsafe_access(source_root)
    errors.extend(unsafe_errors)

    return errors


__all__ = [
    "CANONICAL_NEWTYPE_SUPERTYPES",
    "LLM_SAFE_TYPES",
    "REQUIRED_DATACLASS",
    "REQUIRED_HELPERS",
    "SUMMARY_REQUIRED_TYPE",
    "build_newtype_bindings",
    "check_canonical_redaction_aliases",
    "check_llm_review_unsafe_access",
    "check_llm_safe_canonical_imports",
    "check_llm_safe_dataclass",
    "check_llm_safe_evidence_contract",
    "check_llm_safe_helper_signatures",
    "check_llm_safe_helpers",
    "check_llm_safe_type_aliases",
    "check_newtype_provenance",
    "collect_module_scope_rebindings",
    "extract_dataclass_names",
    "extract_function_definitions",
    "extract_newtype_aliases",
    "extract_union_members",
    "is_pure_llm_safe_evidence_text_annotation",
    "is_safe_ref_shape",
    "iter_module_scope_statements",
    "resolve_alias_base",
]


if __name__ == "__main__":
    print("LLM-safe evidence types required (canonical privacy-state hierarchy):")
    for alias in sorted(LLM_SAFE_TYPES):
        supertype = CANONICAL_NEWTYPE_SUPERTYPES.get(alias, "?")
        print(f"  - {alias} = NewType('{alias}', {supertype})")
    print(f"\nSummary field type: {SUMMARY_REQUIRED_TYPE}")
    print(f"\nRequired dataclass: {REQUIRED_DATACLASS}")
    print("\nRequired helpers:")
    for helper in sorted(REQUIRED_HELPERS):
        print(f"  - {helper}()")
    print("\nLLM/review modules to check:")
    for module in LLM_REVIEW_MODULES:
        print(f"  - {module}")
    sys.exit(0)