"""Self-test fixtures for security claim traceability verification.

This module contains inline fixture cases for testing the verifier.
Keeping fixtures separate keeps the main verifier under size limits.
"""

from __future__ import annotations

# Self-test fixtures for verify_security_claim_traceability.py
SELF_TEST_CASES = [
    {
        "name": "valid security claim with implementation refs passes",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/threat-model.md,test-anchor,Test security claim text.,"
            "security,current,security,true,linked,src/k8s_diag_agent/security/sanitizer.py,"
            "on_change,Verified by tests,,\n"
        ),
        "should_fail": False,
    },
    {
        "name": "strict security claim without evidence_ref fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/threat-model.md,test-anchor,Test security claim text.,"
            "security,current,security,true,linked,,on_change,Missing refs,,\n"
        ),
        "should_fail": True,
        "expect_error_contains": "requires non-empty evidence_ref",
    },
    {
        "name": "strict security claim with TODO-only evidence fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/threat-model.md,test-anchor,Test security claim text.,"
            "security,current,security,true,linked,TODO,on_change,TODO only,,\n"
        ),
        "should_fail": True,
        "expect_error_contains": "TODO-only evidence",
    },
    {
        "name": "strict llm_security claim without implementation fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/threat-model.md,test-anchor,Test llm_security claim.,"
            "llm_security,current,security,true,linked,,on_change,Missing,,\n"
        ),
        "should_fail": True,
        "expect_error_contains": "requires non-empty evidence_ref",
    },
    {
        "name": "strict privacy claim without evidence fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/threat-model.md,test-anchor,Test privacy claim.,"
            "privacy,current,security,true,linked,,on_change,Missing,,\n"
        ),
        "should_fail": True,
        "expect_error_contains": "requires non-empty evidence_ref",
    },
    {
        "name": "strict prompt_security claim without evidence fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/threat-model.md,test-anchor,Test prompt_security claim.,"
            "prompt_security,current,security,true,linked,,on_change,Missing,,\n"
        ),
        "should_fail": True,
        "expect_error_contains": "requires non-empty evidence_ref",
    },
    {
        "name": "unknown claim_category fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/threat-model.md,test-anchor,Test claim.,"
            "unknown_category,current,security,true,linked,src/,on_change,Test,,\n"
        ),
        "should_fail": True,
        "expect_error_contains": "unknown claim_type",
    },
    {
        "name": "N/A claim with rationale passes",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/llm-requirements-na-rag-mcp-self-hosted.md,test,RAG not used.,"
            "llm_security,current,security,true,not_required,N/A,per_release,N/A - RAG not used,\n"
        ),
        "should_fail": False,
    },
    {
        "name": "strict security claim with prose-only evidence fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/threat-model.md,test-anchor,Test security claim.,"
            "security,current,security,true,linked,see docs,on_change,see documentation,,\n"
        ),
        "should_fail": True,
        "expect_error_contains": "prose-only evidence",
    },
    {
        "name": "strict claim with prose-only notes verification fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/threat-model.md,test-anchor,Test security claim.,"
            "security,current,security,true,linked,src/k8s_diag_agent/security/sanitizer.py,"
            "on_change,see documentation,,\n"
        ),
        "should_fail": True,
        "expect_error_contains": "prose-only verification evidence",
    },
    {
        "name": "strict claim with executable evidence and notes passes",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,docs/security/threat-model.md,test-anchor,Test security claim.,"
            "security,current,security,true,linked,src/k8s_diag_agent/security/sanitizer.py,"
            "on_change,Verified by tests/test_security.py,,\n"
        ),
        "should_fail": False,
    },
]
