#!/usr/bin/env python3
"""YAML parsing and image extraction from Helm-rendered Kubernetes manifests."""

from __future__ import annotations

import sys

from k9b_cnpg_image_preflight_types import ExtractedImage


def infer_component(container_name: str, resource_kind: str, resource_name: str) -> str:
    """Infer component name from container/resource names.

    Priority:
    1. Look for explicit component labels in resource name
    2. Use container name patterns
    3. Fall back to resource kind
    """
    name_lower = resource_name.lower()
    container_lower = container_name.lower()

    # Explicit component in resource name
    if "backend" in name_lower or "k9b-backend" in name_lower:
        return "backend"
    if "frontend" in name_lower or "k9b-frontend" in name_lower:
        return "frontend"
    if "scheduler" in name_lower or "k9b-scheduler" in name_lower:
        return "scheduler"

    # Container name patterns
    if container_lower in ("backend", "k9b-backend", "k9b"):
        return "backend"
    if container_lower in ("frontend", "k9b-frontend", "nginx", "nginx-unprivileged"):
        return "frontend"
    if container_lower in ("scheduler", "k9b-scheduler"):
        return "scheduler"
    if "init" in container_lower:
        return f"init-{container_lower.replace('-init', '').replace('init-', '').replace('init', 'unknown') or 'container'}"

    # Init container - infer from resource
    if "backend" in name_lower:
        return "init-backend"
    if "frontend" in name_lower:
        return "init-frontend"

    # Fall back to resource kind
    return resource_kind.lower()


def parse_yaml_documents(content: str) -> list[dict]:
    """Parse YAML content into a list of documents.

    Handles the --- document separator used by Helm templates.
    """
    import yaml

    documents = []
    for doc in content.split("---"):
        doc = doc.strip()
        if not doc:
            continue
        try:
            # Use SafeLoader to prevent arbitrary code execution
            doc_data = yaml.safe_load(doc)
            if doc_data:
                documents.append(doc_data)
        except yaml.YAMLError as e:
            print(f"[image-preflight-render] WARNING: Failed to parse YAML document: {e}", file=sys.stderr)
            continue
    return documents


def extract_images_from_manifest(manifest: dict) -> list[ExtractedImage]:
    """Extract all container images from a Kubernetes manifest.

    Handles:
    - Deployment.spec.template.spec.containers
    - Deployment.spec.template.spec.initContainers
    - StatefulSet (same structure)
    - Job.spec.template.spec.containers
    - CronJob.spec.jobTemplate.spec.template.spec.containers
    - Pod.spec.containers
    - Pod.spec.initContainers
    """
    images: list[ExtractedImage] = []
    kind = manifest.get("kind", "Unknown")
    metadata = manifest.get("metadata", {})
    name = metadata.get("name", "unknown")

    def extract_from_spec(spec: dict | None, is_job_template: bool = False) -> None:
        """Extract images from a pod spec."""
        if not spec:
            return

        # Regular containers
        for container in spec.get("containers", []):
            container_name = container.get("name", "unknown")
            image = container.get("image", "")
            if image:
                component = infer_component(container_name, kind, name)
                images.append(ExtractedImage(
                    image_ref=image,
                    component=component,
                    container_name=container_name,
                    resource_kind=kind,
                    resource_name=name,
                    is_init_container=False,
                ))

        # Init containers
        for container in spec.get("initContainers", []):
            container_name = container.get("name", "unknown")
            image = container.get("image", "")
            if image:
                component = infer_component(container_name, kind, name)
                images.append(ExtractedImage(
                    image_ref=image,
                    component=component,
                    container_name=container_name,
                    resource_kind=kind,
                    resource_name=name,
                    is_init_container=True,
                ))

    # Direct Pod spec
    if kind == "Pod":
        extract_from_spec(manifest.get("spec"))

    # Deployment / StatefulSet / DaemonSet
    elif kind in ("Deployment", "StatefulSet", "DaemonSet"):
        template = manifest.get("spec", {}).get("template", {})
        extract_from_spec(template.get("spec"))

    # Job
    elif kind == "Job":
        template = manifest.get("spec", {}).get("template", {})
        extract_from_spec(template.get("spec"), is_job_template=True)

    # CronJob
    elif kind == "CronJob":
        job_template = manifest.get("spec", {}).get("jobTemplate", {})
        template = job_template.get("spec", {}).get("template", {})
        extract_from_spec(template.get("spec"))

    # ReplicaSet (nested in Deployment)
    elif kind == "ReplicaSet":
        template = manifest.get("spec", {}).get("template", {})
        extract_from_spec(template.get("spec"))

    return images


def extract_images_from_yaml_content(yaml_content: str) -> list[ExtractedImage]:
    """Extract all container images from YAML content.

    Convenience function that parses YAML and extracts images in one call.
    """
    documents = parse_yaml_documents(yaml_content)
    all_images: list[ExtractedImage] = []
    for doc in documents:
        images = extract_images_from_manifest(doc)
        all_images.extend(images)
    return all_images


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Extract container images from YAML")
    parser.add_argument("--input", required=True, help="Input YAML file")
    args = parser.parse_args()

    with open(args.input) as f:
        content = f.read()

    images = extract_images_from_yaml_content(content)
    print(json.dumps([img.to_dict() for img in images], indent=2))
