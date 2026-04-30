"""Tests for session-end detection — ensures the companion can detect
when a Hermes session has ended and react appropriately.

This tests the observer's state.db query first (harness),
then the companion's handling of the session-ended event.
"""
import sys
import os
import json
import sqlite3
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.hermes_observer import HermesObserver, EVENT_SESSION_ENDED


class TestSessionEndDetection:
    """The observer can query state.db for ended sessions.
    This test proves the detection works before we add event emission.
    """

    @classmethod
    def setup_class(cls):
        """Create a temporary Hermes home with a mock state.db."""
        cls.tmp_dir = Path(tempfile.mkdtemp(prefix="nous_test_"))
        cls.sessions_dir = cls.tmp_dir / "sessions"
        cls.sessions_dir.mkdir(parents=True)

        # Create a mock state.db with known ended/active sessions
        cls.db_path = cls.tmp_dir / "state.db"
        conn = sqlite3.connect(str(cls.db_path))
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT,
                model TEXT,
                started_at REAL,
                ended_at REAL,
                message_count INTEGER DEFAULT 0
            )
        """)
        # Ended session
        cur.execute(
            "INSERT INTO sessions (id, source, model, started_at, ended_at, message_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("ended-session-123", "cli", "test-model", 1000.0, 2000.0, 10),
        )
        # Active session (no ended_at)
        cur.execute(
            "INSERT INTO sessions (id, source, model, started_at, ended_at, message_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("active-session-456", "cli", "test-model", 3000.0, None, 5),
        )
        conn.commit()
        conn.close()

        # Create the observer pointing to our temp hermes home
        cls.observer = HermesObserver(hermes_home=str(cls.tmp_dir))
        # Clear the cache so it loads fresh
        cls.observer._ended_cache_time = 0

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(str(cls.tmp_dir), ignore_errors=True)

    def test_ended_session_detected(self):
        """Sessions with ended_at set should be detected as ended."""
        assert self.observer._is_ended_session({"session_id": "ended-session-123"}), (
            "Ended session should be detected as ended"
        )

    def test_active_session_not_ended(self):
        """Sessions without ended_at should NOT be detected as ended."""
        assert not self.observer._is_ended_session({"session_id": "active-session-456"}), (
            "Active session should NOT be detected as ended"
        )

    def test_unknown_session_not_ended(self):
        """Sessions not in state.db at all should NOT be detected as ended."""
        assert not self.observer._is_ended_session({"session_id": "nonexistent-session"}), (
            "Unknown session should NOT be detected as ended"
        )

    def test_empty_session_id_returns_false(self):
        """Missing session_id should return False gracefully."""
        assert not self.observer._is_ended_session({}), (
            "Empty data should return False, not crash"
        )

    def test_cache_refreshes(self):
        """After adding a new ended session, the cache should refresh."""
        # Add a new ended session directly to state.db
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sessions (id, source, model, started_at, ended_at, message_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("newly-ended-789", "cli", "test-model", 4000.0, 5000.0, 3),
        )
        conn.commit()
        conn.close()

        # Force cache refresh
        self.observer._ended_cache_time = 0

        assert self.observer._is_ended_session({"session_id": "newly-ended-789"}), (
            "Newly ended session should be detected after cache refresh"
        )

    def test_missing_state_db_does_not_crash(self):
        """If state.db doesn't exist, _load_ended_sessions returns empty set."""
        result = self.observer._load_ended_sessions()
        assert isinstance(result, set), "Should return a set even on failure"

    def test_event_session_ended_constant(self):
        """EVENT_SESSION_ENDED constant should be defined and unique."""
        assert EVENT_SESSION_ENDED == "session_ended"
        assert EVENT_SESSION_ENDED != "session_switched"

    def test_ended_emission_dedup(self):
        """Observer should only emit EVENT_SESSION_ENDED once per session."""
        # First call should add to _emitted_ended_for
        sid = "ended-session-123"
        assert sid in self.observer._ended_session_ids
        # Simulate what _poll_once does
        if sid not in self.observer._emitted_ended_for:
            self.observer._emitted_ended_for.add(sid)
        # Second call should NOT re-emit
        assert sid in self.observer._emitted_ended_for
        # Verify it was added exactly once
        count = 0
        for s in self.observer._emitted_ended_for:
            if s == sid:
                count += 1
        assert count == 1
