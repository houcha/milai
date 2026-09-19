"""Learner-scoped storage; a successful turn commits state and transcript together."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def identifier() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(UTC).isoformat()


class InvalidReference(ValueError):
    """An opaque reference is absent, wrong-kind, or outside learner scope."""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.exists():
            path.touch(mode=0o600)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, learner TEXT NOT NULL, created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES sessions(id),
                created TEXT NOT NULL, message TEXT NOT NULL, reply TEXT NOT NULL,
                items TEXT NOT NULL, prompt_version TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY, learner TEXT NOT NULL, kind TEXT NOT NULL,
                created TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS records_owner ON records(learner, kind);
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, learner TEXT NOT NULL, session TEXT NOT NULL,
                turn_id TEXT NOT NULL, record_id TEXT NOT NULL,
                kind TEXT NOT NULL, created TEXT NOT NULL, prompt_version TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT);
            INSERT OR IGNORE INTO metadata
                VALUES ('local_owner', lower(hex(randomblob(16))));
        """)

    @property
    def owner(self) -> str:
        return self.db.execute(
            "SELECT value FROM metadata WHERE key='local_owner'"
        ).fetchone()[0]

    def session(self, learner: str, session: str | None = None) -> str:
        if session:
            self.authorize(learner, session)
            return session
        session = identifier()
        self.db.execute(
            "INSERT INTO sessions VALUES (?, ?, ?)", (session, learner, now())
        )
        return session

    def authorize(self, learner: str, session: str):
        row = self.db.execute(
            "SELECT learner FROM sessions WHERE id=?", (session,)
        ).fetchone()
        if row is None or row[0] != learner:
            raise PermissionError("Session is unavailable for this learner")

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def records(
        self, learner: str, kind: str | None = None, limit: int = 60
    ) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM records WHERE learner=? AND (? IS NULL OR kind=?) "
            "ORDER BY rowid DESC LIMIT ?",
            (learner, kind, kind, limit),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "kind": r["kind"],
                "created": r["created"],
                **json.loads(r["payload"]),
            }
            for r in reversed(rows)
        ]

    def record(self, learner: str, record_id: str, kind: str | None = None) -> dict:
        row = self.db.execute(
            "SELECT * FROM records WHERE learner=? AND id=?", (learner, record_id)
        ).fetchone()
        if row is None or (kind and row["kind"] != kind):
            raise InvalidReference("Referenced record is unavailable for this learner")
        return {"id": row["id"], "kind": row["kind"], **json.loads(row["payload"])}

    def exercise_records(self, learner: str, kind: str, exercise_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT payload FROM records WHERE learner=? AND kind=? "
            "AND json_extract(payload, '$.exercise_id')=?",
            (learner, kind, exercise_id),
        )
        return [json.loads(row[0]) for row in rows]

    def append(self, ctx, kind: str, payload: dict) -> dict:
        self.authorize(ctx.learner, ctx.session)
        if not self.db.in_transaction:
            raise RuntimeError("Learning writes require an application transaction")
        record_id, event_id = identifier(), identifier()
        self.db.execute(
            "INSERT INTO records VALUES (?, ?, ?, ?, ?)",
            (
                record_id,
                ctx.learner,
                kind,
                now(),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        self.db.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                ctx.learner,
                ctx.session,
                ctx.turn_id,
                record_id,
                kind,
                now(),
                ctx.prompt_version,
            ),
        )
        ctx.event_ids.append(event_id)
        return {"id": record_id, "kind": kind, **payload}

    def history(self, learner: str, session: str) -> list:
        self.authorize(learner, session)
        rows = self.db.execute(
            "SELECT items FROM turns WHERE session=? ORDER BY rowid DESC LIMIT 12",
            (session,),
        ).fetchall()
        selected, size = [], 0
        for row in rows:
            size += len(row[0])
            if size > 48000:
                break
            selected.append(json.loads(row[0]))
        return [item for turn in reversed(selected) for item in turn]

    def save_turn(self, ctx, reply: str, items: list):
        self.db.execute(
            "INSERT INTO turns VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ctx.turn_id,
                ctx.session,
                now(),
                ctx.message,
                reply,
                json.dumps(items, ensure_ascii=False),
                ctx.prompt_version,
            ),
        )

    def conversation(self, learner: str, session: str, limit: int = 50) -> list[dict]:
        """Return learner-facing messages without replaying internal tool traffic."""
        self.authorize(learner, session)
        rows = self.db.execute(
            "SELECT created, message, reply FROM turns WHERE session=? "
            "ORDER BY rowid DESC LIMIT ?",
            (session, limit),
        ).fetchall()
        messages = []
        for row in reversed(rows):
            messages.extend(
                (
                    {
                        "role": "user",
                        "content": row["message"],
                        "created": row["created"],
                    },
                    {
                        "role": "assistant",
                        "content": row["reply"],
                        "created": row["created"],
                    },
                )
            )
        return messages

    def snapshot(self, learner: str) -> dict:
        facts = [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT payload FROM records WHERE rowid IN "
                "(SELECT max(rowid) FROM records WHERE learner=? AND kind='profile' "
                "GROUP BY json_extract(payload, '$.field'))",
                (learner,),
            )
        ]
        profile = {fact["field"]: fact for fact in facts}
        evidence = self.records(learner, "evidence", 40)
        # This is a count of observations, not a hard-coded mastery/teaching policy.
        recurring = self.db.execute(
            "SELECT json_extract(payload, '$.skill') AS skill, count(*) AS count "
            "FROM records WHERE learner=? AND kind='evidence' "
            "AND json_extract(payload, '$.outcome')='needs_work' GROUP BY skill",
            (learner,),
        ).fetchall()
        return {
            "profile": profile,
            "curriculum": self.records(learner, "curriculum", 1),
            "evidence": evidence,
            "recurring_observations": [dict(r) for r in recurring],
            "exercises": self.records(learner, "exercise", 8),
            "assistance": self.records(learner, "assistance", 20),
            "sources": self.records(learner, "source", 5),
            "teaching_actions": self.records(learner, "teaching_action", 5),
        }

    def inspect(self, learner: str) -> dict:
        return {
            "state": self.snapshot(learner),
            "events": [
                dict(r)
                for r in self.db.execute(
                    "SELECT * FROM events WHERE learner=? ORDER BY rowid", (learner,)
                )
            ],
            "sessions": [
                dict(r)
                for r in self.db.execute(
                    "SELECT * FROM sessions WHERE learner=? ORDER BY rowid", (learner,)
                )
            ],
        }

    def close(self):
        self.db.close()
