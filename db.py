import asyncio
import json
import aiosqlite
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "ailearner.db"

_conn: Optional[aiosqlite.Connection] = None
_write_lock = asyncio.Lock()


async def _get_conn() -> aiosqlite.Connection:
    global _conn
    if _conn is None:
        _conn = await aiosqlite.connect(str(DB_PATH))
        _conn.row_factory = aiosqlite.Row
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA busy_timeout=5000")
    return _conn


async def init_db() -> None:
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
        CREATE TABLE IF NOT EXISTS structured_assessments (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            answers TEXT NOT NULL,
            report TEXT NOT NULL,
            overall_score INTEGER NOT NULL,
            level TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_structured_assessments_session_created
            ON structured_assessments (session_id, created_at DESC);
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
    async with _write_lock:
        await conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
            (session_id,)
        )
        await conn.commit()


async def save_message(session_id: str, role: str, content: Optional[str]):
    conn = await _get_conn()
    async with _write_lock:
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
    async with _write_lock:
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
    async with _write_lock:
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


def _deserialize_assessment(row: aiosqlite.Row) -> dict[str, object]:
    """Convert a database row into the public assessment representation."""
    assessment = dict(row)
    assessment["answers"] = json.loads(assessment["answers"])
    assessment["report"] = json.loads(assessment["report"])
    return assessment


async def create_structured_assessment(
    assessment_id: str,
    session_id: str,
    answers: dict[str, str],
    report: dict[str, object],
) -> None:
    """Persist one completed structured assessment."""
    conn = await _get_conn()
    async with _write_lock:
        await conn.execute(
            """
            INSERT INTO structured_assessments
                (id, session_id, answers, report, overall_score, level)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                assessment_id,
                session_id,
                json.dumps(answers, ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
                int(report["overall_score"]),
                str(report["level"]),
            ),
        )
        await conn.commit()


async def get_structured_assessment(assessment_id: str) -> Optional[dict[str, object]]:
    """Fetch one completed structured assessment by its identifier."""
    conn = await _get_conn()
    cursor = await conn.execute(
        "SELECT * FROM structured_assessments WHERE id = ?", (assessment_id,)
    )
    row = await cursor.fetchone()
    return _deserialize_assessment(row) if row else None


async def list_structured_assessments(session_id: str) -> list[dict[str, object]]:
    """List a session's assessment summaries from newest to oldest."""
    conn = await _get_conn()
    cursor = await conn.execute(
        """
        SELECT id, session_id, overall_score, level, created_at
        FROM structured_assessments
        WHERE session_id = ?
        ORDER BY created_at DESC, rowid DESC
        """,
        (session_id,),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def delete_structured_assessment(assessment_id: str) -> bool:
    """Delete one structured assessment and report whether it existed."""
    conn = await _get_conn()
    async with _write_lock:
        cursor = await conn.execute(
            "DELETE FROM structured_assessments WHERE id = ?", (assessment_id,)
        )
        await conn.commit()
    return cursor.rowcount > 0


async def clear_structured_assessments(session_id: str) -> int:
    """Delete all structured assessments belonging to one session."""
    conn = await _get_conn()
    async with _write_lock:
        cursor = await conn.execute(
            "DELETE FROM structured_assessments WHERE session_id = ?", (session_id,)
        )
        await conn.commit()
    changes_cursor = await conn.execute("SELECT changes()")
    changes_row = await changes_cursor.fetchone()
    return int(changes_row[0]) if changes_row else 0
