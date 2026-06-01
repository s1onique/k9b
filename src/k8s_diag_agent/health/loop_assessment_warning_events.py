"""Warning-event pattern matching helpers for health assessment building."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ..collect.cluster_snapshot import WarningEventSummary
from ..models import ConfidenceLevel, Finding, Hypothesis, Layer, NextCheck, Signal

__all__ = [
    "match_warning_event_patterns",
]


def match_warning_event_patterns(
    *,
    warning_events: Sequence[WarningEventSummary],
    signals: list[Signal],
    signal_id_generator: Callable[[], str],
    matched_event_ids: set[int],
    findings: list[Finding],
    pattern_reasons: list[str],
    pattern_metadata: dict[str, tuple[str, ...]],
    pattern_refs: list[str],
    pattern_next_checks: list[NextCheck],
    pattern_hypotheses: list[Hypothesis],
) -> bool:
    """Match warning events against known patterns and record signals.

    This function extracts warning-event pattern matching logic from build_health_assessment().
    It processes warning events to detect probe failures, scheduling issues, missing metrics,
    PVC provisioning failures, and ingress timeouts.

    Returns True if any pattern was matched, False otherwise.
    """
    matched_any = False

    def _unused_warning_events() -> list[WarningEventSummary]:
        return [event for event in warning_events if id(event) not in matched_event_ids]

    def _capture_namespaces(events: Sequence[WarningEventSummary]) -> tuple[str, ...]:
        seen: list[str] = []
        for event in events:
            namespace = (event.namespace or "").strip()
            if namespace and namespace not in seen:
                seen.append(namespace)
        return tuple(seen)

    def _record_pattern(
        reason_tag: str,
        signal_desc: str,
        severity: str,
        layer: Layer,
        hypothesis_desc: str,
        hypothesis_confidence: ConfidenceLevel,
        probable_layer: Layer,
        falsify: str,
        next_check_desc: str,
        evidence_needed: Sequence[str],
        namespaces: Sequence[str],
        reference_label: str,
    ) -> None:
        nonlocal matched_any
        matched_any = True
        signal = _add_signal(signal_desc, severity, layer)
        _record_finding(signal_desc, layer, [signal.id])
        pattern_reasons.append(reason_tag)
        namespace_tuple = tuple(dict.fromkeys(item for item in namespaces if item))
        pattern_metadata[reason_tag] = namespace_tuple
        pattern_refs.append(reference_label)
        pattern_next_checks.append(
            NextCheck(
                description=next_check_desc,
                owner="platform engineer",
                method="kubectl",
                evidence_needed=list(evidence_needed),
            )
        )
        pattern_hypotheses.append(
            Hypothesis(
                id=signal_id_generator(),
                description=hypothesis_desc,
                confidence=hypothesis_confidence,
                probable_layer=probable_layer,
                what_would_falsify=falsify,
            )
        )

    def _mark_events(events: Sequence[WarningEventSummary]) -> None:
        for event in events:
            matched_event_ids.add(id(event))

    def _describe_namespace(namespace_list: Sequence[str], fallback: str) -> str:
        for namespace in namespace_list:
            if namespace:
                return namespace
        return fallback

    def _add_signal(description: str, severity: str, layer: Layer) -> Signal:
        signal = Signal(
            id=signal_id_generator(),
            description=description,
            layer=layer,
            evidence_id="",
            severity=severity,
        )
        signals.append(signal)
        return signal

    def _record_finding(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
        if not signal_ids:
            return
        findings.append(
            Finding(
                id=signal_id_generator(),
                description=description,
                supporting_signals=list(signal_ids),
                layer=layer,
            )
        )

    def _match_probe_events() -> None:
        candidates = [
            event for event in _unused_warning_events()
            if "readiness probe" in (event.message or "").lower()
            or "liveness probe" in (event.message or "").lower()
        ]
        if not candidates:
            return
        _mark_events(candidates)
        namespace = _describe_namespace(_capture_namespaces(candidates), "default")
        signal_desc = f"Readiness/liveness probe failures recorded in {namespace}."
        _record_pattern(
            reason_tag="probe_failure",
            signal_desc=signal_desc,
            severity="medium",
            layer=Layer.WORKLOAD,
            hypothesis_desc=(
                "A recent rollout or configuration change is likely hitting the probe endpoint "
                "before readiness/liveness succeeds; pods stay unready."
            ),
            hypothesis_confidence=ConfidenceLevel.MEDIUM,
            probable_layer=Layer.WORKLOAD,
            falsify="Pods start reporting Ready and probe failures stop appearing.",
            next_check_desc=f"Inspect pods in {namespace} that are failing probes and review the rollout history.",
            evidence_needed=[
                f"kubectl describe pods -n {namespace}",
                f"kubectl logs -n {namespace} <pod> --previous",
                f"kubectl rollout status deployment -n {namespace}",
            ],
            namespaces=[namespace],
            reference_label="probe failure pattern",
        )

    def _match_scheduling_events() -> None:
        def _scheduling_cause(event: WarningEventSummary) -> str | None:
            msg = (event.message or "").lower()
            if "untolerated taint" in msg:
                return "node taints"
            if "affinity" in msg:
                return "node affinity"
            if "insufficient" in msg:
                return "resource shortage"
            return None

        matches: list[tuple[WarningEventSummary, str]] = []
        for event in _unused_warning_events():
            if event.reason != "FailedScheduling":
                continue
            cause = _scheduling_cause(event)
            if not cause:
                continue
            matches.append((event, cause))
        if not matches:
            return
        events, causes = zip(*matches)
        _mark_events(list(events))
        namespace = _describe_namespace(_capture_namespaces(list(events)), "default")
        cause_label = causes[0]
        signal_desc = f"Pods remain Pending in {namespace} because scheduling is blocked by {cause_label}."
        _record_pattern(
            reason_tag="failed_scheduling",
            signal_desc=signal_desc,
            severity="medium",
            layer=Layer.WORKLOAD,
            hypothesis_desc=(
                f"Scheduling is prevented by {cause_label}, so pods cannot land on nodes; "
                "node taints, affinity, or capacity must be rechecked."
            ),
            hypothesis_confidence=ConfidenceLevel.MEDIUM,
            probable_layer=Layer.NODE,
            falsify="Pods eventually schedule once nodes match the requested taints/affinity and available resources.",
            next_check_desc=f"Describe Pending pods and node taints/affinity in {namespace} to confirm the scheduling block.",
            evidence_needed=[
                f"kubectl describe pods -n {namespace} --field-selector=status.phase=Pending",
                "kubectl describe nodes",
            ],
            namespaces=[namespace],
            reference_label="scheduling block pattern",
        )

    def _match_metrics_events() -> None:
        matches = [
            event for event in _unused_warning_events()
            if event.reason == "FailedGetResourceMetric"
            or "metrics-server" in (event.message or "").lower()
        ]
        if not matches:
            return
        _mark_events(matches)
        namespace = _describe_namespace(_capture_namespaces(matches), "default")
        signal_desc = f"HPA resource metrics are unavailable in {namespace}; metrics-server may be offline."
        _record_pattern(
            reason_tag="missing_metrics",
            signal_desc=signal_desc,
            severity="medium",
            layer=Layer.OBSERVABILITY,
            hypothesis_desc=(
                "The metrics-server endpoint or HPA resource metric API is unreachable, "
                "so scaling decisions cannot proceed."
            ),
            hypothesis_confidence=ConfidenceLevel.MEDIUM,
            probable_layer=Layer.OBSERVABILITY,
            falsify="Metrics-server becomes healthy and resource metrics are present for the HPA.",
            next_check_desc=f"Collect HPA and metrics-server status in {namespace} to see what is missing.",
            evidence_needed=[
                f"kubectl describe hpa -n {namespace}",
                "kubectl get deployment metrics-server -n kube-system",
            ],
            namespaces=[namespace],
            reference_label="metrics-server pattern",
        )

    def _match_pvc_events() -> None:
        matches = [
            event for event in _unused_warning_events()
            if event.reason in {"ProvisioningFailed", "VolumeBindingFailed"}
            or "persistentvolumeclaim" in (event.message or "").lower()
        ]
        if not matches:
            return
        _mark_events(matches)
        namespace = _describe_namespace(_capture_namespaces(matches), "default")
        signal_desc = f"PersistentVolumeClaims in {namespace} remain Pending because provisioning failed."
        _record_pattern(
            reason_tag="pvc_pending",
            signal_desc=signal_desc,
            severity="medium",
            layer=Layer.STORAGE,
            hypothesis_desc=(
                "The storage class or provisioner cannot satisfy the PVC request, "
                "leaving volumes unbound."
            ),
            hypothesis_confidence=ConfidenceLevel.MEDIUM,
            probable_layer=Layer.STORAGE,
            falsify="PVCs bind and PVs attach without provisioning errors.",
            next_check_desc=f"Describe PVCs and related storageclasses in {namespace} to examine the provisioning failure.",
            evidence_needed=[
                f"kubectl describe pvc -n {namespace}",
                "kubectl get storageclass",
            ],
            namespaces=[namespace],
            reference_label="PVC provisioning pattern",
        )

    def _match_ingress_events() -> None:
        matches = [
            event for event in _unused_warning_events()
            if event.reason in {"Unhealthy", "Failed", "BackendTimeout"}
        ]
        matches = [
            event for event in matches
            if any(
                keyword in (event.message or "").lower()
                for keyword in ("backend", "endpoint", "timeout", "connection refused", "503")
            )
        ]
        matches = [
            event for event in matches
            if "probe" not in (event.message or "").lower()
        ]
        if not matches:
            return
        _mark_events(matches)
        namespace = _describe_namespace(_capture_namespaces(matches), "default")
        signal_desc = f"Ingress/backend timeouts detected in {namespace}."
        _record_pattern(
            reason_tag="ingress_timeout",
            signal_desc=signal_desc,
            severity="medium",
            layer=Layer.NETWORK,
            hypothesis_desc=(
                "Ingress or service endpoints are missing/unhealthy, "
                "leading to backend timeouts at the gateway."
            ),
            hypothesis_confidence=ConfidenceLevel.MEDIUM,
            probable_layer=Layer.NETWORK,
            falsify="Endpoints report Ready and timeouts disappear when traffic reaches backends.",
            next_check_desc=f"Inspect ingress endpoints and services in {namespace} to verify backend availability.",
            evidence_needed=[
                f"kubectl get ingress -n {namespace}",
                f"kubectl get endpoints -n {namespace}",
                f"kubectl describe svc -n {namespace}",
            ],
            namespaces=[namespace],
            reference_label="ingress timeout pattern",
        )

    _match_probe_events()
    _match_scheduling_events()
    _match_metrics_events()
    _match_pvc_events()
    _match_ingress_events()

    return matched_any
