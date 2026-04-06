"""Simple HTTP server for the operator UI."""

from __future__ import annotations

import functools
import html
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .model import (
    ClusterView,
    FindingsView,
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
        route = self.path.split("?", 1)[0]
        if route in ("/", "", "/index", "/index.html"):
            self._render_root()
        elif route == "/ui-index.json":
            self._serve_json()
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
      <p class="grid">
        {run_card}
      </p>
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
            </tr>
          </thead>
          <tbody>
            {cluster_rows or '<tr><td colspan="9">No clusters recorded yet</td></tr>'}
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
              <th>Run</th>
            </tr>
          </thead>
          <tbody>
            {proposal_rows or '<tr><td colspan="8">No proposals generated yet</td></tr>'}
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
</tr>
"""


def _render_proposal_row(proposal: ProposalView) -> str:
    status_class = _make_status_class(proposal.status)
    note = html.escape(proposal.latest_note) if proposal.latest_note else "-"
    return f"""
<tr>
  <td><span class=\"status-pill {status_class}\">{html.escape(proposal.status)}</span></td>
  <td>{html.escape(proposal.proposal_id)}</td>
  <td>{html.escape(proposal.target)}</td>
  <td>{html.escape(proposal.confidence)}</td>
  <td>{html.escape(proposal.rationale)}</td>
  <td>{html.escape(proposal.expected_benefit)}</td>
  <td>{note}</td>
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
    return f"""
<p><strong>Cluster:</strong> {html.escape(findings.label or "-")} ({html.escape(findings.context or "-")})</p>
<p><strong>Trigger reasons:</strong> {triggers or "none"}</p>
<p><strong>Rollout status:</strong> {rollout}</p>
<p><strong>Warnings:</strong> {findings.warning_events}, Non-running pods: {findings.non_running_pods}</p>
<ul class=\"list-bullet\">{summary or '<li>No summary entries</li>'}</ul>
<ul class=\"list-bullet\">{patterns or '<li>No pattern details</li>'}</ul>
"""


def _make_status_class(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in value.lower())
    return f"status-{cleaned}"
