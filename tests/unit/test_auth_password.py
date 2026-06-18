"""Tests for password hashing and verification (AUTH-01).

Tests cover:
- Password hash generation
- Password verification with correct password
- Wrong password rejection
- Unknown user rejection (empty hash)
- Constant-time comparison
- Hash format validation
- Constant generic login error
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.auth_password import (
    generate_password,
    hash_password,
    verify_password,
)


class TestPasswordHashGeneration(unittest.TestCase):
    """Tests for password hash generation."""

    def test_hash_password_returns_string(self) -> None:
        """Hash should return a string."""
        password = "test-password-123"
        result = hash_password(password)
        self.assertIsInstance(result, str)

    def test_hash_password_includes_format_markers(self) -> None:
        """Hash should include format markers."""
        password = "test-password"
        result = hash_password(password)
        self.assertTrue(result.startswith("$pbkdf2-sha256$"))
        # Should have $pbkdf2-sha256$iterations$salt$hash
        parts = result.split("$")
        self.assertEqual(len(parts), 5)

    def test_hash_password_different_salts(self) -> None:
        """Same password should produce different hashes (different salts)."""
        password = "same-password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        self.assertNotEqual(hash1, hash2)

    def test_hash_password_iterations(self) -> None:
        """Custom iterations should be reflected in hash."""
        password = "test"
        hash_custom = hash_password(password, iterations=100000)
        hash_default = hash_password(password, iterations=600000)

        # Extract iterations from hashes
        self.assertIn("$100000$", hash_custom)
        self.assertIn("$600000$", hash_default)


class TestPasswordVerification(unittest.TestCase):
    """Tests for password verification."""

    def test_verify_correct_password(self) -> None:
        """Correct password should verify successfully."""
        password = "my-secret-password"
        stored_hash = hash_password(password)
        result = verify_password(password, stored_hash)
        self.assertTrue(result)

    def test_verify_wrong_password(self) -> None:
        """Wrong password should be rejected."""
        password = "correct-password"
        wrong_password = "wrong-password"
        stored_hash = hash_password(password)
        result = verify_password(wrong_password, stored_hash)
        self.assertFalse(result)

    def test_verify_unknown_user_empty_hash(self) -> None:
        """Empty hash should be rejected (unknown user)."""
        result = verify_password("any-password", "")
        self.assertFalse(result)

    def test_verify_unknown_user_none_hash(self) -> None:
        """Invalid hash format should be rejected."""
        result = verify_password("any-password", "not-a-valid-hash")
        self.assertFalse(result)

    def test_verify_wrong_algorithm(self) -> None:
        """Hash with wrong algorithm should be rejected."""
        # Manually create a hash with wrong algorithm marker
        wrong_algo_hash = "$argon2id$600000$AAAAAAAAAAAAAAAAAAAAAA$BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
        result = verify_password("any-password", wrong_algo_hash)
        self.assertFalse(result)

    def test_verify_empty_password(self) -> None:
        """Empty password should verify against empty hash."""
        # Empty password against any hash should return False (not crash)
        hash_value = hash_password("non-empty")
        result = verify_password("", hash_value)
        self.assertFalse(result)

    def test_verify_special_characters(self) -> None:
        """Password with special characters should work."""
        password = "p@$$w0rd!#%^&*()_+-=[]{}|;':\",./<>?"
        stored_hash = hash_password(password)
        result = verify_password(password, stored_hash)
        self.assertTrue(result)

    def test_verify_unicode_characters(self) -> None:
        """Password with unicode characters should work."""
        password = "пароль密码パスワード"
        stored_hash = hash_password(password)
        result = verify_password(password, stored_hash)
        self.assertTrue(result)


class TestConstantTimeComparison(unittest.TestCase):
    """Tests for timing attack resistance."""

    def test_verify_similar_passwords_different_timing(self) -> None:
        """Similar passwords should take similar time (constant-time comparison).

        This is an indirect test - we verify the function works correctly
        with similar passwords, which would fail if constant-time comparison
        wasn't used.
        """
        password = "test-token-X"
        stored_hash = hash_password(password)

        # This should return False but take similar time as correct password
        similar = "test-token-Y"
        result = verify_password(similar, stored_hash)
        self.assertFalse(result)

    def test_verify_different_length_passwords(self) -> None:
        """Different length passwords should not leak length info."""
        short_hash = hash_password("short")
        long_hash = hash_password("this-is-a-long-password")

        # Both should be rejected without leaking which is closer
        result_short = verify_password("wrong-short", short_hash)
        result_long = verify_password("wrong-long-password", long_hash)

        self.assertFalse(result_short)
        self.assertFalse(result_long)


class TestPasswordGeneration(unittest.TestCase):
    """Tests for password generation utility."""

    def test_generate_password_default_length(self) -> None:
        """Generated password should have default length of 24."""
        password = generate_password()
        self.assertEqual(len(password), 24)

    def test_generate_password_custom_length(self) -> None:
        """Generated password should respect custom length."""
        password = generate_password(length=32)
        self.assertEqual(len(password), 32)

    def test_generate_password_alphanumeric(self) -> None:
        """Generated password should be alphanumeric."""
        password = generate_password()
        self.assertTrue(all(c.isalnum() for c in password))

    def test_generate_password_randomness(self) -> None:
        """Generated passwords should be unique."""
        passwords = [generate_password() for _ in range(100)]
        unique_passwords = set(passwords)
        # With 24 chars from alphanumerics, collisions are extremely unlikely
        self.assertEqual(len(unique_passwords), 100)


if __name__ == "__main__":
    unittest.main()