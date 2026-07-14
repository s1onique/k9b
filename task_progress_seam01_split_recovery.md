# SEAM01 Split-Only Recovery Task List

## Status: IN PROGRESS

## Issue Summary
The module split introduced several regressions:
1. Test message assertions fail (output format changed)
2. Fault injection patches target wrong module namespaces  
3. Duplicate file parsing (read once for functions, again for violations)
4. CLI output strings changed (breaks established contract)
5. Semantic regressions in provenance checking
6. Nested-loop fixture expects wrong exit code
7. New files not tracked in git

## Recovery Tasks

### 1. Restore CLI output contract
- [ ] Change "No violations found." → "PASS: No SEAM01 promotion-diagnosis handoff contract violations"
- [ ] Change "N violation(s) found." → "FAIL: SEAM01 contract violations found"  
- [ ] Change "ERROR: ..." → "FAIL: verification infrastructure error"
- [ ] Update all test assertions to match new output strings

### 2. Fix fault injection test patches
- [ ] Fix `test_collect_imports_failure_returns_2`: patch `checks.collect_imports` instead of `verifier.collect_imports`
- [ ] Fix `test_provenance_builder_failure_on_attribute_access_returns_2`: patch `checks.build_provenance_at_node` instead of `verifier.build_provenance_at_node`
- [ ] Fix `test_provenance_builder_failure_on_method_call_returns_2`: patch `checks.build_provenance_at_node` instead of `verifier.build_provenance_at_node`
- [ ] Fix `test_collect_functions_failure_returns_2`: patch `flow_collect.collect_functions` instead of `verifier.collect_functions`
- [ ] Fix `test_unexpected_scan_src_exception_returns_2`: patch `verifier.collect_violations` instead of deleted `scan_src`

### 3. Eliminate duplicate file parsing
- [ ] Combine `collect_violations()` and `scan_file()` into single-pass analysis
- [ ] Parse file once, use same tree for function collection and violation detection

### 4. Fix semantic regressions in checks.py
- [ ] Fix direct batch property access: remove `has_promotion_batch_kind` bypass - only allow `attr_chain == ("promotion_result",)`
- [ ] Fix batch→result transition in `_get_expr_provenance`: preserve provenance kind through `.promotion_result` access
- [ ] Fix `self` global trust: verify class identity before accepting self access
- [ ] Restore ownership checks for AnnAssign (not just FunctionDef/AsyncFunctionDef)
- [ ] Restore qualified `builtins.getattr`/`hasattr` coverage

### 5. Fix nested-loop fixture
- [ ] Change expected exit code from 1 to 0 in nested-loop test case

### 6. Git hygiene
- [ ] Track all new files:
  - scripts/verifiers/promotion_diagnosis_handoff_checks.py
  - scripts/verifiers/promotion_diagnosis_handoff_flow_tracking.py
  - scripts/verify_promotion_diagnosis_handoff.py
  - tests/unit/test_seam01_handoff_infrastructure.py
  - tests/unit/test_seam01_handoff_invariants.py
- [ ] Fix whitespace errors for git diff --check

### 7. Verify all tests pass
- [ ] Run infrastructure tests: all 12 should pass
- [ ] Run flow/negative tests: should pass
- [ ] Run ownership tests: should pass
- [ ] Run symbol tests: should pass

## Exit Criteria
- All 12 infrastructure tests pass
- All flow, ownership, and symbol tests pass
- `git diff --check` passes with no whitespace errors
- CLI output matches established contract format
