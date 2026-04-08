"""HTTP server that serves the new UI assets and read model endpoints."""

from __future__ import annotations

import functools
import json
import mimetypes
import sys
from collections.abc import Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from ..external_analysis.manual_next_check import (
    ManualNextCheckError,
    execute_manual_next_check,
)
from ..external_analysis.next_check_approval import (
    log_next_check_approval_event,
    record_next_check_approval,
)
from .api import (
    build_cluster_detail_payload,
    build_fleet_payload,
    build_proposals_payload,
    build_run_payload,
)
from .model import UIIndexContext, build_ui_context, load_ui_index
from .notifications import query_notifications

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STATIC_DIR = PROJECT_ROOT / "frontend" / "dist"


def start_ui_server(
    runs_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    static_dir: Path | None = None,
) -> None:
    assets = static_dir or DEFAULT_STATIC_DIR
    handler = functools.partial(HealthUIRequestHandler, runs_dir=runs_dir, static_dir=assets)
    server = ThreadingHTTPServer((host, port), handler)
    print(
        f"Operator UI listening on http://{host}:{port}/ (runs: {runs_dir}, assets: {assets})",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down operator UI server", file=sys.stderr)
        server.shutdown()
    finally:
        server.server_close()


class HealthUIRequestHandler(BaseHTTPRequestHandler):
    server_version = "HealthUI/2.0"

    def __init__(self, *args: object, runs_dir: Path, static_dir: Path, **kwargs: object) -> None:
        self.runs_dir = runs_dir
        self.static_dir = static_dir
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def do_GET(self) -> None:
        route, _, query = self.path.partition("?")
        if route.startswith("/api/"):
            self._handle_api(route, query)
        elif route == "/artifact":
            self._serve_artifact(query)
        else:
            self._serve_static(route)

    def do_POST(self) -> None:
        route, _, _ = self.path.partition("?")
        if route == "/api/next-check-execution":
            self._handle_next_check_execution()
            return
        if route == "/api/next-check-approval":
            self._handle_next_check_approval()
            return
        self._send_text(404, "Not Found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_api(self, route: str, query: str) -> None:
        context = self._load_context()
        if context is None:
            return
        if route == "/api/run":
            self._send_json(build_run_payload(context))
            return
        if route == "/api/fleet":
            self._send_json(build_fleet_payload(context))
            return
        if route == "/api/proposals":
            self._send_json(build_proposals_payload(context))
            return
        if route == "/api/notifications":
            params = parse_qs(query)
            payload = query_notifications(
                self.runs_dir,
                kind=params.get("kind", [None])[0],
                cluster_label=params.get("cluster_label", [None])[0],
                search=params.get("search", [None])[0],
                limit=self._parse_limit(params.get("limit", [None])[0]),
                page=self._parse_page(params.get("page", [None])[0]),
            )
            self._send_json(payload)
            return
        if route == "/api/cluster-detail":
            params = parse_qs(query)
            label = params.get("cluster_label", [None])[0]
            self._send_json(build_cluster_detail_payload(context, cluster_label=label))
            return
        self._send_text(404, "Not Found")

    def _resolve_plan_candidate(
        self,
        candidates: Sequence[object],
        requested_candidate_id: str | None,
        requested_candidate_index: int | None,
    ) -> tuple[Mapping[str, object] | None, int | None]:
        if not isinstance(candidates, Sequence):
            return None, None
        entries = list(candidates)
        found_entry: Mapping[str, object] | None = None
        found_position: int | None = None
        if requested_candidate_id:
            for idx, entry in enumerate(entries):
                if not isinstance(entry, Mapping):
                    continue
                entry_id = entry.get("candidateId")
                if isinstance(entry_id, str) and entry_id == requested_candidate_id:
                    found_entry = dict(entry)
                    found_position = idx
                    break
        if found_entry is None and requested_candidate_index is not None:
            if 0 <= requested_candidate_index < len(entries):
                entry = entries[requested_candidate_index]
                if isinstance(entry, Mapping):
                    found_entry = dict(entry)
                    found_position = requested_candidate_index
        if found_entry is None:
            return None, None
        candidate_index_value: int | None = None
        explicit_index = found_entry.get("candidateIndex")
        if isinstance(explicit_index, int):
            candidate_index_value = explicit_index
        elif found_position is not None:
            candidate_index_value = found_position
        elif requested_candidate_index is not None:
            candidate_index_value = requested_candidate_index
        return found_entry, candidate_index_value

    def _handle_next_check_execution(self) -> None:
        context = self._load_context()
        if context is None:
            return
        plan = context.run.next_check_plan
        if not plan or not plan.artifact_path:
            self._send_json({"error": "Next-check plan unavailable"}, 400)
            return
        content_length = int(self.headers.get("Content-Length") or 0)
        if content_length <= 0:
            self._send_json({"error": "Request body required"}, 400)
            return
        try:
            raw_payload = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_payload)
        except Exception:
            self._send_json({"error": "Invalid JSON payload"}, 400)
            return
        candidate_index_raw = payload.get("candidateIndex")
        candidate_index = candidate_index_raw if isinstance(candidate_index_raw, int) else None
        if candidate_index_raw is not None and candidate_index is None:
            self._send_json({"error": "candidateIndex must be an integer"}, 400)
            return
        request_cluster = payload.get("clusterLabel")
        if not isinstance(request_cluster, str) or not request_cluster:
            self._send_json({"error": "clusterLabel is required"}, 400)
            return
        plan_path = (self.runs_dir / plan.artifact_path).resolve()
        if not str(plan_path).startswith(str(self.runs_dir.resolve())):
            self._send_json({"error": "Invalid plan artifact path"}, 400)
            return
        if not plan_path.exists():
            self._send_json({"error": "Plan artifact missing"}, 404)
            return
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception:
            self._send_json({"error": "Unable to read plan artifact"}, 500)
            return
        candidate_id_raw = payload.get("candidateId")
        candidate_id = candidate_id_raw if isinstance(candidate_id_raw, str) and candidate_id_raw else None
        if candidate_id is None and candidate_index is None:
            self._send_json({"error": "candidateId or candidateIndex is required"}, 400)
            return
        candidates = plan_data.get("candidates")
        candidate_entry, resolved_index = self._resolve_plan_candidate(
            candidates if isinstance(candidates, Sequence) else (),
            candidate_id,
            candidate_index,
        )
        if candidate_entry is None or resolved_index is None:
            self._send_json({"error": "Candidate not found"}, 400)
            return
        candidate = candidate_entry
        candidate_index = resolved_index
        candidate_view = None
        plan_view = context.run.next_check_plan
        if plan_view:
            for entry in plan_view.candidates:
                if entry.candidate_index == candidate_index:
                    candidate_view = entry
                    break
        if candidate_view:
            enriched_candidate = dict(candidate)
            if candidate_view.approval_status:
                enriched_candidate["approvalStatus"] = candidate_view.approval_status
            if candidate_view.approval_artifact_path:
                enriched_candidate["approvalArtifactPath"] = candidate_view.approval_artifact_path
            if candidate_view.approval_timestamp:
                enriched_candidate["approvalTimestamp"] = candidate_view.approval_timestamp
            candidate = enriched_candidate
        if not isinstance(candidate, Mapping):
            self._send_json({"error": "Invalid candidate record"}, 500)
            return
        target_cluster = candidate.get("targetCluster")
        if not isinstance(target_cluster, str) or not target_cluster:
            self._send_json({"error": "Candidate target cluster missing"}, 400)
            return
        if target_cluster != request_cluster:
            self._send_json({"error": "Candidate target cluster mismatch"}, 400)
            return
        cluster_context = None
        for cluster in context.clusters:
            if cluster.label == target_cluster:
                cluster_context = cluster.context
                break
        if not cluster_context:
            self._send_json({"error": "Cluster context unavailable"}, 400)
            return
        try:
            artifact = execute_manual_next_check(
                runs_dir=self.runs_dir,
                run_id=context.run.run_id,
                run_label=context.run.run_label,
                plan_artifact_path=Path(plan.artifact_path),
                candidate_index=candidate_index,
                candidate=candidate,
                target_context=cluster_context,
                target_cluster=target_cluster,
            )
        except ManualNextCheckError as exc:
            self._send_json({"error": str(exc)}, 400)
            return
        except Exception as exc:  # pragma: no cover - defensive guard
            self._send_json({"error": f"Execution failed: {exc}"}, 500)
            return
        artifact_path = _relative_path(self.runs_dir, artifact.artifact_path)
        payload = {
            "status": artifact.status.value,
            "summary": artifact.summary,
            "artifactPath": artifact_path,
            "durationMs": artifact.duration_ms,
            "command": artifact.payload.get("command") if isinstance(artifact.payload, Mapping) else None,
            "targetCluster": target_cluster,
            "planCandidateIndex": candidate_index,
            "rawOutput": artifact.raw_output,
            "errorSummary": artifact.error_summary,
            "timedOut": artifact.timed_out,
            "stdoutTruncated": artifact.stdout_truncated,
            "stderrTruncated": artifact.stderr_truncated,
            "outputBytesCaptured": artifact.output_bytes_captured,
        }
        self._send_json(payload)

    def _handle_next_check_approval(self) -> None:
        context = self._load_context()
        if context is None:
            return
        plan = context.run.next_check_plan
        if not plan or not plan.artifact_path:
            self._send_json({"error": "Next-check plan unavailable"}, 400)
            return
        content_length = int(self.headers.get("Content-Length") or 0)
        if content_length <= 0:
            self._send_json({"error": "Request body required"}, 400)
            return
        try:
            raw_payload = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_payload)
        except Exception:
            self._send_json({"error": "Invalid JSON payload"}, 400)
            return
        candidate_index_raw = payload.get("candidateIndex")
        candidate_index = candidate_index_raw if isinstance(candidate_index_raw, int) else None
        if candidate_index_raw is not None and candidate_index is None:
            self._send_json({"error": "candidateIndex must be an integer"}, 400)
            return
        request_cluster = payload.get("clusterLabel")
        if not isinstance(request_cluster, str) or not request_cluster:
            self._send_json({"error": "clusterLabel is required"}, 400)
            return
        plan_path = (self.runs_dir / plan.artifact_path).resolve()
        if not str(plan_path).startswith(str(self.runs_dir.resolve())):
            self._send_json({"error": "Invalid plan artifact path"}, 400)
            return
        if not plan_path.exists():
            self._send_json({"error": "Plan artifact missing"}, 404)
            return
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception:
            self._send_json({"error": "Unable to read plan artifact"}, 500)
            return
        candidate_id_raw = payload.get("candidateId")
        candidate_id = candidate_id_raw if isinstance(candidate_id_raw, str) and candidate_id_raw else None
        if candidate_id is None and candidate_index is None:
            self._send_json({"error": "candidateId or candidateIndex is required"}, 400)
            return
        candidates = plan_data.get("candidates")
        candidate_entry, resolved_index = self._resolve_plan_candidate(
            candidates if isinstance(candidates, Sequence) else (),
            candidate_id,
            candidate_index,
        )
        if candidate_entry is None or resolved_index is None:
            self._send_json({"error": "Candidate not found"}, 400)
            return
        candidate = candidate_entry
        raw_candidate_id_value = candidate.get("candidateId")
        candidate_id_value = (
            raw_candidate_id_value if isinstance(raw_candidate_id_value, str) else None
        )
        candidate_index = resolved_index
        target_cluster = candidate.get("targetCluster")
        if target_cluster and target_cluster != request_cluster:
            self._send_json({"error": "Candidate target cluster mismatch"}, 400)
            return
        requires_approval = bool(candidate.get("requiresOperatorApproval"))
        if not requires_approval:
            log_next_check_approval_event(
                severity="WARNING",
                message="Approval rejected because candidate does not require approval",
                run_label=context.run.run_label,
                run_id=context.run.run_id,
                plan_artifact_path=plan.artifact_path,
                candidate_index=candidate_index,
                candidate_description=str(candidate.get("description") or ""),
                target_cluster=request_cluster,
                event="approval-rejected",
            )
            self._send_json({"error": "Candidate does not require approval"}, 400)
            return
        if candidate.get("duplicateOfExistingEvidence"):
            log_next_check_approval_event(
                severity="WARNING",
                message="Approval rejected because candidate duplicates existing evidence",
                run_label=context.run.run_label,
                run_id=context.run.run_id,
                plan_artifact_path=plan.artifact_path,
                candidate_index=candidate_index,
                candidate_description=str(candidate.get("description") or ""),
                target_cluster=request_cluster,
                event="approval-rejected",
            )
            self._send_json({"error": "Candidate duplicates deterministic evidence"}, 400)
            return
        if target_cluster is None and request_cluster and request_cluster not in {cluster.label for cluster in context.clusters}:
            # allow request even if plan candidate lacks explicit target, as long as cluster exists
            pass
        plan_candidate_description = str(candidate.get("description") or "")
        log_next_check_approval_event(
            severity="INFO",
            message="Operator requested approval for next-check candidate",
            run_label=context.run.run_label,
            run_id=context.run.run_id,
            plan_artifact_path=plan.artifact_path,
            candidate_index=candidate_index,
            candidate_id=candidate_id_value,
            candidate_description=plan_candidate_description,
            target_cluster=request_cluster,
            event="approval-requested",
        )
        try:
            artifact = record_next_check_approval(
                runs_dir=self.runs_dir,
                run_id=context.run.run_id,
                run_label=context.run.run_label,
                plan_artifact_path=plan.artifact_path,
                candidate_index=candidate_index,
                candidate_id=candidate_id_value,
                candidate_description=plan_candidate_description,
                target_cluster=request_cluster,
            )
        except Exception as exc:  # pragma: no cover - fail safe
            self._send_json({"error": f"Approval failed: {exc}"}, 500)
            return
        artifact_path = _relative_path(self.runs_dir, artifact.artifact_path)
        response = {
            "status": artifact.status.value,
            "summary": artifact.summary,
            "artifactPath": artifact_path,
            "durationMs": artifact.duration_ms,
            "candidateIndex": candidate_index,
            "approvalTimestamp": artifact.timestamp.isoformat(),
        }
        self._send_json(response)

    def _serve_static(self, route: str) -> None:
        target = route or "/"
        if target.endswith("/"):
            target += "index.html"
        candidate = (self.static_dir / target.lstrip("/")).resolve()
        static_root = self.static_dir.resolve()
        if not str(candidate).startswith(str(static_root)) or not candidate.exists():
            candidate = static_root / "index.html"
            if not candidate.exists():
                self._send_text(404, "Static assets unavailable")
                return
        self._send_file(candidate)

    def _serve_artifact(self, query: str) -> None:
        params = parse_qs(query)
        paths = params.get("path")
        if not paths:
            self._send_text(400, "Artifact path required")
            return
        requested = Path(paths[0])
        try:
            artifact_path = (self.runs_dir / requested).resolve()
        except Exception:  # pragma: no cover - defensive guard
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

    def _load_context(self) -> UIIndexContext | None:
        try:
            index = load_ui_index(self.runs_dir)
            return build_ui_context(index)
        except Exception as exc:  # pragma: no cover - read-model may be malformed
            self._send_text(500, f"Unable to read ui-index.json: {exc}")
            return None

    def _parse_limit(self, value: str | None) -> int | None:
        if not value:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None

    def _parse_page(self, value: str | None) -> int:
        parsed = self._parse_limit(value)
        return parsed if parsed else 1

    def _send_json(self, body: object, code: int = 200) -> None:
        payload = json.dumps(body, ensure_ascii=False)
        encoded = payload.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, path: Path) -> None:
        try:
            data = path.read_bytes()
        except OSError as exc:
            self._send_text(500, f"Unable to read asset: {exc}")
            return
        content_type, _ = mimetypes.guess_type(path.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, code: int, message: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))


def _relative_path(base: Path, target: object | None) -> str | None:
    if target is None:
        return None
    candidate = Path(str(target))
    try:
        return str(candidate.relative_to(base))
    except ValueError:
        return str(candidate)
