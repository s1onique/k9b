"""API route dispatcher with lazy handler import resolution.

This module provides the dispatch mechanism that makes API_ROUTES the single
source of truth for both HTTP routing and OpenAPI documentation.

Key design principles:
1. Lazy imports: handlers are loaded on-demand to avoid circular imports
2. String import paths: registry entries use "module:function" notation
3. Path matching: supports both exact and template paths with parameter extraction
4. Handler normalization: all handlers are wrapped to a consistent signature
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api_contract_types import APIOperation
    from .server_reads import HealthUIRequestHandler

# Type alias for handler functions with normalized signature
# Handler receives: (handler, query, path_params)
# Handler returns: None (sends response directly)
NormalizedHandler = Callable[..., None]


@dataclass(frozen=True)
class MatchedAPIOperation:
    """Result of a successful route match."""

    operation: APIOperation
    path_params: dict[str, str]


# Cache for resolved handlers to avoid repeated imports
_handler_cache: dict[str, NormalizedHandler] = {}


def resolve_handler(handler_path: str) -> NormalizedHandler:
    """Resolve a handler import path to a callable.

    Args:
        handler_path: Import path like "module.submodule:function"

    Returns:
        The resolved callable handler

    Raises:
        ImportError: If the module cannot be imported
        AttributeError: If the function doesn't exist in the module
    """
    if handler_path in _handler_cache:
        return _handler_cache[handler_path]

    module_path, _, function_name = handler_path.partition(":")
    if not function_name:
        raise ValueError(f"Invalid handler path: {handler_path!r} (missing ':function')")

    module = import_module(module_path)
    handler: NormalizedHandler = getattr(module, function_name)

    _handler_cache[handler_path] = handler
    return handler


def find_api_operation(method: str, route: str) -> MatchedAPIOperation | None:
    """Find a matching API operation for the given method and route.

    This function searches the API_ROUTES registry for a matching operation.
    It supports both exact path matching and template path matching.

    Args:
        method: HTTP method (GET, POST, etc.)
        route: Request path

    Returns:
        MatchedAPIOperation with operation and extracted path_params, or None
    """
    from .api_routes_registry import API_ROUTES

    method_upper = method.upper()

    for op in API_ROUTES:
        if op.method.upper() != method_upper:
            continue

        if op.match == "exact":
            if op.path == route:
                return MatchedAPIOperation(operation=op, path_params={})
        elif op.match == "template":
            # Template matching: /api/incidents/{incident_id}
            match_result = _match_template(op.path, route, op.path_params)
            if match_result is not None:
                return MatchedAPIOperation(operation=op, path_params=match_result)

    return None


def _match_template(
    template: str,
    route: str,
    expected_params: tuple[str, ...],
) -> dict[str, str] | None:
    """Match a route against a template path and extract parameters.

    Args:
        template: Path template like "/api/incidents/{incident_id}"
        route: Actual request path
        expected_params: Expected parameter names from registry

    Returns:
        Dict of extracted path params, or None if no match
    """
    # Build regex from template
    # Replace {param} with named capture group
    param_names: list[str] = []

    for param in re.finditer(r"\{(\w+)\}", template):
        param_names.append(param.group(1))

    # Escape special regex characters EXCEPT { and }
    # First, temporarily replace {param} with a placeholder
    temp_template = template
    placeholders: dict[str, str] = {}
    for i, param_name in enumerate(param_names):
        placeholder = f"__PARAM_{i}__"
        placeholders[placeholder] = param_name
        temp_template = temp_template.replace("{" + param_name + "}", placeholder)

    # Now escape the template (no braces to worry about)
    escaped = re.escape(temp_template)

    # Replace placeholders with named capture groups
    for placeholder, param_name in placeholders.items():
        escaped = escaped.replace(placeholder, f"(?P<{param_name}>[^/]+)")

    try:
        regex = re.compile(f"^{escaped}$")
    except re.error:
        return None

    match = regex.match(route)
    if not match:
        return None

    # Extract params from match
    path_params: dict[str, str] = match.groupdict()

    # Validate expected params are present
    for expected in expected_params:
        if expected not in path_params:
            return None

    return path_params


def dispatch_api_operation(
    handler: HealthUIRequestHandler,
    method: str,
    route: str,
    query: str,
) -> bool:
    """Dispatch an API request to the matching handler.

    This is the main entry point for API dispatch. It:
    1. Finds the matching operation in API_ROUTES
    2. Resolves the handler import path to a callable
    3. Calls the handler with normalized arguments

    Args:
        handler: The HTTP request handler instance
        method: HTTP method (GET, POST, etc.)
        route: Request path
        query: Query string

    Returns:
        True if a route was matched and handled, False otherwise
    """
    matched = find_api_operation(method, route)
    if matched is None:
        return False

    op = matched.operation

    # Skip if no handler is defined (shouldn't happen after registry is complete)
    if not op.handler:
        return False

    try:
        handler_func = resolve_handler(op.handler)
    except (ImportError, AttributeError, ValueError) as exc:
        # Handler resolution failed - log and return 500
        handler._status_code = 500
        handler._send_text(500, f"Handler resolution error: {exc}")
        return True

    # Call handler with normalized signature
    # The adapter will handle the conversion to handler-specific signature
    try:
        handler_func(handler, query, matched.path_params)
    except Exception:
        # Let exceptions propagate to the dispatcher's exception handler
        raise

    return True


def clear_handler_cache() -> None:
    """Clear the handler cache. Useful for testing."""
    global _handler_cache
    _handler_cache = {}
