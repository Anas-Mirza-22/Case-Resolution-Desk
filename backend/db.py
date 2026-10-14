"""SQLite persistence. Parameterized SQL only."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from . import constants as C

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    assessed_on TEXT NOT NULL,
    learner_name TEXT NOT NULL,
    question TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    outcome_json TEXT NOT NULL,
    eligibility TEXT NOT NULL,
    status TEXT NOT NULL,
    next_action TEXT NOT NULL,
    other_actions_json TEXT NOT NULL,
    missing_facts_json TEXT NOT NULL,
    answer TEXT,
    citations_json TEXT NOT NULL,
    case_note TEXT NOT NULL,
    llm_error TEXT
);
"""


class Database:
    """Thin wrapper around sqlite3 with parameterized queries."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def insert_case(
        self,
        *,
        assessed_on: str,
        learner_name: str,
        question: str,
        inputs: dict[str, Any],
        outcome: dict[str, Any],
        eligibility: str,
        status: str,
        next_action: str,
        other_actions: list[str],
        missing_facts: list[str],
        answer: str | None,
        citations: list[dict[str, Any]],
        case_note: str,
        llm_error: str | None,
    ) -> int:
        created_at = datetime.utcnow().isoformat(timespec="seconds")
        cur = self._conn.execute(
            """
            INSERT INTO cases (
                created_at, assessed_on, learner_name, question, inputs_json,
                outcome_json, eligibility, status, next_action, other_actions_json,
                missing_facts_json, answer, citations_json, case_note, llm_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                assessed_on,
                learner_name,
                question,
                json.dumps(inputs),
                json.dumps(outcome),
                eligibility,
                status,
                next_action,
                json.dumps(other_actions),
                json.dumps(missing_facts),
                answer,
                json.dumps(citations),
                case_note,
                llm_error,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_cases(self) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            """
            SELECT id, learner_name, eligibility, status, created_at
            FROM cases ORDER BY id DESC
            """
        )
        return [dict(row) for row in cur.fetchall()]
    
    def delete_case(self, case_id: int) -> bool:
        """Delete a case. Returns True if a row was removed, False otherwise."""
        cur = self._conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))
        self._conn.commit()
        return cur.rowcount > 0
    
    def get_case(self, case_id: int) -> dict[str, Any] | None:
        cur = self._conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
        row = cur.fetchone()
        if row is None:
            return None
        data = dict(row)
        for key, target in (
            ("inputs_json", "inputs"),
            ("outcome_json", "outcome"),
            ("other_actions_json", "other_actions"),
            ("missing_facts_json", "missing_facts"),
            ("citations_json", "citations"),
        ):
            data[target] = json.loads(data.pop(key))
        return data


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")