"""Application factory and the parts that aren't tasks or accounts."""
import hmac
import os
import secrets
import sqlite3
from datetime import date

import click
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request, session
from werkzeug.security import generate_password_hash

import db
from db import get_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Local development: read .env from the project root if it exists.
# Variables already set in the real environment always win, so Railway's
# injected values are never overwritten.
load_dotenv()


def create_app(config=None):
    app = Flask(__name__)

    app.config.update(
        DATABASE=os.environ.get("DATABASE", os.path.join(BASE_DIR, "todos.db")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Railway terminates TLS; set COOKIE_SECURE=1 there so cookies never
        # travel over plain HTTP.
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    )

    secret = os.environ.get("SECRET_KEY")
    if not secret:
        # Random per boot: sessions are safe from forgery, but logins don't
        # survive a restart. Set SECRET_KEY in production.
        secret = secrets.token_hex(32)
        app.logger.warning(
            "SECRET_KEY is not set - generated a temporary key. "
            "Sessions will be invalidated on restart. Set SECRET_KEY in production."
        )
    app.config["SECRET_KEY"] = secret

    if config:
        app.config.update(config)

    db.init_app(app)
    with app.app_context():
        db.init_db()

    from auth import bp as auth_bp, load_logged_in_user
    from tasks import bp as tasks_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)

    @app.before_request
    def protect_csrf():
        token = session.get("_csrf")
        if not token:
            token = session["_csrf"] = secrets.token_urlsafe(32)
        if request.method == "POST":
            sent = request.form.get("_csrf", "")
            if not hmac.compare_digest(sent, token):
                abort(400, description="Invalid or missing CSRF token.")

    app.before_request(load_logged_in_user)

    @app.context_processor
    def inject_globals():
        return {
            "csrf": session.get("_csrf", ""),
            "today_label": date.today().strftime("%A, %d %B"),
        }

    @app.route("/health")
    def health():
        """Used by container/platform health probes. No user data exposed."""
        try:
            get_db().execute("SELECT COUNT(*) FROM tasks").fetchone()
        except sqlite3.Error as exc:
            return jsonify(status="error", database=str(exc)), 503
        return jsonify(status="ok", database="ok")

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify(error="not found"), 404
        return render_template("404.html"), 404

    @app.cli.command("reset-password")
    @click.argument("name")
    def reset_password(name):
        """Set a new password for an existing account (no email needed)."""
        row = get_db().execute(
            "SELECT id, name FROM users WHERE name_key = ?", (name.strip().casefold(),)
        ).fetchone()
        if row is None:
            raise click.ClickException("No account called {!r}.".format(name))

        password = click.prompt(
            "New password for {}".format(row["name"]),
            hide_input=True,
            confirmation_prompt=True,
        )
        if len(password) < 8:
            raise click.ClickException("Password must be at least 8 characters.")

        conn = get_db()
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password[:1024]), row["id"]),
        )
        conn.commit()
        click.echo("Password updated for {}.".format(row["name"]))

    return app


app = create_app()


if __name__ == "__main__":
    # Railway/Render/Heroku inject PORT, and public traffic is routed to the
    # port configured in the platform's dashboard. These must match, so we
    # honour PORT and only fall back to 5000 when it is unset.
    port = int(os.environ.get("PORT", 5000))
    print(" * Listening on http://0.0.0.0:{}".format(port), flush=True)
    print(" * Database: {}".format(app.config["DATABASE"]), flush=True)
    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
