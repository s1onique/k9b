"""Alertmanager adapter for external analysis pipeline."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

from .adapter import (
    ExternalAnalysisAdapter,
    ExternalAnalysisExecutionError,
    ExternalAnalysisRequest,
    register_external_analysis_adapter,
)
from .alertmanager_config import AlertmanagerConfig
from .alertmanager_snapshot import (
    AlertmanagerCompact,
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    create_error_snapshot,
    normalize_alertmanager_payload,
    snapshot_to_compact,
)
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .config import ExternalAnalysisAdapterConfig, ExternalAnalysisSettings


def _compute_deterministic_fingerprint(labels_sorted: tuple[tuple[str, str], ...]) -> str:
    """Compute deterministic fingerprint from sorted labels tuple using MD5."""
    raw = json.dumps(dict(labels_sorted), sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:32]


class AlertmanagerAdapter(ExternalAnalysisAdapter):
    """Adapter for querying Alertmanager and producing run-scoped artifacts."""

    name = "alertmanager"

    def __init__(
        self,
        config: AlertmanagerConfig,
        command: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(command)
        self._config = config

    def run(self, request: ExternalAnalysisRequest) -> ExternalAnalysisArtifact:
        """Fetch Alertmanager alerts and produce snapshot/compact artifacts."""
        start_time = datetime.now(UTC)
        duration_ms: int | None = None
        snapshot: AlertmanagerSnapshot
        try:
            if not self._config.enabled:
                snapshot = create_error_snapshot(
                    AlertmanagerStatus.DISABLED,
                    "Alertmanager integration is disabled",
                )
            elif not self._config.is_configured():
                snapshot = create_error_snapshot(
                    AlertmanagerStatus.INVALID_RESPONSE,
                    "Alertmanager endpoint not configured",
                )
            else:
                raw_response = self._fetch_alerts()
                snapshot = normalize_alertmanager_payload(
                    raw_response,
                    config_max_alerts=self._config.max_alerts_in_snapshot,
                    config_max_string_length=self._config.max_string_length,
                )
        except ExternalAnalysisExecutionError as exc:
            # Fetch failures create error snapshots instead of crashing
            snapshot = create_error_snapshot(
                AlertmanagerStatus.UPSTREAM_ERROR,
                f"Fetch failed: {exc}",
            )
        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
        compact = snapshot_to_compact(
            snapshot,
            max_alerts=self._config.max_alerts_in_compact,
        )
        status_map = {
            AlertmanagerStatus.OK: ExternalAnalysisStatus.SUCCESS,
            AlertmanagerStatus.EMPTY: ExternalAnalysisStatus.SUCCESS,
            AlertmanagerStatus.TIMEOUT: ExternalAnalysisStatus.FAILED,
            AlertmanagerStatus.AUTH_ERROR: ExternalAnalysisStatus.FAILED,
            AlertmanagerStatus.UPSTREAM_ERROR: ExternalAnalysisStatus.FAILED,
            AlertmanagerStatus.DISABLED: ExternalAnalysisStatus.SKIPPED,
            AlertmanagerStatus.INVALID_RESPONSE: ExternalAnalysisStatus.FAILED,
        }
        artifact_status = status_map.get(snapshot.status, ExternalAnalysisStatus.FAILED)
        summary = _build_summary(snapshot)
        return ExternalAnalysisArtifact(
            tool_name=self.name,
            run_id=request.run_id,
            cluster_label=request.cluster_label,
            source_artifact=request.source_artifact,
            summary=summary,
            status=artifact_status,
            raw_output=json.dumps(snapshot.to_dict(), indent=2),
            timestamp=start_time,
            provider="alertmanager",
            duration_ms=duration_ms,
            purpose=ExternalAnalysisArtifact.purpose,
            payload={
                "snapshot": snapshot.to_dict(),
                "compact": compact.to_dict(),
            },
            error_summary="; ".join(snapshot.errors) if snapshot.errors else None,
        )

    def _fetch_alerts(self) -> dict | list | None:
        """Fetch alerts from Alertmanager endpoint."""
        endpoint = self._config.endpoint
        if not endpoint:
            return None
        auth = self._config.auth
        timeout = self._config.timeout_seconds
        headers: dict[str, str] = {"Accept": "application/json"}
        if auth.bearer_token:
            headers["Authorization"] = f"Bearer {auth.bearer_token}"
        elif auth.username and auth.password:
            import base64
            credentials = f"{auth.username}:{auth.password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        url = f"{endpoint.rstrip('/')}/api/v2/alerts"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read()
                parsed: dict[str, object] | list[object] = json.loads(body)
                return parsed
        except urllib.error.HTTPError as exc:
            if exc.code == 401 or exc.code == 403:
                raise ExternalAnalysisExecutionError(
                    f"Alertmanager auth failed: {exc.code}"
                ) from exc
            raise ExternalAnalysisExecutionError(
                f"Alertmanager returned {exc.code}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ExternalAnalysisExecutionError(
                f"Alertmanager unreachable: {exc.reason}"
            ) from exc
        except TimeoutError:
            raise ExternalAnalysisExecutionError("Alertmanager request timed out")
        except json.JSONDecodeError as exc:
            raise ExternalAnalysisExecutionError(
                f"Alertmanager returned invalid JSON: {exc}"
            ) from exc


def _build_summary(snapshot: AlertmanagerSnapshot) -> str:
    """Build human-readable summary for artifact."""
    count = snapshot.alert_count
    status = snapshot.status.value
    if status == "disabled":
        return "Alertmanager integration disabled"
    if status == "timeout":
        return "Alertmanager query timed out"
    if status == "auth_error":
        return "Alertmanager authentication failed"
    if status == "upstream_error":
        return f"Alertmanager returned error: {'; '.join(snapshot.errors)[:100]}"
    if status == "invalid_response":
        return f"Alertmanager returned invalid response: {'; '.join(snapshot.errors)[:100]}"
    if count == 0:
        return "No active alerts in Alertmanager"
    return f"Alertmanager: {count} alert(s) (status: {status})"


@register_external_analysis_adapter("alertmanager")
def _build_alertmanager_adapter(
    config: ExternalAnalysisAdapterConfig,
    settings: ExternalAnalysisSettings,
) -> ExternalAnalysisAdapter | None:
    """Build Alertmanager adapter using AlertmanagerConfig from settings."""
    return AlertmanagerAdapter(config=settings.alertmanager)


def create_alertmanager_artifact(
    request: ExternalAnalysisRequest,
    snapshot: AlertmanagerSnapshot,
    compact: AlertmanagerCompact,
) -> ExternalAnalysisArtifact:
    """Create ExternalAnalysisArtifact from snapshot and compact."""
    status_map = {
        AlertmanagerStatus.OK: ExternalAnalysisStatus.SUCCESS,
        AlertmanagerStatus.EMPTY: ExternalAnalysisStatus.SUCCESS,
        AlertmanagerStatus.TIMEOUT: ExternalAnalysisStatus.FAILED,
        AlertmanagerStatus.AUTH_ERROR: ExternalAnalysisStatus.FAILED,
        AlertmanagerStatus.UPSTREAM_ERROR: ExternalAnalysisStatus.FAILED,
        AlertmanagerStatus.DISABLED: ExternalAnalysisStatus.SKIPPED,
        AlertmanagerStatus.INVALID_RESPONSE: ExternalAnalysisStatus.FAILED,
    }
    artifact_status = status_map.get(snapshot.status, ExternalAnalysisStatus.FAILED)
    summary = _build_summary(snapshot)
    return ExternalAnalysisArtifact(
        tool_name="alertmanager",
        run_id=request.run_id,
        cluster_label=request.cluster_label,
        source_artifact=request.source_artifact,
        summary=summary,
        status=artifact_status,
        raw_output=json.dumps(snapshot.to_dict(), indent=2),
        timestamp=datetime.now(UTC),
        provider="alertmanager",
        duration_ms=None,
        purpose=ExternalAnalysisArtifact.purpose,
        payload={
            "snapshot": snapshot.to_dict(),
            "compact": compact.to_dict(),
        },
        error_summary="; ".join(snapshot.errors) if snapshot.errors else None,
    )
