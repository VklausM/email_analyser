import sqlite3, json, tempfile
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
    return conn

@contextmanager
def transaction():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except:
        conn.rollback()
        raise
    finally: conn.close()

def init_db():
    with transaction() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS emails (id INTEGER PRIMARY KEY AUTOINCREMENT, email_id TEXT, from_addr TEXT, to_addr TEXT, subject TEXT, body TEXT, date TEXT);
            CREATE TABLE IF NOT EXISTS analyses (id INTEGER PRIMARY KEY AUTOINCREMENT, email_id TEXT, classifications TEXT, tags TEXT, confidence REAL, reasoning TEXT, evidence_lines TEXT, manual_review_required INTEGER, manual_review_reason TEXT, risk_score REAL, criticality_level TEXT, rank INTEGER);
            CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, email_id TEXT, verdict TEXT, reviewer_note TEXT);
            CREATE TABLE IF NOT EXISTS sender_scores (sender TEXT PRIMARY KEY, weight_modifier REAL DEFAULT 1.0, fp_count INTEGER DEFAULT 0, tp_count INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        """)

def clear_data():
    with transaction() as conn:
        conn.execute("DELETE FROM emails")
        conn.execute("DELETE FROM analyses")
        conn.execute("DELETE FROM feedback")

def save_email(eid, f, t, s, b, d=None):
    with transaction() as conn:
        conn.execute("INSERT INTO emails (email_id, from_addr, to_addr, subject, body, date) VALUES (?,?,?,?,?,?)", (eid, f, t, s, b, d))

def save_analysis(r):
    a = r.analysis
    with transaction() as conn:
        conn.execute("""
            INSERT INTO analyses (email_id, classifications, tags, confidence, reasoning, evidence_lines, manual_review_required, manual_review_reason, risk_score, criticality_level, rank)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (r.email_id, json.dumps(a.classifications), json.dumps(a.tags), a.confidence, a.reasoning, json.dumps([e.model_dump() for e in a.evidence_lines]), int(a.manual_review_required), a.manual_review_reason, r.risk_score, r.criticality_level, r.rank))

def get_results():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT a.*, e.from_addr, e.to_addr, e.subject, e.body FROM analyses a JOIN emails e ON a.email_id = e.email_id ORDER BY a.rank").fetchall()]

def get_manual_review_emails():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT a.*, e.from_addr, e.to_addr, e.subject, e.body FROM analyses a JOIN emails e ON a.email_id = e.email_id WHERE a.manual_review_required = 1 ORDER BY a.risk_score DESC").fetchall()]

def record_feedback(eid, v, n=""):
    with get_connection() as conn:
        row = conn.execute("SELECT from_addr FROM emails WHERE email_id = ?", (eid,)).fetchone()
        sender = dict(row)["from_addr"] if row else None
    with transaction() as conn:
        conn.execute("INSERT INTO feedback (email_id, verdict, reviewer_note) VALUES (?,?,?)", (eid, v, n))
        if sender:
            if v == "tp": conn.execute("INSERT INTO sender_scores VALUES (?, 1.05, 1, 0) ON CONFLICT(sender) DO UPDATE SET weight_modifier = MIN(2.0, weight_modifier + 0.05), tp_count = tp_count + 1", (sender,))
            else: conn.execute("INSERT INTO sender_scores VALUES (?, 0.95, 0, 1) ON CONFLICT(sender) DO UPDATE SET weight_modifier = MAX(0.1, weight_modifier - 0.05), fp_count = fp_count + 1", (sender,))

def get_sender_modifier(s):
    with get_connection() as conn:
        r = conn.execute("SELECT weight_modifier FROM sender_scores WHERE sender = ?", (s,)).fetchone()
        return dict(r)["weight_modifier"] if r else 1.0

def get_config(k, d=None):
    with get_connection() as conn:
        r = conn.execute("SELECT value FROM config WHERE key = ?", (k,)).fetchone()
        if r:
            try: return json.loads(dict(r)["value"])
            except: return dict(r)["value"]
        return d

def set_config(k, v):
    with transaction() as conn: conn.execute("INSERT INTO config VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, json.dumps(v)))

def set_meta(k, v):
    with transaction() as conn: conn.execute("INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, v))

def get_meta(k):
    with get_connection() as conn:
        r = conn.execute("SELECT value FROM meta WHERE key = ?", (k,)).fetchone()
        return dict(r)["value"] if r else None
