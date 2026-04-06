"""Render and deliver Mattermost notification payloads."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path

import requests

from ..health.notifications import NotificationArtifact


def load_notification_artifact(path: Path) -> NotificationArtifact:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(f"Notification file does not contain a mapping: {path}")
    return NotificationArtifact.from_dict(raw)


def render_mattermost_payload(artifact: NotificationArtifact) -> dict[str, object]:
    template = _TEMPLATES.get(artifact.kind, _default_render)
    text = template(artifact)
    return {"text": text}


class MattermostNotifier:
    def __init__(
        self,
        webhook_url: str,
        *,
        session: requests.Session | None = None,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
    ) -> None:
        self.webhook_url = webhook_url
        self.session = session or requests.Session()
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds

    def dispatch(self, artifact: NotificationArtifact) -> requests.Response:
        payload = render_mattermost_payload(artifact)
        last_error: requests.RequestException | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.post(self.webhook_url, json=payload, timeout=10)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    raise
                time.sleep(self.backoff_seconds)
        assert last_error is not None
        raise last_error


def _default_render(artifact: NotificationArtifact) -> str:
    return _format_footer(artifact, artifact.summary)


def _render_degraded(artifact: NotificationArtifact) -> str:
    details = artifact.details
    cluster_label = artifact.cluster_label or details.get("cluster") or "unknown"
    context = artifact.context or "unknown"
    warnings = _stringify(details.get("warnings"))
    lines = [
        f"🚨 {artifact.summary}",
        f"Cluster: {cluster_label}",
        f"Context: {context}",
        f"Missing evidence: {warnings}",
    ]
    return _format_footer(artifact, "\n".join(lines))


def _render_suspicious(artifact: NotificationArtifact) -> str:
    details = artifact.details
    reasons = _stringify(details.get("reasons"))
    differences = _stringify(details.get("differences"))
    intent = details.get("intent") or "unknown"
    lines = [
        f"🔍 {artifact.summary}",
        f"Intent: {intent}",
        f"Trigger reasons: {reasons}",
        f"Differences: {differences}",
    ]
    return _format_footer(artifact, "\n".join(lines))


def _render_proposal_created(artifact: NotificationArtifact) -> str:
    details = artifact.details
    lines = [
        f"🧭 {artifact.summary}",
        f"Target: {details.get('target') or '-'}",
        f"Confidence: {details.get('confidence') or '-'}",
        f"Rationale: {details.get('rationale') or '-'}",
    ]
    return _format_footer(artifact, "\n".join(lines))


def _render_proposal_checked(artifact: NotificationArtifact) -> str:
    details = artifact.details
    lines = [
        f"✅ {artifact.summary}",
        f"Outcome: {details.get('outcome') or '-'}",
        f"Noise reduction: {details.get('noise_reduction') or '-'}",
        f"Signal loss: {details.get('signal_loss') or '-'}",
    ]
    return _format_footer(artifact, "\n".join(lines))


def _format_footer(artifact: NotificationArtifact, body: str) -> str:
    footer = f"Run: {artifact.run_id or '-'} | Timestamp: {artifact.timestamp}"
    return f"{body}\n{footer}"


def _stringify(value: object | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


_TEMPLATES: dict[str, Callable[[NotificationArtifact], str]] = {
    "degraded-health": _render_degraded,
    "suspicious-comparison": _render_suspicious,
    "proposal-created": _render_proposal_created,
    "proposal-checked": _render_proposal_checked,
}
