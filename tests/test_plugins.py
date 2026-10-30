"""Offline checks for plugin discovery, context, routing, and permissions."""
import asyncio
from concurrent.futures import Future
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent
import shell_tool
from mcp import Client
from mcp.server import MCPServer
from plugin_runtime import PluginRuntime, PluginConfigurationError, discover, expand


class PluginTests(unittest.TestCase):
    def test_expansion_never_runs_shell_and_missing_setting_fails(self):
        result = expand({"args": ["${CLAUDE_PLUGIN_ROOT}/server.py", "${TOKEN}"]}, Path("demo"), {"TOKEN": "$(not-a-command)"})
        self.assertEqual(result["args"][1], "$(not-a-command)")
        self.assertTrue(Path(result["args"][0]).is_absolute())
        with self.assertRaisesRegex(PluginConfigurationError, "Set TOKEN"):
            expand("${TOKEN}", Path("demo"), {})

    def test_discovery_uses_metadata_without_skill_body_or_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plugin = root / "plugins" / "demo"
            (plugin / ".claude-plugin").mkdir(parents=True)
            (plugin / ".claude-plugin/plugin.json").write_text('{"name":"demo"}')
            (plugin / ".mcp.json").write_text('{"mcpServers":{"demo":{"command":"python","env":{"TOKEN":"${TOKEN}"}}}}')
            skill = plugin / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text('---\nname: demo\ndescription: Read-only synthetic task\n---\nBODY_MUST_NOT_BE_IN_PROMPT\n')
            with patch.dict("os.environ", {"TOKEN": "synthetic-private-value"}):
                runtime = PluginRuntime(root)
            prompt = runtime.skill_prompt()
            self.assertIn("Read-only synthetic task", prompt)
            self.assertIn(str(skill.resolve()), prompt)
            self.assertNotIn("BODY_MUST_NOT_BE_IN_PROMPT", prompt)
            self.assertNotIn("synthetic-private-value", prompt)
            self.assertEqual(runtime.servers[0][2]["env"]["TOKEN"], "synthetic-private-value")

    def test_unlisted_tool_denial_never_dispatches(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = PluginRuntime(folder)
            runtime.routes["demo__read"] = (None, "read")
            with patch("plugin_runtime.asyncio.run_coroutine_threadsafe") as dispatch:
                result = runtime.call_tool("demo__read", {}, lambda request: False)
            self.assertTrue(result["declined"])
            dispatch.assert_not_called()

    def test_allow_list_executes_only_registered_mcp_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "settings.json").write_text('{"allow":["demo__read","bash"]}')
            runtime = PluginRuntime(root)
            self.assertNotIn("bash", runtime.allow)
            runtime.routes["demo__read"] = (None, "read")
            def complete(coroutine, loop):
                coroutine.close()
                future = Future()
                future.set_result({"ok": True})
                return future
            with patch("plugin_runtime.asyncio.run_coroutine_threadsafe", side_effect=complete):
                result = runtime.call_tool("demo__read", {}, lambda request: self.fail("Trusted MCP tool asked unexpectedly"))
            self.assertTrue(result["ok"])
            self.assertIn("error", runtime.call_tool("unknown", {}, lambda request: True))

    def test_bash_still_asks_with_plugins_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = PluginRuntime(folder)
            with patch.object(agent, "PLUGINS", runtime), patch("shell_tool.subprocess.Popen") as process:
                result = agent.execute_tool({"function": {"name": "bash", "arguments": '{"command":"never execute"}'}}, lambda command: False)
            self.assertTrue(result["declined"])
            process.assert_not_called()

    def test_shell_child_does_not_inherit_model_or_telegram_credentials(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(shell_tool, "WORKSPACE", Path(folder)), patch.dict(os.environ, {"API_KEY": "synthetic-model-key", "TELEGRAM_BOT_TOKEN": "synthetic-bot-token", "EMAIL_APP_PASSWORD": "synthetic-app-password"}), patch.object(shell_tool.subprocess, "Popen", wraps=shell_tool.subprocess.Popen) as process:
            result = shell_tool.run_bash("Write-Output fixture" if os.name == "nt" else "printf fixture", lambda command: True)
            self.assertEqual(result["exit_code"], 0)
            environment = process.call_args.kwargs["env"]
            self.assertNotIn("API_KEY", environment)
            self.assertNotIn("TELEGRAM_BOT_TOKEN", environment)
            self.assertNotIn("EMAIL_APP_PASSWORD", environment)

    def test_model_gets_plugin_schema_and_metadata_with_matching_tool_id(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = PluginRuntime(folder)
            runtime.tools = [{"type": "function", "function": {"name": "demo__read", "description": "Read", "parameters": {"type": "object"}}}]
            runtime.skills = [{"name": "demo", "description": "Read-only task", "path": "/synthetic/SKILL.md"}]
            call = {"role": "assistant", "content": None, "tool_calls": [{"id": "mcp-call", "type": "function", "function": {"name": "demo__read", "arguments": "{}"}}]}
            replies = [{"choices": [{"message": call}]}, {"choices": [{"message": {"role": "assistant", "content": "Done"}}]}]
            with patch.object(agent, "PLUGINS", runtime), patch.object(runtime, "call_tool", return_value={"value": 42}) as dispatch, patch.object(agent, "call_model", side_effect=replies) as model:
                messages = agent.conversation()
                agent.run_turn(messages, "Synthetic question", lambda request: False, lambda event: None)
            self.assertIn("Read-only task", messages[0]["content"])
            self.assertEqual(model.call_args_list[0].args[1][1]["function"]["name"], "demo__read")
            self.assertEqual(messages[-2]["tool_call_id"], "mcp-call")
            self.assertEqual(json.loads(messages[-2]["content"]), {"value": 42})
            dispatch.assert_called_once()

    def test_empty_plugin_runtime_starts_and_closes_its_thread(self):
        with tempfile.TemporaryDirectory() as folder:
            with PluginRuntime(folder) as runtime:
                self.assertTrue(runtime.thread.is_alive())
            self.assertFalse(runtime.thread.is_alive())


class ProtocolRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_client_response_is_returned_by_dispatcher(self):
        server = MCPServer("synthetic")
        @server.tool()
        def read_fixture() -> dict:
            return {"value": 42}
        with tempfile.TemporaryDirectory() as folder:
            runtime = PluginRuntime(folder)
            async with Client(server) as client:
                runtime.routes["demo__read_fixture"] = (client, "read_fixture")
                self.assertEqual(await runtime._call("demo__read_fixture", {}), {"value": 42})


if __name__ == "__main__":
    unittest.main()
