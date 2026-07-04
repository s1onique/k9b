"""Duration parsing and aggregation utilities for test timing manifests."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

JUNIT_NS = {"junit": "https://java.com/junit"}
BOOTSTRAP_PLACEHOLDER = "Bootstrap duration manifest"


def classname_to_nodeid(classname: str, name: str) -> str:
    """Convert pytest JUnit classname back to path-style nodeid."""
    if not classname:
        return name
    if "/" in classname:
        # Avoid duplicate names when classname already contains full nodeid
        if "::" in classname and (not name or classname.endswith(f"::{name}")):
            return classname
        return f"{classname}::{name}"
    parts = classname.split(".")
    if len(parts) > 1 and parts[-1][0].isupper():
        module_path = "/".join(parts[:-1]) + ".py"
        return f"{module_path}::{parts[-1]}::{name}"
    return f"{'/'.join(parts)}.py::{name}"


def find_junit_xml_files(paths: list[Path]) -> list[Path]:
    """Find all JUnit XML files from input paths."""
    xml_files: list[Path] = []
    for path in paths:
        if path.is_file():
            if path.suffix.lower() == ".xml":
                xml_files.append(path)
        elif path.is_dir():
            for xml_file in sorted(path.rglob("*.xml")):
                xml_files.append(xml_file)
    return sorted(xml_files)


def parse_junit_xml(file_path: Path) -> list[tuple[str, float]]:
    """Parse JUnit XML file and extract testcase durations."""
    durations: list[tuple[str, float]] = []
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except ET.ParseError as e:
        raise ET.ParseError(f"Failed to parse {file_path}: {e}")
    for testcase in root.iter("testcase"):
        name = testcase.get("name", "")
        classname = testcase.get("classname", "")
        nodeid = classname_to_nodeid(classname, name) if classname else name
        time_str = testcase.get("time", None)
        if time_str is None:
            duration = 0.0
        else:
            try:
                duration = float(time_str)
            except ValueError:
                continue
        if nodeid:
            durations.append((nodeid, duration))
    return durations


def aggregate_durations(
    all_durations: list[tuple[str, float]],
    aggregate_method: str = "max",
) -> list[dict[str, str | float]]:
    """Aggregate multiple duration measurements for the same nodeid."""
    by_nodeid: dict[str, list[float]] = {}
    for nodeid, duration in all_durations:
        by_nodeid.setdefault(nodeid, []).append(duration)
    aggregated: list[dict[str, str | float]] = []
    for nodeid, durations in sorted(by_nodeid.items()):
        final_duration = sum(durations) / len(durations) if aggregate_method == "avg" else max(durations)
        aggregated.append({"nodeid": nodeid, "duration_s": round(final_duration, 6)})
    return aggregated


def is_bootstrap_manifest(file_path: Path | None) -> bool:
    """Check if a duration manifest is a bootstrap placeholder."""
    if file_path is None or not file_path.exists():
        return False
    try:
        with open(file_path) as f:
            data = json.load(f)
        if data.get("durations") == []:
            desc = data.get("description", "")
            note = data.get("note", "")
            return BOOTSTRAP_PLACEHOLDER in desc or BOOTSTRAP_PLACEHOLDER in note
    except (json.JSONDecodeError, OSError):
        pass
    return False


def load_existing_durations(file_path: Path) -> dict[str, float]:
    """Load existing duration manifest for comparison."""
    if not file_path.exists():
        return {}
    try:
        with open(file_path) as f:
            data = json.load(f)
        return {e["nodeid"]: e["duration_s"] for e in data.get("durations", []) if "nodeid" in e and "duration_s" in e}
    except (json.JSONDecodeError, OSError):
        return {}


def compute_shard_balance(durations: dict[str, float], num_shards: int, fallback_weight: float = 1.0) -> dict:
    """Compute shard balance metrics for a duration manifest using LPT algorithm."""
    nodeids = sorted(durations.keys())
    weights = [durations.get(n, fallback_weight) for n in nodeids]
    sorted_pairs = sorted(zip(nodeids, weights), key=lambda x: x[1], reverse=True)
    shard_weights = [0.0] * num_shards
    shard_assignments: list[list[str]] = [[] for _ in range(num_shards)]
    for nodeid, weight in sorted_pairs:
        lightest = min(range(num_shards), key=lambda i: shard_weights[i])
        shard_weights[lightest] += weight
        shard_assignments[lightest].append(nodeid)
    total_weight = sum(shard_weights)
    min_weight = min(shard_weights) if shard_weights else 0
    max_weight = max(shard_weights) if shard_weights else 0
    skew_ratio = max_weight / min_weight if min_weight > 0 else float("inf")
    return {
        "num_shards": num_shards,
        "total_tests": len(nodeids),
        "total_weight": round(total_weight, 4),
        "shard_weights": [round(w, 4) for w in shard_weights],
        "shard_counts": [len(a) for a in shard_assignments],
        "min_weight": round(min_weight, 4),
        "max_weight": round(max_weight, 4),
        "skew_ratio": round(skew_ratio, 4),
    }


def check_balance_threshold(metrics: dict, max_skew_ratio: float = 2.0) -> tuple[bool, str]:
    """Check if shard balance meets acceptable threshold."""
    skew = metrics["skew_ratio"]
    if skew <= max_skew_ratio:
        return True, f"Balance OK (skew={skew:.2f})"
    return False, f"Poor balance (skew={skew:.2f}, threshold={max_skew_ratio})"
