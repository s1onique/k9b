"""Registry manifest preflight using curl with proper Accept headers."""

import re
import subprocess
import sys
from datetime import UTC, datetime

# Accept headers for Docker/OCI manifests
MANIFEST_ACCEPT_HEADERS = (
    "application/vnd.oci.image.index.v1+json,"
    "application/vnd.docker.distribution.manifest.list.v2+json,"
    "application/vnd.oci.image.manifest.v1+json,"
    "application/vnd.docker.distribution.manifest.v2+json,"
    "application/vnd.docker.distribution.manifest.v1+json"
)


def parse_image_ref(image_ref: str) -> tuple[str, str, str]:
    """Parse image reference into (registry_host, repository_path, tag)."""
    if "@" in image_ref:
        image_ref = image_ref.split("@")[0]

    parts = image_ref.split("/", 1)
    if len(parts) == 1:
        image_name = parts[0]
        if ":" in image_name:
            name, tag = image_name.rsplit(":", 1)
            return "docker.io", f"library/{name}", tag
        return "docker.io", f"library/{image_name}", "latest"

    registry_host = parts[0]
    remainder = parts[1]
    has_domain = "." in registry_host or "localhost" in registry_host.lower()
    has_port = ":" in registry_host

    if not has_domain and not has_port:
        if ":" in remainder:
            repo_path, tag = remainder.rsplit(":", 1)
            return "docker.io", f"{registry_host}/{repo_path}", tag
        return "docker.io", f"{registry_host}/{remainder}", "latest"

    if ":" in remainder:
        repo_path, tag = remainder.rsplit(":", 1)
        return registry_host, repo_path, tag

    return registry_host, remainder, "latest"


def sanitize_error(error_msg: str) -> str:
    """Sanitize error message to remove sensitive data."""
    sanitized = error_msg
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9+/=._-]+", "Bearer [REDACTED]", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\b[A-Za-z0-9+/]{32,}={0,2}\b", "[REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)password[\"\s:=]+[\"']?[^\s,\"\']+[\"']?", "password=[REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)secret[\"\s:=]+[\"']?[^\s,\"\']+[\"']?", "secret=[REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)authorization[\"\s:=]+[\"']?[^\s,\"\']+[\"']?", "authorization=[REDACTED]", sanitized)
    return sanitized.strip()


def classify_http_error(status_code: int, error_body: str = "") -> str:
    """Classify HTTP error into failure class."""
    from k9b_cnpg_image_preflight_types import (
        FAIL_IMAGE_FORBIDDEN,
        FAIL_IMAGE_MISSING,
        FAIL_IMAGE_UNAUTHORIZED,
        FAIL_IMAGE_UNKNOWN,
    )

    error_lower = error_body.lower()
    if status_code == 401:
        return FAIL_IMAGE_UNAUTHORIZED
    if status_code == 403:
        return FAIL_IMAGE_FORBIDDEN
    if status_code == 404:
        return FAIL_IMAGE_MISSING
    if "manifest unknown" in error_lower or "not found" in error_lower:
        return FAIL_IMAGE_MISSING
    if "unauthorized" in error_lower or "authentication" in error_lower:
        return FAIL_IMAGE_UNAUTHORIZED
    if "forbidden" in error_lower or "denied" in error_lower:
        return FAIL_IMAGE_FORBIDDEN
    return FAIL_IMAGE_UNKNOWN


def check_manifest_with_curl(
    image_ref: str,
    registry_username: str | None = None,
    registry_password: str | None = None,
    ca_cert_path: str | None = None,
) -> dict:
    """Check if image manifest exists using curl with proper Accept headers.

    Args:
        image_ref: Image reference (e.g., "harbor.example.com/project/image:tag")
        registry_username: Optional registry username for authenticated requests
        registry_password: Optional registry password for authenticated requests
        ca_cert_path: Optional path to CA certificate for TLS verification

    Returns dict with keys: component, image_ref, registry_host, repository_path,
    tag, success, failure_class, status_code, error_message, command_used, timestamp
    """
    from k9b_cnpg_image_preflight_types import (
        FAIL_IMAGE_AUTH_UNVERIFIED,
        FAIL_IMAGE_CREDS_MISSING,
        FAIL_IMAGE_MISSING,
        FAIL_IMAGE_NETWORK,
        FAIL_IMAGE_TLS,
        FAIL_IMAGE_UNKNOWN,
        RegistryResult,
    )

    component = _infer_component(image_ref)
    registry_host, repository_path, tag = parse_image_ref(image_ref)
    timestamp = datetime.now(UTC).isoformat()

    manifest_url = f"https://{registry_host}/v2/{repository_path}/manifests/{tag}"

    curl_cmd = [
        "curl", "-sS", "-I",
        "-H", f"Accept: {MANIFEST_ACCEPT_HEADERS}",
        "-o", "/dev/null",
        "-w", "%{http_code}",
        "--connect-timeout", "10",
        "-L",
    ]

    # Add CA certificate for TLS verification if provided
    if ca_cert_path:
        curl_cmd.extend(["--cacert", ca_cert_path])

    cmd_prefix = ""
    if registry_username and registry_password:
        curl_cmd.extend(["-u", f"{registry_username}:{registry_password}"])
        cmd_prefix = "[authenticated] "
    elif registry_username or registry_password:
        return RegistryResult(
            component=component,
            image_ref=image_ref,
            registry_host=registry_host,
            repository_path=repository_path,
            tag=tag,
            success=False,
            failure_class=FAIL_IMAGE_CREDS_MISSING,
            error_message="Partial registry credentials provided (need both username and password)",
            command_used=f"{cmd_prefix}curl -I {manifest_url} [partial-auth]",
            timestamp=timestamp,
        ).to_dict()

    curl_cmd.append(manifest_url)
    ca_cert_flag = f" --cacert {ca_cert_path}" if ca_cert_path else ""
    command_used = f"{cmd_prefix}curl{ca_cert_flag} -I -H 'Accept: ...' -w '%{{http_code}}' {manifest_url}"

    try:
        proc = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
        status_code_str = proc.stdout.strip()
        stderr = proc.stderr or ""

        # Detect curl-specific TLS errors (exit code 60 = SSL certificate problem)
        if proc.returncode == 60:
            stderr_lower = stderr.lower()
            if "ssl certificate problem" in stderr_lower or "unable to get local issuer certificate" in stderr_lower:
                return RegistryResult(
                    component=component,
                    image_ref=image_ref,
                    registry_host=registry_host,
                    repository_path=repository_path,
                    tag=tag,
                    success=False,
                    failure_class=FAIL_IMAGE_TLS,
                    status_code=0,
                    error_message="SSL certificate problem: unable to get local issuer certificate. Install Harbor CA certificate to verify registry TLS.",
                    command_used=command_used,
                    timestamp=timestamp,
                ).to_dict()

        try:
            status_code = int(status_code_str)
        except ValueError:
            status_code = 0

        if status_code == 200:
            return RegistryResult(
                component=component,
                image_ref=image_ref,
                registry_host=registry_host,
                repository_path=repository_path,
                tag=tag,
                success=True,
                status_code=status_code,
                command_used=command_used,
                timestamp=timestamp,
            ).to_dict()

        if status_code in (401, 403):
            # If no credentials provided, classify as unverified rather than auth failure
            # Node-side pullability is the source of truth for auth
            if not registry_username and not registry_password:
                failure_class = FAIL_IMAGE_AUTH_UNVERIFIED
                error_msg = "Registry requires authentication (401/403); no credentials provided. Node-side pullability is authoritative."
            else:
                failure_class = classify_http_error(status_code, stderr)
                error_msg = sanitize_error(stderr[:500])

            return RegistryResult(
                component=component,
                image_ref=image_ref,
                registry_host=registry_host,
                repository_path=repository_path,
                tag=tag,
                success=False,
                failure_class=failure_class,
                status_code=status_code,
                error_message=error_msg,
                command_used=command_used,
                timestamp=timestamp,
            ).to_dict()

        if status_code == 404:
            return RegistryResult(
                component=component,
                image_ref=image_ref,
                registry_host=registry_host,
                repository_path=repository_path,
                tag=tag,
                success=False,
                failure_class=FAIL_IMAGE_MISSING,
                status_code=status_code,
                error_message=sanitize_error(stderr[:500] or "Tag not found"),
                command_used=command_used,
                timestamp=timestamp,
            ).to_dict()

        return RegistryResult(
            component=component,
            image_ref=image_ref,
            registry_host=registry_host,
            repository_path=repository_path,
            tag=tag,
            success=False,
            failure_class=classify_http_error(status_code, stderr),
            status_code=status_code,
            error_message=sanitize_error(stderr[:500] or f"HTTP {status_code}"),
            command_used=command_used,
            timestamp=timestamp,
        ).to_dict()

    except subprocess.TimeoutExpired:
        return RegistryResult(
            component=component,
            image_ref=image_ref,
            registry_host=registry_host,
            repository_path=repository_path,
            tag=tag,
            success=False,
            failure_class=FAIL_IMAGE_NETWORK,
            error_message="Connection timeout (10s)",
            command_used=command_used,
            timestamp=timestamp,
        ).to_dict()

    except FileNotFoundError:
        return RegistryResult(
            component=component,
            image_ref=image_ref,
            registry_host=registry_host,
            repository_path=repository_path,
            tag=tag,
            success=False,
            failure_class=FAIL_IMAGE_UNKNOWN,
            error_message="curl not available in environment",
            command_used=command_used,
            timestamp=timestamp,
        ).to_dict()

    except Exception as e:
        error_str = str(e)
        error_lower = error_str.lower()
        if "ssl" in error_lower or "tls" in error_lower or "certificate" in error_lower:
            failure_class = FAIL_IMAGE_TLS
        elif "network" in error_lower or "connect" in error_lower or "dns" in error_lower:
            failure_class = FAIL_IMAGE_NETWORK
        else:
            failure_class = FAIL_IMAGE_UNKNOWN

        return RegistryResult(
            component=component,
            image_ref=image_ref,
            registry_host=registry_host,
            repository_path=repository_path,
            tag=tag,
            success=False,
            failure_class=failure_class,
            error_message=sanitize_error(error_str),
            command_used=command_used,
            timestamp=timestamp,
        ).to_dict()


def _infer_component(image_ref: str) -> str:
    """Infer component name from image reference."""
    image_lower = image_ref.lower()
    if "frontend" in image_lower:
        return "frontend"
    if "backend" in image_lower:
        return "backend"
    if "scheduler" in image_lower:
        return "scheduler"
    return "unknown"


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Check registry manifest")
    parser.add_argument("--image", required=True, help="Image reference")
    parser.add_argument("--registry-username", default=None)
    parser.add_argument("--registry-password", default=None)
    args = parser.parse_args(sys.argv[1:])

    result = check_manifest_with_curl(args.image, args.registry_username, args.registry_password)
    print(json.dumps(result, indent=2))
