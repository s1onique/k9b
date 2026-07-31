import json
import re
import sys
from pathlib import Path

pattern = re.compile(r"^[^[:space:]@]+@sha256:[0-9a-f]{64}$")
canonical_registry = "harbor-pve1.spbnix.local"
canonical_project = "k9b"
upstream_sha = sys.argv[1]

paths = list(Path("artifacts/record_extracted").glob("*.json"))
if not paths:
    print("FATAL: no JSON in artifact")
    sys.exit(1)
record_path = paths[0]
data = json.loads(record_path.read_text())
errors = []

for f in ("schema_version", "image_class", "subject_sha", "runtime_gate",
          "backend_image_ref", "scheduler_image_ref", "frontend_image_ref",
          "scheduler_uses_backend_image", "full_verify_remains_authoritative",
          "ready_for_image_publication", "ready_for_production_deployment",
          "ready_for_live_acceptance"):
    if f not in data:
        errors.append(f"missing: {f}")

if data.get("image_class") != "experimental-lab":
    errors.append("image_class must be experimental-lab")
if data.get("subject_sha") != upstream_sha:
    errors.append("subject_sha mismatch")
if data.get("runtime_gate") != "pass":
    errors.append("runtime_gate must be pass")
if data.get("scheduler_uses_backend_image") is not True:
    errors.append("scheduler_uses_backend_image must be true")
if data.get("full_verify_remains_authoritative") is not True:
    errors.append("full_verify_remains_authoritative must be true")
for f in ("ready_for_image_publication", "ready_for_production_deployment", "ready_for_live_acceptance"):
    if data.get(f) is not False:
        errors.append(f"{f} must be false")

for label in ("backend", "scheduler", "frontend"):
    ref = data.get(f"{label}_image_ref", "")
    if not pattern.match(ref):
        errors.append(f"malformed {label}_image_ref")

for label in ("backend", "frontend"):
    ref = data.get(f"{label}_image_ref", "")
    repo = ref.split("@")[0]
    parts = repo.split("/")
    if len(parts) != 3:
        errors.append("invalid repo format")
    else:
        _, proj, basename = parts
        if proj != canonical_project:
            errors.append(f"wrong project for {label}")
        if basename != f"k9b-{label}":
            errors.append(f"wrong basename for {label}")

if data.get("scheduler_image_ref") != data.get("backend_image_ref"):
    errors.append("scheduler_image_ref != backend_image_ref")

backend_ref = data.get("backend_image_ref", "")
scheduler_ref = data.get("scheduler_image_ref", "")
backend_digest = backend_ref.split("@")[1] if "@" in backend_ref else ""
scheduler_digest = scheduler_ref.split("@")[1] if "@" in scheduler_ref else ""
if backend_digest != scheduler_digest:
    errors.append("backend/scheduler digest mismatch")

if errors:
    for e in errors:
        print(f"FATAL: {e}")
    sys.exit(1)

print("SCHEMA_AND_IMAGE_CONTRACT=PASS")
print(f"backend_image_ref={data['backend_image_ref']}")
print(f"scheduler_image_ref={data['scheduler_image_ref']}")
print(f"frontend_image_ref={data['frontend_image_ref']}")
