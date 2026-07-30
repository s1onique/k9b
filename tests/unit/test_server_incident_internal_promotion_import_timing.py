"""Regression coverage for lazy incident-store provider imports."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROVIDER = "k8s_diag_agent.collect.incident_store_provider"


def _run_isolated(script: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


@pytest.mark.parametrize(
    "module_name",
    [
        "k8s_diag_agent.ui.server_incident_internal_handlers",
        "k8s_diag_agent.ui.server_incident_internal_promotion_handlers",
        "k8s_diag_agent.ui.server_incident_internal_promotion_candidates",
    ],
)
def test_handler_import_does_not_reload_store_provider(module_name: str) -> None:
    script = (
        "import importlib, sys\n"
        "import k8s_diag_agent.ui\n"
        f"sys.modules.pop({PROVIDER!r}, None)\n"
        f"sys.modules.pop({module_name!r}, None)\n"
        f"importlib.import_module({module_name!r})\n"
        f"assert {PROVIDER!r} not in sys.modules\n"
    )
    _run_isolated(script)


@pytest.mark.parametrize("mode", ["unauthorized", "malformed"])
def test_rejected_alert_request_does_not_load_store_provider(mode: str) -> None:
    if mode == "malformed":
        header_value = "Bearer expected"
        content_length = "'invalid'"
    else:
        header_value = "Bearer wrong"
        content_length = "str(len(body))"
    script = (
        "import importlib, io, json, os, sys\n"
        "import k8s_diag_agent.ui\n"
        f"provider = {PROVIDER!r}\n"
        "module_name = 'k8s_diag_agent.ui.server_incident_internal_promotion_handlers'\n"
        "sys.modules.pop(provider, None)\n"
        "sys.modules.pop(module_name, None)\n"
        "module = importlib.import_module(module_name)\n"
        "class Handler:\n"
        "    runs_dir = '/tmp/nonexistent-k9b-import-timing'\n"
        "    def __init__(self):\n"
        "        body = json.dumps({'runId':'run-1','sourceIdentity':'source-1','signalIds':['sig-1']}).encode()\n"
        "        self.rfile = io.BytesIO(body)\n"
        f"        self.headers = {{'Content-Length': {content_length}, 'Authorization':'{header_value}'}}\n"
        "        self.sent = []\n"
        "    def _send_json(self, body, status): self.sent.append((body, status))\n"
        "os.environ['K9B_INTERNAL_API_TOKEN'] = 'expected'\n"
        "module.handle_promote_alert_signals(Handler())\n"
        "assert provider not in sys.modules\n"
    )
    _run_isolated(script)


def test_valid_alert_request_loads_provider_only_at_store_boundary() -> None:
    script = (
        "import importlib, io, json, os, sys\n"
        "import k8s_diag_agent.ui\n"
        f"provider = {PROVIDER!r}\n"
        "module_name = 'k8s_diag_agent.ui.server_incident_internal_promotion_handlers'\n"
        "sys.modules.pop(provider, None)\n"
        "sys.modules.pop(module_name, None)\n"
        "module = importlib.import_module(module_name)\n"
        "assert provider not in sys.modules\n"
        "os.environ['K9B_INTERNAL_API_TOKEN'] = 'expected'\n"
        "class Handler:\n"
        "    runs_dir = '/tmp/nonexistent-k9b-import-timing'\n"
        "    def __init__(self):\n"
        "        body = json.dumps({'runId':'run-1','sourceIdentity':'source-1','signalIds':['sig-1']}).encode()\n"
        "        self.rfile = io.BytesIO(body)\n"
        "        self.headers = {'Content-Length':str(len(body)), 'Authorization':'Bearer expected'}\n"
        "        self.sent = []\n"
        "    def _send_json(self, body, status): self.sent.append((body, status))\n"
        "module.handle_promote_alert_signals(Handler())\n"
        "assert provider in sys.modules\n"
    )
    _run_isolated(script)
