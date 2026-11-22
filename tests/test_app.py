import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app_module.app.config.update(
        DATABASE=str(tmp_path / "test.db"),
        TESTING=True,
        SECRET_KEY="test",
    )
    app_module.init_db()
    with app_module.app.test_client() as test_client:
        yield test_client


def add(client, title, priority="normal", due=""):
    return client.post(
        "/add", data={"title": title, "priority": priority, "due_date": due}
    )


def tasks(client):
    return client.get("/api/tasks").get_json()["tasks"]


def test_index_starts_empty(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Your list is empty" in response.data


def test_add_task(client):
    response = add(client, "Buy milk", priority="high")
    assert response.status_code == 302

    stored = tasks(client)
    assert len(stored) == 1
    assert stored[0]["title"] == "Buy milk"
    assert stored[0]["priority"] == "high"
    assert stored[0]["done"] is False


def test_add_trims_whitespace(client):
    add(client, "   Walk the dog   ")
    assert tasks(client)[0]["title"] == "Walk the dog"


def test_blank_title_is_rejected(client):
    add(client, "    ")
    assert tasks(client) == []


def test_tasks_persist_across_requests(client):
    add(client, "Persisted task")
    assert b"Persisted task" in client.get("/").data


def test_invalid_priority_falls_back_to_normal(client):
    add(client, "Sneaky", priority="urgent!!")
    assert tasks(client)[0]["priority"] == "normal"


def test_invalid_due_date_is_ignored(client):
    add(client, "No date", due="not-a-date")
    assert tasks(client)[0]["due"] is None


def test_valid_due_date_is_stored(client):
    add(client, "Dated", due="2030-01-15")
    due = tasks(client)[0]["due"]
    assert due is not None
    assert due["date"] == "2030-01-15"
    assert due["overdue"] is False


def test_past_due_date_is_overdue(client):
    add(client, "Late", due="2020-01-01")
    assert tasks(client)[0]["due"]["overdue"] is True


def test_toggle_marks_done_and_back(client):
    add(client, "Toggle me")
    task_id = tasks(client)[0]["id"]

    client.post("/toggle/{}".format(task_id))
    assert tasks(client)[0]["done"] is True

    client.post("/toggle/{}".format(task_id))
    assert tasks(client)[0]["done"] is False


def test_toggle_missing_task_does_not_crash(client):
    response = client.post("/toggle/999")
    assert response.status_code == 302
    assert client.get("/health").status_code == 200


def test_edit_task(client):
    add(client, "Old title")
    task_id = tasks(client)[0]["id"]

    client.post(
        "/edit/{}".format(task_id),
        data={"title": "New title", "priority": "low", "due_date": "2030-05-01"},
    )

    stored = tasks(client)[0]
    assert stored["title"] == "New title"
    assert stored["priority"] == "low"
    assert stored["due"]["date"] == "2030-05-01"


def test_edit_rejects_blank_title(client):
    add(client, "Keep me")
    task_id = tasks(client)[0]["id"]

    client.post("/edit/{}".format(task_id), data={"title": "  "})

    assert tasks(client)[0]["title"] == "Keep me"


def test_delete_task(client):
    add(client, "Delete me")
    task_id = tasks(client)[0]["id"]

    client.post("/delete/{}".format(task_id))

    assert tasks(client) == []


def test_filters(client):
    add(client, "Active one")
    add(client, "Done one")
    done_id = [t for t in tasks(client) if t["title"] == "Done one"][0]["id"]
    client.post("/toggle/{}".format(done_id))

    active = client.get("/?status=active").data
    assert b"Active one" in active and b"Done one" not in active

    done = client.get("/?status=done").data
    assert b"Done one" in done and b"Active one" not in done


def test_search(client):
    add(client, "Buy coffee beans")
    add(client, "Fix the bike")

    response = client.get("/?q=coffee")
    assert b"Buy coffee beans" in response.data
    assert b"Fix the bike" not in response.data


def test_unknown_filter_and_sort_are_safe(client):
    add(client, "Still here")
    response = client.get("/?status=bogus&sort=;DROP TABLE tasks;--")
    assert response.status_code == 200
    assert len(tasks(client)) == 1


def test_clear_completed(client):
    add(client, "Done A")
    add(client, "Done B")
    add(client, "Keep me")
    for task in tasks(client):
        if task["title"].startswith("Done"):
            client.post("/toggle/{}".format(task["id"]))

    client.post("/clear-completed")

    remaining = [t["title"] for t in tasks(client)]
    assert remaining == ["Keep me"]


def test_titles_are_escaped(client):
    add(client, "<script>alert(1)</script>")
    html = client.get("/").data.decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_open_redirect_is_blocked(client):
    response = client.post(
        "/add", data={"title": "Safe redirect", "next": "https://evil.example"}
    )
    assert response.headers["Location"] == "/"


def test_relative_next_is_followed(client):
    response = client.post(
        "/add",
        data={"title": "Filtered add", "next": "/?status=active"},
    )
    assert response.headers["Location"] == "/?status=active"


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["tasks"] == 0


def test_unknown_page_returns_404(client):
    assert client.get("/does-not-exist").status_code == 404


def test_init_db_falls_back_when_path_is_unwritable(client):
    app_module.app.config["DATABASE"] = "/proc/definitely-not-writable/todos.db"
    app_module.init_db()

    assert app_module.app.config["DATABASE"] != "/proc/definitely-not-writable/todos.db"
    assert client.get("/health").status_code == 200


def test_init_db_is_idempotent(client):
    add(client, "Only one")
    app_module.init_db()
    assert len(tasks(client)) == 1
