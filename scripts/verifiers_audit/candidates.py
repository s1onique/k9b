"""Migration candidate scoring (R7) and wave assignment.

Each candidate is a per-group scoring record with the eight
R7 axes (0..3). The ``wave`` field is decided by the R7
criteria:

* ``Wave 1`` - exact structural duplicate + no diagnostic
  change + no traversal-boundary change + no exception-behaviour
  change + executable-equivalence-suite passes + no new core
  primitive + expected net deletion.
* ``Wave 2`` - bounded parameter or adapter, no new semantic
  analysis.
* ``Deferred`` - any candidate that requires new shared policy,
  alias resolution, call-graph traversal, closure interpretation,
  flow-sensitive state, generic recursive search, changed
  diagnostic contracts, or weak/absent tests.
* ``CORE-GAP-REQUIRES-DESIGN-REVIEW`` - candidate requires a NEW
  core primitive; the audit MUST NOT add it.
* ``Prohibited`` - the candidate is doctrine-bearing or
  infrastructure-specific and must remain in its production
  verifier.

A candidate is eligible for Wave 1 only if the executable
equivalence suite for its core symbol passed on every case
(see :mod:`scripts.verifiers_audit.equivalence`).

The Wave-1 case counts in :attr:`Candidate.rationale` are
DERIVED from the live equivalence suite at audit time, not
hard-coded, per R3 / CORRECTION03.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from dataclasses import dataclass

# Map core_symbol -> equivalence suite name.  Wave-1 candidates
# must have a suite listed here.
_CORE_SUITE: dict[str, str] = {
    "read_source": "read_source",
    "parse_path": "parse",
    "top_level_function": "top_level_function",
}


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    group_id: str
    core_symbol: str
    structural_equivalence: int
    test_strength: int
    diagnostic_compatibility: int
    control_flow_complexity: int
    typing_readiness: int
    import_bootstrap_simplicity: int
    expected_deletion_benefit: int
    risk_of_behavior_drift: int
    confidence: str
    wave: str
    rationale_template: str

    @property
    def migration_score(self) -> int:
        return (
            self.structural_equivalence
            + self.test_strength
            + self.diagnostic_compatibility
            + self.control_flow_complexity
            + self.typing_readiness
            + self.import_bootstrap_simplicity
            + self.expected_deletion_benefit
        )

    @property
    def risk_score(self) -> int:
        return self.risk_of_behavior_drift

    def rationale(self, suites: dict[str, dict[str, object]]) -> str:
        """Return a rationale string whose case count comes from
        the live equivalence suite, not from a hard-coded literal.
        """
        suite_name = _CORE_SUITE.get(self.core_symbol)
        if suite_name is None:
            return self.rationale_template
        suite = suites.get(suite_name)
        if not isinstance(suite, dict):
            return self.rationale_template
        passed = suite.get("passed")
        total = suite.get("total")
        skipped = suite.get("skipped", 0)
        if not isinstance(passed, int) or not isinstance(total, int):
            return self.rationale_template
        suffix = (
            f" {passed}/{total} equivalence cases pass"
            f" ({skipped} skipped)."
        )
        return self.rationale_template + suffix

    def to_dict(self, suites: dict[str, dict[str, object]]) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "group_id": self.group_id,
            "core_symbol": self.core_symbol,
            "scores": {
                "structural_equivalence": self.structural_equivalence,
                "test_strength": self.test_strength,
                "diagnostic_compatibility": self.diagnostic_compatibility,
                "control_flow_complexity": self.control_flow_complexity,
                "typing_readiness": self.typing_readiness,
                "import_bootstrap_simplicity": self.import_bootstrap_simplicity,
                "expected_deletion_benefit": self.expected_deletion_benefit,
                "risk_of_behavior_drift": self.risk_of_behavior_drift,
            },
            "migration_score": self.migration_score,
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "wave": self.wave,
            "rationale": self.rationale(suites),
        }


_CANDIDATE_TEMPLATES: tuple[Candidate, ...] = (
    Candidate(
        candidate_id="MC-01-WORKSET-READ",
        group_id="GR-03-SOURCE-READ",
        core_symbol="read_source",
        structural_equivalence=3,
        test_strength=3,
        diagnostic_compatibility=3,
        control_flow_complexity=3,
        typing_readiness=3,
        import_bootstrap_simplicity=3,
        expected_deletion_benefit=3,
        risk_of_behavior_drift=0,
        confidence="high",
        wave="Wave 1",
        rationale_template=(
            "_read_source vs read_source: byte-equivalent on every "
            "positive and negative fixture."
        ),
    ),
    Candidate(
        candidate_id="MC-02-WORKSET-PARSE",
        group_id="GR-02-AST-PARSE",
        core_symbol="parse_path",
        structural_equivalence=3,
        test_strength=3,
        diagnostic_compatibility=3,
        control_flow_complexity=3,
        typing_readiness=3,
        import_bootstrap_simplicity=3,
        expected_deletion_benefit=3,
        risk_of_behavior_drift=0,
        confidence="high",
        wave="Wave 1",
        rationale_template=(
            "_parse vs parse_path: byte-equivalent. Both swallow "
            "(OSError, SyntaxError) and return None; both return "
            "ast.Module for valid Python."
        ),
    ),
    Candidate(
        candidate_id="MC-03-WORKSET-TOP-LEVEL-FN-DIRECT",
        group_id="GR-01-TOP-LEVEL-FN-DIRECT",
        core_symbol="top_level_function",
        structural_equivalence=3,
        test_strength=3,
        diagnostic_compatibility=3,
        control_flow_complexity=3,
        typing_readiness=3,
        import_bootstrap_simplicity=3,
        expected_deletion_benefit=3,
        risk_of_behavior_drift=0,
        confidence="high",
        wave="Wave 1",
        rationale_template=(
            "_function_def_in vs top_level_function: both are "
            "direct-child, first-match; neither descends into "
            "nested defs; both ignore AsyncFunctionDef."
        ),
    ),
    Candidate(
        candidate_id="MC-04-WORKSET-TOP-LEVEL-FN-RECURSIVE",
        group_id="GR-04-RECURSIVE-FUNCTION-LOOKUP",
        core_symbol="(no core analogue; new primitive required)",
        structural_equivalence=1,
        test_strength=2,
        diagnostic_compatibility=3,
        control_flow_complexity=2,
        typing_readiness=2,
        import_bootstrap_simplicity=2,
        expected_deletion_benefit=2,
        risk_of_behavior_drift=2,
        confidence="low",
        wave="CORE-GAP-REQUIRES-DESIGN-REVIEW",
        rationale_template=(
            "Both _function_def and _find_function_node use "
            "ast.walk recursively. The core only ships direct-child "
            "top_level_function. Migration requires a NEW "
            "recursive_top_level_function primitive; the audit "
            "MUST NOT add it."
        ),
    ),
    Candidate(
        candidate_id="MC-05-POLICY-AST-CHECKS",
        group_id="GR-05-POLICY-AST-CHECKS",
        core_symbol="(no core analogue)",
        structural_equivalence=0,
        test_strength=0,
        diagnostic_compatibility=0,
        control_flow_complexity=0,
        typing_readiness=0,
        import_bootstrap_simplicity=0,
        expected_deletion_benefit=0,
        risk_of_behavior_drift=3,
        confidence="none",
        wave="Prohibited",
        rationale_template="Policy-bearing; prohibited from migrating.",
    ),
    Candidate(
        candidate_id="MC-06-FLOW-ANALYSIS",
        group_id="GR-06-FLOW-ANALYSIS",
        core_symbol="(no core analogue)",
        structural_equivalence=0,
        test_strength=0,
        diagnostic_compatibility=0,
        control_flow_complexity=0,
        typing_readiness=0,
        import_bootstrap_simplicity=0,
        expected_deletion_benefit=0,
        risk_of_behavior_drift=3,
        confidence="none",
        wave="Prohibited",
        rationale_template="Doctrinal; prohibited from migrating.",
    ),
    Candidate(
        candidate_id="MC-07-METADATA-COLLECTION",
        group_id="GR-07-METADATA-COLLECTION",
        core_symbol="(no core analogue)",
        structural_equivalence=0,
        test_strength=0,
        diagnostic_compatibility=0,
        control_flow_complexity=0,
        typing_readiness=0,
        import_bootstrap_simplicity=0,
        expected_deletion_benefit=0,
        risk_of_behavior_drift=3,
        confidence="none",
        wave="Prohibited",
        rationale_template="Doctrinal; prohibited from migrating.",
    ),
    Candidate(
        candidate_id="MC-08-PARENT-MAP",
        group_id="GR-08-PARENT-MAP",
        core_symbol="(no core analogue)",
        structural_equivalence=0,
        test_strength=0,
        diagnostic_compatibility=0,
        control_flow_complexity=0,
        typing_readiness=0,
        import_bootstrap_simplicity=0,
        expected_deletion_benefit=0,
        risk_of_behavior_drift=3,
        confidence="none",
        wave="Prohibited",
        rationale_template=(
            "Infrastructure-specific; prohibited from migrating."
        ),
    ),
)


CANDIDATES: tuple[Candidate, ...] = _CANDIDATE_TEMPLATES


def wave_breakdown() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in CANDIDATES:
        out.setdefault(c.wave, []).append(c.candidate_id)
    return {wave: sorted(ids) for wave, ids in sorted(out.items())}


def wave_1_candidates() -> list[Candidate]:
    return [c for c in CANDIDATES if c.wave == "Wave 1"]


# ----------------------------------------------------------------------
# Stub kept for backwards compatibility; removed in CORRECTION03 R4.
# The audit object no longer exposes ``projected_net_deletion_lines``;
# the measured value lives in ``source_preservation.measured_deletion``.
# ----------------------------------------------------------------------
def projected_net_deletion_lines() -> int:  # pragma: no cover
    raise NotImplementedError(
        "projected_net_deletion_lines was removed in CORRECTION03 R4; "
        "use scripts.verifiers_audit.patch_simulation.measured_net_deletion_lines()"
    )
