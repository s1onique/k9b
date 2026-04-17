"""Alertmanager adapter for external analysis pipeline."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime

from .adapter import (
    AuthError,
    ExternalAnalysisAdapter,
    ExternalAnalysisRequest,
    InvalidResponseError,
    TimeoutError,
    UpstreamError,
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
        except TimeoutError as exc:
            # Distinct timeout handling
            snapshot = create_error_snapshot(
                AlertmanagerStatus.TIMEOUT,
                str(exc),
            )
        except AuthError as exc:
            # Distinct auth failure handling
            snapshot = create_error_snapshot(
                AlertmanagerStatus.AUTH_ERROR,
                str(exc),
            )
        except UpstreamError as exc:
            # Upstream service error (5xx, connection issues)
            snapshot = create_error_snapshot(
                AlertmanagerStatus.UPSTREAM_ERROR,
                str(exc),
            )
        except InvalidResponseError as exc:
            # Distinct invalid response handling
            snapshot = create_error_snapshot(
                AlertmanagerStatus.INVALID_RESPONSE,
                str(exc),
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
        """Fetch alerts from Alertmanager endpoint.
        
        Raises:
            TimeoutError: When the request times out
            AuthError: When authentication fails (401/403)
            InvalidResponseError: When response is malformed
        """
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
                raise AuthError(f"Alertmanager auth failed: {exc.code}") from exc
            # Other HTTP errors (500, 502, 503, etc.) -> upstream error
            raise UpstreamError(
                f"Alertmanager returned {exc.code}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            # Connection refused, DNS failure, etc. -> upstream error
            raise UpstreamError(
                f"Alertmanager unreachable: {exc.reason}"
            ) from exc
        except TimeoutError:
            raise TimeoutError("Alertmanager request timed out")
        except json.JSONDecodeError as exc:
            raise InvalidResponseError(
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
