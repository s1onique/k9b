"""Helpers for detecting broken image pull secret supply chains.

This module has been migrated to use the Kubernetes Python client for critical reads.
kubectl subprocess calls remain in the bounded fallback seam for debugging.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..collect.cluster_snapshot import WarningEventSummary
from ..security.kubernetes_client import (
    KubernetesReadClient,
    get_cached_kubernetes_client,
)

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)

_SECRET_MESSAGE_PATTERN = re.compile(r'image pull secret "(?P<secret>[^"]+)"', re.IGNORECASE)
_FAILED_REASON = "UpdateFailed"
_MISSING_SECRET_MESSAGE = "Secret does not exist"
BROKEN_IMAGE_PULL_SECRET_REASON = "broken_image_pull_secret_path"
KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS = 30

# Module-level client for reuse
_kubernetes_client: KubernetesReadClient | None = None


def _get_kubernetes_client() -> KubernetesReadClient:
    """Get or create the Kubernetes client (lazy initialization)."""
    global _kubernetes_client
    if _kubernetes_client is None:
        _kubernetes_client = get_cached_kubernetes_client()
    return _kubernetes_client


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        items = payload.get("items")
        if isinstance(items, list):
            return [dict(item) for item in items if isinstance(item, Mapping)]
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    return []


def _extract_secret_name(message: str) -> str | None:
    if not message:
        return None
    match = _SECRET_MESSAGE_PATTERN.search(message)
    if not match:
        return None
    return match.group("secret")


@dataclass(frozen=True)
class ExternalSecretStatus:
    namespace: str
    name: str
    target_secret: str
    secret_store_ref: dict[str, str]
    status_reason: str | None
    status_message: str | None
    ready: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "target_secret": self.target_secret,
            "secret_store_ref": self.secret_store_ref,
            "status_reason": self.status_reason,
            "status_message": self.status_message,
            "ready": self.ready,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ExternalSecretStatus:
        return cls(
            namespace=str(raw.get("namespace") or ""),
            name=str(raw.get("name") or ""),
            target_secret=str(raw.get("target_secret") or ""),
            secret_store_ref={
                str(key): str(value)
                for key, value in (raw.get("secret_store_ref") or {}).items()
                if key
            },
            status_reason=str(raw.get("status_reason")) if raw.get("status_reason") is not None else None,
            status_message=str(raw.get("status_message")) if raw.get("status_message") is not None else None,
            ready=bool(raw.get("ready")) if raw.get("ready") is not None else None,
        )


@dataclass(frozen=True)
class TargetSecretStatus:
    namespace: str
    name: str
    exists: bool
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "exists": self.exists,
            "details": self.details,
        }

    @classmethod
    def missing(cls, namespace: str, name: str, message: str) -> TargetSecretStatus:
        return cls(
            namespace=namespace,
            name=name,
            exists=False,
            details={"message": message},
        )


@dataclass(frozen=True)
class ImagePullSecretInsight:
    namespace: str
    secret_name: str
    deployments: tuple[dict[str, str], ...]
    external_secrets: tuple[ExternalSecretStatus, ...]
    secret_store_refs: tuple[dict[str, str], ...]
    target_secret_status: TargetSecretStatus
    events: tuple[WarningEventSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "secret_name": self.secret_name,
            "deployments": list(self.deployments),
            "external_secrets": [entry.to_dict() for entry in self.external_secrets],
            "secret_store_refs": list(self.secret_store_refs),
            "target_secret_status": self.target_secret_status.to_dict(),
            "events": [event.to_dict() for event in self.events],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ImagePullSecretInsight:
        if not isinstance(raw, Mapping):
            raise ValueError("image pull secret insight must be a mapping")
        external = raw.get("external_secrets") or []
        if not isinstance(external, list):
            raise ValueError("external_secrets must be a list")
        event_entries = raw.get("events") or []
        if not isinstance(event_entries, list):
            raise ValueError("events must be a list")
        target_status_raw = raw.get("target_secret_status") or {}
        details_raw = target_status_raw.get("details")
        detail_items = details_raw.items() if isinstance(details_raw, Mapping) else []
        details = {
            str(key): value
            for key, value in detail_items
            if isinstance(key, str)
        }
        return cls(
            namespace=str(raw.get("namespace") or ""),
            secret_name=str(raw.get("secret_name") or ""),
            deployments=tuple(
                {str(key): str(value) for key, value in entry.items() if isinstance(key, str)}
                for entry in (raw.get("deployments") or [])
                if isinstance(entry, Mapping)
            ),
            external_secrets=tuple(
                ExternalSecretStatus.from_dict(entry)
                for entry in external
                if isinstance(entry, Mapping)
            ),
            secret_store_refs=tuple(
                {
                    str(key): str(value)
                    for key, value in entry.items()
                    if isinstance(key, str)
                }
                for entry in (raw.get("secret_store_refs") or [])
                if isinstance(entry, Mapping)
            ),
            target_secret_status=TargetSecretStatus(
                namespace=str(target_status_raw.get("namespace") or ""),
                name=str(target_status_raw.get("name") or ""),
                exists=bool(target_status_raw.get("exists")),
                details=details,
            ),
            events=tuple(
                WarningEventSummary.from_dict(entry)
                for entry in event_entries
                if isinstance(entry, Mapping)
            ),
        )


class ImagePullSecretInspector:
    """Inspector for image pull secret issues.

    This class uses the Kubernetes Python client for critical reads.
    """

    def __init__(self, command_runner: Callable[[Sequence[str]], str] | None = None):
        self._runner = command_runner
        self._client: KubernetesReadClient | None = None

    def _get_client(self) -> KubernetesReadClient:
        """Get or create the Kubernetes client."""
        if self._client is None:
            self._client = _get_kubernetes_client()
        return self._client

    def inspect(
        self,
        context: str,
        namespaces: Iterable[str],
        warning_events: Iterable[WarningEventSummary],
    ) -> ImagePullSecretInsight | None:
        namespace_filter = set(namespaces)
        candidates: list[tuple[str, str, list[WarningEventSummary]]] = []
        for event in warning_events:
            if event.reason != "FailedToRetrieveImagePullSecret":
                continue
            namespace = event.namespace
            if namespace_filter and namespace not in namespace_filter:
                continue
            secret_name = _extract_secret_name(event.message)
            if not secret_name:
                continue
            candidates.append((namespace, secret_name, [event]))
        for namespace, secret_name, events in candidates:
            deployments = self._deployments_using_secret(namespace, secret_name)
            if not deployments:
                continue
            external_secrets = self._external_secrets(namespace)
            matches = tuple(
                secret
                for secret in external_secrets
                if secret.target_secret == secret_name
                and secret.status_reason == _FAILED_REASON
                and secret.status_message
                and _MISSING_SECRET_MESSAGE.lower() in secret.status_message.lower()
            )
            if not matches:
                continue
            target_status = self._target_secret_status(namespace, secret_name)
            if target_status.exists:
                continue
            store_refs = self._unique_store_refs(matches)
            return ImagePullSecretInsight(
                namespace=namespace,
                secret_name=secret_name,
                deployments=tuple(deployments),
                external_secrets=matches,
                secret_store_refs=store_refs,
                target_secret_status=target_status,
                events=tuple(events),
            )
        return None

    def _deployments_using_secret(
        self, namespace: str, secret_name: str
    ) -> list[dict[str, str]]:
        """Find deployments using a specific image pull secret.

        This checks spec.template.spec.imagePullSecrets[].name == secret_name
        directly on the deployment resource, matching the original kubectl behavior.

        Uses Kubernetes Python client with pagination.
        """
        try:
            client = self._get_client()
            deployments, _metadata = client.list_namespaced_deployments_projected(
                namespace=namespace,
                max_items=200,
            )
        except Exception:
            return []

        # Filter deployments that have the secret in their pod template
        deployments_using_secret: list[dict[str, str]] = []
        for deploy in deployments:
            if secret_name in deploy.image_pull_secrets:
                deployments_using_secret.append({
                    "namespace": namespace,
                    "name": deploy.name,
                })

        return deployments_using_secret

    def _external_secrets(
        self, namespace: str
    ) -> tuple[ExternalSecretStatus, ...]:
        """Get ExternalSecret resources in a namespace.

        Uses CustomObjectsApi for the ExternalSecret CRD from external-secrets.io.
        Falls back to kubectl if the CRD is not available.
        """
        # ExternalSecret CRD from external-secrets.io
        # group: external-secrets.io
        # version: typically v1 (check cluster for exact version)
        external_secret_items = self._list_external_secrets(namespace)

        secrets: list[ExternalSecretStatus] = []
        for entry in external_secret_items:
            metadata = entry.get("metadata") or {}
            spec = entry.get("spec") or {}
            status = entry.get("status") or {}
            target = spec.get("target") or {}
            secret_store = spec.get("secretStoreRef") or {}
            conditions = status.get("conditions") or []
            reason = None
            message = None
            ready = None
            if isinstance(conditions, list):
                for condition in reversed(conditions):
                    if not isinstance(condition, Mapping):
                        continue
                    reason = condition.get("reason")
                    message = condition.get("message")
                    status_value = condition.get("status")
                    if isinstance(status_value, str):
                        ready = status_value.lower() == "true"
                    break
            secrets.append(
                ExternalSecretStatus(
                    namespace=str(metadata.get("namespace") or namespace),
                    name=str(metadata.get("name") or ""),
                    target_secret=str(target.get("name") or ""),
                    secret_store_ref={
                        "name": str(secret_store.get("name") or ""),
                        "kind": str(secret_store.get("kind") or "SecretStore"),
                        "namespace": str(secret_store.get("namespace") or ""),
                    },
                    status_reason=str(reason) if reason is not None else None,
                    status_message=str(message) if message is not None else None,
                    ready=ready,
                )
            )
        return tuple(secrets)

    def _list_external_secrets(self, namespace: str) -> list[dict[str, Any]]:
        """List ExternalSecret resources using CustomObjectsApi.

        Tries multiple API versions for external-secrets.io CRD.
        Falls back to kubectl if CustomObjectsApi fails.
        Uses bounded pagination (max_items=200) to prevent unbounded memory growth.
        """
        # Try CustomObjectsApi first (preferred approach)
        try:
            client = self._get_client()
            # Try v1 first (common version)
            items, _metadata = client.list_namespaced_custom_objects(
                group="external-secrets.io",
                version="v1",
                plural="externalsecrets",
                namespace=namespace,
                max_items=200,
            )
            return items
        except Exception:
            pass

        # Try v1beta1 (older versions of external-secrets operator)
        try:
            client = self._get_client()
            items, _metadata = client.list_namespaced_custom_objects(
                group="external-secrets.io",
                version="v1beta1",
                plural="externalsecrets",
                namespace=namespace,
                max_items=200,
            )
            return items
        except Exception:
            pass

        # Fall back to kubectl if CustomObjectsApi fails (e.g., CRD not installed)
        if self._runner:
            try:
                import json
                output = self._runner([
                    "kubectl", "get", "externalsecrets.external-secrets.io",
                    "-n", namespace, "-o", "json"
                ])
                payload = json.loads(output)
                return _extract_items(payload)
            except Exception:
                return []
        return []

    def _target_secret_status(
        self, namespace: str, secret_name: str
    ) -> TargetSecretStatus:
        """Check if a target secret exists.

        Uses Kubernetes Python client.
        """
        try:
            client = self._get_client()
            secret = client.read_namespaced_secret_projected(
                namespace=namespace,
                name=secret_name,
            )
            if secret:
                return TargetSecretStatus(
                    namespace=namespace,
                    name=secret_name,
                    exists=True,
                    details={
                        "type": secret.secret_type,
                        "uid": secret.uid,
                    },
                )
            return TargetSecretStatus.missing(namespace, secret_name, "Secret not found")
        except Exception as exc:
            return TargetSecretStatus.missing(namespace, secret_name, str(exc))

    def _unique_store_refs(
        self, secrets: Iterable[ExternalSecretStatus]
    ) -> tuple[dict[str, str], ...]:
        seen: list[tuple[str, str, str]] = []
        refs: list[dict[str, str]] = []
        for entry in secrets:
            ref = entry.secret_store_ref
            key = (
                str(ref.get("name") or ""),
                str(ref.get("kind") or ""),
                str(ref.get("namespace") or ""),
            )
            if key in seen:
                continue
            seen.append(key)
            refs.append({
                "name": ref.get("name", ""),
                "kind": ref.get("kind", "SecretStore"),
                "namespace": ref.get("namespace", ""),
            })
        return tuple(refs)
