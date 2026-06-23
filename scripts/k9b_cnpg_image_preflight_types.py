"""Image preflight data types for CNPG Live Lab."""

from dataclasses import dataclass, field


@dataclass
class RegistryResult:
    """Registry manifest preflight result."""
    component: str
    image_ref: str
    registry_host: str
    repository_path: str
    tag: str
    success: bool
    failure_class: str = ""
    status_code: int | None = None
    error_message: str = ""
    command_used: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "image_ref": self.image_ref,
            "registry_host": self.registry_host,
            "repository_path": self.repository_path,
            "tag": self.tag,
            "success": self.success,
            "failure_class": self.failure_class,
            "status_code": self.status_code,
            "error_message": self.error_message,
            "command_used": self.command_used,
            "timestamp": self.timestamp,
        }


@dataclass
class NodePullResult:
    """Node-side pullability preflight result."""
    component: str
    image_ref: str
    pod_name: str
    success: bool
    failure_class: str = ""
    pod_phase: str = ""
    container_waiting_reason: str = ""
    container_waiting_message: str = ""
    events_summary: str = ""
    describe_output: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "component": self.component,
            "image_ref": self.image_ref,
            "pod_name": self.pod_name,
            "success": self.success,
            "failure_class": self.failure_class,
            "pod_phase": self.pod_phase,
            "container_waiting_reason": self.container_waiting_reason,
            "container_waiting_message": self.container_waiting_message,
            "events_summary": self.events_summary[:500] if self.events_summary else "",
            "describe_output": self.describe_output[:2000] if self.describe_output else "",
            "timestamp": self.timestamp,
        }


@dataclass
class ImagePullSecretStatus:
    """ImagePullSecrets verification result."""
    namespace: str
    secrets_exist: bool
    secret_names: list[str] = field(default_factory=list)
    has_service_account_ref: bool = False
    service_account_name: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        return {
            "namespace": self.namespace,
            "secrets_exist": self.secrets_exist,
            "secret_names": self.secret_names,
            "has_service_account_ref": self.has_service_account_ref,
            "service_account_name": self.service_account_name,
            "error_message": self.error_message,
        }


# Failure class constants
FAIL_IMAGE_UNRESOLVED = "image_ref_unresolved"
FAIL_IMAGE_MISSING = "image_manifest_missing"
FAIL_IMAGE_UNAUTHORIZED = "image_registry_unauthorized"
FAIL_IMAGE_FORBIDDEN = "image_registry_forbidden"
FAIL_IMAGE_TLS = "image_registry_tls_error"
FAIL_IMAGE_NETWORK = "image_registry_network_error"
FAIL_IMAGE_UNKNOWN = "image_registry_unknown_error"
FAIL_IMAGE_CREDS_MISSING = "image_registry_credentials_missing"
FAIL_IMAGE_AUTH_UNVERIFIED = "runner_registry_auth_unverified"
FAIL_NODE_PULL_BACKOFF = "node_image_pull_backoff"
FAIL_NODE_UNAUTHORIZED = "node_registry_unauthorized"
FAIL_NODE_TLS = "node_registry_tls_error"
FAIL_NODE_NETWORK = "node_registry_network_error"
FAIL_NODE_IMAGE_MISSING = "node_image_manifest_missing"
FAIL_NODE_UNKNOWN = "node_image_pull_unknown"
