#!/usr/bin/env bash
set -euo pipefail

MODE="staged"
OUT=""
RANGE_ARG=""
declare -a FILE_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --staged) MODE="staged"; shift ;;
    --unstaged) MODE="unstaged"; shift ;;
    --dirty) MODE="dirty"; shift ;;
    --range) MODE="range"; RANGE_ARG="$2"; shift 2 ;;
    --output) OUT="$2"; shift 2 ;;
    --) shift; break ;;
    -*) echo "ERROR: unknown flag $1" >&2; exit 1 ;;
    *) FILE_ARGS+=("$1"); shift ;;
  esac
done

for arg in "$@"; do FILE_ARGS+=("$arg"); done

if [[ -z "$OUT" ]]; then echo "ERROR: --output is required" >&2; exit 1; fi
if ! command -v git >/dev/null 2>&1; then echo "ERROR: git not found" >&2; exit 1; fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

# R11 invariant: the digest must NEVER include its own output path in
# the FILES list, the manifest, or the diff section. Generating to a
# path inside the repository would otherwise append the artifact to
# its own manifest and embed thousands of lines of self-referential
# diff that also breaks ``git diff --check`` (whitespace, line
# endings). Resolve ``$OUT`` to a canonical absolute path and filter
# it out before any counting or diff rendering happens.
OUT_REL="$(realpath -m --relative-to="$repo_root" "$OUT")"
# ``realpath -m`` resolves the path even if the file does not yet
# exist; the canonical form is what the manifest will eventually
# show.

# Filter ``$OUT_REL`` from a list of repo-relative paths.
# Sets ``OUT_REL`` as a side effect; result goes to stdout.
_filter_out_path() {
  local out_rel="$1"
  shift
  local f
  for f in "$@"; do
    [[ "$f" != "$out_rel" ]] && printf '%s\n' "$f"
  done
}

declare -a FILES=()
if [[ ${#FILE_ARGS[@]} -gt 0 ]]; then
  while IFS= read -r f; do FILES+=("$f"); done < <(_filter_out_path "$OUT_REL" "${FILE_ARGS[@]}")
else
  case "$MODE" in
    staged) mapfile -t RAW_FILES < <(git diff --cached --name-only) ;;
    unstaged) mapfile -t RAW_FILES < <(git diff --name-only) ;;
    range)
      if [[ -z "$RANGE_ARG" ]]; then echo "ERROR: --range requires a commit range argument" >&2; exit 1; fi
      mapfile -t RAW_FILES < <(git diff --name-only "$RANGE_ARG")
      ;;
    dirty)
      mapfile -t STAGED_FILES < <(git diff --cached --name-only)
      mapfile -t UNSTAGED_FILES < <(git diff --name-only)
      mapfile -t UNTRACKED_FILES < <(git ls-files --others --exclude-standard)
      declare -A SEEN
      ALL_FILES=()
      for f in "${STAGED_FILES[@]}" "${UNSTAGED_FILES[@]}" "${UNTRACKED_FILES[@]}"; do
        [[ -n "$f" && -z "${SEEN[$f]:-}" ]] || continue
        SEEN[$f]=1
        ALL_FILES+=("$f")
      done
      RAW_FILES=("${ALL_FILES[@]}")
      ;;
  esac
  while IFS= read -r f; do FILES+=("$f"); done < <(_filter_out_path "$OUT_REL" "${RAW_FILES[@]}")
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
  { echo "No changed files found in mode: $MODE"; } >"$OUT"
  echo "$OUT"
  exit 0
fi

is_tracked() { git ls-files --error-unmatch "$1" >/dev/null 2>&1; }
has_staged() { git diff --cached --quiet -- "$1" 2>/dev/null && return 1 || return 0; }
has_unstaged() { git diff --quiet -- "$1" 2>/dev/null && return 1 || return 0; }

diff_cmd() {
  case "$MODE" in
    staged) git diff --cached "$@" ;;
    unstaged) git diff "$@" ;;
    range) git diff "$RANGE_ARG" -- "$@" ;;
    dirty) echo "# ERROR: diff_cmd called in dirty mode" >&2; return 1 ;;
  esac
}

staged_diff() { git diff --cached "$@"; }
unstaged_diff() { git diff "$@"; }

print_file_metadata() {
  local file="$1"
  if is_tracked "$file"; then
    local staged_yes="no" unstaged_yes="no"
    if has_staged "$file"; then staged_yes="yes"; fi
    if has_unstaged "$file"; then unstaged_yes="yes"; fi
    echo "Metadata: tracked, staged present: $staged_yes, unstaged present: $unstaged_yes"
  else
    echo "Metadata: untracked, staged present: no, unstaged present: yes"
  fi
}

is_file_untracked() { ! is_tracked "$1"; }

print_file_entry() {
  local file="$1"
  if is_tracked "$file"; then
    local staged_yes="no" unstaged_yes="no"
    if has_staged "$file"; then staged_yes="yes"; fi
    if has_unstaged "$file"; then unstaged_yes="yes"; fi
    printf "%s  [tracked, staged present: %s, unstaged present: %s]\n" "$file" "$staged_yes" "$unstaged_yes"
  else
    printf "%s  [untracked, staged present: no, unstaged present: yes]\n" "$file"
  fi
}

print_manifest_summary() {
  local added="$1" modified="$2" renamed="$3" deleted="$4" other="$5" total="$6"
  echo "files_changed=${total}"
  echo "added_files=${added}"
  echo "modified_files=${modified}"
  echo "renamed_files=${renamed}"
  echo "deleted_files=${deleted}"
  if [[ "$other" -gt 0 ]]; then echo "other_files=${other}"; fi
}

# R10 invariant: every ``git diff --name-status`` invocation in this
# script MUST enable rename detection explicitly with ``-M`` so the
# rename-vs-add/delete classification is deterministic across
# repositories and user ``diff.renames`` configurations. Git's
# rename detection is opt-in via ``-M`` (or ``--find-renames``); the
# default similarity threshold is 50%. Without ``-M``, a file with
# similarity above the threshold is silently split into A+D entries
# and the manifest counts can disagree with the actual operations.
manifest_diff_args() {
  # Echo the canonical ``git diff --name-status`` argument vector
  # for the requested section (staged/unstaged/range). The caller
  # appends ``--cached`` or a commit range as appropriate.
  echo "-M" "--name-status" "--diff-filter=ACDMRT"
}

# Filter ``$OUT_REL`` from ``MANIFEST_ENTRIES``. The manifest is
# derived from git diff output, which can independently include the
# output path (e.g. if a previous digest has been staged as an
# addition). Stripping the entry here keeps the manifest consistent
# with the FILES list and prevents self-reference in either section.
_filter_manifest() {
  local out_rel="$1"
  local entry
  for entry in "${MANIFEST_ENTRIES[@]}"; do
    local status="${entry%%	*}"
    local path="${entry#*	}"
    [[ "$path" != "$out_rel" ]] && printf '%s\t%s\n' "$status" "$path"
  done
}

collect_manifest_entries() {
  MANIFEST_ENTRIES=()
  case "$MODE" in
    staged|unstaged|range)
      local diff_args
      read -r -a diff_args < <(manifest_diff_args)
      if [[ "$MODE" == "staged" ]]; then diff_args+=(--cached); fi
      if [[ "$MODE" == "range" ]]; then diff_args+=("$RANGE_ARG"); fi
      while IFS=$'\t' read -r status rest; do
        [[ -z "$status" || -z "$rest" ]] && continue
        local first_char="${status:0:1}"
        if [[ "$first_char" == "R" || "$first_char" == "C" ]]; then
          local path="${rest##*$'\t'}"
          MANIFEST_ENTRIES+=("$first_char	$path")
        else
          MANIFEST_ENTRIES+=("$first_char	$rest")
        fi
      done < <(git diff "${diff_args[@]}" 2>/dev/null || true)
      ;;
    dirty)
      local staged_args unstaged_args
      read -r -a staged_args < <(manifest_diff_args)
      staged_args+=(--cached)
      read -r -a unstaged_args < <(manifest_diff_args)
      while IFS=$'\t' read -r status rest; do
        [[ -z "$status" || -z "$rest" ]] && continue
        local first_char="${status:0:1}"
        if [[ "$first_char" == "R" || "$first_char" == "C" ]]; then
          local path="${rest##*$'\t'}"
          MANIFEST_ENTRIES+=("$first_char	$path")
        else
          MANIFEST_ENTRIES+=("$first_char	$rest")
        fi
      done < <(git diff "${staged_args[@]}" 2>/dev/null || true)
      while IFS=$'\t' read -r status rest; do
        [[ -z "$status" || -z "$rest" ]] && continue
        local first_char="${status:0:1}"
        if [[ "$first_char" == "R" || "$first_char" == "C" ]]; then
          local path="${rest##*$'\t'}"
          local already=0
          for entry in "${MANIFEST_ENTRIES[@]}"; do
            if [[ "$entry" == *"	$path" ]]; then already=1; break; fi
          done
          [[ "$already" -eq 0 ]] && MANIFEST_ENTRIES+=("$first_char	$path")
        else
          local already=0
          for entry in "${MANIFEST_ENTRIES[@]}"; do
            if [[ "$entry" == *"	$rest" ]]; then already=1; break; fi
          done
          [[ "$already" -eq 0 ]] && MANIFEST_ENTRIES+=("$first_char	$rest")
        fi
      done < <(git diff "${unstaged_args[@]}" 2>/dev/null || true)
      # Untracked-loop dedup: a path that was already recorded (with
      # ANY status) MUST NOT be re-emitted as ``A``. The R10
      # regression is a path staged as ``D`` and then recreated as
      # untracked; without this dedup the manifest would list the
      # path twice (``D`` and ``A``) and ``files_changed`` would
      # over-count. The inner ``|| true`` is required because the
      # test expression ``[[ $already -eq 0 ]]`` returns 1 when the
      # path is already recorded, which would otherwise trip
      # ``set -e`` and abort the script before the next stage.
      while IFS= read -r untracked || [[ -n "$untracked" ]]; do
        [[ -z "$untracked" ]] && continue
        local already=0
        for entry in "${MANIFEST_ENTRIES[@]}"; do
          if [[ "$entry" == *"	$untracked" ]]; then already=1; break; fi
        done
        if [[ "$already" -eq 0 ]]; then
          MANIFEST_ENTRIES+=("A	$untracked")
        fi
      done < <(git ls-files --others --exclude-standard 2>/dev/null || true)
      ;;
  esac
  # Drop the digest's own output path from the manifest. This is a
  # no-op on the first run (the file does not yet exist in any
  # section) and a self-reference guard on subsequent runs.
  local filtered=()
  while IFS=$'\t' read -r status path; do
    filtered+=("$status	$path")
  done < <(_filter_manifest "$OUT_REL")
  MANIFEST_ENTRIES=("${filtered[@]}")
}

print_manifest_section() {
  collect_manifest_entries
  local added=0 modified=0 renamed=0 deleted=0 other=0 total=0
  for entry in "${MANIFEST_ENTRIES[@]}"; do
    local status="${entry%%	*}"
    total=$((total + 1))
    case "$status" in
      A) added=$((added + 1)) ;;
      M) modified=$((modified + 1)) ;;
      R) renamed=$((renamed + 1)) ;;
      D) deleted=$((deleted + 1)) ;;
      *) other=$((other + 1)) ;;
    esac
  done
  print_manifest_summary "$added" "$modified" "$renamed" "$deleted" "$other" "$total"
  echo
  for entry in "${MANIFEST_ENTRIES[@]}"; do
    local status="${entry%%	*}"
    local path="${entry#*	}"
    printf "%s	%s\n" "$status" "$path"
  done
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
  echo "## Manifest"
  print_manifest_section
  echo
  echo "## Changed files"
  for file in "${FILES[@]}"; do print_file_entry "$file"; done
  echo

  if [[ "$MODE" == "dirty" ]]; then
    echo "## Diffs"
    for file in "${FILES[@]}"; do
      echo
      echo "=== $file ==="
      print_file_metadata "$file"
      echo
      if is_file_untracked "$file"; then
        echo "--- untracked file preview ---"
        if [[ -f "$file" ]]; then cat "$file"; else echo "(file not present)"; fi
        continue
      fi
      if has_staged "$file"; then
        echo "--- staged diff ---"
        # ``git diff --check`` flags trailing whitespace in any line
        # of the generated digest. Strip it from the diff output so
        # the digest itself does not introduce whitespace errors
        # when it is later staged and diffed.
        staged_diff --unified=3 -- "$file" | sed -e 's/[[:space:]]*$//'
        echo
      fi
      if has_unstaged "$file"; then
        echo "--- unstaged diff ---"
        unstaged_diff --unified=3 -- "$file" | sed -e 's/[[:space:]]*$//'
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
      diff_cmd --unified=3 -- "$file" | sed -e 's/[[:space:]]*$//' || true
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
