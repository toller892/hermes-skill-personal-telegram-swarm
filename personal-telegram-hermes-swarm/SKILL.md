---
name: personal-telegram-hermes-swarm
description: Set up and operate an isolated personal Hermes Telegram swarm with one new master bot and two role worker bots in a private group or channel. Use when configuring a self-contained three-bot team, creating BotFather bots, wiring developer and QA workers, running group_hermes_swarm.py, protecting an existing Hermes Telegram bot/gateway from changes, troubleshooting Telegram getUpdates conflicts, or explaining how each operator can independently dispatch /task work from their own Hermes environment.
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
Hermes workers/profiles execute role TODOs
      |
      v
Controller posts results with worker bot tokens
```

The operator owns all bot tokens and all Hermes execution. No external central controller is required for this swarm.
Only the swarm master bot listens to Telegram updates through `group_hermes_swarm.py`. Worker bots do not run gateways; they are speaking identities used by the controller through Telegram `sendMessage`.

If the operator already has a Hermes Telegram bot, leave it untouched. Create a separate new master/developer/QA bot set for this swarm and keep all swarm files in an isolated working directory.

## Default Team

Use this default three-bot pattern unless the user asks for another shape:

- Master bot: listens to `/task`, plans TODOs, assigns workers.
- Developer bot: requirements refinement, implementation, backend/frontend/scripts, integration, and reproducible commands.
- QA bot: verification, tests, acceptance checks, final summary, and unverified-risk notes.

## Setup Workflow

1. Read `references/setup-guide.md` when doing full setup.
2. Create one new master bot and two new worker bots with `@BotFather`.
3. Add all bots to one Telegram group or channel.
4. Run only the swarm controller process. Do not run independent worker bot gateways.
5. Configure `workers.json` with each worker bot token and role.
6. Run `scripts/group_hermes_swarm.py` from the colleague's machine.
7. Test with `/task@master_bot ...`.

## Important Rules

- Existing Hermes Telegram bots, gateways, profiles, and config files are out of scope. Do not modify them, stop them, or reuse their tokens for this swarm.
- Do not run `hermes gateway stop`, `hermes gateway start`, `hermes gateway restart`, or `hermes gateway setup` during swarm setup.
- Keep swarm files in a dedicated directory such as `~/hermes_swarm_<slug>`, not inside an existing Hermes gateway/profile directory.
- Require `ORCHESTRATOR_BOT_TOKEN` for the new swarm master. Do not rely on an inherited `TELEGRAM_BOT_TOKEN`.
- Only one process may call `getUpdates` for the new swarm master bot token. If Telegram returns HTTP 409, stop duplicate swarm controller processes for that new master.
- Worker bot tokens are send-only identities. They should not independently consume bare `/task`; the master owns `/task`.
- If worker Hermes profiles all run on the same machine, paths are shared. If workers run on separate machines, paths are not shared.
- Long tasks enter project mode: the master saves the original task under `tasks/` and assigns workers a file path plus their TODOs. Use worker `"task_transport": "inline"` only when a worker cannot read the master's filesystem.
- Never commit bot tokens, API keys, or `.env` files.
- If Telegram API is blocked locally, run the master script with `HTTP_PROXY` and `HTTPS_PROXY`.

## Recommended Files

When configuring a new colleague swarm, create these local files outside the skill folder:

```text
~/hermes_swarm_<slug>/
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
