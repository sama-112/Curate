import sqlite3
import time
from pathlib import Path

from curate.domain import IncomingMessage, StylistReply


class Inbox:
    """A local durable transport journal, not the future user/wardrobe database.

    One application process owns one worker. Replies are cached before sending so an
    ambiguous network failure can retry the exact body with the same idempotency key.
    """

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path, timeout=1)
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS inbox (
                event_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                reply TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0,
                last_error TEXT,
                sent_message_id TEXT,
                UNIQUE (agent_id, message_id)
            );
        """)

    def accept(self, message: IncomingMessage) -> bool:
        with self.db:
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO inbox(event_id,agent_id,message_id,payload) VALUES(?,?,?,?)",
                (message.event_id, message.agent_id, message.message_id, message.model_dump_json()),
            )
        return cursor.rowcount == 1

    def next_due(self) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM inbox WHERE status='pending' AND next_attempt<=? ORDER BY rowid LIMIT 1",
            (time.time(),),
        ).fetchone()

    def save_reply(self, event_id: str, reply: StylistReply) -> None:
        with self.db:
            self.db.execute(
                "UPDATE inbox SET reply=? WHERE event_id=?", (reply.model_dump_json(), event_id)
            )

    def delivered(self, event_id: str, message_id: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE inbox SET status='delivered',sent_message_id=? WHERE event_id=?",
                (message_id, event_id),
            )

    def failed_attempt(self, event_id: str, attempts: int, error: str, *, terminal: bool) -> None:
        with self.db:
            self.db.execute(
                "UPDATE inbox SET attempts=?,last_error=?,status=?,next_attempt=? WHERE event_id=?",
                (
                    attempts,
                    error,
                    "failed" if terminal else "pending",
                    time.time() + min(2**attempts, 30),
                    event_id,
                ),
            )

    def counts(self) -> dict[str, int]:
        return {
            row["status"]: row["count"]
            for row in self.db.execute("SELECT status,COUNT(*) AS count FROM inbox GROUP BY status")
        }

    def close(self) -> None:
        self.db.close()
