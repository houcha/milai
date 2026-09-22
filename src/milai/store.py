# ruff: noqa: E501, S608
"""Normalized learner state with atomic turn and presentation persistence."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = "3"


def identifier() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(UTC).isoformat()


class InvalidReference(ValueError):
    """An opaque reference is absent, wrong-kind, or outside learner scope."""


class SchemaMismatch(RuntimeError):
    """The database cannot be opened without an explicit reset."""

    def __init__(self, found: str | None):
        label = found or "legacy/unversioned"
        super().__init__(
            f"Database schema {label} is incompatible with schema {SCHEMA_VERSION}. "
            "Run `milai reset --yes` to archive it and create a fresh database."
        )
        self.found = found


SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sessions (id TEXT PRIMARY KEY, learner TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE turns (
    id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES sessions(id),
    learner TEXT NOT NULL, created TEXT NOT NULL, message TEXT NOT NULL,
    reply TEXT NOT NULL, items TEXT NOT NULL, prompt_version TEXT NOT NULL
);
CREATE INDEX turns_session ON turns(session, created);
CREATE TABLE events (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL,
    session TEXT NOT NULL REFERENCES sessions(id), turn_id TEXT NOT NULL,
    entity_id TEXT NOT NULL, kind TEXT NOT NULL, created TEXT NOT NULL,
    prompt_version TEXT NOT NULL
);
CREATE INDEX events_learner ON events(learner, created);
CREATE TABLE learner_facts (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL, field TEXT NOT NULL,
    value TEXT NOT NULL, learner_quote TEXT NOT NULL, created TEXT NOT NULL
);
CREATE INDEX facts_current ON learner_facts(learner, field, created);
CREATE TABLE sources (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL, status TEXT NOT NULL,
    title TEXT, url TEXT, provenance TEXT NOT NULL, text TEXT, reason TEXT,
    retrieved_at TEXT, sha256 TEXT, truncated INTEGER,
    created TEXT NOT NULL
);
CREATE INDEX sources_learner ON sources(learner, created);
CREATE TABLE skills (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL, language TEXT NOT NULL,
    skill_key TEXT NOT NULL, name TEXT NOT NULL, definition TEXT NOT NULL,
    success_criteria TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'superseded')),
    version INTEGER NOT NULL, created TEXT NOT NULL,
    UNIQUE(learner, language, skill_key, version)
);
CREATE INDEX skills_active ON skills(learner, language, status);
CREATE TABLE skill_prerequisites (
    learner TEXT NOT NULL,
    prerequisite_id TEXT NOT NULL REFERENCES skills(id),
    dependent_id TEXT NOT NULL REFERENCES skills(id), created TEXT NOT NULL,
    PRIMARY KEY(prerequisite_id, dependent_id)
);
CREATE TABLE skill_changes (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL, reason TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE skill_supersessions (
    change_id TEXT NOT NULL REFERENCES skill_changes(id),
    old_skill_id TEXT NOT NULL REFERENCES skills(id),
    new_skill_id TEXT NOT NULL REFERENCES skills(id),
    relation TEXT NOT NULL CHECK(relation IN ('redefined', 'split', 'merged')),
    PRIMARY KEY(change_id, old_skill_id, new_skill_id)
);
CREATE TABLE topics (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL, language TEXT NOT NULL,
    name TEXT NOT NULL, purpose TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'archived')), created TEXT NOT NULL
);
CREATE INDEX topics_learner ON topics(learner, status, created);
CREATE TABLE topic_skills (
    topic_id TEXT NOT NULL REFERENCES topics(id), skill_id TEXT NOT NULL REFERENCES skills(id),
    role TEXT NOT NULL CHECK(role IN ('core', 'extension', 'contextual')),
    priority INTEGER NOT NULL, created TEXT NOT NULL, PRIMARY KEY(topic_id, skill_id)
);
CREATE TABLE focuses (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL, topic_id TEXT NOT NULL REFERENCES topics(id),
    reason TEXT NOT NULL, active INTEGER NOT NULL CHECK(active IN (0, 1)), created TEXT NOT NULL
);
CREATE UNIQUE INDEX one_active_focus ON focuses(learner) WHERE active=1;
CREATE TABLE focus_skills (
    focus_id TEXT NOT NULL REFERENCES focuses(id), skill_id TEXT NOT NULL REFERENCES skills(id),
    role TEXT NOT NULL CHECK(role IN ('target', 'supporting')), PRIMARY KEY(focus_id, skill_id)
);
CREATE TABLE exercises (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL, topic_id TEXT NOT NULL REFERENCES topics(id),
    title TEXT NOT NULL, task TEXT NOT NULL, context TEXT NOT NULL, hint TEXT,
    scaffolding TEXT NOT NULL CHECK(scaffolding IN ('none', 'cues', 'worked_example')),
    created_turn TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE exercise_skills (
    exercise_id TEXT NOT NULL REFERENCES exercises(id), skill_id TEXT NOT NULL REFERENCES skills(id),
    role TEXT NOT NULL CHECK(role IN ('target', 'supporting')), success_criterion TEXT NOT NULL,
    PRIMARY KEY(exercise_id, skill_id)
);
CREATE TABLE exercise_sources (
    exercise_id TEXT NOT NULL REFERENCES exercises(id), source_id TEXT NOT NULL REFERENCES sources(id),
    PRIMARY KEY(exercise_id, source_id)
);
CREATE TABLE assistance (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL, exercise_id TEXT NOT NULL REFERENCES exercises(id),
    level TEXT NOT NULL CHECK(level IN ('hint', 'explanation', 'answer_shown')),
    content TEXT NOT NULL, turn_id TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE assistance_skills (
    assistance_id TEXT NOT NULL REFERENCES assistance(id), skill_id TEXT NOT NULL REFERENCES skills(id),
    PRIMARY KEY(assistance_id, skill_id)
);
CREATE TABLE attempts (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL, exercise_id TEXT NOT NULL REFERENCES exercises(id),
    turn_id TEXT NOT NULL, learner_response TEXT NOT NULL, feedback TEXT NOT NULL,
    created TEXT NOT NULL, UNIQUE(exercise_id, turn_id)
);
CREATE TABLE skill_observations (
    id TEXT PRIMARY KEY, learner TEXT NOT NULL, attempt_id TEXT NOT NULL REFERENCES attempts(id),
    exercise_id TEXT NOT NULL REFERENCES exercises(id), skill_id TEXT NOT NULL REFERENCES skills(id),
    outcome TEXT NOT NULL CHECK(outcome IN ('success', 'needs_work', 'uncertain')),
    rationale TEXT NOT NULL, independent_success INTEGER NOT NULL CHECK(independent_success IN (0, 1)),
    created TEXT NOT NULL, UNIQUE(attempt_id, skill_id)
);
CREATE INDEX observations_skill ON skill_observations(learner, skill_id, created);
CREATE TABLE turn_exercises (
    turn_id TEXT NOT NULL REFERENCES turns(id), position INTEGER NOT NULL,
    exercise_id TEXT NOT NULL REFERENCES exercises(id), PRIMARY KEY(turn_id, position)
);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        existed = self.path.exists()
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        tables = {
            row[0]
            for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if not tables:
            self.db.executescript(SCHEMA)
            self.db.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                (("schema_version", SCHEMA_VERSION), ("local_owner", identifier())),
            )
            os.chmod(self.path, 0o600)
        else:
            version = None
            if "metadata" in tables:
                row = self.db.execute(
                    "SELECT value FROM metadata WHERE key='schema_version'"
                ).fetchone()
                version = row[0] if row else None
            if version != SCHEMA_VERSION:
                self.db.close()
                raise SchemaMismatch(version if existed else None)

        # Add session ownership without resetting existing conversations. The old
        # shared learning state belongs to the most recently used legacy session.
        if "session_scopes" not in tables:
            with self.transaction():
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS session_scopes ("
                    "session TEXT PRIMARY KEY REFERENCES sessions(id), "
                    "scope TEXT NOT NULL UNIQUE, title TEXT NOT NULL DEFAULT '')"
                )
                seen = set()
                for row in self.db.execute(
                    "SELECT s.id, s.learner FROM sessions s ORDER BY "
                    "EXISTS (SELECT 1 FROM turns WHERE session=s.id) DESC, "
                    "coalesce((SELECT max(created) FROM turns WHERE session=s.id), s.created) DESC, s.rowid DESC"
                ).fetchall():
                    scope = (
                        row["learner"]
                        if row["learner"] not in seen
                        else f"session:{row['id']}"
                    )
                    seen.add(row["learner"])
                    self.db.execute(
                        "INSERT INTO session_scopes(session, scope) VALUES (?, ?)",
                        (row["id"], scope),
                    )
        if "hint" not in {
            row[1] for row in self.db.execute("PRAGMA table_info(exercises)")
        }:
            self.db.execute("ALTER TABLE exercises ADD COLUMN hint TEXT")

    @classmethod
    def reset(cls, path: Path) -> list[Path]:
        """Archive an existing database and sidecars, then create schema v2."""
        path = Path(path)
        archived: list[Path] = []
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        for suffix in ("", "-wal", "-shm"):
            old = Path(f"{path}{suffix}")
            if old.exists():
                destination = old.with_name(f"{old.name}.legacy-{stamp}.bak")
                old.replace(destination)
                archived.append(destination)
        fresh = cls(path)
        fresh.close()
        return archived

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
        with self.savepoint():
            self.db.execute(
                "INSERT INTO sessions(id, learner, created) VALUES (?, ?, ?)",
                (session, learner, now()),
            )
            self.db.execute(
                "INSERT INTO session_scopes(session, scope) VALUES (?, ?)",
                (session, f"session:{session}"),
            )
        return session

    def learning_scope(self, learner: str, session: str) -> str:
        self.authorize(learner, session)
        return self.db.execute(
            "SELECT scope FROM session_scopes WHERE session=?", (session,)
        ).fetchone()[0]

    def sessions(self, learner: str) -> list[dict]:
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT s.id, s.created, coalesce(nullif(sc.title, ''), "
                "(SELECT substr(message, 1, 80) FROM turns WHERE session=s.id ORDER BY rowid LIMIT 1), "
                "'New learning session') AS title, "
                "(SELECT count(*) FROM turns WHERE session=s.id) AS turns "
                "FROM sessions s JOIN session_scopes sc ON sc.session=s.id "
                "WHERE s.learner=? ORDER BY s.rowid DESC",
                (learner,),
            )
        ]

    def rename_session(self, learner: str, session: str, title: str) -> None:
        self.authorize(learner, session)
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
            raise ValueError("Use a session name between 1 and 80 characters")
        self.db.execute(
            "UPDATE session_scopes SET title=? WHERE session=?",
            (title.strip(), session),
        )

    def delete_session(self, learner: str, session: str) -> None:
        scope = self.learning_scope(learner, session)
        with self.transaction():
            # Delete dependent records before their parents, retaining other sessions.
            for table, parent, column in (
                ("turn_exercises", "exercises", "exercise_id"),
                ("assistance_skills", "assistance", "assistance_id"),
                ("exercise_sources", "exercises", "exercise_id"),
                ("exercise_skills", "exercises", "exercise_id"),
                ("focus_skills", "focuses", "focus_id"),
                ("topic_skills", "topics", "topic_id"),
                ("skill_supersessions", "skill_changes", "change_id"),
            ):
                self.db.execute(
                    f"DELETE FROM {table} WHERE {column} IN (SELECT id FROM {parent} WHERE learner=?)",
                    (scope,),
                )
            for table in (
                "skill_observations",
                "attempts",
                "assistance",
                "exercises",
                "focuses",
                "skill_prerequisites",
                "skill_changes",
                "topics",
                "skills",
                "sources",
                "learner_facts",
            ):
                self.db.execute(f"DELETE FROM {table} WHERE learner=?", (scope,))
            self.db.execute(
                "DELETE FROM turn_exercises WHERE turn_id IN (SELECT id FROM turns WHERE session=?)",
                (session,),
            )
            self.db.execute(
                "DELETE FROM events WHERE session=? OR learner=?", (session, scope)
            )
            self.db.execute("DELETE FROM turns WHERE session=?", (session,))
            self.db.execute("DELETE FROM session_scopes WHERE session=?", (session,))
            self.db.execute("DELETE FROM sessions WHERE id=?", (session,))

    def latest_session(self, learner: str) -> str | None:
        row = self.db.execute(
            "SELECT s.id FROM sessions s WHERE s.learner=? "
            "AND EXISTS (SELECT 1 FROM turns t WHERE t.session=s.id) "
            "ORDER BY s.rowid DESC LIMIT 1",
            (learner,),
        ).fetchone()
        return row[0] if row else None

    def authorize(self, learner: str, session: str) -> None:
        row = self.db.execute(
            "SELECT s.learner, sc.scope FROM sessions s LEFT JOIN session_scopes sc ON sc.session=s.id WHERE s.id=?",
            (session,),
        ).fetchone()
        if row is None or learner not in (row[0], row[1]):
            raise PermissionError("Session is unavailable for this learner")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    @contextmanager
    def savepoint(self) -> Iterator[None]:
        """Make a single tool call atomic inside the surrounding turn."""
        name = f"tool_{identifier()}"
        self.db.execute(f"SAVEPOINT {name}")
        try:
            yield
            self.db.execute(f"RELEASE SAVEPOINT {name}")
        except BaseException:
            self.db.execute(f"ROLLBACK TO SAVEPOINT {name}")
            self.db.execute(f"RELEASE SAVEPOINT {name}")
            raise

    def _event(self, ctx: Any, kind: str, entity_id: str) -> None:
        if not self.db.in_transaction:
            raise RuntimeError("Learning writes require an application transaction")
        event_id = identifier()
        self.db.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                ctx.learner,
                ctx.session,
                ctx.turn_id,
                entity_id,
                kind,
                now(),
                ctx.prompt_version,
            ),
        )
        ctx.event_ids.append(event_id)

    def _owned(self, table: str, learner: str, entity_id: str) -> sqlite3.Row:
        allowed = {
            "sources",
            "skills",
            "topics",
            "focuses",
            "exercises",
            "assistance",
            "attempts",
        }
        if table not in allowed:
            raise ValueError("Invalid reference kind")
        row = self.db.execute(
            f"SELECT * FROM {table} WHERE id=? AND learner=?", (entity_id, learner)
        ).fetchone()
        if row is None:
            raise InvalidReference("Referenced entity is unavailable for this learner")
        return row

    def record_facts(self, ctx: Any, facts: Iterable[dict]) -> list[dict]:
        saved = []
        for fact in facts:
            fact_id, created = identifier(), now()
            self.db.execute(
                "INSERT INTO learner_facts VALUES (?, ?, ?, ?, ?, ?)",
                (
                    fact_id,
                    ctx.learner,
                    fact["field"],
                    fact["value"],
                    fact["learner_quote"],
                    created,
                ),
            )
            self._event(ctx, "learner_fact", fact_id)
            saved.append({"id": fact_id, **fact, "created": created})
        return saved

    def profile(self, learner: str) -> dict[str, dict]:
        rows = self.db.execute(
            "SELECT * FROM learner_facts WHERE learner=? ORDER BY rowid", (learner,)
        ).fetchall()
        return {
            row["field"]: {
                "id": row["id"],
                "value": row["value"],
                "learner_quote": row["learner_quote"],
                "created": row["created"],
            }
            for row in rows
        }

    def save_source(self, ctx: Any, source: dict) -> dict:
        source_id, created = identifier(), now()
        self.db.execute(
            "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_id,
                ctx.learner,
                source.get("status", "available"),
                source.get("title"),
                source.get("url"),
                source.get("provenance", "retrieved_public_web"),
                source.get("text"),
                source.get("reason"),
                source.get("retrieved_at"),
                source.get("sha256"),
                int(bool(source.get("truncated"))),
                created,
            ),
        )
        self._event(ctx, "source", source_id)
        return {"id": source_id, **source, "created": created}

    def source_urls(self, learner: str) -> set[str]:
        return {
            row[0]
            for row in self.db.execute(
                "SELECT url FROM sources WHERE learner=? AND url IS NOT NULL",
                (learner,),
            )
        }

    def source_excerpt(
        self, learner: str, source_id: str, start: int, length: int
    ) -> dict:
        row = self._owned("sources", learner, source_id)
        if row["status"] != "available":
            raise InvalidReference("Source is unavailable")
        text = row["text"] or ""
        start = min(start, len(text))
        return {
            "source_id": source_id,
            "title": row["title"],
            "url": row["url"],
            "start": start,
            "text": text[start : start + length],
            "has_more": start + length < len(text),
        }

    def search_skills(
        self, learner: str, language: str, query: str, limit: int
    ) -> list[dict]:
        pattern = f"%{query.lower()}%"
        rows = self.db.execute(
            "SELECT * FROM skills WHERE learner=? AND language=? AND status='active' "
            "AND (lower(name) LIKE ? OR lower(definition) LIKE ? OR lower(skill_key) LIKE ?) "
            "ORDER BY name LIMIT ?",
            (learner, language, pattern, pattern, pattern, limit),
        ).fetchall()
        return [self._skill_dict(row) for row in rows]

    @staticmethod
    def _skill_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "language": row["language"],
            "key": row["skill_key"],
            "name": row["name"],
            "definition": row["definition"],
            "success_criteria": json.loads(row["success_criteria"]),
            "status": row["status"],
            "version": row["version"],
        }

    def skill(self, learner: str, skill_id: str, *, active: bool = False) -> dict:
        row = self._owned("skills", learner, skill_id)
        if active and row["status"] != "active":
            raise InvalidReference("Skill is no longer active")
        return self._skill_dict(row)

    def _create_skill(self, ctx: Any, language: str, spec: dict) -> str:
        previous = self.db.execute(
            "SELECT max(version) FROM skills WHERE learner=? AND language=? AND skill_key=?",
            (ctx.learner, language, spec["key"]),
        ).fetchone()[0]
        skill_id = identifier()
        self.db.execute(
            "INSERT INTO skills VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                skill_id,
                ctx.learner,
                language,
                spec["key"],
                spec["name"],
                spec["definition"],
                _json(spec["success_criteria"]),
                (previous or 0) + 1,
                now(),
            ),
        )
        self._event(ctx, "skill", skill_id)
        return skill_id

    def _validate_edges(self, learner: str, edges: Iterable[tuple[str, str]]) -> None:
        proposed = set(edges)
        existing = {
            (row[0], row[1])
            for row in self.db.execute(
                "SELECT prerequisite_id, dependent_id FROM skill_prerequisites WHERE learner=?",
                (learner,),
            )
        }
        graph: dict[str, set[str]] = {}
        for prerequisite, dependent in existing | proposed:
            if prerequisite == dependent:
                raise ValueError("A skill cannot be its own prerequisite")
            self.skill(learner, prerequisite, active=True)
            self.skill(learner, dependent, active=True)
            graph.setdefault(prerequisite, set()).add(dependent)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError(
                    "Skill prerequisites must form a directed acyclic graph"
                )
            if node in visited:
                return
            visiting.add(node)
            for child in graph.get(node, ()):
                visit(child)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)

    def _resolve_skills(
        self,
        ctx: Any,
        language: str,
        existing_ids: list[str],
        new_specs: list[dict],
        replacing_ids: set[str] | None = None,
    ) -> dict[str, str]:
        resolved: dict[str, str] = {}
        created_keys: set[str] = set()
        replacing_ids = replacing_ids or set()
        for skill_id in existing_ids:
            skill = self.skill(ctx.learner, skill_id, active=True)
            if skill["language"] != language:
                raise InvalidReference("Skill language does not match the topic")
            resolved[skill_id] = skill_id
            resolved[skill["key"]] = skill_id
        for spec in new_specs:
            if spec["key"] in resolved:
                raise ValueError("Duplicate skill reference")
            if spec["key"] in created_keys:
                raise ValueError("New skill keys must be unique within one operation")
            duplicate = self.db.execute(
                "SELECT id FROM skills WHERE learner=? AND language=? AND skill_key=? AND status='active'",
                (ctx.learner, language, spec["key"]),
            ).fetchone()
            if duplicate and duplicate["id"] not in replacing_ids:
                raise ValueError(
                    "An active skill with this key already exists; reuse its id"
                )
            skill_id = self._create_skill(ctx, language, spec)
            created_keys.add(spec["key"])
            resolved[spec["key"]] = skill_id
            resolved[skill_id] = skill_id
        return resolved

    @staticmethod
    def _resolve(ref: str, resolved: dict[str, str]) -> str:
        try:
            return resolved[ref]
        except KeyError as error:
            raise InvalidReference(f"Unknown skill reference: {ref}") from error

    def _set_focus(
        self,
        ctx: Any,
        topic_id: str,
        targets: list[str],
        supporting: list[str],
        reason: str,
    ) -> dict:
        self._owned("topics", ctx.learner, topic_id)
        if (
            not 1 <= len(targets) <= 3
            or len(supporting) > 5
            or len(set(targets + supporting)) != len(targets + supporting)
        ):
            raise ValueError(
                "A focus needs 1–3 unique targets and distinct support skills"
            )
        linked = {
            row[0]
            for row in self.db.execute(
                "SELECT skill_id FROM topic_skills WHERE topic_id=?", (topic_id,)
            )
        }
        if not set(targets + supporting) <= linked:
            raise InvalidReference("Every focus skill must be linked to its topic")
        for skill_id in targets + supporting:
            self.skill(ctx.learner, skill_id, active=True)
        self.db.execute("UPDATE focuses SET active=0 WHERE learner=?", (ctx.learner,))
        focus_id = identifier()
        self.db.execute(
            "INSERT INTO focuses VALUES (?, ?, ?, ?, 1, ?)",
            (focus_id, ctx.learner, topic_id, reason, now()),
        )
        self.db.executemany(
            "INSERT INTO focus_skills VALUES (?, ?, ?)",
            [(focus_id, skill_id, "target") for skill_id in targets]
            + [(focus_id, skill_id, "supporting") for skill_id in supporting],
        )
        self._event(ctx, "learning_focus", focus_id)
        return self.focus(ctx.learner) or {}

    def establish_topic(
        self,
        ctx: Any,
        topic: dict,
        existing_skill_ids: list[str],
        new_skills: list[dict],
        prerequisites: list[dict],
        links: list[dict],
        focus: dict,
    ) -> dict:
        resolved = self._resolve_skills(
            ctx, topic["language"], existing_skill_ids, new_skills
        )
        resolved_edges = [
            (
                self._resolve(edge["prerequisite"], resolved),
                self._resolve(edge["dependent"], resolved),
            )
            for edge in prerequisites
        ]
        self._validate_edges(ctx.learner, resolved_edges)
        topic_id = identifier()
        self.db.execute(
            "INSERT INTO topics VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (
                topic_id,
                ctx.learner,
                topic["language"],
                topic["name"],
                topic["purpose"],
                now(),
            ),
        )
        linked: set[str] = set()
        core = 0
        for link in links:
            skill_id = self._resolve(link["skill_ref"], resolved)
            if skill_id in linked:
                raise ValueError("A skill can be linked to a topic only once")
            linked.add(skill_id)
            core += link["role"] == "core"
            self.db.execute(
                "INSERT INTO topic_skills VALUES (?, ?, ?, ?, ?)",
                (topic_id, skill_id, link["role"], link["priority"], now()),
            )
        if not 3 <= core <= 8:
            raise ValueError("A new topic needs 3–8 core skills")
        supplied = set(existing_skill_ids) | {
            self._resolve(s["key"], resolved) for s in new_skills
        }
        if supplied != linked:
            raise ValueError("Every supplied skill must be linked to the topic")
        self.db.executemany(
            "INSERT OR IGNORE INTO skill_prerequisites VALUES (?, ?, ?, ?)",
            [(ctx.learner, a, b, now()) for a, b in resolved_edges],
        )
        self._event(ctx, "topic", topic_id)
        focus_result = self._set_focus(
            ctx,
            topic_id,
            [self._resolve(ref, resolved) for ref in focus["target_refs"]],
            [self._resolve(ref, resolved) for ref in focus["supporting_refs"]],
            focus["reason"],
        )
        return {
            "topic": self.topic(ctx.learner, topic_id),
            "focus": focus_result,
            "resolved_skill_ids": {
                key: value for key, value in resolved.items() if key != value
            },
        }

    def expand_topic(
        self,
        ctx: Any,
        topic_id: str,
        existing_skill_ids: list[str],
        new_skills: list[dict],
        prerequisites: list[dict],
        links: list[dict],
        rationale: str,
    ) -> dict:
        topic = self._owned("topics", ctx.learner, topic_id)
        resolved = self._resolve_skills(
            ctx, topic["language"], existing_skill_ids, new_skills
        )
        edges = [
            (
                self._resolve(e["prerequisite"], resolved),
                self._resolve(e["dependent"], resolved),
            )
            for e in prerequisites
        ]
        self._validate_edges(ctx.learner, edges)
        linked: set[str] = set()
        for link in links:
            skill_id = self._resolve(link["skill_ref"], resolved)
            if skill_id in linked:
                raise ValueError("A skill can be linked to a topic only once")
            linked.add(skill_id)
            if self.db.execute(
                "SELECT 1 FROM topic_skills WHERE topic_id=? AND skill_id=?",
                (topic_id, skill_id),
            ).fetchone():
                raise ValueError("This skill is already linked to the topic")
            self.db.execute(
                "INSERT INTO topic_skills VALUES (?, ?, ?, ?, ?)",
                (topic_id, skill_id, link["role"], link["priority"], now()),
            )
        new_ids = {self._resolve(skill["key"], resolved) for skill in new_skills}
        if not new_ids <= linked:
            raise ValueError("Every new expansion skill must be linked exactly once")
        already_linked = {
            row[0]
            for row in self.db.execute(
                "SELECT skill_id FROM topic_skills WHERE topic_id=?", (topic_id,)
            )
        }
        if not set(existing_skill_ids) <= already_linked | linked:
            raise ValueError(
                "Existing expansion skills must already belong to the topic or be newly linked"
            )
        self.db.executemany(
            "INSERT OR IGNORE INTO skill_prerequisites VALUES (?, ?, ?, ?)",
            [(ctx.learner, a, b, now()) for a, b in edges],
        )
        change_id = identifier()
        self.db.execute(
            "INSERT INTO skill_changes VALUES (?, ?, ?, ?)",
            (change_id, ctx.learner, rationale, now()),
        )
        self._event(ctx, "topic_expansion", change_id)
        return self.topic(ctx.learner, topic_id)

    def supersede_skills(
        self,
        ctx: Any,
        old_skill_ids: list[str],
        new_skills: list[dict],
        relations: list[dict],
        replacements: list[dict],
        reason: str,
    ) -> dict:
        old = {
            skill_id: self.skill(ctx.learner, skill_id, active=True)
            for skill_id in old_skill_ids
        }
        if not old or len({item["language"] for item in old.values()}) != 1:
            raise ValueError("Superseded skills must share one language")
        language = next(iter(old.values()))["language"]
        resolved = self._resolve_skills(
            ctx, language, [], new_skills, replacing_ids=set(old)
        )
        replacement_map: dict[str, list[str]] = {skill_id: [] for skill_id in old}
        for item in replacements:
            old_id = item["old_skill_id"]
            if old_id not in old:
                raise InvalidReference("Replacement references an unknown old skill")
            replacement_id = self._resolve(item["replacement_ref"], resolved)
            if replacement_id in replacement_map[old_id]:
                raise ValueError("Duplicate skill replacement")
            replacement_map[old_id].append(replacement_id)
        if any(not replacement_ids for replacement_ids in replacement_map.values()):
            raise ValueError(
                "Every superseded skill needs an explicit active replacement"
            )
        relation_rows = []
        for item in relations:
            old_id = item["old_skill_id"]
            if old_id not in old:
                raise InvalidReference("Supersession references an unknown old skill")
            relation_rows.append(
                (
                    old_id,
                    self._resolve(item["new_skill_ref"], resolved),
                    item["relation"],
                )
            )
        if {row[0] for row in relation_rows} != set(old):
            raise ValueError("Every old skill needs at least one supersession relation")
        relation_pairs = {(old_id, new_id) for old_id, new_id, _ in relation_rows}
        replacement_pairs = {
            (old_id, new_id)
            for old_id, new_ids in replacement_map.items()
            for new_id in new_ids
        }
        if not replacement_pairs <= relation_pairs:
            raise ValueError(
                "Every replacement needs an explicit supersession relation"
            )
        if set(resolved.values()) != {new_id for _, new_id in replacement_pairs}:
            raise ValueError(
                "Every new skill must explicitly replace at least one old skill"
            )
        change_id = identifier()
        self.db.execute(
            "INSERT INTO skill_changes VALUES (?, ?, ?, ?)",
            (change_id, ctx.learner, reason, now()),
        )
        self.db.executemany(
            "INSERT INTO skill_supersessions VALUES (?, ?, ?, ?)",
            [(change_id, a, b, relation) for a, b, relation in relation_rows],
        )
        for old_id, replacement_ids in replacement_map.items():
            for row in self.db.execute(
                "SELECT topic_id, role, priority FROM topic_skills WHERE skill_id=?",
                (old_id,),
            ).fetchall():
                self.db.execute(
                    "DELETE FROM topic_skills WHERE topic_id=? AND skill_id=?",
                    (row["topic_id"], old_id),
                )
                for position, replacement_id in enumerate(replacement_ids):
                    conflict = self.db.execute(
                        "SELECT role, priority FROM topic_skills WHERE topic_id=? AND skill_id=?",
                        (row["topic_id"], replacement_id),
                    ).fetchone()
                    if not conflict:
                        self.db.execute(
                            "INSERT INTO topic_skills VALUES (?, ?, ?, ?, ?)",
                            (
                                row["topic_id"],
                                replacement_id,
                                row["role"],
                                row["priority"] + position,
                                now(),
                            ),
                        )
                    else:
                        roles = {"core": 0, "extension": 1, "contextual": 2}
                        best_role = min(
                            (row["role"], conflict["role"]),
                            key=lambda role: roles.get(str(role), 99),
                        )
                        self.db.execute(
                            "UPDATE topic_skills SET role=?, priority=min(priority, ?) "
                            "WHERE topic_id=? AND skill_id=?",
                            (
                                best_role,
                                row["priority"],
                                row["topic_id"],
                                replacement_id,
                            ),
                        )
            for row in self.db.execute(
                "SELECT focus_id, role FROM focus_skills WHERE skill_id=?", (old_id,)
            ).fetchall():
                self.db.execute(
                    "DELETE FROM focus_skills WHERE focus_id=? AND skill_id=?",
                    (row["focus_id"], old_id),
                )
                for replacement_id in replacement_ids:
                    existing_focus = self.db.execute(
                        "SELECT role FROM focus_skills WHERE focus_id=? AND skill_id=?",
                        (row["focus_id"], replacement_id),
                    ).fetchone()
                    if not existing_focus:
                        self.db.execute(
                            "INSERT INTO focus_skills VALUES (?, ?, ?)",
                            (row["focus_id"], replacement_id, row["role"]),
                        )
                    elif (
                        row["role"] == "target"
                        and existing_focus["role"] == "supporting"
                    ):
                        self.db.execute(
                            "UPDATE focus_skills SET role='target' WHERE focus_id=? AND skill_id=?",
                            (row["focus_id"], replacement_id),
                        )
            self.db.execute(
                "UPDATE skills SET status='superseded' WHERE id=?", (old_id,)
            )
        affected_edges = self.db.execute(
            "SELECT prerequisite_id, dependent_id FROM skill_prerequisites WHERE learner=? "
            f"AND (prerequisite_id IN ({','.join('?' for _ in old)}) "
            f"OR dependent_id IN ({','.join('?' for _ in old)}))",
            (ctx.learner, *old, *old),
        ).fetchall()
        self.db.execute(
            "DELETE FROM skill_prerequisites WHERE learner=? "
            f"AND (prerequisite_id IN ({','.join('?' for _ in old)}) "
            f"OR dependent_id IN ({','.join('?' for _ in old)}))",
            (ctx.learner, *old, *old),
        )
        candidates: set[tuple[str, str]] = set()
        for edge in affected_edges:
            prerequisites = replacement_map.get(
                edge["prerequisite_id"], [edge["prerequisite_id"]]
            )
            dependents = replacement_map.get(
                edge["dependent_id"], [edge["dependent_id"]]
            )
            candidates.update(
                (prerequisite, dependent)
                for prerequisite in prerequisites
                for dependent in dependents
                if prerequisite != dependent
            )
        self._validate_edges(ctx.learner, candidates)
        self.db.executemany(
            "INSERT OR IGNORE INTO skill_prerequisites VALUES (?, ?, ?, ?)",
            [(ctx.learner, a, b, now()) for a, b in candidates],
        )
        self._event(ctx, "skill_supersession", change_id)
        return {
            "change_id": change_id,
            "replacements": replacement_map,
            "new_skills": [
                self.skill(ctx.learner, skill_id) for skill_id in set(resolved.values())
            ],
        }

    def topic(self, learner: str, topic_id: str) -> dict:
        topic = self._owned("topics", learner, topic_id)
        skills = []
        for row in self.db.execute(
            "SELECT s.*, ts.role, ts.priority FROM topic_skills ts JOIN skills s ON s.id=ts.skill_id "
            "WHERE ts.topic_id=? ORDER BY ts.priority, s.name",
            (topic_id,),
        ):
            item = self._skill_dict(row)
            item.update(role=row["role"], priority=row["priority"])
            skills.append(item)
        ids = {item["id"] for item in skills}
        edges = [
            {"prerequisite_id": row[0], "dependent_id": row[1]}
            for row in self.db.execute(
                "SELECT prerequisite_id, dependent_id FROM skill_prerequisites WHERE learner=?",
                (learner,),
            )
            if row[0] in ids and row[1] in ids
        ]
        return {
            "id": topic["id"],
            "language": topic["language"],
            "name": topic["name"],
            "purpose": topic["purpose"],
            "status": topic["status"],
            "skills": skills,
            "prerequisites": edges,
        }

    def topics(self, learner: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT id FROM topics WHERE learner=? AND status='active' ORDER BY created, rowid",
            (learner,),
        ).fetchall()
        return [self.topic(learner, row[0]) for row in rows]

    def focus(self, learner: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM focuses WHERE learner=? AND active=1", (learner,)
        ).fetchone()
        if row is None:
            return None
        skills = [
            {**self.skill(learner, skill["skill_id"]), "role": skill["role"]}
            for skill in self.db.execute(
                "SELECT skill_id, role FROM focus_skills WHERE focus_id=? "
                "ORDER BY CASE role WHEN 'target' THEN 0 ELSE 1 END",
                (row["id"],),
            )
        ]
        return {
            "id": row["id"],
            "topic_id": row["topic_id"],
            "reason": row["reason"],
            "skills": skills,
        }

    def set_focus(
        self,
        ctx: Any,
        topic_id: str,
        targets: list[str],
        supporting: list[str],
        reason: str,
    ) -> dict:
        return self._set_focus(ctx, topic_id, targets, supporting, reason)

    def _validate_sources(self, learner: str, source_ids: list[str]) -> None:
        for source_id in source_ids:
            if self._owned("sources", learner, source_id)["status"] != "available":
                raise InvalidReference("Only available sources can support an activity")

    def present_exercise(self, ctx: Any, exercise: dict) -> dict:
        focus = self.focus(ctx.learner)
        if focus is None:
            raise ValueError("Set a learning focus before presenting an exercise")
        topic = self.topic(ctx.learner, focus["topic_id"])
        linked = {item["id"] for item in topic["skills"] if item["status"] == "active"}
        target_focus = {
            item["id"] for item in focus["skills"] if item["role"] == "target"
        }
        requirements = exercise["skills"]
        ids = [item["skill_id"] for item in requirements]
        targets = [
            item["skill_id"] for item in requirements if item["role"] == "target"
        ]
        if len(ids) != len(set(ids)) or not 1 <= len(targets) <= 3:
            raise ValueError("Exercise skills must be unique with 1–3 targets")
        if not set(ids) <= linked or not set(targets) <= target_focus:
            raise InvalidReference(
                "Exercise targets must be focused; support skills must be topic-linked"
            )
        self._validate_sources(ctx.learner, exercise["source_ids"])
        exercise_id = identifier()
        self.db.execute(
            "INSERT INTO exercises (id, learner, topic_id, title, task, context, hint, scaffolding, created_turn, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                exercise_id,
                ctx.learner,
                focus["topic_id"],
                exercise["title"],
                exercise["task"],
                exercise["context"],
                exercise.get("hint"),
                exercise["scaffolding"],
                ctx.turn_id,
                now(),
            ),
        )
        self.db.executemany(
            "INSERT INTO exercise_skills VALUES (?, ?, ?, ?)",
            [
                (exercise_id, item["skill_id"], item["role"], item["success_criterion"])
                for item in requirements
            ],
        )
        self.db.executemany(
            "INSERT INTO exercise_sources VALUES (?, ?)",
            [(exercise_id, source_id) for source_id in exercise["source_ids"]],
        )
        self._event(ctx, "exercise", exercise_id)
        ctx.exercise_ids.append(exercise_id)
        return self.exercise(ctx.learner, exercise_id)

    def record_assistance(
        self, ctx: Any, exercise_id: str, skill_ids: list[str], level: str, content: str
    ) -> dict:
        exercise = self._owned("exercises", ctx.learner, exercise_id)
        if not self.db.execute(
            "SELECT 1 FROM turn_exercises WHERE exercise_id=?",
            (exercise_id,),
        ).fetchone():
            raise InvalidReference("The exercise was not presented in a committed turn")
        exercise_skills = {
            row[0]
            for row in self.db.execute(
                "SELECT skill_id FROM exercise_skills WHERE exercise_id=?",
                (exercise_id,),
            )
        }
        if not skill_ids or not set(skill_ids) <= exercise_skills:
            raise InvalidReference("Assistance skills must belong to the exercise")
        assistance_id = identifier()
        self.db.execute(
            "INSERT INTO assistance VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                assistance_id,
                ctx.learner,
                exercise["id"],
                level,
                content,
                ctx.turn_id,
                now(),
            ),
        )
        self.db.executemany(
            "INSERT INTO assistance_skills VALUES (?, ?)",
            [(assistance_id, skill_id) for skill_id in skill_ids],
        )
        self._event(ctx, "assistance", assistance_id)
        return {
            "id": assistance_id,
            "exercise_id": exercise_id,
            "skill_ids": skill_ids,
            "level": level,
            "content": content,
        }

    def assess_attempt(
        self, ctx: Any, exercise_id: str, feedback: str, observations: list[dict]
    ) -> dict:
        exercise = self._owned("exercises", ctx.learner, exercise_id)
        if exercise["created_turn"] == ctx.turn_id:
            raise ValueError(
                "Cannot assess an exercise before the learner can attempt it"
            )
        if not self.db.execute(
            "SELECT 1 FROM turn_exercises WHERE exercise_id=?",
            (exercise_id,),
        ).fetchone():
            raise InvalidReference("The exercise was not presented in a committed turn")
        allowed = {
            row[0]
            for row in self.db.execute(
                "SELECT skill_id FROM exercise_skills WHERE exercise_id=?",
                (exercise_id,),
            )
        }
        observed = [item["skill_id"] for item in observations]
        if (
            not observed
            or len(observed) != len(set(observed))
            or not set(observed) <= allowed
        ):
            raise InvalidReference(
                "Observations must uniquely reference exercise skills"
            )
        attempt_id, created = identifier(), now()
        self.db.execute(
            "INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                attempt_id,
                ctx.learner,
                exercise_id,
                ctx.turn_id,
                ctx.message,
                feedback,
                created,
            ),
        )
        saved = []
        for observation in observations:
            skill_id = observation["skill_id"]
            assisted = self.db.execute(
                "SELECT 1 FROM assistance a JOIN assistance_skills s ON s.assistance_id=a.id "
                "WHERE a.exercise_id=? AND s.skill_id=? LIMIT 1",
                (exercise_id, skill_id),
            ).fetchone()
            independent = (
                observation["outcome"] == "success"
                and exercise["scaffolding"] == "none"
                and assisted is None
            )
            observation_id = identifier()
            self.db.execute(
                "INSERT INTO skill_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    observation_id,
                    ctx.learner,
                    attempt_id,
                    exercise_id,
                    skill_id,
                    observation["outcome"],
                    observation["rationale"],
                    int(independent),
                    created,
                ),
            )
            saved.append(
                {
                    **observation,
                    "id": observation_id,
                    "independent_success": independent,
                }
            )
        self._event(ctx, "attempt", attempt_id)
        return {
            "id": attempt_id,
            "exercise_id": exercise_id,
            "learner_response": ctx.message,
            "feedback": feedback,
            "observations": saved,
        }

    def exercise(self, learner: str, exercise_id: str) -> dict:
        row = self._owned("exercises", learner, exercise_id)
        skills = []
        for item in self.db.execute(
            "SELECT skill_id, role, success_criterion FROM exercise_skills WHERE exercise_id=? "
            "ORDER BY CASE role WHEN 'target' THEN 0 ELSE 1 END",
            (exercise_id,),
        ):
            skill = self.skill(learner, item["skill_id"])
            skills.append(
                {
                    "id": skill["id"],
                    "name": skill["name"],
                    "role": item["role"],
                    "success_criterion": item["success_criterion"],
                }
            )
        sources = [
            item[0]
            for item in self.db.execute(
                "SELECT source_id FROM exercise_sources WHERE exercise_id=?",
                (exercise_id,),
            )
        ]
        return {
            "id": exercise_id,
            "kind": "exercise",
            "title": row["title"],
            "task": row["task"],
            "context": row["context"],
            "scaffolding": row["scaffolding"],
            "skills": skills,
            "source_ids": sources,
        }

    def exercise_hint(self, learner: str, session: str, exercise_id: str) -> dict:
        status = self.exercise_status(learner, session, exercise_id)
        if status["completed"]:
            raise ValueError("This exercise is already complete")
        scope = self.learning_scope(learner, session)
        row = self._owned("exercises", scope, exercise_id)
        hint = row["hint"]
        if not hint:
            return {"hint": None, "status": status}
        if not self.db.execute(
            "SELECT 1 FROM assistance WHERE exercise_id=? AND level='hint' AND content=? LIMIT 1",
            (exercise_id, hint),
        ).fetchone():
            assistance_id = identifier()
            self.db.execute(
                "INSERT INTO assistance VALUES (?, ?, ?, ?, ?, ?, ?)",
                (assistance_id, scope, exercise_id, "hint", hint, identifier(), now()),
            )
            self.db.executemany(
                "INSERT INTO assistance_skills VALUES (?, ?)",
                [
                    (assistance_id, skill["id"])
                    for skill in self.exercise(scope, exercise_id)["skills"]
                ],
            )
            self.db.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier(),
                    scope,
                    session,
                    identifier(),
                    assistance_id,
                    "assistance",
                    now(),
                    "application-hint",
                ),
            )
        return {
            "hint": hint,
            "status": self.exercise_status(learner, session, exercise_id),
        }

    def exercise_status(self, learner: str, session: str, exercise_id: str) -> dict:
        self.authorize(learner, session)
        scope = self.learning_scope(learner, session)
        exercise = self.exercise(scope, exercise_id)
        target_ids = {
            skill["id"] for skill in exercise["skills"] if skill["role"] == "target"
        }
        if not self.db.execute(
            "SELECT 1 FROM turn_exercises p JOIN turns t ON t.id=p.turn_id "
            "WHERE p.exercise_id=? AND t.session=?",
            (exercise_id, session),
        ).fetchone():
            raise InvalidReference("Exercise is unavailable in this session")
        rows = self.db.execute(
            "SELECT a.id, a.learner_response, a.feedback FROM attempts a "
            "JOIN turns t ON t.id=a.turn_id WHERE a.exercise_id=? AND t.session=? "
            "ORDER BY a.rowid",
            (exercise_id, session),
        ).fetchall()
        assessments = []
        for row in rows:
            assessments.append(
                {
                    "id": row["id"],
                    "learner_response": row["learner_response"],
                    "feedback": row["feedback"],
                    "observations": [
                        dict(item)
                        for item in self.db.execute(
                            "SELECT skill_id, outcome, rationale, independent_success "
                            "FROM skill_observations WHERE attempt_id=?",
                            (row["id"],),
                        )
                    ],
                }
            )
        assessment = assessments[-1] if assessments else None
        assisted = (
            self.db.execute(
                "SELECT 1 FROM assistance WHERE exercise_id=? LIMIT 1", (exercise_id,)
            ).fetchone()
            is not None
        )
        return {
            "latest_assessment": assessment,
            "assessments": assessments,
            "assisted": assisted,
            "completed": bool(
                assessment
                and target_ids
                <= {
                    item["skill_id"]
                    for item in assessment["observations"]
                    if item["outcome"] == "success"
                }
                and all(
                    item["outcome"] == "success" for item in assessment["observations"]
                )
            ),
        }

    def exercise_statuses(self, learner: str, session: str) -> dict:
        self.authorize(learner, session)
        ids = self.db.execute(
            "SELECT p.exercise_id FROM turn_exercises p JOIN turns t ON t.id=p.turn_id "
            "WHERE t.session=?",
            (session,),
        )
        return {row[0]: self.exercise_status(learner, session, row[0]) for row in ids}

    def review_exercise(self, learner: str, session: str, exercise_id: str) -> dict:
        self.exercise_status(learner, session, exercise_id)
        scope = self.learning_scope(learner, session)
        existing = self.db.execute(
            "SELECT 1 FROM assistance WHERE exercise_id=? AND level='explanation' "
            "AND content='Reviewed explanation in conversation' LIMIT 1",
            (exercise_id,),
        ).fetchone()
        if not existing:
            assistance_id = identifier()
            self.db.execute(
                "INSERT INTO assistance VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    assistance_id,
                    scope,
                    exercise_id,
                    "explanation",
                    "Reviewed explanation in conversation",
                    identifier(),
                    now(),
                ),
            )
            self.db.executemany(
                "INSERT INTO assistance_skills VALUES (?, ?)",
                [
                    (assistance_id, skill["id"])
                    for skill in self.exercise(scope, exercise_id)["skills"]
                ],
            )
            self.db.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier(),
                    scope,
                    session,
                    identifier(),
                    assistance_id,
                    "assistance",
                    now(),
                    "application-review",
                ),
            )
        return self.exercise_status(learner, session, exercise_id)

    def _turn_activities(self, learner: str, turn_id: str) -> list[dict]:
        return [
            self.exercise(learner, row["exercise_id"])
            for row in self.db.execute(
                "SELECT exercise_id FROM turn_exercises WHERE turn_id=? ORDER BY position",
                (turn_id,),
            )
        ]

    def save_turn(self, ctx: Any, reply: str, items: list) -> None:
        self.db.execute(
            "INSERT INTO turns VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ctx.turn_id,
                ctx.session,
                ctx.learner,
                now(),
                ctx.message,
                reply,
                _json(items),
                ctx.prompt_version,
            ),
        )
        for position, exercise_id in enumerate(ctx.exercise_ids):
            row = self._owned("exercises", ctx.learner, exercise_id)
            if row["created_turn"] != ctx.turn_id:
                raise InvalidReference(
                    "Only exercises created in this turn can be presented"
                )
            self.db.execute(
                "INSERT INTO turn_exercises VALUES (?, ?, ?)",
                (ctx.turn_id, position, exercise_id),
            )

    def conversation(
        self, learner: str, session: str, limit: int | None = 50
    ) -> list[dict]:
        self.authorize(learner, session)
        query = "SELECT id, learner, created, message, reply FROM turns WHERE session=? ORDER BY rowid DESC"
        parameters: tuple = (session,)
        if limit is not None:
            query += " LIMIT ?"
            parameters = (session, limit)
        rows = self.db.execute(query, parameters).fetchall()
        messages = []
        for row in reversed(rows):
            messages.extend(
                (
                    {
                        "role": "user",
                        "turn_id": row["id"],
                        "content": row["message"],
                        "created": row["created"],
                    },
                    {
                        "role": "assistant",
                        "turn_id": row["id"],
                        "content": row["reply"],
                        "activities": self._turn_activities(row["learner"], row["id"]),
                        "created": row["created"],
                    },
                )
            )
        return messages

    def topic_anchors(self, learner: str, session: str) -> dict[str, str]:
        """Browser navigation links, derived only from committed session turns."""
        self.authorize(learner, session)
        scope = self.learning_scope(learner, session)
        rows = self.db.execute(
            "SELECT e.entity_id, e.turn_id FROM events e "
            "JOIN turns t ON t.id=e.turn_id AND t.session=e.session "
            "JOIN topics p ON p.id=e.entity_id AND p.learner=e.learner "
            "WHERE e.learner=? AND e.session=? AND e.kind='topic' "
            "ORDER BY t.rowid, e.rowid",
            (scope, session),
        )
        anchors: dict[str, str] = {}
        for row in rows:
            anchors.setdefault(row["entity_id"], row["turn_id"])
        return anchors

    def model_history(
        self, learner: str, session: str, max_turns: int = 6, max_chars: int = 20_000
    ) -> list[dict]:
        self.authorize(learner, session)
        rows = self.db.execute(
            "SELECT id, learner, message, reply FROM turns WHERE session=? ORDER BY rowid DESC LIMIT ?",
            (session, max_turns),
        ).fetchall()
        selected: list[tuple[sqlite3.Row, str]] = []
        size = 0
        for row in rows:
            activities = self._turn_activities(row["learner"], row["id"])
            assistant = row["reply"]
            if activities:
                assistant += "\n\nPresented activities:\n" + _json(activities)
            turn_size = len(row["message"]) + len(assistant)
            if selected and size + turn_size > max_chars:
                break
            if turn_size > max_chars:
                assistant = assistant[: max(0, max_chars - len(row["message"]))]
                turn_size = len(row["message"]) + len(assistant)
            selected.append((row, assistant))
            size += turn_size
        history = []
        for row, assistant in reversed(selected):
            history.extend(
                [
                    {"role": "user", "content": row["message"]},
                    {"role": "assistant", "content": assistant},
                ]
            )
        return history

    def observations(
        self, learner: str, skill_ids: list[str], limit: int = 5
    ) -> list[dict]:
        if not skill_ids:
            return []
        marks = ",".join("?" for _ in skill_ids)
        rows = self.db.execute(
            f"SELECT o.*, e.title AS exercise_title, t.name AS topic_name "
            f"FROM skill_observations o JOIN exercises e ON e.id=o.exercise_id "
            f"JOIN topics t ON t.id=e.topic_id WHERE o.learner=? AND o.skill_id IN ({marks}) "
            "ORDER BY o.rowid DESC LIMIT ?",
            (learner, *skill_ids, limit),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "skill_id": row["skill_id"],
                "outcome": row["outcome"],
                "independent_success": bool(row["independent_success"]),
                "rationale": row["rationale"],
                "exercise": row["exercise_title"],
                "topic": row["topic_name"],
                "created": row["created"],
            }
            for row in rows
        ]

    def progress(self, learner: str, skill_ids: list[str] | None = None) -> list[dict]:
        params: list[Any] = [learner]
        where = "s.learner=?"
        if skill_ids is not None:
            if not skill_ids:
                return []
            where += f" AND s.id IN ({','.join('?' for _ in skill_ids)})"
            params.extend(skill_ids)
        rows = self.db.execute(
            "SELECT s.id, s.name, s.status, count(o.id) AS observations, "
            "coalesce(sum(o.outcome='success'), 0) AS successes, "
            "coalesce(sum(o.outcome='needs_work'), 0) AS needs_work, "
            "coalesce(sum(o.outcome='uncertain'), 0) AS uncertain, "
            "coalesce(sum(o.independent_success), 0) AS independent_successes, max(o.created) AS last_observed "
            "FROM skills s LEFT JOIN skill_observations o ON o.skill_id=s.id "
            f"WHERE {where} GROUP BY s.id ORDER BY s.name",
            params,
        ).fetchall()
        result = []
        for row in rows:
            contexts = [
                item[0]
                for item in self.db.execute(
                    "SELECT DISTINCT t.name FROM skill_observations o JOIN exercises e ON e.id=o.exercise_id "
                    "JOIN topics t ON t.id=e.topic_id WHERE o.skill_id=? ORDER BY o.created DESC LIMIT 5",
                    (row["id"],),
                )
            ]
            assisted = self.db.execute(
                "SELECT count(DISTINCT a.id) FROM assistance a JOIN assistance_skills x "
                "ON x.assistance_id=a.id WHERE x.skill_id=?",
                (row["id"],),
            ).fetchone()[0]
            result.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "status": row["status"],
                    "observations": row["observations"],
                    "successes": row["successes"],
                    "needs_work": row["needs_work"],
                    "uncertain": row["uncertain"],
                    "independent_successes": row["independent_successes"],
                    "assistance_events": assisted,
                    "last_observed": row["last_observed"],
                    "contexts": contexts,
                }
            )
        return result

    def active_exercise(self, learner: str) -> dict | None:
        row = self.db.execute(
            "SELECT e.id FROM exercises e JOIN turn_exercises p "
            "ON p.exercise_id=e.id "
            "WHERE e.learner=? ORDER BY e.rowid DESC LIMIT 1",
            (learner,),
        ).fetchone()
        return self.exercise(learner, row[0]) if row else None

    def prompt_state(self, learner: str, max_chars: int = 16_000) -> dict:
        focus = self.focus(learner)
        topics = self.topics(learner)
        active_topic = None
        if focus:
            active_topic = next(
                (topic for topic in topics if topic["id"] == focus["topic_id"]), None
            )
        summaries = [
            {
                "id": topic["id"],
                "name": topic["name"],
                "purpose": topic["purpose"],
                "language": topic["language"],
                "skill_count": len(topic["skills"]),
            }
            for topic in topics
            if active_topic is None or topic["id"] != active_topic["id"]
        ]
        focus_ids = [item["id"] for item in (focus or {}).get("skills", [])]
        source_metadata = [
            {
                "id": row["id"],
                "title": row["title"],
                "url": row["url"],
                "status": row["status"],
            }
            for row in self.db.execute(
                "SELECT id, title, url, status FROM sources WHERE learner=? ORDER BY rowid DESC LIMIT 5",
                (learner,),
            )
        ]
        state: dict[str, Any] = {
            "profile": {
                field: fact["value"] for field, fact in self.profile(learner).items()
            },
            "other_topics": summaries,
            "active_topic": active_topic,
            "focus": focus,
            "active_exercise": self.active_exercise(learner),
            "focus_progress": self.progress(learner, focus_ids),
            "recent_focus_observations": self.observations(learner, focus_ids, 5),
            "sources": source_metadata,
        }
        for key in ("other_topics", "recent_focus_observations", "sources"):
            while len(_json(state)) > max_chars and state[key]:
                state[key].pop(0)
        if len(_json(state)) > max_chars and state["active_topic"]:
            state["active_topic"]["skills"] = [
                skill
                for skill in state["active_topic"]["skills"]
                if skill["role"] == "core"
            ]
            ids = {skill["id"] for skill in state["active_topic"]["skills"]}
            state["active_topic"]["prerequisites"] = [
                edge
                for edge in state["active_topic"]["prerequisites"]
                if edge["prerequisite_id"] in ids and edge["dependent_id"] in ids
            ]
        if len(_json(state)) > max_chars:
            state["focus_progress"] = state["focus_progress"][:3]
        if len(_json(state)) > max_chars:
            topic = state["active_topic"]
            if topic:
                state["active_topic"] = {
                    "id": topic["id"],
                    "language": topic["language"],
                    "name": topic["name"],
                    "purpose": topic["purpose"][:400],
                    "skills": [
                        {
                            "id": skill["id"],
                            "key": skill["key"],
                            "name": skill["name"],
                            "definition": skill["definition"][:300],
                            "success_criteria": [
                                criterion[:200]
                                for criterion in skill["success_criteria"][:2]
                            ],
                            "role": skill["role"],
                            "priority": skill["priority"],
                        }
                        for skill in topic["skills"]
                    ],
                    "prerequisites": topic["prerequisites"],
                }
            focus_state = state["focus"]
            if focus_state:
                state["focus"] = {
                    "id": focus_state["id"],
                    "topic_id": focus_state["topic_id"],
                    "reason": focus_state["reason"][:300],
                    "skills": [
                        {
                            "id": skill["id"],
                            "name": skill["name"],
                            "role": skill["role"],
                        }
                        for skill in focus_state["skills"]
                    ],
                }
            exercise = state["active_exercise"]
            if exercise:
                state["active_exercise"] = {
                    "id": exercise["id"],
                    "title": exercise["title"],
                    "task": exercise["task"][:1600],
                    "context": exercise["context"][:500],
                    "scaffolding": exercise["scaffolding"],
                    "skills": [
                        {
                            "id": skill["id"],
                            "name": skill["name"],
                            "role": skill["role"],
                            "success_criterion": skill["success_criterion"][:200],
                        }
                        for skill in exercise["skills"]
                    ],
                }
            state["profile"] = {
                key: value[:300] for key, value in state["profile"].items()
            }
            state["truncated"] = True
        if len(_json(state)) > max_chars:
            state["other_topics"] = []
            state["recent_focus_observations"] = []
            state["sources"] = []
            state["focus_progress"] = state["focus_progress"][:3]
            for skill in (state.get("active_topic") or {}).get("skills", []):
                skill["definition"] = skill["definition"][:120]
                skill["success_criteria"] = [
                    item[:120] for item in skill["success_criteria"][:1]
                ]
            if state["active_exercise"]:
                state["active_exercise"]["task"] = state["active_exercise"]["task"][
                    :800
                ]
                state["active_exercise"]["context"] = state["active_exercise"][
                    "context"
                ][:250]
            state["profile"] = {
                key: value[:150] for key, value in state["profile"].items()
            }
        return state

    def learning_view(self, learner: str) -> dict:
        topics = self.topics(learner)
        skills = {
            row["id"]: self._skill_dict(row)
            for row in self.db.execute(
                "SELECT * FROM skills WHERE learner=? ORDER BY name", (learner,)
            )
        }
        progress = {item["id"]: item for item in self.progress(learner)}
        return {
            "profile": self.profile(learner),
            "topics": topics,
            "focus": self.focus(learner),
            "skills": [
                {**skill, "progress": progress.get(skill_id, {})}
                for skill_id, skill in sorted(
                    skills.items(), key=lambda item: item[1]["name"]
                )
            ],
        }

    def snapshot(self, learner: str) -> dict:
        all_skill_ids = [
            row[0]
            for row in self.db.execute(
                "SELECT id FROM skills WHERE learner=?", (learner,)
            )
        ]
        return {
            **self.learning_view(learner),
            "active_exercise": self.active_exercise(learner),
            "recent_observations": self.observations(learner, all_skill_ids, 20),
            "sources": [
                dict(row)
                for row in self.db.execute(
                    "SELECT id, status, title, url, provenance, reason, retrieved_at, "
                    "sha256, truncated, created FROM sources "
                    "WHERE learner=? ORDER BY rowid DESC LIMIT 20",
                    (learner,),
                )
            ],
        }

    def inspect(self, learner: str) -> dict:
        return {
            "learning_sessions": [
                {
                    **session,
                    "state": self.snapshot(self.learning_scope(learner, session["id"])),
                }
                for session in self.sessions(learner)
            ],
            "schema_version": SCHEMA_VERSION,
            "state": self.snapshot(learner),
            "events": [
                dict(row)
                for row in self.db.execute(
                    "SELECT * FROM events WHERE learner=? ORDER BY rowid", (learner,)
                )
            ],
            "sessions": [
                dict(row)
                for row in self.db.execute(
                    "SELECT * FROM sessions WHERE learner=? ORDER BY rowid", (learner,)
                )
            ],
        }

    def close(self) -> None:
        self.db.close()
