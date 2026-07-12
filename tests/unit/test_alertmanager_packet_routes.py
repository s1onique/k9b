"""Route registry contract tests for Alertmanager packet routes.

Tests that all Alertmanager packet routes are registered and conform to the route contract.

Routes tested (post sourceId body/query migration):
- GET  /api/runs/{run_id}/alertmanager-sources/review-packet
- GET  /api/runs/{run_id}/alertmanager-sources/debug-packet?sourceId=...
- POST /api/runs/{run_id}/alertmanager-sources/debug-packet/probe
       (JSON body: {"sourceId": ...})
- GET  /api/runs/{run_id}/alertmanager-sources/promotion-review?sourceId=...

The ``{source_id}`` placeholder was removed from these paths because Starlette
path params default to ``[^/]+`` and identifiers such as
``crd:monitoring.coreos.com/v1/Alertmanager/example`` contain slashes. The
identifier now travels either in the required ``sourceId`` query parameter
(GET routes) or in the JSON request body (POST probe), so the URL path stays
stable regardless of the identifier content.

Run with: python -m pytest tests/unit/test_alertmanager_packet_routes.py -v
"""

from __future__ import annotations

import unittest


class TestAlertmanagerPacketRouteRegistry(unittest.TestCase):
    """Route registry contract tests for Alertmanager packet routes."""

    def test_review_packet_route_registered(self) -> None:
        """Review packet route must be registered in route registry."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        # Find the review packet route (exact match to avoid partial-suffix collisions).
        review_routes = [
            r
            for r in NEXTCHECK_ROUTES
            if r.path == "/api/runs/{run_id}/alertmanager-sources/review-packet"
            and r.method == "GET"
        ]
        self.assertEqual(len(review_routes), 1, "Exactly one review packet route must be registered")

        route = review_routes[0]
        self.assertEqual(route.match, "template")
        self.assertEqual(route.path_params, ("run_id",))

    def test_debug_packet_route_registered(self) -> None:
        """Debug packet route must be registered in route registry.

        ``{source_id}`` must not appear in the path; the identifier is
        transported via the required ``sourceId`` query parameter.
        """
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        debug_routes = [
            r
            for r in NEXTCHECK_ROUTES
            if r.path == "/api/runs/{run_id}/alertmanager-sources/debug-packet"
            and r.method == "GET"
        ]
        self.assertEqual(len(debug_routes), 1, "Exactly one debug packet route must be registered")

        route = debug_routes[0]
        self.assertEqual(route.match, "template")
        self.assertEqual(route.path_params, ("run_id",))
        self.assertNotIn("source_id", route.path_params)
        self.assertIn("sourceId", route.required_query_params)

    def test_debug_packet_probe_route_registered(self) -> None:
        """Debug packet probe route must be registered in route registry.

        ``{source_id}`` must not appear in the path; the identifier is
        transported in the JSON request body.
        """
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        probe_routes = [
            r
            for r in NEXTCHECK_ROUTES
            if r.path == "/api/runs/{run_id}/alertmanager-sources/debug-packet/probe"
            and r.method == "POST"
        ]
        self.assertEqual(len(probe_routes), 1, "Exactly one debug packet probe route must be registered")

        route = probe_routes[0]
        self.assertEqual(route.match, "template")
        self.assertEqual(route.path_params, ("run_id",))
        self.assertNotIn("source_id", route.path_params)
        self.assertIsNotNone(route.request_schema, "Probe route must carry a request schema for the body")

    def test_promotion_review_route_registered(self) -> None:
        """Promotion review route must be registered in route registry.

        ``{source_id}`` must not appear in the path; the identifier is
        transported via the required ``sourceId`` query parameter.
        """
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        promotion_routes = [
            r
            for r in NEXTCHECK_ROUTES
            if r.path == "/api/runs/{run_id}/alertmanager-sources/promotion-review"
            and r.method == "GET"
        ]
        self.assertEqual(len(promotion_routes), 1, "Exactly one promotion review route must be registered")

        route = promotion_routes[0]
        self.assertEqual(route.match, "template")
        self.assertEqual(route.path_params, ("run_id",))
        self.assertNotIn("source_id", route.path_params)
        self.assertIn("sourceId", route.required_query_params)


class TestAlertmanagerPacketRoutePaths(unittest.TestCase):
    """Tests for exact route path patterns."""

    def test_review_packet_exact_path(self) -> None:
        """Review packet route must have exact path pattern."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/review-packet"
            ),
            None,
        )
        self.assertIsNotNone(route, "Review packet route must exist")
        self.assertEqual(
            route.path,  # type: ignore[union-attr]
            "/api/runs/{run_id}/alertmanager-sources/review-packet",
        )

    def test_debug_packet_exact_path(self) -> None:
        """Debug packet route must have exact path pattern.

        ``{source_id}`` must not appear in the path; the identifier is
        transported via the required ``sourceId`` query parameter so that
        slashes in the identifier are not parsed as path segments.
        """
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/debug-packet"
                and r.method == "GET"
            ),
            None,
        )
        self.assertIsNotNone(route, "Debug packet route must exist")
        self.assertEqual(
            route.path,  # type: ignore[union-attr]
            "/api/runs/{run_id}/alertmanager-sources/debug-packet",
        )

    def test_debug_packet_probe_exact_path(self) -> None:
        """Debug packet probe route must have exact path pattern.

        ``{source_id}`` must not appear in the path; the identifier is
        transported in the JSON request body so that slashes in the
        identifier are not parsed as path segments.
        """
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/debug-packet/probe"
                and r.method == "POST"
            ),
            None,
        )
        self.assertIsNotNone(route, "Debug packet probe route must exist")
        self.assertEqual(
            route.path,  # type: ignore[union-attr]
            "/api/runs/{run_id}/alertmanager-sources/debug-packet/probe",
        )

    def test_promotion_review_exact_path(self) -> None:
        """Promotion review route must have exact path pattern.

        ``{source_id}`` must not appear in the path; the identifier is
        transported via the required ``sourceId`` query parameter so that
        slashes in the identifier are not parsed as path segments.
        """
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/promotion-review"
                and r.method == "GET"
            ),
            None,
        )
        self.assertIsNotNone(route, "Promotion review route must exist")
        self.assertEqual(
            route.path,  # type: ignore[union-attr]
            "/api/runs/{run_id}/alertmanager-sources/promotion-review",
        )


class TestAlertmanagerPacketRouteHandlers(unittest.TestCase):
    """Tests for route handler configuration."""

    def test_review_packet_handler_configured(self) -> None:
        """Review packet route must have handler configured."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/review-packet"
            ),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.handler)  # type: ignore[union-attr]
        self.assertIn("alertmanager", route.handler)  # type: ignore[union-attr]

    def test_debug_packet_handler_configured(self) -> None:
        """Debug packet route must have handler configured."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/debug-packet"
                and r.method == "GET"
            ),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.handler)  # type: ignore[union-attr]
        self.assertIn("alertmanager", route.handler)  # type: ignore[union-attr]

    def test_debug_packet_probe_handler_configured(self) -> None:
        """Debug packet probe route must have handler configured."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/debug-packet/probe"
                and r.method == "POST"
            ),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.handler)  # type: ignore[union-attr]
        self.assertIn("alertmanager", route.handler)  # type: ignore[union-attr]

    def test_promotion_review_handler_configured(self) -> None:
        """Promotion review route must have handler configured."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/promotion-review"
                and r.method == "GET"
            ),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.handler)  # type: ignore[union-attr]
        self.assertIn("alertmanager", route.handler)  # type: ignore[union-attr]


class TestAlertmanagerPacketRouteResponses(unittest.TestCase):
    """Tests for route response schemas."""

    def test_review_packet_response_schema(self) -> None:
        """Review packet route must have response schema."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/review-packet"
            ),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.responses)  # type: ignore[union-attr]
        self.assertGreater(len(route.responses), 0)  # type: ignore[union-attr]

        response_200 = next((r for r in route.responses if r.status_code == 200), None)  # type: ignore[union-attr]
        self.assertIsNotNone(response_200, "Route must have 200 response")

    def test_debug_packet_response_schema(self) -> None:
        """Debug packet route must have response schema."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/debug-packet"
                and r.method == "GET"
            ),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.responses)  # type: ignore[union-attr]
        self.assertGreater(len(route.responses), 0)  # type: ignore[union-attr]

        response_200 = next((r for r in route.responses if r.status_code == 200), None)  # type: ignore[union-attr]
        self.assertIsNotNone(response_200, "Route must have 200 response")

    def test_debug_packet_probe_response_schema(self) -> None:
        """Debug packet probe route must have response schema."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/debug-packet/probe"
                and r.method == "POST"
            ),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.responses)  # type: ignore[union-attr]
        self.assertGreater(len(route.responses), 0)  # type: ignore[union-attr]

        response_200 = next((r for r in route.responses if r.status_code == 200), None)  # type: ignore[union-attr]
        self.assertIsNotNone(response_200, "Route must have 200 response")

    def test_promotion_review_response_schema(self) -> None:
        """Promotion review route must have response schema."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if r.path == "/api/runs/{run_id}/alertmanager-sources/promotion-review"
                and r.method == "GET"
            ),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.responses)  # type: ignore[union-attr]
        self.assertGreater(len(route.responses), 0)  # type: ignore[union-attr]

        response_200 = next((r for r in route.responses if r.status_code == 200), None)  # type: ignore[union-attr]
        self.assertIsNotNone(response_200, "Route must have 200 response")


if __name__ == "__main__":
    unittest.main()
