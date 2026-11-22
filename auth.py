"""Accounts: signup, login, logout, and the login_required guard.

Identity is a display name plus a password. Names are stored twice: as typed
(`name`, shown in the UI) and casefolded (`name_key`, unique), so "Aman" and
"aman" cannot be two accounts.
"""
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db
from helpers import safe_next

bp = Blueprint("auth", __name__)

NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
RESERVED_NAMES = {
    "admin", "administrator", "root", "superuser", "support",
    "me", "guest", "system", "moderator", "owner", "null", "undefined",
}
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024
MAX_ATTEMPTS = 5
ATTEMPT_WINDOW = 15 * 60  # seconds


# --------------------------------------------------------------------------- #
# Session helpers
# --------------------------------------------------------------------------- #
def load_logged_in_user():
    """Populate g.user for every request."""
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, name FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if g.user is None:  # account deleted while the cookie lived on
            session.pop("user_id", None)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "error")
            return redirect(
                url_for("auth.login", next=request.full_path.rstrip("?"))
            )
        return view(*args, **kwargs)

    return wrapped


def _start_session(user_id):
    session.clear()  # fresh session: no fixation, no stale CSRF token
    session["user_id"] = user_id
    session["_csrf"] = secrets.token_urlsafe(32)


# --------------------------------------------------------------------------- #
# Login throttling (in-memory; good enough for a single-process deployment)
# --------------------------------------------------------------------------- #
def _attempt_store():
    return current_app.extensions.setdefault("login_attempts", {})


def _attempt_key(name_key):
    return (name_key, request.remote_addr or "?")


def _too_many_attempts(key):
    now = time.time()
    recent = [t for t in _attempt_store().get(key, []) if now - t < ATTEMPT_WINDOW]
    _attempt_store()[key] = recent
    return len(recent) >= MAX_ATTEMPTS


def _record_failure(key):
    _attempt_store().setdefault(key, []).append(time.time())


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user is not None:
        return redirect(url_for("tasks.home"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("password2", "")
        name_key = name.casefold()

        if not NAME_RE.fullmatch(name):
            flash("Name must be 3-30 letters, numbers or underscores.", "error")
        elif name_key in RESERVED_NAMES:
            flash("That name is reserved - please pick another.", "error")
        elif len(password) < MIN_PASSWORD_LENGTH:
            flash(
                "Password must be at least {} characters.".format(MIN_PASSWORD_LENGTH),
                "error",
            )
        elif password != confirm:
            flash("Those passwords don't match.", "error")
        else:
            db = get_db()
            first_account = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            try:
                cursor = db.execute(
                    "INSERT INTO users (name, name_key, password_hash, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        name,
                        name_key,
                        generate_password_hash(password[:MAX_PASSWORD_LENGTH]),
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    ),
                )
                # Tasks created before accounts existed belong to the first user.
                if first_account:
                    db.execute(
                        "UPDATE tasks SET user_id = ? WHERE user_id IS NULL",
                        (cursor.lastrowid,),
                    )
                db.commit()
            except sqlite3.IntegrityError:
                flash("That name is already taken.", "error")
            else:
                _start_session(cursor.lastrowid)
                flash("Welcome, {}!".format(name), "success")
                return redirect(url_for("tasks.home"))

    return render_template("signup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("tasks.home"))

    if request.method == "POST":
        name_key = request.form.get("name", "").strip().casefold()
        password = request.form.get("password", "")
        key = _attempt_key(name_key)

        if _too_many_attempts(key):
            flash("Too many attempts. Please wait 15 minutes and try again.", "error")
            return render_template("login.html"), 429

        row = get_db().execute(
            "SELECT id, name, password_hash FROM users WHERE name_key = ?", (name_key,)
        ).fetchone()

        # One generic message for both "no such user" and "wrong password", so
        # the form can't be used to discover which names exist.
        if row is None or not check_password_hash(
            row["password_hash"], password[:MAX_PASSWORD_LENGTH]
        ):
            _record_failure(key)
            flash("Name or password is incorrect.", "error")
        else:
            _attempt_store().pop(key, None)
            _start_session(row["id"])
            return redirect(safe_next(url_for("tasks.home")))

    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You're logged out.", "success")
    return redirect(url_for("auth.login"))
