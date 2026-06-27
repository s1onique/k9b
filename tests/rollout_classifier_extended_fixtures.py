#!/usr/bin/env python3
"""Shared JSON fixture builders for rollout classifier extended tests.

Provides lightweight helpers to construct Kubernetes API response JSON for testing.
"""

from __future__ import annotations

import json


def make_pods_json(pods: list[dict[str, object]]) -> str:
    """Build pods JSON from list of pod dicts."""
    return json.dumps({"items": pods})


def make_deployments_json(deployments: list[dict[str, object]]) -> str:
    """Build deployments JSON from list of deployment dicts."""
    return json.dumps({"items": deployments})


def make_pvc_json(pvcs: list[dict[str, object]]) -> str:
    """Build PVC JSON from list of PVC dicts."""
    return json.dumps({"items": pvcs})


def make_events_json(events: list[dict[str, object]]) -> str:
    """Build events JSON from list of event dicts."""
    return json.dumps({"items": events})
