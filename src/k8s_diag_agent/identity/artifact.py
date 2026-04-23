"""Artifact identity using UUIDv7 and shared artifact write helpers."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID


def new_artifact_id() -> str:
    """Generate a new immutable artifact ID using UUIDv7.

    UUIDv7 combines timestamp with random data, providing:
    - Time-ordered IDs (useful for sorting)
    - Immutable IDs (once generated, never changes)
    - Globally unique identifiers

    Returns:
        A UUIDv7 string representation.
    """
    return str(_uuid7())


def _uuid7() -> UUID:
    """Generate a UUIDv7.

    UUIDv7 structure:
    - 48 bits: timestamp_ms (milliseconds since Unix epoch)
    - 4 bits: version (7)
    - 12 bits: variant and high 8 bits of random
    - 62 bits: remaining random data

    Returns:
        A UUIDv7 instance.
    """
    # Get current timestamp in milliseconds
    timestamp_ms = int(time.time() * 1000)

    # Generate random bytes (only need 10 bytes for UUIDv7)
    import secrets

    random_bytes = bytearray(secrets.randbits(80).to_bytes(10, byteorder="big"))

    # Pack timestamp_ms into first 48 bits (6 bytes)
    timestamp_bytes = timestamp_ms.to_bytes(6, byteorder="big")

    # Build UUID bytes
    # First 6 bytes: timestamp (48 bits)
    uuid_bytes = bytearray(timestamp_bytes)

    # Next byte: version 7 in high 4 bits, top 4 bits of random
    version_and_random = (7 << 4) | ((random_bytes[0] >> 4) & 0x0F)
    uuid_bytes.append(version_and_random)

    # Add remaining random bytes (9 bytes)
    uuid_bytes.extend(random_bytes[1:])

    # Set variant bits (RFC 4122) in byte 9: 0b10xx_xxxx
    uuid_bytes[8] = (uuid_bytes[8] & 0x3F) | 0x80

    # Convert to UUID
    return UUID(bytes=bytes(uuid_bytes))


def write_append_only_json_artifact(
    path: Path,
    data: Mapping[str, Any],
    *,
    context: str | None = None,
) -> Path:
    """Write an immutable JSON artifact to disk.

    This helper enforces append-only semantics for artifact writes:
    - Creates parent directories as needed
    - Rejects overwrites to enforce immutability contract
    - Writes JSON with stable formatting (indent=2, utf-8)

    Mutable exceptions (NOT covered by this guard):
    - history.json
    - alertmanager-source-registry.json
    - ui-index.json
    - diagnostic-packs/latest/
    - per-run override artifacts
    - any other explicitly documented mutable/derived artifacts

    Args:
        path: Precomputed path where the artifact should be written.
        data: Serializable mapping (e.g., dict or artifact.to_dict() result).
        context: Optional context string for error messages when path exists.

    Returns:
        The path to the written artifact.

    Raises:
        FileExistsError: If the artifact path already exists (immutability guarantee).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        if context:
            raise FileExistsError(
                f"Artifact already exists at {path}; "
                f"immutability contract violated: {context}"
            )
        raise FileExistsError(
            f"Artifact already exists at {path}; "
            f"immutability contract violated"
        )

    path.write_text(json.dumps(dict(data), indent=2), encoding="utf-8")
    return path
