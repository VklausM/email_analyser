import sqlite3
import json
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from utils.logger import get_logger

log = get_logger("db")

DB_PATH = Path(__file__).parent / "email_analyser.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def transaction():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with transaction() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS batches (
                id          TEXT PRIMARY KEY,
                filename    TEXT NOT NULL,
                total       INTEGER DEFAULT 0,
                critical    INTEGER DEFAULT 0,
                high        INTEGER DEFAULT 0,
                medium      INTEGER DEFAULT 0,
                low         INTEGER DEFAULT 0,
                manual      INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS emails (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id    TEXT NOT NULL,
                email_id    TEXT NOT NULL,
                from_addr   TEXT,
                to_addr     TEXT,
                subject     TEXT,
                body        TEXT,
                date        TEXT,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES batches(id)
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id                TEXT NOT NULL,
                batch_id                TEXT NOT NULL,
                classifications         TEXT,
                tags                    TEXT,
                confidence              REAL,
                reasoning               TEXT,
                evidence_lines          TEXT,
                manual_review_required  INTEGER DEFAULT 0,
                manual_review_reason    TEXT,
                risk_score              REAL,
                criticality_level       TEXT,
                rank                    INTEGER,
                created_at              TEXT NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES batches(id)
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id        TEXT NOT NULL,
                batch_id        TEXT NOT NULL,
                verdict         TEXT NOT NULL,
                reviewer_note   TEXT,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sender_scores (
                sender          TEXT PRIMARY KEY,
                weight_modifier REAL DEFAULT 1.0,
                fp_count        INTEGER DEFAULT 0,
                tp_count        INTEGER DEFAULT 0,
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS config (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
        """)
    log.info("Database ready at %s", DB_PATH)


def save_batch(batch_id: str, filename: str, summary: dict):
    now = datetime.utcnow().isoformat()
    with transaction() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO batches (id, filename, total, critical, high, medium, low, manual, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            batch_id, filename,
            summary.get("total", 0), summary.get("critical", 0),
            summary.get("high", 0), summary.get("medium", 0),
            summary.get("low", 0), summary.get("manual", 0),
            now
        ))


def save_email(batch_id: str, email_id: str, from_addr: str, to_addr: str,
               subject: str, body: str, date: str = None):
    now = datetime.utcnow().isoformat()
    with transaction() as conn:
        conn.execute("""
            INSERT INTO emails (batch_id, email_id, from_addr, to_addr, subject, body, date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_id, email_id, from_addr, to_addr, subject, body, date, now))


def save_analysis(batch_id: str, result):
    now = datetime.utcnow().isoformat()
    a = result.analysis
    evidence = json.dumps([e.model_dump() for e in a.evidence_lines])
    classifications = json.dumps(a.classifications)
    tags = json.dumps(getattr(a, "tags", []))

    with transaction() as conn:
        conn.execute("""
            INSERT INTO analyses
                (email_id, batch_id, classifications, tags, confidence, reasoning,
                 evidence_lines, manual_review_required, manual_review_reason,
                 risk_score, criticality_level, rank, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.email_id, batch_id, classifications, tags,
            a.confidence, a.reasoning, evidence,
            int(a.manual_review_required), a.manual_review_reason,
            result.risk_score, result.criticality_level, result.rank, now
        ))


def get_all_batches() -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM batches ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_batch_results(batch_id: str) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.*, e.from_addr, e.to_addr, e.subject, e.body
        FROM analyses a
        JOIN emails e ON a.email_id = e.email_id AND a.batch_id = e.batch_id
        WHERE a.batch_id = ?
        ORDER BY a.rank
    """, (batch_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_manual_review_emails(batch_id: str) -> list:
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.*, e.from_addr, e.to_addr, e.subject, e.body
        FROM analyses a
        JOIN emails e ON a.email_id = e.email_id AND a.batch_id = e.batch_id
        WHERE a.batch_id = ? AND a.manual_review_required = 1
        ORDER BY a.risk_score DESC
    """, (batch_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_feedback(email_id: str, batch_id: str, verdict: str, note: str = ""):
    now = datetime.utcnow().isoformat()

    # Get the sender for this email
    conn = get_connection()
    row = conn.execute(
        "SELECT from_addr FROM emails WHERE email_id = ? AND batch_id = ?",
        (email_id, batch_id)
    ).fetchone()
    conn.close()

    sender = dict(row)["from_addr"] if row else None

    with transaction() as conn:
        conn.execute("""
            INSERT INTO feedback (email_id, batch_id, verdict, reviewer_note, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (email_id, batch_id, verdict, note, now))

        if sender:
            if verdict == "tp":
                conn.execute("""
                    INSERT INTO sender_scores (sender, weight_modifier, tp_count, fp_count, updated_at)
                    VALUES (?, 1.05, 1, 0, ?)
                    ON CONFLICT(sender) DO UPDATE SET
                        weight_modifier = MIN(2.0, weight_modifier + 0.05),
                        tp_count = tp_count + 1,
                        updated_at = excluded.updated_at
                """, (sender, now))
            elif verdict == "fp":
                conn.execute("""
                    INSERT INTO sender_scores (sender, weight_modifier, tp_count, fp_count, updated_at)
                    VALUES (?, 0.95, 0, 1, ?)
                    ON CONFLICT(sender) DO UPDATE SET
                        weight_modifier = MAX(0.1, weight_modifier - 0.05),
                        fp_count = fp_count + 1,
                        updated_at = excluded.updated_at
                """, (sender, now))


def get_sender_modifier(sender: str) -> float:
    conn = get_connection()
    row = conn.execute(
        "SELECT weight_modifier FROM sender_scores WHERE sender = ?", (sender,)
    ).fetchone()
    conn.close()
    return dict(row)["weight_modifier"] if row else 1.0


def get_config(key: str, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(dict(row)["value"])
        except (json.JSONDecodeError, KeyError):
            return dict(row)["value"]
    return default


def set_config(key: str, value):
    now = datetime.utcnow().isoformat()
    with transaction() as conn:
        conn.execute("""
            INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (key, json.dumps(value), now))


def get_all_config() -> dict:
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM config").fetchall()
    conn.close()
    result = {}
    for r in rows:
        try:
            result[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, KeyError):
            result[r["key"]] = r["value"]
    return result
