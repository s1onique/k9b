Feedback artifacts, snapshots, comparisons, and assessments referenced by the operational, evaluation, and adaptation loops live here.

See `docs/schemas/run-artifact-layout.md` for the schema details and naming conventions.

These directories are intentionally DB-free and filesystem-backed so the CLI can replay runs deterministically and the adaptation loop can point to the exact artifact revisions it analyzed.
