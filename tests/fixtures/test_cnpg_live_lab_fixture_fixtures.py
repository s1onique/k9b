"""Test fixtures for fixture renderer tests."""

from __future__ import annotations

# Test fixture: Pod with hardcoded namespace
FIXTURE_WITH_HARDCODED_NAMESPACE = """# Pod with hardcoded namespace
apiVersion: v1
kind: Pod
metadata:
  name: failing-app
  namespace: cnpg-lab
  labels:
    app: test-app
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: alpine:3.19
      command: ["sleep", "infinity"]
"""

# Test fixture: Pod with correct namespace
FIXTURE_WITH_CORRECT_NAMESPACE = """# Pod with namespace matching LAB_NAMESPACE
apiVersion: v1
kind: Pod
metadata:
  name: failing-app
  namespace: k9b-cnpg-lab-12345678
  labels:
    app: test-app
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: alpine:3.19
      command: ["sleep", "infinity"]
"""

# Test fixture: Pod without namespace
FIXTURE_NO_NAMESPACE = """# Pod without explicit namespace
apiVersion: v1
kind: Pod
metadata:
  name: failing-app
  labels:
    app: test-app
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: alpine:3.19
      command: ["sleep", "infinity"]
"""

# Test fixture: Cluster-scoped Node resource
FIXTURE_CLUSTER_SCOPED = """# Node (cluster-scoped, should be rejected)
apiVersion: v1
kind: Node
metadata:
  name: k3s-node-1
  labels:
    node-role.kubernetes.io/master: "true"
"""

# Test fixture: Mixed resources
FIXTURE_MIXED_RESOURCES = """# Multiple documents: namespaced and cluster-scoped
---
apiVersion: v1
kind: Namespace
metadata:
  name: k9b-cnpg-lab-12345678
---
apiVersion: v1
kind: Pod
metadata:
  name: failing-app
  namespace: wrong-namespace
  labels:
    app: test-app
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: alpine:3.19
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-config
  namespace: wrong-namespace
data:
  key: value
"""

# Test fixture: Namespace object with wrong name
FIXTURE_NAMESPACE_OBJECT_WRONG = """# Namespace object with wrong name
apiVersion: v1
kind: Namespace
metadata:
  name: cnpg-lab
"""
