"""Tests for schema evidence resource mapping in k9b_cnpg_live_lab_bootstrap.py.

This module tests:
- _parse_rendered_yaml_for_resource() function
- Bogus resource name rejection
- Rendered YAML integration with extract_schema_warnings()
"""

import sys
from pathlib import Path

# Import the functions to test
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from k9b_cnpg_live_lab_bootstrap import (
    _parse_rendered_yaml_for_resource,
    extract_schema_warnings,
)


class TestParseRenderedYamlForResource:
    """Tests for _parse_rendered_yaml_for_resource function."""

    def test_finds_deployment_by_container_field(self) -> None:
        """Must find Deployment resource when field path contains containers."""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-frontend
  namespace: default
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: frontend
        image: nginx:latest
"""
        kind, name, namespace = _parse_rendered_yaml_for_resource(
            rendered,
            "spec.template.spec.containers[0].allowPrivilegeEscalation"
        )
        assert kind == "Deployment"
        assert name == "k9b-frontend"
        assert namespace == "default"

    def test_finds_statefulset_by_container_field(self) -> None:
        """Must find StatefulSet resource when field path contains containers."""
        rendered = """
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cnpg-cluster
  namespace: database
spec:
  serviceName: cnpg-cluster
  replicas: 1
  template:
    spec:
      containers:
      - name: cnpg
        image: postgres:15
"""
        kind, name, namespace = _parse_rendered_yaml_for_resource(
            rendered,
            "spec.template.spec.containers[0].limits"
        )
        assert kind == "StatefulSet"
        assert name == "cnpg-cluster"
        assert namespace == "database"

    def test_finds_resource_for_non_container_field(self) -> None:
        """Must find resource for non-container fields like spec.replicas."""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
  namespace: monitoring
spec:
  replicas: 2
  selector:
    matchLabels:
      app: k9b
"""
        kind, name, namespace = _parse_rendered_yaml_for_resource(
            rendered,
            "spec.replicas"
        )
        assert kind == "Deployment"
        assert name == "k9b-backend"
        assert namespace == "monitoring"

    def test_handles_multiple_documents(self) -> None:
        """Must correctly identify which document contains containers."""
        rendered = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-config
data:
  nginx.conf: |
    worker_processes 1;
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-frontend
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: frontend
        image: nginx:latest
---
apiVersion: v1
kind: Service
metadata:
  name: k9b-service
"""
        kind, name, namespace = _parse_rendered_yaml_for_resource(
            rendered,
            "spec.template.spec.containers[0].securityContext"
        )
        # Should find the Deployment, not the ConfigMap or Service
        assert kind == "Deployment"
        assert name == "k9b-frontend"

    def test_returns_empty_for_empty_content(self) -> None:
        """Must handle empty rendered content."""
        kind, name, namespace = _parse_rendered_yaml_for_resource("", "spec.limits")
        assert kind == ""
        assert name == ""
        assert namespace == ""

    def test_handles_document_with_no_kind(self) -> None:
        """Must handle documents without kind field."""
        rendered = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-config
data:
  key: value
"""
        kind, name, namespace = _parse_rendered_yaml_for_resource(
            rendered,
            "spec.template.spec.containers[0].limits"
        )
        # Should return empty since no containers section
        assert kind == ""


class TestBogusResourceNameRejection:
    """Tests for bogus resource name rejection."""

    def test_rejects_bogus_name_in(self) -> None:
        """Must reject 'in' as a bogus resource name."""
        log_content = """
error from Deployment/in: unknown field "spec.limits"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        # "in" should be rejected as a bogus name
        assert warnings[0].get("name") != "in"

    def test_rejects_bogus_name_version(self) -> None:
        """Must reject 'version' as a bogus resource name."""
        log_content = """
error from StatefulSet/version: unknown field "spec.replicas"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0].get("name") != "version"

    def test_rejects_bogus_name_the(self) -> None:
        """Must reject 'the' as a bogus resource name."""
        log_content = """
error from DaemonSet/the: unknown field "spec.template.spec.tolerations"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0].get("name") != "the"

    def test_rejects_bogus_name_a(self) -> None:
        """Must reject 'a' as a bogus resource name."""
        log_content = """
error from Job/a: unknown field "spec.backoffLimit"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0].get("name") != "a"

    def test_rejects_bogus_name_an(self) -> None:
        """Must reject 'an' as a bogus resource name."""
        log_content = """
error from CronJob/an: unknown field "spec.schedule"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0].get("name") != "an"

    def test_rejects_bogus_name_for(self) -> None:
        """Must reject 'for' as a bogus resource name."""
        log_content = """
error from ConfigMap/for: unknown field "spec.data"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0].get("name") != "for"

    def test_rejects_bogus_name_with(self) -> None:
        """Must reject 'with' as a bogus resource name."""
        log_content = """
error from Secret/with: unknown field "spec.type"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 1
        assert warnings[0].get("name") != "with"

    def test_accepts_valid_resource_name(self) -> None:
        """Must accept valid resource names like 'k9b', 'my-app', 'cluster_1'."""
        log_content = """
error from Deployment/k9b: unknown field "spec.limits"
error from StatefulSet/my-cluster: unknown field "spec.replicas"
error from ConfigMap/app_config: unknown field "spec.data"
"""
        warnings = extract_schema_warnings(log_content)
        assert len(warnings) == 3
        assert warnings[0]["name"] == "k9b"
        assert warnings[1]["name"] == "my-cluster"
        assert warnings[2]["name"] == "app_config"

    def test_rejects_name_starting_with_dash(self) -> None:
        """Must reject resource names starting with dash."""
        log_content = """
error from Deployment/-invalid: unknown field "spec.limits"
"""
        warnings = extract_schema_warnings(log_content)
        assert warnings[0].get("name") != "-invalid"

    def test_rejects_name_starting_with_underscore(self) -> None:
        """Must reject resource names starting with underscore."""
        log_content = """
error from Deployment/_internal: unknown field "spec.limits"
"""
        warnings = extract_schema_warnings(log_content)
        assert warnings[0].get("name") != "_internal"


class TestRenderedYamlIntegration:
    """Tests for integration between extract_schema_warnings and _parse_rendered_yaml_for_resource."""

    def test_uses_rendered_yaml_for_resource_when_provided(self) -> None:
        """Must use rendered YAML for kind/name when available."""
        log_content = """
error from Deployment/wrong-name: unknown field "spec.template.spec.containers[0].limits"
"""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: correct-name
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: app
        image: nginx:latest
"""
        warnings = extract_schema_warnings(log_content, rendered)
        assert len(warnings) == 1
        assert warnings[0]["kind"] == "Deployment"
        assert warnings[0]["name"] == "correct-name"

    def test_prioritizes_rendered_yaml_for_container_fields(self) -> None:
        """Must prioritize rendered YAML for container-related field paths."""
        log_content = """
unknown field "spec.template.spec.containers[0].allowPrivilegeEscalation"
"""
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: web
spec:
  template:
    spec:
      containers:
      - name: frontend
        image: nginx:latest
"""
        warnings = extract_schema_warnings(log_content, rendered)
        assert len(warnings) == 1
        assert warnings[0]["kind"] == "Deployment"
        assert warnings[0]["name"] == "frontend"

    def test_falls_back_to_log_parsing_when_no_rendered(self) -> None:
        """Must fall back to log parsing when no rendered YAML provided."""
        log_content = """
error from Service/backend: unknown field "spec.ports"
"""
        warnings = extract_schema_warnings(log_content, "")
        assert len(warnings) == 1
        assert warnings[0]["kind"] == "Service"
        assert warnings[0]["name"] == "backend"

    def test_handles_rendered_yaml_with_multiple_resources(self) -> None:
        """Must find correct resource when rendered YAML has multiple documents."""
        log_content = """
unknown field "spec.template.spec.containers[0].readOnlyRootFilesystem"
"""
        rendered = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  key: value
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
  namespace: monitoring
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: backend
        image: backend:latest
---
apiVersion: v1
kind: Service
metadata:
  name: backend-svc
"""
        warnings = extract_schema_warnings(log_content, rendered)
        assert len(warnings) == 1
        assert warnings[0]["kind"] == "Deployment"
        assert warnings[0]["name"] == "k9b-backend"
