"""SQLite persistence with append-only events and auditable label revisions."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  agent TEXT NOT NULL,
  external_id TEXT,
  session_id TEXT,
  goal TEXT NOT NULL,
  config_hash TEXT,
  created_at TEXT NOT NULL,
  source_started_at TEXT,
  UNIQUE(agent, external_id)
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TABLE IF NOT EXISTS ingestion_cursors (
  agent TEXT NOT NULL,
  external_id TEXT NOT NULL,
  last_message_id INTEGER NOT NULL,
  PRIMARY KEY(agent, external_id)
);
CREATE TABLE IF NOT EXISTS labels (
  task_id TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE CASCADE,
  outcome TEXT NOT NULL,
  failure_stage TEXT NOT NULL,
  expected_selection TEXT,
  comment TEXT,
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS label_revisions (
  revision_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
  outcome TEXT NOT NULL,
  failure_stage TEXT NOT NULL,
  expected_selection TEXT,
  comment TEXT,
  source TEXT NOT NULL,
  actor TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_label_revisions_task ON label_revisions(task_id, created_at);
CREATE TABLE IF NOT EXISTS task_segments (
  task_id TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE CASCADE,
  segment_type TEXT NOT NULL CHECK(segment_type IN ('task','ambiguous')),
  ambiguous_reason TEXT
);
CREATE TABLE IF NOT EXISTS segment_messages (
  task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
  agent TEXT NOT NULL,
  session_id TEXT NOT NULL,
  message_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  is_automated INTEGER NOT NULL DEFAULT 0,
  event_source TEXT NOT NULL CHECK(event_source IN ('user','background','delegation','cron')),
  relation TEXT NOT NULL CHECK(relation IN ('new_task','continuation','correction','child_event')),
  PRIMARY KEY(agent, session_id, message_id),
  UNIQUE(task_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_segment_messages_task ON segment_messages(task_id, message_id);
CREATE TABLE IF NOT EXISTS schema_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT OR IGNORE INTO label_revisions
SELECT 'legacy_' || task_id, task_id, outcome, failure_stage, expected_selection,
       comment, source, source, 'Legacy current label migration', updated_at
FROM labels
WHERE NOT EXISTS (
  SELECT 1 FROM label_revisions existing WHERE existing.task_id = labels.task_id
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        # Explicit additive migration for v0.5 databases. The Hermes adapter still
        # rejects v1 segmentation because message ownership cannot be merged in place.
        columns = {row["name"] for row in self.con.execute("PRAGMA table_info(segment_messages)")}
        if "event_source" not in columns:
            self.con.execute("ALTER TABLE segment_messages ADD COLUMN event_source TEXT NOT NULL DEFAULT 'background'")
        if "relation" not in columns:
            self.con.execute("ALTER TABLE segment_messages ADD COLUMN relation TEXT NOT NULL DEFAULT 'continuation'")
        segment_columns = {row["name"] for row in self.con.execute("PRAGMA table_info(task_segments)")}
        if "ambiguous_reason" not in segment_columns:
            self.con.execute("ALTER TABLE task_segments ADD COLUMN ambiguous_reason TEXT")
        task_columns = {row["name"] for row in self.con.execute("PRAGMA table_info(tasks)")}
        if "source_started_at" not in task_columns:
            self.con.execute("ALTER TABLE tasks ADD COLUMN source_started_at TEXT")
        self.con.commit()

    def close(self) -> None:
        with self.lock:
            self.con.close()

    @contextmanager
    def transaction(self):
        with self.lock, self.con:
            yield

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.lock, self.con:
            return self.con.execute(sql, params)

    def one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        with self.lock:
            row = self.con.execute(sql, params).fetchone()
            return dict(row) if row else None

    def all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.con.execute(sql, params).fetchall()]

    @staticmethod
    def payload(row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row["payload"] = json.loads(row["payload"])
        return row
