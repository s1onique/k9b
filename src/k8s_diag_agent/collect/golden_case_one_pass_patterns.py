"""Safety patterns for golden-case diagnosis enforcement.

This module defines forbidden patterns that should not appear in golden-case outputs:
- Forbidden conclusions (image pull, PVC, scheduling, etc.)
- Mutation patterns (kubectl apply, helm install, etc.)
"""

from __future__ import annotations

# Forbidden conclusion patterns - these should not appear as root cause
_FORBIDDEN_CONCLUSION_PATTERNS = [
    ("ImagePullBackOff", "image_pull_failure"),
    ("ErrImagePull", "image_pull_failure"),
    ("PVC", "pvc_storage_failure"),
    ("PersistentVolumeClaim", "pvc_storage_failure"),
    ("FailedScheduling", "node_scheduling_failure"),
    ("registry.*auth", "registry_auth_failure"),
    ("cnpg.*operator.*fail", "cnpg_operator_failure"),
]

# Mutation patterns - these actions should not be proposed
_MUTATION_PATTERNS = [
    r"kubectl\s+apply",
    r"kubectl\s+delete",
    r"kubectl\s+scale",
    r"helm\s+upgrade",
    r"helm\s+install",
    r"helm\s+uninstall",
    r"kubectl\s+edit",
    r"kubectl\s+replace",
    r"kubectl\s+patch",
    r"kubectl\s+rollout",
    r"kubectl\s+set",
]
