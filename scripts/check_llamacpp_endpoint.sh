#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${LLAMA_CPP_BASE_URL:-http://192.168.99.134:32597}"
MODEL="${LLAMA_CPP_MODEL:-openai/qwen}"
OUT_DIR="${OUT_DIR:-runs/llamacpp-checks/$(date -u +%Y%m%dT%H%M%SZ)}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-90}"
ENABLE_THINKING="${LLAMA_CPP_ENABLE_THINKING:-false}"

# Normalize LLAMA_CPP_ENABLE_THINKING to valid JSON boolean
_normalize_enable_thinking() {
  local val="${1:-false}"
  case "${val,,}" in
    true|1|yes) echo "true" ;;
    *) echo "false" ;;
  esac
}
ENABLE_THINKING_JSON="$(_normalize_enable_thinking "$ENABLE_THINKING")"

mkdir -p "$OUT_DIR"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$OUT_DIR/check.log"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: missing required command: $1"
    exit 2
  fi
}

json_pretty() {
  if command -v jq >/dev/null 2>&1; then
    jq . || cat
  else
    cat
  fi
}

run_curl_json() {
  local name="$1"
  local url="$2"
  local payload="$3"
  local raw="$OUT_DIR/${name}.raw.json"
  local pretty="$OUT_DIR/${name}.json"
  local meta="$OUT_DIR/${name}.meta.txt"

  log "Running $name -> $url"

  {
    printf 'URL=%s\n' "$url"
    printf 'PAYLOAD=%s\n' "$payload"
  } > "$meta"

  set +e
  curl -sS --max-time "$TIMEOUT_SECONDS" \
    -H 'Content-Type: application/json' \
    -d "$payload" \
    "$url" > "$raw" 2>>"$OUT_DIR/check.log"
  local rc=$?
  set -e

  echo "curl_exit_code=$rc" >> "$meta"

  if [[ "$rc" -ne 0 ]]; then
    log "FAIL $name: curl exit code $rc"
    return 1
  fi

  json_pretty < "$raw" > "$pretty" || cp "$raw" "$pretty"

  if grep -q 'ฉากฉาก' "$raw"; then
    log "FAIL $name: detected repeated Thai token pattern"
    echo "thai_repetition_detected=true" >> "$meta"
    return 1
  fi

  if command -v jq >/dev/null 2>&1; then
    local content finish_reason
    content="$(jq -r '.choices[0].message.content // .choices[0].text // empty' "$raw" 2>/dev/null || true)"
    finish_reason="$(jq -r '.choices[0].finish_reason // empty' "$raw" 2>/dev/null || true)"

    printf 'finish_reason=%s\n' "$finish_reason" >> "$meta"
    printf '%s\n' "$content" > "$OUT_DIR/${name}.content.txt"

    if [[ -z "$content" ]]; then
      log "WARN $name: no content found in response"
      return 1
    fi

    if printf '%s' "$content" | jq . >/dev/null 2>&1; then
      log "PASS $name: content is valid JSON"
      echo "content_valid_json=true" >> "$meta"
      return 0
    else
      log "FAIL $name: content is not valid JSON"
      echo "content_valid_json=false" >> "$meta"
      return 1
    fi
  else
    log "WARN $name: jq not installed; saved raw output only"
    return 0
  fi
}

run_get() {
  local name="$1"
  local url="$2"
  local raw="$OUT_DIR/${name}.raw.json"
  local pretty="$OUT_DIR/${name}.json"

  log "Running GET $name -> $url"

  set +e
  curl -sS --max-time "$TIMEOUT_SECONDS" "$url" > "$raw" 2>>"$OUT_DIR/check.log"
  local rc=$?
  set -e

  echo "curl_exit_code=$rc" > "$OUT_DIR/${name}.meta.txt"

  if [[ "$rc" -ne 0 ]]; then
    log "FAIL $name: curl exit code $rc"
    return 1
  fi

  json_pretty < "$raw" > "$pretty" || cp "$raw" "$pretty"
  log "PASS $name"
  return 0
}

run_python_smoke() {
  local name="k9b_provider_smoke"
  local raw="$OUT_DIR/${name}.txt"

  if [[ ! -f "scripts/smoke_llamacpp_json.py" ]]; then
    log "SKIP $name: scripts/smoke_llamacpp_json.py not found"
    return 0
  fi

  log "Running $name"

  set +e
  LLAMA_CPP_BASE_URL="$BASE_URL" \
  LLAMA_CPP_MODEL="$MODEL" \
  LLAMA_CPP_RESPONSE_FORMAT_JSON="${LLAMA_CPP_RESPONSE_FORMAT_JSON:-false}" \
  LLAMA_CPP_TEMPERATURE="${LLAMA_CPP_TEMPERATURE:-0}" \
  python scripts/smoke_llamacpp_json.py > "$raw" 2>&1
  local rc=$?
  set -e

  echo "exit_code=$rc" > "$OUT_DIR/${name}.meta.txt"

  if grep -q 'ฉากฉาก' "$raw"; then
    log "FAIL $name: detected repeated Thai token pattern"
    return 1
  fi

  if [[ "$rc" -eq 0 ]]; then
    log "PASS $name"
    return 0
  fi

  log "FAIL $name: exit code $rc"
  return 1
}

main() {
  need_cmd curl

  log "llama.cpp endpoint check started"
  log "BASE_URL=$BASE_URL"
  log "MODEL=$MODEL"
  log "OUT_DIR=$OUT_DIR"
  log "TIMEOUT_SECONDS=$TIMEOUT_SECONDS"
  log "ENABLE_THINKING=$ENABLE_THINKING_JSON"

  local required_failures=0
  local diagnostic_failures=0

  run_get "models" "$BASE_URL/v1/models" || required_failures=$((required_failures + 1))

  local chat_payload
  chat_payload="$(cat <<JSON
{
  "model": "$MODEL",
  "messages": [
    {
      "role": "user",
      "content": "Return exactly this JSON and nothing else: {\"ok\": true}"
    }
  ],
  "temperature": 0,
  "max_tokens": 64,
  "chat_template_kwargs": {
    "enable_thinking": $ENABLE_THINKING_JSON
  }
}
JSON
)"
  run_curl_json "chat_minimal" "$BASE_URL/v1/chat/completions" "$chat_payload" || required_failures=$((required_failures + 1))

  local chat_payload_repeat_penalty
  chat_payload_repeat_penalty="$(cat <<JSON
{
  "model": "$MODEL",
  "messages": [
    {
      "role": "user",
      "content": "Return exactly this JSON and nothing else: {\"ok\": true}"
    }
  ],
  "temperature": 0,
  "top_p": 0.8,
  "repeat_penalty": 1.15,
  "seed": 42,
  "max_tokens": 64,
  "chat_template_kwargs": {
    "enable_thinking": $ENABLE_THINKING_JSON
  }
}
JSON
)"
  run_curl_json "chat_repeat_penalty" "$BASE_URL/v1/chat/completions" "$chat_payload_repeat_penalty" || required_failures=$((required_failures + 1))

  local chat_payload_json_mode
  chat_payload_json_mode="$(cat <<JSON
{
  "model": "$MODEL",
  "messages": [
    {
      "role": "user",
      "content": "Return exactly this JSON and nothing else: {\"ok\": true}"
    }
  ],
  "temperature": 0,
  "max_tokens": 64,
  "response_format": {
    "type": "json_object"
  },
  "chat_template_kwargs": {
    "enable_thinking": $ENABLE_THINKING_JSON
  }
}
JSON
)"
  run_curl_json "chat_response_format_json" "$BASE_URL/v1/chat/completions" "$chat_payload_json_mode" || required_failures=$((required_failures + 1))

  local completion_payload
  completion_payload="$(cat <<JSON
{
  "model": "$MODEL",
  "prompt": "Return exactly this JSON and nothing else: {\"ok\": true}\\n",
  "temperature": 0,
  "max_tokens": 64
}
JSON
)"
  if ! run_curl_json "completion_minimal" "$BASE_URL/v1/completions" "$completion_payload"; then
    diagnostic_failures=$((diagnostic_failures + 1))
    log "WARN completion_minimal: diagnostic check failed, not blocking overall status"
  fi

  run_python_smoke || required_failures=$((required_failures + 1))

  {
    echo "{"
    echo "  \"base_url\": \"${BASE_URL}\","
    echo "  \"model\": \"${MODEL}\","
    echo "  \"out_dir\": \"${OUT_DIR}\","
    echo "  \"required_failures\": ${required_failures},"
    echo "  \"diagnostic_failures\": ${diagnostic_failures},"
    if [[ "$required_failures" -eq 0 ]]; then
      echo "  \"overall_status\": \"PASS\""
    else
      echo "  \"overall_status\": \"FAIL\""
    fi
    echo "}"
  } > "$OUT_DIR/summary.json"

  log "llama.cpp endpoint check finished; required_failures=$required_failures, diagnostic_failures=$diagnostic_failures"
  log "Artifacts written to: $OUT_DIR"

  if [[ "$required_failures" -eq 0 ]]; then
    log "OVERALL: PASS"
    exit 0
  else
    log "OVERALL: FAIL"
    exit 1
  fi
}

main "$@"
