"""Small request/formatting helpers shared by the blueprints."""
from datetime import date

from flask import request

PRIORITIES = ("low", "normal", "high")


def safe_next(fallback="/"):
    """Only follow relative internal redirects (`?next=...`), never external URLs."""
    nxt = request.form.get("next") or request.args.get("next") or ""
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
