"""Memoria locale di AGIS: conversazioni e feedback, in SQLite.

I feedback sono il motore dell'auto-miglioramento: ogni volta che l'utente
corregge AGIS, la correzione viene salvata, esportata in
workspace/memoria/feedback.md (che CLAUDE.md importa) e riletta a ogni risposta.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session TEXT,
    role TEXT NOT NULL,          -- 'user' | 'agis'
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    message_id INTEGER,
    rating INTEGER NOT NULL,     -- +1 utile, -1 da correggere
    note TEXT
);
"""


class Memory:
    def __init__(self, db_path: Path, feedback_md: Path):
        self.db_path = db_path
        self.feedback_md = feedback_md
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        cols = {r[1] for r in self._db.execute("PRAGMA table_info(feedback)")}
        if "synced" not in cols:  # database creato dalla v0.1
            self._db.execute("ALTER TABLE feedback ADD COLUMN synced INTEGER NOT NULL DEFAULT 0")
            self._db.commit()
        self.export_feedback()

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def add_message(self, role: str, text: str, session: str | None = None) -> int:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO messages (ts, session, role, text) VALUES (?, ?, ?, ?)",
                (self._now(), session, role, text),
            )
            self._db.commit()
            return cur.lastrowid

    def add_feedback(self, message_id: int | None, rating: int, note: str = "") -> int:
        if rating not in (1, -1):
            raise ValueError("rating deve essere +1 o -1")
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO feedback (ts, message_id, rating, note) VALUES (?, ?, ?, ?)",
                (self._now(), message_id, rating, note.strip()),
            )
            self._db.commit()
        self.export_feedback()
        return cur.lastrowid

    def unsynced_feedback(self) -> list[tuple]:
        """Feedback non ancora caricati su Notion: (id, ts, rating, note, testo risposta)."""
        with self._lock:
            return self._db.execute(
                """SELECT f.id, f.ts, f.rating, f.note, m.text
                   FROM feedback f LEFT JOIN messages m ON m.id = f.message_id
                   WHERE f.synced = 0 ORDER BY f.id""").fetchall()

    def mark_synced(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            self._db.executemany("UPDATE feedback SET synced = 1 WHERE id = ?",
                                 [(i,) for i in ids])
            self._db.commit()

    def recent_feedback(self, limit: int = 30) -> list[tuple]:
        with self._lock:
            return self._db.execute(
                """SELECT f.ts, f.rating, f.note, m.text
                   FROM feedback f LEFT JOIN messages m ON m.id = f.message_id
                   ORDER BY f.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()

    def export_feedback(self) -> None:
        """Scrive i feedback in un file Markdown letto da Claude Code via CLAUDE.md."""
        rows = self.recent_feedback()
        lines = [
            "# Feedback di Loffre",
            "",
            "Correzioni e apprezzamenti più recenti. Applicali sempre: hanno priorità",
            "sulle tue abitudini. Se due feedback si contraddicono, vale il più recente.",
            "",
        ]
        if not rows:
            lines.append("_Nessun feedback ancora._")
        for ts, rating, note, msg in rows:
            segno = "👍" if rating > 0 else "👎"
            ref = (msg or "").replace("\n", " ")[:120]
            riga = f"- {ts[:10]} {segno} {note or '(nessuna nota)'}"
            if ref:
                riga += f" — sulla risposta: \"{ref}…\""
            lines.append(riga)
        self.feedback_md.parent.mkdir(parents=True, exist_ok=True)
        self.feedback_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
