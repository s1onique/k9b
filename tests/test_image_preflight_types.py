#!/usr/bin/env python3
"""Tests for image preflight types.

Tests:
- ImagePullSecretStatus data class
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from k9b_cnpg_image_preflight_types import ImagePullSecretStatus


class TestImagePullSecretStatus:
    """Tests for ImagePullSecretStatus data class."""

    def test_to_dict_contains_all_fields(self) -> None:
        """Should serialize all fields to dict."""
        status = ImagePullSecretStatus(
            namespace="k9b-cnpg-lab-123",
            secrets_exist=True,
            secret_names=["reg-creds", "another-secret"],
            has_service_account_ref=True,
            service_account_name="default",
            error_message="",
        )
        d = status.to_dict()
        assert d["namespace"] == "k9b-cnpg-lab-123"
        assert d["secrets_exist"] is True
        assert d["secret_names"] == ["reg-creds", "another-secret"]
        assert d["has_service_account_ref"] is True
        assert d["service_account_name"] == "default"

    def test_no_secret_data_leaked(self) -> None:
        """Should not expose secret data types."""
        status = ImagePullSecretStatus(
            namespace="test",
            secrets_exist=True,
            secret_names=["reg-creds"],
        )
        d = status.to_dict()
        assert "data" not in d
        assert "dockerconfigjson" not in str(d)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
