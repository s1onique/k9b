"""Security helpers shared across logging and prompts."""

from __future__ import annotations

from .anonymizer import (
    MetadataAnonymizer,
    anonymize_metadata,
)
from .deanonymization import (
    ALIAS_PATTERN,
    assert_no_provider_aliases,
    deanonymize_command,
    deanonymize_next_check_candidate,
    deanonymize_payload,
    deanonymize_review_enrichment,
    deanonymize_text,
    flatten_alias_mappings,
)
from .kubectl_errors import (
    KUBECTL_OUTPUT_TOO_LARGE,
    KubectlExecutionError,
    KubectlOutputTooLargeError,
)
from .kubectl_invocation import (
    DEFAULT_TIMEOUT_SECONDS,
    KubectlInvocation,
)
from .kubectl_subprocess import (
    DEFAULT_CHUNK_SIZE,
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    build_bounded_kubectl_get,
    collect_events_bounded,
    collect_pods_bounded,
    run_kubectl,
    set_run_id_context,
)
from .kubernetes_client import (
    DEFAULT_ACTIVE_PODS_MAX,
    DEFAULT_EVICTED_PODS_REPORTED_MAX,
    DEFAULT_FAILED_PODS_REPORTED_MAX,
    DEFAULT_FAILED_PODS_SCANNED_MAX,
    DEFAULT_POD_PAGE_LIMIT,
    KubernetesApiNotFoundError,
    KubernetesApiPermissionError,
    KubernetesApiResponseTooLargeError,
    KubernetesApiTimeoutError,
    KubernetesClientError,
    KubernetesClientUnavailableError,
    KubernetesReadClient,
    PodSummary,
    create_kubernetes_read_client,
)
from .kubernetes_client_models import (
    CrdSummary,
    DeploymentProjection,
    EventProjection,
    NamespaceProjection,
    NodeSummary,
    PaginationMetadata,
    PodProjection,
    SecretProjection,
    ServiceAccountProjection,
    StatefulSetSummary,
)
from .path_validation import (
    SecurityError,
    safe_child_path,
    safe_glob_pattern,
    safe_run_artifact_glob,
    validate_run_id,
    validate_safe_path_id,
)
from .sanitizer import (
    sanitize_exception_message,
    sanitize_execution_output,
    sanitize_log_entry,
    sanitize_payload,
    sanitize_prompt,
)

__all__ = [
    "ALIAS_PATTERN",
    "SecurityError",
    "KubernetesReadClient",
    "KubernetesClientError",
    "KubernetesClientUnavailableError",
    "KubernetesApiPermissionError",
    "KubernetesApiNotFoundError",
    "KubernetesApiTimeoutError",
    "KubernetesApiResponseTooLargeError",
    "create_kubernetes_read_client",
    "assert_no_provider_aliases",
    "deanonymize_command",
    "deanonymize_next_check_candidate",
    "deanonymize_payload",
    "deanonymize_review_enrichment",
    "deanonymize_text",
    "flatten_alias_mappings",
    "MetadataAnonymizer",
    "anonymize_metadata",
    "safe_child_path",
    "safe_glob_pattern",
    "safe_run_artifact_glob",
    "sanitize_log_entry",
    "sanitize_payload",
    "sanitize_prompt",
    "validate_run_id",
    "validate_safe_path_id",
]
