"""Baseline policy definitions for the health loop."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .utils import normalize_ref


class BaselineDriftCategory(str, Enum):
    CONTROL_PLANE_VERSION = "control_plane_version"
    WATCHED_HELM_RELEASE = "watched_helm_release"
    WATCHED_CRD = "watched_crd"


DEFAULT_CONTROL_PLANE_REASON = (
    "Control plane lifecycle must match the supported Kubernetes release cadence."
)
DEFAULT_CONTROL_PLANE_NEXT_CHECK = "Review kube-apiserver and kubelet versions to confirm platform policy compliance."
DEFAULT_RELEASE_NEXT_CHECK = "Validate the Helm release version against the curated platform channel."
DEFAULT_CRD_NEXT_CHECK = "Confirm the CRD family exists and is being served across the cluster."


def _parse_version_tuple(value: str) -> Tuple[int, ...]:
    digits = [int(segment) for segment in re.findall(r"\d+", value)]
    while len(digits) < 3:
        digits.append(0)
    return tuple(digits)


def _normalize_chart_version(value: str) -> str:
    if not value:
        return ""
    normalized = value.lstrip("vV").strip()
    return normalized


@dataclass(frozen=True)
class ControlPlaneExpectation:
    min_version: Optional[str]
    max_version: Optional[str]
    why: str
    next_check: str

    def allows(self, candidate: Optional[str]) -> bool:
        if not candidate:
            return False
        candidate_tuple = _parse_version_tuple(candidate)
        if self.min_version:
            min_tuple = _parse_version_tuple(self.min_version)
            if candidate_tuple < min_tuple:
                return False
        if self.max_version:
            max_tuple = _parse_version_tuple(self.max_version)
            if candidate_tuple > max_tuple:
                return False
        return True

    def describe(self) -> str:
        if self.min_version and self.max_version:
            return f"{self.min_version} – {self.max_version}"
        if self.min_version:
            return f"≥ {self.min_version}"
        if self.max_version:
            return f"≤ {self.max_version}"
        return "any version"


@dataclass(frozen=True)
class ReleasePolicy:
    release_key: str
    allowed_versions: Tuple[str, ...]
    why: str
    next_check: str

    def allows(self, candidate: Optional[str]) -> bool:
        if not candidate:
            return False
        candidate_norm = _normalize_chart_version(candidate)
        return any(_normalize_chart_version(version) == candidate_norm for version in self.allowed_versions)

    def describe(self) -> str:
        if not self.allowed_versions:
            return "any version"
        return ", ".join(self.allowed_versions)


@dataclass(frozen=True)
class CRDPolicy:
    family: str
    why: str
    next_check: str


@dataclass(frozen=True)
class BaselinePolicy:
    control_plane_expectation: Optional[ControlPlaneExpectation]
    release_policies: Dict[str, ReleasePolicy]
    required_crds: Dict[str, CRDPolicy]
    ignored_drift_categories: Set[BaselineDriftCategory]
    peer_roles: Dict[str, str]

    @staticmethod
    def _parse_control_plane(raw: Mapping[str, Any]) -> Optional[ControlPlaneExpectation]:
        if not raw:
            return None
        min_version = _str_or_none(raw.get("min_version"))
        max_version = _str_or_none(raw.get("max_version"))
        why = _str_or_none(raw.get("why")) or DEFAULT_CONTROL_PLANE_REASON
        next_check = _str_or_none(raw.get("next_check")) or DEFAULT_CONTROL_PLANE_NEXT_CHECK
        return ControlPlaneExpectation(
            min_version=min_version,
            max_version=max_version,
            why=why,
            next_check=next_check,
        )

    @staticmethod
    def _parse_release(raw: Mapping[str, Any]) -> Optional[ReleasePolicy]:
        if not raw:
            return None
        release_key = _str_or_none(raw.get("release"))
        if not release_key:
            return None
        allowed_versions = tuple(
            normalized
            for entry in raw.get("allowed_versions") or []
            if (normalized := _str_or_none(entry))
        )
        why = _str_or_none(raw.get("why")) or "Platform stability depends on curated Helm releases."
        next_check = _str_or_none(raw.get("next_check")) or DEFAULT_RELEASE_NEXT_CHECK
        return ReleasePolicy(
            release_key=release_key,
            allowed_versions=allowed_versions,
            why=why,
            next_check=next_check,
        )

    @staticmethod
    def _parse_crd(raw: Mapping[str, Any]) -> Optional[CRDPolicy]:
        if not raw:
            return None
        family = _str_or_none(raw.get("family"))
        if not family:
            return None
        why = _str_or_none(raw.get("why")) or "Workload delivery requires this CRD family."
        next_check = _str_or_none(raw.get("next_check")) or DEFAULT_CRD_NEXT_CHECK
        return CRDPolicy(family=family, why=why, next_check=next_check)

    @staticmethod
    def _parse_ignored(values: Sequence[str]) -> Set[BaselineDriftCategory]:
        cats: Set[BaselineDriftCategory] = set()
        for value in values:
            normalized = _str_or_none(value)
            if not normalized:
                continue
            for category in BaselineDriftCategory:
                if category.value == normalized:
                    cats.add(category)
                    break
        return cats

    @staticmethod
    def _normalize_peer_roles(raw: Mapping[str, str]) -> Dict[str, str]:
        roles: Dict[str, str] = {}
        for ref, role in raw.items():
            if not ref:
                continue
            if not role:
                continue
            roles[normalize_ref(ref)] = role.strip()
        return roles

    @classmethod
    def load_from_file(cls, path: Path) -> BaselinePolicy:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cp_raw = raw.get("control_plane_version_range") or {}
        control_plane = cls._parse_control_plane(cp_raw)
        releases_raw = raw.get("watched_releases") or []
        release_policies: Dict[str, ReleasePolicy] = {}
        for entry in releases_raw:
            if not isinstance(entry, dict):
                continue
            release_entry = cls._parse_release(entry)
            if release_entry:
                release_policies[release_entry.release_key] = release_entry
        crds_raw = raw.get("required_crd_families") or []
        crd_policies: Dict[str, CRDPolicy] = {}
        for entry in crds_raw:
            if not isinstance(entry, dict):
                continue
            crd_entry = cls._parse_crd(entry)
            if crd_entry:
                crd_policies[crd_entry.family] = crd_entry
        ignored = cls._parse_ignored(raw.get("ignored_drift") or [])
        peer_roles = cls._normalize_peer_roles(raw.get("peer_roles") or {})
        return cls(
            control_plane_expectation=control_plane,
            release_policies=release_policies,
            required_crds=crd_policies,
            ignored_drift_categories=ignored,
            peer_roles=peer_roles,
        )

    @classmethod
    def empty(cls) -> BaselinePolicy:
        return cls(
            control_plane_expectation=None,
            release_policies={},
            required_crds={},
            ignored_drift_categories=set(),
            peer_roles={},
        )

    def is_drift_allowed(self, category: BaselineDriftCategory) -> bool:
        return category in self.ignored_drift_categories

    def release_policy(self, release_key: str) -> Optional[ReleasePolicy]:
        return self.release_policies.get(release_key)

    def crd_policy(self, family: str) -> Optional[CRDPolicy]:
        return self.required_crds.get(family)

    def role_for(self, reference: str) -> Optional[str]:
        return self.peer_roles.get(normalize_ref(reference))


def _str_or_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None
