import json
import sys

with open('/tmp/artifacts.json') as f:
    data = json.load(f)
matches = [a for a in data.get('artifacts', []) if a['name'].startswith('experimental-lab-record-')]
if len(matches) != 1:
    print('ERROR: expected 1 artifact, found', len(matches))
    sys.exit(1)
print(matches[0]['id'])
