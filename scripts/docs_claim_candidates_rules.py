"""Rules for docs_claim_candidates scanner.

Detection patterns and claim analysis logic.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from docs_claim_candidates_contract import (
    CLAIM_TYPE_PATTERNS,
    MIN_PROSE_LENGTH,
    REPO_ROOT,
    SEVERITY_BY_TYPE,
    ScanResult,
)
from docs_claim_candidates_loader import (
    get_claim_trace_required,
    get_doc_class,
    get_truth_status,
)


def generate_candidate_id(
    doc_path: str, candidate_text: str, claim_type: str, line_number: int
) -> str:
    """Generate a deterministic candidate ID from content."""
    normalized = f"{doc_path}|{line_number}|{candidate_text.lower().strip()}|{claim_type}"
    hash_digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"DOC-CAND-{hash_digest}"


def detect_claim_types(text: str) -> list[str]:
    """Detect which claim types match the given text."""
    detected: list[str] = []
    text_lower = text.lower()

    for claim_type, patterns in CLAIM_TYPE_PATTERNS.items():
        keywords = patterns.get("keywords", [])
        for pattern in keywords:
            if re.search(pattern, text_lower, re.IGNORECASE) is not None:
                if claim_type not in detected:
                    detected.append(claim_type)
                break

    return detected


def determine_severity(claim_types: list[str]) -> str:
    """Determine severity based on claim types present."""
    if not claim_types:
        return "low"

    for claim_type in claim_types:
        if SEVERITY_BY_TYPE.get(claim_type) == "high":
            return "high"

    for claim_type in claim_types:
        if SEVERITY_BY_TYPE.get(claim_type) == "medium":
            return "medium"

    return "low"


def determine_registration_status(doc_path: str, truth_status: str, doc_class: str) -> str:
    """Determine initial registration status based on doc classification."""
    if doc_class in ("historical", "external_import"):
        return "ignored_historical"
    if truth_status in ("historical",):
        return "ignored_historical"
    if truth_status in ("stale", "unknown"):
        return "ignored_stale"
    if doc_class == "generated":
        return "ignored_by_policy"
    return "unregistered"


def is_code_block(text: str) -> bool:
    """Check if text appears to be inside a code block."""
    return text.strip().startswith(("```", "    ", "\t"))


def is_table_separator(text: str) -> bool:
    """Check if text is a table separator row."""
    stripped = text.strip()
    return bool(stripped) and all(c in "|-: " for c in stripped) and "|" in stripped


def is_pure_heading(text: str) -> bool:
    """Check if text is just a heading."""
    stripped = text.strip()
    return bool(stripped) and stripped.startswith("#") and "\n" not in stripped


def is_trivial_prose(text: str, claim_types: list[str]) -> bool:
    """Check if text is too short or trivial to be a claim."""
    if len(text.strip()) < MIN_PROSE_LENGTH:
        return True
    if not claim_types:
        return True
    return False


def is_stale_historical_doc(doc_path: str, truth_status: str, doc_class: str) -> bool:
    """Check if doc is stale or historical."""
    if doc_class in ("historical", "external_import"):
        return True
    if truth_status in ("historical", "stale", "unknown"):
        return True
    return False


def extract_candidate_text(line: str, doc_path: str, line_num: int) -> str:
    """Extract candidate text from a line, stripping formatting."""
    text = line.strip()
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`#]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def scan_document(doc_path: Path) -> ScanResult:
    """Scan a single document for claim candidates."""
    result = ScanResult()
    rel_path = str(doc_path.relative_to(REPO_ROOT)).replace("\\", "/")

    truth_status = get_truth_status(rel_path)
    doc_class = get_doc_class(rel_path)
    claim_trace_required = get_claim_trace_required(rel_path)

    try:
        content = doc_path.read_text(encoding="utf-8")
    except Exception as e:
        result.errors.append(f"Failed to read {rel_path}: {e}")
        return result

    in_code_block = False
    lines = content.split("\n")

    for line_num, line in enumerate(lines, start=1):
        if re.match(r"```", line.strip()):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        stripped = line.strip()

        if not stripped:
            continue

        if is_pure_heading(stripped) and not any(
            stripped.startswith(f"{'#' * i} ") for i in range(1, 5)
        ):
            continue

        if is_table_separator(stripped):
            continue

        if is_code_block(stripped):
            continue

        candidate_text = extract_candidate_text(stripped, rel_path, line_num)

        if len(candidate_text) < MIN_PROSE_LENGTH:
            continue

        claim_types = detect_claim_types(candidate_text)

        if not claim_types:
            continue

        severity = determine_severity(claim_types)
        registration_status = determine_registration_status(rel_path, truth_status, doc_class)
        trace_required = "true" if claim_trace_required else "false"
        candidate_id = generate_candidate_id(
            rel_path, candidate_text, "|".join(claim_types), line_num
        )
        anchor = f"line-{line_num}"
        detection_rules = "|".join(claim_types)

        candidate = {
            "candidate_id": candidate_id,
            "doc_path": rel_path,
            "line_number": str(line_num),
            "anchor": anchor,
            "candidate_text": candidate_text,
            "detected_claim_types": "|".join(claim_types),
            "detection_rules": detection_rules,
            "doc_class": doc_class,
            "truth_status": truth_status,
            "claim_trace_required": trace_required,
            "candidate_severity": severity,
            "registered_claim_id": "",
            "registration_status": registration_status,
            "notes": "",
        }

        result.candidates.append(candidate)

    return result


CSV_FIELDS = [
    "candidate_id",
    "doc_path",
    "line_number",
    "anchor",
    "candidate_text",
    "detected_claim_types",
    "detection_rules",
    "doc_class",
    "truth_status",
    "claim_trace_required",
    "candidate_severity",
    "registered_claim_id",
    "registration_status",
    "notes",
]
