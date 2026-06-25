# Copy-Paste Prompts For Colleagues

Use these prompts with each colleague's own Hermes. The colleague only needs one cloud/server Hermes machine.

## Prompt 1: Before Bot Tokens

Paste this into the colleague's Hermes first. Replace `<COLLEAGUE_SLUG>` with `windy`, `lunar`, `yongcheng`, `leo`, or `rachel_lu`.

```text
你现在要帮我配置一套个人 Telegram Hermes swarm。

目标：
我只使用一台云端/本机 Hermes，不接入 Tony 的主控。
我会在自己的 Telegram 群里拉入 1 个 master bot 和 5 个 worker bots。
master bot 接收 /task，worker bots 分别扮演产品、开发、前端、测试、文档角色。

请使用这个 skill：
https://github.com/toller892/hermes-skill-personal-telegram-swarm

我的名字 slug 是：<COLLEAGUE_SLUG>

请先不要配置文件，不要启动服务。
第一步只需要给我生成 BotFather 里需要创建的 bot 清单，并告诉我每个 bot 创建完成后要把 token 填到哪个环境变量。

bot 命名请用：
<COLLEAGUE_SLUG>_hermes_master_bot
<COLLEAGUE_SLUG>_product_bot
<COLLEAGUE_SLUG>_developer_bot
<COLLEAGUE_SLUG>_frontend_bot
<COLLEAGUE_SLUG>_qa_bot
<COLLEAGUE_SLUG>_docs_bot

如果 BotFather 提示 username 被占用，请让我在末尾加 `_2026_bot` 或 `_team_bot`。

输出要求：
1. 给出我要发给 @BotFather 的创建清单。
2. 给出 token 到环境变量的对应关系。
3. 最后让我把 6 个 token 按固定格式发给你，等待我下一步输入。

注意：
Telegram Bot API 不能直接创建普通 bot，必须通过 @BotFather 创建。
不要让我把 token 发到 Telegram 群里。
不要编造 token。
```

## Prompt 2: After BotFather Tokens Are Ready

Paste this into the colleague's Hermes after replacing the placeholders.

```text
你现在要帮我把个人 Telegram Hermes swarm 真实配置并启动起来。

请全程执行，不要只给说明。
如果遇到必须我手工操作的步骤，再停下来明确告诉我。

我的 swarm skill：
https://github.com/toller892/hermes-skill-personal-telegram-swarm

我的配置：
COLLEAGUE_SLUG=<COLLEAGUE_SLUG>

ORCHESTRATOR_BOT_TOKEN=<master_bot_token>
WORKER_PRODUCT_BOT_TOKEN=<product_bot_token>
WORKER_DEVELOPER_BOT_TOKEN=<developer_bot_token>
WORKER_FRONTEND_BOT_TOKEN=<frontend_bot_token>
WORKER_QA_BOT_TOKEN=<qa_bot_token>
WORKER_DOCS_BOT_TOKEN=<docs_bot_token>

请按以下流程执行：

1. 检查当前机器是否有 git、python3、screen、hermes。
   - 如果缺少 git/screen，请尝试安装或告诉我需要安装什么。
   - 如果缺少 hermes，请停下来告诉我 Hermes 未安装，先不要继续。

2. 安装 skill：
   - clone https://github.com/toller892/hermes-skill-personal-telegram-swarm 到临时目录或 ~/hermes_swarm_skill。
   - mkdir -p ~/.hermes/skills
   - 把 personal-telegram-hermes-swarm 复制到 ~/.hermes/skills/

3. 创建工作目录：
   - mkdir -p ~/hermes_swarm
   - 从 skill 中复制 scripts/group_hermes_swarm.py 到 ~/hermes_swarm/group_hermes_swarm.py
   - 从 skill 中复制 references/workers-template.json 到 ~/hermes_swarm/workers.json
   - chmod +x ~/hermes_swarm/group_hermes_swarm.py

4. 创建 ~/hermes_swarm/.env：
   - 写入上面的 6 个 token。
   - chmod 600 ~/hermes_swarm/.env
   - 不要在最终回复里完整打印 token，只能用前 6 位和后 4 位脱敏展示。

5. 创建 ~/hermes_swarm/run_swarm.sh：
   内容要求：
   - cd 到 ~/hermes_swarm
   - set -a; . ./.env; set +a
   - 执行 ./group_hermes_swarm.py
   - --workers-config ./workers.json
   - --hermes-bin 使用 command -v hermes 的绝对路径
   - --max-tasks 6
   - --todos-per-worker 2
   - --hermes-timeout 420
   然后 chmod +x run_swarm.sh

6. 验证：
   - hermes -z "只回复 ok"
   - 用每个 token 调 Telegram getMe，确认 6 个 bot 都有效。输出 bot username，不要输出完整 token。
   - python3 -m json.tool ~/hermes_swarm/workers.json 验证 JSON。

7. 启动：
   - 如果已有旧的 group_hermes_swarm.py 进程，先提示并清理旧进程，避免 Telegram HTTP 409。
   - 使用 screen 后台启动：
     screen -dmS hermes_swarm ./run_swarm.sh
   - 检查 screen -ls
   - 等待 10 秒，查看启动日志，确认出现：
     Orchestrator: @...
     Workers: ...
     Group swarm is running.

8. 最终回复请给我：
   - master bot username
   - worker bot usernames
   - 工作目录路径
   - screen 名称
   - Telegram 群里应该发送的测试命令：
     /task@<master_bot_username> 请让每个 worker 做一次自检：说明自己的角色、运行位置、当前时间，并返回一条可验证结果。

安全要求：
不要把 token 写入 git。
不要把完整 token 打印到终端最终汇报。
不要运行 worker bot 的独立 Telegram gateway；worker bot 在这个 swarm 中只是发言身份，/task 由 master bot 统一处理。
```

## Slugs

```text
windy
lunar
yongcheng
leo
rachel_lu
```
