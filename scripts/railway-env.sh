#!/usr/bin/env bash
# Prints the environment variables the app needs on Railway, with a freshly
# generated SECRET_KEY, plus the ready-to-paste CLI command.
#
#   ./scripts/railway-env.sh              # print values + CLI command
#   ./scripts/railway-env.sh --apply      # set them with the Railway CLI
#
# Requires the Railway CLI for --apply:  npm i -g @railway/cli && railway link
set -euo pipefail

SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
PORT_TARGET="${PORT_TARGET:-5000}"

cat <<EOF
Railway -> your service -> Variables
-----------------------------------
PORT=${PORT_TARGET}
COOKIE_SECURE=1
FLASK_DEBUG=0
DATABASE=/data/todos.db
SECRET_KEY=${SECRET_KEY}

Before deploying, in Railway:
  1. Networking -> Public Networking -> target port must be ${PORT_TARGET}
     (or change PORT above to match whatever your domain already uses)
  2. Attach a Volume mounted at /data, so SQLite survives deploys

CLI equivalent
--------------
railway variables --service todo-app \\
  --set "PORT=${PORT_TARGET}" \\
  --set "COOKIE_SECURE=1" \\
  --set "FLASK_DEBUG=0" \\
  --set "DATABASE=/data/todos.db" \\
  --set "SECRET_KEY=${SECRET_KEY}"
EOF

if [ "${1:-}" = "--apply" ]; then
  echo
  echo "Applying to Railway..."
  railway variables \
    --set "PORT=${PORT_TARGET}" \
    --set "COOKIE_SECURE=1" \
    --set "FLASK_DEBUG=0" \
    --set "DATABASE=/data/todos.db" \
    --set "SECRET_KEY=${SECRET_KEY}"
  echo "Done. Redeploy for the changes to take effect: railway up"
fi
