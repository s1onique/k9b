import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, cast
from unittest.mock import patch

import requests

from k8s_diag_agent.cli import main
from k8s_diag_agent.llm.assessor_schema import AssessorAssessment
from k8s_diag_agent.llm.provider import LLMAssessmentInput, LLMProvider
from k8s_diag_agent.llm.llamacpp_provider import LlamaCppProvider, LlamaCppProviderConfig
from k8s_diag_agent.llm.prompts import build_assessment_prompt
from k8s_diag_agent.collect.cluster_snapshot import (
    CollectionStatus,
    ClusterSnapshot,
    ClusterSnapshotMetadata,
    CRDRecord,
    HelmReleaseRecord,
)
from k8s_diag_agent.compare.two_cluster import compare_snapshots


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
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _FakeSession:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[tuple[str, Dict[str, Any], Dict[str, str], int]] = []

    def post(self, url: str, json: Dict[str, Any], headers: Dict[str, str], timeout: int) -> Any:
        self.calls.append((url, json, headers, timeout))
        return self.response


class _FakeHttpErrorResponse(requests.Response):
    def __init__(self, status_code: int, reason: str, text: str) -> None:
        super().__init__()
        self.status_code = status_code
        self.reason = reason
        self._content = text.encode("utf-8")
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        raise requests.HTTPError("http error", response=self)



class _RaisingSession:
    def __init__(self, error: requests.RequestException) -> None:
        self.error = error
        self.calls: list[str] = []

    def post(self, url: str, json: Dict[str, Any], headers: Dict[str, str], timeout: int) -> Any:
        self.calls.append(url)
        raise self.error


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

    def test_observed_signals_entries_require_objects(self) -> None:
        payload = _mock_assessment_payload()
        payload["observed_signals"] = ["bad string"]
        with self.assertRaises(ValueError) as ctx:
            AssessorAssessment.from_dict(payload)
        message = str(ctx.exception)
        self.assertIn("observed_signals[0]", message)
        self.assertIn("str", message)

    def test_findings_entries_require_objects(self) -> None:
        payload = _mock_assessment_payload()
        payload["findings"] = ["bad string"]
        with self.assertRaises(ValueError) as ctx:
            AssessorAssessment.from_dict(payload)
        message = str(ctx.exception)
        self.assertIn("findings[0]", message)
        self.assertIn("str", message)

    def test_hypotheses_entries_require_objects(self) -> None:
        payload = _mock_assessment_payload()
        payload["hypotheses"] = ["bad string"]
        with self.assertRaises(ValueError) as ctx:
            AssessorAssessment.from_dict(payload)
        message = str(ctx.exception)
        self.assertIn("hypotheses[0]", message)
        self.assertIn("str", message)

    def test_next_checks_entries_require_objects(self) -> None:
        payload = _mock_assessment_payload()
        payload["next_evidence_to_collect"] = ["bad string"]
        with self.assertRaises(ValueError) as ctx:
            AssessorAssessment.from_dict(payload)
        message = str(ctx.exception)
        self.assertIn("next_evidence_to_collect[0]", message)
        self.assertIn("str", message)

    def test_recommended_action_must_be_object(self) -> None:
        payload = _mock_assessment_payload()
        payload["recommended_action"] = "bad string"
        with self.assertRaises(ValueError) as ctx:
            AssessorAssessment.from_dict(payload)
        message = str(ctx.exception)
        self.assertIn("recommended_action", message)
        self.assertIn("str", message)


class PromptBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        metadata_primary = ClusterSnapshotMetadata(
            cluster_id="cluster-a",
            captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            control_plane_version="1.26.0",
            node_count=3,
            pod_count=20,
            region="europe",
            labels={"env": "prod"},
        )
        metadata_secondary = ClusterSnapshotMetadata(
            cluster_id="cluster-a",
            captured_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            control_plane_version="1.26.0",
            node_count=4,
            pod_count=25,
            region="europe",
            labels={"env": "prod"},
        )
        self.primary_snapshot = ClusterSnapshot(
            metadata=metadata_primary,
            helm_releases={
                "default/payments": HelmReleaseRecord(
                    name="payments",
                    namespace="default",
                    chart="payments",
                    chart_version="1.0.0",
                    app_version="1.0.0",
                )
            },
            crds={
                "widgets.example.com": CRDRecord(
                    name="widgets.example.com",
                    served_versions=("v1",),
                    storage_version="v1",
                )
            },
            collection_status=CollectionStatus(helm_error=None, missing_evidence=("logs",)),
        )
        self.secondary_snapshot = ClusterSnapshot(
            metadata=metadata_secondary,
            helm_releases={
                "default/payments": HelmReleaseRecord(
                    name="payments",
                    namespace="default",
                    chart="payments",
                    chart_version="1.1.0",
                    app_version="1.1.0",
                )
            },
            crds={
                "widgets.example.com": CRDRecord(
                    name="widgets.example.com",
                    served_versions=("v1", "v2"),
                    storage_version="v2",
                )
            },
            collection_status=CollectionStatus(helm_error="helm timeout", missing_evidence=()),
        )

    def test_build_assessment_prompt_compacts_and_logs(self) -> None:
        comparison = compare_snapshots(self.primary_snapshot, self.secondary_snapshot)
        with self.assertLogs("k8s_diag_agent.llm.prompts", level="INFO") as cm:
            prompt = build_assessment_prompt(
                self.primary_snapshot, self.secondary_snapshot, comparison
            )
        self.assertIn("Helm release changes (count: 1)", prompt)
        self.assertIn("CRD differences (count: 1)", prompt)
        self.assertIn("\"node_count\"", prompt)
        log_output = " ".join(cm.output)
        self.assertIn("helm_diffs=1", log_output)
        self.assertIn("crd_diffs=1", log_output)
        self.assertIn("prompt_chars=", log_output)


class LlamaCppProviderTest(unittest.TestCase):
    def _dummy_payload(self) -> LLMAssessmentInput:
        return LLMAssessmentInput(
            primary_snapshot={"foo": "bar"},
            secondary_snapshot={"foo": "baz"},
            comparison={"differences": {}},
            collection_statuses={"primary": {"status": "ok"}, "secondary": {"status": "ok"}},
        )

    def _assert_schema_error_includes_field(self, field: str) -> None:
        assessment = _mock_assessment_payload()
        assessment[field] = ["bad string"]
        response = _FakeResponse({"choices": [{"message": {"content": json.dumps(assessment)}}]})
        session = _FakeSession(response)
        provider = LlamaCppProvider(
            config=LlamaCppProviderConfig(
                base_url="http://example.com/api",
                api_key="secret",
                model="llama-model",
            ),
            session_factory=lambda: cast(requests.Session, session),
        )
        with self.assertRaises(ValueError) as ctx:
            provider.assess("prompt", self._dummy_payload())
        message = str(ctx.exception)
        self.assertIn("Assessor schema validation failed", message)
        self.assertIn(field, message)
        self.assertIn('["bad string"]', message)
        self.assertIn("assessment snippet", message)

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
        self.assertEqual(session.calls[0][3], 90)

    def test_request_headers_skip_authorization_without_api_key(self) -> None:
        response = _FakeResponse(
            {
                "choices": [
                    {"message": {"content": json.dumps(_mock_assessment_payload())}}
                ]
            }
        )
        session = _FakeSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api", model="llama-model", api_key=""
        )
        provider = LlamaCppProvider(config=config, session_factory=lambda: cast(requests.Session, session))
        provider.assess("some prompt", self._dummy_payload())
        headers = session.calls[0][2]
        self.assertNotIn("Authorization", headers)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Accept"], "application/json")

    def test_uses_configured_timeout(self) -> None:
        response = _FakeResponse(
            {
                "choices": [
                    {"message": {"content": json.dumps(_mock_assessment_payload())}}
                ]
            }
        )
        session = _FakeSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api", model="llama-model", timeout_seconds=120
        )
        provider = LlamaCppProvider(config=config, session_factory=lambda: cast(requests.Session, session))
        provider.assess("some prompt", self._dummy_payload())
        self.assertEqual(session.calls[0][3], 120)

    def test_timeout_error_includes_timeout_and_endpoint(self) -> None:
        error = requests.Timeout("read timed out")
        session = _RaisingSession(error)
        config = LlamaCppProviderConfig(base_url="http://example.com/api", model="llama-model")
        provider = LlamaCppProvider(config=config, session_factory=lambda: cast(requests.Session, session))
        with self.assertRaises(RuntimeError) as ctx:
            provider.assess("prompt", self._dummy_payload())
        message = str(ctx.exception)
        self.assertIn("Endpoint http://example.com/api/v1/chat/completions", message)
        self.assertIn("timeout=90s", message)

    def test_validates_response_schema(self) -> None:
        response = _FakeResponse({"choices": [{"message": {"content": json.dumps({})}}]})
        session = _FakeSession(response)
        config = LlamaCppProviderConfig(
            base_url="http://example.com/api", api_key="secret", model="llama-model"
        )
        provider = LlamaCppProvider(config=config, session_factory=lambda: cast(requests.Session, session))
        with self.assertRaises(ValueError):
            provider.assess("prompt", self._dummy_payload())

    def test_observed_signals_schema_error_reports_snippet(self) -> None:
        self._assert_schema_error_includes_field("observed_signals")

    def test_findings_schema_error_reports_snippet(self) -> None:
        self._assert_schema_error_includes_field("findings")

    def test_hypotheses_schema_error_reports_snippet(self) -> None:
        self._assert_schema_error_includes_field("hypotheses")

    def test_accepts_message_as_raw_string(self) -> None:
        assessment = _mock_assessment_payload()
        response = _FakeResponse({"choices": [{"message": json.dumps(assessment)}]})
        session = _FakeSession(response)
        provider = LlamaCppProvider(
            config=LlamaCppProviderConfig(
                base_url="http://example.com/api", api_key="secret", model="llama-model"
            ),
            session_factory=lambda: cast(requests.Session, session),
        )
        returned = provider.assess("prompt", self._dummy_payload())
        self.assertEqual(returned, assessment)

    def test_accepts_text_field_when_message_missing(self) -> None:
        assessment = _mock_assessment_payload()
        response = _FakeResponse({"choices": [{"text": json.dumps(assessment)}]})
        session = _FakeSession(response)
        provider = LlamaCppProvider(
            config=LlamaCppProviderConfig(
                base_url="http://example.com/api", api_key="secret", model="llama-model"
            ),
            session_factory=lambda: cast(requests.Session, session),
        )
        returned = provider.assess("prompt", self._dummy_payload())
        self.assertEqual(returned, assessment)

    def test_choice_not_dict_reports_type_and_snippet(self) -> None:
        payload = {"choices": ["broken"], "unexpected": True}
        response = _FakeResponse(payload)
        session = _FakeSession(response)
        provider = LlamaCppProvider(
            config=LlamaCppProviderConfig(
                base_url="http://example.com/api", api_key="secret", model="llama-model"
            ),
            session_factory=lambda: cast(requests.Session, session),
        )
        with self.assertRaises(ValueError) as ctx:
            provider.assess("prompt", self._dummy_payload())
        message = str(ctx.exception)
        self.assertIn("choices[0]", message)
        self.assertIn("str", message)
        self.assertIn("response snippet", message)
        self.assertIn(json.dumps(payload), message)

    def test_extract_assessment_rejects_top_level_string(self) -> None:
        provider = LlamaCppProvider(
            config=LlamaCppProviderConfig(
                base_url="http://example.com/api", api_key="secret", model="llama-model"
            ),
            session_factory=lambda: cast(requests.Session, _FakeSession(_FakeResponse({}))),
        )
        with self.assertRaises(ValueError) as ctx:
            provider._extract_assessment("plain string response")
        message = str(ctx.exception)
        self.assertIn("llama.cpp response expected an object but got str", message)
        self.assertIn('response snippet: "plain string response"', message)

    def test_assess_reports_top_level_string(self) -> None:
        response = _FakeResponse("plain string response")
        session = _FakeSession(response)
        provider = LlamaCppProvider(
            config=LlamaCppProviderConfig(
                base_url="http://example.com/api", api_key="secret", model="llama-model"
            ),
            session_factory=lambda: cast(requests.Session, session),
        )
        with self.assertRaises(ValueError) as ctx:
            provider.assess("prompt", self._dummy_payload())
        message = str(ctx.exception)
        self.assertIn("llama.cpp response expected an object but got str", message)
        self.assertIn('response snippet: "plain string response"', message)

    def test_http_error_includes_status_body_and_endpoint(self) -> None:
        response = _FakeHttpErrorResponse(
            status_code=404,
            reason="Not Found",
            text="error detail snippet that reveals the issue",
        )
        session = _FakeSession(response)
        config = LlamaCppProviderConfig(
            base_url="https://example.com/v1", api_key="secret", model="llama-model"
        )
        provider = LlamaCppProvider(config=config, session_factory=lambda: cast(requests.Session, session))
        with self.assertRaises(RuntimeError) as ctx:
            provider.assess("prompt", self._dummy_payload())
        message = str(ctx.exception)
        self.assertIn("Endpoint https://example.com/v1/v1/chat/completions", message)
        self.assertIn("Base URL already includes '/v1'", message)
        self.assertIn("HTTP 404 Not Found", message)
        self.assertIn("Response snippet: error detail snippet", message)

    def test_connection_error_includes_exception_details(self) -> None:
        error = requests.ConnectionError("failed to reach the llama.cpp service")
        session = _RaisingSession(error)
        config = LlamaCppProviderConfig(base_url="http://example.com/api", model="llama-model")
        provider = LlamaCppProvider(config=config, session_factory=lambda: cast(requests.Session, session))
        with self.assertRaises(RuntimeError) as ctx:
            provider.assess("prompt", self._dummy_payload())
        message = str(ctx.exception)
        self.assertIn("Endpoint http://example.com/api/v1/chat/completions", message)
        self.assertIn("ConnectionError: failed to reach the llama.cpp service", message)


class LlamaCppProviderConfigTest(unittest.TestCase):
    def test_from_env_allows_missing_api_key(self) -> None:
        env = {
            "LLAMA_CPP_BASE_URL": "https://example.com",
            "LLAMA_CPP_MODEL": "llama-model",
        }
        config = LlamaCppProviderConfig.from_env(env=env)
        self.assertEqual(config.base_url, "https://example.com")
        self.assertEqual(config.model, "llama-model")
        self.assertIsNone(config.api_key)

    def test_from_env_discards_blank_api_key(self) -> None:
        env = {
            "LLAMA_CPP_BASE_URL": "https://example.com",
            "LLAMA_CPP_MODEL": "llama-model",
            "LLAMA_CPP_API_KEY": "   ",
        }
        config = LlamaCppProviderConfig.from_env(env=env)
        self.assertIsNone(config.api_key)

    def test_from_env_parses_timeout_seconds(self) -> None:
        env = {
            "LLAMA_CPP_BASE_URL": "https://example.com",
            "LLAMA_CPP_MODEL": "llama-model",
            "LLAMA_CPP_TIMEOUT_SECONDS": "120",
        }
        config = LlamaCppProviderConfig.from_env(env=env)
        self.assertEqual(config.timeout_seconds, 120)

    def test_from_env_rejects_invalid_timeout(self) -> None:
        env = {
            "LLAMA_CPP_BASE_URL": "https://example.com",
            "LLAMA_CPP_MODEL": "llama-model",
            "LLAMA_CPP_TIMEOUT_SECONDS": "fast",
        }
        with self.assertRaises(ValueError):
            LlamaCppProviderConfig.from_env(env=env)


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
