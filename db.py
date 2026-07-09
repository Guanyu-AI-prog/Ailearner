import json
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "ailearner.db"


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            evaluation_started INTEGER DEFAULT 0,
            evaluation_done INTEGER DEFAULT 0,
            evaluation_phase INTEGER DEFAULT 0,
            evaluation_report TEXT DEFAULT '',
            evaluation_path TEXT DEFAULT '',
            evaluation_answers TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );
    """)
    conn.commit()
    conn.close()


def get_session(session_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    data = dict(row)
    data["evaluation_answers"] = json.loads(data.get("evaluation_answers", "{}"))
    data["evaluation_started"] = bool(data["evaluation_started"])
    data["evaluation_done"] = bool(data["evaluation_done"])
    msgs = conn.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
        (session_id,)
    ).fetchall()
    data["messages"] = [{"role": m["role"], "content": m["content"]} for m in msgs]
    conn.close()
    return data


def create_session(session_id: str):
    conn = _get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
        (session_id,)
    )
    conn.commit()
    conn.close()


def save_message(session_id: str, role: str, content: str):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content)
    )
    conn.execute(
        "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
        (session_id,)
    )
    conn.commit()
    conn.close()


_ALLOWED_COLS = {
    "evaluation_started", "evaluation_done", "evaluation_phase",
    "evaluation_report", "evaluation_path", "evaluation_answers",
}


def update_session(session_id: str, **kwargs):
    conn = _get_conn()
    fields = []
    values = []
    for key, val in kwargs.items():
        if key not in _ALLOWED_COLS:
            raise ValueError(f"非法列名: {key}")
        if key == "evaluation_answers":
            val = json.dumps(val, ensure_ascii=False)
        elif isinstance(val, bool):
            val = int(val)
        fields.append(f"{key} = ?")
        values.append(val)
    values.append(session_id)
    conn.execute(
        f"UPDATE sessions SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP "
        f"WHERE session_id = ?",
        values
    )
    conn.commit()
    conn.close()


def delete_session(session_id: str):
    conn = _get_conn()
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def close_db():
    conn = _get_conn()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
