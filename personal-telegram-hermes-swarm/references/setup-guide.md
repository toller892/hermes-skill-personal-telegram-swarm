# Setup Guide

This guide creates one colleague-owned Telegram Hermes swarm.

## 1. Create Bots

Use `@BotFather` to create:

- `<name>_hermes_master_bot`
- `<name>_product_bot`
- `<name>_developer_bot`
- `<name>_frontend_bot`
- `<name>_qa_bot`
- `<name>_docs_bot`

Put every token in a private `.env` file. Do not commit it.

## 2. Create Telegram Group

Create a Telegram group or channel for this colleague's bot team. Add all bots.

Recommended:

- Use `/task@master_bot ...` for testing.
- Do not run separate Hermes gateways for worker bots in the group.
- If worker gateways are running for private chat, set `TELEGRAM_REQUIRE_MENTION=true`.

## 3. Prepare Local Files

Create a local working directory:

```bash
mkdir -p ~/hermes_swarm
cd ~/hermes_swarm
cp /path/to/personal-telegram-hermes-swarm/scripts/group_hermes_swarm.py .
cp /path/to/personal-telegram-hermes-swarm/references/workers-template.json workers.json
chmod +x group_hermes_swarm.py
```

Create `.env`:

```bash
cat > .env <<'EOF'
ORCHESTRATOR_BOT_TOKEN=<master_bot_token>
WORKER_PRODUCT_BOT_TOKEN=<product_bot_token>
WORKER_DEVELOPER_BOT_TOKEN=<developer_bot_token>
WORKER_FRONTEND_BOT_TOKEN=<frontend_bot_token>
WORKER_QA_BOT_TOKEN=<qa_bot_token>
WORKER_DOCS_BOT_TOKEN=<docs_bot_token>
EOF
chmod 600 .env
```

## 4. Configure Workers

Edit `workers.json`. Each worker can use:

- the same `hermes` command with role instructions, or
- a profile wrapper such as `hermes --profile frontend`.
- an optional `"skill": "<skill-name>"` field if that worker has a separate role skill installed.

For a simple MVP, leave `hermes_bin` as `hermes` and let the role prompt guide behavior.

If using profiles, create small wrapper scripts:

```bash
#!/usr/bin/env bash
exec hermes --profile frontend "$@"
```

Then set `"hermes_bin": "/absolute/path/to/frontend_wrapper"`.

## 5. Run The Master

Create `run_swarm.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a
. ./.env
set +a

exec ./group_hermes_swarm.py \
  --workers-config ./workers.json \
  --hermes-bin "$(command -v hermes)" \
  --max-tasks 6 \
  --todos-per-worker 2 \
  --hermes-timeout 420
```

Run it:

```bash
chmod +x run_swarm.sh
./run_swarm.sh
```

For background mode:

```bash
screen -dmS hermes_swarm ./run_swarm.sh
screen -ls
```

## 6. Telegram Test

In the group:

```text
/task@<master_bot_username> 请让每个 worker 做一次自检：说明自己的角色、运行位置、当前时间，并返回一条可验证结果。
```

Expected result:

- Master bot receives the task.
- Master bot posts a TODO distribution.
- Worker bot identities post their completion reports.
- Master bot posts final completion.

## Common Failures

### HTTP 409 Conflict

Meaning: two processes are calling `getUpdates` for the same master bot token.

Fix:

```bash
ps auxww | grep group_hermes_swarm.py
kill <old_pid>
```

### Worker Says Unknown Command

Meaning: a worker's independent Telegram gateway is also listening in the group.

Fix: stop that worker gateway for group mode, or set it to require mentions. The master script should be the only `/task` owner.

### Planner Falls Back

Meaning: local `hermes` command failed or returned invalid JSON.

Fix: verify:

```bash
command -v hermes
hermes -z "只回复 ok"
```

Use `--hermes-bin /absolute/path/to/hermes` if needed.

### Telegram API Timeout

If Telegram is unreachable from the local network, set proxy variables:

```bash
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897
```

### Same Path But Different Machines

If workers run on separate machines, `/home/ubuntu/result.txt` on each machine is a different file. Use a shared repo/storage if the task needs a single shared artifact.
