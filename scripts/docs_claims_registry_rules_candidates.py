"""Candidate ID validation rules for docs_claims_registry verifier.

Contains validation logic for candidate_ids field.
"""

from __future__ import annotations

from docs_claims_registry_contract import (
    CANDIDATE_ID_PATTERN,
    RegistryCheckResult,
)
from docs_claims_registry_loader import read_candidates


def check_candidate_ids_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check candidate_ids validity and backlink symmetry."""
    result = RegistryCheckResult()

    # Load candidates with their registration info
    candidates_by_id = read_candidates()

    # Build registry candidate_ids lookup: claim_id -> set of candidate_ids
    claim_to_candidates: dict[str, set[str]] = {}
    for row in rows:
        claim_id = row.get("claim_id", "").strip()
        candidate_ids = row.get("candidate_ids", "").strip()
        if candidate_ids:
            claim_to_candidates[claim_id] = {
                cid.strip() for cid in candidate_ids.split(";") if cid.strip()
            }

    # Reverse checks: scan all candidates for backlink symmetry
    for cid, cand in candidates_by_id.items():
        reg_id = cand.get("registered_claim_id", "").strip()
        status = cand.get("registration_status", "").strip()

        # registered must have back-link
        if status == "registered" and not reg_id:
            result.add_error(
                f"Candidate '{cid}' has registration_status='registered' but missing registered_claim_id"
            )

        # back-link must have registered status
        if reg_id and status != "registered":
            result.add_error(
                f"Candidate '{cid}' has registered_claim_id='{reg_id}' but status='{status}' "
                f"(expected: registered)"
            )

        # back-link must point to existing claim
        if reg_id:
            claim_exists = any(r.get("claim_id", "").strip() == reg_id for r in rows)
            if not claim_exists:
                result.add_error(
                    f"Candidate '{cid}' back-links to '{reg_id}' which does not exist in registry"
                )

            # registered candidate must be listed in that exact claim's candidate_ids
            if status == "registered":
                claim_cids = claim_to_candidates.get(reg_id, set())
                if cid not in claim_cids:
                    result.add_error(
                        f"Candidate '{cid}' back-links to '{reg_id}' but is not listed "
                        f"in that claim's candidate_ids field"
                    )

    for i, row in enumerate(rows):
        claim_id = row.get("claim_id", "").strip()
        candidate_ids = row.get("candidate_ids", "").strip()
        claim_status = row.get("claim_status", "").strip()
        evidence_required = row.get("evidence_required", "").strip().lower()

        # New curated claims (DOC-CLAIM-0019+) require candidate_ids
        is_new_claim = claim_id >= "DOC-CLAIM-0019"
        if is_new_claim and claim_status == "current" and evidence_required == "true":
            if not candidate_ids:
                result.add_error(
                    f"Row {i + 2}: New curated claim '{claim_id}' is missing candidate_ids "
                    f"(expected: at least one DOC-CAND-xxx reference)"
                )

        if not candidate_ids:
            continue

        # Parse semicolon-separated candidate IDs
        for cid in candidate_ids.split(";"):
            cid = cid.strip()
            if not cid:
                continue

            # Check format
            if not CANDIDATE_ID_PATTERN.match(cid):
                result.add_error(
                    f"Row {i + 2}: candidate_id '{cid}' does not match pattern DOC-CAND-<12-char-hex>"
                )
                continue

            # Check existence
            if cid not in candidates_by_id:
                result.add_error(
                    f"Row {i + 2}: candidate_id '{cid}' not found in generated_claim_candidates shards"
                )
                continue

            # Check backlink symmetry
            cand = candidates_by_id[cid]
            cand_reg_id = cand.get("registered_claim_id", "").strip()
            cand_status = cand.get("registration_status", "").strip()

            # Candidate must be registered
            if cand_status != "registered":
                result.add_error(
                    f"Row {i + 2}: candidate '{cid}' has registration_status='{cand_status}' "
                    f"(expected: registered)"
                )

            # Candidate's back-link must match this claim
            if cand_reg_id != claim_id:
                result.add_error(
                    f"Row {i + 2}: candidate '{cid}' back-links to '{cand_reg_id}' "
                    f"(expected: {claim_id})"
                )

    return result