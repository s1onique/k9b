"""Tests for strict Harbor cache policy validation.

This module validates that cache specs conform to Harbor policy requirements
using CacheContractValidationError for rejection proofs.
"""

from __future__ import annotations

import pytest

from tests.helpers.docker_harbor_cache_helpers import (
    CacheContractValidationError,
    CacheDirection,
    parse_registry_cache_spec,
    validate_harbor_registry_cache_contract,
)

# =============================================================================
# Cache-from policy validation tests
# =============================================================================


class TestCacheFromPolicyValidation:
    """Tests for cache-from Harbor policy validation."""

    def test_valid_cache_from_spec(self) -> None:
        """Valid cache-from spec passes validation."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)

    def test_cache_from_wrong_condition_rejected(self) -> None:
        """Cache-from with wrong condition is rejected."""
        value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="condition must be 'inputs.registry_cache_read_enabled'",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)

    def test_cache_from_missing_buildcache_suffix_rejected(self) -> None:
        """Cache-from without :buildcache suffix is rejected."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:cache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="must end with ':buildcache'",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)

    def test_cache_from_missing_image_name_rejected(self) -> None:
        """Cache-from missing image_name argument is rejected."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project) || '' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="format_arguments must be",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)

    def test_cache_from_wrong_argument_order_rejected(self) -> None:
        """Cache-from with wrong argument order is rejected."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.image_name, inputs.registry, inputs.harbor_project) || '' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="format_arguments must be",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)

    def test_cache_from_non_empty_false_branch_rejected(self) -> None:
        """Cache-from with nonempty false branch is rejected."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || 'disabled' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="must have empty false branch",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)

    def test_cache_from_non_registry_backend_rejected(self) -> None:
        """Cache-from with non-registry backend is rejected."""
        value = "type=local,ref=registry/project/cache/image:buildcache"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="must use backend=registry",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)

    def test_cache_from_with_mode_rejected(self) -> None:
        """Cache-from with mode present is rejected."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=max', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="must not have mode",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)


# =============================================================================
# Cache-to policy validation tests
# =============================================================================


class TestCacheToPolicyValidation:
    """Tests for cache-to Harbor policy validation."""

    def test_valid_cache_to_spec(self) -> None:
        """Valid cache-to spec passes validation."""
        value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=max', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        validate_harbor_registry_cache_contract(spec, CacheDirection.TO)

    def test_cache_to_wrong_condition_rejected(self) -> None:
        """Cache-to with wrong condition is rejected."""
        value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=max', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="condition must be 'inputs.registry_cache_write_enabled'",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.TO)

    def test_cache_to_missing_buildcache_suffix_rejected(self) -> None:
        """Cache-to without :buildcache suffix is rejected."""
        value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:cache,mode=max', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="must end with ':buildcache'",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.TO)

    def test_cache_to_missing_mode_max_rejected(self) -> None:
        """Cache-to with missing or wrong mode is rejected."""
        value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="mode must be 'max'",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.TO)

    def test_cache_to_wrong_mode_rejected(self) -> None:
        """Cache-to with wrong mode value is rejected."""
        value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=min', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="mode must be 'max'",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.TO)

    def test_cache_to_missing_image_name_rejected(self) -> None:
        """Cache-to missing image_name argument is rejected."""
        value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=max', inputs.registry, inputs.harbor_project) || '' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="format_arguments must be",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.TO)

    def test_cache_to_non_empty_false_branch_rejected(self) -> None:
        """Cache-to with nonempty false branch is rejected."""
        value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=max', inputs.registry, inputs.harbor_project, inputs.image_name) || 'disabled' }}"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="must have empty false branch",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.TO)

    def test_cache_to_non_registry_backend_rejected(self) -> None:
        """Cache-to with non-registry backend is rejected."""
        value = "type=local,ref=registry/project/cache/image:buildcache,mode=max"
        spec = parse_registry_cache_spec(value)
        with pytest.raises(
            CacheContractValidationError,
            match="must use backend=registry",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.TO)


# =============================================================================
# Policy validation matrix - exact harbor-build-image.yml expressions
# =============================================================================


class TestHarborBuildImageCachePolicy:
    """Regression tests for exact harbor-build-image.yml cache expressions."""

    def test_harbor_build_image_cache_from_policy(self) -> None:
        """The exact cache-from expression from harbor-build-image.yml is valid."""
        cache_from_value = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(cache_from_value)
        validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)

    def test_harbor_build_image_cache_to_policy(self) -> None:
        """The exact cache-to expression from harbor-build-image.yml is valid."""
        cache_to_value = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=max', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(cache_to_value)
        validate_harbor_registry_cache_contract(spec, CacheDirection.TO)

    def test_harbor_build_image_cache_from_mutation_rejected(self) -> None:
        """Mutating :buildcache to :cache in cache-from fails policy."""
        cache_from_mutation = "${{ inputs.registry_cache_read_enabled && format('type=registry,ref={0}/{1}/cache/{2}:cache', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(cache_from_mutation)
        with pytest.raises(
            CacheContractValidationError,
            match="must end with ':buildcache'",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.FROM)

    def test_harbor_build_image_cache_to_mutation_rejected(self) -> None:
        """Mutating mode=max to mode=min in cache-to fails policy."""
        cache_to_mutation = "${{ inputs.registry_cache_write_enabled && format('type=registry,ref={0}/{1}/cache/{2}:buildcache,mode=min', inputs.registry, inputs.harbor_project, inputs.image_name) || '' }}"
        spec = parse_registry_cache_spec(cache_to_mutation)
        with pytest.raises(
            CacheContractValidationError,
            match="mode must be 'max'",
        ):
            validate_harbor_registry_cache_contract(spec, CacheDirection.TO)
