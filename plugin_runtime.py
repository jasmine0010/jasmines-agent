"""Discover Claude-style plugins and keep their stdio MCP sessions alive.

The existing harness has synchronous terminal and web workers. One background
asyncio loop owns the SDK sessions, so both interfaces can call the same small
synchronous adapter without starting a server for every model tool call.
"""

import asyncio
from concurrent.futures import TimeoutError as CallTimeout
from contextlib import AsyncExitStack
import json
import os
from pathlib import Path
import re
import shutil
import threading

from mcp import Client, StdioServerParameters
import yaml
from agent_types import AgentTypeError, load_agent_types, type_prompt
from shell_tool import TOOL

VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
TOOL_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PluginConfigurationError(RuntimeError):
    pass


def expand(value, root, environment):
    """Expand argv/env values without evaluating any shell text."""
    if isinstance(value, list):
        return [expand(item, root, environment) for item in value]
    if isinstance(value, dict):
        return {key: expand(item, root, environment) for key, item in value.items()}
    if not isinstance(value, str):
        return value

    def replace(match):
        name = match.group(1)
        if name == "CLAUDE_PLUGIN_ROOT":
            return str(root.resolve())
        if not environment.get(name):
            raise PluginConfigurationError(f"Set {name} locally in .env before loading this plugin.")
        return environment[name]
    return VARIABLE.sub(replace, value)


def discover(root, environment):
    """Read manifests and skill metadata; skill bodies stay out of the prompt."""
    plugins, servers, skills = [], [], []
    for folder in sorted((Path(root) / "plugins").glob("*")):
        manifest = folder / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            continue
        metadata = json.loads(manifest.read_text(encoding="utf-8-sig"))
        name = metadata.get("name")
        if not isinstance(name, str) or not TOOL_NAME.fullmatch(name):
            raise PluginConfigurationError(f"Invalid plugin name in {manifest.name}.")
        plugins.append(name)
        config = folder / ".mcp.json"
        if config.is_file():
            for server_name, settings in json.loads(config.read_text(encoding="utf-8-sig")).get("mcpServers", {}).items():
                settings = expand(settings, folder, environment)
                if not settings.get("command") or settings.get("type", "stdio") != "stdio":
                    raise PluginConfigurationError(f"Plugin {name} must declare a stdio command.")
                servers.append((server_name, folder.resolve(), settings))
        for path in sorted((folder / "skills").glob("*/SKILL.md")):
            source = path.read_text(encoding="utf-8-sig")
            if not source.startswith("---\n"):
                raise PluginConfigurationError(f"Missing skill frontmatter in {path.name}.")
            fields = yaml.safe_load(source.split("---", 2)[1]) or {}
            if not all(isinstance(fields.get(key), str) and fields[key].strip() for key in ("name", "description")):
                raise PluginConfigurationError(f"Skill {path.parent.name} needs a name and description.")
            skills.append({"name": fields["name"], "description": fields["description"], "path": str(path.resolve())})
    return plugins, servers, skills


class PluginRuntime:
    def __init__(self, root):
        self.root = Path(root)
        self.plugins, self.servers, self.skills = discover(self.root, os.environ)
        settings = self.root / "settings.json"
        allow = json.loads(settings.read_text(encoding="utf-8-sig")).get("allow", []) if settings.exists() else []
        if not isinstance(allow, list) or any(not isinstance(name, str) for name in allow):
            raise PluginConfigurationError("settings.json allow must be a list of MCP tool names.")
        self.allow = set(allow) - {"bash"}  # bash can never be allow-listed.
        self.tools, self.routes = [], {}
        self.agent_types = {}
        self.ready = threading.Event()
        self.error = None
        self.thread = None
        self.loop = None
        self.stop = None

    def __enter__(self):
        self.thread = threading.Thread(target=self._worker, name="mcp-plugins", daemon=True)
        self.thread.start()
        if not self.ready.wait(180):
            self.__exit__(None, None, None)
            raise RuntimeError("Plugin startup timed out. Check the interpreter and server commands.")
        if self.error:
            self.thread.join(timeout=10)
            raise self.error
        return self

    def __exit__(self, *args):
        if self.loop and self.stop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.stop.set)
        if self.thread:
            self.thread.join(timeout=30)

    def _worker(self):
        try:
            asyncio.run(self._serve())
        except Exception as error:
            # Never include client parameter reprs, env values or secret URLs.
            self.error = error if isinstance(error, (PluginConfigurationError, AgentTypeError)) else RuntimeError(
                f"Plugin connection failed ({type(error).__name__}). Check required settings and the documented server command."
            )
            self.ready.set()

    async def _serve(self):
        self.loop = asyncio.get_running_loop()
        self.stop = asyncio.Event()
        async with AsyncExitStack() as stack:
            seen_servers = set()
            for name, folder, settings in self.servers:
                if name in seen_servers:
                    raise PluginConfigurationError(f"Duplicate MCP server name: {name}.")
                seen_servers.add(name)
                command = settings["command"]
                if command == "uv" and not shutil.which(command):
                    candidate = Path.home() / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv")
                    if candidate.is_file():
                        command = str(candidate)
                parameters = StdioServerParameters(command=command, args=settings.get("args", []), env=settings.get("env", {}), cwd=str(folder))
                client = await stack.enter_async_context(Client(parameters))
                result = await client.list_tools()
                for tool in result.tools:
                    exposed_name = name + "__" + tool.name
                    if not TOOL_NAME.fullmatch(exposed_name) or exposed_name in self.routes:
                        raise PluginConfigurationError(f"Invalid or duplicate MCP tool name: {exposed_name}.")
                    self.routes[exposed_name] = (client, tool.name)
                    self.tools.append({"type": "function", "function": {"name": exposed_name, "description": tool.description or "", "parameters": tool.input_schema}})
            self.agent_types = load_agent_types(self.root, [TOOL] + self.tools)
            self.ready.set()
            await self.stop.wait()  # Enter and close SDK contexts in this task.

    def skill_prompt(self):
        if not self.skills:
            return ""
        lines = ["Available plugin skills (read the full SKILL.md with bash before using a skill):"]
        lines.extend(f"- {skill['name']}: {skill['description']} File: {skill['path']}" for skill in self.skills)
        return "\n".join(lines)

    def describe(self):
        print("Plugins: " + (", ".join(self.plugins) or "none"), flush=True)
        print("MCP tools: " + (", ".join(self.routes) or "none"), flush=True)
        print("Skills: " + (", ".join(skill["name"] for skill in self.skills) or "none"), flush=True)
        print("Agent types: " + (", ".join(self.agent_types) or "none"), flush=True)

    def agent_type_prompt(self):
        return type_prompt(self.agent_types)

    def call_tool(self, name, arguments, approve, *, cancel_event=None, deadline=None):
        if name not in self.routes:
            return {"error": "Unknown MCP tool. Choose a tool from the supplied schemas."}
        if name not in self.allow and not approve("MCP tool " + name + "\n" + json.dumps(arguments, ensure_ascii=False, indent=2)):
            return {"declined": True, "error": "The user declined this MCP tool call. Respect that decision."}
        if cancel_event is not None and cancel_event.is_set():
            return {"error": "The subagent stopped; the MCP action was not started."}
        if cancel_event is not None or deadline is not None:
            return self._dispatch(name, arguments, cancel_event=cancel_event, deadline=deadline)
        return self._dispatch(name, arguments)

    def channel_call(self, name, arguments):
        """Fixed phone I/O owned by the harness, never a model tool dispatcher.

        Model requests always go through call_tool and its approval policy.
        Delivering the approval prompt itself cannot recursively ask approval.
        """
        if name not in {"telegram__send_message", "telegram__wait_for_messages"} or name not in self.routes:
            raise ValueError("The phone channel only supports its configured send and wait tools.")
        return self._dispatch(name, arguments)

    def _dispatch(self, name, arguments, *, cancel_event=None, deadline=None):
        future = asyncio.run_coroutine_threadsafe(self._call(name, arguments), self.loop)
        try:
            if cancel_event is None and deadline is None:
                return future.result(timeout=120)
            import time
            end = min(time.monotonic() + 120, deadline) if deadline is not None else time.monotonic() + 120
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    future.cancel()
                    return {"error": "The subagent stopped; the in-flight MCP result was cancelled. Completed external effects cannot be undone."}
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise CallTimeout()
                try:
                    return future.result(timeout=min(0.1, remaining))
                except CallTimeout:
                    continue
        except CallTimeout:
            future.cancel()
            return {"error": "The MCP tool timed out. Check the server before retrying."}
        except Exception as error:
            return {"error": f"MCP tool failed ({type(error).__name__}). Check the server configuration and retry."}

    async def _call(self, name, arguments):
        client, original_name = self.routes[name]
        result = await client.call_tool(original_name, arguments)
        content = "\n".join(item.text for item in result.content if item.type == "text")[:20_000]
        if result.is_error:
            return {"error": content}
        try:
            return json.loads(content)
        except ValueError:
            return {"text": content}
