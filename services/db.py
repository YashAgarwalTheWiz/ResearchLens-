"""One local SQLite file holds everything: users, tokens, sessions, chunks.
SQLite is built into Python, so there is nothing to install or sign up for."""
import json
import os
import sqlite3

from config import DB_PATH


def get_connection():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def loads(value, default):
    """SQLite stores JSON as text; turn it back into Python (or a default if empty)."""
    if value in (None, ""):
        return default
    return json.loads(value)


def init_db():
    conn = get_connection()
    conn.execute("PRAGMA journal_mode = WAL")   # lets reads happen while a write is going on
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rpa_users (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rpa_user_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES rpa_users(user_id),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rpa_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT REFERENCES rpa_users(user_id),
            pdf_name TEXT,
            pdf_hash TEXT,
            chat_history TEXT DEFAULT '[]',
            extracted TEXT,
            positioning TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON rpa_sessions (user_id);

        CREATE TABLE IF NOT EXISTS rpa_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            paper_id TEXT,
            chunk_index INTEGER NOT NULL,
            page_number INTEGER,
            section TEXT,
            chunk_text TEXT NOT NULL,
            embedding BLOB NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_session ON rpa_chunks (session_id);
    """)
    conn.commit()
    conn.close()