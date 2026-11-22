"""SQLite access, schema and migrations."""
import os
import sqlite3
import tempfile

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    done       INTEGER NOT NULL DEFAULT 0,
    priority   TEXT    NOT NULL DEFAULT 'normal',
    due_date   TEXT,
    created_at TEXT    NOT NULL
);
"""


def _migration_1(conn):
    """v1: accounts, task ownership, and the index the app queries on."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            name_key      TEXT    NOT NULL UNIQUE,  -- casefolded name
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_users_name_key ON users (name_key);
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "user_id" not in columns:
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN user_id INTEGER "
            "REFERENCES users(id) ON DELETE CASCADE"
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks (user_id)")


# Each migration bumps PRAGMA user_version, so an existing database (including
# the one already running on Railway) is upgraded in place instead of reset.
MIGRATIONS = [_migration_1]


def _prepare(path):
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    try:
        conn.execute("PRAGMA foreign_keys = ON")  # required for ON DELETE CASCADE
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)

        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for number, migration in enumerate(MIGRATIONS, start=1):
            if version >= number:
                continue
            migration(conn)
            conn.execute("PRAGMA user_version = {}".format(number))
        conn.commit()
    finally:
        conn.close()


def init_db(database=None):
    """Create/upgrade the schema. Returns the database path actually in use.

    Falls back to the temp dir on read-only filesystems so the app still boots
    instead of crash-looping on every deploy.
    """
    path = database or current_app.config["DATABASE"]
    try:
        _prepare(path)
        return path
    except (OSError, sqlite3.Error) as exc:
        fallback = os.path.join(tempfile.gettempdir(), "todos.db")
        current_app.logger.warning(
            "Could not use database %s (%s); falling back to %s", path, exc, fallback
        )
        current_app.config["DATABASE"] = fallback
        _prepare(fallback)
        return fallback


def get_db():
    """One connection per request/app context."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exception=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)
