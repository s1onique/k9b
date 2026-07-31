import json
import sys
import urllib.request
from pathlib import Path

paths = list(Path("artifacts/auth_extracted").glob("*.json"))
if not paths:
    print("ERROR: no JSON")
    sys.exit(1)
data = json.loads(paths[0].read_text())

req = urllib.request.Request(
    "https://api.github.com/repos/${{ github.repository }}/git/ref/heads/main",
    headers={"Authorization": "Bearer ${{ github.token }}",
             "Accept": "application/vnd.github.v3+json"}
)
with urllib.request.urlopen(req) as resp:
    current_main = json.loads(resp.read())["object"]["sha"]

if data["upstream_head_sha"] != current_main:
    print("FATAL: main SHA changed")
    sys.exit(1)

required = ("authorization_status", "subject_sha", "backend_image_ref",
            "scheduler_image_ref", "frontend_image_ref")
for f in required:
    if f not in data:
        print(f"ERROR: missing {f}")
        sys.exit(1)

print(f"RECORD_VALID=PASS status={data['authorization_status']}")
