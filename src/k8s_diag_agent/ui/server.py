"""Simple HTTP server for the operator UI."""

from __future__ import annotations

import functools
import html
import json
import sys
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote

from .model import (
    AssessmentView,
    ClusterView,
    DrilldownAvailabilityView,
    DrilldownCoverageEntry,
    ExternalAnalysisSummary,
    ExternalAnalysisView,
    FindingsView,
    FleetStatusSummary,
    NotificationView,
    ProposalStatusSummary,
    ProposalView,
    RunView,
    UIIndexContext,
    build_ui_context,
    load_ui_index,
)

_CSS = """
body {
  font-family: 'Space Grotesk', 'Inter', 'Segoe UI', system-ui, sans-serif;
  margin: 0;
  background: linear-gradient(135deg, #020617, #0b1231 60%, #111827);
  color: #f8fafc;
}

.page {
  max-width: 1200px;
  margin: auto;
  padding: 2rem 1rem 3rem;
}

.panel {
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 1rem;
  padding: 1.75rem;
  margin-bottom: 1.5rem;
  backdrop-filter: blur(10px);
  box-shadow: 0 20px 60px rgba(2, 6, 23, 0.35);
}

h1, h2 {
  margin-top: 0;
}

.hero {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 1rem;
}

.hero-content {
  max-width: 680px;
}

.hero h1 {
  font-size: 2.2rem;
  letter-spacing: 0.02em;
}

.hero-meta {
  margin: 0.35rem 0 0;
  color: rgba(248, 250, 252, 0.75);
  font-size: 0.9rem;
}

.hero-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.5rem;
}

.refresh-button {
  background: #4c1d95;
  border: none;
  padding: 0.65rem 1.15rem;
  border-radius: 999px;
  color: #f8fafc;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease;
}

.refresh-button:hover {
  background: #7c3aed;
  transform: translateY(-1px);
}

.floating-nav {
  display: flex;
  gap: 0.85rem;
  align-items: center;
  flex-wrap: wrap;
  padding: 0.8rem 1.1rem;
  background: rgba(15, 118, 110, 0.08);
  border-radius: 0.75rem;
  margin-bottom: 1rem;
}

.floating-nav a {
  color: #a5b4fc;
  text-transform: uppercase;
  font-size: 0.8rem;
  letter-spacing: 0.1em;
}

.fleet-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 1rem;
  gap: 0.75rem;
}

.fleet-metrics {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.fleet-metric {
  padding: 0.6rem 0.9rem;
  background: rgba(15, 23, 42, 0.9);
  border-radius: 0.65rem;
  border: 1px solid rgba(148, 163, 184, 0.3);
  text-align: right;
}

.fleet-metric strong {
  display: block;
  font-size: 1.4rem;
}

.fleet-metric .small {
  display: block;
  margin-top: 0.2rem;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  text-align: left;
  padding: 0.6rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.3);
}

.fleet-table-card {
  overflow-x: auto;
}

.status-pill {
  padding: 0.2rem 0.75rem;
  border-radius: 999px;
  font-size: 0.85rem;
  text-transform: capitalize;
}

.status-pending { background: #facc15; color: #0a0a0a; }
.status-checked { background: #22c55e; color: #0a0a0a; }
.status-accepted { background: #2563eb; }
.status-rejected { background: #ef4444; }
.status-applied { background: #14b8a6; }
.status-proposed, .status-replayed, .status-promoted { background: #94a3b8; }

.list-bullet {
  margin: 0;
  padding-left: 1.5rem;
}

.card {
  background: rgba(30, 41, 59, 0.95);
  padding: 1rem;
  border-radius: 0.85rem;
  border: 1px solid rgba(148, 163, 184, 0.3);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.25rem;
}

.detail-column {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.detail-card {
  background: rgba(15, 23, 42, 0.95);
  border-radius: 0.85rem;
  border: 1px solid rgba(59, 130, 246, 0.25);
  padding: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.detail-card h3 {
  margin: 0;
  font-size: 1rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #94a3b8;
}

.detail-list {
  margin: 0;
  padding-left: 1.2rem;
  color: rgba(248, 250, 252, 0.9);
}

.detail-action {
  background: rgba(59, 130, 246, 0.08);
  padding: 0.75rem;
  border-radius: 0.65rem;
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.detail-artifacts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  font-size: 0.85rem;
}

.small {
  font-size: 0.85rem;
  color: rgba(148, 163, 184, 0.9);
}

.drilldown-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.75rem;
}

.drilldown-card {
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid rgba(59, 130, 246, 0.4);
  border-radius: 0.75rem;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.drilldown-card.available {
  border-color: rgba(16, 185, 129, 0.6);
}

.drilldown-card.missing {
  border-color: rgba(239, 68, 68, 0.6);
}

.drilldown-card-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 0.95rem;
}

.notification-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.notification-entry {
  background: rgba(30, 41, 59, 0.85);
  border-radius: 0.75rem;
  border: 1px solid rgba(148, 163, 184, 0.4);
  padding: 0.95rem 1rem;
}

.notification-head {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.notification-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: rgba(148, 163, 184, 0.8);
}

.notification-details {
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
  font-size: 0.85rem;
}

.notification-artifact {
  margin-top: 0.5rem;
}

.external-analysis-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.external-analysis-entry {
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  padding-bottom: 0.5rem;
}

.external-analysis-entry:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

"""

def start_ui_server(runs_dir: Path, host: str = "127.0.0.1", port: int = 8080) -> None:
    handler = functools.partial(HealthUIRequestHandler, runs_dir=runs_dir)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Operator UI listening on http://{host}:{port}/ (runs: {runs_dir})", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down operator UI server", file=sys.stderr)
        server.shutdown()
    finally:
        server.server_close()


class HealthUIRequestHandler(BaseHTTPRequestHandler):
    server_version = "HealthUI/1.0"

    def __init__(self, *args: object, runs_dir: Path, **kwargs: object) -> None:
        self.runs_dir = runs_dir
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def do_GET(self) -> None:
        route, _, query = self.path.partition("?")
        if route in ("/", "", "/index", "/index.html"):
            self._render_root()
        elif route == "/ui-index.json":
            self._serve_json()
        elif route == "/artifact":
            self._serve_artifact(query)
        else:
            self.send_error(404, "Not Found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _render_root(self) -> None:
        try:
            index = load_ui_index(self.runs_dir)
            context = build_ui_context(index)
            body = _render_html(context)
        except Exception as exc:
            self._send_text(500, f"Unable to render UI: {exc}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _serve_json(self) -> None:
        try:
            index = load_ui_index(self.runs_dir)
        except Exception as exc:
            self._send_text(500, f"Unable to read ui-index.json: {exc}")
            return
        payload = json.dumps(index)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(payload.encode("utf-8"))

    def _serve_artifact(self, query: str) -> None:
        params = parse_qs(query)
        paths = params.get("path")
        if not paths:
            self._send_text(400, "Artifact path required")
            return
        requested = Path(paths[0])
        try:
            artifact_path = (self.runs_dir / requested).resolve()
        except Exception:
            self._send_text(400, "Invalid artifact path")
            return
        root_resolved = self.runs_dir.resolve()
        if not str(artifact_path).startswith(str(root_resolved)):
            self._send_text(400, "Invalid artifact path")
            return
        if not artifact_path.exists():
            self._send_text(404, "Artifact not found")
            return
        try:
            payload = artifact_path.read_text(encoding="utf-8")
        except OSError as exc:
            self._send_text(500, f"Unable to read artifact: {exc}")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(payload.encode("utf-8"))

    def _send_text(self, code: int, message: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))


def _render_html(context: UIIndexContext) -> str:
    cluster_rows = "".join(_render_cluster_row(cluster) for cluster in context.clusters)
    proposal_rows = "".join(_render_proposal_row(proposal) for proposal in context.proposals)
    run_card = _render_run_card(context.run)
    status_summary = _render_status_cards(context.fleet_status)
    degraded_hint = _render_degraded_hint(context.fleet_status)
    proposal_badges = _render_proposal_status_badges(context.proposal_status_summary)
    drilldown_section = _render_drilldown_section(context.drilldown_availability)
    notification_section = _render_notification_history(context.notification_history)
    external_analysis_section = _render_external_analysis_section(context.external_analysis)
    pending_proposals, total_proposals = _count_proposal_totals(context.proposal_status_summary)
    detail_section = _render_detail_section(context)
    detail_artifacts = _render_detail_artifacts(context)
    return (
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Operator Health Console</title>
  <style>{_CSS}</style>
</head>
<body>
  <div class="page">
    <header class="panel hero">
      <div class="hero-content">
        <h1>Health Operator Console</h1>
        <p class="hero-meta">Run <strong>{html.escape(context.run.run_label)}</strong> ({html.escape(context.run.run_id)})</p>
        <p class="hero-meta small">Collector {html.escape(context.run.collector_version)} &middot; {context.run.cluster_count} clusters &middot; {context.run.notification_count} notifications</p>
      </div>
      <div class="hero-actions">
        <button class="refresh-button" type="button" onclick="location.reload()">Refresh data</button>
        <span class="hero-meta small">Updated {html.escape(context.run.timestamp)}</span>
      </div>
      <div class="status-summary">{status_summary}</div>
      {degraded_hint}
    </header>
    <nav class="floating-nav panel" aria-label="Quick links">
      <a href="#fleet">Fleet overview</a>
      <a href="#detail">Run detail</a>
      <a href="#proposals">Proposal queue</a>
    </nav>
    <section class="panel">
      <h2>Run summary</h2>
      <div class="run-grid">
        {run_card}
      </div>
    </section>
    <section id="fleet" class="panel">
      <div class="fleet-header">
        <h2>Fleet overview</h2>
        <div class="fleet-metrics">
          <div class="fleet-metric">
            <span class="fleet-metric-label">Pending proposals</span>
            <strong class="fleet-metric-value">{pending_proposals}</strong>
            <span class="small">pending</span>
          </div>
          <div class="fleet-metric">
            <span class="fleet-metric-label">Total proposals</span>
            <strong class="fleet-metric-value">{total_proposals}</strong>
            <span class="small">queued</span>
          </div>
        </div>
      </div>
      <div class="card fleet-table-card">
        <table>
          <thead>
            <tr>
              <th>Cluster</th>
              <th>Class / Role</th>
              <th>Cohort</th>
              <th>Rating</th>
              <th>Latest run</th>
              <th>Top trigger</th>
              <th>Drilldown</th>
              <th>Artifacts</th>
            </tr>
          </thead>
          <tbody>
            {cluster_rows or '<tr><td colspan="8">No clusters recorded yet.</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section id="detail" class="panel">
      <h2>Cluster & run detail</h2>
      <div class="detail-grid">
        {detail_section}
      </div>
      <div class="detail-artifacts">
        {detail_artifacts}
      </div>
    </section>
    <section class="panel">
      <h2>Drilldown availability</h2>
      <div class="card">
        {drilldown_section}
      </div>
    </section>
    <section id="proposals" class="panel">
      <h2>Proposal queue</h2>
      <div class="card">
        {proposal_badges}
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Proposal ID</th>
              <th>Target</th>
              <th>Confidence</th>
              <th>Rationale</th>
              <th>Benefit</th>
              <th>Note</th>
              <th>Lifecycle</th>
              <th>Artifacts</th>
              <th>Run</th>
            </tr>
          </thead>
          <tbody>
            {proposal_rows or '<tr><td colspan="10">No proposals generated yet</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <h2>External analysis</h2>
      <div class="card">
        {external_analysis_section}
      </div>
    </section>
    <section class="panel">
      <h2>Notification history</h2>
      <div class="card">
        {notification_section}
      </div>
    </section>
  </div>
</body>
</html>
"""
    )


def _render_run_card(run: RunView) -> str:
    items = [
        ("Run ID", run.run_id),
        ("Collector", run.collector_version),
        ("Clusters", str(run.cluster_count)),
        ("Drilldowns", str(run.drilldown_count)),
        ("Proposals", str(run.proposal_count)),
        ("External Analysis", str(run.external_analysis_count)),
        ("Notifications", str(run.notification_count)),
    ]
    cards = "".join(f"<div class=\"card\"><strong>{html.escape(label)}</strong><p>{html.escape(value)}</p></div>" for label, value in items)
    return cards


def _render_cluster_row(cluster: ClusterView) -> str:
    artifact_links = _render_artifact_links(
        (
            ("Snapshot", cluster.snapshot_path),
            ("Assessment", cluster.assessment_path),
            ("Drilldown", cluster.drilldown_path),
        )
    )
    trigger_reason = html.escape(cluster.top_trigger_reason or "Awaiting trigger")
    drilldown_status = "Ready" if cluster.drilldown_available else "Missing"
    timestamp = html.escape(cluster.drilldown_timestamp or "pending")
    rating_class = _make_status_class(cluster.health_rating)
    return f"""
<tr>
  <td>
    <strong>{html.escape(cluster.label)}</strong><br>
    <span class="small">{html.escape(cluster.context)}</span>
  </td>
  <td>
    {html.escape(cluster.cluster_class)} / {html.escape(cluster.cluster_role)}
  </td>
  <td>{html.escape(cluster.baseline_cohort)}</td>
  <td><span class="status-pill {rating_class}">{html.escape(cluster.health_rating)}</span></td>
  <td>{html.escape(cluster.latest_run_timestamp)}</td>
  <td>{trigger_reason}</td>
  <td><span class="small">{drilldown_status}</span><br><span class="small">{timestamp}</span></td>
  <td>{artifact_links}</td>
</tr>
"""


def _render_proposal_row(proposal: ProposalView) -> str:
    status_class = _make_status_class(proposal.status)
    note = html.escape(proposal.latest_note) if proposal.latest_note else "-"
    lifecycle = _render_proposal_lifecycle(proposal.lifecycle_history)
    artifact_links = _render_artifact_links(
        (
            ("Proposal JSON", proposal.artifact_path),
            ("Review JSON", proposal.review_path),
        )
    )
    return f"""
<tr>
  <td><span class=\"status-pill {status_class}\">{html.escape(proposal.status)}</span></td>
  <td>{html.escape(proposal.proposal_id)}</td>
  <td>{html.escape(proposal.target)}</td>
  <td>{html.escape(proposal.confidence)}</td>
  <td>{html.escape(proposal.rationale)}</td>
  <td>{html.escape(proposal.expected_benefit)}</td>
  <td>{note}</td>
  <td>{lifecycle}</td>
  <td>{artifact_links}</td>
  <td>{html.escape(proposal.source_run_id)}</td>
</tr>
"""


def _render_findings(findings: FindingsView | None) -> str:
    if not findings:
        return "<p>No findings captured yet.</p>"
    summary = "".join(f"<li><strong>{html.escape(label)}</strong>: {html.escape(value)}</li>" for label, value in findings.summary)
    patterns = "".join(f"<li><strong>{html.escape(label)}</strong>: {html.escape(value)}</li>" for label, value in findings.pattern_details)
    triggers = ", ".join(html.escape(reason) for reason in findings.trigger_reasons)
    rollout = ", ".join(html.escape(item) for item in findings.rollout_status) or "none"
    artifact_link = ""
    if findings.artifact_path:
        artifact_link = f"<p>{_render_artifact_link('Open drilldown JSON', findings.artifact_path)}</p>"
    return f"""
<p><strong>Cluster:</strong> {html.escape(findings.label or "-")} ({html.escape(findings.context or "-")})</p>
<p><strong>Trigger reasons:</strong> {triggers or "none"}</p>
<p><strong>Rollout status:</strong> {rollout}</p>
<p><strong>Warnings:</strong> {findings.warning_events}, Non-running pods: {findings.non_running_pods}</p>
<ul class=\"list-bullet\">{summary or '<li>No summary entries</li>'}</ul>
<ul class=\"list-bullet\">{patterns or '<li>No pattern details</li>'}</ul>
{artifact_link}
"""


def _make_status_class(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in value.lower())
    return f"status-{cleaned}"


def _render_status_cards(summary: FleetStatusSummary) -> str:
    if not summary.rating_counts:
        return "<p class=\"small\">No fleet health data yet.</p>"
    cards = []
    for rating, count in summary.rating_counts:
        label = html.escape(rating or "unknown")
        class_name = _make_status_class(rating)
        cards.append(
            f"<div class=\"status-card {class_name}\"><strong>{count}</strong><span>{label}</span></div>"
        )
    return f"<div class=\"status-grid\">{''.join(cards)}</div>"


def _render_degraded_hint(summary: FleetStatusSummary) -> str:
    if not summary.degraded_clusters:
        return '<p class="small">All clusters are healthy or reporting unknown ratings.</p>'
    clusters = ", ".join(html.escape(label) for label in summary.degraded_clusters)
    return f'<p class="small">Degraded clusters: {clusters}</p>'


def _render_proposal_status_badges(summary: ProposalStatusSummary) -> str:
    if not summary.status_counts:
        return '<p class="small">No proposals generated yet.</p>'
    badges = []
    for status, count in summary.status_counts:
        entry = html.escape(status or "unknown")
        class_name = _make_status_class(status)
        badges.append(
            f"<span class=\"status-pill {class_name}\">{entry} ({count})</span>"
        )
    return f"<div class=\"status-badges\">{' '.join(badges)}</div>"


def _render_proposal_lifecycle(history: tuple[tuple[str, str, str | None], ...]) -> str:
    if not history:
        return '<p class="small">Lifecycle records unavailable.</p>'
    items = []
    for status, timestamp, note in history:
        label = html.escape(status or "unknown")
        when = html.escape(timestamp)
        note_text = f" — {html.escape(note)}" if note else ""
        items.append(f"<li><strong>{label}</strong> @ {when}{note_text}</li>")
    return f"<ul class=\"lifecycle-history\">{''.join(items)}</ul>"


def _render_artifact_links(items: Sequence[tuple[str, str | None]]) -> str:
    links = []
    for label, path in items:
        links.append(_render_artifact_link(label, path))
    return f"<div class=\"artifact-links\">{' • '.join(links)}</div>"


def _render_artifact_link(label: str, path: str | None) -> str:
    if not path:
        return f"<span class=\"artifact-missing\">{html.escape(label)}</span>"
    href = _artifact_href(path)
    return f"<a href=\"{html.escape(href)}\" class=\"artifact-link\" target=\"_blank\" rel=\"noopener\">{html.escape(label)}</a>"


def _render_drilldown_section(availability: DrilldownAvailabilityView) -> str:
    if not availability.coverage:
        return '<p class="small">No drilldowns captured yet.</p>'
    cards = "".join(_render_drilldown_card(entry) for entry in availability.coverage)
    summary = (
        f'<p class="small">{availability.available}/{availability.total_clusters} clusters have drilldowns.</p>'
    )
    if availability.missing_clusters:
        missing = ", ".join(html.escape(label) for label in availability.missing_clusters)
        summary += f'<p class="small">Missing drilldowns: {missing}</p>'
    return f"<div class=\"drilldown-grid\">{cards}</div>{summary}"


def _render_drilldown_card(entry: DrilldownCoverageEntry) -> str:
    status = "Ready" if entry.available else "Missing"
    status_class = "available" if entry.available else "missing"
    timestamp = html.escape(entry.timestamp) if entry.timestamp else "pending"
    artifact_link = _render_artifact_link("View drilldown", entry.artifact_path)
    return f"""
    <div class="drilldown-card {status_class}">
      <div class="drilldown-card-head">
        <strong>{html.escape(entry.label)}</strong>
        <span>{status}</span>
      </div>
      <p class="small">Context: {html.escape(entry.context)}</p>
      <p class="small">Captured: {timestamp}</p>
      <div class="artifact-links">{artifact_link}</div>
    </div>
    """


def _render_notification_history(notifications: tuple[NotificationView, ...]) -> str:
    if not notifications:
        return '<p class="small">No notifications recorded for this run.</p>'
    entries = "".join(_render_notification_entry(entry) for entry in notifications)
    return f"<ul class=\"notification-list\">{entries}</ul>"


def _render_notification_entry(entry: NotificationView) -> str:
    details = "".join(
        f"<li><strong>{html.escape(label)}</strong>: {html.escape(value)}</li>"
        for label, value in entry.details
    ) or "<li>-</li>"
    artifact_link = _render_artifact_link("View notification", entry.artifact_path)
    return f"""
    <li class="notification-entry">
      <div class="notification-head">
        <span class="status-pill {_make_status_class(entry.kind)}">{html.escape(entry.kind)}</span>
        <strong>{html.escape(entry.summary)}</strong>
        <span class="small">{html.escape(entry.timestamp)}</span>
      </div>
      <div class="notification-meta">
        <span>Run: {html.escape(entry.run_id or "-")}</span>
        <span>Cluster: {html.escape(entry.cluster_label or "-")}</span>
        <span>Context: {html.escape(entry.context or "-")}</span>
      </div>
      <ul class="notification-details">{details}</ul>
      <div class="notification-artifact">{artifact_link}</div>
    </li>
    """


def _render_external_analysis_section(summary: ExternalAnalysisSummary) -> str:
    if not summary.artifacts:
        return '<p class="small">External analysis not executed for this run.</p>'
    badges = "".join(
        f"<span class=\"status-pill {_make_status_class(status)}\">{html.escape(status)} ({count})</span>"
        for status, count in summary.status_counts
    )
    entries = "".join(_render_external_analysis_entry(entry) for entry in summary.artifacts)
    return f"<div class=\"status-badges\">{badges}</div><ul class=\"external-analysis-list\">{entries}</ul>"


def _render_external_analysis_entry(entry: ExternalAnalysisView) -> str:
    details = entry.findings + entry.suggested_next_checks
    detail_lines = "".join(f"<li>{html.escape(value)}</li>" for value in details) or "<li>-</li>"
    artifact_link = _render_artifact_link("View output", entry.artifact_path)
    return f"""
    <li class="external-analysis-entry">
      <strong>{html.escape(entry.tool_name)}</strong>
      <span class="small">{html.escape(entry.cluster_label or "")}</span>
      <p>{html.escape(entry.summary or "-")}</p>
      <p class="small">Status: {html.escape(entry.status)}, Captured: {html.escape(entry.timestamp)}</p>
      <ul class="notification-details">{detail_lines}</ul>
      <div class="notification-artifact">{artifact_link}</div>
    </li>
    """


def _count_proposal_totals(summary: ProposalStatusSummary) -> tuple[int, int]:
    counts: dict[str, int] = {}
    for status, count in summary.status_counts:
        text = (status or "").lower()
        if not text:
            continue
        counts[text] = counts.get(text, 0) + count
    total = sum(counts.values())
    return counts.get("pending", 0), total


def _render_detail_section(context: UIIndexContext) -> str:
    assessment_panel = _render_assessment_panel(context.latest_assessment)
    drilldown_panel = _render_findings(context.latest_findings)
    notification_panel = _render_related_notifications(context.notification_history, context.latest_assessment)
    return f"""
    <div class="detail-column">
      <div class="detail-card">
        <h3>Latest assessment summary</h3>
        {assessment_panel}
      </div>
    </div>
    <div class="detail-column">
      <div class="detail-card">
        <h3>Latest drilldown summary</h3>
        {drilldown_panel}
      </div>
      <div class="detail-card">
        <h3>Related notifications</h3>
        {notification_panel}
      </div>
    </div>
    """


def _render_assessment_panel(assessment: AssessmentView | None) -> str:
    if not assessment:
        return '<p class="small">Assessment information will appear after the next run.</p>'
    missing = ", ".join(html.escape(item) for item in assessment.missing_evidence) or "none"
    findings = []
    for finding in assessment.findings:
        signals = ", ".join(html.escape(value) for value in finding.supporting_signals) or "n/a"
        findings.append(
            f"<li><strong>{html.escape(finding.description)}</strong><br><span class=\"small\">{html.escape(finding.layer)} · Signals: {signals}</span></li>"
        )
    hypotheses = []
    for hypothesis in assessment.hypotheses:
        falsifier = html.escape(hypothesis.what_would_falsify or "n/a")
        hypotheses.append(
            "<li><strong>"
            f"{html.escape(hypothesis.description)}"
            "</strong><br>"
            "<span class=\"small\">"
            f"Confidence: {html.escape(hypothesis.confidence)}, Layer: {html.escape(hypothesis.probable_layer)}"
            "</span><br>"
            "<span class=\"small\">"
            f"Falsifier: {falsifier}"
            "</span></li>"
        )
    next_checks = []
    for check in assessment.next_checks:
        evidence = ", ".join(html.escape(item) for item in check.evidence_needed) or "-"
        next_checks.append(
            f"<li><strong>{html.escape(check.description)}</strong><br><span class=\"small\">{html.escape(check.owner)} · {html.escape(check.method)}</span><br><span class=\"small\">Evidence needed: {evidence}</span></li>"
        )
    action_html = '<p class="small">No recommended action yet.</p>'
    if assessment.recommended_action:
        action = assessment.recommended_action
        references = ", ".join(html.escape(value) for value in action.references) or "-"
        action_html = f"""
        <div class=\"detail-action\">
          <p><strong>{html.escape(action.action_type)}</strong>: {html.escape(action.description)}</p>
          <p class=\"small\">Safety: {html.escape(action.safety_level)} · References: {references}</p>
        </div>
        """
    confidence_text = html.escape(assessment.overall_confidence or "n/a")
    layer_text = html.escape(assessment.probable_layer or "n/a")
    rating_class = _make_status_class(assessment.health_rating)
    return f"""
    <p class=\"small\">Cluster: {html.escape(assessment.cluster_label)} · Context: {html.escape(assessment.context)}</p>
    <p class=\"small\">Confidence: {confidence_text} · Layer: {layer_text}</p>
    <span class=\"status-pill {rating_class}\">{html.escape(assessment.health_rating)}</span>
    <p class=\"small\">Missing evidence: {missing}</p>
    <h4>Findings</h4>
    <ul class=\"detail-list\">{''.join(findings) or '<li>No findings logged</li>'}</ul>
    <h4>Hypotheses</h4>
    <ul class=\"detail-list\">{''.join(hypotheses) or '<li>No hypotheses recorded</li>'}</ul>
    <h4>Recommended next checks</h4>
    <ul class=\"detail-list\">{''.join(next_checks) or '<li>No next checks yet</li>'}</ul>
    {action_html}
    """


def _render_related_notifications(
    notifications: tuple[NotificationView, ...],
    assessment: AssessmentView | None,
) -> str:
    if not notifications:
        return '<p class="small">No notifications recorded for this run.</p>'
    relevant: list[NotificationView] = []
    if assessment and (assessment.cluster_label or assessment.context):
        for entry in notifications:
            if assessment.cluster_label and entry.cluster_label == assessment.cluster_label:
                relevant.append(entry)
            elif assessment.context and entry.context == assessment.context:
                relevant.append(entry)
    if not relevant:
        relevant = list(notifications[:3])
    else:
        relevant = relevant[:3]
    if not relevant:
        return '<p class="small">No related notifications.</p>'
    entries = "".join(_render_notification_entry(entry) for entry in relevant)
    return f"<ul class=\"notification-list\">{entries}</ul>"


def _render_detail_artifacts(context: UIIndexContext) -> str:
    links: list[tuple[str, str | None]] = []
    if context.latest_assessment:
        links.append(("Assessment JSON", context.latest_assessment.artifact_path))
        links.append(("Snapshot JSON", context.latest_assessment.snapshot_path))
    if context.latest_findings and context.latest_findings.artifact_path:
        links.append(("Drilldown JSON", context.latest_findings.artifact_path))
    filtered = [(label, path) for label, path in links if path]
    if not filtered:
        return '<p class="small">Artifacts will appear once the next run completes.</p>'
    return _render_artifact_links(filtered)


def _artifact_href(path: str) -> str:
    return f"/artifact?path={quote(path)}"
