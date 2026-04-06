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
    ClusterView,
    FindingsView,
    FleetStatusSummary,
    ProposalStatusSummary,
    ProposalView,
    RunView,
    UIIndexContext,
    build_ui_context,
    load_ui_index,
)

_CSS = """
body {
  font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
  margin: 0;
  background: linear-gradient(135deg, #0f172a, #111827);
  color: #f9fafb;
}

.page {
  max-width: 1200px;
  margin: auto;
  padding: 2rem;
}

.panel {
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.4);
  border-radius: 1rem;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  backdrop-filter: blur(8px);
}

h1, h2 {
  margin-top: 0;
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

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.card {
  background: rgba(30, 41, 59, 0.9);
  padding: 1rem;
  border-radius: 0.75rem;
  border: 1px solid rgba(148, 163, 184, 0.3);
}

.run-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1rem;
  align-items: start;
}

.run-summary .card {
  margin-bottom: 0.75rem;
}

.run-insight h3 {
  margin-top: 0;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  font-size: 0.9rem;
  color: #94a3b8;
}

.status-summary {
  margin-bottom: 0.5rem;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
}

.status-card {
  background: rgba(15, 118, 110, 0.2);
  border-radius: 0.75rem;
  padding: 0.65rem 0.8rem;
  border: 1px solid rgba(59, 130, 246, 0.35);
  text-align: center;
}

.status-card strong {
  display: block;
  font-size: 1.4rem;
}

.status-card span {
  display: block;
  font-size: 0.85rem;
  margin-top: 0.15rem;
}

.status-badges {
  margin-bottom: 1rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
}

.artifact-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  font-size: 0.85rem;
}

.artifact-link {
  color: #a5b4fc;
}

.artifact-link:hover {
  text-decoration: underline;
}

.artifact-missing {
  color: rgba(255, 255, 255, 0.65);
}

.lifecycle-history {
  margin: 0.25rem 0 0;
  padding-left: 1.25rem;
  font-size: 0.85rem;
}

.lifecycle-history li {
  margin-bottom: 0.25rem;
}

.small {
  font-size: 0.85rem;
  color: rgba(148, 163, 184, 0.9);
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
    findings_html = _render_findings(context.latest_findings)
    run_card = _render_run_card(context.run)
    status_summary = _render_status_cards(context.fleet_status)
    degraded_hint = _render_degraded_hint(context.fleet_status)
    proposal_badges = _render_proposal_status_badges(context.proposal_status_summary)
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Operator Health Console</title>
  <style>{_CSS}</style>
</head>
<body>
  <div class="page">
    <header class="panel">
      <h1>Health Operator Console</h1>
      <p>Run <strong>{html.escape(context.run.run_label)}</strong> ({html.escape(context.run.run_id)}) at {html.escape(context.run.timestamp)}</p>
      <div class="run-grid">
        <div class="run-summary">
          {run_card}
        </div>
        <div class="run-insight">
          <h3>Fleet snapshot</h3>
          <div class="status-summary">
            {status_summary}
          </div>
          {degraded_hint}
        </div>
      </div>
    </header>
    <section class="panel">
      <h2>Fleet Status</h2>
      <div class="card">
        <table>
          <thead>
            <tr>
              <th>Cluster</th>
              <th>Class</th>
              <th>Role</th>
              <th>Cohort</th>
              <th>Rating</th>
              <th>Warnings</th>
              <th>Non-running</th>
              <th>Nodes</th>
              <th>Control Plane</th>
              <th>Artifacts</th>
            </tr>
          </thead>
          <tbody>
            {cluster_rows or '<tr><td colspan="10">No clusters recorded yet</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <h2>Latest Findings</h2>
      <div class="card">
        {findings_html}
      </div>
    </section>
    <section class="panel">
      <h2>Proposal Queue</h2>
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
  </div>
</body>
</html>
"""


def _render_run_card(run: RunView) -> str:
    items = [
        ("Run ID", run.run_id),
        ("Collector", run.collector_version),
        ("Clusters", str(run.cluster_count)),
        ("Drilldowns", str(run.drilldown_count)),
        ("Proposals", str(run.proposal_count)),
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
    return f"""
<tr>
  <td>{html.escape(cluster.label)}</td>
  <td>{html.escape(cluster.cluster_class)}</td>
  <td>{html.escape(cluster.cluster_role)}</td>
  <td>{html.escape(cluster.baseline_cohort)}</td>
  <td>{html.escape(cluster.health_rating)}</td>
  <td>{cluster.warnings}</td>
  <td>{cluster.non_running_pods}</td>
  <td>{cluster.node_count}</td>
  <td>{html.escape(cluster.control_plane_version)}</td>
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


def _artifact_href(path: str) -> str:
    return f"/artifact?path={quote(path)}"
