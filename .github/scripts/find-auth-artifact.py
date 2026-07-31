import json
import sys

arts = json.load(sys.stdin).get('artifacts', [])
matches = [a for a in arts if 'experimental-lab-deploy-authorization' in a['name']]
if not matches:
    print('ERROR: no auth artifact', file=sys.stderr)
    sys.exit(1)
print(matches[0]['id'])
