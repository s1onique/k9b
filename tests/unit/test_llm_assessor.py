import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, cast
from unittest.mock import patch

import requests

from k8s_diag_agent.cli import main
from k8s_diag_agent.llm.assessor_schema import AssessorAssessment
from k8s_diag_agent.llm.provider import LLMAssessmentInput, LLMProvider
from k8s_diag_agent.llm.llamacpp_provider import LlamaCppProvider, LlamaCppProviderConfig


def _mock_assessment_payload() -> Dict[str, Any]:
    return {
        "observed_signals": [
            {
                "id": "mocked",
                "description": "mocked signal",
                "layer": "observability",
                "evidence_id": "mocked.comparison",
                "severity": "info",
            }
        ],
        "findings": [
            {
                "description": "mocked finding",
                "supporting_signals": ["mocked"],
                "layer": "workload",
            }
        ],
        "hypotheses": [
            {
                "description": "mocked hypothesis",
                "confidence": "low",
                "probable_layer": "workload",
                "what_would_falsify": "mocked falsifier",
            }
        ],
        "next_evidence_to_collect": [
            {
                "description": "mocked check",
                "owner": "platform-engineer",
                "method": "kubectl",
                "evidence_needed": ["mocked evidence"],
            }
        ],
        "recommended_action": {
            "type": "observation",
            "description": "mocked action",
            "references": ["mocked"],
            "safety_level": "low-risk",
        },
        "safety_level": "low-risk",
        "probable_layer_of_origin": "workload",
        "overall_confidence": "low",
    }


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, Dict[str, Any], Dict[str, str], int]] = []

    def post(self, url: str, json: Dict[str, Any], headers: Dict[str, str], timeout: int) -> _FakeResponse:
        self.calls.append((url, json, headers, timeout))
        return self.response


class AssessorSchemaTest(unittest.TestCase):
    def test_from_dict_requires_fields(self) -> None:
        with self.assertRaises(ValueError):
            AssessorAssessment.from_dict({})

    def test_roundtrip_preserves_data(self) -> None:
        payload = {
            "observed_signals": [
                {
                    "id": "sig-1",
                    "description": "Primary metric spike",
                    "layer": "workload",
                    "evidence_id": "evt-1",
                    "severity": "warning",
                }
            ],
            "findings": [
                {
                    "description": "Replica set is starved for CPU.",
                    "supporting_signals": ["sig-1"],
                    "layer": "workload",
                }
            ],
            "hypotheses": [
                {
                    "description": "CPU limit likely too low.",
                    "confidence": "medium",
                    "probable_layer": "workload",
                    "what_would_falsify": "Telemetry shows CPU well below the limit.",
                }
            ],
            "next_evidence_to_collect": [
                {
                    "description": "Gather `kubectl top pod` for the affected pods.",
                    "owner": "platform-engineer",
                    "method": "kubectl",
                    "evidence_needed": ["kubectl top pod"],
                }
            ],
            "recommended_action": {
                "type": "observation",
                "description": "Monitor the pods while gathering CPU metrics.",
                "references": ["sig-1"],
                "safety_level": "low-risk",
            },
            "safety_level": "low-risk",
            "probable_layer_of_origin": "workload",
            "overall_confidence": "medium",
        }
        assessment = AssessorAssessment.from_dict(payload)
        self.assertEqual(assessment.to_dict(), payload)


class LlamaCppProviderTest(unittest.TestCase):
    def _dummy_payload(self) -> LLMAssessmentInput:
        return LLMAssessmentInput(
            primary_snapshot={"foo": "bar"},
            secondary_snapshot={"foo": "baz"},
            comparison={"differences": {}},
            collection_statuses={"primary": {"status": "ok"}, "secondary": {"status": "ok"}},
        )

    def test_builds_openai_request(self) -> None:
        response = _FakeResponse(
            {
                "choices": [
                    {"message": {"content": json.dumps(_mock_assessment_payload())}}
                ]
            }
        )
        session = _FakeSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api", api_key="secret", model="llama-model"
        )
        provider = LlamaCppProvider(config=config, session_factory=lambda: cast(requests.Session, session))
        provider.assess("some prompt", self._dummy_payload())
        self.assertEqual(session.calls[0][0], "http://example.com/api/v1/chat/completions")
        payload = session.calls[0][1]
        self.assertEqual(payload["model"], "llama-model")
        self.assertEqual(payload["temperature"], 0.0)
        self.assertEqual(payload["messages"][1]["content"], "some prompt")
        headers = session.calls[0][2]
        self.assertEqual(headers["Authorization"], "Bearer secret")
        self.assertEqual(session.calls[0][3], 30)

    def test_validates_response_schema(self) -> None:
        response = _FakeResponse({"choices": [{"message": {"content": json.dumps({})}}]})
        session = _FakeSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api", api_key="secret", model="llama-model"
        )
        provider = LlamaCppProvider(config=config, session_factory=lambda: cast(requests.Session, session))
        with self.assertRaises(ValueError):
            provider.assess("prompt", self._dummy_payload())


class RecordingProvider(LLMProvider):
    def __init__(self) -> None:
        self.last_payload = None

    def assess(self, prompt: str, payload: Any) -> dict:
        self.last_payload = payload
        return _mock_assessment_payload()


class LLMCLIWiringTest(unittest.TestCase):
    def test_assess_snapshots_uses_provider_output(self) -> None:
        fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
        primary_path = fixture_dir / "snapshots" / "sanitized-alpha.json"
        secondary_data = json.loads(primary_path.read_text(encoding="utf-8"))
        secondary_data["metadata"]["node_count"] = 4
        secondary_data["metadata"]["pod_count"] = 61
        secondary_data["helm_releases"][0]["chart_version"] = "2.2.0"
        secondary_data["helm_releases"][0]["chart"] = "payments-2.2.0"
        secondary_data["helm_releases"][0]["app_version"] = "2.2.0"
        secondary_data["crds"] = [
            {
                "name": "widgets.example.com",
                "served_versions": ["v1"],
                "storage_version": "v1",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            secondary_path = Path(tmpdir) / "secondary.json"
            secondary_path.write_text(json.dumps(secondary_data), encoding="utf-8")
            provider = RecordingProvider()
            with patch("k8s_diag_agent.cli.get_provider", return_value=provider):
                with patch("sys.stdout", new_callable=io.StringIO) as fake_out:
                    exit_code = main([
                        "assess-snapshots",
                        str(primary_path),
                        str(secondary_path),
                    ])
            self.assertEqual(exit_code, 0)
            assessment = json.loads(fake_out.getvalue())
            self.assertEqual(
                assessment["observed_signals"][0]["id"],
                "mocked",
            )
            self.assertIsNotNone(provider.last_payload)

    def test_assess_snapshots_uses_llamacpp_provider(self) -> None:
        fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
        primary_path = fixture_dir / "snapshots" / "sanitized-alpha.json"
        secondary_data = json.loads(primary_path.read_text(encoding="utf-8"))
        valid_assessment = _mock_assessment_payload()
        response = _FakeResponse({"choices": [{"message": {"content": json.dumps(valid_assessment)}}]})
        session = _FakeSession(response)
        provider = LlamaCppProvider(
            config=LlamaCppProviderConfig(
                base_url="http://localhost", api_key="api-key", model="llama-model"
            ),
            session_factory=lambda: cast(requests.Session, session),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            secondary_path = Path(tmpdir) / "secondary.json"
            secondary_path.write_text(json.dumps(secondary_data), encoding="utf-8")
            with patch.dict(
                "k8s_diag_agent.llm.provider.PROVIDERS",
                {"llamacpp": provider},
                clear=False,
            ):
                with patch("sys.stdout", new_callable=io.StringIO) as fake_out:
                    exit_code = main([
                        "assess-snapshots",
                        str(primary_path),
                        str(secondary_path),
                        "--provider",
                        "llamacpp",
                    ])
        self.assertEqual(exit_code, 0)
        assessment = json.loads(fake_out.getvalue())
        self.assertEqual(assessment, valid_assessment)
        self.assertTrue(session.calls)
