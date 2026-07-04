#!/usr/bin/env python3
"""P4c forensic dump: provenance and loop dumps.

This module is a thin facade that re-exports from focused sibling modules:
- k9b_otel_demo_lab_p4c_forensic_dump_contract: Constants and helpers
- k9b_otel_demo_lab_p4c_forensic_dump_provenance: Freshness guard and provenance capture
- k9b_otel_demo_lab_p4c_forensic_dump_writers: Dump writer functions

Required forensic dumps:
1. Backend runtime provenance (image, labels, env)
2. P4c script/runtime provenance (git SHA, module source)
3. Backend incident detail JSON before diagnosis-loop pass 1
4. Backend diagnosis-loop request/response JSON for each pass

This is committed as test/lab instrumentation, NOT ad-hoc manual debugging.

Enable with: K9B_P4C_FORENSIC_DUMP=1

The remaining dumps (5-6) and summary/integration helpers are in
k9b_otel_demo_lab_p4c_forensic_dump_evidence.py.
"""

from __future__ import annotations

# Re-export for consumers that import from this module
from scripts.k9b_otel_demo_lab_p4c_forensic_dump_evidence import (  # noqa: F401
    FORENSIC_DUMP_DIR_ENV,
    FORENSIC_DUMP_ENABLED,
    _get_forensic_dump_dir,
    _mapping_summary,
)

# Re-export provenance functions
from scripts.k9b_otel_demo_lab_p4c_forensic_dump_provenance import (  # noqa: F401
    check_live_lab_freshness,
    dump_backend_runtime_provenance,
    dump_p4c_runtime_provenance,
)

# Re-export dump writer functions
from scripts.k9b_otel_demo_lab_p4c_forensic_dump_writers import (  # noqa: F401
    dump_backend_incident_detail_before_loop,
    dump_diagnosis_loop_pass,
)
