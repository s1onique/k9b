#!/usr/bin/env bash
# =============================================================================
# ensure_live_lab_venv.sh - Deterministic live-lab venv preparation
# =============================================================================
# Replaces GitHub cache restore/save pattern with local fingerprint-based
# recreation. Uses pre-baked venv if available, otherwise creates fresh
# from local requirements. No remote cache dependency.
#
# Usage:
#   export K9B_LIVE_LAB_PYTHON="/path/to/python"
#   export K9B_LIVE_LAB_PREBAKED_VENV="/opt/k9b/live-lab-venv"  # optional
#   scripts/ci/ensure_live_lab_venv.sh
#
# Outputs (via GITHUB_OUTPUT):
#   venv-source: fresh | local-existing | prebaked
# =============================================================================

set -euo pipefail

venv_path="${K9B_LIVE_LAB_VENV_PATH:-.venv}"
requirements="${K9B_LIVE_LAB_REQUIREMENTS:-requirements-live-lab.txt}"
python_bin="${K9B_LIVE_LAB_PYTHON:-python3}"

# Normalize python_bin: if it is a directory (toolcache-style .../x64/bin),
# resolve to the actual executable. This guards against GitHub Actions
# outputs that pass the bin directory instead of the python executable.
if [[ -d "${python_bin}" ]]; then
  if [[ -x "${python_bin}/python" ]]; then
    python_bin="${python_bin}/python"
  elif [[ -x "${python_bin}/python3" ]]; then
    python_bin="${python_bin}/python3"
  else
    echo "ERROR: python_bin points to a directory without python/python3: ${python_bin}" >&2
    exit 2
  fi
fi

if [[ ! -x "${python_bin}" ]]; then
  echo "ERROR: python_bin is not an executable: ${python_bin}" >&2
  exit 2
fi

validate_venv() {
  local candidate="$1"

  [[ -x "${candidate}/bin/python" ]] || return 1
  "${candidate}/bin/python" --version

  # Validate required imports
  "${candidate}/bin/python" - <<'PY'
import importlib
for name in ("pytest", "yaml", "requests", "ijson"):
    importlib.import_module(name)
print("live-lab venv validation OK")
PY
}

venv_fingerprint() {
  {
    "${python_bin}" -VV
    sha256sum "${requirements}"
    [[ -f pyproject.toml ]] && sha256sum pyproject.toml || true
  } | sha256sum | awk '{print $1}'
}

expected_fingerprint="$(venv_fingerprint)"
fingerprint_file="${venv_path}/.k9b-live-lab-fingerprint"

echo "=== Preparing live-lab Python venv ==="
echo "python_bin=${python_bin}"
echo "venv_path=${venv_path}"
echo "requirements=${requirements}"
echo "expected_fingerprint=${expected_fingerprint}"

# Check for pre-baked venv first (highest priority)
if [[ -n "${K9B_LIVE_LAB_PREBAKED_VENV:-}" ]]; then
  echo "=== Checking pre-baked venv: ${K9B_LIVE_LAB_PREBAKED_VENV} ==="
  if validate_venv "${K9B_LIVE_LAB_PREBAKED_VENV}"; then
    rm -rf "${venv_path}"
    ln -s "${K9B_LIVE_LAB_PREBAKED_VENV}" "${venv_path}"
    echo "=== Pre-baked venv linked successfully ==="
    echo "venv-source=prebaked" >> "${GITHUB_OUTPUT:-/dev/null}"
    exit 0
  fi
  echo "WARNING: Pre-baked venv is not usable; falling back to local recreate"
fi

# Check existing local venv with fingerprint
if [[ -f "${fingerprint_file}" ]] \
  && [[ "$(cat "${fingerprint_file}")" == "${expected_fingerprint}" ]] \
  && validate_venv "${venv_path}"; then
  echo "=== Existing local venv is valid (fingerprint match) ==="
  echo "venv-source=local-existing" >> "${GITHUB_OUTPUT:-/dev/null}"
  exit 0
fi

# Create fresh venv
echo "=== Creating fresh live-lab venv ==="
rm -rf "${venv_path}"
"${python_bin}" -m venv "${venv_path}"

"${venv_path}/bin/python" -m pip install --upgrade pip
"${venv_path}/bin/python" -m pip install -r "${requirements}"

# Validate fresh venv
validate_venv "${venv_path}"

# Write fingerprint for future runs
printf '%s\n' "${expected_fingerprint}" > "${fingerprint_file}"

echo "=== Fresh venv created and validated ==="
echo "venv-source=fresh" >> "${GITHUB_OUTPUT:-/dev/null}"
