#!/usr/bin/env bash
set -uo pipefail

# Default mode: staged changes (current index)
MODE="staged"
OUT=""
RANGE_ARG=""
declare -a FILE_ARGS=()

# Parse arguments
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
    --output)
      OUT="$2"
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
      FILE_ARGS+=("$1")
      shift
      ;;
  esac
done

# Add remaining positional args as file arguments
for arg in "$@"; do
  FILE_ARGS+=("$arg")
done

if [[ -z "$OUT" ]]; then
  echo "ERROR: --output is required" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git not found" >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# Determine files based on mode
declare -a FILES=()
if [[ ${#FILE_ARGS[@]} -gt 0 ]]; then
  # Explicit file args always take precedence
  FILES=("${FILE_ARGS[@]}")
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

# Helper: check if a file is tracked by git
is_tracked() {
  git ls-files --error-unmatch "$1" >/dev/null 2>&1
}

# Helper: check if file has staged changes (returns 0 if present, 1 if absent)
has_staged() {
  if git diff --cached --quiet -- "$1" 2>/dev/null; then
    return 1
  fi
  return 0
}

# Helper: check if file has unstaged changes (returns 0 if present, 1 if absent)
has_unstaged() {
  if git diff --quiet -- "$1" 2>/dev/null; then
    return 1
  fi
  return 0
}

# Helper: run diff based on mode
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

# Helper: format file entry for Changed files list
format_file_entry() {
  local file="$1"
  
  if is_tracked "$file"; then
    local tracked_state="tracked"
    local staged_yes="no"
    local unstaged_yes="no"
    if has_staged "$file"; then staged_yes="yes"; fi
    if has_unstaged "$file"; then unstaged_yes="yes"; fi
    printf '%s  [%s, staged present: %s, unstaged present: %s]\n' \
      "$file" "$tracked_state" "$staged_yes" "$unstaged_yes"
  else
    printf '%s  [untracked, staged present: no, unstaged present: yes]\n' "$file"
  fi
}

# Helper: format file metadata for Diffs section
format_file_metadata() {
  local file="$1"
  
  if is_tracked "$file"; then
    local tracked_state="tracked"
    local staged_yes="no"
    local unstaged_yes="no"
    if has_staged "$file"; then staged_yes="yes"; fi
    if has_unstaged "$file"; then unstaged_yes="yes"; fi
    echo "Metadata: $tracked_state, staged present: $staged_yes, unstaged present: $unstaged_yes"
  else
    echo "Metadata: untracked, staged present: no, unstaged present: yes"
  fi
}

{
  echo "# Targeted digest"
  echo
  echo "Generated at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "Repo: $repo_root"
  echo "Mode: $MODE"
  [[ -n "$RANGE_ARG" ]] && echo "Range: $RANGE_ARG"
  [[ ${#FILE_ARGS[@]} -gt 0 ]] && echo "File filter: ${FILE_ARGS[*]}"
  echo

  echo "## Changed files"
  for file in "${FILES[@]}"; do
    format_file_entry "$file"
  done
  echo

  if [[ "$MODE" == "dirty" ]]; then
    # Unified diffs section - organized per file, not per Git area
    echo "## Diffs"
    for file in "${FILES[@]}"; do
      echo
      echo "=== $file ==="
      format_file_metadata "$file"
      echo

      # Untracked files: show full content as new
      if ! is_tracked "$file"; then
        echo "--- untracked file preview ---"
        if [[ -f "$file" ]]; then
          cat "$file"
        else
          echo "(file not present)"
        fi
        continue
      fi

      # Tracked files with staged changes
      if has_staged "$file"; then
        echo "--- staged diff ---"
        staged_diff --unified=3 -- "$file"
        echo
      fi

      # Tracked files with unstaged changes
      if has_unstaged "$file"; then
        echo "--- unstaged diff ---"
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
      echo "=== $file ==="
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