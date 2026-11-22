import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from db import get_db  # noqa: E402

PASSWORD = "password123"


# --------------------------------------------------------------------------- #
# Fixtures & helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.db"),
            "SECRET_KEY": "test-secret",
        }
    )
    yield application
    application.extensions.pop("login_attempts", None)


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client):
    """Read (or seed) the CSRF token the app expects for this session."""
    with client.session_transaction() as session:
        return session.setdefault("_csrf", "test-token")


def post(client, url, **data):
    data.setdefault("_csrf", csrf(client))
    return client.post(url, data=data)


def signup(client, name="alice", password=PASSWORD):
    return post(client, "/signup", name=name, password=password, password2=password)


def login(client, name="alice", password=PASSWORD):
    return post(client, "/login", name=name, password=password)


def logout(client):
    return post(client, "/logout")


def add(client, title="A task", priority="normal", due=""):
    return post(client, "/add", title=title, priority=priority, due_date=due)


def tasks(client):
    return client.get("/api/tasks").get_json()["tasks"]


# --------------------------------------------------------------------------- #
# Access control
# --------------------------------------------------------------------------- #
def test_home_requires_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_every_task_route_requires_login(client):
    csrf(client)  # a valid token, so we're testing the login guard and not CSRF
    for url in ["/add", "/toggle/1", "/edit/1", "/delete/1", "/clear-completed"]:
        response = post(client, url, title="x")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    assert "/login" in client.get("/").headers["Location"]


def test_signup_creates_account_and_logs_in(client):
    response = signup(client, "alice")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"

    home = client.get("/")
    assert home.status_code == 200
    assert b"Hi," in home.data and b"alice" in home.data


def test_password_is_stored_hashed(app, client):
    signup(client, "alice")
    with app.app_context():
        row = get_db().execute("SELECT password_hash FROM users").fetchone()
    assert PASSWORD not in row["password_hash"]
    assert row["password_hash"].startswith(("scrypt:", "pbkdf2:"))


def test_signup_rejects_bad_names(client):
    for name in ["ab", "has space", "no-dashes", "x" * 31, "emoji😀"]:
        response = signup(client, name)
        assert b"3-30 letters" in response.data, name


def test_signup_rejects_reserved_names(client):
    response = signup(client, "Admin")
    assert b"reserved" in response.data


def test_signup_rejects_short_password(client):
    response = post(client, "/signup", name="alice", password="short", password2="short")
    assert b"at least 8" in response.data


def test_signup_rejects_password_mismatch(client):
    response = post(
        client, "/signup", name="alice", password=PASSWORD, password2="different1"
    )
    assert b"don&#39;t match" in response.data or b"don't match" in response.data


def test_names_are_unique_case_insensitively(client):
    signup(client, "alice")
    logout(client)
    response = signup(client, "Alice")
    assert b"already taken" in response.data


def test_login_is_case_insensitive(client):
    signup(client, "Alice")
    logout(client)
    response = login(client, "alice")
    assert response.status_code == 302
    assert b"Hi," in client.get("/").data


def test_login_wrong_password_uses_generic_message(client):
    signup(client, "alice")
    logout(client)
    response = login(client, "alice", "wrong-password")
    assert b"Name or password is incorrect" in response.data
    assert b"Hi," not in response.data


def test_login_unknown_user_uses_same_message(client):
    response = login(client, "nobody", "whatever123")
    assert b"Name or password is incorrect" in response.data


def test_login_preserves_next(client):
    signup(client, "alice")
    logout(client)
    response = post(
        client, "/login", name="alice", password=PASSWORD, next="/?status=active"
    )
    assert response.headers["Location"] == "/?status=active"


def test_login_blocks_open_redirect(client):
    signup(client, "alice")
    logout(client)
    response = post(
        client, "/login", name="alice", password=PASSWORD, next="https://evil.example"
    )
    assert response.headers["Location"] == "/"


def test_logout_requires_post(client):
    signup(client, "alice")
    assert client.get("/logout").status_code == 405
    assert logout(client).status_code == 302
    assert "/login" in client.get("/").headers["Location"]


def test_post_without_csrf_token_is_rejected(client):
    signup(client, "alice")
    response = client.post("/add", data={"title": "No token"})
    assert response.status_code == 400
    assert tasks(client) == []


def test_login_is_throttled(app, client):
    signup(client, "alice")
    logout(client)
    for _ in range(5):
        login(client, "alice", "wrong-password")

    blocked = login(client, "alice", PASSWORD)  # even the right password
    assert blocked.status_code == 429
    assert b"Too many attempts" in blocked.data


def test_session_cookie_is_hardened(client):
    cookie = client.get("/login").headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


# --------------------------------------------------------------------------- #
# Tasks (single user)
# --------------------------------------------------------------------------- #
def test_add_and_list_task(client):
    signup(client)
    assert add(client, "Buy milk", priority="high", due="2030-01-15").status_code == 302

    stored = tasks(client)
    assert len(stored) == 1
    assert stored[0]["title"] == "Buy milk"
    assert stored[0]["priority"] == "high"
    assert stored[0]["due"]["date"] == "2030-01-15"
    assert b"Buy milk" in client.get("/").data


def test_blank_title_is_rejected(client):
    signup(client)
    add(client, "   ")
    assert tasks(client) == []


def test_invalid_values_fall_back(client):
    signup(client)
    add(client, "Sneaky", priority="urgent!!", due="not-a-date")
    stored = tasks(client)[0]
    assert stored["priority"] == "normal"
    assert stored["due"] is None


def test_toggle_edit_delete(client):
    signup(client)
    add(client, "Toggle me")
    task_id = tasks(client)[0]["id"]

    post(client, "/toggle/{}".format(task_id))
    assert tasks(client)[0]["done"] is True
    post(client, "/toggle/{}".format(task_id))
    assert tasks(client)[0]["done"] is False

    post(
        client,
        "/edit/{}".format(task_id),
        title="Edited",
        priority="low",
        due_date="2030-05-01",
    )
    edited = tasks(client)[0]
    assert edited["title"] == "Edited"
    assert edited["priority"] == "low"

    post(client, "/delete/{}".format(task_id))
    assert tasks(client) == []


def test_filters_and_search(client):
    signup(client)
    add(client, "Buy coffee beans")
    add(client, "Fix the bike")
    done_id = [t for t in tasks(client) if t["title"] == "Fix the bike"][0]["id"]
    post(client, "/toggle/{}".format(done_id))

    active = client.get("/?status=active").data
    assert b"Buy coffee beans" in active and b"Fix the bike" not in active

    done = client.get("/?status=done").data
    assert b"Fix the bike" in done and b"Buy coffee beans" not in done

    search = client.get("/?q=coffee").data
    assert b"Buy coffee beans" in search and b"Fix the bike" not in search


def test_unknown_filter_and_sort_are_safe(client):
    signup(client)
    add(client, "Still here")
    response = client.get("/?status=bogus&sort=;DROP TABLE tasks;--")
    assert response.status_code == 200
    assert len(tasks(client)) == 1


def test_clear_completed(client):
    signup(client)
    add(client, "Done A")
    add(client, "Keep me")
    done_id = [t for t in tasks(client) if t["title"] == "Done A"][0]["id"]
    post(client, "/toggle/{}".format(done_id))

    post(client, "/clear-completed")
    assert [t["title"] for t in tasks(client)] == ["Keep me"]


def test_titles_are_escaped(client):
    signup(client)
    add(client, "<script>alert(1)</script>")
    html = client.get("/").data.decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# --------------------------------------------------------------------------- #
# Privacy between accounts
# --------------------------------------------------------------------------- #
def test_users_cannot_see_each_others_tasks(client):
    signup(client, "alice")
    add(client, "Alice secret")
    alice_task = tasks(client)[0]["id"]
    logout(client)

    signup(client, "bob")
    home = client.get("/")

    assert b"Alice secret" not in home.data
    assert tasks(client) == []
    assert client.get("/?q=secret").data.count(b"Alice secret") == 0
    assert b"Your list is empty" in home.data

    for url in [
        "/toggle/{}".format(alice_task),
        "/edit/{}".format(alice_task),
        "/delete/{}".format(alice_task),
    ]:
        assert post(client, url, title="hijacked").status_code == 404

    # Alice's task is untouched.
    logout(client)
    login(client, "alice")
    stored = tasks(client)
    assert len(stored) == 1
    assert stored[0]["title"] == "Alice secret"
    assert stored[0]["done"] is False


def test_second_account_does_not_adopt_first_accounts_tasks(client):
    signup(client, "alice")
    add(client, "Alice task")
    logout(client)

    signup(client, "bob")
    assert tasks(client) == []

    logout(client)
    login(client, "alice")
    assert [t["title"] for t in tasks(client)] == ["Alice task"]


def test_clear_completed_only_touches_own_tasks(client):
    signup(client, "alice")
    add(client, "Alice done")
    post(client, "/toggle/{}".format(tasks(client)[0]["id"]))
    logout(client)

    signup(client, "bob")
    post(client, "/clear-completed")

    logout(client)
    login(client, "alice")
    assert [t["title"] for t in tasks(client)] == ["Alice done"]


def test_legacy_tasks_are_adopted_by_first_account(app, client):
    with app.app_context():
        conn = get_db()
        conn.execute(
            "INSERT INTO tasks (title, created_at) VALUES ('Legacy task', "
            "'2026-01-01T00:00:00+00:00')"
        )
        conn.commit()

    signup(client, "alice")
    assert [t["title"] for t in tasks(client)] == ["Legacy task"]


def test_api_requires_authentication(client):
    response = client.get("/api/tasks")
    assert response.status_code == 401
    assert response.get_json()["error"] == "authentication required"


# --------------------------------------------------------------------------- #
# Infra
# --------------------------------------------------------------------------- #
def test_health_needs_no_login_and_leaks_nothing(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body == {"status": "ok", "database": "ok"}


def test_unknown_page_returns_404(client):
    assert client.get("/does-not-exist").status_code == 404


def test_unknown_api_path_returns_json(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.get_json()["error"] == "not found"


def test_migrations_are_idempotent(tmp_path):
    database = str(tmp_path / "again.db")
    create_app({"TESTING": True, "DATABASE": database, "SECRET_KEY": "k"})
    # Second boot on the same file must not re-run migrations or lose data.
    second = create_app({"TESTING": True, "DATABASE": database, "SECRET_KEY": "k"})
    with second.app_context():
        columns = {row[1] for row in get_db().execute("PRAGMA table_info(tasks)")}
        version = get_db().execute("PRAGMA user_version").fetchone()[0]
    assert "user_id" in columns
    assert version == 1


def test_unwritable_database_falls_back(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": "/proc/definitely-not-writable/todos.db",
            "SECRET_KEY": "k",
        }
    )
    assert application.config["DATABASE"] != "/proc/definitely-not-writable/todos.db"
    assert application.test_client().get("/health").status_code == 200


def test_upgrades_an_existing_pre_accounts_database(tmp_path):
    """The database already running on Railway has no users table and no user_id."""
    import sqlite3

    database = str(tmp_path / "old.db")
    with sqlite3.connect(database) as conn:
        conn.executescript(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                priority TEXT NOT NULL DEFAULT 'normal',
                due_date TEXT,
                created_at TEXT NOT NULL);
            INSERT INTO tasks (title, created_at)
                VALUES ('Task from before accounts', '2026-01-01T00:00:00+00:00');
            """
        )
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0

    application = create_app(
        {"TESTING": True, "DATABASE": database, "SECRET_KEY": "k"}
    )
    client = application.test_client()
    signup(client, "alice")

    assert [t["title"] for t in tasks(client)] == ["Task from before accounts"]
    with application.app_context():
        version = get_db().execute("PRAGMA user_version").fetchone()[0]
    assert version == 1


def test_environment_variables_configure_the_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE", str(tmp_path / "from-env.db"))
    monkeypatch.setenv("SECRET_KEY", "secret-from-env")
    monkeypatch.setenv("COOKIE_SECURE", "1")

    application = create_app()
    assert application.config["DATABASE"] == str(tmp_path / "from-env.db")
    assert application.config["SECRET_KEY"] == "secret-from-env"
    assert application.config["SESSION_COOKIE_SECURE"] is True
    assert application.test_client().get("/health").status_code == 200


def test_cookie_secure_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    application = create_app(
        {"TESTING": True, "DATABASE": str(tmp_path / "plain.db"), "SECRET_KEY": "k"}
    )
    assert application.config["SESSION_COOKIE_SECURE"] is False
