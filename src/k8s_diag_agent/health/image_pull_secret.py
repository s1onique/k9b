"""Helpers for detecting broken image pull secret supply chains."""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence, Tuple

from ..collect.cluster_snapshot import WarningEventSummary

CommandRunner = Callable[[Sequence[str]], str]

_SECRET_MESSAGE_PATTERN = re.compile(r'image pull secret "(?P<secret>[^"]+)"', re.IGNORECASE)
_FAILED_REASON = "UpdateFailed"
_MISSING_SECRET_MESSAGE = "Secret does not exist"
BROKEN_IMAGE_PULL_SECRET_REASON = "broken_image_pull_secret_path"


def _run_command(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command `{command[0]}` not found.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"`{command[0]}` failed: {message}") from exc
    return result.stdout


def _kubectl(context: str, *args: str, runner: CommandRunner) -> str:
    return runner(("kubectl", *args, "--context", context))


def _extract_items(payload: Any) -> List[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
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
    secret_store_ref: Dict[str, str]
    status_reason: str | None
    status_message: str | None
    ready: bool | None

    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExternalSecretStatus":
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
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "exists": self.exists,
            "details": self.details,
        }

    @classmethod
    def missing(cls, namespace: str, name: str, message: str) -> "TargetSecretStatus":
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
    deployments: Tuple[Dict[str, str], ...]
    external_secrets: Tuple[ExternalSecretStatus, ...]
    secret_store_refs: Tuple[Dict[str, str], ...]
    target_secret_status: TargetSecretStatus
    events: Tuple[WarningEventSummary, ...]

    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls, raw: Mapping[str, Any]) -> "ImagePullSecretInsight":
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
    def __init__(self, command_runner: CommandRunner | None = None):
        self._runner = command_runner or _run_command

    def inspect(
        self,
        context: str,
        namespaces: Iterable[str],
        warning_events: Iterable[WarningEventSummary],
    ) -> ImagePullSecretInsight | None:
        namespace_filter = set(namespaces)
        candidates: List[Tuple[str, str, List[WarningEventSummary]]] = []
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
            deployments = self._deployments_using_secret(context, namespace, secret_name)
            if not deployments:
                continue
            external_secrets = self._external_secrets(context, namespace)
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
            target_status = self._target_secret_status(context, namespace, secret_name)
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
        self, context: str, namespace: str, secret_name: str
    ) -> List[Dict[str, str]]:
        try:
            output = _kubectl(context, "get", "deployments", "-n", namespace, "-o", "json", runner=self._runner)
        except RuntimeError:
            return []
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return []
        deployments: List[Dict[str, str]] = []
        for entry in _extract_items(payload):
            spec = entry.get("spec", {})
            template = spec.get("template", {}).get("spec", {})
            image_pull_secrets = template.get("imagePullSecrets") or []
            if any(
                isinstance(secret_entry, Mapping)
                and str(secret_entry.get("name")) == secret_name
                for secret_entry in image_pull_secrets
            ):
                metadata = entry.get("metadata") or {}
                name = str(metadata.get("name") or "")
                deployments.append({"namespace": namespace, "name": name})
        return deployments

    def _external_secrets(
        self, context: str, namespace: str
    ) -> Tuple[ExternalSecretStatus, ...]:
        try:
            output = _kubectl(
                context,
                "get",
                "externalsecrets.external-secrets.io",
                "-n",
                namespace,
                "-o",
                "json",
                runner=self._runner,
            )
        except RuntimeError:
            return ()
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return ()
        secrets: List[ExternalSecretStatus] = []
        for entry in _extract_items(payload):
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

    def _target_secret_status(
        self, context: str, namespace: str, secret_name: str
    ) -> TargetSecretStatus:
        try:
            output = _kubectl(
                context,
                "get",
                "secret",
                secret_name,
                "-n",
                namespace,
                "-o",
                "json",
                runner=self._runner,
            )
        except RuntimeError as exc:
            return TargetSecretStatus.missing(namespace, secret_name, str(exc))
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            return TargetSecretStatus.missing(namespace, secret_name, f"invalid secret payload: {exc}")
        metadata = payload.get("metadata") or {}
        secret_type = str(payload.get("type") or "")
        return TargetSecretStatus(
            namespace=str(metadata.get("namespace") or namespace),
            name=str(metadata.get("name") or secret_name),
            exists=True,
            details={
                "type": secret_type,
                "creationTimestamp": str(metadata.get("creationTimestamp") or ""),
                "uid": str(metadata.get("uid") or ""),
            },
        )

    def _unique_store_refs(
        self, secrets: Iterable[ExternalSecretStatus]
    ) -> Tuple[Dict[str, str], ...]:
        seen: List[Tuple[str, str, str]] = []
        refs: List[Dict[str, str]] = []
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
