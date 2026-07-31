import json
import sys

data = json.load(sys.stdin)
if data.get('expired'):
    print('FATAL: artifact is expired')
    sys.exit(1)
print('ARTIFACT_NOT_EXPIRED=ok')
