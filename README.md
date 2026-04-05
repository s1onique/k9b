# k8s-diag-agent

Fixture-driven Kubernetes diagnostics agent that can ingest replayable snapshots or collect real cluster state. Prefer running commands through the project virtual environment (`.venv/bin/python`).

## CLI usage

### Diagnose a fixture (legacy interface)
```bash
k8s-diag-agent fixtures/<name>.json [--output <path>] [--quiet]
```
This path loads a fixture, normalizes signals, runs the reasoning layer, and optionally writes a structured assessment.

### Collect a live snapshot
```bash
k8s-diag-agent snapshot --context <kube-context> --output <snapshot.json>
```
This command discovers the requested Kubernetes context, queries the control plane version, Helm releases, and CRD definitions, and writes a typed `ClusterSnapshot` to the specified file.

### Compare two snapshots
```bash
k8s-diag-agent compare <snapshot-a.json> <snapshot-b.json>
```
Runs the comparator over two snapshot files, reporting differences in Kubernetes versions, Helm release/chart versions, and CRD presence/versions.

### Collect snapshots for configured contexts
```bash
k8s-diag-agent batch-snapshot [--config snapshots/targets.json]
```
Reads `snapshots/targets.json` (or the path passed via `--config`), validates each listed context, and writes typed `ClusterSnapshot` files into `snapshots/` while recording partial Helm/CRD failures inside each snapshot.

## Development

- `.venv/bin/python -m unittest discover tests` (active verification path)
- `.venv/bin/python -m mypy src tests` (type checker; see [typing guidance](docs/typing.md))

## Optional LLM assessment path

```bash
k8s-diag-agent assess-snapshots \
  tests/fixtures/snapshots/sanitized-alpha.json \
  <edited-snapshot.json> \
  [--provider default] [--output path.json]
```

The new `assess-snapshots` command runs the live comparison logic, feeds the sanitized snapshots and diff into the provider seam, and emits an `Assessment`-like JSON payload. Base the initial pairs on `tests/fixtures/snapshots/sanitized-alpha.json` and the derived comparison artifact under `tests/fixtures/comparisons/sanitized-alpha-vs-beta.json` while adjusting the secondary snapshot to produce the diff you want to replay.

See `docs/typing.md` for the type-annotation conventions that guide new code.
