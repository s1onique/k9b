"""Shell Containment Output Formatting.

Handles formatting and display of verification results.
"""

from __future__ import annotations

import json

from shell_containment_contract import FindingDict, VerificationResult


def generate_migration_backlog(findings: list[FindingDict]) -> list[dict]:
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


def format_results(
    result: VerificationResult,
    json_output: bool = False,
    verbose: bool = False,
) -> str:
    """Format verification results."""
    backlog = generate_migration_backlog(result.findings)
    
    if json_output:
        return json.dumps({
            'success': result.success,
            'summary': {
                'total_scripts': result.total_scripts,
                'registered_scripts': result.registered_scripts,
                'unregistered_scripts': result.unregistered_scripts,
                'complex_shims': result.complex_shims,
            },
            'verify_all_violations': result.verify_all_violations,
            'errors': result.errors,
            'findings': result.findings,
            'migration_backlog': backlog,
        }, indent=2)
    
    lines = []
    lines.append("=" * 60)
    lines.append("Shell Containment Verification")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Total shell scripts: {result.total_scripts}")
    lines.append(f"Registered: {result.registered_scripts}")
    lines.append(f"Unregistered: {result.unregistered_scripts}")
    lines.append(f"Complex shims: {result.complex_shims}")
    lines.append("")
    
    if result.errors:
        lines.append("ERRORS:")
        for error in result.errors:
            lines.append(f"  - {error}")
        lines.append("")
    
    if verbose and result.findings:
        lines.append("FINDINGS:")
        for finding in result.findings:
            lines.append(f"  [{finding.get('status', 'UNKNOWN')}] {finding['path']}")
            if 'violations' in finding:
                for v in finding['violations']:
                    lines.append(f"    - {v}")
            if 'patterns' in finding and finding['patterns']:
                lines.append(f"    Patterns: {', '.join(finding['patterns'])}")
            if 'risk_score' in finding:
                lines.append(f"    Risk score: {finding['risk_score']}")
        lines.append("")
    
    if backlog:
        lines.append("MIGRATION BACKLOG (by risk):")
        for i, item in enumerate(backlog[:10], 1):
            lines.append(f"  {i}. {item['path']}")
            lines.append(f"     Risk: {item.get('risk_level', 'N/A')} (score: {item.get('risk_score', 0)})")
            lines.append(f"     Lines: {item.get('line_count', 0)}")
            lines.append(f"     Owner: {item.get('owner', 'N/A')}")
            if item.get('patterns'):
                lines.append(f"     Patterns: {', '.join(item['patterns'][:3])}")
        lines.append("")
    
    lines.append("=" * 60)
    status = "PASSED" if result.success else "FAILED"
    lines.append(f"Shell Containment: {status}")
    lines.append("=" * 60)
    
    return '\n'.join(lines)
