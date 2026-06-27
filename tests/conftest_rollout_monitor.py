# Shared fixtures for rollout monitor regression tests.
"""Shared test fixtures for k9b CNPG live-lab rollout monitor regression tests."""

from __future__ import annotations

# =============================================================================
# Rendered manifest fixture with k9b-backend, k9b-scheduler
# =============================================================================

RENDERED_MANIFEST_FIXTURE = """
apiVersion: v1
kind: Namespace
metadata:
  name: k9b-live-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: k9b-config
  namespace: k9b-live-lab
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
  namespace: k9b-live-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: k9b-backend
  template:
    metadata:
      labels:
        app: k9b-backend
    spec:
      containers:
      - name: backend
        image: k9b-backend:latest
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
  namespace: k9b-live-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: k9b-scheduler
  template:
    metadata:
      labels:
        app: k9b-scheduler
    spec:
      containers:
      - name: scheduler
        image: k9b-scheduler:latest
"""
