#!/usr/bin/env bash
# =============================================================================
# k9b CNPG Live Lab Bootstrap - Shell Shim
#
# Thin wrapper that delegates to Python implementation.
# All complex logic is in k9b_cnpg_live_lab_bootstrap.py
#
# Usage:
#   k9b_cnpg_live_lab_bootstrap.sh <env_secret_name> <kubeconfig_out_var> [namespace]
#   k9b_cnpg_live_lab_bootstrap.sh classify-error
#
# Exit codes:
#   0 - Bootstrap succeeded, KUBECONFIG exported
#   1 - Secret missing, decode failed, or wrong credential source
# =============================================================================

set -euo pipefail

# Delegate to Python implementation
exec python3 "${BASH_SOURCE[0]%.sh}.py" "$@"
