import json
import sys
from pathlib import Path

record = json.loads(sys.argv[1])
path = Path("artifacts/experimental-lab-deploy-authorization.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(record, indent=2))
print(json.dumps(record, indent=2))
