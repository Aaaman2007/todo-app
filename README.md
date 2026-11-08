
# To-Do App

A simple to-do list web app built with Flask. It is the first stage of my DevOps learning project: Docker, CI/CD, Terraform, Kubernetes, and monitoring come next.

## Features
- Add and delete tasks
- Mobile-friendly page
- `/health` endpoint for health checks

## Run locally

    git clone https://github.com/Aaman2007/todo-app.git
    cd todo-app
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python app.py

Open http://localhost:5000. To use it from a phone on the same Wi-Fi, open http://YOUR_IP:5000.

## Roadmap
- [x] Flask app
- [ ] Docker and Docker Compose
- [ ] GitHub Actions CI/CD
- [ ] Terraform
- [ ] Kubernetes
- [ ] Prometheus and Grafana monitoring
EOF