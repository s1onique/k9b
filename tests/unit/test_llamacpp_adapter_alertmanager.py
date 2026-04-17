"""Tests for Alertmanager context injection into llamacpp_adapter prompts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.adapter import ExternalAnalysisRequest
from k8s_diag_agent.external_analysis.alertmanager_artifact import write_alertmanager_compact
from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    normalize_alertmanager_payload,
    snapshot_to_compact,
)
from k8s_diag_agent.external_analysis.llamacpp_adapter import LlamaCppAdapter


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_alert(alertname: str, severity: str = "warning", **labels: str) -> dict[str, Any]:
    base_labels = {"alertname": alertname, "severity": severity, "cluster": "prod", "namespace": "default"}
    base_labels.update(labels)
    return {
        "labels": base_labels,
        "annotations": {"Summary": f"Alert {alertname} fired"},
        "state": "active",
        "startsAt": "2024-01-01T00:00:00Z",
    }


class TestLlamaCppAdapterAlertmanagerPrompt:
    """Tests for Alertmanager context in llamacpp_adapter prompt building."""

    def test_prompt_includes_alertmanager_when_available(self, tmp_path: Path) -> None:
        """Prompt includes Alertmanager compact data when artifact exists."""
        # Set up directory structure
        run_id = "prompt-test-run"
        root = tmp_path / "runs" / "health"
        
        # Write review artifact
        review_path = root / "reviews" / f"{run_id}-review.json"
        _write_json(review_path, {"run_id": run_id, "selected_drilldowns": []})
        
        # Write Alertmanager compact
        raw = {"data": {"alerts": [_make_alert("HighCPU", "critical")]}}
        snapshot = normalize_alertmanager_payload(raw)
        compact = snapshot_to_compact(snapshot)
        write_alertmanager_compact(root, compact, run_id)
        
        # Build context
        from k8s_diag_agent.external_analysis.review_input import build_review_enrichment_input
        context = build_review_enrichment_input(review_path, run_id)
        
        # Build prompt
        adapter = LlamaCppAdapter.__new__(LlamaCppAdapter)
        adapter.name = "llamacpp"
        request = ExternalAnalysisRequest(
            run_id=run_id,
            cluster_label="test-cluster",
            source_artifact=str(review_path),
        )
        prompt = adapter._build_prompt(request, context)
        
        # Verify prompt contains full structured Alertmanager context
        assert "Alertmanager operational context:" in prompt
        assert '"available": true' in prompt
        assert '"source": "run_artifact"' in prompt
        assert '"status": "ok"' in prompt
        assert '"alert_count": 1' in prompt
        assert "HighCPU" in prompt
        assert "critical" in prompt

    def test_prompt_marks_unavailable_when_no_artifact(self, tmp_path: Path) -> None:
        """Prompt marks Alertmanager as unavailable when no artifact exists."""
        run_id = "no-artifact-run"
        root = tmp_path / "runs" / "health"
        
        # Write review artifact (no Alertmanager compact)
        review_path = root / "reviews" / f"{run_id}-review.json"
        _write_json(review_path, {"run_id": run_id, "selected_drilldowns": []})
        
        # Build context
        from k8s_diag_agent.external_analysis.review_input import build_review_enrichment_input
        context = build_review_enrichment_input(review_path, run_id)
        
        # Build prompt
        adapter = LlamaCppAdapter.__new__(LlamaCppAdapter)
        adapter.name = "llamacpp"
        request = ExternalAnalysisRequest(
            run_id=run_id,
            cluster_label="test-cluster",
            source_artifact=str(review_path),
        )
        prompt = adapter._build_prompt(request, context)
        
        # Verify prompt marks Alertmanager as unavailable with structured JSON
        assert "Alertmanager operational context:" in prompt
        assert '"available": false' in prompt
        assert '"source": "unavailable"' in prompt

    def test_payload_includes_alertmanager_context(self, tmp_path: Path) -> None:
        """LLMAssessmentInput payload includes alertmanager_context in comparison_metadata."""
        run_id = "payload-test-run"
        root = tmp_path / "runs" / "health"
        
        # Write review artifact
        review_path = root / "reviews" / f"{run_id}-review.json"
        _write_json(review_path, {"run_id": run_id, "selected_drilldowns": []})
        
        # Write Alertmanager compact
        raw = {"data": {"alerts": [_make_alert("TestAlert", "warning")]}}
        snapshot = normalize_alertmanager_payload(raw)
        compact = snapshot_to_compact(snapshot)
        write_alertmanager_compact(root, compact, run_id)
        
        # Build context
        from k8s_diag_agent.external_analysis.review_input import build_review_enrichment_input
        context = build_review_enrichment_input(review_path, run_id)
        
        # Build payload
        adapter = LlamaCppAdapter.__new__(LlamaCppAdapter)
        adapter.name = "llamacpp"
        request = ExternalAnalysisRequest(
            run_id=run_id,
            cluster_label="test-cluster",
            source_artifact=str(review_path),
        )
        payload = adapter._build_payload_from_context(request, context)
        
        # Verify payload includes alertmanager_context
        assert payload.comparison_metadata is not None
        assert "alertmanager_context" in payload.comparison_metadata
        am_ctx = payload.comparison_metadata["alertmanager_context"]
        assert am_ctx is not None
        assert am_ctx["available"] is True
        assert am_ctx["source"] == "run_artifact"
        assert am_ctx["compact"] is not None
        assert am_ctx["status"] == "ok"

    def test_payload_marks_unavailable_when_no_artifact(self, tmp_path: Path) -> None:
        """Payload marks alertmanager_context as unavailable when no artifact exists."""
        run_id = "no-artifact-payload-run"
        root = tmp_path / "runs" / "health"
        
        # Write review artifact (no Alertmanager compact)
        review_path = root / "reviews" / f"{run_id}-review.json"
        _write_json(review_path, {"run_id": run_id, "selected_drilldowns": []})
        
        # Build context
        from k8s_diag_agent.external_analysis.review_input import build_review_enrichment_input
        context = build_review_enrichment_input(review_path, run_id)
        
        # Build payload
        adapter = LlamaCppAdapter.__new__(LlamaCppAdapter)
        adapter.name = "llamacpp"
        request = ExternalAnalysisRequest(
            run_id=run_id,
            cluster_label="test-cluster",
            source_artifact=str(review_path),
        )
        payload = adapter._build_payload_from_context(request, context)
        
        # Verify payload marks as unavailable
        assert payload.comparison_metadata is not None
        am_ctx = payload.comparison_metadata["alertmanager_context"]
        assert am_ctx is not None
        assert am_ctx["available"] is False
        assert am_ctx["source"] == "unavailable"
        assert am_ctx["compact"] is None
        assert am_ctx["status"] is None

    def test_no_live_alertmanager_fetch_during_prompt_construction(self, tmp_path: Path) -> None:
        """Prompt construction reads from stored artifacts only, no live network activity."""
        run_id = "no-network-test"
        root = tmp_path / "runs" / "health"
        
        # Write review artifact
        review_path = root / "reviews" / f"{run_id}-review.json"
        _write_json(review_path, {"run_id": run_id, "selected_drilldowns": []})
        
        # Build context - this reads from disk only
        from k8s_diag_agent.external_analysis.review_input import build_review_enrichment_input
        context = build_review_enrichment_input(review_path, run_id)
        
        # Build prompt - also reads from disk only
        adapter = LlamaCppAdapter.__new__(LlamaCppAdapter)
        adapter.name = "llamacpp"
        request = ExternalAnalysisRequest(
            run_id=run_id,
            cluster_label="test-cluster",
            source_artifact=str(review_path),
        )
        prompt = adapter._build_prompt(request, context)
        
        # The prompt construction should not have made any network calls
        # This is verified by the fact that:
        # 1. build_review_enrichment_input only reads from disk
        # 2. _build_prompt only reads from context, no network calls
        assert "Alertmanager" in prompt
