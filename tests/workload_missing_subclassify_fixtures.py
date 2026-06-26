#!/usr/bin/env python3
"""Shared fixtures and test data for workload_missing_subclassify tests.

This module provides reusable YAML content and test data constants
for testing the workload missing sub-classification logic.
"""

from __future__ import annotations

# Multi-document YAML with Deployment/k9b
YAML_WITH_DEPLOYMENT_K9B = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
  namespace: test-ns
spec:
  replicas: 1
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: config
"""

# Multi-document YAML with other deployment only
YAML_WITH_OTHER_DEPLOYMENT = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: other-deployment
  namespace: test-ns
---
apiVersion: v1
kind: Service
metadata:
  name: service
"""

# YAML with comments only
YAML_COMMENTS_ONLY = """# This is a comment
# Another comment
---
# Another comment block
"""

# YAML with non-dict documents and deployment
YAML_NON_DICT_WITH_DEPLOYMENT = """---
- item1
- item2
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
"""

# Malformed YAML
YAML_MALFORMED = """apiVersion: apps/v1
kind: Deployment
  metadata:
    name: k9b
  invalid indent
"""

# Deployment in wrong namespace
YAML_WRONG_NAMESPACE = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
  namespace: wrong-namespace
"""

# Deployment with wrong name
YAML_WRONG_NAME = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: other-deployment
"""

# Multiple workload kinds
YAML_MULTI_WORKLOAD = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deployment-1
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: statefulset-1
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: daemonset-1
---
apiVersion: batch/v1
kind: Job
metadata:
  name: job-1
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cronjob-1
"""

# Rendered manifest with YAML but no k9b deployment
RENDERED_NO_K9B = """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: config
"""

# Rendered manifest with k9b deployment
RENDERED_WITH_K9B = """---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b
"""

# Rendered manifest with ConfigMap (not Deployment/k9b)
RENDERED_CONFIGMAP_ONLY = """---
apiVersion: v1
kind: ConfigMap
metadata:
  name: some-config
"""

# Malformed YAML for evidence collection failure test
RENDERED_MALFORMED = """
apiVersion: apps/v1
kind: Deployment
  metadata:
    name: k9b
  invalid: indent
"""

# Chart values with k9b.enabled=false
VALUES_K9B_DISABLED = {"k9b": {"enabled": False}}

# Chart values with backend.enabled=false
VALUES_BACKEND_DISABLED = {"backend": {"enabled": False}}

# Chart values with backend.replicas=0
VALUES_REPLICAS_ZERO = {"backend": {"replicas": 0}}

# Chart values with backend.replicas=1 (not suppressed)
VALUES_REPLICAS_ONE = {"backend": {"replicas": 1}}

# RBAC/admission error strings
RBAC_ERROR_FORBIDDEN = "Error: admission webhook denied: forbbiden"
RBAC_ERROR_DENIED = "Error: admission webhook denied: some resource"
RBAC_SUCCESS = "Release deployed successfully"

# Helm status JSON fixtures
HELM_STATUS_DEPLOYED = {
    "name": "k9b",
    "info": {"status": {"status": "deployed"}}
}

HELM_HISTORY_FAILED = [
    {"revision": 1, "status": "failed", "description": "Install failed"}
]

# Deployment JSON fixtures
DEPLOYMENTS_WITH_K9B = {"items": [{"metadata": {"name": "k9b"}}]}
DEPLOYMENTS_EMPTY = {"items": []}

# Inventory fixture for artifact directory test
WORKLOAD_INVENTORY_FIXTURE = {
    "expected": {"kind": "Deployment", "name": "k9b"},
    "rendered": {"deployment_k9b_present": True, "all_workloads": []},
    "parse_errors": [],
}
