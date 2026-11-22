# To-Do App

A private, multi-user to-do list built with Flask and SQLite. It is the first stage of my
DevOps learning project: Docker, CI/CD, Terraform, Kubernetes, and monitoring come next.

## Features
- **Accounts** — sign up and log in with a display name and password
- **Private by default** — every query is scoped to the logged-in user, so a list only ever
  shows the tasks added on that account, on that person's device
- **Persistent tasks** stored in SQLite, upgraded in place by migrations
- **Add, edit, complete, and delete** tasks, with inline editing
- **Priority levels** (low / normal / high) and **due dates** (`Due today`, `Overdue by 3d`)
- **Filters and search** — All / Active / Done, text search, four sort orders
- **Progress tracking** — completion percentage and a progress bar
- **Responsive, dark-mode-aware UI** — one stylesheet, no external CSS/JS dependencies
- **Keyboard shortcuts** — `/` or `n` jumps to the input, `Esc` leaves it
- `/health` endpoint for container/platform health checks
- JSON API at `/api/tasks` (login required)

## How accounts and privacy work
- Identity is a **display name + password**. Names are unique case-insensitively
  (`Aman` and `aman` are the same account), so no email is involved.
- Passwords are stored as **scrypt hashes** (Werkzeug) — never in plain text.
- The session cookie is **signed, HttpOnly, SameSite=Lax**, and `Secure` when
  `COOKIE_SECURE=1`; it only contains the user id.
- Every task query filters on `user_id`. Asking for someone else's task by id returns
  **404**, never their data — the response doesn't even confirm the task exists.
- All `POST` forms carry a **CSRF token**; requests without one are rejected with 400.
- **Login throttling**: 5 failed attempts per name/IP within 15 minutes, then 429.
- Wrong password and unknown name return the **same** message, so the form can't be used
  to discover which names exist.
- Forgot a password (there's no email reset by design):
  `flask --app app reset-password <name>`

## Project structure
```
todo-app/
├── app.py                  # app factory, CSRF, /health, error pages, CLI
├── auth.py                 # signup / login / logout, login_required, throttling
├── tasks.py                # task routes, all scoped to the logged-in user
├── db.py                   # connection handling, schema, migrations
├── helpers.py              # date/priority formatting, safe redirects
├── requirements.txt        # runtime dependencies (Flask + gunicorn)
├── requirements-dev.txt    # + pytest
├── railway.json            # Railway build/deploy config (start command, healthcheck)
├── Procfile                # same start command for other PaaS hosts
├── static/
│   ├── style.css           # the whole design, light + dark
│   └── app.js              # delete confirmation, keyboard shortcuts
├── templates/
│   ├── base.html           # shared shell: header, account menu, flash messages
│   ├── index.html          # the task list
│   ├── login.html
│   ├── signup.html
│   └── 404.html
├── .github/workflows/tests.yml   # runs pytest on every push and PR
└── tests/
    ├── conftest.py
    └── test_app.py         # 37 tests, incl. cross-account isolation
```

## Run locally

    git clone https://github.com/Aaman2007/todo-app.git
    cd todo-app
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python app.py

Open http://localhost:5000, then sign up. To use it from a phone on the same Wi-Fi, open
http://YOUR_IP:5000.

The database file (`todos.db`) is created and migrated automatically on first run and is
git-ignored. Delete it to start from scratch.

## Configuration

| Variable       | Default              | Purpose                                                    |
| -------------- | -------------------- | ---------------------------------------------------------- |
| `PORT`         | `5000`               | Port to listen on (set by Railway/Render/Heroku)           |
| `DATABASE`     | `./todos.db`         | SQLite file path                                           |
| `SECRET_KEY`   | random per boot      | Signs the session cookie. **Set this in production** — a random key logs everyone out on restart |
| `COOKIE_SECURE`| `0`                  | Set to `1` on HTTPS hosts so cookies are `Secure`          |
| `FLASK_DEBUG`  | off                  | Set to `1` locally for the reloader                        |

## API

| Method | Path                 | Auth | Purpose                                          |
| ------ | -------------------- | ---- | ------------------------------------------------ |
| GET    | `/health`            | —    | `{"status": "ok", "database": "ok"}`             |
| GET    | `/api/tasks`         | yes  | Your tasks + stats (401 when logged out)         |
| GET/POST | `/signup`          | —    | Create an account (name, password, password2)    |
| GET/POST | `/login`           | —    | Log in (name, password)                          |
| POST   | `/logout`            | yes  | Ends the session (GET returns 405)               |
| POST   | `/add`               | yes  | Add a task (`title`, `priority`, `due_date`)     |
| POST   | `/edit/<id>`         | yes  | Update title / priority / due date               |
| POST   | `/toggle/<id>`       | yes  | Flip done state                                  |
| POST   | `/delete/<id>`       | yes  | Delete a task                                    |
| POST   | `/clear-completed`   | yes  | Delete all your finished tasks                   |

## Tests

    pip install -r requirements-dev.txt
    pytest -q          # 37 passed

The suite includes the privacy tests that matter: one user cannot read, toggle, edit,
delete, or clear another user's tasks, nor see them through the API.

## Deploying to Railway

The app listens on **`$PORT`** (falling back to `5000`) behind gunicorn. Railway routes
public traffic to the port configured under **Networking → Public Networking**, and those
two ports must match. `railway.json` holds the start command and the `/health` healthcheck.

**Checklist**

1. **Variables → `PORT`** must equal your domain's target port (if the domain is on 5000,
   set `PORT=5000`).
2. **Variables → `SECRET_KEY`** = a long random string:
   `python -c "import secrets; print(secrets.token_hex(32))"`.
   Without it, a random key is generated per boot and everyone is logged out on redeploy.
3. **Variables → `COOKIE_SECURE=1`** so session cookies are only sent over HTTPS.
4. **Volume** mounted at `/data` + `DATABASE=/data/todos.db`, otherwise accounts and tasks
   are wiped on every deploy (the container filesystem is ephemeral).
5. **Deployments → View logs** should show
   `Listening at: http://0.0.0.0:<port>` matching step 1.

Existing tasks from before accounts existed are attached to the **first account created**
after deploying this version.

**Troubleshooting**

| Symptom | Cause |
| --- | --- |
| `502 Application failed to respond`, deploy **Success** | Nothing listening on the domain's target port — `PORT` ≠ target port. |
| Logged out after every deploy | `SECRET_KEY` unset (random per boot) — set it. |
| Empty list after redeploy | No volume: SQLite lives on the ephemeral container disk. |
| `400 Invalid or missing CSRF token` | A form was submitted from a stale page/tab — reload and retry. |
| `Could not use database ... falling back to` | `DATABASE` points somewhere unwritable (volume not mounted yet). |

## Roadmap
- [x] Flask app
- [x] SQLite persistence, priorities, due dates, filters and search
- [x] Test suite + `/health` endpoint
- [x] Name/password accounts with per-user privacy
- [x] CI running the tests
- [ ] Docker and Docker Compose
- [ ] Terraform
- [ ] Kubernetes
- [ ] Prometheus and Grafana monitoring
