"""Entrypoint for operational + evaluation feedback runs."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ..collect.cluster_snapshot import ClusterSnapshot, CollectionStatus
from ..collect.live_snapshot import collect_cluster_snapshot, list_kube_contexts
from ..compare.two_cluster import (
    ClusterComparison,
    ComparisonIntentMetadata,
    compare_snapshots,
)
from ..llm.assessor_schema import AssessorAssessment
from ..llm.prompts import build_assessment_prompt
from ..llm.provider import (
    DEFAULT_PROVIDER_NAME,
    LLMProvider,
    build_assessment_input,
    get_provider,
)
from .models import (
    AssessmentArtifact,
    FailureMode,
    RunArtifact,
    SnapshotPairArtifact,
    ValidationResult,
)

_LABEL_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _safe_label(value: str) -> str:
    cleaned = _LABEL_RE.sub("-", value or "")
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.strip("-")
    result = cleaned.lower() or "entry"
    return result


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_category_list(value: object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        normalized = _normalize_text(value)
        return (normalized,) if normalized else ()
    if isinstance(value, list | tuple):
        categories: list[str] = []
        for item in value:
            normalized = _normalize_text(item)
            if normalized:
                categories.append(normalized)
        return tuple(categories)
    raise ValueError("drift categories must be a string or list of strings")


def _write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _to_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _serialize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return _to_iso(value)


def _serialize_run_artifact(artifact: RunArtifact) -> dict[str, Any]:
    data = asdict(artifact)
    return {key: _serialize_value(value) for key, value in data.items()}


@dataclass(frozen=True)
class FeedbackTarget:
    context: str
    label: str
    output: Path | None


_DEFAULT_COMPARISON_METADATA = ComparisonIntentMetadata(None, (), (), None)


@dataclass(frozen=True)
class FeedbackPair:
    primary: str
    secondary: str
    label: str
    assess: bool
    comparison_metadata: ComparisonIntentMetadata = _DEFAULT_COMPARISON_METADATA


@dataclass(frozen=True)
class FeedbackRunConfig:
    run_id: str
    targets: tuple[FeedbackTarget, ...]
    pairs: tuple[FeedbackPair, ...]
    output_dir: Path
    provider: str | None
    collector_version: str

    @classmethod
    def load(cls, path: Path) -> FeedbackRunConfig:
        raw = json.loads(path.read_text(encoding="utf-8"))
        run_id = str(raw.get("run_id") or _safe_label(path.stem))
        output_dir = Path(str(raw.get("output_dir") or "runs"))
        provider = raw.get("provider")
        provider_value: str | None
        if provider is None:
            provider_value = DEFAULT_PROVIDER_NAME
        else:
            provider_value = str(provider).strip() or None
        collector_version = str(raw.get("collector_version") or "dev")

        targets_raw = raw.get("targets")
        if not isinstance(targets_raw, list):
            raise ValueError("`targets` must be a list")
        targets: list[FeedbackTarget] = []
        for entry in targets_raw:
            if not isinstance(entry, dict):
                continue
            context = entry.get("context")
            if not context:
                continue
            label = _safe_label(entry.get("label") or str(context))
            output_value = entry.get("output")
            output_path = Path(str(output_value)) if output_value else None
            targets.append(FeedbackTarget(context=str(context), label=label, output=output_path))
        if not targets:
            raise ValueError("`targets` must specify at least one context")

        valid_names = {target.context for target in targets} | {target.label for target in targets}
        pairs_raw = raw.get("pairs")
        if not isinstance(pairs_raw, list):
            raise ValueError("`pairs` must be a list")
        pairs: list[FeedbackPair] = []
        for entry in pairs_raw:
            if not isinstance(entry, dict):
                continue
            primary = entry.get("primary")
            secondary = entry.get("secondary")
            if not primary or not secondary:
                continue
            if str(primary) not in valid_names or str(secondary) not in valid_names:
                raise ValueError(f"Pair references unknown context: {primary} vs {secondary}")
            label = _safe_label(entry.get("label") or f"{primary}-vs-{secondary}")
            assess_flag = bool(entry.get("assess", True))
            intent = _normalize_text(entry.get("intent"))
            notes = _normalize_text(entry.get("notes") or entry.get("role_description"))
            expected_categories = _parse_category_list(entry.get("expected_drift_categories"))
            unexpected_categories = _parse_category_list(entry.get("unexpected_drift_categories"))
            metadata = ComparisonIntentMetadata(
                intent=intent,
                expected_drift_categories=expected_categories,
                unexpected_drift_categories=unexpected_categories,
                notes=notes,
            )
            pairs.append(
                FeedbackPair(
                    primary=str(primary),
                    secondary=str(secondary),
                    label=label,
                    assess=assess_flag,
                    comparison_metadata=metadata,
                )
            )
        if not pairs:
            raise ValueError("`pairs` must specify at least one comparison pair")
        return cls(
            run_id=run_id,
            targets=tuple(targets),
            pairs=tuple(pairs),
            output_dir=output_dir,
            provider=provider_value,
            collector_version=collector_version,
        )


class SnapshotRecord:
    def __init__(self, target: FeedbackTarget, snapshot: ClusterSnapshot, path: Path) -> None:
        self.target = target
        self.snapshot = snapshot
        self.path = path
        self.status: CollectionStatus = snapshot.collection_status


class FeedbackRunRunner:
    def __init__(
        self,
        config: FeedbackRunConfig,
        available_contexts: Iterable[str],
        probe_provider: str | None = None,
        quiet: bool = False,
    ) -> None:
        self.config = config
        self.available_contexts = set(available_contexts)
        self.provider_name = probe_provider or config.provider
        self.quiet = quiet
        self._provider_instance: LLMProvider | None = None
        self._provider_error: str | None = None
        self._collection_messages: list[str] = []
        self._collection_issues: list[str] = []

    def execute(self) -> list[RunArtifact]:
        directories = self._ensure_directories()
        records = self._collect_snapshots(directories["snapshots"])
        artifacts: list[RunArtifact] = []
        for pair in self.config.pairs:
            artifact = self._process_pair(pair, records, directories)
            if artifact:
                artifacts.append(artifact)
        if not self.quiet:
            print(
                f"Feedback run '{self.config.run_id}' produced {len(artifacts)} artifact(s).",
            )
            for message in self._collection_messages:
                print(message)
        return artifacts

    def _ensure_directories(self) -> dict[str, Path]:
        directories: dict[str, Path] = {}
        for subdir in ("snapshots", "comparisons", "assessments", "feedback"):
            path = self.config.output_dir / subdir
            path.mkdir(parents=True, exist_ok=True)
            directories[subdir] = path
        return directories

    def _collect_snapshots(self, snapshot_dir: Path) -> dict[str, SnapshotRecord]:
        records: dict[str, SnapshotRecord] = {}
        for target in self.config.targets:
            if target.context not in self.available_contexts:
                message = f"Context '{target.context}' not available; skipping snapshot."
                self._collection_messages.append(message)
                self._collection_issues.append(message)
                continue
            path = target.output or (snapshot_dir / f"{self.config.run_id}-{target.label}.json")
            try:
                snapshot = collect_cluster_snapshot(target.context)
            except RuntimeError as exc:
                message = f"Snapshot for '{target.context}' failed: {exc}"
                self._collection_messages.append(message)
                self._collection_issues.append(message)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(snapshot.to_dict(), path)
            records[target.context] = SnapshotRecord(target=target, snapshot=snapshot, path=path)
            self._collection_messages.append(f"Collected snapshot for '{target.context}' -> {path}")
        return records

    def _process_pair(
        self,
        pair: FeedbackPair,
        records: dict[str, SnapshotRecord],
        directories: dict[str, Path],
    ) -> RunArtifact | None:
        primary = self._lookup_record(pair.primary, records)
        secondary = self._lookup_record(pair.secondary, records)
        if not primary or not secondary:
            return None
        comparison = compare_snapshots(
            primary.snapshot, secondary.snapshot, metadata=pair.comparison_metadata
        )
        comparison_path = directories["comparisons"] / f"{self.config.run_id}-{pair.label}-diff.json"
        _write_json({"differences": comparison.differences}, comparison_path)
        snapshot_pair = SnapshotPairArtifact(
            primary_snapshot_id=primary.snapshot.metadata.cluster_id,
            primary_snapshot_path=str(primary.path),
            secondary_snapshot_id=secondary.snapshot.metadata.cluster_id,
            secondary_snapshot_path=str(secondary.path),
            comparison_summary={
                key: len(value) for key, value in comparison.differences.items()
            },
            status="complete",
            missing_evidence=self._collect_missing_evidence(primary, secondary),
        )
        assessment_data, assessment_issue = self._run_assessment(pair, primary, secondary, comparison)
        assessment_artifact = None
        validation_results: list[ValidationResult] = []
        failure_modes: list[FailureMode] = []
        if assessment_data is not None:
            assessment_artifact = AssessmentArtifact(
                assessment_id=f"{self.config.run_id}-{pair.label}",
                schema_version="assessment-schema:v1",
                assessment=assessment_data,
                overall_confidence=assessment_data.get("overall_confidence"),
            )
            parsed, parse_error = self._parse_assessment(assessment_data)
            if parse_error:
                validation_results.append(
                    ValidationResult(
                        name="schema-check",
                        passed=False,
                        errors=[parse_error],
                        failure_mode=FailureMode.INVALID_ARTIFACT,
                    )
                )
                failure_modes.append(FailureMode.INVALID_ARTIFACT)
            else:
                assert parsed is not None
                validation_results.extend(self._score_assessment(parsed, assessment_data, snapshot_pair))
        elif assessment_issue:
            failure_modes.append(FailureMode.LLM_ERROR)
            validation_results.append(
                ValidationResult(
                    name="llm-assessment",
                    passed=False,
                    errors=[assessment_issue],
                    failure_mode=FailureMode.LLM_ERROR,
                )
            )
        run_artifact = RunArtifact(
            run_id=self.config.run_id,
            timestamp=datetime.now(UTC),
            context_name=pair.label,
            comparison_intent=pair.comparison_metadata.intent,
            comparison_notes=pair.comparison_metadata.notes,
            expected_drift_categories=pair.comparison_metadata.expected_drift_categories,
            unexpected_drift_categories=pair.comparison_metadata.unexpected_drift_categories,
            collector_version=self.config.collector_version,
            collection_status=self._collection_status(snapshot_pair),
            snapshot_pair=snapshot_pair,
            comparison_summary=snapshot_pair.comparison_summary,
            missing_evidence=snapshot_pair.missing_evidence,
            assessment=assessment_artifact,
            validation_results=validation_results,
            failure_modes=failure_modes,
            proposed_improvements=[],
        )
        artifact_path = directories["feedback"] / f"{self.config.run_id}-{pair.label}.json"
        _write_json(_serialize_run_artifact(run_artifact), artifact_path)
        if assessment_artifact:
            assessment_path = directories["assessments"] / f"{self.config.run_id}-{pair.label}-assessment.json"
            _write_json(assessment_artifact.assessment, assessment_path)
        return run_artifact

    def _lookup_record(self, key: str, records: dict[str, SnapshotRecord]) -> SnapshotRecord | None:
        if key in records:
            return records[key]
        for record in records.values():
            if key == record.target.label:
                return record
        return None

    def _collect_missing_evidence(self, primary: SnapshotRecord, secondary: SnapshotRecord) -> list[str]:
        missing: list[str] = []
        missing.extend(primary.status.missing_evidence)
        missing.extend(secondary.status.missing_evidence)
        return missing

    def _collection_status(self, snapshot_pair: SnapshotPairArtifact) -> str:
        if snapshot_pair.missing_evidence or self._collection_issues:
            return "partial"
        return "complete"

    def _parse_assessment(
        self, assessment_data: dict[str, Any]
    ) -> tuple[AssessorAssessment | None, str | None]:
        try:
            parsed = AssessorAssessment.from_dict(assessment_data)
            return parsed, None
        except ValueError as exc:
            return None, str(exc)

    def _score_assessment(
        self, parsed: AssessorAssessment, raw: dict[str, Any], snapshot_pair: SnapshotPairArtifact
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        results.append(ValidationResult(name="schema-check", passed=True))
        missing_ok = len(snapshot_pair.missing_evidence) == 0
        results.append(
            ValidationResult(
                name="missing-evidence-check",
                passed=missing_ok,
                errors=[] if missing_ok else ["missing evidence detected"],
                failure_mode=FailureMode.MISSING_EVIDENCE if not missing_ok else None,
            )
        )
        confidence_present = bool(raw.get("overall_confidence"))
        results.append(
            ValidationResult(
                name="confidence-present",
                passed=confidence_present,
                errors=[] if confidence_present else ["overall_confidence missing"],
                failure_mode=FailureMode.OTHER if not confidence_present else None,
            )
        )
        safety_present = bool(raw.get("safety_level"))
        results.append(
            ValidationResult(
                name="safety-level-present",
                passed=safety_present,
                errors=[] if safety_present else ["safety_level missing"],
                failure_mode=FailureMode.OTHER if not safety_present else None,
            )
        )
        return results

    def _run_assessment(
        self,
        pair: FeedbackPair,
        primary: SnapshotRecord,
        secondary: SnapshotRecord,
        comparison: ClusterComparison,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not pair.assess:
            return None, None
        provider = self._get_provider_instance()
        if not provider:
            return None, self._provider_error or "provider unavailable"
        prompt = build_assessment_prompt(
            primary.snapshot,
            secondary.snapshot,
            comparison,
            intent_metadata=comparison.metadata,
        )
        payload = build_assessment_input(primary.snapshot, secondary.snapshot, comparison)
        try:
            raw = provider.assess(prompt, payload)
            return raw, None
        except Exception as exc:
            return None, str(exc)

    def _get_provider_instance(self) -> LLMProvider | None:
        if self.provider_name is None:
            return None
        if self._provider_instance is not None:
            return self._provider_instance
        try:
            self._provider_instance = get_provider(self.provider_name)
        except ValueError as exc:
            self._provider_error = str(exc)
            self._provider_instance = None
        return self._provider_instance


def run_feedback_loop(
    config_path: Path, provider_override: str | None = None, quiet: bool = False
) -> tuple[int, list[RunArtifact]]:
    try:
        config = FeedbackRunConfig.load(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to load feedback config {config_path}: {exc}", file=sys.stderr)
        return 1, []
    try:
        contexts = list_kube_contexts()
    except RuntimeError as exc:
        print(f"Unable to discover kube contexts: {exc}", file=sys.stderr)
        return 1, []
    runner = FeedbackRunRunner(config, contexts, provider_override, quiet=quiet)
    artifacts = runner.execute()
    if not quiet:
        for artifact in artifacts:
            print(f"Artifact written: {artifact.run_id} / {artifact.context_name}")
    return 0, artifacts
