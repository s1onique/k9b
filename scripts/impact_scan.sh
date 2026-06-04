#!/usr/bin/env sh
# impact_scan.sh
# Lightweight impact map bootstrap for non-trivial code edits.
# Uses rg/git grep only. No DB, no AST, no third-party tools.
#
# Usage:
#   scripts/impact_scan.sh <target>
#   scripts/impact_scan.sh --help
#
# Target can be a file path (e.g., frontend/src/App.tsx) or a symbol name.
set -eu

HELP="impact_scan.sh - Lightweight pre-edit impact map bootstrap

Usage:
  scripts/impact_scan.sh <target>

Target is a file path or symbol name (e.g., useRunSelection, App.tsx).

The script produces a small impact map with:
  - target symbol / file
  - definitions
  - direct references
  - likely tests
  - intended edit surface (TODO: fill before editing)
  - reason if broader exploration is needed (TODO: fill if needed)

This is derived evidence, not source of truth. Correct manually.

Search order: rg + git grep + existing tests.
No DB, no AST, no tree-sitter, no MCP, no third-party tools."

# ── Helpers ────────────────────────────────────────────────────────────────

usage() {
    printf '%s\n' "$HELP"
}

die() {
    printf '%s\n' "$*" >&2
    exit 1
}

# ── Args ────────────────────────────────────────────────────────────────────

if [ "$#" -eq 0 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    usage
    exit 0
fi

TARGET="$1"

# ── Repo root (assumes script is under scripts/) ────────────────────────────

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Detect if target looks like a file path ────────────────────────────────

is_file() {
    [ -f "$REPO_ROOT/$1" ] || [ -f "$1" ]
}

# ── Extract search name from file path ──────────────────────────────────────

file_to_search_name() {
    # Get basename, then strip common extensions one by one (macOS-compatible)
    fname="$(basename "$1")"
    fname="${fname%.tsx}"
    fname="${fname%.ts}"
    fname="${fname%.jsx}"
    fname="${fname%.js}"
    fname="${fname%.py}"
    fname="${fname%.rs}"
    fname="${fname%.go}"
    fname="${fname%.yaml}"
    fname="${fname%.yml}"
    fname="${fname%.md}"
    fname="${fname%.txt}"
    printf '%s' "$fname"
}

# ── Find likely test files ──────────────────────────────────────────────────

find_tests() {
    search_name="$1"
    # Search test patterns
    find "$REPO_ROOT" -type f \( \
        -name "*${search_name}*.test.*" \
        -o -name "*${search_name}*.spec.*" \
        -o -name "test_*${search_name}*" \
        -o -name "*_test.py" \
        -o -name "*_test.sh" \
    \) -not -path "*/node_modules/*" \
       -not -path "*/.venv/*" \
       -not -path "*/.git/*" \
       2>/dev/null | head -20
}

# ── Main scan ───────────────────────────────────────────────────────────────

main() {
    SEARCH_NAME=""
    IS_FILE_TARGET=false

    if is_file "$TARGET"; then
        IS_FILE_TARGET=true
        SEARCH_NAME="$(file_to_search_name "$TARGET")"
    else
        SEARCH_NAME="$TARGET"
    fi

    printf '%s\n' "## Impact scan"
    printf '%s\n' ""
    printf '%s\n' "- Target: $TARGET"
    if [ "$IS_FILE_TARGET" = true ]; then
        printf '%s\n' "  (file target: searching for $SEARCH_NAME)"
    fi
    printf '%s\n' ""

    # ── Definitions ─────────────────────────────────────────────────────────
    printf '%s\n' "- Definitions:"
    if command -v rg >/dev/null 2>&1; then
        DEF_COUNT=$(rg -l "^[^/]*\b(const|function|class|def|interface|type|struct|enum)\s+($SEARCH_NAME)\b" "$REPO_ROOT" 2>/dev/null | wc -l | tr -d ' ')
    else
        DEF_COUNT=0
    fi
    if [ "$DEF_COUNT" -gt 0 ]; then
        rg -l "^[^/]*\b(const|function|class|def|interface|type|struct|enum)\s+($SEARCH_NAME)\b" "$REPO_ROOT" 2>/dev/null \
            | head -10 \
            | while read -r f; do
                printf '  - %s\n' "$f"
            done
    else
        # Fallback: git grep for definition-like lines
        DEFINES=$(git grep -l "\b$SEARCH_NAME\b" "$REPO_ROOT" -- "*.py" "*.ts" "*.tsx" "*.js" "*.jsx" 2>/dev/null | head -10)
        if [ -n "$DEFINES" ]; then
            printf '%s\n' "$DEFINES" | while read -r f; do
                printf '  - %s\n' "$f"
            done
        else
            printf '  - (none found via grep; verify manually)\n'
        fi
    fi
    printf '\n'

    # ── Direct references ────────────────────────────────────────────────────
    printf '%s\n' "- Direct references:"
    if command -v rg >/dev/null 2>&1; then
        REF_FILES=$(rg -l "\b$SEARCH_NAME\b" "$REPO_ROOT" \
            --type py --type ts --type tsx --type js --type jsx \
            -g '!.git' -g '!node_modules' -g '!.venv' \
            2>/dev/null | head -20)
        if [ -n "$REF_FILES" ]; then
            printf '%s\n' "$REF_FILES" | while read -r f; do
                printf '  - %s\n' "$f"
            done
        else
            printf '  - (none found)\n'
        fi
    else
        REFS=$(git grep -l "\b$SEARCH_NAME\b" "$REPO_ROOT" -- "*.py" "*.ts" "*.tsx" "*.js" "*.jsx" 2>/dev/null | head -20)
        if [ -n "$REFS" ]; then
            printf '%s\n' "$REFS" | while read -r f; do
                printf '  - %s\n' "$f"
            done
        else
            printf '  - (none found)\n'
        fi
    fi
    printf '\n'

    # ── Likely tests ─────────────────────────────────────────────────────────
    printf '%s\n' "- Likely tests:"
    TESTS=$(find_tests "$SEARCH_NAME")
    if [ -n "$TESTS" ]; then
        printf '%s\n' "$TESTS" | while read -r t; do
            printf '  - %s\n' "$t"
        done
    else
        printf '  - (none found by pattern; check manually for: *test* *spec* __tests__)\n'
    fi
    printf '\n'

    # ── Human-filled fields ──────────────────────────────────────────────────
    printf '%s\n' "- Intended edit surface:"
    printf '%s\n' "  - (TODO: fill before editing)"
    printf '%s\n' ""
    printf '%s\n' "- Reason for broader exploration:"
    printf '%s\n' "  - (TODO: fill if needed)"
    printf '%s\n' ""

    # ── Footer ───────────────────────────────────────────────────────────────
    printf '%s\n' "--- END OF IMPACT SCAN ---"
    printf '%s\n' "This is derived evidence. Verify manually before editing."
}

main