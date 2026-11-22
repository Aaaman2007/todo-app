"""Task routes. Every query is scoped to the logged-in user."""
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
)
from auth import login_required
from db import get_db
from helpers import (
    PRIORITIES,
    clean_due_date,
    clean_priority,
    current_url,
    safe_next,
    shape,
)

bp = Blueprint("tasks", __name__)

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


def stats(user_id):
    row = get_db().execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(done), 0) AS done "
        "FROM tasks WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    total, done = row["total"], row["done"]
    return {
        "total": total,
        "done": done,
        "active": total - done,
        "percent": round(done * 100 / total) if total else 0,
    }


def owned_or_404(task_id):
    """Fetch a task only if it belongs to the current user."""
    row = get_db().execute(
        "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, g.user["id"])
    ).fetchone()
    if row is None:
        abort(404)  # never reveal that another user's task exists
    return row


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@bp.route("/")
@login_required
def home():
    db = get_db()

    status = request.args.get("status", "all")
    if status not in FILTERS:
        status = "all"

    sort = request.args.get("sort", "newest")
    if sort not in SORTS:
        sort = "newest"

    query = request.args.get("q", "").strip()

    where, params = ["user_id = ?"], [g.user["id"]]
    if status == "active":
        where.append("done = 0")
    elif status == "done":
        where.append("done = 1")
    if query:
        where.append("LOWER(title) LIKE ?")
        params.append("%{}%".format(query.lower()))

    rows = db.execute(
        "SELECT * FROM tasks WHERE {} ORDER BY {}".format(" AND ".join(where), SORTS[sort]),
        params,
    ).fetchall()

    return render_template(
        "index.html",
        tasks=[shape(row) for row in rows],
        stats=stats(g.user["id"]),
        status=status,
        sort=sort,
        query=query,
        filters=FILTERS,
        sorts=list(SORTS),
        priorities=PRIORITIES,
        next_url=current_url(),
    )


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
@bp.route("/add", methods=["POST"])
@login_required
def add():
    title = request.form.get("title", "").strip()
    if not title:
        flash("Task title can't be empty.", "error")
        return redirect(safe_next())

    raw_due = request.form.get("due_date", "").strip()
    due_date = clean_due_date(raw_due)
    if raw_due and due_date is None:
        flash("That due date wasn't valid, so I left it blank.", "error")

    db = get_db()
    db.execute(
        "INSERT INTO tasks (user_id, title, priority, due_date, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            g.user["id"],
            title[:200],
            clean_priority(request.form.get("priority")),
            due_date,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    db.commit()
    return redirect(safe_next())


@bp.route("/toggle/<int:task_id>", methods=["POST"])
@login_required
def toggle(task_id):
    row = owned_or_404(task_id)
    db = get_db()
    db.execute(
        "UPDATE tasks SET done = ? WHERE id = ? AND user_id = ?",
        (0 if row["done"] else 1, task_id, g.user["id"]),
    )
    db.commit()
    return redirect(safe_next())


@bp.route("/edit/<int:task_id>", methods=["POST"])
@login_required
def edit(task_id):
    owned_or_404(task_id)

    title = request.form.get("title", "").strip()
    if not title:
        flash("Task title can't be empty.", "error")
        return redirect(safe_next())

    raw_due = request.form.get("due_date", "").strip()
    due_date = clean_due_date(raw_due)
    if raw_due and due_date is None:
        flash("That due date wasn't valid, so I left it blank.", "error")

    db = get_db()
    db.execute(
        "UPDATE tasks SET title = ?, priority = ?, due_date = ? "
        "WHERE id = ? AND user_id = ?",
        (
            title[:200],
            clean_priority(request.form.get("priority")),
            due_date,
            task_id,
            g.user["id"],
        ),
    )
    db.commit()
    flash("Task updated.", "success")
    return redirect(safe_next())


@bp.route("/delete/<int:task_id>", methods=["POST"])
@login_required
def delete(task_id):
    owned_or_404(task_id)
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, g.user["id"]))
    db.commit()
    return redirect(safe_next())


@bp.route("/clear-completed", methods=["POST"])
@login_required
def clear_completed():
    db = get_db()
    removed = db.execute(
        "DELETE FROM tasks WHERE done = 1 AND user_id = ?", (g.user["id"],)
    ).rowcount
    db.commit()
    if removed:
        flash(
            "Cleared {} completed task{}.".format(removed, "" if removed == 1 else "s"),
            "success",
        )
    return redirect(safe_next())


# --------------------------------------------------------------------------- #
# JSON API
# --------------------------------------------------------------------------- #
@bp.route("/api/tasks")
def api_tasks():
    if g.user is None:
        return jsonify(error="authentication required"), 401

    rows = get_db().execute(
        "SELECT * FROM tasks WHERE user_id = ? ORDER BY id DESC", (g.user["id"],)
    ).fetchall()
    return jsonify(
        user=g.user["name"],
        tasks=[shape(row) for row in rows],
        stats=stats(g.user["id"]),
    )
