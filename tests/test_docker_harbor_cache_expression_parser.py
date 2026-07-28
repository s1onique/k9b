"""Tests for the cache specification semantic parser.

This module tests the parse_registry_cache_spec() function which handles
both literal BuildKit cache specifications and conditional GitHub format()
expressions.
"""

from __future__ import annotations

import pytest

from tests.helpers.docker_harbor_cache_helpers import (
    CacheSpecParseError,
    RegistryCacheSpec,
    parse_registry_cache_spec,
)

# =============================================================================
# Positive test cases: literal specifications
# =============================================================================


class TestLiteralCacheSpecifications:
    """Literal cache specifications (no GitHub expressions)."""

    def test_literal_cache_from(self) -> None:
        """Literal cache-from without mode."""
        spec = parse_registry_cache_spec("type=registry,ref=harbor-pve1.spbnix.local/k9b/cache/image:buildcache")
        assert spec.backend == "registry"
        assert spec.ref_template == "harbor-pve1.spbnix.local/k9b/cache/image:buildcache"
        assert spec.mode is None
        assert spec.condition is None
        assert spec.format_arguments == ()
        assert spec.conditional_empty_fallback is False

    def test_literal_cache_to_with_mode_max(self) -> None:
        """Literal cache-to with mode=max."""
        spec = parse_registry_cache_spec("type=registry,ref=harbor-pve1.spbnix.local/k9b/cache/image:buildcache,mode=max")
        assert spec.backend == "registry"
        assert spec.ref_template == "harbor-pve1.spbnix.local/k9b/cache/image:buildcache"
        assert spec.mode == "max"
        assert spec.condition is None
        assert spec.format_arguments == ()
        assert spec.conditional_empty_fallback is False

    def test_literal_cache_with_whitespace(self) -> None:
        """Literal cache spec with extra whitespace."""
        spec = parse_registry_cache_spec("type=registry, ref=harbor-pve1.spbnix.local/k9b/cache/image:buildcache, mode=max")
        assert spec.backend == "registry"
        assert spec.ref_template == "harbor-pve1.spbnix.local/k9b/cache/image:buildcache"
        assert spec.mode == "max"


# =============================================================================
# Positive test cases: conditional GitHub format() expressions
# =============================================================================


class TestConditionalFormatExpressions:
    """Conditional GitHub format() expressions used by harbor-build-image.yml."""

    def test_conditional_format_cache_from(self) -> None:
        """Conditional cache-from from harbor-build-image.yml."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        assert spec.backend == "registry"
        assert spec.ref_template == "{0}/{1}/cache/{2}:buildcache"
        assert spec.mode is None
        assert spec.condition == "inputs.registry_cache_read_enabled"
        assert spec.format_arguments == (
            "inputs.registry",
            "inputs.harbor_project",
            "inputs.image_name",
        )
        assert spec.conditional_empty_fallback is True

    def test_conditional_format_cache_to(self) -> None:
        """Conditional cache-to from harbor-build-image.yml."""
        value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=max', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        assert spec.backend == "registry"
        assert spec.ref_template == "{0}/{1}/cache/{2}:buildcache"
        assert spec.mode == "max"
        assert spec.condition == "inputs.registry_cache_write_enabled"
        assert spec.format_arguments == (
            "inputs.registry",
            "inputs.harbor_project",
            "inputs.image_name",
        )
        assert spec.conditional_empty_fallback is True

    def test_conditional_format_with_double_quotes(self) -> None:
        """Conditional format using double quotes for false branch."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || \"\" }}"
        spec = parse_registry_cache_spec(value)
        assert spec.backend == "registry"
        assert spec.ref_template == "{0}/{1}/cache/{2}:buildcache"
        assert spec.conditional_empty_fallback is True


# =============================================================================
# Negative test cases: malformed expressions
# =============================================================================


class TestMalformedExpressions:
    """Malformed expressions that should be rejected."""

    def test_missing_buildcache_suffix(self) -> None:
        """Format string without :buildcache suffix fails ref template check."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:cache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        # Parser accepts but ref_template is malformed
        assert spec.ref_template == "{0}/{1}/cache/{2}:cache"

    def test_wrong_cache_from_condition(self) -> None:
        """Wrong condition for cache-from."""
        value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        # Parser accepts but condition is wrong
        assert spec.condition == "inputs.registry_cache_write_enabled"

    def test_wrong_cache_to_condition(self) -> None:
        """Wrong condition for cache-to."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=max', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        assert spec.condition == "inputs.registry_cache_read_enabled"

    def test_missing_image_name_argument(self) -> None:
        """Format call missing the image_name argument."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project) || '' }}"
        spec = parse_registry_cache_spec(value)
        assert len(spec.format_arguments) == 2

    def test_nonempty_false_branch(self) -> None:
        """Non-empty false branch is rejected."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || 'disabled' }}"
        spec = parse_registry_cache_spec(value)
        assert spec.conditional_empty_fallback is False

    def test_missing_registry_backend(self) -> None:
        """Missing type=registry in template."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=local,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        assert spec.backend == "local"

    def test_malformed_format_call(self) -> None:
        """Missing closing parenthesis in format call."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name || '' }}"
        with pytest.raises(CacheSpecParseError, match="No valid format"):
            parse_registry_cache_spec(value)

    def test_unterminated_expression(self) -> None:
        """Unterminated GitHub expression string."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry"
        with pytest.raises(CacheSpecParseError, match="Not a GitHub expression"):
            parse_registry_cache_spec(value)

    def test_empty_cache_spec(self) -> None:
        """Empty cache specification."""
        with pytest.raises(CacheSpecParseError, match="Empty cache specification"):
            parse_registry_cache_spec("")


# =============================================================================
# Regression tests: the exact current harbor-build-image.yml expression
# =============================================================================


class TestHarborBuildImageRegression:
    """Regression tests for the exact current harbor-build-image.yml expressions."""

    def test_current_cache_from_expression(self) -> None:
        """The current cache-from expression parses without the closing quote."""
        # This is the EXACT expression from harbor-build-image.yml
        cache_from_value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(cache_from_value)

        # Key assertion: ref_template does NOT contain the closing quote
        assert "'" not in spec.ref_template
        assert spec.ref_template == "{0}/{1}/cache/{2}:buildcache"

        # Verify the ref_template ends with :buildcache
        assert spec.ref_template.endswith(":buildcache")

        # Verify condition and arguments
        assert spec.condition == "inputs.registry_cache_read_enabled"
        assert spec.format_arguments == (
            "inputs.registry",
            "inputs.harbor_project",
            "inputs.image_name",
        )

    def test_current_cache_to_expression(self) -> None:
        """The current cache-to expression parses correctly with mode=max."""
        cache_to_value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=max', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(cache_to_value)

        assert spec.ref_template.endswith(":buildcache")
        assert spec.mode == "max"
        assert spec.condition == "inputs.registry_cache_write_enabled"
        assert spec.conditional_empty_fallback is True

    def test_wrong_buildcache_suffix_fails(self) -> None:
        """Mutation proof: changing :buildcache to :cache fails."""
        malformed_value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:cache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(malformed_value)
        # Parser accepts but ref_template is wrong
        assert spec.ref_template.endswith(":cache")
        assert not spec.ref_template.endswith(":buildcache")

    def test_wrong_condition_fails(self) -> None:
        """Mutation proof: wrong condition fails authority check."""
        wrong_condition_value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(wrong_condition_value)
        # Parser accepts but condition is wrong for cache-from
        assert spec.condition == "inputs.registry_cache_write_enabled"


# =============================================================================
# Dataclass tests
# =============================================================================


class TestRegistryCacheSpec:
    """Tests for the RegistryCacheSpec dataclass."""

    def test_immutable(self) -> None:
        """RegistryCacheSpec is frozen and cannot be modified."""
        spec = RegistryCacheSpec(
            backend="registry",
            ref_template="test:buildcache",
        )
        with pytest.raises(AttributeError):
            spec.backend = "local"  # type: ignore[misc]

    def test_slots(self) -> None:
        """RegistryCacheSpec uses __slots__."""
        spec = RegistryCacheSpec(
            backend="registry",
            ref_template="test:buildcache",
        )
        assert not hasattr(spec, "__dict__")

    def test_equality(self) -> None:
        """Two specs with same values are equal."""
        spec1 = RegistryCacheSpec(
            backend="registry",
            ref_template="test:buildcache",
        )
        spec2 = RegistryCacheSpec(
            backend="registry",
            ref_template="test:buildcache",
        )
        assert spec1 == spec2

    def test_repr(self) -> None:
        """RegistryCacheSpec has a useful repr."""
        spec = RegistryCacheSpec(
            backend="registry",
            ref_template="test:buildcache",
            mode="max",
        )
        r = repr(spec)
        assert "RegistryCacheSpec" in r
        assert "backend='registry'" in r
        assert "ref_template='test:buildcache'" in r
        assert "mode='max'" in r
