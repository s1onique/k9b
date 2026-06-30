"""Regression tests for Docker Harbor BuildKit registry cache configuration.

These tests ensure that all docker/build-push-action usages in k9b workflows
import cache from and export cache to Harbor-backed BuildKit registry cache.

Cache pattern:
  cache-from: type=registry,ref=harbor-pve1.spbnix.local/k9b/cache/<image-name>:buildcache
  cache-to: type=registry,ref=harbor-pve1.spbnix.local/k9b/cache/<image-name>:buildcache,mode=max

Requirements:
- Every docker/build-push-action step must have cache-from
- Every docker/build-push-action step must have cache-to
- Cache backend must be type=registry
- Cache refs must point to harbor-pve1.spbnix.local/k9b/cache/
- Cache refs must end with :buildcache
- cache-to must use mode=max
- Each image has its own cache ref (not shared)
- Multi-platform builds preserved (linux/amd64,linux/arm64)
- Harbor login/CA setup steps remain present
"""

import re
from pathlib import Path
from typing import Any

import yaml

# Paths to workflow files that use docker/build-push-action
HARBOR_BUILD_IMAGE_WORKFLOW = (
    Path(__file__).parent.parent / ".github" / "workflows" / "harbor-build-image.yml"
)
K9B_IMAGE_BUILDER_WORKFLOW = (
    Path(__file__).parent.parent / ".github" / "workflows" / "k9b-image-builder.yml"
)
OTEL_DEMO_LIVE_LAB_WORKFLOW = (
    Path(__file__).parent.parent / ".github" / "workflows" / "k9b-otel-demo-live-lab.yml"
)


def load_workflow(path: Path) -> dict[str, Any]:
    """Load a workflow YAML file."""
    return yaml.safe_load(path.read_text())  # type: ignore[no-any-return]


def find_build_push_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Find all docker/build-push-action steps in a workflow."""
    steps = []
    for job_name, job in workflow.get("jobs", {}).items():
        job_steps = job.get("steps", [])
        for step in job_steps:
            if step.get("uses", "").startswith("docker/build-push-action"):
                steps.append(step)
    return steps


class TestHarborBuildImageWorkflowCache:
    """Tests for .github/workflows/harbor-build-image.yml"""

    def test_workflow_file_exists(self) -> None:
        """The Harbor build image workflow should exist."""
        assert HARBOR_BUILD_IMAGE_WORKFLOW.exists(), (
            f"Harbor build workflow not found at {HARBOR_BUILD_IMAGE_WORKFLOW}"
        )

    def test_workflow_has_build_push_action(self) -> None:
        """Workflow should use docker/build-push-action."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        assert len(steps) >= 1, "Should have at least one build-push-action step"

    def test_build_push_has_cache_from(self) -> None:
        """build-push-action step must have cache-from."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        assert len(steps) >= 1, "Should have build-push-action step"
        
        for i, step in enumerate(steps):
            assert "cache-from" in step.get("with", {}), (
                f"Step {i} must have cache-from in 'with' block"
            )

    def test_build_push_has_cache_to(self) -> None:
        """build-push-action step must have cache-to."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        assert len(steps) >= 1, "Should have build-push-action step"
        
        for i, step in enumerate(steps):
            assert "cache-to" in step.get("with", {}), (
                f"Step {i} must have cache-to in 'with' block"
            )

    def test_cache_backend_is_registry(self) -> None:
        """Cache backend must be type=registry."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")
            cache_to = step.get("with", {}).get("cache-to", "")
            
            assert "type=registry" in cache_from, (
                f"Step {i} cache-from must use type=registry, got: {cache_from}"
            )
            assert "type=registry" in cache_to, (
                f"Step {i} cache-to must use type=registry, got: {cache_to}"
            )

    def test_cache_refs_use_harbor_path(self) -> None:
        """Cache refs must point to harbor-pve1.spbnix.local/k9b/cache/.
        
        Note: harbor-build-image.yml uses GitHub Actions template syntax (${{ inputs.xxx }})
        which is resolved at workflow invocation time, not YAML parse time.
        """
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")
            
            # Check for resolved path OR template syntax that will resolve to the right path
            has_harbor_path = (
                "harbor-pve1.spbnix.local/k9b/cache/" in cache_from or
                ("inputs.registry" in cache_from and "inputs.harbor_project" in cache_from and "cache/" in cache_from)
            )
            assert has_harbor_path, (
                f"Step {i} cache-from must use Harbor cache path, got: {cache_from}"
            )

    def test_cache_refs_end_with_buildcache(self) -> None:
        """Cache refs must end with :buildcache.
        
        Note: harbor-build-image.yml uses GitHub Actions template syntax that will
        resolve to image-specific cache refs at invocation time.
        """
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")
            cache_to = step.get("with", {}).get("cache-to", "")
            
            # Extract the ref portion (format: type=registry,ref=xxx:tag or type=registry,ref=xxx:tag,mode=xxx)
            # Handle both literal refs and template refs
            cache_from_match = re.search(r"ref=([^,]+)", cache_from)
            cache_to_match = re.search(r"ref=([^,]+)", cache_to)
            
            assert cache_from_match, f"Step {i} cache-from should have ref= pattern, got: {cache_from}"
            assert cache_to_match, f"Step {i} cache-to should have ref= pattern, got: {cache_to}"
            
            cache_from_ref = cache_from_match.group(1)
            cache_to_ref = cache_to_match.group(1)
            
            # For template syntax, check that inputs.image_name is in the ref
            if "${{" in cache_from_ref:
                assert "inputs.image_name" in cache_from_ref, (
                    f"Step {i} cache-from template should use inputs.image_name, got: {cache_from_ref}"
                )
            else:
                assert cache_from_ref.endswith(":buildcache"), (
                    f"Step {i} cache-from ref must end with :buildcache, got: {cache_from_ref}"
                )
            
            if "${{" in cache_to_ref:
                assert "inputs.image_name" in cache_to_ref, (
                    f"Step {i} cache-to template should use inputs.image_name, got: {cache_to_ref}"
                )
            else:
                assert cache_to_ref.endswith(":buildcache"), (
                    f"Step {i} cache-to ref must end with :buildcache, got: {cache_to_ref}"
                )

    def test_cache_to_uses_mode_max(self) -> None:
        """cache-to must use mode=max."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        for i, step in enumerate(steps):
            cache_to = step.get("with", {}).get("cache-to", "")
            
            assert "mode=max" in cache_to, (
                f"Step {i} cache-to must use mode=max, got: {cache_to}"
            )

    def test_workflow_has_harbor_login(self) -> None:
        """Workflow should have Harbor login step."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()
        assert "docker/login-action" in content, (
            "Workflow should use docker/login-action for Harbor authentication"
        )
        assert "harbor-pve1.spbnix.local" in content, (
            "Workflow should reference Harbor registry"
        )

    def test_workflow_has_buildkit_ca_config(self) -> None:
        """Workflow should have BuildKit CA configuration for Harbor."""
        content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()
        assert "Configure BuildKit with Harbor CA" in content, (
            "Should have BuildKit CA configuration step"
        )
        assert "buildkitd.toml" in content, (
            "Should create buildkitd.toml for BuildKit registry CA config"
        )

    def test_workflow_has_multiplatform_build(self) -> None:
        """Workflow should build for multiple platforms."""
        workflow = load_workflow(HARBOR_BUILD_IMAGE_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        for i, step in enumerate(steps):
            platforms = step.get("with", {}).get("platforms", "")
            assert "linux/amd64" in platforms, (
                f"Step {i} should build for linux/amd64"
            )
            assert "linux/arm64" in platforms, (
                f"Step {i} should build for linux/arm64"
            )


class TestK9BImageBuilderWorkflowCache:
    """Tests for .github/workflows/k9b-image-builder.yml"""

    def test_workflow_file_exists(self) -> None:
        """The k9b-image-builder workflow should exist."""
        assert K9B_IMAGE_BUILDER_WORKFLOW.exists(), (
            f"k9b-image-builder workflow not found at {K9B_IMAGE_BUILDER_WORKFLOW}"
        )

    def test_workflow_has_build_push_actions(self) -> None:
        """Workflow should use docker/build-push-action for both backend and frontend."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        assert len(steps) >= 2, "Should have at least 2 build-push-action steps (backend + frontend)"

    def test_backend_build_has_cache_from(self) -> None:
        """Backend build step must have cache-from."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        # First step should be backend
        backend_step = steps[0]
        assert "cache-from" in backend_step.get("with", {}), (
            "Backend build step must have cache-from"
        )

    def test_backend_build_has_cache_to(self) -> None:
        """Backend build step must have cache-to."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        backend_step = steps[0]
        assert "cache-to" in backend_step.get("with", {}), (
            "Backend build step must have cache-to"
        )

    def test_frontend_build_has_cache_from(self) -> None:
        """Frontend build step must have cache-from."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        # Second step should be frontend
        assert len(steps) >= 2, "Should have frontend build step"
        frontend_step = steps[1]
        assert "cache-from" in frontend_step.get("with", {}), (
            "Frontend build step must have cache-from"
        )

    def test_frontend_build_has_cache_to(self) -> None:
        """Frontend build step must have cache-to."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        frontend_step = steps[1]
        assert "cache-to" in frontend_step.get("with", {}), (
            "Frontend build step must have cache-to"
        )

    def test_backend_cache_ref_is_image_specific(self) -> None:
        """Backend cache ref must be specific to k9b-backend."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        backend_cache_from = steps[0].get("with", {}).get("cache-from", "")
        backend_cache_to = steps[0].get("with", {}).get("cache-to", "")
        
        assert "/cache/k9b-backend:" in backend_cache_from, (
            f"Backend cache-from should reference k9b-backend, got: {backend_cache_from}"
        )
        assert "/cache/k9b-backend:" in backend_cache_to, (
            f"Backend cache-to should reference k9b-backend, got: {backend_cache_to}"
        )

    def test_frontend_cache_ref_is_image_specific(self) -> None:
        """Frontend cache ref must be specific to k9b-frontend."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        frontend_cache_from = steps[1].get("with", {}).get("cache-from", "")
        frontend_cache_to = steps[1].get("with", {}).get("cache-to", "")
        
        assert "/cache/k9b-frontend:" in frontend_cache_from, (
            f"Frontend cache-from should reference k9b-frontend, got: {frontend_cache_from}"
        )
        assert "/cache/k9b-frontend:" in frontend_cache_to, (
            f"Frontend cache-to should reference k9b-frontend, got: {frontend_cache_to}"
        )

    def test_cache_refs_are_not_shared(self) -> None:
        """Backend and frontend should NOT share cache refs."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        backend_cache = steps[0].get("with", {}).get("cache-from", "")
        frontend_cache = steps[1].get("with", {}).get("cache-from", "")
        
        assert backend_cache != frontend_cache, (
            "Backend and frontend should not share cache refs"
        )
        assert "k9b-backend" in backend_cache, "Backend cache should reference k9b-backend"
        assert "k9b-frontend" in frontend_cache, "Frontend cache should reference k9b-frontend"

    def test_all_cache_backends_are_registry(self) -> None:
        """All cache steps must use type=registry backend."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        for i, step in enumerate(steps):
            cache_from = step.get("with", {}).get("cache-from", "")
            cache_to = step.get("with", {}).get("cache-to", "")
            
            assert "type=registry" in cache_from, (
                f"Step {i} cache-from must use type=registry"
            )
            assert "type=registry" in cache_to, (
                f"Step {i} cache-to must use type=registry"
            )

    def test_all_cache_to_use_mode_max(self) -> None:
        """All cache-to steps must use mode=max."""
        workflow = load_workflow(K9B_IMAGE_BUILDER_WORKFLOW)
        steps = find_build_push_steps(workflow)
        
        for i, step in enumerate(steps):
            cache_to = step.get("with", {}).get("cache-to", "")
            assert "mode=max" in cache_to, (
                f"Step {i} cache-to must use mode=max"
            )

    def test_workflow_has_harbor_login(self) -> None:
        """Workflow should have Harbor login step."""
        content = K9B_IMAGE_BUILDER_WORKFLOW.read_text()
        assert "docker/login-action" in content, (
            "Workflow should use docker/login-action for Harbor authentication"
        )


class TestOTelDemoLiveLabWorkflowCache:
    """Tests for .github/workflows/k9b-otel-demo-live-lab.yml"""

    def test_workflow_file_exists(self) -> None:
        """The OTel demo live lab workflow should exist."""
        assert OTEL_DEMO_LIVE_LAB_WORKFLOW.exists(), (
            f"OTel demo live lab workflow not found at {OTEL_DEMO_LIVE_LAB_WORKFLOW}"
        )

    def test_build_lab_images_has_cache(self) -> None:
        """build-lab-images job should have cache-from and cache-to."""
        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()
        
        # Find the build-lab-images section
        build_start = content.find("build-lab-images:")
        assert build_start != -1, "build-lab-images section not found"
        
        # Find next job or end
        next_marker = content.find("\n  # ======", build_start)
        if next_marker == -1:
            next_marker = len(content)
        
        build_section = content[build_start:next_marker]
        
        assert "cache-from:" in build_section, (
            "build-lab-images should have cache-from"
        )
        assert "cache-to:" in build_section, (
            "build-lab-images should have cache-to"
        )

    def test_cache_uses_registry_backend(self) -> None:
        """Cache must use type=registry backend."""
        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()
        
        build_start = content.find("build-lab-images:")
        next_marker = content.find("\n  # ======", build_start)
        if next_marker == -1:
            next_marker = len(content)
        
        build_section = content[build_start:next_marker]
        
        # Extract cache-from and cache-to values
        cache_from_match = re.search(r"cache-from:\s*(\S+)", build_section)
        cache_to_match = re.search(r"cache-to:\s*(\S+)", build_section)
        
        assert cache_from_match, "Should have cache-from value"
        assert cache_to_match, "Should have cache-to value"
        
        cache_from = cache_from_match.group(1)
        cache_to = cache_to_match.group(1)
        
        assert "type=registry" in cache_from, (
            f"cache-from must use type=registry, got: {cache_from}"
        )
        assert "type=registry" in cache_to, (
            f"cache-to must use type=registry, got: {cache_to}"
        )

    def test_cache_uses_harbor_path(self) -> None:
        """Cache refs must use Harbor path."""
        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()
        
        assert "harbor-pve1.spbnix.local/k9b/cache/" in content, (
            "Workflow should use Harbor cache path"
        )

    def test_cache_ends_with_buildcache(self) -> None:
        """Cache refs must end with :buildcache."""
        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()
        
        # Find cache-from and cache-to in build section
        build_start = content.find("build-lab-images:")
        next_marker = content.find("\n  # ======", build_start)
        if next_marker == -1:
            next_marker = len(content)
        
        build_section = content[build_start:next_marker]
        
        # Extract the ref portion - ref comes before comma for mode= params
        # Format: type=registry,ref=<ref>,mode=max OR type=registry,ref=<ref>
        cache_from_match = re.search(r"cache-from:\s*type=registry,ref=([^,\n]+)", build_section)
        cache_to_match = re.search(r"cache-to:\s*type=registry,ref=([^,\n]+)", build_section)
        
        assert cache_from_match, f"Should have cache-from with ref, got section:\n{build_section[:500]}"
        assert cache_to_match, f"Should have cache-to with ref, got section:\n{build_section[:500]}"
        
        cache_from_ref = cache_from_match.group(1).strip()
        cache_to_ref = cache_to_match.group(1).strip()
        
        assert cache_from_ref.endswith(":buildcache"), (
            f"cache-from ref must end with :buildcache, got: {cache_from_ref}"
        )
        assert cache_to_ref.endswith(":buildcache"), (
            f"cache-to ref must end with :buildcache, got: {cache_to_ref}"
        )

    def test_cache_to_uses_mode_max(self) -> None:
        """cache-to must use mode=max."""
        content = OTEL_DEMO_LIVE_LAB_WORKFLOW.read_text()
        
        build_start = content.find("build-lab-images:")
        next_marker = content.find("\n  # ======", build_start)
        if next_marker == -1:
            next_marker = len(content)
        
        build_section = content[build_start:next_marker]
        
        cache_to_match = re.search(r"cache-to:\s*(\S+)", build_section)
        assert cache_to_match, "Should have cache-to value"
        
        cache_to = cache_to_match.group(1)
        assert "mode=max" in cache_to, (
            f"cache-to must use mode=max, got: {cache_to}"
        )


class TestCacheConsistencyAcrossWorkflows:
    """Tests to ensure cache configuration is consistent and correct."""

    def test_all_workflows_use_same_registry_host(self) -> None:
        """All workflows should use the same Harbor registry host."""
        files = [
            HARBOR_BUILD_IMAGE_WORKFLOW,
            K9B_IMAGE_BUILDER_WORKFLOW,
            OTEL_DEMO_LIVE_LAB_WORKFLOW,
        ]
        
        for path in files:
            if not path.exists():
                continue
            content = path.read_text()
            assert "harbor-pve1.spbnix.local" in content, (
                f"{path.name} should use Harbor registry host"
            )

    def test_all_cache_refs_use_same_cache_project(self) -> None:
        """All cache refs should use the same cache project path.
        
        Note: harbor-build-image.yml uses GitHub Actions template syntax that resolves
        to the correct path at workflow invocation time.
        """
        files = [
            K9B_IMAGE_BUILDER_WORKFLOW,
            OTEL_DEMO_LIVE_LAB_WORKFLOW,
        ]
        
        for path in files:
            if not path.exists():
                continue
            content = path.read_text()
            
            # Find all cache refs
            cache_refs = re.findall(
                r"cache-(?:from|to):\s*type=registry,ref=([^\s,]+)",
                content,
            )
            
            for ref in cache_refs:
                assert ref.startswith("harbor-pve1.spbnix.local/k9b/cache/"), (
                    f"{path.name} cache ref should use /k9b/cache/ path, got: {ref}"
                )
        
        # Special handling for harbor-build-image.yml which uses template syntax
        if HARBOR_BUILD_IMAGE_WORKFLOW.exists():
            content = HARBOR_BUILD_IMAGE_WORKFLOW.read_text()
            # Check that template syntax is used correctly for cache refs
            assert "inputs.registry" in content and "inputs.harbor_project" in content, (
                "harbor-build-image.yml should use inputs for registry and project"
            )
            assert "inputs.image_name" in content, (
                "harbor-build-image.yml should use inputs.image_name for cache ref"
            )
