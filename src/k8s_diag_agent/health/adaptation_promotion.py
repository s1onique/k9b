"""Proposal promotion and patch rendering for health adaptation."""
from __future__ import annotations

import difflib
import json
from collections import OrderedDict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .adaptation_models import HealthProposal
from .baseline import (
    DEFAULT_CRD_NEXT_CHECK,
    DEFAULT_RELEASE_NEXT_CHECK,
    BaselineDriftCategory,
    resolve_baseline_policy_path,
)


class PromotionError(Exception):
    pass


class UnsupportedProposalTarget(PromotionError):
    pass


class PromotionNotApplicable(PromotionError):
    """Raised when proposal promotion does not apply."""
    pass


_HEALTH_CONFIG_TARGETS = {
    "health.trigger_policy.warning_event_threshold",
    "health.noise_filters.ignored_reasons",
}

_BASELINE_TARGETS = {
    "health.baseline_policy.watched_releases",
    "health.baseline_policy.required_crd_families",
    "health.baseline_policy.ignored_drift",
}

_DURABLE_LEARNING_TARGETS = {
    "health.durable_learning.namespace",
    "health.durable_learning.cluster",
    "health.durable_learning.service",
}


def render_proposal_patch(
    proposal: HealthProposal,
    health_config_path: Path,
    output_dir: Path,
    baseline_path: Path | None = None,
) -> Path:
    target = proposal.target
    if target in _HEALTH_CONFIG_TARGETS:
        target_path = health_config_path
    elif target in _BASELINE_TARGETS:
        target_path = baseline_path or _resolve_baseline_path(health_config_path)
    elif target in _DURABLE_LEARNING_TARGETS:
        # Durable learning proposals are advisory-only, not auto-applicable
        raise PromotionNotApplicable(
            f"Durable learning proposals require explicit operator review: {target}"
        )
    else:
        raise UnsupportedProposalTarget(f"Unsupported proposal target: {target}")
    original_text = target_path.read_text(encoding="utf-8")
    data = _load_ordered_json(target_path)
    if target == "health.trigger_policy.warning_event_threshold":
        _apply_threshold_update(data, proposal.promotion_payload)
    elif target == "health.noise_filters.ignored_reasons":
        _apply_noise_update(data, proposal.promotion_payload)
    elif target == "health.baseline_policy.watched_releases":
        _apply_release_update(data, proposal.promotion_payload)
    elif target == "health.baseline_policy.required_crd_families":
        _apply_crd_update(data, proposal.promotion_payload)
    elif target == "health.baseline_policy.ignored_drift":
        _apply_ignored_drift_update(data, proposal.promotion_payload)
    else:
        raise UnsupportedProposalTarget(f"Unsupported proposal target: {target}")
    updated_text = _dump_json(data)
    return _write_patch(target_path, original_text, updated_text, output_dir, proposal.proposal_id)


def _load_ordered_json(path: Path) -> OrderedDict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    parsed = json.loads(raw_text, object_pairs_hook=OrderedDict)
    if isinstance(parsed, Mapping):
        return OrderedDict(parsed)
    return OrderedDict()


def _dump_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _normalize_version(value: str) -> str:
    return value.lstrip("vV").strip()


def _apply_threshold_update(data: OrderedDict[str, Any], payload: Mapping[str, Any]) -> None:
    triggers = data.setdefault("comparison_triggers", OrderedDict())
    threshold_value = payload.get("threshold")
    if threshold_value is None:
        raise PromotionError("Promotion payload missing threshold value")
    try:
        triggers["warning_event_threshold"] = int(threshold_value)
    except (TypeError, ValueError) as exc:
        raise PromotionError(f"Invalid threshold value: {threshold_value}") from exc


def _apply_noise_update(data: OrderedDict[str, Any], payload: Mapping[str, Any]) -> None:
    reason = payload.get("reason")
    if not reason:
        raise PromotionError("Promotion payload missing noise reason")
    noise_filters = data.setdefault("noise_filters", OrderedDict())
    ignored = noise_filters.setdefault("ignored_reasons", [])
    if not isinstance(ignored, list):
        ignored = list(ignored)
        noise_filters["ignored_reasons"] = ignored
    if reason not in ignored:
        ignored.append(str(reason))


def _apply_release_update(data: OrderedDict[str, Any], payload: Mapping[str, Any]) -> None:
    release_key = payload.get("release_key")
    versions = payload.get("versions")
    if not release_key or not versions:
        raise PromotionError("Promotion payload missing release key or versions")
    releases = data.setdefault("watched_releases", [])
    target_entry: OrderedDict[str, Any] | None = None
    for entry in releases:
        if isinstance(entry, Mapping) and str(entry.get("release")) == release_key:
            target_entry = OrderedDict(entry)
            index = releases.index(entry)
            releases[index] = target_entry
            break
    if target_entry is None:
        target_entry = OrderedDict(
            [
                ("release", release_key),
                ("allowed_versions", []),
                ("why", "Platform stability depends on curated Helm releases."),
                ("next_check", DEFAULT_RELEASE_NEXT_CHECK),
            ]
        )
        releases.append(target_entry)
    allowed = target_entry.setdefault("allowed_versions", [])
    if not isinstance(allowed, list):
        allowed = list(allowed)
        target_entry["allowed_versions"] = allowed
    seen: set[str] = { _normalize_version(str(entry)) for entry in allowed if entry }
    for version in versions:
        normalized = _normalize_version(str(version))
        if not normalized or normalized in seen:
            continue
        allowed.append(str(version))
        seen.add(normalized)


def _apply_crd_update(data: OrderedDict[str, Any], payload: Mapping[str, Any]) -> None:
    family = payload.get("family")
    if not family:
        raise PromotionError("Promotion payload missing CRD family")
    crds = data.setdefault("required_crd_families", [])
    for entry in crds:
        if isinstance(entry, Mapping) and str(entry.get("family")) == family:
            return
    crds.append(
        OrderedDict(
            [
                ("family", family),
                ("why", "Workload delivery requires this CRD family."),
                ("next_check", DEFAULT_CRD_NEXT_CHECK),
            ]
        )
    )


def _apply_ignored_drift_update(data: OrderedDict[str, Any], payload: Mapping[str, Any]) -> None:
    category = payload.get("category")
    if not category:
        raise PromotionError("Promotion payload missing drift category")
    valid_categories = {item.value for item in BaselineDriftCategory}
    if str(category) not in valid_categories:
        raise PromotionError(f"Unknown drift category: {category}")
    ignored = data.setdefault("ignored_drift", [])
    if not isinstance(ignored, list):
        ignored = list(ignored)
        data["ignored_drift"] = ignored
    if category not in ignored:
        ignored.append(category)


def _resolve_baseline_path(config_path: Path) -> Path:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    baseline_raw = raw.get("baseline_policy_path") if isinstance(raw, Mapping) else None
    explicit = str(baseline_raw) if baseline_raw else None
    try:
        return resolve_baseline_policy_path(config_path.parent, explicit)
    except FileNotFoundError as exc:
        raise PromotionError(str(exc)) from exc


def _write_patch(
    target_path: Path,
    original_text: str,
    updated_text: str,
    output_dir: Path,
    proposal_id: str,
) -> Path:
    if original_text == updated_text:
        raise PromotionNotApplicable("No changes would result from this promotion")
    original_lines = original_text.splitlines()
    updated_lines = updated_text.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            original_lines,
            updated_lines,
            fromfile=str(target_path),
            tofile=str(target_path),
            lineterm="",
        )
    )
    if not diff_lines:
        raise PromotionNotApplicable("No differences found after promotion")
    patch_content = "\n".join(diff_lines) + "\n"
    output_dir.mkdir(parents=True, exist_ok=True)
    patch_file = output_dir / f"{proposal_id}.patch"
    patch_file.write_text(patch_content, encoding="utf-8")
    return patch_file


# Re-export for backward compatibility
__all__ = [
    "PromotionError",
    "PromotionNotApplicable",
    "UnsupportedProposalTarget",
    "render_proposal_patch",
]