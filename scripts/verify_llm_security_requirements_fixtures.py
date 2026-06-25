"""Self-test fixtures for LLM security requirements verification.

This module contains inline fixture cases for testing the verifier.
Keeping fixtures separate keeps the main verifier under size limits.
"""

from __future__ import annotations

# Self-test fixtures for verify_llm_security_requirements.py
SELF_TEST_CASES = [
    {
        "name": "valid minimal REQ register passes",
        "registry": (
            "req_id,title,requirement_text,claim_category,security_domain,assurance_level,"
            "source_doc,source_section,status,implementation_refs,verification_refs,owner,"
            "freshness_policy,notes\n"
            "REQ-LLMSEC-001,Test REQ,Test requirement text.,llm_security,threat_model,MUST,"
            "docs/security/threat-model.md,1,current,src/,tests/,security,per_release,Test\n"
        ),
        "should_fail": False,
    },
    {
        "name": "duplicate REQ ID fails",
        "registry": (
            "req_id,title,requirement_text,claim_category,security_domain,assurance_level,"
            "source_doc,source_section,status,implementation_refs,verification_refs,owner,"
            "freshness_policy,notes\n"
            "REQ-LLMSEC-001,First REQ,First requirement text.,llm_security,threat_model,MUST,"
            "docs/security/threat-model.md,1,current,src/,tests/,security,per_release,First\n"
            "REQ-LLMSEC-001,Second REQ,Second requirement text.,llm_security,threat_model,MUST,"
            "docs/security/threat-model.md,2,current,src/,tests/,security,per_release,Duplicate\n"
        ),
        "should_fail": True,
        "expect_error_contains": "Duplicate req_id",
    },
    {
        "name": "malformed REQ ID fails",
        "registry": (
            "req_id,title,requirement_text,claim_category,security_domain,assurance_level,"
            "source_doc,source_section,status,implementation_refs,verification_refs,owner,"
            "freshness_policy,notes\n"
            "REQ-LLMSEC-1,Bad ID,Requirement text.,llm_security,threat_model,MUST,"
            "docs/security/threat-model.md,1,current,src/,tests/,security,per_release,Bad\n"
        ),
        "should_fail": True,
        "expect_error_contains": "does not match pattern",
    },
    {
        "name": "unsorted REQ IDs fail",
        "registry": (
            "req_id,title,requirement_text,claim_category,security_domain,assurance_level,"
            "source_doc,source_section,status,implementation_refs,verification_refs,owner,"
            "freshness_policy,notes\n"
            "REQ-LLMSEC-002,Second REQ,Second requirement text.,llm_security,threat_model,MUST,"
            "docs/security/threat-model.md,2,current,src/,tests/,security,per_release,Second\n"
            "REQ-LLMSEC-001,First REQ,First requirement text.,llm_security,threat_model,MUST,"
            "docs/security/threat-model.md,1,current,src/,tests/,security,per_release,First\n"
        ),
        "should_fail": True,
        "expect_error_contains": "not sorted ascending",
    },
    {
        "name": "unknown claim_category fails",
        "registry": (
            "req_id,title,requirement_text,claim_category,security_domain,assurance_level,"
            "source_doc,source_section,status,implementation_refs,verification_refs,owner,"
            "freshness_policy,notes\n"
            "REQ-LLMSEC-001,Bad Category,Requirement text.,invalid_category,threat_model,MUST,"
            "docs/security/threat-model.md,1,current,src/,tests/,security,per_release,Bad\n"
        ),
        "should_fail": True,
        "expect_error_contains": "invalid claim_category",
    },
    {
        "name": "MUST without implementation_refs fails",
        "registry": (
            "req_id,title,requirement_text,claim_category,security_domain,assurance_level,"
            "source_doc,source_section,status,implementation_refs,verification_refs,owner,"
            "freshness_policy,notes\n"
            "REQ-LLMSEC-001,Missing Refs,Requirement text.,llm_security,threat_model,MUST,"
            "docs/security/threat-model.md,1,current,,tests/,security,per_release,Bad\n"
        ),
        "should_fail": True,
        "expect_error_contains": "requires non-empty implementation_refs",
    },
    {
        "name": "MUST without verification_refs fails",
        "registry": (
            "req_id,title,requirement_text,claim_category,security_domain,assurance_level,"
            "source_doc,source_section,status,implementation_refs,verification_refs,owner,"
            "freshness_policy,notes\n"
            "REQ-LLMSEC-001,Missing Refs,Requirement text.,llm_security,threat_model,MUST,"
            "docs/security/threat-model.md,1,current,src/,,security,per_release,Bad\n"
        ),
        "should_fail": True,
        "expect_error_contains": "requires non-empty verification_refs",
    },
    {
        "name": "N/A requirement passes without impl/ver refs",
        "registry": (
            "req_id,title,requirement_text,claim_category,security_domain,assurance_level,"
            "source_doc,source_section,status,implementation_refs,verification_refs,owner,"
            "freshness_policy,notes\n"
            "REQ-LLMSEC-001,N/A REQ,RAG not used.,llm_security,rag,N/A,"
            "docs/security/llm-requirements-na-rag-mcp-self-hosted.md,1,current,N/A,N/A,"
            "security,per_release,N/A - RAG not used\n"
        ),
        "should_fail": False,
    },
    # Dangling REQ prevention self-tests
    {
        "name": "dangling REQ reference in doc fails",
        "registry": (
            "req_id,title,requirement_text,claim_category,security_domain,assurance_level,"
            "source_doc,source_section,status,implementation_refs,verification_refs,owner,"
            "freshness_policy,notes\n"
            "REQ-LLMSEC-001,Test REQ,Test requirement text.,llm_security,threat_model,MUST,"
            "docs/security/test_fixture.md,1,current,src/,tests/,security,per_release,Test\n"
        ),
        "doc_content": {
            "docs/security/test_fixture.md": "# Test\n\nThis references REQ-LLMSEC-999 which does not exist.",
        },
        "should_fail": True,
        "expect_error_contains": "Dangling REQ reference",
    },
    {
        "name": "known REQ reference in doc passes",
        "registry": (
            "req_id,title,requirement_text,claim_category,security_domain,assurance_level,"
            "source_doc,source_section,status,implementation_refs,verification_refs,owner,"
            "freshness_policy,notes\n"
            "REQ-LLMSEC-001,Test REQ,Test requirement text.,llm_security,threat_model,MUST,"
            "docs/security/test_fixture.md,1,current,src/,tests/,security,per_release,Test\n"
        ),
        "doc_content": {
            "docs/security/test_fixture.md": "# Test\n\nThis references REQ-LLMSEC-001 which exists.",
        },
        "should_fail": False,
    },
]
