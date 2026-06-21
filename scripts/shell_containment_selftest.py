"""Shell Containment Self-Test Fixtures and Validation.

Provides self-test validation for the shell containment verifier.
"""

from __future__ import annotations

from shell_containment_inventory import (
    REPO_ROOT,
    check_verify_all_shim,
    verify_shell_containment,
)
from shell_containment_rules import (
    calculate_risk_score,
    detect_complex_patterns,
    is_shim_compliant,
)

SELF_TEST_FIXTURES = [
    {
        'name': 'good_shim',
        'path': '.fixtures/shell-containment/good_shim.sh',
        'expected': 'pass',
        'content': '''#!/usr/bin/env bash
# Good shim - only sets env and delegates
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"
exec "$PYTHON" "$REPO_ROOT/scripts/verify.py" "$@"
''',
    },
    {
        'name': 'bad_shim_case',
        'path': '.fixtures/shell-containment/bad_shim_case.sh',
        'expected': 'fail',
        'content': '''#!/usr/bin/env bash
# Bad shim - contains case statement
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"

case "$1" in
    --fast) exec "$PYTHON" "$REPO_ROOT/scripts/verify.py" --fast ;;
    --full) exec "$PYTHON" "$REPO_ROOT/scripts/verify.py" --full ;;
    *) exit 1 ;;
esac
''',
    },
    {
        'name': 'bad_shim_loop',
        'path': '.fixtures/shell-containment/bad_shim_loop.sh',
        'expected': 'fail',
        'content': '''#!/usr/bin/env bash
# Bad shim - contains while loop
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
count=0
while [[ $count -lt 10 ]]; do
    count=$((count + 1))
done
exec python "$REPO_ROOT/script.py"
''',
    },
    {
        'name': 'bad_shim_arrays',
        'path': '.fixtures/shell-containment/bad_shim_arrays.sh',
        'expected': 'fail',
        'content': '''#!/usr/bin/env bash
# Bad shim - contains arrays
set -euo pipefail
declare -a steps=("step1" "step2" "step3")
for step in "${steps[@]}"; do
    echo "$step"
done
exec python script.py
''',
    },
    {
        'name': 'unregistered_shell',
        'path': '.fixtures/shell-containment/unregistered_complex.sh',
        'expected': 'fail',
        'content': '''#!/usr/bin/env bash
# Unregistered complex shell script
set -euo pipefail
curl -s https://example.com/api | jq '.data'
''',
    },
    {
        'name': 'verify_all_shim_only',
        'path': '.fixtures/shell-containment/verify_all.sh',
        'expected': 'pass',
        'content': '''#!/usr/bin/env bash
# Compatibility shim for verify_all.py.
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"
exec "$PYTHON" "$(dirname "$0")/verify_all.py" "$@"
''',
    },
    {
        'name': 'verify_all_shim_violation',
        'path': '.fixtures/shell-containment/verify_all_violation.sh',
        'expected': 'fail',
        'content': '''#!/usr/bin/env bash
# Bad verify_all.sh with case statement
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"

case "$1" in
    --fast) PROFILE=fast ;;
    --full) PROFILE=full ;;
    *) PROFILE=fast ;;
esac

exec "$PYTHON" "$(dirname "$0")/verify_all.py" --profile "$PROFILE"
''',
    },
]


INVENTORY_PATH = REPO_ROOT / "docs/tooling/shell-containment-inventory.csv"


def run_self_test() -> tuple[bool, list[str]]:
    """Run self-test validation."""
    errors = []
    fixture_dir = REPO_ROOT / '.fixtures/shell-containment'
    
    # Create fixture directory
    fixture_dir.mkdir(parents=True, exist_ok=True)
    
    # Write fixtures
    for fixture in SELF_TEST_FIXTURES:
        path = REPO_ROOT / fixture['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fixture['content'])
    
    # Temporarily add fixtures to inventory
    original_inventory = INVENTORY_PATH.read_text() if INVENTORY_PATH.exists() else ""
    
    # Add fixture entries to inventory (matching actual fixture paths)
    inventory_lines = original_inventory.strip().split('\n')
    inventory_lines.append('.fixtures/shell-containment/good_shim.sh,shim,test,Test fixture,Python,done,N/A')
    inventory_lines.append('.fixtures/shell-containment/bad_shim_case.sh,shim,test,Test fixture,Python,done,N/A')
    inventory_lines.append('.fixtures/shell-containment/bad_shim_loop.sh,shim,test,Test fixture,Python,done,N/A')
    inventory_lines.append('.fixtures/shell-containment/bad_shim_arrays.sh,shim,test,Test fixture,Python,done,N/A')
    
    INVENTORY_PATH.write_text('\n'.join(inventory_lines))
    
    try:
        # Test full verifier with unregistered fixture present
        # The unregistered_complex.sh fixture is NOT in inventory, so verify_shell_containment should fail
        result = verify_shell_containment()
        if result.success:
            errors.append("self-test: full verifier should fail with unregistered fixture")
        if result.unregistered_scripts == 0:
            errors.append("self-test: full verifier should detect unregistered scripts")
        unregistered_found = any(
            f.get('status') == 'UNREGISTERED' and 'unregistered_complex.sh' in f.get('path', '')
            for f in result.findings
        )
        if not unregistered_found:
            errors.append("self-test: unregistered_complex.sh should appear in findings")
        
        # Test good shim
        good_shim = REPO_ROOT / '.fixtures/shell-containment/good_shim.sh'
        content = good_shim.read_text()
        is_compliant, violations = is_shim_compliant(content)
        if not is_compliant:
            errors.append(f"self-test: good_shim should pass but got violations: {violations}")
        
        # Test bad shim with case
        bad_case = REPO_ROOT / '.fixtures/shell-containment/bad_shim_case.sh'
        content = bad_case.read_text()
        is_compliant, violations = is_shim_compliant(content)
        if is_compliant:
            errors.append("self-test: bad_shim_case should fail shim check")
        
        # Test bad shim with loop
        bad_loop = REPO_ROOT / '.fixtures/shell-containment/bad_shim_loop.sh'
        content = bad_loop.read_text()
        is_compliant, violations = is_shim_compliant(content)
        if is_compliant:
            errors.append("self-test: bad_shim_loop should fail shim check")
        
        # Test bad shim with arrays
        bad_arrays = REPO_ROOT / '.fixtures/shell-containment/bad_shim_arrays.sh'
        content = bad_arrays.read_text()
        is_compliant, violations = is_shim_compliant(content)
        if is_compliant:
            errors.append("self-test: bad_shim_arrays should fail shim check")
        
        # Test verify_all.sh validation
        verify_all_ok = REPO_ROOT / '.fixtures/shell-containment/verify_all.sh'
        content = verify_all_ok.read_text()
        violations = check_verify_all_shim(content)
        if violations:
            errors.append(f"self-test: verify_all.sh should pass but got violations: {violations}")
        
        verify_all_bad = REPO_ROOT / '.fixtures/shell-containment/verify_all_violation.sh'
        content = verify_all_bad.read_text()
        violations = check_verify_all_shim(content)
        if not violations:
            errors.append("self-test: verify_all_violation.sh should fail verify_all check")
        
        # Test pattern detection
        findings = detect_complex_patterns('while true; do echo hi; done')
        if not findings:
            errors.append("self-test: while loop should be detected")
        
        findings = detect_complex_patterns('curl -s http://example.com | jq .')
        if not findings:
            errors.append("self-test: curl and jq should be detected")
        
        findings = detect_complex_patterns('declare -a arr=(a b c)')
        if not findings:
            errors.append("self-test: array declaration should be detected")
        
        # Test risk scoring
        score = calculate_risk_score([('pattern', 'test', 'HIGH'), ('pattern', 'test', 'MEDIUM')])
        if score != 4:
            errors.append(f"self-test: risk score should be 4, got {score}")
        
        # Test migration backlog generation
        test_findings: list[dict] = [
            {'path': 'test1.sh', 'status': 'DEBT', 'risk_score': 3, 'line_count': 100},
            {'path': 'test2.sh', 'status': 'DEBT', 'risk_score': 1, 'line_count': 50},
            {'path': 'test3.sh', 'status': 'OK'},
        ]
        backlog = generate_migration_backlog(test_findings)
        if len(backlog) != 2:
            errors.append(f"self-test: backlog should have 2 entries, got {len(backlog)}")
        if backlog[0]['risk_score'] != 3:
            errors.append("self-test: backlog should be sorted by risk_score desc")
        
    finally:
        # Restore original inventory
        INVENTORY_PATH.write_text(original_inventory)
        
        # Clean up fixtures
        for fixture in SELF_TEST_FIXTURES:
            path = REPO_ROOT / fixture['path']
            if path.exists():
                path.unlink()
        
        # Remove fixture directory if empty
        if fixture_dir.exists() and not any(fixture_dir.iterdir()):
            fixture_dir.rmdir()
    
    return len(errors) == 0, errors


def generate_migration_backlog(findings: list[dict]) -> list[dict]:
    """Generate ranked migration backlog from findings."""
    debt_scripts = [f for f in findings if f.get('status') == 'DEBT']
    
    # Sort by risk score (highest first)
    ranked = sorted(
        debt_scripts,
        key=lambda x: (x.get('risk_score', 0), x.get('line_count', 0)),
        reverse=True
    )
    
    return [
        {
            'path': item['path'],
            'risk_level': item.get('risk_level'),
            'risk_score': item.get('risk_score'),
            'line_count': item.get('line_count'),
            'patterns': item.get('patterns', []),
            'owner': item.get('owner'),
            'migration_status': item.get('migration_status'),
        }
        for item in ranked
    ]
