# CI Gate Drift Verifier

## Purpose

The CI Gate Drift Verifier (`scripts/verify_ci_gate_drift.py`) proves that required verification gates from `scripts/verify_all.sh` are represented in GitHub Actions workflows. It prevents silent drift where local verification steps are dropped from CI.

## How It Works

1. **Manifest-based mapping**: Gate mappings are defined in `scripts/ci_gate_mapping.json`
2. **Workflow parsing**: Extracts jobs and commands from `.github/workflows/*.yml`
3. **Fragment verification**: Checks that required command fragments exist in CI jobs
4. **Shard union verification**: Ensures test sharding has both matrix execution AND union verification
5. **Allowlist validation**: Tracks intentional gaps with documented reasons

## Manifest Structure

```json
{
  "_metadata": {
    "version": "1.0.0",
    "description": "Mapping between local verify_all.sh gates and CI workflow equivalents"
  },
  "required_gates": {
    "gate-id": {
      "ci_equivalent": ["job-name-in-ci"],
      "required_command_fragments": ["command fragment to find"],
      "shard_required": false,
      "shard_union_required": false,
      "reason": "Why this gate exists"
    }
  },
  "workflows_to_check": [".github/workflows/harbor.yml"],
  "allowlist": [
    {
      "gate": "gate-id",
      "workflow": ".github/workflows/some.yml",
      "reason": "Why this gate is allowlisted"
    }
  ]
}
```

## Gate Requirements

### Standard Gates
- `ci_equivalent`: List of CI job names that cover this gate
- `required_command_fragments`: Command strings that must appear in CI jobs
- `reason`: Human-readable explanation for the gate

### Sharded Test Gates
For gates like `unit-tests` that run in parallel shards:
- `shard_required: true`: Matrix configuration with multiple shards
- `shard_union_required: true`: Union verification job that proves completeness

Both conditions must be met for the gate to pass.

## Usage

```bash
# Run verification
python scripts/verify_ci_gate_drift.py

# Run self-tests
python scripts/verify_ci_gate_drift.py --self-test

# Verbose output
python scripts/verify_ci_gate_drift.py --verbose
```

## Exit Codes

- `0`: All gates verified (PASS)
- `1`: Verification failed (FAIL)
- `2`: Self-test failed

## Integration

The verifier is wired into `scripts/verify_all.sh` as the `ci-gate-drift` step in the Python lane. It runs after all other verification steps to catch any drift that may have occurred.

## Workflow Files Checked

- `.github/workflows/harbor.yml`
- `.github/workflows/verify.yml`
- `.github/workflows/helm-chart.yml`

## Adding a New Gate

1. Add the gate to `scripts/ci_gate_mapping.json` under `required_gates`
2. Specify `ci_equivalent` job names
3. Add `required_command_fragments` that must appear in CI
4. Set `shard_required` and `shard_union_required` if applicable
5. Provide a `reason` explaining the gate's purpose

## Allowlist Usage

Use the allowlist for intentional gaps:
- Gate is not represented in CI but has a valid reason
- Workflow is path-triggered and not covered by general gates
- Gate is covered by a different mechanism

Allowlist entries require:
- `gate`: Gate ID from `required_gates`
- `workflow`: Workflow file where the gap exists
- `reason`: Minimum 10 characters explaining why the gap is acceptable
