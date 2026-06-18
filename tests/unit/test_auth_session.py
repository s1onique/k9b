"""Tests for session management (AUTH-02/03).

Tests cover:
- Session creation with opaque ID
- Session lookup before expiry
- Session expiry denies access
- Logout invalidates session
- Session ID is cryptographically random
- Session attributes are set correctly
"""

from __future__ import annotations

import time
import unittest

from k8s_diag_agent.ui.auth_session import (
    SessionStore,
    create_session,
    delete_session,
    get_session,
    reset_session_store,
)


class TestSessionCreation(unittest.TestCase):
    """Tests for session creation."""

    def setUp(self) -> None:
        """Reset session store before each test."""
        reset_session_store()

    def test_create_session_returns_opaque_id(self) -> None:
        """Session should have an opaque ID."""
        session = create_session("test-user")
        self.assertIsInstance(session.session_id, str)
        self.assertGreater(len(session.session_id), 20)  # Should be long

    def test_create_session_unique_ids(self) -> None:
        """Each session should have a unique ID."""
        session1 = create_session("user1")
        session2 = create_session("user2")
        self.assertNotEqual(session1.session_id, session2.session_id)

    def test_create_session_stores_principal(self) -> None:
        """Session should store the principal ID."""
        session = create_session("admin-user")
        self.assertEqual(session.principal_id, "admin-user")

    def test_create_session_sets_timestamps(self) -> None:
        """Session should have created_at and last_accessed_at set."""
        before = time.time()
        session = create_session("test")
        after = time.time()

        self.assertGreaterEqual(session.created_at, before)
        self.assertLessEqual(session.created_at, after)
        self.assertEqual(session.created_at, session.last_accessed_at)

    def test_create_session_id_is_url_safe(self) -> None:
        """Session ID should be URL-safe (base64 encoded)."""
        session = create_session("test")
        # URL-safe base64 uses A-Za-z0-9_- and no padding
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
        self.assertTrue(all(c in valid_chars for c in session.session_id))


class TestSessionLookup(unittest.TestCase):
    """Tests for session lookup."""

    def setUp(self) -> None:
        """Reset session store before each test."""
        reset_session_store()

    def test_get_session_works_before_expiry(self) -> None:
        """Valid session should be retrievable."""
        session = create_session("test-user")
        retrieved = get_session(session.session_id)

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.principal_id, "test-user")

    def test_get_session_touches_last_accessed(self) -> None:
        """Getting a session should update last_accessed_at."""
        session = create_session("test-user")
        original_accessed = session.last_accessed_at

        # Wait a tiny bit
        time.sleep(0.01)

        retrieved = get_session(session.session_id)
        self.assertIsNotNone(retrieved)
        self.assertGreater(retrieved.last_accessed_at, original_accessed)

    def test_get_session_unknown_id_returns_none(self) -> None:
        """Unknown session ID should return None."""
        result = get_session("unknown-session-id")
        self.assertIsNone(result)


class TestSessionExpiry(unittest.TestCase):
    """Tests for session expiry."""

    def setUp(self) -> None:
        """Reset session store before each test."""
        reset_session_store()

    def test_session_is_expired_after_max_age(self) -> None:
        """Session should be expired after max age."""
        store = SessionStore(max_age_seconds=1, idle_timeout_seconds=3600)
        session = store.create("test-user")

        # Session should not be expired yet
        self.assertFalse(session.is_expired)

        # Wait for expiry
        time.sleep(1.1)

        # Now session should be expired
        self.assertTrue(session.is_expired)

    def test_session_is_idle_expired_after_timeout(self) -> None:
        """Session should expire after idle timeout."""
        store = SessionStore(max_age_seconds=3600, idle_timeout_seconds=1)
        session = store.create("test-user")

        # Session should not be idle expired yet
        self.assertFalse(session.is_idle_expired)

        # Wait for idle timeout
        time.sleep(1.1)

        # Now session should be idle expired
        self.assertTrue(session.is_idle_expired)

    def test_get_expired_session_returns_none(self) -> None:
        """Getting an expired session should return None."""
        store = SessionStore(max_age_seconds=1, idle_timeout_seconds=3600)
        session = store.create("test-user")
        session_id = session.session_id

        # Wait for expiry
        time.sleep(1.1)

        # Session should be expired
        result = store.get(session_id)
        self.assertIsNone(result)


class TestSessionDeletion(unittest.TestCase):
    """Tests for session deletion (logout)."""

    def setUp(self) -> None:
        """Reset session store before each test."""
        reset_session_store()

    def test_delete_session_invalidates(self) -> None:
        """Deleting a session should make it inaccessible."""
        session = create_session("test-user")
        session_id = session.session_id

        # Verify session exists
        self.assertIsNotNone(get_session(session_id))

        # Delete session
        result = delete_session(session_id)
        self.assertTrue(result)

        # Session should be gone
        self.assertIsNone(get_session(session_id))

    def test_delete_nonexistent_session_returns_false(self) -> None:
        """Deleting a non-existent session should return False."""
        result = delete_session("nonexistent-id")
        self.assertFalse(result)


class TestSessionStore(unittest.TestCase):
    """Tests for SessionStore functionality."""

    def setUp(self) -> None:
        """Reset session store before each test."""
        reset_session_store()

    def test_session_store_count(self) -> None:
        """Store should track session count."""
        store = SessionStore()
        self.assertEqual(store.count(), 0)

        store.create("user1")
        self.assertEqual(store.count(), 1)

        store.create("user2")
        self.assertEqual(store.count(), 2)

    def test_session_store_clear(self) -> None:
        """Store should clear all sessions."""
        store = SessionStore()
        store.create("user1")
        store.create("user2")

        store.clear()
        self.assertEqual(store.count(), 0)

    def test_session_store_cleanup_expired(self) -> None:
        """Cleanup should remove expired sessions."""
        store = SessionStore(max_age_seconds=1, idle_timeout_seconds=3600)
        store.create("user1")
        store.create("user2")

        # Wait for expiry
        time.sleep(1.1)

        # Cleanup should remove expired sessions
        removed = store.cleanup_expired()
        self.assertEqual(removed, 2)
        self.assertEqual(store.count(), 0)


if __name__ == "__main__":
    unittest.main()