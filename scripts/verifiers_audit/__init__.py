"""AST-driven audit tooling for ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01.

The audit tooling is split into small modules (each <500 lines)
to stay under the LLM-friendly production threshold. The
generator is fully deterministic and never modifies production
verifier files or the verifier-core package.

Top-level entry points:

* :mod:`scripts.verifiers_audit.cli` — argparse CLI
  (``--check``, ``--write``)
* :mod:`scripts.verifiers_audit.builder` — top-level audit object
* :mod:`scripts.verifiers_audit.discovery` — AST-driven helper
  discovery from included verifier files
* :mod:`scripts.verifiers_audit.consumer_map` — real AST-derived
  consumer map for every ``verifier_core.__all__`` symbol
* :mod:`scripts.verifiers_audit.groups` — duplicate-group
  classification (evidence-backed)
* :mod:`scripts.verifiers_audit.candidates` — migration candidate
  scoring and wave assignment
* :mod:`scripts.verifiers_audit.equivalence` — Wave-1 equivalence
  fixtures
* :mod:`scripts.verifiers_audit.report_io` — sharded JSON writer
* :mod:`scripts.verifiers_audit.render` — Markdown renderer
* :mod:`scripts.verifiers_audit.validation` — cross-check
  validators run by ``--check``
"""
