"""Route registry contract tests for Alertmanager packet routes.

Tests that all Alertmanager packet routes are registered and conform to the route contract.

Routes tested:
- GET /api/runs/{run_id}/alertmanager-sources/review-packet
- GET /api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet
- POST /api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet/probe
- GET /api/runs/{run_id}/alertmanager-sources/{source_id}/promotion-review

Run with: python -m pytest tests/unit/test_alertmanager_packet_routes.py -v
"""

from __future__ import annotations

import unittest


class TestAlertmanagerPacketRouteRegistry(unittest.TestCase):
    """Route registry contract tests for Alertmanager packet routes."""

    def test_review_packet_route_registered(self) -> None:
        """Review packet route must be registered in route registry."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        # Find the review packet route
        review_routes = [r for r in NEXTCHECK_ROUTES if "review-packet" in r.path and "alertmanager-sources" in r.path]
        self.assertGreater(len(review_routes), 0, "Review packet route must be registered")

        # Check it's a GET route
        route = review_routes[0]
        self.assertEqual(route.method, "GET")
        self.assertEqual(route.match, "template")
        self.assertIn("run_id", route.path_params)

    def test_debug_packet_route_registered(self) -> None:
        """Debug packet route must be registered in route registry."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        # Find the debug packet route (GET, not probe)
        debug_routes = [
            r for r in NEXTCHECK_ROUTES
            if "debug-packet" in r.path
            and "alertmanager-sources" in r.path
            and r.method == "GET"
            and "/probe" not in r.path
        ]
        self.assertGreater(len(debug_routes), 0, "Debug packet route must be registered")

        # Check path params
        route = debug_routes[0]
        self.assertEqual(route.match, "template")
        self.assertIn("run_id", route.path_params)
        self.assertIn("source_id", route.path_params)

    def test_debug_packet_probe_route_registered(self) -> None:
        """Debug packet probe route must be registered in route registry."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        # Find the probe route
        probe_routes = [
            r for r in NEXTCHECK_ROUTES
            if "debug-packet/probe" in r.path
            and "alertmanager-sources" in r.path
            and r.method == "POST"
        ]
        self.assertGreater(len(probe_routes), 0, "Debug packet probe route must be registered")

        # Check path params
        route = probe_routes[0]
        self.assertEqual(route.match, "template")
        self.assertIn("run_id", route.path_params)
        self.assertIn("source_id", route.path_params)

    def test_promotion_review_route_registered(self) -> None:
        """Promotion review route must be registered in route registry."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        # Find the promotion review route
        promotion_routes = [
            r for r in NEXTCHECK_ROUTES
            if "promotion-review" in r.path
            and "alertmanager-sources" in r.path
        ]
        self.assertGreater(len(promotion_routes), 0, "Promotion review route must be registered")

        # Check it's a GET route
        route = promotion_routes[0]
        self.assertEqual(route.method, "GET")
        self.assertEqual(route.match, "template")
        self.assertIn("run_id", route.path_params)
        self.assertIn("source_id", route.path_params)


class TestAlertmanagerPacketRoutePaths(unittest.TestCase):
    """Tests for exact route path patterns."""

    def test_review_packet_exact_path(self) -> None:
        """Review packet route must have exact path pattern."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (r for r in NEXTCHECK_ROUTES if "alertmanager-sources/review-packet" in r.path),
            None,
        )
        self.assertIsNotNone(route, "Review packet route must exist")
        self.assertEqual(
            route.path,  # type: ignore[union-attr]
            "/api/runs/{run_id}/alertmanager-sources/review-packet",
        )

    def test_debug_packet_exact_path(self) -> None:
        """Debug packet route must have exact path pattern."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if "/debug-packet" in r.path and "/probe" not in r.path and r.method == "GET"
            ),
            None,
        )
        self.assertIsNotNone(route, "Debug packet route must exist")
        self.assertEqual(
            route.path,  # type: ignore[union-attr]
            "/api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet",
        )

    def test_debug_packet_probe_exact_path(self) -> None:
        """Debug packet probe route must have exact path pattern."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (r for r in NEXTCHECK_ROUTES if "/debug-packet/probe" in r.path),
            None,
        )
        self.assertIsNotNone(route, "Debug packet probe route must exist")
        self.assertEqual(
            route.path,  # type: ignore[union-attr]
            "/api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet/probe",
        )

    def test_promotion_review_exact_path(self) -> None:
        """Promotion review route must have exact path pattern."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (r for r in NEXTCHECK_ROUTES if "/promotion-review" in r.path),
            None,
        )
        self.assertIsNotNone(route, "Promotion review route must exist")
        self.assertEqual(
            route.path,  # type: ignore[union-attr]
            "/api/runs/{run_id}/alertmanager-sources/{source_id}/promotion-review",
        )


class TestAlertmanagerPacketRouteHandlers(unittest.TestCase):
    """Tests for route handler configuration."""

    def test_review_packet_handler_configured(self) -> None:
        """Review packet route must have handler configured."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (r for r in NEXTCHECK_ROUTES if "alertmanager-sources/review-packet" in r.path),
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
                if "/debug-packet" in r.path and "/probe" not in r.path and r.method == "GET"
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
            (r for r in NEXTCHECK_ROUTES if "/debug-packet/probe" in r.path),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.handler)  # type: ignore[union-attr]
        self.assertIn("alertmanager", route.handler)  # type: ignore[union-attr]

    def test_promotion_review_handler_configured(self) -> None:
        """Promotion review route must have handler configured."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (r for r in NEXTCHECK_ROUTES if "/promotion-review" in r.path),
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
            (r for r in NEXTCHECK_ROUTES if "alertmanager-sources/review-packet" in r.path),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.responses)  # type: ignore[union-attr]
        self.assertGreater(len(route.responses), 0)  # type: ignore[union-attr]

        # Should have 200 response
        response_200 = next((r for r in route.responses if r.status_code == 200), None)  # type: ignore[union-attr]
        self.assertIsNotNone(response_200, "Route must have 200 response")

    def test_debug_packet_response_schema(self) -> None:
        """Debug packet route must have response schema."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (
                r
                for r in NEXTCHECK_ROUTES
                if "/debug-packet" in r.path and "/probe" not in r.path and r.method == "GET"
            ),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.responses)  # type: ignore[union-attr]
        self.assertGreater(len(route.responses), 0)  # type: ignore[union-attr]

        # Should have 200 response
        response_200 = next((r for r in route.responses if r.status_code == 200), None)  # type: ignore[union-attr]
        self.assertIsNotNone(response_200, "Route must have 200 response")

    def test_debug_packet_probe_response_schema(self) -> None:
        """Debug packet probe route must have response schema."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (r for r in NEXTCHECK_ROUTES if "/debug-packet/probe" in r.path),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.responses)  # type: ignore[union-attr]
        self.assertGreater(len(route.responses), 0)  # type: ignore[union-attr]

        # Should have 200 response
        response_200 = next((r for r in route.responses if r.status_code == 200), None)  # type: ignore[union-attr]
        self.assertIsNotNone(response_200, "Route must have 200 response")

    def test_promotion_review_response_schema(self) -> None:
        """Promotion review route must have response schema."""
        from k8s_diag_agent.ui.api_routes_nextcheck import NEXTCHECK_ROUTES

        route = next(
            (r for r in NEXTCHECK_ROUTES if "/promotion-review" in r.path),
            None,
        )
        self.assertIsNotNone(route)
        self.assertIsNotNone(route.responses)  # type: ignore[union-attr]
        self.assertGreater(len(route.responses), 0)  # type: ignore[union-attr]

        # Should have 200 response
        response_200 = next((r for r in route.responses if r.status_code == 200), None)  # type: ignore[union-attr]
        self.assertIsNotNone(response_200, "Route must have 200 response")


if __name__ == "__main__":
    unittest.main()
