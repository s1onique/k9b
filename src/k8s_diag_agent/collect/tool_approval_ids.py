"""Approval stream ID generation.

This module contains ID generation functions:
- new_request_id: Generate unique request IDs
- new_stream_id: Generate unique stream IDs

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-APPROVAL-STREAM01
"""
from __future__ import annotations


def new_request_id() -> str:
    """Generate a new request ID.
    
    Returns:
        32-character hex string (16 bytes of entropy)
    """
    import secrets
    return secrets.token_hex(16)


def new_stream_id() -> str:
    """Generate a new stream ID.
    
    Returns:
        32-character hex string (16 bytes of entropy)
    """
    import secrets
    return secrets.token_hex(16)


__all__ = [
    "new_request_id",
    "new_stream_id",
]
