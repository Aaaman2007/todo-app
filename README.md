# To-Do App

A to-do list web app built with Flask and SQLite. It is the first stage of my DevOps
learning project: Docker, CI/CD, Terraform, Kubernetes, and monitoring come next.

## Features
- **Persistent tasks** stored in SQLite, so they survive restarts
- **Add, edit, complete, and delete** tasks — edit opens inline, no page reload needed to reorder
- **Priority levels** (low / normal / high) with colour-coded badges
- **Due dates** with friendly labels (`Due today`, `Due tomorrow`, `Overdue by 3d`)
- **Filters and search** — All / Active / Done, live text search, and sorting
  (newest, oldest, priority, due date)
- **Progress tracking** — completion percentage and a progress bar at the top
- **Clear completed** in one click
- **Responsive, dark-mode-aware UI** — single page, no external CSS/JS dependencies
- **Keyboard shortcuts** — `/` or `n` jumps to the input, `Esc` leaves it
- `/health` endpoint for container/Kubernetes health checks
- JSON API at `/api/tasks`

## Project structure
```
todo-app/
├── app.py                  # Flask app: routes, SQLite access, helpers
├── requirements.txt        # runtime dependencies
├── requirements-dev.txt    # + pytest
├── templates/
│   ├── index.html          # the whole UI (inline CSS + a little vanilla JS)
│   └── 404.html
└── tests/
    └── test_app.py         # 23 tests covering routes, validation and security
```

## Run locally

    git clone https://github.com/Aaman2007/todo-app.git
    cd todo-app
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python app.py

Open http://localhost:5000. To use it from a phone on the same Wi-Fi, open
http://YOUR_IP:5000.

The database file (`todos.db`) is created automatically on first run and is git-ignored.
Delete it to start with an empty list.

## Configuration

| Variable    | Default              | Purpose                                        |
| ----------- | -------------------- | ---------------------------------------------- |
| `PORT`      | `5000`               | Port the dev server listens on                 |
| `DATABASE`  | `./todos.db`         | SQLite file path (`:memory:` for tests)        |
| `SECRET_KEY`| dev placeholder      | Signs flash messages — set a real one in prod  |
| `FLASK_DEBUG` | off                | Set to `1` to enable the debug reloader        |

## API

| Method | Path                 | Returns                              |
| ------ | -------------------- | ------------------------------------ |
| GET    | `/health`            | `{"status": "ok", "database": "ok"}` |
| GET    | `/api/tasks`         | All tasks plus summary stats         |
| POST   | `/add`               | Adds a task (`title`, `priority`, `due_date`) |
| POST   | `/edit/<id>`         | Updates title / priority / due date  |
| POST   | `/toggle/<id>`       | Flips done state                     |
| POST   | `/delete/<id>`       | Deletes a task                       |
| POST   | `/clear-completed`   | Deletes every finished task          |

## Tests

    pip install -r requirements-dev.txt
    pytest -q

## Roadmap
- [x] Flask app
- [x] SQLite persistence, priorities, due dates, filters and search
- [x] Test suite + `/health` endpoint
- [ ] Docker and Docker Compose
- [ ] GitHub Actions CI/CD
- [ ] Terraform
- [ ] Kubernetes
- [ ] Prometheus and Grafana monitoring
