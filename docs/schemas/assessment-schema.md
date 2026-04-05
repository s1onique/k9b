# Assessment Schema

| Section | Description |
| --- | --- |
| `observed_signals` | Each signal includes `id`, `description`, `layer`, `evidence_id`, `severity`. |
| `findings` | Derived observations referencing supporting signals and the layer where they arose. |
| `hypotheses` | Causal hypotheses with required `confidence`, `probable_layer`, and `what_would_falsify`. |
| `next_evidence_to_collect` | Actionable checks including owner, method, and needed evidence. |
| `recommended_action` | Observational or mitigation steps annotated with `safety_level`. |
| `safety_level` | Global safety tag for the assessment output. |
| `probable_layer_of_origin` | Optional string indicating the most likely layer (workload/node/etc.). |
| `impact_estimate` | Optional dict describing blast radius and affected services. |
| `overall_confidence` | Optional value pulled from hypotheses if not explicitly provided. |

The machine-checkable schema resides in `src/k8s_diag_agent/schemas.py` (`ASSESSMENT_SCHEMA`). Use `AssessmentValidator.validate` to ensure output stability.
