"""Response parsing for llama.cpp provider."""
from __future__ import annotations

import json
from typing import Any, NoReturn

from .llamacpp_provider_errors import LLMResponseParseError


def _type_name(value: Any) -> str:
    """Get type name for error messages."""
    if value is None:
        return "NoneType"
    return type(value).__name__


def _payload_snippet(value: Any, limit: int = 320) -> str:
    """Create a compact snippet of a payload for error messages."""
    try:
        serialized = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        serialized = repr(value)
    snippet = " ".join(serialized.split())
    if len(snippet) > limit:
        snippet = snippet[:limit].rstrip()
        snippet = f"{snippet}…"
    return snippet


def _response_body_snippet(response: Any, limit: int = 320) -> str | None:
    """Extract a compact snippet from HTTP response body."""
    raw = getattr(response, "text", None)
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    snippet = " ".join(text.split())
    if len(snippet) > limit:
        snippet = snippet[:limit].rstrip()
        snippet = f"{snippet}…"
    return snippet


def _format_http_status(response: Any) -> str | None:
    """Format HTTP status for error messages."""
    status_code = getattr(response, "status_code", None)
    if status_code is None:
        return None
    reason = getattr(response, "reason", "") or ""
    reason_text = f" {reason}" if reason else ""
    return f"HTTP {status_code}{reason_text}"


def _base_url_mutually_exclusive_v1(base_url: str) -> bool:
    """Check if base_url already includes /v1 suffix."""
    return base_url.rstrip('/').endswith('/v1')


def _extract_response_diagnostics(data: Any, max_prefix_len: int = 200) -> dict[str, Any]:
    """Extract structured output diagnostics from LLM response."""
    diagnostics: dict[str, Any] = {}
    try:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            top_choice = choices[0]
            if isinstance(top_choice, dict):
                finish_reason = top_choice.get("finish_reason")
                if finish_reason is not None:
                    diagnostics["finish_reason"] = str(finish_reason)
                message = top_choice.get("message")
                content: str | None = None
                if isinstance(message, dict):
                    content = message.get("content")
                elif isinstance(message, str):
                    content = message
                if content is not None:
                    diagnostics["response_content_chars"] = len(content)
                    if content:
                        prefix = content[:max_prefix_len]
                        diagnostics["response_content_prefix"] = prefix
    except Exception:  # noqa: BLE001
        pass
    return diagnostics


def _raise_shape_error(path: str, expected: str, value: Any, debug_ctx: str) -> NoReturn:
    """Raise a structured shape error."""
    raise ValueError(
        f"llama.cpp response {path} expected {expected} but got {_type_name(value)}; {debug_ctx}"
    )


def _extract_text_from_content(node: Any, path: str) -> str | None:
    """Extract text content from a nested structure."""
    if node is None:
        return None
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        nested_path = f"{path}['content']"
        return _extract_text_from_content(node.get("content"), nested_path)
    _raise_shape_error(path, "a string or nested 'content' object", node, "")


def extract_assessment(data: Any, *, max_tokens: int | None = None) -> dict[str, Any]:
    """Extract and parse assessment JSON from llama.cpp response.

    Args:
        data: The parsed JSON response from the LLM
        max_tokens: The max_tokens limit used for the request (for diagnostics)

    Returns:
        The parsed assessment dictionary

    Raises:
        ValueError: If response structure is invalid or content is not valid JSON
    """
    payload_snippet = _payload_snippet(data)
    if not isinstance(data, dict):
        raise ValueError(
            f"llama.cpp response expected an object but got {_type_name(data)}; "
            f"response snippet: {payload_snippet}"
        )

    def debug_context() -> str:
        return f"response snippet: {payload_snippet}"

    choices = data.get("choices")
    if not isinstance(choices, list):
        _raise_shape_error("'choices'", "a list", choices, debug_context())
    if not choices:
        raise ValueError(
            f"llama.cpp response 'choices' expected a non-empty list; {debug_context()}"
        )
    top_choice = choices[0]
    if not isinstance(top_choice, dict):
        _raise_shape_error("'choices[0]'", "a dictionary", top_choice, debug_context())

    message = top_choice.get("message")
    if message is not None and not isinstance(message, dict | str):
        _raise_shape_error("'choices[0]['message']'", "a dictionary or string", message, debug_context())

    content: str | None
    if isinstance(message, str):
        content = message
    elif isinstance(message, dict):
        content = _extract_text_from_content(
            message.get("content"), "'choices[0]['message']['content']'"
        )
    else:
        content = None

    if content is None:
        text_field = top_choice.get("text")
        if text_field is None:
            raise ValueError(
                f"llama.cpp response choice lacks textual content; response snippet: {payload_snippet}"
            )
        if not isinstance(text_field, str):
            _raise_shape_error("'choices[0]['text']'", "a string", text_field, debug_context())
        content = text_field

    if not content:
        raise ValueError(
            f"llama.cpp response content is empty; response snippet: {payload_snippet}"
        )

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        resp_diags = _extract_response_diagnostics(data)
        excerpt = content[:500]
        excerpt_snippet = " ".join(excerpt.split()) or excerpt
        if len(content) > 500:
            excerpt_snippet = f"{excerpt_snippet}…"
        finish_reason = resp_diags.get("finish_reason")
        stopped_by_length = finish_reason == "length" if finish_reason else False
        raise LLMResponseParseError(
            f"llama.cpp response text content is not valid JSON (first 500 chars: {excerpt_snippet}); "
            f"response snippet: {payload_snippet}",
            finish_reason=resp_diags.get("finish_reason"),
            response_content_chars=resp_diags.get("response_content_chars"),
            response_content_prefix=resp_diags.get("response_content_prefix"),
            completion_stopped_by_length=stopped_by_length,
            max_tokens=max_tokens,
        ) from exc

    if not isinstance(parsed, dict):
        _raise_shape_error("message JSON", "an object", parsed, debug_context())

    return parsed


def build_error_message(
    base_url: str,
    endpoint: str,
    exc: BaseException,
    response: Any | None,
    timeout_seconds: int,
) -> str:
    """Build a human-readable error message for request failures."""
    context: list[str] = [f"Endpoint {endpoint} (LLAMA_CPP_BASE_URL={base_url})"]
    if _base_url_mutually_exclusive_v1(base_url):
        context.append(
            "Base URL already includes '/v1'; provider still appends '/v1/chat/completions'. "
            "Remove the trailing '/v1' if you only meant to specify the server root."
        )
    if response is not None:
        status_text = _format_http_status(response)
        if status_text:
            context.append(status_text)
        snippet = _response_body_snippet(response)
        if snippet:
            context.append(f"Response snippet: {snippet}")
    else:
        context.append(f"{exc.__class__.__name__}: {exc}")
    context.append(f"timeout={timeout_seconds}s")
    return "llama.cpp request failed: " + "; ".join(context)


__all__ = [
    "extract_assessment",
    "build_error_message",
    "_payload_snippet",
    "_extract_response_diagnostics",
]
