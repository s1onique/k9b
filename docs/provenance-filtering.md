# BETA-G7: Provenance Filtering for Artifact Quality

## Overview

This document describes the provenance filtering mechanism implemented in Epic BETA-G7 to improve operator trust by filtering skipped, empty, or otherwise non-useful artifact references from incident report and operator worklist source references.

## Problem

Today, source references are surfaced in `sourceArtifactRefs`, but not all surfaced references are equally useful. Operators were being encouraged to click artifacts that:
- Were skipped intentionally
- Contained only adapter/preflight failure stubs
- Contained no meaningful evidence payload
- Were known to be non-actionable placeholders

This weakened operator trust and made provenance feel noisy.

## Solution

Implemented filtering logic in `src/k8s_diag_agent/ui/api_incident_report_filtering.py` that:

1. Reads artifact metadata from disk to determine provenance quality
2. Filters artifacts that are non-useful
3. Preserves useful and partially useful artifacts
4. Maintains a minimum fallback to prevent claims from losing all provenance

## Filtering Rules

### Artifacts Filtered (Non-Useful)

1. **Skipped artifacts** (status=skipped)
   - Explicitly not executed
   - No evidence collected

2. **Placeholder artifacts** (known error patterns)
   - `adapter is not configured`
   - `adapter is not registered`
   - `adapter not found`
   - `not configured`
   - `not registered`

3. **Empty artifacts** (no evidence content)
   - No raw_output
   - No payload
   - No summary
   - No findings or suggestions

### Artifacts Preserved (Useful)

1. **Successful artifacts with evidence**
   - Has actual output, payload, or diagnostic content
   - Contains findings or suggested_next_checks

2. **Failed artifacts with diagnostic context**
   - Has failure_metadata (structured diagnostic info)
   - Has meaningful error_summary
   - Has partial evidence in payload

3. **Canonical references**
   - Assessment artifacts
   - Drilldown artifacts
   - Execution result artifacts

### Safety Fallback

If filtering would remove ALL provenance from a claim, the original list is preserved. This prevents the edge case where a claim would appear to have provenance but have no actual references.

## Implementation

### Module: `api_incident_report_filtering.py`

Key functions:

- `_is_placeholder_artifact()`: Checks if artifact is a known placeholder pattern
- `_has_useful_evidence()`: Checks if artifact contains useful diagnostic content
- `_should_filter_artifact()`: Determines if artifact should be filtered
- `filter_artifact_links()`: Filters a list of artifact links
- `filter_artifact_refs_preserving_minimum()`: Filters with safety fallback

### Integration Points

1. **Incident Report Builder** (`_build_incident_report_payload`)
   - Filters `sourceArtifactRefs` before returning report
   - Applied after deduplication step

2. **Worklist Builder** (`_build_operator_worklist_payload`)
   - Filters `sourceArtifactRefs` for each worklist item
   - Applied after all items are built

## Data Flow

```
Artifact Links (from assessment/drilldown/enrichment)
         |
         v
   Deduplication (preserve order)
         |
         v
   Artifact Filtering (read metadata, apply rules)
         |
         v
   Provenance Quality Improved
         |
         v
   Incident Report / Worklist Output
```

## Observability

The filtering result includes:
- `filtered_links`: Filtered artifact links suitable for operator-facing provenance
- `had_filtered_refs`: Boolean indicating if any refs were filtered
- `original_count`: Count of refs before filtering
- `filter_summary`: Human-readable summary of what was filtered

## Testing

Tests in `tests/unit/test_api_incident_report_filtering.py`:

1. **SkippedArtifactFilteringTests**
   - Skipped artifacts are filtered
   - Skipped with skip_reason_only are filtered
   - Mixed refs: only skipped filtered

2. **PlaceholderArtifactFilteringTests**
   - Adapter-not-registered filtered
   - Adapter-not-configured filtered
   - Error summary placeholders filtered
   - Meaningful errors preserved

3. **UsefulArtifactPreservationTests**
   - Successful with output preserved
   - Successful with payload preserved
   - Failed with failure_metadata preserved
   - Failed with meaningful error preserved

4. **MixedRefsFilteringTests**
   - Multiple useful refs all survive
   - Mixed refs filter non-useful only

5. **PreservingMinimumTests**
   - Filtering all would remove preserves original
   - Filtering some preserves filtered

6. **NoFakeUnknownTests**
   - No unknown labels in filtered results
   - No unknown paths in filtered results

## Fixtures

Regression fixtures in `tests/fixtures/incident_report_filtering_fixtures.py`:

- `_fixture_skipped_external_analysis`: Skipped artifact (filtered)
- `_fixture_adapter_not_registered`: Placeholder (filtered)
- `_fixture_useful_execution_artifact`: Useful execution (preserved)
- `_fixture_partial_diagnostic_artifact`: Partial evidence (preserved)
- `_fixture_failed_with_diagnostic_context`: Failed with context (preserved)
- `_fixture_empty_placeholder`: Empty artifact (filtered)
- `_fixture_mixed_refs_with_filtering`: Mixed scenario

## Constraints

1. **No new persistence layer**: Filtering is derived-only and stateless
2. **Preserve artifact-first behavior**: No frontend-only filtering
3. **Backward compatibility**: Additive or behaviorally narrowing only
4. **Truthfulness standards**: Do not over-filter
5. **Minimum fallback**: Claims don't lose all provenance

## Future Considerations

- Add more sophisticated useful evidence detection
- Consider aggregating filter statistics for observability
- Potential for operator-configurable filtering rules