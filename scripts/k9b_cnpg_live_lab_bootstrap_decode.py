#!/usr/bin/env python3
"""Bootstrap decode and credential validation functions for CNPG Live Lab.

This module contains kubeconfig decoding and credential source validation logic.
"""

from __future__ import annotations

import base64 as b64_module
import os
import subprocess
from pathlib import Path

from .k9b_cnpg_live_lab_config import DiagnosisGenerator, PreflightData
from .k9b_cnpg_live_lab_constants import (
    FAILURE_CREDENTIAL_SOURCE_WRONG,
    FAILURE_KUBECONFIG_AUTH_FAILED,
    FAILURE_KUBECONFIG_DECODE_FAILED,
    FAILURE_KUBECONFIG_MISSING,
)
from .k9b_cnpg_live_lab_helpers import (
    error,
    get_env_secret,
    log,
)


def bootstrap_decode_kubeconfig(
    secret_name: str,
    out_var: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> tuple[str | None, int]:
    """Decode kubeconfig from base64 secret.

    Returns:
        Tuple of (kubeconfig_path, exit_code)
    """
    secret_value = get_env_secret(secret_name)
    if not secret_value:
        error(f"Secret '{secret_name}' is not set or empty")
        preflight.failure_class = FAILURE_KUBECONFIG_MISSING
        preflight.failure_reason = "KUBECONFIG secret not found in environment"
        preflight.save()
        diagnosis.text("**FAIL**: KUBECONFIG secret not found in environment")
        diagnosis.save()
        return None, 1

    out_path = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "k9b-lab-kubeconfig"

    # Decode base64 to file
    try:
        # Try standard base64 decode with padding
        kubeconfig_bytes = b64_module.b64decode(secret_value + "=" * (4 - len(secret_value) % 4))
    except Exception:
        try:
            kubeconfig_bytes = b64_module.b64decode(secret_value)
        except Exception:
            error("Failed to decode base64 kubeconfig")
            preflight.failure_class = FAILURE_KUBECONFIG_DECODE_FAILED
            preflight.failure_reason = "KUBECONFIG base64 decode failed"
            preflight.save()
            diagnosis.text("**FAIL**: KUBECONFIG base64 decode failed")
            diagnosis.save()
            return None, 1

    # Write kubeconfig file
    out_path.write_bytes(kubeconfig_bytes)
    out_path.chmod(0o600)

    # Verify it's a valid kubeconfig
    content = out_path.read_text()
    if "apiVersion:" not in content:
        error("Decoded file does not appear to be a valid kubeconfig")
        out_path.unlink(missing_ok=True)
        preflight.failure_class = FAILURE_KUBECONFIG_DECODE_FAILED
        preflight.failure_reason = "KUBECONFIG does not appear valid after decode"
        preflight.save()
        diagnosis.text("**FAIL**: KUBECONFIG does not appear valid after decode")
        diagnosis.save()
        return None, 1

    log(f"KUBECONFIG={out_path}")
    log("KUBECONFIG decoded successfully")

    # Export to GITHUB_ENV
    github_env = Path(os.environ.get("GITHUB_ENV", ".github_env"))
    with open(github_env, "a") as f:
        f.write(f"{out_var}={out_path}\n")
        f.write(f"KUBECONFIG_PATH={out_path}\n")

    return str(out_path), 0


def validate_credential_source(
    kubeconfig: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> int:
    """Validate credential source using kubectl auth whoami.

    Returns:
        Exit code (0 = valid, 1 = invalid)
    """
    log("Validating credential source...")

    # Get active identity
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "auth", "whoami"],
        capture_output=True,
        text=True,
    )
    whoami_output = result.stdout.strip()
    preflight.active_identity = whoami_output

    diagnosis.heading(2, "Credential Validation Result")

    if result.returncode != 0 or not whoami_output:
        error("kubectl auth whoami failed or returned empty")
        preflight.failure_class = FAILURE_KUBECONFIG_AUTH_FAILED
        preflight.failure_reason = f"kubectl auth whoami failed (exit={result.returncode})"
        preflight.save()
        diagnosis.text("**FAIL**: kubectl auth whoami failed")
        diagnosis.text(f"Exit code: {result.returncode}")
        diagnosis.text(f"Output: {whoami_output or result.stderr}")
        diagnosis.save()
        return 1

    diagnosis.text("**PASS**: Credential source is valid")
    diagnosis.text(f"Active identity: {diagnosis.inline_code(whoami_output)}")
    preflight.credential_source = "valid"

    # Check for wrong credential source (ARC runner SA)
    if whoami_output.startswith("system:serviceaccount:github-actions-runner:"):
        error("Credential source is ARC runner ServiceAccount - this is WRONG")
        error(f"Active identity: {whoami_output}")
        error("Expected: protected environment kubeconfig identity")
        preflight.failure_class = FAILURE_CREDENTIAL_SOURCE_WRONG
        preflight.failure_reason = "Wrong credential source: ARC runner ServiceAccount used instead of protected kubeconfig"
        preflight.save()
        diagnosis.text("**FAIL**: Wrong credential source detected")
        diagnosis.text(f"Active identity: {diagnosis.inline_code(whoami_output)}")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Problem')}: The workflow is using the ARC runner's ServiceAccount credentials")
        diagnosis.text("instead of the protected environment kubeconfig.")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Root cause')}: The protected kubeconfig secret was not properly loaded,")
        diagnosis.text("or the workflow fell back to ambient in-cluster credentials.")
        diagnosis.text("")
        diagnosis.text(f"{diagnosis.bold('Required action')}: Verify the workflow is running in the protected")
        diagnosis.text("environment 'k9b-live-lab-admin' and that the KUBECONFIG_B64 secret")
        diagnosis.text("is correctly set in that environment.")
        diagnosis.save()
        return 1

    log(f"Active identity: {whoami_output}")
    return 0
