"""Reusable CLI handlers extracted from the main entry point.

Snapshot-related handlers have been extracted to cli_snapshot_handlers.py
for better LLM-friendly traversal.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

from .cli_logging import CLI_LOG_PATH, _cli_run_label, _log_cli_event  # noqa: F401
from .cli_snapshot_handlers import (  # noqa: F401
    BATCH_CONFIG_FALLBACK,
    DEFAULT_BATCH_CONFIG,
    BatchSnapshotConfig,
    SnapshotTarget,
    handle_assess_snapshots,
    handle_batch_snapshot,
    handle_compare,
    handle_fixture,
    handle_snapshot,
)
from .feedback.runner import run_feedback_loop
from .health import run_health_loop, schedule_health_loop
from .health.adaptation import (
    HealthProposal,
    PromotionError,
    PromotionNotApplicable,
    ProposalLifecycleStatus,
    evaluate_proposal,
    render_proposal_patch,
)
from .health.drilldown import DrilldownArtifact
from .health.drilldown_assessor import assess_drilldown_artifact
from .health.notifications import (
    build_proposal_checked_notification,
    write_notification_artifact,
)
from .health.proposal_lifecycle_events import (
    ProposalLifecycleEvent,
    derive_proposal_evaluation_from_events,
    write_proposal_lifecycle_event,
)
from .health.summary import format_health_summary, gather_health_summary
from .notifications.delivery import DeliveryJournal, artifact_digest
from .structured_logging import emit_structured_log
from .ui import start_ui_server

RUN_CONFIG_DEFAULT = Path("runs/run-config.local.json")
RUN_CONFIG_FALLBACK = Path("runs/run-config.local.example.json")
HEALTH_CONFIG_DEFAULT = Path("runs/health-config.local.json")
HEALTH_CONFIG_FALLBACK = Path("runs/health-config.local.example.json")


def handle_assess_drilldown(args: argparse.Namespace) -> int:
    try:
        raw = json.loads(args.artifact.read_text(encoding="utf-8"))
        artifact = DrilldownArtifact.from_dict(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to load drilldown artifact: {exc}", file=sys.stderr)
        return 1
    try:
        validated = assess_drilldown_artifact(artifact, provider_name=args.provider)
    except Exception as exc:  # noqa: BLE001 - LLM provider errors are diverse
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
        exit_code, *_ = run_health_loop(
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
    # Read token from CLI arg or environment variable
    auth_token = args.auth_token or os.environ.get("K9B_UI_TOKEN")
    start_ui_server(runs_dir=args.runs_dir, host=args.host, port=args.port, unsafe_bind=args.unsafe_bind, auth_token=auth_token)
    return 0


def handle_deliver_notifications(args: argparse.Namespace) -> int:
    from .notifications.mattermost import (
        MattermostNotifier,
        load_notification_artifact,
        render_mattermost_payload,
    )
    directory = args.notifications_dir
    journal = DeliveryJournal.load(directory)
    artifacts = sorted(
        path
        for path in directory.glob("*.json")
        if path.name != journal.path.name
    )
    if not artifacts:
        print(f"No notification artifacts found in '{directory}'.")
        return 0
    notifier = MattermostNotifier(args.webhook_url)
    failure = False
    for path in artifacts:
        try:
            artifact = load_notification_artifact(path)
        except Exception as exc:  # noqa: BLE001 - Mattermost API errors are diverse
            print(f"Skipping {path.name}: {exc}", file=sys.stderr)
            continue
        digest = artifact_digest(artifact)
        if not journal.needs_delivery(path.name, digest):
            print(f"Skipping {path.name}: already delivered")
            continue
        payload = render_mattermost_payload(artifact)
        snippet = payload.get("text", "")
        print(f"Prepared {artifact.kind} ({path.name}): {snippet.splitlines()[0] if snippet else ''}")
        if args.dry_run:
            print("  (dry-run; not sent)")
            continue
        try:
            notifier.dispatch(artifact)
            journal.record_result(path.name, digest, "sent")
            print(f"  Sent {artifact.kind} to Mattermost webhook.")
        except requests.RequestException as exc:
            journal.record_result(path.name, digest, "failed", str(exc))
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
    # Write an immutable lifecycle event artifact instead of mutating the base proposal
    event = ProposalLifecycleEvent(
        proposal_id=proposal.proposal_id,
        proposal_artifact_id=proposal.artifact_id,
        status=ProposalLifecycleStatus.CHECKED,
        transition="check",
        note=f"Replayed against {args.fixture}",
        provenance={
            "artifact_path": str(args.proposal),
            "fixture_path": str(args.fixture),
            "evaluation": evaluation.to_dict(),
        },
    )
    transitions_dir = args.proposal.parent / "transitions"
    event_path = write_proposal_lifecycle_event(event, transitions_dir)
    emit_structured_log(
        component="proposal-lifecycle-event",
        severity="INFO",
        message="Lifecycle event written",
        run_label=run_label,
        run_id=proposal.source_run_id or None,
        proposal_id=proposal.proposal_id,
        artifact_path=str(event_path),
        event="lifecycle-event",
        metadata={"transition": "check", "status": event.status.value},
    )
    return 0


def handle_promote_proposal(args: argparse.Namespace) -> int:
    try:
        raw = json.loads(args.proposal.read_text(encoding="utf-8"))
        proposal = HealthProposal.from_dict(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to read proposal: {exc}", file=sys.stderr)
        return 1

    # Derive evaluation from lifecycle events first, fall back to embedded evaluation for legacy proposals
    transitions_dir = args.proposal.parent / "transitions"
    evaluation = derive_proposal_evaluation_from_events(proposal.proposal_id, transitions_dir)
    if not evaluation:
        # Fall back to embedded promotion_evaluation for backward compatibility with legacy proposals
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

    # Write an immutable lifecycle event artifact instead of mutating the base proposal
    event = ProposalLifecycleEvent(
        proposal_id=proposal.proposal_id,
        proposal_artifact_id=proposal.artifact_id,
        status=ProposalLifecycleStatus.ACCEPTED,
        transition="promote",
        note=updated_note,
        provenance={
            "artifact_path": str(args.proposal),
            "patch_path": str(patch_path),
            "operator_note": args.note,
        },
    )
    transitions_dir = args.proposal.parent / "transitions"
    event_path = write_proposal_lifecycle_event(event, transitions_dir)

    run_label = proposal.source_run_id or proposal.proposal_id
    metadata: dict[str, object] = {
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
    emit_structured_log(
        component="proposal-lifecycle-event",
        severity="INFO",
        message="Lifecycle event written",
        run_label=run_label,
        run_id=proposal.source_run_id or None,
        proposal_id=proposal.proposal_id,
        artifact_path=str(event_path),
        event="lifecycle-event",
        metadata={"transition": "promote", "status": event.status.value},
    )
    print(f"Promotion patch written to '{patch_path}'")
    return 0


def _resolve_config_path(preferred: Path, fallback: Path, allow_fallback: bool) -> Path:
    if preferred.exists():
        return preferred
    if allow_fallback and fallback.exists():
        raise RuntimeError(
            f"Local config {preferred} is missing; copy {fallback} → {preferred} and replace the placeholder contexts with your real kube contexts before running."
        )
    raise RuntimeError(f"Config {preferred} not found; create it from {fallback} before running.")


# Re-export for backward compatibility
__all__ = [
    "CLI_LOG_PATH",
    "SnapshotTarget",
    "BatchSnapshotConfig",
    "DEFAULT_BATCH_CONFIG",
    "BATCH_CONFIG_FALLBACK",
    "RUN_CONFIG_DEFAULT",
    "RUN_CONFIG_FALLBACK",
    "HEALTH_CONFIG_DEFAULT",
    "HEALTH_CONFIG_FALLBACK",
    "handle_fixture",
    "handle_snapshot",
    "handle_batch_snapshot",
    "handle_compare",
    "handle_assess_snapshots",
    "handle_assess_drilldown",
    "handle_run_feedback",
    "handle_health_loop",
    "handle_health_summary",
    "handle_health_ui",
    "handle_deliver_notifications",
    "handle_check_proposal",
    "handle_promote_proposal",
    "_cli_run_label",
    "_log_cli_event",
]
