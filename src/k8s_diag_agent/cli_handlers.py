"""Reusable CLI handlers extracted from the main entry point."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import requests

from .collect.cluster_snapshot import ClusterSnapshot, CollectionStatus
from .collect.fixture_loader import load_fixture
from .collect.live_snapshot import collect_cluster_snapshot, list_kube_contexts
from .compare.two_cluster import compare_snapshots
from .correlate.linkers import correlate_signals
from .feedback.runner import run_feedback_loop
from .health import run_health_loop, schedule_health_loop
from .health.adaptation import (
    HealthProposal,
    PromotionError,
    PromotionNotApplicable,
    ProposalLifecycleStatus,
    evaluate_proposal,
    render_proposal_patch,
    with_lifecycle_status,
)
from .health.drilldown import DrilldownArtifact
from .health.drilldown_assessor import assess_drilldown_artifact
from .health.notifications import (
    build_proposal_checked_notification,
    write_notification_artifact,
)
from .health.summary import format_health_summary, gather_health_summary
from .llm.assessor_schema import AssessorAssessment
from .llm.prompts import build_assessment_prompt
from .llm.provider import build_assessment_input, get_provider
from .models import Assessment
from .normalize.evidence import normalize_signals
from .reason.diagnoser import build_findings_and_hypotheses
from .recommend.next_steps import build_recommended_action, propose_next_steps
from .render.formatter import assessment_to_dict, dump_json, format_summary
from .structured_logging import emit_structured_log
from .ui import start_ui_server

DEFAULT_BATCH_CONFIG = Path("snapshots/targets.local.json")
BATCH_CONFIG_FALLBACK = Path("snapshots/targets.local.example.json")
RUN_CONFIG_DEFAULT = Path("runs/run-config.local.json")
RUN_CONFIG_FALLBACK = Path("runs/run-config.local.example.json")
HEALTH_CONFIG_DEFAULT = Path("runs/health-config.local.json")
HEALTH_CONFIG_FALLBACK = Path("runs/health-config.local.example.json")


@dataclass(frozen=True)
class SnapshotTarget:
    context: str
    label: str | None = None
    output: str | None = None


@dataclass(frozen=True)
class BatchSnapshotConfig:
    targets: tuple[SnapshotTarget, ...]
    output_dir: Path

CLI_LOG_PATH: Path | None = None


def _cli_run_label(command: str, identifier: str | None = None) -> str:
    label = command
    if identifier:
        label = f"{label}-{identifier}"
    return label


def _log_cli_event(
    component: str,
    run_label: str,
    message: str,
    *,
    severity: str = "INFO",
    run_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    **extra_metadata: Any,
) -> dict[str, Any]:
    return emit_structured_log(
        component=component,
        message=message,
        run_label=run_label,
        severity=severity,
        run_id=run_id,
        log_path=CLI_LOG_PATH,
        metadata=metadata,
        **extra_metadata,
    )


def handle_fixture(args: argparse.Namespace) -> int:
    fixture_data = load_fixture(args.fixture)
    evidence, signals = normalize_signals(fixture_data)
    correlated = correlate_signals(signals)
    findings, hypotheses = build_findings_and_hypotheses(signals, correlated)
    next_checks = propose_next_steps(hypotheses)
    action = build_recommended_action()

    assessment = Assessment(
        observed_signals=signals,
        findings=findings,
        hypotheses=hypotheses,
        next_evidence_to_collect=next_checks,
        recommended_action=action,
        safety_level=action.safety_level,
        probable_layer_of_origin=findings[0].layer if findings and findings[0].layer else None,
    )

    serialized = assessment_to_dict(assessment)
    if args.output:
        dump_json(assessment, str(args.output))
    else:
        sys.stdout.write(json.dumps(serialized, indent=2))
        sys.stdout.write("\n")
    if not args.quiet:
        print(format_summary(assessment))
    return 0


def handle_snapshot(args: argparse.Namespace) -> int:
    component = "cli-snapshot"
    run_label = _cli_run_label(component, args.context)
    _log_cli_event(
        component,
        run_label,
        "snapshot command started",
        metadata={"context": args.context},
    )
    try:
        contexts = list_kube_contexts()
    except RuntimeError as exc:
        _log_cli_event(
            component,
            run_label,
            "unable to discover kube contexts",
            severity="ERROR",
            metadata={"error": str(exc)},
        )
        print(f"Unable to discover kube contexts: {exc}", file=sys.stderr)
        return 1
    if contexts and args.context not in contexts:
        _log_cli_event(
            component,
            run_label,
            "requested context unavailable",
            severity="ERROR",
            metadata={"context": args.context, "available": contexts},
        )
        print(
            f"Context '{args.context}' not found. Available contexts: {', '.join(contexts)}",
            file=sys.stderr,
        )
        return 1
    try:
        snapshot = collect_cluster_snapshot(args.context)
    except RuntimeError as exc:
        _log_cli_event(
            component,
            run_label,
            "snapshot collection failed",
            severity="ERROR",
            metadata={"error": str(exc)},
        )
        print(f"Snapshot collection failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
    print(f"Snapshot for '{args.context}' written to {args.output}")
    _log_cli_event(
        component,
        run_label,
        "snapshot command completed",
        metadata={"output": str(args.output)},
    )
    return 0


def handle_batch_snapshot(args: argparse.Namespace, default_config: Path = DEFAULT_BATCH_CONFIG) -> int:
    try:
        config_path = _resolve_config_path(
            args.config,
            BATCH_CONFIG_FALLBACK,
            args.config == default_config,
        )
    except RuntimeError as exc:
        run_label = _cli_run_label("cli-batch-snapshot", args.config.name)
        _log_cli_event(
            "cli-batch-snapshot",
            run_label,
            "batch snapshot config resolution failed",
            severity="ERROR",
            metadata={"error": str(exc), "config": str(args.config)},
        )
        print(f"Unable to resolve batch config: {exc}", file=sys.stderr)
        return 1
    component = "cli-batch-snapshot"
    run_label = _cli_run_label(component, config_path.name)
    _log_cli_event(
        component,
        run_label,
        "batch snapshot command started",
        metadata={"config": str(config_path)},
    )
    try:
        config = _load_batch_config(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _log_cli_event(
            component,
            run_label,
            "unable to load batch config",
            severity="ERROR",
            metadata={"error": str(exc), "config": str(config_path)},
        )
        print(f"Unable to load batch config {config_path}: {exc}", file=sys.stderr)
        return 1
    if not config.targets:
        _log_cli_event(
            component,
            run_label,
            "batch config contains no targets",
            severity="ERROR",
            metadata={"config": str(config_path)},
        )
        print(f"Batch config {config_path} contains no targets.", file=sys.stderr)
        return 1
    try:
        contexts = list_kube_contexts()
    except RuntimeError as exc:
        print(f"Unable to discover kube contexts: {exc}", file=sys.stderr)
        return 1
    available = set(contexts)
    successes = 0
    issues: list[str] = []
    config.output_dir.mkdir(parents=True, exist_ok=True)
    for target in config.targets:
        label = target.label or target.context
        if target.context not in available:
            msg = f"Context '{target.context}' not found; skipping {label}."
            print(msg, file=sys.stderr)
            issues.append(msg)
            continue
        output_path = Path(target.output) if target.output else config.output_dir / f"{target.context}.json"
        try:
            snapshot = collect_cluster_snapshot(target.context)
        except RuntimeError as exc:
            msg = f"Snapshot for '{target.context}' failed: {exc}"
            print(msg, file=sys.stderr)
            issues.append(msg)
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
        print(f"Collected snapshot for '{target.context}' -> {output_path}")
        partial = _format_partial_status(snapshot.collection_status)
        if partial:
            print(f"  partial issues: {partial}", file=sys.stderr)
        successes += 1
    print(f"Batch snapshot processed {successes} target(s).")
    if issues:
        print(f"Issues encountered for {len(issues)} target(s).", file=sys.stderr)
        _log_cli_event(
            component,
            run_label,
            "batch snapshot completed with issues",
            severity="WARNING",
            metadata={"successes": successes, "issues": issues},
        )
    else:
        _log_cli_event(
            component,
            run_label,
            "batch snapshot completed",
            metadata={"successes": successes},
        )
    return 0


def handle_compare(args: argparse.Namespace) -> int:
    component = "cli-compare"
    run_label = _cli_run_label(component, f"{args.snapshot_a.name}-{args.snapshot_b.name}")
    _log_cli_event(
        component,
        run_label,
        "compare command started",
        metadata={"snapshot_a": str(args.snapshot_a), "snapshot_b": str(args.snapshot_b)},
    )
    try:
        primary = _load_snapshot(args.snapshot_a)
        secondary = _load_snapshot(args.snapshot_b)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        _log_cli_event(
            component,
            run_label,
            "unable to load snapshots",
            severity="ERROR",
            metadata={"error": str(exc)},
        )
        print(f"Unable to load snapshots: {exc}", file=sys.stderr)
        return 1
    comparison = compare_snapshots(primary, secondary)
    if not comparison.differences:
        print("Snapshots match across tracked dimensions.")
        _log_cli_event(
            component,
            run_label,
            "compare command completed with no differences",
            metadata={"differences": 0},
        )
        return 0
    print(json.dumps(comparison.differences, indent=2))
    _log_cli_event(
        component,
        run_label,
        "compare command completed with differences",
        metadata={"differences": len(comparison.differences)},
    )
    return 0


def handle_assess_snapshots(args: argparse.Namespace) -> int:
    try:
        primary = _load_snapshot(args.snapshot_a)
        secondary = _load_snapshot(args.snapshot_b)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"Unable to load snapshots: {exc}", file=sys.stderr)
        return 1
    comparison = compare_snapshots(primary, secondary)
    prompt = build_assessment_prompt(primary, secondary, comparison)
    provider = get_provider(args.provider)
    payload = build_assessment_input(primary, secondary, comparison)
    try:
        raw_assessment = provider.assess(prompt, payload)
    except Exception as exc:
        print(f"LLM assessment failed: {exc}", file=sys.stderr)
        return 1
    try:
        validated = AssessorAssessment.from_dict(raw_assessment)
    except ValueError as exc:
        print(f"LLM assessment returned invalid schema: {exc}", file=sys.stderr)
        return 1
    serialized = validated.to_dict()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    else:
        sys.stdout.write(json.dumps(serialized, indent=2))
        sys.stdout.write("\n")
    if not args.quiet and validated.hypotheses:
        print(
            f"LLM assessment ready. Hypothesis: {validated.hypotheses[0].description}",
            file=sys.stderr,
        )
    return 0


def handle_assess_drilldown(args: argparse.Namespace) -> int:
    try:
        raw = json.loads(args.artifact.read_text(encoding="utf-8"))
        artifact = DrilldownArtifact.from_dict(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to load drilldown artifact: {exc}", file=sys.stderr)
        return 1
    try:
        validated = assess_drilldown_artifact(artifact, provider_name=args.provider)
    except Exception as exc:
        print(f"LLM assessment failed: {exc}", file=sys.stderr)
        return 1
    serialized = validated.to_dict()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    else:
        sys.stdout.write(json.dumps(serialized, indent=2))
        sys.stdout.write("\n")
    if not args.quiet and validated.hypotheses:
        print(
            f"LLM drilldown assessment ready. Hypothesis: {validated.hypotheses[0].description}",
            file=sys.stderr,
        )
    return 0


def handle_run_feedback(args: argparse.Namespace, default_config: Path = RUN_CONFIG_DEFAULT) -> int:
    component = "cli-run-feedback"
    start_label = _cli_run_label(component, args.config.stem)
    _log_cli_event(
        component,
        start_label,
        "run-feedback command started",
        metadata={"config": str(args.config), "provider_override": args.provider},
    )
    try:
        config_path = _resolve_config_path(
            args.config,
            RUN_CONFIG_FALLBACK,
            args.config == default_config,
        )
    except RuntimeError as exc:
        _log_cli_event(
            component,
            start_label,
            "unable to resolve run config",
            severity="ERROR",
            metadata={"error": str(exc), "config": str(args.config)},
        )
        print(f"Unable to resolve run config: {exc}", file=sys.stderr)
        return 1
    exit_code, artifacts = run_feedback_loop(config_path, provider_override=args.provider, quiet=args.quiet)
    final_label = artifacts[0].run_id if artifacts else start_label
    severity = "INFO" if exit_code == 0 else "ERROR"
    _log_cli_event(
        component,
        final_label,
        "run-feedback command completed",
        severity=severity,
        metadata={"exit_code": exit_code, "artifact_count": len(artifacts)},
    )
    return exit_code


def handle_health_loop(args: argparse.Namespace, default_config: Path = HEALTH_CONFIG_DEFAULT) -> int:
    try:
        config_path = _resolve_config_path(
            args.config,
            HEALTH_CONFIG_FALLBACK,
            args.config == default_config,
        )
    except RuntimeError as exc:
        print(f"Unable to resolve health config: {exc}", file=sys.stderr)
        return 1
    manual = args.trigger or []
    manual_drilldowns = args.drilldown or []
    run_once_mode = args.once or args.every_seconds is None
    if run_once_mode:
        exit_code, _, _, _ = run_health_loop(
            config_path,
            manual_triggers=manual,
            manual_drilldown_contexts=manual_drilldowns,
            quiet=args.quiet,
        )
        return exit_code
    return schedule_health_loop(
        config_path,
        manual_triggers=manual,
        manual_drilldown_contexts=manual_drilldowns,
        quiet=args.quiet,
        interval_seconds=args.every_seconds,
        max_runs=args.max_runs,
        run_once=args.once,
    )


def handle_health_summary(args: argparse.Namespace) -> int:
    try:
        summary = gather_health_summary(args.runs_dir, run_id=args.run_id)
    except RuntimeError as exc:
        print(f"Unable to summarize health runs: {exc}", file=sys.stderr)
        return 1
    print(format_health_summary(summary))
    return 0


def handle_health_ui(args: argparse.Namespace) -> int:
    start_ui_server(runs_dir=args.runs_dir, host=args.host, port=args.port)
    return 0


def handle_deliver_notifications(args: argparse.Namespace) -> int:
    from .notifications.mattermost import (
        MattermostNotifier,
        load_notification_artifact,
        render_mattermost_payload,
    )
    directory = args.notifications_dir
    artifacts = sorted(directory.glob("*.json"))
    if not artifacts:
        print(f"No notification artifacts found in '{directory}'.")
        return 0
    notifier = MattermostNotifier(args.webhook_url)
    failure = False
    for path in artifacts:
        try:
            artifact = load_notification_artifact(path)
        except Exception as exc:
            print(f"Skipping {path.name}: {exc}", file=sys.stderr)
            continue
        payload = render_mattermost_payload(artifact)
        snippet = payload.get("text", "")
        print(f"Prepared {artifact.kind} ({path.name}): {snippet.splitlines()[0] if snippet else ''}")
        if args.dry_run:
            print("  (dry-run; not sent)")
            continue
        try:
            notifier.dispatch(artifact)
            print(f"  Sent {artifact.kind} to Mattermost webhook.")
        except requests.RequestException as exc:
            print(f"Failed to send {path.name}: {exc}", file=sys.stderr)
            failure = True
    return 1 if failure else 0


def handle_check_proposal(args: argparse.Namespace) -> int:
    try:
        raw = json.loads(args.proposal.read_text(encoding="utf-8"))
        proposal = HealthProposal.from_dict(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to read proposal: {exc}", file=sys.stderr)
        return 1
    evaluation = evaluate_proposal(proposal, args.fixture)
    run_label = proposal.source_run_id or proposal.proposal_id
    emit_structured_log(
        component="review-assessment",
        severity="INFO",
        message="Proposal replayed",
        run_label=run_label,
        run_id=proposal.source_run_id or None,
        proposal_id=proposal.proposal_id,
        artifact_path=str(args.proposal),
        event="proposal-replay",
    )
    print(f"Proposal: {proposal.proposal_id}")
    print(f"  Likely noise reduction: {evaluation.noise_reduction}")
    print(f"  Possible signal loss: {evaluation.signal_loss}")
    print(f"  Test/eval outcome: {evaluation.test_outcome}")
    notification = build_proposal_checked_notification(proposal, evaluation)
    write_notification_artifact(
        args.proposal.parent / "notifications",
        notification,
    )
    evaluated_proposal = replace(proposal, promotion_evaluation=evaluation)
    promoted = with_lifecycle_status(
        evaluated_proposal,
        ProposalLifecycleStatus.CHECKED,
        note=f"Replayed against {args.fixture}",
    )
    if promoted is not proposal:
        args.proposal.write_text(json.dumps(promoted.to_dict(), indent=2), encoding="utf-8")
    return 0


def handle_promote_proposal(args: argparse.Namespace) -> int:
    try:
        raw = json.loads(args.proposal.read_text(encoding="utf-8"))
        proposal = HealthProposal.from_dict(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to read proposal: {exc}", file=sys.stderr)
        return 1
    evaluation = proposal.promotion_evaluation
    if not evaluation:
        print("Proposal must be replayed and evaluated before promotion.", file=sys.stderr)
        return 1
    required_history = {
        ProposalLifecycleStatus.CHECKED,
        ProposalLifecycleStatus.REPLAYED,
    }
    if not any(entry.status in required_history for entry in proposal.lifecycle_history):
        print("Proposal must be replayed before promotion.", file=sys.stderr)
        return 1
    try:
        patch_path = render_proposal_patch(
            proposal,
            health_config_path=args.health_config,
            baseline_path=args.baseline,
            output_dir=args.output_dir,
        )
    except PromotionNotApplicable as exc:
        print(f"Promotion not required: {exc}", file=sys.stderr)
        return 1
    except PromotionError as exc:
        print(f"Unable to promote proposal: {exc}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Unable to render promotion: {exc}", file=sys.stderr)
        return 1
    note_parts = [f"Promotion patch: {patch_path}"]
    if args.note:
        note_parts.append(args.note)
    updated_note = " | ".join(note_parts)
    updated = with_lifecycle_status(
        proposal,
        ProposalLifecycleStatus.ACCEPTED,
        note=updated_note,
    )
    if updated is not proposal:
        args.proposal.write_text(json.dumps(updated.to_dict(), indent=2), encoding="utf-8")
    run_label = proposal.source_run_id or proposal.proposal_id
    metadata = {
        "noise_reduction": evaluation.noise_reduction,
        "signal_loss": evaluation.signal_loss,
        "test_outcome": evaluation.test_outcome,
    }
    if args.note:
        metadata["operator_note"] = args.note
    emit_structured_log(
        component="proposal-promotion",
        severity="INFO",
        message="Promotion patch written",
        run_label=run_label,
        run_id=proposal.source_run_id or None,
        proposal_id=proposal.proposal_id,
        artifact_path=str(patch_path),
        metadata=metadata,
        event="promotion",
    )
    print(f"Promotion patch written to '{patch_path}'")
    return 0


def _load_batch_config(path: Path) -> BatchSnapshotConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    output_dir = Path(str(raw.get("output_dir") or "snapshots"))
    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, list):
        raise ValueError("`targets` must be a list")
    targets: list[SnapshotTarget] = []
    for raw_target in targets_raw:
        if not isinstance(raw_target, dict):
            continue
        context = raw_target.get("context")
        if not context:
            continue
        targets.append(
            SnapshotTarget(
                context=str(context),
                label=_str_or_none(raw_target.get("label")),
                output=_str_or_none(raw_target.get("output")),
            )
        )
    return BatchSnapshotConfig(tuple(targets), output_dir)


def _resolve_config_path(preferred: Path, fallback: Path, allow_fallback: bool) -> Path:
    if preferred.exists():
        return preferred
    if allow_fallback and fallback.exists():
        raise RuntimeError(
            f"Local config {preferred} is missing; copy {fallback} → {preferred} and replace the placeholder contexts with your real kube contexts before running."
        )
    raise RuntimeError(f"Config {preferred} not found; create it from {fallback} before running.")


def _format_partial_status(status: CollectionStatus) -> str | None:
    issues: list[str] = []
    if status.helm_error:
        issues.append(f"helm_error={status.helm_error}")
    if status.missing_evidence:
        issues.append(f"missing_evidence={','.join(status.missing_evidence)}")
    if not issues:
        return None
    return "; ".join(issues)


def _str_or_none(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _load_snapshot(path: Path) -> ClusterSnapshot:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ClusterSnapshot.from_dict(raw)
