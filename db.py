import json
import aiosqlite
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "ailearner.db"

_conn: Optional[aiosqlite.Connection] = None


async def _get_conn() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        _conn = await aiosqlite.connect(str(DB_PATH))
        _conn.row_factory = aiosqlite.Row
        await _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


async def init_db():
    conn = await _get_conn()
    await conn.executescript("""
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
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );
    """)
    await conn.commit()


async def get_session(session_id: str) -> Optional[dict]:
    conn = await _get_conn()
    cursor = await conn.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    data = dict(row)
    data["evaluation_answers"] = json.loads(data.get("evaluation_answers", "{}"))
    data["evaluation_started"] = bool(data["evaluation_started"])
    data["evaluation_done"] = bool(data["evaluation_done"])
    cursor = await conn.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
        (session_id,)
    )
    msgs = await cursor.fetchall()
    data["messages"] = [{"role": m["role"], "content": m["content"]} for m in msgs]
    return data


async def create_session(session_id: str):
    conn = await _get_conn()
    await conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
        (session_id,)
    )
    await conn.commit()


async def save_message(session_id: str, role: str, content: Optional[str]):
    conn = await _get_conn()
    await conn.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content)
    )
    await conn.execute(
        "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
        (session_id,)
    )
    await conn.commit()


_ALLOWED_COLS = {
    "evaluation_started", "evaluation_done", "evaluation_phase",
    "evaluation_report", "evaluation_path", "evaluation_answers",
}


async def update_session(session_id: str, **kwargs):
    conn = await _get_conn()
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
    await conn.execute(
        f"UPDATE sessions SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP "
        f"WHERE session_id = ?",
        values
    )
    await conn.commit()


async def delete_session(session_id: str):
    conn = await _get_conn()
    await conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    await conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    await conn.commit()


async def get_or_create_session(session_id: str):
    """Load session state from DB or create a new one. Returns a SessionState."""
    from agent.schemas import SessionState, Message

    data = await get_session(session_id)
    if data:
        state = SessionState(session_id=session_id)
        state.messages = [Message(**m) for m in data["messages"]]
        state.evaluation_answers = data["evaluation_answers"]
        state.evaluation_phase = data["evaluation_phase"]
        state.evaluation_started = data["evaluation_started"]
        state.evaluation_done = data["evaluation_done"]
        state.evaluation_report = data["evaluation_report"]
        state.evaluation_path = data["evaluation_path"]
        return state
    await create_session(session_id)
    return SessionState(session_id=session_id)


async def close_db():
    global _conn
    if _conn is not None:
        await _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        await _conn.close()
        _conn = None
