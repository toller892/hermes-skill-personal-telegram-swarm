---
name: personal-telegram-hermes-swarm
description: Set up and operate a personal Hermes Telegram swarm with one master bot and multiple role worker bots in a private group or channel. Use when configuring a colleague-owned bot team, creating BotFather bots, wiring worker roles such as product/developer/frontend/QA/docs, running group_hermes_swarm.py, troubleshooting Telegram getUpdates conflicts, or explaining how each colleague can independently dispatch /task work without sharing machine access with Tony.
---

# Personal Telegram Hermes Swarm

## Core Model

Build a self-contained swarm owned by one colleague:

```text
Colleague Telegram group/channel
  /task@master_bot ...
      |
      v
Colleague machine runs group_hermes_swarm.py
      |
      v
Local Hermes profiles execute role TODOs
      |
      v
Worker bot identities post results back to the group
```

The colleague owns all bot tokens and all Hermes execution. Tony does not need SSH, relay, or worker bot tokens for that colleague's swarm.

## Default Team

Use this default five-bot pattern unless the user asks for another shape:

- Master bot: listens to `/task`, plans TODOs, assigns workers.
- Product bot: requirements, scope, acceptance criteria.
- Developer bot: backend, scripts, APIs, integration.
- Frontend bot: UI, HTML/CSS/JS, browser-facing work.
- QA bot: verification, tests, acceptance checks.
- Docs bot: final summary, README, release notes.

## Setup Workflow

1. Read `references/setup-guide.md` when doing full setup.
2. Create one master bot and 3-5 worker bots with `@BotFather`.
3. Add all bots to one Telegram group or channel.
4. Disable independent worker gateways in that group. Worker bots are speaking identities controlled by the master script.
5. Configure `workers.json` with each worker bot token and role.
6. Run `scripts/group_hermes_swarm.py` from the colleague's machine.
7. Test with `/task@master_bot ...`.

## Important Rules

- Only one process may call `getUpdates` for the master bot token. If Telegram returns HTTP 409, stop duplicate master processes.
- Worker bots should not independently consume bare `/task`; the master owns `/task`.
- If worker Hermes profiles all run on the same machine, paths are shared. If workers run on separate machines, paths are not shared.
- Never commit bot tokens, API keys, or `.env` files.
- If Telegram API is blocked locally, run the master script with `HTTP_PROXY` and `HTTPS_PROXY`.

## Recommended Files

When configuring a new colleague swarm, create these local files outside the skill folder:

```text
swarm/
  group_hermes_swarm.py
  workers.json
  run_swarm.sh
  .env
```

Use `scripts/group_hermes_swarm.py` as the controller script and `references/workers-template.json` as the starting worker config.

## Test Prompt

Use this in the colleague's Telegram group:

```text
/task@<master_bot_username> 请让每个 worker 做一次自检：说明自己的角色、运行位置、当前时间，并返回一条可验证结果。
```

## Troubleshooting

For setup details and common failures, read `references/setup-guide.md`.
