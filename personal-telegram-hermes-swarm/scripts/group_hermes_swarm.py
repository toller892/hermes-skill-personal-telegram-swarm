#!/usr/bin/env python3
"""Minimal Telegram group swarm for local Hermes.

One orchestrator bot listens for /task messages in a group. The local process
plans a todo list with Hermes, assigns items round-robin to worker bot tokens,
runs local `hermes -z` for each item, and posts results back as the worker bots.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


TELEGRAM_MESSAGE_LIMIT = 4096
LONG_TASK_PREVIEW_LIMIT = 1200
CLOUDFLARE_TASK_RE = re.compile(
    r"\b(cloudflare|workers?|wrangler|d1|r2|kv|cache api)\b",
    flags=re.IGNORECASE,
)
CF_TOKEN_RE = re.compile(r"\bcf[a-zA-Z0-9_-]{24,}\b")
CF_ACCOUNT_ID_RE = re.compile(r"\b[a-f0-9]{32}\b", flags=re.IGNORECASE)


class TelegramError(RuntimeError):
    pass


class PlannerOutputError(RuntimeError):
    pass


class HermesTimeoutError(RuntimeError):
    pass


@dataclass(frozen=True)
class Bot:
    token: str
    username: str
    first_name: str


@dataclass(frozen=True)
class Agent:
    bot: Bot
    agent_name: str
    role: str
    hermes_bin: str | None = None
    skill: str | None = None
    session: str | None = None
    model: str | None = None
    provider: str | None = None
    toolsets: str | None = None
    task_transport: str = "file"


@dataclass(frozen=True)
class TaskItem:
    title: str
    description: str
    is_full_task: bool = False


@dataclass(frozen=True)
class Assignment:
    agent: Agent
    todos: list[TaskItem]


@dataclass(frozen=True)
class TaskContext:
    text: str
    file_path: str | None = None
    is_large: bool = False


def telegram_request(
    token: str, method: str, payload: dict | None = None, attempts: int = 6
) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request_timeout = 20
    if method == "getUpdates" and isinstance(payload, dict):
        request_timeout = int(payload.get("timeout") or 0) + 10

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                body = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"Telegram HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == attempts:
                raise TelegramError(f"Telegram request failed: {exc}") from exc
            time.sleep(min(attempt * 2, 10))
    else:
        raise TelegramError(f"Telegram request failed: {last_error}")

    result = json.loads(body)
    if not result.get("ok"):
        raise TelegramError(f"Telegram API error: {result}")
    return result


def get_bot(token: str) -> Bot:
    result = telegram_request(token, "getMe")["result"]
    return Bot(
        token=token,
        username=result.get("username", ""),
        first_name=result.get("first_name", result.get("username", "bot")),
    )


def split_for_telegram(text: str) -> list[str]:
    if not text:
        return ["(empty response)"]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > TELEGRAM_MESSAGE_LIMIT:
        split_at = remaining.rfind("\n", 0, TELEGRAM_MESSAGE_LIMIT)
        if split_at < 500:
            split_at = TELEGRAM_MESSAGE_LIMIT
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()
    chunks.append(remaining)
    return chunks


def send_message(
    token: str,
    chat_id: int | str,
    text: str,
    message_thread_id: int | None = None,
) -> None:
    for chunk in split_for_telegram(text):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        telegram_request(token, "sendMessage", payload)


def get_updates(token: str, offset: int | None, timeout: int) -> list[dict]:
    payload = {
        "timeout": timeout,
        "allowed_updates": ["message", "channel_post"],
    }
    if offset is not None:
        payload["offset"] = offset
    return telegram_request(token, "getUpdates", payload).get("result", [])


def latest_offset(updates: list[dict]) -> int | None:
    if not updates:
        return None
    return max(update["update_id"] for update in updates) + 1


def run_hermes(args: argparse.Namespace, prompt: str, agent: Agent | None = None) -> str:
    if args.dry_run:
        prefix = f"dry-run Hermes output"
        if agent:
            prefix += f" from {agent.agent_name} (@{agent.bot.username})"
        return f"{prefix}:\n{prompt[:800]}"

    hermes_bin = agent.hermes_bin if agent and agent.hermes_bin else args.hermes_bin
    command = [hermes_bin]
    model = agent.model if agent and agent.model else args.model
    provider = agent.provider if agent and agent.provider else args.provider
    toolsets = agent.toolsets if agent and agent.toolsets else args.toolsets

    if model:
        command.extend(["--model", model])
    if provider:
        command.extend(["--provider", provider])
    if toolsets:
        command.extend(["--toolsets", toolsets])
    if agent and agent.session:
        command.extend(["--continue", agent.session])
    command.extend(["-z", prompt])

    try:
        completed = subprocess.run(
            command,
            cwd=args.cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.hermes_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HermesTimeoutError(
            f"Hermes did not finish within {args.hermes_timeout} seconds"
        ) from exc
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"Hermes failed: {detail}")
    return stdout or stderr or "(Hermes returned no text)"


def strip_task_command(text: str, orchestrator_username: str) -> str | None:
    pattern = rf"^/(task|assign|todo)(@{re.escape(orchestrator_username)})?\s*(.*)$"
    match = re.match(pattern, text.strip(), flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    task = match.group(3).strip()
    leading_mention = f"@{orchestrator_username}"
    if task.lower().startswith(leading_mention.lower()):
        task = task[len(leading_mention) :].lstrip(" \t\r\n:：,，")
    return task


def parse_tasks(raw: str, max_tasks: int) -> list[TaskItem]:
    json_text = raw.strip()
    if "```" in json_text:
        fenced = re.search(r"```(?:json)?\s*(.*?)```", json_text, flags=re.DOTALL)
        if fenced:
            json_text = fenced.group(1).strip()
    if not json_text.startswith("["):
        start = json_text.find("[")
        end = json_text.rfind("]")
        if start >= 0 and end > start:
            json_text = json_text[start : end + 1]

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise PlannerOutputError(f"planner did not return valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise PlannerOutputError("planner JSON must be an array")

    tasks = []
    for item in data:
        if not isinstance(item, dict):
            raise PlannerOutputError("each planner item must be an object")
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not title or not description:
            raise PlannerOutputError("each planner item needs title and description")
        tasks.append(TaskItem(title=title[:80], description=description))

    if not tasks:
        raise PlannerOutputError("planner returned no tasks")
    return tasks[:max_tasks]


def full_task(task: str) -> TaskItem:
    return TaskItem(title="完整任务", description=task, is_full_task=True)


def deterministic_tasks(task: str, worker_count: int, max_tasks: int) -> list[TaskItem]:
    if worker_count <= 1:
        return [
            TaskItem(
                title="执行完整任务",
                description="读取原始任务，完成可执行交付物，并报告路径、命令、结果和阻塞项。",
            )
        ]

    tasks = [
        TaskItem(
            title="实现与交付",
            description=(
                "读取原始任务，完成主要实现、部署、文件创建、脚本、页面或集成工作。"
                "必须返回真实产物路径、URL、资源名、关键命令和已完成范围。"
            ),
        ),
        TaskItem(
            title="验证与总结",
            description=(
                "读取原始任务和实现结果，执行验收检查、测试、回读或浏览器验证。"
                "输出通过项、失败项、未验证项、风险和最终可复现步骤。"
            ),
        ),
    ]
    if worker_count > 2 and max_tasks > 2:
        tasks.insert(
            1,
            TaskItem(
                title="体验与文档检查",
                description="检查页面体验、使用说明、边界情况和交付说明是否满足原始任务。",
            ),
        )
    return tasks[:max_tasks]


def plan_tasks(args: argparse.Namespace, task: str, worker_count: int) -> tuple[list[TaskItem], str]:
    if worker_count <= 1:
        return deterministic_tasks(task, worker_count, 1), "single-worker-direct"

    target_tasks = max(worker_count, worker_count * args.todos_per_worker)
    max_tasks = max(worker_count, min(args.max_tasks, target_tasks))
    if args.dry_run:
        return (
            [
                TaskItem("需求澄清", f"确认目标、输出路径和验收标准：{task}"),
                TaskItem("核心实现", "完成主要交付物或主要研究结论。"),
                TaskItem("体验打磨", "检查可用性、文本说明和边界情况。"),
                TaskItem("验收总结", "基于真实产物检查功能、路径和使用方式。"),
            ][:max_tasks],
            "dry-run",
        )

    prompt = (
        "你是 Telegram 多 agent 调度器里的 planner，只能规划，禁止执行任务。"
        "不要创建、修改、读取或删除文件；不要调用工具；不要声称任务已经完成。"
        f"把下面的群聊任务拆成 {worker_count} 到 {max_tasks} 个可并行执行的 TODO。"
        "只输出 JSON 数组，不要 Markdown，不要解释，不要任何前后缀文本。"
        "每项必须是 {\"title\":\"短标题\",\"description\":\"清晰的执行说明\"}。"
        "description 必须描述要做什么，不要写完成报告。\n\n"
        f"任务：\n{task}"
    )
    try:
        raw = run_hermes(args, prompt)
        return parse_tasks(raw, max_tasks), "planned"
    except Exception as exc:
        print(f"Planner fallback to deterministic split: {exc}", file=sys.stderr, flush=True)
        return deterministic_tasks(task, worker_count, max_tasks), "planner-fallback"


def format_todo_list(todos: list[TaskItem]) -> str:
    lines = []
    for index, item in enumerate(todos, start=1):
        lines.append(f"{index}. {item.title}\n   {item.description}")
    return "\n".join(lines)


def task_preview(text: str) -> str:
    if len(text) <= LONG_TASK_PREVIEW_LIMIT:
        return text
    return text[:LONG_TASK_PREVIEW_LIMIT].rstrip() + "\n\n...[原始任务较长，完整内容见任务文件]..."


def format_task_context(task_context: TaskContext, agent: Agent) -> str:
    if task_context.file_path and agent.task_transport != "inline":
        return (
            f"原始完整任务已保存到本机文件：{task_context.file_path}\n"
            "请先读取该文件，再按你的 TODO 执行。"
            "如果你无法访问这个路径，请明确说明无法读取原始任务文件，不要编造执行结果。\n\n"
            f"任务摘录：\n{task_preview(task_context.text)}"
        )
    return f"总任务：\n{task_context.text}"


def execute_assignment(args: argparse.Namespace, task_context: TaskContext, assignment: Assignment) -> str:
    todo_list = format_todo_list(assignment.todos)
    skill_line = ""
    if assignment.agent.skill:
        skill_line = f"执行前请使用 ${assignment.agent.skill} skill，并遵守该 skill 的输出格式和边界。\n"
    prompt = (
        f"你是一个被调度到 Telegram 群里的本地 Hermes 子 agent，名称是 {assignment.agent.agent_name}。"
        f"你的角色设定：{assignment.agent.role}\n\n"
        f"{skill_line}"
        "请完成分配给你的 TODO list，并用中文给出简洁、可直接贴回群里的结果。"
        "回复时按 TODO 编号逐项说明：完成 / 部分完成 / 阻塞，以及关键产出。"
        "如果任务要求创建或修改文件，完成后必须基于真实文件状态报告路径和功能，不要编造未验证的特性。"
        "如果无法完全完成，请明确说明缺口和下一步。\n\n"
        f"{format_task_context(task_context, assignment.agent)}\n\n"
        f"你的 TODO list：\n{todo_list}"
    )
    return run_hermes(args, prompt, assignment.agent)


def build_assignments(tasks: list[TaskItem], workers: list[Agent]) -> list[Assignment]:
    if len(tasks) == 1 and tasks[0].is_full_task:
        worker = workers[0]
        return [Assignment(worker, tasks)]

    grouped: list[list[TaskItem]] = [[] for _ in workers]
    for index, item in enumerate(tasks):
        grouped[index % len(workers)].append(item)
    return [
        Assignment(worker, todos)
        for worker, todos in zip(workers, grouped)
        if todos
    ]


def format_assignments(assignments: list[Assignment]) -> str:
    if len(assignments) == 1 and len(assignments[0].todos) == 1 and assignments[0].todos[0].is_full_task:
        worker = assignments[0].agent
        return f"收到任务，直接分配完整任务给 {worker.agent_name} (@{worker.bot.username})。"

    lines = ["收到任务，已按 bot 分配 TODO list："]
    for assignment in assignments:
        lines.append(f"\n{assignment.agent.agent_name} (@{assignment.agent.bot.username})")
        for index, item in enumerate(assignment.todos, start=1):
            lines.append(f"{index}. {item.title}")
    return "\n".join(lines)


def save_large_task(args: argparse.Namespace, task_text: str) -> str | None:
    if len(task_text) <= args.large_task_threshold:
        return None
    task_dir = args.task_dir or os.path.join(args.cwd, "tasks")
    os.makedirs(task_dir, mode=0o700, exist_ok=True)
    file_path = os.path.join(task_dir, f"task_{time.strftime('%Y%m%d_%H%M%S')}.md")
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(task_text)
        file.write("\n")
    os.chmod(file_path, 0o600)
    return file_path


def cloudflare_preflight(task_text: str) -> list[str]:
    if not CLOUDFLARE_TASK_RE.search(task_text):
        return []

    missing: list[str] = []
    has_token = bool(os.environ.get("CLOUDFLARE_API_TOKEN") or CF_TOKEN_RE.search(task_text))
    has_account = bool(
        os.environ.get("CLOUDFLARE_ACCOUNT_ID") or CF_ACCOUNT_ID_RE.search(task_text)
    )
    has_wrangler = bool(shutil.which("wrangler") or shutil.which("npx"))

    if not has_token:
        missing.append("Cloudflare API token（可放在环境变量 CLOUDFLARE_API_TOKEN 或任务正文中）")
    if not has_account:
        missing.append("Cloudflare account id（可放在环境变量 CLOUDFLARE_ACCOUNT_ID 或任务正文中）")
    if not has_wrangler:
        missing.append("wrangler 或 npx（用于部署 Cloudflare Workers）")
    return missing


def friendly_worker_error(agent: Agent, exc: Exception, timeout: int) -> str:
    if isinstance(exc, HermesTimeoutError):
        return (
            f"{agent.agent_name} (@{agent.bot.username}) 执行超时。\n"
            f"当前 worker 超时时间是 {timeout} 秒。任务可能超过该 worker 能力、外部服务响应较慢，"
            "或缺少必要工具/权限。\n"
            "已停止本次 worker 子进程。建议检查凭据、网络、部署工具，并把大型任务拆成实现与验证阶段重试。"
        )

    detail = str(exc).strip()
    if len(detail) > 1200:
        detail = detail[:1200].rstrip() + "\n...[错误信息已截断]..."
    return f"{agent.agent_name} (@{agent.bot.username}) 执行失败：{detail}"


def handle_task(
    args: argparse.Namespace,
    orchestrator: Bot,
    workers: list[Agent],
    chat_id: int | str,
    thread_id: int | None,
    task_text: str,
) -> None:
    if not task_text:
        send_message(
            orchestrator.token,
            chat_id,
            "用法：/task 你要分配的任务\n例如：/task 帮我设计一个 10 人 agent 带练任务",
            thread_id,
        )
        return

    missing = cloudflare_preflight(task_text)
    if missing:
        send_message(
            orchestrator.token,
            chat_id,
            "收到 Cloudflare 相关任务，但执行前检查未通过，暂不分配给 worker 空跑。\n缺少：\n- "
            + "\n- ".join(missing),
            thread_id,
        )
        return

    task_file = save_large_task(args, task_text)
    task_context = TaskContext(
        text=task_text,
        file_path=task_file,
        is_large=task_file is not None,
    )

    if task_context.is_large:
        send_message(
            orchestrator.token,
            chat_id,
            "收到，这是大型任务，已进入 project mode。\n"
            f"原始任务已保存：{task_context.file_path}\n"
            "接下来会按 worker 角色分工执行；如果 planner 无法稳定拆 JSON，会使用内置的实现/验证分工。",
            thread_id,
        )

    if len(workers) == 1:
        send_message(orchestrator.token, chat_id, "收到，当前只有 1 个 worker，直接分配完整任务...", thread_id)
    else:
        send_message(orchestrator.token, chat_id, "收到，正在拆 TODO 并分配给 worker bot...", thread_id)

    tasks, plan_mode = plan_tasks(args, task_text, len(workers))
    if plan_mode == "planner-fallback":
        send_message(
            orchestrator.token,
            chat_id,
            "planner 没有返回合法 TODO JSON，已使用内置实现/验证分工继续处理，避免把完整长任务塞给单个 worker。",
            thread_id,
        )
    assignments = build_assignments(tasks, workers)
    send_message(orchestrator.token, chat_id, format_assignments(assignments), thread_id)

    for assignment in assignments:
        worker = assignment.agent
        assignment_title = "完整任务" if assignment.todos[0].is_full_task else f"{len(assignment.todos)} 个 TODO"
        send_message(
            orchestrator.token,
            chat_id,
            f"分配给 {worker.agent_name} (@{worker.bot.username})：{assignment_title}",
            thread_id,
        )
        try:
            result = execute_assignment(args, task_context, assignment)
            send_message(
                worker.bot.token,
                chat_id,
                f"{worker.agent_name} 完成 TODO list\n\n{result}",
                thread_id,
            )
        except Exception as exc:
            send_message(
                orchestrator.token,
                chat_id,
                friendly_worker_error(worker, exc, args.hermes_timeout),
                thread_id,
            )

    send_message(orchestrator.token, chat_id, "本轮任务处理完成。", thread_id)


def parse_worker_tokens() -> list[str]:
    raw = os.environ.get("WORKER_BOT_TOKENS") or os.environ.get("WORKER_BOT_TOKEN")
    if not raw:
        return []
    return [token.strip() for token in raw.split(",") if token.strip()]


def env_or_literal(spec: dict, key: str, env_key: str | None = None) -> str | None:
    if env_key and spec.get(env_key):
        value = os.environ.get(str(spec[env_key]))
        if value:
            return value
    value = spec.get(key)
    if value is None:
        return None
    return str(value)


def load_worker_specs(args: argparse.Namespace) -> list[dict]:
    if args.workers_config:
        with open(args.workers_config, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise ValueError("--workers-config must be a JSON array")
        return data

    raw_specs = os.environ.get("WORKER_BOT_SPECS")
    if raw_specs:
        data = json.loads(raw_specs)
        if not isinstance(data, list):
            raise ValueError("WORKER_BOT_SPECS must be a JSON array")
        return data

    return [{"token": token} for token in parse_worker_tokens()]


def build_workers(args: argparse.Namespace) -> list[Agent]:
    agents: list[Agent] = []
    for index, spec in enumerate(load_worker_specs(args), start=1):
        token = env_or_literal(spec, "token", "token_env")
        if not token:
            raise ValueError(f"Worker spec #{index} is missing token or token_env")

        bot = get_bot(token)
        agent_name = str(spec.get("agent_name") or spec.get("name") or bot.first_name)
        role = str(
            spec.get("role")
            or "通用执行型子 agent，负责完成被分配的具体任务并给出可交付结果。"
        )
        agents.append(
            Agent(
                bot=bot,
                agent_name=agent_name,
                role=role,
                hermes_bin=env_or_literal(spec, "hermes_bin"),
                skill=env_or_literal(spec, "skill"),
                session=env_or_literal(spec, "session"),
                model=env_or_literal(spec, "model"),
                provider=env_or_literal(spec, "provider"),
                toolsets=env_or_literal(spec, "toolsets"),
                task_transport=str(spec.get("task_transport") or "file"),
            )
        )
    return agents


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local Hermes-backed Telegram group swarm."
    )
    parser.add_argument("--hermes-bin", default="hermes")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--model")
    parser.add_argument("--provider")
    parser.add_argument("--toolsets")
    parser.add_argument("--poll-timeout", type=int, default=30)
    parser.add_argument("--hermes-timeout", type=int, default=240)
    parser.add_argument("--large-task-threshold", type=int, default=2000)
    parser.add_argument("--task-dir")
    parser.add_argument("--max-tasks", type=int, default=5)
    parser.add_argument("--todos-per-worker", type=int, default=2)
    parser.add_argument("--workers-config")
    parser.add_argument("--no-drop-pending", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--allow-telegram-token-fallback",
        action="store_true",
        help=(
            "Legacy mode only: use TELEGRAM_BOT_TOKEN when "
            "ORCHESTRATOR_BOT_TOKEN is missing."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    orchestrator_token = os.environ.get("ORCHESTRATOR_BOT_TOKEN")
    if not orchestrator_token and args.allow_telegram_token_fallback:
        orchestrator_token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not orchestrator_token:
        print(
            "Missing ORCHESTRATOR_BOT_TOKEN. Refusing to fall back to "
            "TELEGRAM_BOT_TOKEN by default so an existing Hermes Telegram bot "
            "is not accidentally reused. Set ORCHESTRATOR_BOT_TOKEN to the new "
            "swarm master bot token.",
            file=sys.stderr,
        )
        return 2

    try:
        workers = build_workers(args)
    except Exception as exc:
        print(f"Failed to load worker specs: {exc}", file=sys.stderr)
        return 2

    orchestrator = get_bot(orchestrator_token)
    if not workers:
        print(
            "Missing workers. Set WORKER_BOT_TOKEN, WORKER_BOT_TOKENS, "
            "WORKER_BOT_SPECS, or --workers-config.",
            file=sys.stderr,
        )
        return 2

    print(f"Orchestrator: @{orchestrator.username}", flush=True)
    print(
        "Workers: "
        + ", ".join(f"{worker.agent_name} (@{worker.bot.username})" for worker in workers),
        flush=True,
    )

    offset = None
    if not args.no_drop_pending:
        pending = get_updates(orchestrator.token, offset=None, timeout=0)
        offset = latest_offset(pending)
        if offset is not None:
            print(f"Dropped {len(pending)} pending update(s).", flush=True)

    print("Group swarm is running. Use /task in the group. Press Ctrl+C to stop.", flush=True)
    while True:
        try:
            updates = get_updates(orchestrator.token, offset=offset, timeout=args.poll_timeout)
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message") or update.get("channel_post")
                if not message:
                    continue

                sender = message.get("from") or {}
                if sender.get("is_bot"):
                    continue

                text = message.get("text")
                if not text:
                    continue

                task_text = strip_task_command(text, orchestrator.username)
                if task_text is None:
                    continue

                chat_id = message["chat"]["id"]
                thread_id = message.get("message_thread_id")
                print(f"Task from chat {chat_id}: {task_text[:100]}", flush=True)
                handle_task(args, orchestrator, workers, chat_id, thread_id, task_text)
        except KeyboardInterrupt:
            print("\nStopped.", flush=True)
            return 0
        except Exception as exc:
            print(f"Loop error: {exc}", file=sys.stderr, flush=True)
            time.sleep(3)


if __name__ == "__main__":
    raise SystemExit(main())
