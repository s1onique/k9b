"""Curl retry logic for provider preflight in k9b live labs.

This module provides the curl retry helpers with bounded exponential backoff.
It is split from provider_preflight.py to keep file sizes under LLM-friendly limits.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from scripts.lab_common.constants import (
    PREFLIGHT_RETRY_DEADLINE_SECONDS,
    PREFLIGHT_RETRY_INITIAL_SLEEP_SECONDS,
    PREFLIGHT_RETRY_MAX_SLEEP_SECONDS,
)
from scripts.lab_common.provider_curl_helpers import (
    CurlResult,
    _curl_exec_pod,
    _curl_service_pod,
    _is_retryable,
)

if TYPE_CHECKING:
    pass


def _curl_service_pod_with_retry(
    kubeconfig: str,
    namespace: str,
    target_url: str,
    timeout_seconds: int = 30,
) -> CurlResult:
    """Run _curl_service_pod with bounded retry and exponential backoff."""
    deadline = time.time() + PREFLIGHT_RETRY_DEADLINE_SECONDS
    attempt = 0
    sleep_s: float = float(PREFLIGHT_RETRY_INITIAL_SLEEP_SECONDS)
    last_result: CurlResult | None = None

    while time.time() < deadline:
        attempt += 1

        curl_result = _curl_service_pod(
            kubeconfig=kubeconfig,
            namespace=namespace,
            target_url=target_url,
            timeout_seconds=timeout_seconds,
        )
        last_result = curl_result

        if curl_result.success and curl_result.http_code == 200:
            try:
                json.loads(curl_result.body)
                return curl_result
            except json.JSONDecodeError:
                pass

        if not _is_retryable(curl_result):
            return curl_result

        remaining = deadline - time.time()
        if remaining <= 0:
            break

        sleep_for = min(sleep_s, remaining)
        if sleep_for > 0:
            time.sleep(sleep_for)

        if sleep_s < PREFLIGHT_RETRY_MAX_SLEEP_SECONDS:
            sleep_s = min(sleep_s * 2, PREFLIGHT_RETRY_MAX_SLEEP_SECONDS)

    return last_result or CurlResult(
        success=False,
        body=f"Retry deadline exceeded after {attempt} attempts",
        http_code=0,
        curl_rc=None,
        stderr="Retry deadline exceeded",
    )


def _curl_exec_pod_with_retry(
    kubeconfig: str,
    namespace: str,
    deployment: str,
    container: str,
    target_url: str,
    timeout_seconds: int = 30,
) -> CurlResult:
    """Run _curl_exec_pod with bounded retry and exponential backoff."""
    deadline = time.time() + PREFLIGHT_RETRY_DEADLINE_SECONDS
    attempt = 0
    sleep_s: float = float(PREFLIGHT_RETRY_INITIAL_SLEEP_SECONDS)
    last_result: CurlResult | None = None

    while time.time() < deadline:
        attempt += 1

        curl_result = _curl_exec_pod(
            kubeconfig=kubeconfig,
            namespace=namespace,
            deployment=deployment,
            container=container,
            target_url=target_url,
            timeout_seconds=timeout_seconds,
        )
        last_result = curl_result

        if curl_result.success and curl_result.http_code == 200:
            try:
                json.loads(curl_result.body)
                return curl_result
            except json.JSONDecodeError:
                pass

        if not _is_retryable(curl_result):
            return curl_result

        remaining = deadline - time.time()
        if remaining <= 0:
            break

        sleep_for = min(sleep_s, remaining)
        if sleep_for > 0:
            time.sleep(sleep_for)

        if sleep_s < PREFLIGHT_RETRY_MAX_SLEEP_SECONDS:
            sleep_s = min(sleep_s * 2, PREFLIGHT_RETRY_MAX_SLEEP_SECONDS)

    return last_result or CurlResult(
        success=False,
        body=f"Retry deadline exceeded after {attempt} attempts",
        http_code=0,
        curl_rc=None,
        stderr="Retry deadline exceeded",
    )
