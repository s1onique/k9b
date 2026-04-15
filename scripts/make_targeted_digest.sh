#!/usr/bin/env bash
set -euo pipefail

# Default mode: staged changes (current index)
MODE="${MODE:-staged}"
OUT="${1:-/tmp/targeted-digest.txt}"
RANGE_ARG=""
shift || true

# Parse explicit mode flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --staged)
      MODE="staged"
      shift
      ;;
    --unstaged)
      MODE="unstaged"
      shift
      ;;
    --range)
      MODE="range"
      RANGE_ARG="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      break
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git not found" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# Determine files based on mode
if [[ $# -gt 0 ]]; then
  # Explicit file args always take precedence
  FILES=("$@")
else
  case "$MODE" in
    staged)
      mapfile -t FILES < <(git diff --cached --name-only)
      ;;
    unstaged)
      mapfile -t FILES < <(git diff --name-only)
      ;;
    range)
      if [[ -z "$RANGE_ARG" ]]; then
        echo "ERROR: --range requires a commit range argument" >&2
        exit 1
      fi
      mapfile -t FILES < <(git diff --name-only "$RANGE_ARG")
      ;;
  esac
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  {
    echo "No changed files found in mode: $MODE"
  } >"$OUT"
  echo "$OUT"
  exit 0
fi

# Helper to run diff based on mode
diff_cmd() {
  case "$MODE" in
    staged)
      git diff --cached "$@"
      ;;
    unstaged)
      git diff "$@"
      ;;
    range)
      git diff "$RANGE_ARG" -- "$@"
      ;;
  esac
}

{
  echo "# Targeted digest"
  echo
  echo "Generated at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "Repo: $repo_root"
  echo "Mode: $MODE"
  [[ -n "$RANGE_ARG" ]] && echo "Range: $RANGE_ARG"
  echo

  echo "## Changed files"
  printf '%s\n' "${FILES[@]}"
  echo

  echo "## Diff stat"
  diff_cmd --stat -- "${FILES[@]}"
  echo

  echo "## Diffs"
  for file in "${FILES[@]}"; do
    echo
    echo "### FILE: $file"
    diff_cmd --unified=3 -- "$file" || true
  done

  echo
  echo "## Workflow anchors"
  for file in "${FILES[@]}"; do
    [[ -f "$file" ]] || continue
    case "$file" in
      frontend/src/App.tsx|frontend/src/__tests__/app.test.tsx|frontend/src/index.css)
        echo
        echo "### ANCHORS IN: $file"
        grep -nE 'WORKFLOW_LANES|Diagnose now|Diagnose Now|Work next checks|Work Next Checks|Improve the system|Improve the System|ExecutionHistoryPanel|ReviewEnrichmentPanel|ProviderExecutionPanel|LLMActivityPanel|LLMPolicyPanel|Proposal' "$file" || true
        ;;
    esac
  done
} >"$OUT"

echo "$OUT"
