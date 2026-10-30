"""A small agent loop: messages -> model -> approved tool -> messages."""

from dataclasses import dataclass, field
from contextlib import nullcontext
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from queue import Queue, Empty
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from shell_tool import TOOL, run_bash

ROOT = Path(__file__).resolve().parent
MAX_TOOL_ROUNDS = 20
PLUGINS = None


class AgentLimitExceeded(RuntimeError):
    pass


class AgentStopped(RuntimeError):
    pass


@dataclass(eq=False)
class Agent:
    """One loop's state. Sharing a runtime never shares a conversation."""

    id: str = "main"
    type_name: str = "main"
    system_prompt: str = ""
    messages: list = field(default_factory=list)
    tools: list | None = None
    runtime: object | None = None
    state: str = "idle"
    inbox: Queue = field(default_factory=Queue)
    stop_event: threading.Event = field(default_factory=threading.Event)
    max_turns: int = 20
    max_seconds: float | None = 600
    deadline: float | None = None
    turns: int = 0
    token_usage: dict = field(default_factory=dict)
    tokens: int = 0
    child_tokens: int = 0
    manager: object | None = None
    log_path: Path | None = None
    model: str | None = None
    report: str = ""
    failure_reason: str | None = None
    started_at: float | None = None
    process: object | None = None
    process_lock: object = field(default_factory=threading.RLock)
    managed: bool = False
    task: str = ""
    current_action: str = ""
    active_seconds: float = 0
    lock: object = field(default_factory=threading.RLock)

    def record(self, kind, payload):
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        event = {"at_utc": datetime.now(timezone.utc).isoformat(), "agent": self.id,
                 "kind": kind, "payload": payload}
        with self.lock, self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")

    def add_usage(self, result):
        with self.lock:
            self._add_usage(result)

    def _add_usage(self, result):
        usage = result.get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                self.token_usage[key] = self.token_usage.get(key, 0) + value
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        if isinstance(cached, int) and not isinstance(cached, bool):
            self.token_usage["cached_tokens"] = self.token_usage.get("cached_tokens", 0) + cached
        # Cached tokens are already part of prompt_tokens, not extra usage.
        self.tokens = self.token_usage.get("prompt_tokens", 0) + self.token_usage.get("completion_tokens", 0) + self.child_tokens

    def run(self, prompt, approve, emit, checkpoint=None, *, hidden_tools=()):
        with self.lock:
            if self.stop_event.is_set():
                if self.state not in {"failed", "stopped"}:
                    self.state = "stopped"
                return self
            self.state = "running"
            self.failure_reason = None
        self.started_at = self.started_at or time.monotonic()
        if self.deadline is None and self.max_seconds is not None:
            self.deadline = time.monotonic() + self.max_seconds
        try:
            _run_agent(self, prompt, approve, emit, checkpoint, hidden_tools=hidden_tools)
        except Exception as error:
            with self.lock:
                if not (self.stop_event.is_set() and self.state in {"failed", "stopped"}):
                    self.state = "stopped" if isinstance(error, AgentStopped) else "failed"
                    self.failure_reason = str(error) if isinstance(error, (AgentLimitExceeded, AgentStopped)) else type(error).__name__
                self.record(self.state, {"reason": self.failure_reason})
            raise
        return self


class ModelUnavailable(RuntimeError):
    """A transient model request failed; completed tool results remain valid."""


def call_model(messages, tools=None, *, model=None, deadline=None, stop_event=None):
    """Send the complete conversation to the configured model API."""
    settings = {name: os.environ.get(name, "") for name in ("BASE_URL", "API_KEY", "MODEL")}
    missing = [name for name, value in settings.items() if not value or value.startswith("replace_")]
    if missing:
        raise RuntimeError("Configure " + ", ".join(missing) + " in .env first.")
    payload = {"model": model or settings["MODEL"], "messages": messages, "max_tokens": 2048}
    if tools:
        payload["tools"] = tools
    request = Request(
        settings["BASE_URL"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + settings["API_KEY"], "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(2):
        if stop_event is not None and stop_event.is_set():
            raise AgentStopped("Stopped by the owner or session shutdown.")
        remaining = deadline - time.monotonic() if deadline is not None else 90
        if remaining <= 0:
            raise AgentLimitExceeded("max_seconds deadline exceeded")
        try:
            with urlopen(request, timeout=min(90, remaining)) as response:
                result = json.load(response)
            break
        except HTTPError as error:
            status = error.code
            error.close()
            if status not in {502, 503, 504}:
                raise RuntimeError(f"Model API returned HTTP {status}. Check the key, model, credits, or rate limits.") from None
            if attempt:
                raise ModelUnavailable(f"Model API returned HTTP {status} after one retry.") from None
        except (URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
            if attempt:
                raise ModelUnavailable("Could not reach the model API after one retry, or both requests timed out.") from None
        print("Model connection interrupted; retrying the API request once. Completed tools are not rerun.", flush=True)
        delay = min(2, max(0, deadline - time.monotonic())) if deadline is not None else 2
        if stop_event is not None:
            stop_event.wait(delay)
        else:
            time.sleep(delay)
    if result.get("error") or not result.get("choices"):
        raise RuntimeError("The model API returned an error or no choices.")
    return result


def usage_text(result):
    """Cached tokens are a subset of input tokens; absent counts stay unknown."""
    usage = result.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    return (
        f"Tokens: input={usage.get('prompt_tokens', 'not reported')}, "
        f"cached input={details.get('cached_tokens', 'not reported')}, "
        f"output={usage.get('completion_tokens', 'not reported')}"
    )


def conversation():
    prompt = (ROOT / "system_prompt.md").read_text(encoding="utf-8-sig")
    if PLUGINS is not None:
        prompt += "\n\n" + PLUGINS.skill_prompt()
        types = getattr(PLUGINS, "agent_type_prompt", None)
        if types is not None:
            prompt += "\n\n" + types()
    return [{"role": "system", "content": prompt}]


def execute_tool(call, approve, hidden_tools=(), *, worker=None):
    """Validate model-written arguments before reaching the shell tool."""
    try:
        if worker is not None and worker.stop_event.is_set():
            return {"error": "This agent has stopped; no action was started."}
        function = call["function"]
        if function["name"] in hidden_tools:
            return {"error": "This tool belongs to the interface and is unavailable to the model."}
        if worker is not None and worker.type_name != "main":
            allowed = {tool["function"]["name"] for tool in (worker.tools or [])}
            if function["name"] not in allowed:
                return {"error": "This tool is not permitted for this agent type."}
        arguments = json.loads(function["arguments"])
        if not isinstance(arguments, dict):
            return {"error": "Tool arguments must be a JSON object."}
        if function["name"] == "delegate" and worker is not None and worker.type_name == "main" and worker.manager is not None:
            if set(arguments) != {"agent", "task"}:
                return {"error": "delegate requires exactly agent and task."}
            return worker.manager.delegate(**arguments)
        if function["name"] == "subagent" and worker is not None and worker.type_name == "main" and worker.manager is not None:
            if "action" not in arguments:
                return {"error": "subagent requires an action."}
            return worker.manager.control(**arguments)
        if function["name"] != "bash":
            runtime = worker.runtime if worker is not None else PLUGINS
            if runtime is not None:
                if worker is not None and worker.type_name != "main":
                    return runtime.call_tool(function["name"], arguments, approve,
                                             cancel_event=worker.stop_event, deadline=worker.deadline)
                return runtime.call_tool(function["name"], arguments, approve)
            return {"error": "Unknown tool; only bash is available."}
        if not isinstance(arguments, dict) or set(arguments) != {"command"}:
            return {"error": "Expected exactly one argument: command."}
        if worker is not None and worker.type_name != "main" and worker.deadline is not None:
            remaining = worker.deadline - time.monotonic()
            if remaining <= 0:
                return {"error": "max_seconds deadline exceeded; command was not started."}
            return run_bash(arguments["command"], approve, timeout=min(60, remaining), worker=worker)
        if worker is not None and worker.type_name != "main":
            return run_bash(arguments["command"], approve, worker=worker)
        return run_bash(arguments["command"], approve)
    except (KeyError, TypeError, ValueError):
        return {"error": "Invalid tool arguments. Provide a JSON object with one string command."}
    except OSError:
        return {"error": "The shell could not be started or its working folder is unavailable."}


def run_turn(messages, prompt, approve, emit, checkpoint=None, *, hidden_tools=(), system_suffix="", agent_state=None, child_approve=None, main_hidden_tools=()):
    """Compatibility entry point: every interface runs an Agent object."""
    if not messages:
        messages.extend(conversation())
    worker = agent_state if agent_state is not None else Agent(max_seconds=None)
    worker.messages = messages
    worker.runtime = PLUGINS
    worker.max_turns = MAX_TOOL_ROUNDS
    worker.tools = [TOOL] + (PLUGINS.tools if PLUGINS is not None else [])
    if getattr(PLUGINS, "agent_types", None):
        from subagents import SubagentManager, DELEGATE_TOOL, SUBAGENT_TOOL
        if worker.manager is None:
            worker.manager = SubagentManager(worker, ROOT)
        worker.manager.configure(approve, child_approve or approve, emit, hidden_tools)
        worker.tools += [DELEGATE_TOOL, SUBAGENT_TOOL]
        approve = worker.manager.approve_main
    if PLUGINS is not None and messages and messages[0].get("role") == "system":
        messages[0] = conversation()[0]
        messages[0]["content"] += system_suffix
    worker.system_prompt = messages[0].get("content", "") if messages else ""
    return worker.run(prompt, approve, emit, checkpoint, hidden_tools=set(hidden_tools) | set(main_hidden_tools))


def _run_agent(worker, prompt, approve, emit, checkpoint=None, *, hidden_tools=()):
    """Shared loop; messages, tools, usage and lifecycle belong to worker."""
    checkpoint = checkpoint or (lambda messages: None)
    messages = worker.messages
    if not messages:
        messages.append({"role": "system", "content": worker.system_prompt})
    if prompt is not None:
        messages.append({"role": "user", "content": prompt})
        worker.record("message", messages[-1])
    checkpoint(messages)
    for round_number in range(worker.max_turns):
        if worker.stop_event.is_set():
            if worker.state != "failed":
                worker.state = "stopped"
            return
        if worker.deadline is not None and time.monotonic() >= worker.deadline:
            raise AgentLimitExceeded("max_seconds deadline exceeded")
        if worker.type_name != "main" and worker.turns >= worker.max_turns:
            raise AgentLimitExceeded(f"max_turns limit ({worker.max_turns})")
        pending = []
        boundary = worker.manager.lock if worker.type_name == "main" and worker.manager is not None else nullcontext()
        with boundary:
            while True:
                try:
                    pending.append(worker.inbox.get_nowait())
                except Empty:
                    break
        if pending:
            messages.append({"role": "user", "content": "\n\n".join(pending)})
            worker.record("message", messages[-1])
            checkpoint(messages)
        tools = list(worker.tools or [])
        tools = [tool for tool in tools if tool["function"]["name"] not in hidden_tools]
        worker.current_action = "model request"
        worker.record("model_call_started", {"turn": worker.turns + 1, "model": worker.model or os.environ.get("MODEL")})
        if worker.type_name != "main":
            result = call_model(messages, tools, model=worker.model, deadline=worker.deadline, stop_event=worker.stop_event)
        else:
            result = call_model(messages, tools, model=worker.model) if worker.model else call_model(messages, tools)
        worker.turns += 1
        worker.add_usage(result)
        worker.record("usage", result.get("usage") or {})
        worker.current_action = ""
        if worker.stop_event.is_set():
            if worker.state != "failed":
                worker.state = "stopped"
            return
        if worker.deadline is not None and time.monotonic() >= worker.deadline:
            raise AgentLimitExceeded("max_seconds deadline exceeded")
        if worker.runtime is not None and round_number == 0 and worker.type_name == "main":
            print("First model call: " + usage_text(result), flush=True)
        emit({"type": "usage", "text": usage_text(result), "model": result.get("model")})
        message = result["choices"][0]["message"]
        messages.append(message)  # 2. Remember the model's reply, including tool IDs.
        worker.record("message", message)
        checkpoint(messages)
        if message.get("content"):
            emit({"type": "assistant", "text": message["content"]})
        calls = message.get("tool_calls") or []
        if not calls:  # 3. Plain text ends this turn; wait for the next user message.
            with worker.lock:
                if worker.stop_event.is_set():
                    return
                worker.report = message.get("content") or ""
                if not worker.managed:
                    worker.state = "idle"
            return
        for call in calls:  # 4. Execute each tool only after the user approves it.
            worker.current_action = (call.get("function") or {}).get("name", "tool")
            try:
                output = execute_tool(call, approve, hidden_tools, worker=worker)
            finally:
                worker.current_action = ""
            messages.append({  # 5. Give the result back using the same tool-call ID.
                "role": "tool", "tool_call_id": call["id"],
                "content": json.dumps(output),
            })
            worker.record("message", messages[-1])
            checkpoint(messages)
            emit({"type": "tool_result", "result": output})
        # 6. Repeat so the model can use the results or request another command.
    with worker.lock:
        if worker.stop_event.is_set():
            return
        worker.state = "failed"
        worker.failure_reason = f"max_turns limit ({worker.max_turns})"
    worker.record("failed", {"reason": worker.failure_reason})
    emit({"type": "error", "text": f"Stopped at the {worker.max_turns}-round limit. Send a new message to continue."})


def terminal_read(prompt, *, cancel_event=None, deadline=None, draft=None):
    """One console reader; Windows TTY input can be cancelled by a child stop."""
    from subagents import CONSOLE_LOCK
    with CONSOLE_LOCK:
        if os.name != "nt" or not sys.stdin.isatty():
            return input(prompt)
        import msvcrt
        buffer = draft if draft is not None else []
        print(prompt + "".join(buffer), end="", flush=True)
        while True:
            if ((cancel_event is not None and cancel_event.is_set())
                    or (deadline is not None and time.monotonic() >= deadline)):
                print()
                return None
            if not msvcrt.kbhit():
                time.sleep(0.05)
                continue
            character = msvcrt.getwch()
            if character == "\x03":
                raise KeyboardInterrupt
            if character in {"\x00", "\xe0"}:
                msvcrt.getwch()
            elif character in {"\r", "\n"}:
                print()
                line = "".join(buffer)
                buffer.clear()
                return line
            elif character == "\b":
                if buffer:
                    buffer.pop()
                    print("\b \b", end="", flush=True)
            else:
                buffer.append(character)
                print(character, end="", flush=True)


def terminal_approve(command, *, cancel_event=None, deadline=None):
    from subagents import APPROVAL_PENDING, CONSOLE_LOCK
    APPROVAL_PENDING.set()
    try:
        with CONSOLE_LOCK:
            print("\nProposed action:\n" + command)
            answer = terminal_read("Run this action? [y/N] ", cancel_event=cancel_event, deadline=deadline)
            return bool(answer and answer.strip().lower() in {"y", "yes"})
    except EOFError:
        return False
    finally:
        APPROVAL_PENDING.clear()


def terminal_emit(event):
    if event["type"] == "tool_result":
        print(json.dumps(event["result"], indent=2))
    else:
        print(event["text"])
        if event.get("model"):
            print("Model:", event["model"])


def terminal_main():
    messages = conversation()
    worker = Agent(max_seconds=None)
    if sys.argv[1:] == ["--chat"]:
        from subagents import APPROVAL_PENDING
        print("Chat with Jasmine's Agent. Type /agents for job status, /quit to finish.")
        draft = []
        while True:
            try:
                while APPROVAL_PENDING.is_set():
                    time.sleep(0.05)
                text = terminal_read("You: ", cancel_event=APPROVAL_PENDING, draft=draft)
                if text is None:
                    continue
                prompt = text.strip()
            except EOFError:
                break
            if prompt == "/quit":
                break
            if prompt == "/agents":
                print(json.dumps(worker.manager.list() if worker.manager else {"agents": []}, indent=2))
                continue
            if prompt:
                try:
                    run_turn(messages, prompt, terminal_approve, terminal_emit, agent_state=worker)
                except RuntimeError as error:
                    print(f"Error: {error}")
    else:
        run_turn(messages, " ".join(sys.argv[1:]) or "Say hello in one sentence.", terminal_approve, terminal_emit, agent_state=worker)


def main():
    global PLUGINS
    from plugin_runtime import PluginRuntime
    with PluginRuntime(ROOT) as runtime:
        PLUGINS = runtime
        runtime.describe()
        try:
            if sys.argv[1:] == ["--telegram"]:
                from telegram_mode import TelegramMode
                path = ROOT / "settings.json"
                settings = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
                TelegramMode(runtime, auto_approve=settings.get("telegram_auto_approve", False)).run()
            else:
                terminal_main()
        finally:
            from subagents import shutdown_all
            shutdown_all()
            PLUGINS = None


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    except (RuntimeError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
