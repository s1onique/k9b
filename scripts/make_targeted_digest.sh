#!/usr/bin/env bash
set -euo pipefail

# Default mode: staged changes (current index)
MODE="${MODE:-staged}"
OUT="/tmp/targeted-digest.txt"
RANGE_ARG=""
FILE_ARGS=()

# Parse arguments - first non-flag non-path is output, rest are file args
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
    --dirty)
      MODE="dirty"
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
    -*)
      echo "ERROR: unknown flag $1" >&2
      exit 1
      ;;
    *)
      # Non-flag argument
      # Heuristic: if OUT is still default and this looks like a path (contains / or is absolute)
      # then it's the output file; otherwise it's a file argument
      if [[ "$OUT" == "/tmp/targeted-digest.txt" && ("$1" == */* || ! -f "$1") ]]; then
        OUT="$1"
      else
        FILE_ARGS+=("$1")
      fi
      shift
      ;;
  esac
done

# Set file args for explicit file restriction
set -- "${FILE_ARGS[@]+"${FILE_ARGS[@]}"}"

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git not found" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# Determine files based on mode
declare -a FILES=()
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
    dirty)
      # Collect union of: staged tracked + unstaged tracked + untracked-not-ignored
      mapfile -t STAGED_FILES < <(git diff --cached --name-only)
      mapfile -t UNSTAGED_FILES < <(git diff --name-only)
      mapfile -t UNTRACKED_FILES < <(git ls-files --others --exclude-standard)
      # Combine and dedupe, preserving order from staged, unstaged, untracked
      declare -A SEEN
      ALL_FILES=()
      for f in "${STAGED_FILES[@]}" "${UNSTAGED_FILES[@]}" "${UNTRACKED_FILES[@]}"; do
        [[ -n "$f" && -z "${SEEN[$f]:-}" ]] || continue
        SEEN[$f]=1
        ALL_FILES+=("$f")
      done
      FILES=("${ALL_FILES[@]}")
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

# Helper to check if file has staged changes
has_staged() {
  git diff --cached --quiet -- "$1" 2>/dev/null && return 1 || return 0
}

# Helper to check if file has unstaged changes
has_unstaged() {
  git diff --quiet -- "$1" 2>/dev/null && return 1 || return 0
}

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
    dirty)
      # For dirty mode, caller should use staged_diff/unstaged_diff helpers instead
      echo "# ERROR: diff_cmd called in dirty mode, use staged_diff or unstaged_diff" >&2
      return 1
      ;;
  esac
}

# Helpers for dirty mode
staged_diff() {
  git diff --cached "$@"
}

unstaged_diff() {
  git diff "$@"
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

  if [[ "$MODE" == "dirty" ]]; then
    # For dirty mode, show which category each file falls into
    echo "## File state summary"
    for file in "${FILES[@]}"; do
      if [[ -f "$file" ]] && git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
        # Tracked file
        staged_flag=""
        unstaged_flag=""
        has_staged "$file" && staged_flag="+staged"
        has_unstaged "$file" && unstaged_flag="+unstaged"
        echo "$file: tracked${staged_flag}${unstaged_flag}"
      else
        echo "$file: untracked"
      fi
    done
    echo

    echo "## Diff stat (staged)"
    staged_diff --stat -- "${FILES[@]}" 2>/dev/null || echo "(no staged changes)"
    echo

    echo "## Diff stat (unstaged)"
    unstaged_diff --stat -- "${FILES[@]}" 2>/dev/null || echo "(no unstaged changes)"
    echo

    echo "## Diffs"
    for file in "${FILES[@]}"; do
      echo
      # Untracked files: show full content as new
      if [[ ! -f "$file" ]] || ! git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
        echo "### FILE (untracked): $file"
        if [[ -f "$file" ]]; then
          echo "--- $file (new file)"
          cat "$file"
        else
          echo "(file not present)"
        fi
        continue
      fi

      # Tracked files: show staged diff if any
      if has_staged "$file"; then
        echo "### FILE (staged): $file"
        staged_diff --unified=3 -- "$file"
        echo
      fi

      # Tracked files: show unstaged diff if any
      if has_unstaged "$file"; then
        echo "### FILE (unstaged): $file"
        unstaged_diff --unified=3 -- "$file"
      fi
    done
  else
    echo "## Diff stat"
    diff_cmd --stat -- "${FILES[@]}"
    echo

    echo "## Diffs"
    for file in "${FILES[@]}"; do
      echo
      echo "### FILE: $file"
      diff_cmd --unified=3 -- "$file" || true
    done
  fi

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
