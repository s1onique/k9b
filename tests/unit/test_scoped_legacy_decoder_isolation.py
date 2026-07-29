"""Architecture/source guard for the legacy decoder isolation boundary.

ACT-K9B-HULK-PROMOTION-SCOPED-CLIENT-TYPED-HTTP-SEAM01.

The active scoped HTTP path
(``SchedulerClient.promote_alert_signals_scoped``) MUST consume
only the canonical scoped types:

* ``PromoteAlertSignalsRequest``
* ``IncidentPromotionResult``
* ``BoundScopedPromotionResult``
* ``ScopedPromotionHttpRequestContext``
* ``ScopedPromotionHttpSucceeded``

It MUST NOT import or call any of the legacy snake_case symbols:

* ``PromotionResponse``
* ``PromotionHttpWireResult``
* ``BoundPromotionHttpWireResult``
* ``_coerce_promotion_response``
* the ``promotion_http_wire_decode`` module

The module docstrings are advisory; this AST-based source guard
provides a deterministic, machine-checkable boundary so a future
import cannot silently route the scoped client through the legacy
decoder.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCOPED_CLIENT_FILES: tuple[Path, ...] = (
    REPO_ROOT
    / "src"
    / "k8s_diag_agent"
    / "ui"
    / "server_incident_internal_fetch.py",
    REPO_ROOT
    / "src"
    / "k8s_diag_agent"
    / "ui"
    / "server_incident_internal_scoped_client.py",
    REPO_ROOT
    / "src"
    / "k8s_diag_agent"
    / "collect"
    / "promotion_scoped_http_seam.py",
)

FORBIDDEN_IMPORT_MODULES: tuple[str, ...] = (
    "k8s_diag_agent.collect.promotion_http_wire_decode",
    "k8s_diag_agent.collect.promotion_http_wire_types",
    "k8s_diag_agent.collect.promotion_http_wire_semantics",
    "k8s_diag_agent.collect.promotion_http_wire_binding",
    "k8s_diag_agent.collect.promotion_http_wire_result",
    "k8s_diag_agent.ui.server_incident_internal_models",
)

FORBIDDEN_NAMES: tuple[str, ...] = (
    "PromotionResponse",
    "PromotionHttpWireResult",
    "PromotionWireRecord",
    "BoundPromotionHttpWireResult",
    "_coerce_promotion_response",
)

ALLOWED_SCOPED_REFS: tuple[str, ...] = (
    "PromoteAlertSignalsRequest",
    "IncidentPromotionResult",
    "BoundScopedPromotionResult",
    "ScopedPromotionHttpRequestContext",
    "ScopedPromotionHttpSucceeded",
)


def _typed_scoped_class_source() -> str:
    """Return the source of ``ScopedSchedulerClient`` plus any helper
    functions it references.
    """
    text = SCOPED_CLIENT_FILES[1].read_text(encoding="utf-8")
    tree = ast.parse(text)
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ScopedSchedulerClient":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(
                        ast.get_source_segment(text, item) or ""
                    )
    return "\n".join(out)


class TestLegacyDecoderUnreachableFromScopedClient:
    @pytest.mark.parametrize("file", SCOPED_CLIENT_FILES, ids=lambda p: p.name)
    def test_scoped_client_source_parses(self, file: Path) -> None:
        """Sanity: each scoped client file must still parse."""
        text = file.read_text(encoding="utf-8")
        ast.parse(text)

    @pytest.mark.parametrize("file", SCOPED_CLIENT_FILES, ids=lambda p: p.name)
    @pytest.mark.parametrize("module", FORBIDDEN_IMPORT_MODULES)
    def test_no_import_of_legacy_module(
        self, file: Path, module: str
    ) -> None:
        text = file.read_text(encoding="utf-8")
        pattern_from = re.compile(
            rf"^\s*from\s+{re.escape(module)}\b",
            re.MULTILINE,
        )
        pattern_import = re.compile(
            rf"^\s*import\s+{re.escape(module)}\b",
            re.MULTILINE,
        )
        assert not pattern_from.search(text), (
            f"scoped client must not import from legacy module {module!r}"
        )
        assert not pattern_import.search(text), (
            f"scoped client must not import from legacy module {module!r}"
        )

    @pytest.mark.parametrize("name", FORBIDDEN_NAMES)
    def test_no_reference_to_legacy_name_in_typed_client(
        self, name: str
    ) -> None:
        """``ScopedSchedulerClient`` must not name the legacy
        snake_case types. The check uses word boundaries so the
        substrings in identifiers like ``PromotionResponseDecodingStage``
        do not trigger a false positive.
        """
        typed_source = _typed_scoped_class_source()
        pattern = re.compile(rf"\b{re.escape(name)}\b")
        assert not pattern.search(typed_source), (
            f"scoped client must not reference legacy symbol {name!r}"
        )

    def test_scoped_method_only_references_allowed_types(self) -> None:
        """Every name referenced inside ``promote_alert_signals_scoped``
        must be one of the canonical scoped types, an in-method local,
        a stdlib symbol, or a documented transport helper. This is a
        soft check that fails loudly if a legacy name slips in.
        """
        typed_source = _typed_scoped_class_source()
        for forbidden in FORBIDDEN_NAMES:
            pattern = re.compile(rf"\b{re.escape(forbidden)}\b")
            assert not pattern.search(typed_source), (
                f"scoped method body must not reference {forbidden!r}"
            )

    @pytest.mark.parametrize(
        "file",
        [SCOPED_CLIENT_FILES[1]],  # only the typed client file
        ids=lambda p: p.name,
    )
    def test_allowed_scoped_types_are_present(self, file: Path) -> None:
        """The typed client file must reference the canonical request
        type to demonstrate the wired binding. The seam module and
        the legacy fetch module reference the request type
        transitively (via typed context or via the legacy method)
        and are not bound by this check.
        """
        text = file.read_text(encoding="utf-8")
        assert "PromoteAlertSignalsRequest" in text, (
            f"{file.name} must reference the canonical request type"
        )

    def test_scoped_client_method_uses_canonical_binding(self) -> None:
        """``ScopedSchedulerClient.promote_alert_signals_scoped``
        must reference the canonical bound-result type.
        """
        text = SCOPED_CLIENT_FILES[1].read_text(encoding="utf-8")
        assert "BoundScopedPromotionResult" in text, (
            "scoped client must reference the canonical binding type"
        )
        assert "ScopedPromotionHttpRequestContext" in text, (
            "scoped client must reference the canonical request context"
        )
        assert "ScopedPromotionHttpSucceeded" in text, (
            "scoped client must reference the canonical success variant"
        )
