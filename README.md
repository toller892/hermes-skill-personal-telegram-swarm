# Personal Telegram Hermes Swarm

Open-source Hermes/Codex skill for setting up an isolated colleague-owned Telegram bot team:

- one master bot that listens to `/task`
- two worker bots for developer and QA roles
- one local `group_hermes_swarm.py` controller on the colleague's machine

This pattern lets every operator run their own mini development team in their own Telegram group without sharing SSH access, relay access, or bot tokens with an external coordinator.

It also works on machines that already have a Hermes Telegram bot configured. The existing bot, gateway, profiles, and config stay untouched; the swarm uses a new master/developer/QA bot set and a separate working directory.

## Install

```bash
git clone https://github.com/toller892/hermes-skill-personal-telegram-swarm.git
mkdir -p ~/.hermes/skills
cp -R hermes-skill-personal-telegram-swarm/personal-telegram-hermes-swarm ~/.hermes/skills/
```

If you also use Codex directly:

```bash
mkdir -p ~/.codex/skills
cp -R hermes-skill-personal-telegram-swarm/personal-telegram-hermes-swarm ~/.codex/skills/
```

## Use

Ask Hermes/Codex to use the skill:

```text
Use $personal-telegram-hermes-swarm to set up my own Telegram Hermes swarm.
```

The setup guide is in:

```text
personal-telegram-hermes-swarm/references/setup-guide.md
```

## Contents

- `personal-telegram-hermes-swarm/SKILL.md`: skill instructions
- `personal-telegram-hermes-swarm/scripts/group_hermes_swarm.py`: reusable Telegram swarm controller
- `personal-telegram-hermes-swarm/references/workers-template.json`: default worker config
- `personal-telegram-hermes-swarm/references/setup-guide.md`: detailed setup guide

## Security

Never commit Telegram bot tokens or API keys. Keep `.env` private. Each colleague owns their own bot tokens and their own Hermes execution environment. Do not reuse an existing Hermes gateway bot as the swarm master; create a new master bot and set it with `ORCHESTRATOR_BOT_TOKEN`.

## License

MIT
