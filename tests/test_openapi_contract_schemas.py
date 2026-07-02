"""OpenAPI schema and component assertion tests.

Tests that:
- The generated OpenAPI schema is valid and well-structured
- Schema components are properly defined
- Response schemas meet requirements
"""

from __future__ import annotations

from k8s_diag_agent.ui.api_contract import build_openapi_schema


class TestOpenAPISchemaValidity:
    """Tests that the OpenAPI schema is valid."""

    def test_openapi_schema_is_valid_json(self) -> None:
        """The generated OpenAPI schema should be valid JSON."""
        schema = build_openapi_schema()
        assert isinstance(schema, dict)
        assert "openapi" in schema
        assert schema["openapi"].startswith("3.")

    def test_openapi_has_required_fields(self) -> None:
        """The schema should have all required OpenAPI fields."""
        schema = build_openapi_schema()
        assert "info" in schema
        assert "paths" in schema
        assert "servers" in schema
        assert schema["info"]["title"] == "k9b API"
        assert schema["info"]["version"] == "0.1.0"

    def test_openapi_paths_not_empty(self) -> None:
        """The schema should document at least some paths."""
        schema = build_openapi_schema()
        assert len(schema["paths"]) > 0


class TestOpenAPISchemaStructure:
    """Tests for OpenAPI schema structure."""

    def test_tags_are_defined(self) -> None:
        """Schema should define tags."""
        schema = build_openapi_schema()
        assert "tags" in schema
        assert len(schema["tags"]) > 0

        # Check for expected tags
        tag_names = {t["name"] for t in schema["tags"]}
        assert "auth" in tag_names
        assert "incidents" in tag_names
        assert "health" in tag_names

    def test_schema_components(self) -> None:
        """Schema should have proper structure."""
        schema = build_openapi_schema()

        # Each path should have at least one HTTP method
        for path, methods in schema["paths"].items():
            assert methods, f"Path {path} has no HTTP methods"
            for method, operation in methods.items():
                assert method in ("get", "post", "put", "patch", "delete")
                assert "summary" in operation
                assert "responses" in operation


class TestSchemaStrictness:
    """Tests for schema strictness requirements."""

    def test_request_body_object_schemas_disallow_extra_properties(self) -> None:
        """Request body objects should explicitly set additionalProperties: false.

        This ensures that object schemas in the OpenAPI spec are strict and will
        reject unexpected fields. Without explicit additionalProperties: false,
        JSON Schema/OpenAPI defaults allow extra properties, which can mask typos
        and version skew between client and server.
        """
        schema = build_openapi_schema()

        # Check the next-check-execution endpoint as a representative request body
        request_schema = schema["paths"]["/api/next-check-execution"]["post"]["requestBody"][
            "content"
        ]["application/json"]["schema"]

        # Request schemas must explicitly disallow extra properties
        assert request_schema["type"] == "object", "Request body must be an object schema"
        assert (
            "additionalProperties" in request_schema
        ), "Object schema must have additionalProperties key"
        assert (
            request_schema["additionalProperties"] is False
        ), "additionalProperties must be False to reject unknown fields"

    def test_open_object_schemas_allow_additional_properties(self) -> None:
        """Open object schemas (like bundle) should allow additional properties.

        The bundle field in incident review packet is intentionally open-ended
        to accept arbitrary evidence data.
        """
        schema = build_openapi_schema()

        request_schema = schema["paths"]["/api/incidents/review-packet"]["post"]["requestBody"][
            "content"
        ]["application/json"]["schema"]

        # The bundle property is an open object
        assert request_schema["type"] == "object"
        assert "properties" in request_schema
        assert "bundle" in request_schema["properties"]
        assert request_schema["properties"]["bundle"]["type"] == "object"
        assert request_schema["properties"]["bundle"].get(
            "additionalProperties", False
        ) is True, "bundle schema must allow additional properties"


class TestOpenAPIResponseSchemas:
    """Tests that operations have response schemas."""

    def test_all_success_responses_have_schema(self) -> None:
        """Non-204 success responses should have a schema."""
        schema = build_openapi_schema()
        weak: list[tuple[str, str, str]] = []

        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                for status_code, response in operation.get("responses", {}).items():
                    if not status_code.startswith("2"):
                        continue
                    if status_code == "204":
                        continue

                    content = response.get("content", {})
                    json_response = content.get("application/json")

                    if not json_response:
                        weak.append((method.upper(), path, f"{status_code} missing application/json content"))
                        continue

                    if not json_response.get("schema"):
                        weak.append((method.upper(), path, f"{status_code} missing response schema"))

        assert not weak, f"Success responses missing schemas: {weak}"
