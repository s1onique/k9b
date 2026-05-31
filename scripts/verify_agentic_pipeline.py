#!/usr/bin/env python3
"""
verify_agentic_pipeline.py

Verifies the agentic doctrine pipeline is complete and wired correctly.

Checks:
1. Doctrine manifest exists and is valid YAML
2. Every doctrine file listed in manifest exists
3. Every active non-manual doctrine has at least one agent_rules entry
4. Each agent_rules path exists
5. Each active non-manual doctrine is referenced by at least one agent_rules file
6. Security/path doctrines are referenced from bootstrap rules
7. Task-type bootstrap table exists in fast-task-bootstrap.md
8. Close report requirements are included

Exit codes:
0 - All checks passed
1 - One or more checks failed
"""

import sys
from pathlib import Path

# Add repo root to path for imports
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Install with: pip install pyyaml")
    sys.exit(1)


class PipelineVerifier:
    def __init__(self):
        self.repo_root = REPO_ROOT
        self.errors = []
        self.warnings = []
        
    def log_error(self, msg: str):
        self.errors.append(msg)
        print(f"FAIL: {msg}")
        
    def log_warning(self, msg: str):
        self.warnings.append(msg)
        print(f"WARN: {msg}")
        
    def log_pass(self, msg: str):
        print(f"PASS: {msg}")

    def verify_manifest_exists(self) -> bool:
        """Verify doctrine manifest exists."""
        manifest_path = self.repo_root / "docs" / "doctrine" / "manifest.yaml"
        if not manifest_path.exists():
            self.log_error(f"Manifest not found: {manifest_path}")
            return False
        self.log_pass(f"Manifest exists: {manifest_path}")
        return True

    def verify_manifest_valid_yaml(self) -> bool:
        """Verify manifest is valid YAML."""
        manifest_path = self.repo_root / "docs" / "doctrine" / "manifest.yaml"
        try:
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f)
            if not manifest:
                self.log_error("Manifest is empty")
                return False
            if 'doctrines' not in manifest:
                self.log_error("Manifest missing 'doctrines' key")
                return False
            self.log_pass("Manifest is valid YAML with doctrines list")
            return True
        except yaml.YAMLError as e:
            self.log_error(f"Manifest YAML parse error: {e}")
            return False

    def verify_doctrine_files_exist(self) -> bool:
        """Verify every non-planned doctrine file listed in manifest exists."""
        manifest_path = self.repo_root / "docs" / "doctrine" / "manifest.yaml"
        all_exist = True
        
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)
            
        for doc in manifest.get('doctrines', []):
            doc_file = doc.get('file', '')
            if not doc_file:
                self.log_warning(f"Doctrine {doc.get('id', 'unknown')} has no file specified")
                continue
            
            # Skip planned doctrines - they don't exist yet
            if doc.get('planned', False):
                self.log_pass(f"Doctrine is planned (file not yet created): {doc.get('id', 'unknown')}")
                continue
                
            doc_path = self.repo_root / doc_file
            if not doc_path.exists():
                self.log_error(f"Doctrine file not found: {doc_path}")
                all_exist = False
            else:
                self.log_pass(f"Doctrine file exists: {doc_file}")
                
        return all_exist

    def verify_agent_rules_exist(self) -> bool:
        """Verify agent rule files exist."""
        agent_rules_dir = self.repo_root / ".kilocode" / "rules"
        if not agent_rules_dir.exists():
            self.log_error(f"Agent rules directory not found: {agent_rules_dir}")
            return False
            
        required_rules = [
            '00-global.md',
            '05-fast-task-bootstrap.md',
            '20-architecture-doctrine.md',
        ]
        
        all_exist = True
        for rule in required_rules:
            rule_path = agent_rules_dir / rule
            if not rule_path.exists():
                self.log_error(f"Required agent rule not found: {rule_path}")
                all_exist = False
            else:
                self.log_pass(f"Agent rule exists: {rule}")
                
        return all_exist

    def verify_manifest_agent_rules_exist(self) -> bool:
        """Verify all agent_rules paths in manifest exist."""
        manifest_path = self.repo_root / "docs" / "doctrine" / "manifest.yaml"
        
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)
            
        all_exist = True
        for doc in manifest.get('doctrines', []):
            for rule_path_str in doc.get('agent_rules', []):
                rule_path = self.repo_root / rule_path_str
                if not rule_path.exists():
                    self.log_error(f"agent_rules file not found: {rule_path_str} (from {doc.get('id', 'unknown')})")
                    all_exist = False
                    
        if all_exist:
            self.log_pass("All manifest agent_rules paths exist")
        return all_exist

    def verify_all_active_doctrines_have_agent_rules(self) -> bool:
        """Verify every active non-manual non-planned doctrine has at least one agent_rules entry."""
        manifest_path = self.repo_root / "docs" / "doctrine" / "manifest.yaml"
        
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)
            
        missing = []
        for doc in manifest.get('doctrines', []):
            if doc.get('manual_only', False):
                continue
            if doc.get('planned', False):
                continue
            if not doc.get('agent_rules'):
                missing.append(doc.get('id', 'unknown'))
                
        if missing:
            self.log_error(f"Active non-manual doctrines missing agent_rules: {', '.join(missing)}")
            return False
            
        self.log_pass("All active non-manual doctrines have agent_rules entries")
        return True

    def verify_doctrine_references_in_rules(self) -> bool:
        """Verify active non-manual non-planned doctrines are explicitly referenced in their own agent_rules files."""
        manifest_path = self.repo_root / "docs" / "doctrine" / "manifest.yaml"
        
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)
            
        # Check each active non-manual non-planned doctrine
        unreferenced = []
        for doc in manifest.get('doctrines', []):
            if doc.get('manual_only', False) or doc.get('planned', False):
                continue
                
            doc_id = doc.get('id', '')
            doc_file = doc.get('file', '')
            agent_rules = doc.get('agent_rules', [])
            
            # A doctrine is covered only if one of its own agent_rules files
            # contains either the exact doctrine file path or the exact doctrine id
            referenced_in_rules = False
            
            for rule_path_str in agent_rules:
                rule_path = self.repo_root / rule_path_str
                if rule_path.exists():
                    with open(rule_path) as rf:
                        content = rf.read()
                    # Check for exact doctrine file path
                    if doc_file and doc_file in content:
                        referenced_in_rules = True
                        break
                    # Check for exact doctrine id
                    if doc_id and doc_id in content:
                        referenced_in_rules = True
                        break
                        
            if not referenced_in_rules:
                unreferenced.append(f"{doc_id} (needs reference in: {', '.join(agent_rules)})")
                
        if unreferenced:
            self.log_error(f"Doctrines not explicitly referenced in their own agent_rules files: {', '.join(unreferenced)}")
            return False
            
        self.log_pass("All active non-manual non-planned doctrines are explicitly referenced in their own agent_rules")
        return True

    def verify_security_doctrine_wired(self) -> bool:
        """Verify security/path doctrine is referenced from bootstrap rules."""
        fast_task_bootstrap = self.repo_root / ".kilocode" / "rules" / "05-fast-task-bootstrap.md"
        
        if not fast_task_bootstrap.exists():
            self.log_error("05-fast-task-bootstrap.md not found")
            return False
            
        with open(fast_task_bootstrap) as f:
            content = f.read()
            
        required_references = [
            'path-security-doctrine.md',
            'security/path_validation.py',
            'test_security_path_validation.py',
        ]
        
        all_found = True
        for ref in required_references:
            if ref in content:
                self.log_pass(f"Security bootstrap references: {ref}")
            else:
                self.log_error(f"Security bootstrap missing reference: {ref}")
                all_found = False
                
        return all_found

    def verify_task_bootstrap_table_exists(self) -> bool:
        """Verify task-type bootstrap table exists in fast-task-bootstrap.md."""
        fast_task_bootstrap = self.repo_root / ".kilocode" / "rules" / "05-fast-task-bootstrap.md"
        
        if not fast_task_bootstrap.exists():
            self.log_error("05-fast-task-bootstrap.md not found")
            return False
            
        with open(fast_task_bootstrap) as f:
            content = f.read()
            
        required_sections = [
            'Security-path work',
            'Bug fix',
            'File creation',
            'Doctrines read',
        ]
        
        all_found = True
        for section in required_sections:
            if section.lower() in content.lower():
                self.log_pass(f"Task bootstrap includes: {section}")
            else:
                self.log_error(f"Task bootstrap missing section: {section}")
                all_found = False
                
        return all_found

    def verify_00_global_references_manifest(self) -> bool:
        """Verify 00-global.md references the doctrine manifest."""
        global_rules = self.repo_root / ".kilocode" / "rules" / "00-global.md"
        
        if not global_rules.exists():
            self.log_error("00-global.md not found")
            return False
            
        with open(global_rules) as f:
            content = f.read()
            
        if 'manifest.yaml' in content or 'doctrine' in content.lower():
            self.log_pass("00-global.md references doctrine system")
            return True
        else:
            self.log_warning("00-global.md may not reference doctrine system")
            return True  # Warning, not error

    def verify_path_security_doctrine_content(self) -> bool:
        """Verify path security doctrine has required content."""
        path_doc = self.repo_root / "docs" / "doctrine" / "path-security-doctrine.md"
        
        if not path_doc.exists():
            self.log_error("path-security-doctrine.md not found")
            return False
            
        with open(path_doc) as f:
            content = f.read()
            
        required_sections = [
            'Never validate paths using raw string prefix alone',
            'Resolve/canonicalize before boundary checks',
            'Negative Test Cases',
            'SecurityError',
            'safe_child_path',
        ]
        
        all_found = True
        for section in required_sections:
            if section.lower() in content.lower():
                self.log_pass(f"Path security doctrine includes: {section}")
            else:
                self.log_error(f"Path security doctrine missing: {section}")
                all_found = False
                
        return all_found

    def verify_close_report_section_in_rules(self) -> bool:
        """Verify agent rules include close report requirements."""
        fast_task_bootstrap = self.repo_root / ".kilocode" / "rules" / "05-fast-task-bootstrap.md"
        
        if not fast_task_bootstrap.exists():
            self.log_error("05-fast-task-bootstrap.md not found")
            return False
            
        with open(fast_task_bootstrap) as f:
            content = f.read()
            
        required_elements = [
            'Doctrines read',
            'verification run',
        ]
        
        all_found = True
        for element in required_elements:
            if element.lower() in content.lower():
                self.log_pass(f"Close report section includes: {element}")
            else:
                self.log_error(f"Close report section missing: {element}")
                all_found = False
                
        return all_found

    def run_all_checks(self) -> bool:
        """Run all verification checks."""
        print("=" * 60)
        print("Verifying agentic doctrine pipeline...")
        print("=" * 60)
        print()
        
        checks = [
            ("Manifest exists", self.verify_manifest_exists),
            ("Manifest valid YAML", self.verify_manifest_valid_yaml),
            ("Doctrine files exist", self.verify_doctrine_files_exist),
            ("Agent rules exist", self.verify_agent_rules_exist),
            ("Manifest agent_rules paths exist", self.verify_manifest_agent_rules_exist),
            ("Active doctrines have agent_rules", self.verify_all_active_doctrines_have_agent_rules),
            ("Doctrines referenced in rules", self.verify_doctrine_references_in_rules),
            ("Security doctrine wired", self.verify_security_doctrine_wired),
            ("Task bootstrap table exists", self.verify_task_bootstrap_table_exists),
            ("Global rules reference manifest", self.verify_00_global_references_manifest),
            ("Path security doctrine content", self.verify_path_security_doctrine_content),
            ("Close report section in rules", self.verify_close_report_section_in_rules),
        ]
        
        all_passed = True
        for name, check in checks:
            print(f"\n[{name}]")
            if not check():
                all_passed = False
                
        return all_passed

    def print_summary(self):
        """Print verification summary."""
        print()
        print("=" * 60)
        if self.errors:
            print(f"FAILED: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
            print()
            print("Errors:")
            for err in self.errors:
                print(f"  - {err}")
        if self.warnings:
            print()
            print("Warnings:")
            for warn in self.warnings:
                print(f"  - {warn}")
        print("=" * 60)


def main():
    verifier = PipelineVerifier()
    
    try:
        passed = verifier.run_all_checks()
        verifier.print_summary()
        
        if passed:
            print()
            print("AGENTIC PIPELINE: PASSED")
            sys.exit(0)
        else:
            print()
            print("AGENTIC PIPELINE: FAILED")
            sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Verification failed with exception: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()