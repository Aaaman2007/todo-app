import os
import sqlite3
from datetime import date, datetime, timezone

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config["DATABASE"] = os.environ.get("DATABASE", os.path.join(BASE_DIR, "todos.db"))
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-insecure-key")

PRIORITIES = ("low", "normal", "high")
FILTERS = {"all": "All", "active": "Active", "done": "Done"}

# Only these values ever reach the ORDER BY clause, so user input can't be
# injected into the SQL string.
SORTS = {
    "newest": "id DESC",
    "oldest": "id ASC",
    "priority": (
        "CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, id DESC"
    ),
    "due": "due_date IS NULL, due_date ASC, id DESC",
}

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


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #
def get_db():
    """Return a connection bound to the current request/app context."""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the tasks table. Safe to call on every start."""
    path = app.config["DATABASE"]
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)


init_db()


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def safe_next(fallback="/"):
    """Only follow relative internal redirects (`?next=...`), never external URLs."""
    nxt = request.form.get("next") or ""
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return fallback


def current_url():
    return request.full_path.rstrip("?")


def clean_priority(value):
    return value if value in PRIORITIES else "normal"


def clean_due_date(value):
    """Return an ISO date string, or None when blank/invalid."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def due_info(due_date, done):
    """Human-friendly due date label plus an overdue flag."""
    if not due_date:
        return None
    try:
        due = date.fromisoformat(due_date)
    except ValueError:
        return None

    days = (due - date.today()).days
    if done:
        label = due.strftime("%d %b %Y")
    elif days < 0:
        label = "Overdue by {}d".format(abs(days))
    elif days == 0:
        label = "Due today"
    elif days == 1:
        label = "Due tomorrow"
    else:
        label = "Due {}".format(due.strftime("%d %b"))

    return {"label": label, "overdue": (not done and days < 0), "date": due_date}


def shape(row):
    """Turn a sqlite row into the dict the templates/API consume."""
    done = bool(row["done"])
    return {
        "id": row["id"],
        "title": row["title"],
        "done": done,
        "priority": row["priority"],
        "due": due_info(row["due_date"], done),
        "created_at": row["created_at"],
    }


def stats(db):
    row = db.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done FROM tasks"
    ).fetchone()
    total, done = row["total"], row["done"]
    return {
        "total": total,
        "done": done,
        "active": total - done,
        "percent": round(done * 100 / total) if total else 0,
    }


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.route("/")
def home():
    db = get_db()

    status = request.args.get("status", "all")
    if status not in FILTERS:
        status = "all"

    sort = request.args.get("sort", "newest")
    if sort not in SORTS:
        sort = "newest"

    query = request.args.get("q", "").strip()

    where, params = [], []
    if status == "active":
        where.append("done = 0")
    elif status == "done":
        where.append("done = 1")
    if query:
        where.append("LOWER(title) LIKE ?")
        params.append("%{}%".format(query.lower()))

    sql = "SELECT * FROM tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + SORTS[sort]

    tasks = [shape(row) for row in db.execute(sql, params).fetchall()]

    return render_template(
        "index.html",
        tasks=tasks,
        stats=stats(db),
        status=status,
        sort=sort,
        query=query,
        filters=FILTERS,
        priorities=PRIORITIES,
        today_label=date.today().strftime("%A, %d %B"),
        next_url=current_url(),
    )


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
@app.route("/add", methods=["POST"])
def add():
    title = request.form.get("title", "").strip()
    if not title:
        flash("Task title can't be empty.", "error")
        return redirect(safe_next())

    priority = clean_priority(request.form.get("priority"))
    raw_due = request.form.get("due_date", "").strip()
    due_date = clean_due_date(raw_due)
    if raw_due and due_date is None:
        flash("That due date wasn't valid, so I left it blank.", "error")

    db = get_db()
    db.execute(
        "INSERT INTO tasks (title, priority, due_date, created_at) VALUES (?, ?, ?, ?)",
        (
            title[:200],
            priority,
            due_date,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    db.commit()
    return redirect(safe_next())


@app.route("/toggle/<int:task_id>", methods=["POST"])
def toggle(task_id):
    db = get_db()
    row = db.execute("SELECT done FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        flash("That task no longer exists.", "error")
    else:
        db.execute(
            "UPDATE tasks SET done = ? WHERE id = ?", (0 if row["done"] else 1, task_id)
        )
        db.commit()
    return redirect(safe_next())


@app.route("/edit/<int:task_id>", methods=["POST"])
def edit(task_id):
    db = get_db()
    row = db.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        flash("That task no longer exists.", "error")
        return redirect(safe_next())

    title = request.form.get("title", "").strip()
    if not title:
        flash("Task title can't be empty.", "error")
        return redirect(safe_next())

    raw_due = request.form.get("due_date", "").strip()
    due_date = clean_due_date(raw_due)
    if raw_due and due_date is None:
        flash("That due date wasn't valid, so I left it blank.", "error")

    db.execute(
        "UPDATE tasks SET title = ?, priority = ?, due_date = ? WHERE id = ?",
        (
            title[:200],
            clean_priority(request.form.get("priority")),
            due_date,
            task_id,
        ),
    )
    db.commit()
    flash("Task updated.", "success")
    return redirect(safe_next())


@app.route("/delete/<int:task_id>", methods=["POST"])
def delete(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return redirect(safe_next())


@app.route("/clear-completed", methods=["POST"])
def clear_completed():
    db = get_db()
    removed = db.execute("DELETE FROM tasks WHERE done = 1").rowcount
    db.commit()
    if removed:
        flash("Cleared {} completed task{}.".format(removed, "" if removed == 1 else "s"), "success")
    return redirect(safe_next())


# --------------------------------------------------------------------------- #
# Machine endpoints
# --------------------------------------------------------------------------- #
@app.route("/api/tasks")
def api_tasks():
    db = get_db()
    rows = db.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    return jsonify(tasks=[shape(row) for row in rows], stats=stats(db))


@app.route("/health")
def health():
    """Used by Docker/Kubernetes probes. Checks the DB is actually readable."""
    try:
        total = get_db().execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    except sqlite3.Error as exc:
        return jsonify(status="error", database=str(exc)), 503
    return jsonify(status="ok", database="ok", tasks=total)


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
