"""Fresh context, report-only return, permissions, accounting and limits."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import agent
from agent_types import AgentType, type_prompt
from subagents import RUNNING_SLOTS, SubagentManager


def response(text=None, calls=None):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = calls
    return {"choices": [{"message": message}], "usage": {"prompt_tokens": 12, "completion_tokens": 4}}


def call(name, arguments, identity="fixture-call"):
    return {"id": identity, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


class FixtureRuntime:
    def __init__(self):
        self.tools = [{"type": "function", "function": {"name": "fixture__read", "parameters": {"type": "object"}}}]
        self.agent_types = {"reader": AgentType("reader", "Read a synthetic fixture", ("fixture__read",), "Own reader prompt", 10)}
        self.approvals = []

    def skill_prompt(self):
        return ""

    def agent_type_prompt(self):
        return type_prompt(self.agent_types)

    def call_tool(self, name, arguments, approve, **kwargs):
        if not approve("MCP tool " + name + "\n" + json.dumps(arguments)):
            return {"declined": True}
        return {"raw_fixture": "CHILD_ONLY_RAW_DATA"}


class DelegateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.runtime = FixtureRuntime()
        self.parent = agent.Agent(max_seconds=None, runtime=self.runtime,
                                  messages=[{"role": "system", "content": "MAIN_ONLY_PRIVATE_CONTEXT"}])
        self.manager = SubagentManager(self.parent, self.root)
        self.approvals, self.events = [], []
        self.manager.configure(lambda request: True, lambda request: self.approvals.append(request) or True, self.events.append, ())
        self.addCleanup(self.manager.close)

    def test_fresh_context_report_only_result_and_private_log(self):
        observed = []
        replies = iter([response(calls=[call("fixture__read", {})]), response("One-line fixture report")])

        def model(messages, tools, **kwargs):
            observed.append(json.loads(json.dumps(messages)))
            return next(replies)

        with patch.object(agent, "call_model", side_effect=model):
            result = self.manager.delegate("reader", "Read fixture and report one line")
        self.assertNotIn("MAIN_ONLY_PRIVATE_CONTEXT", json.dumps(observed))
        self.assertNotIn("CHILD_ONLY_RAW_DATA", json.dumps(result))
        self.assertEqual((result["state"], result["report"]), ("idle", "One-line fixture report"))
        self.assertTrue(self.approvals[0].startswith("[sa-1 · reader] MCP tool fixture__read"))
        child = self.manager.agents[result["id"]]
        self.assertIn("CHILD_ONLY_RAW_DATA", child.log_path.read_text(encoding="utf-8"))
        self.assertEqual((self.parent.child_tokens, self.parent.tokens), (32, 32))

    def test_real_main_loop_sees_report_and_counts_child_usage(self):
        responses = [response(calls=[call("delegate", {"agent": "reader", "task": "Read fixture and report one line"})]),
                     response(calls=[call("fixture__read", {})]), response("One-line fixture report"), response("Main combined answer")]
        observed = []

        def model(messages, tools, **kwargs):
            observed.append((json.loads(json.dumps(messages)), [item["function"]["name"] for item in tools]))
            return responses.pop(0)

        with patch.object(agent, "PLUGINS", self.runtime), patch.object(agent, "ROOT", self.root), patch.object(agent, "conversation", return_value=[{"role": "system", "content": "Main prompt"}]), patch.object(agent, "call_model", side_effect=model):
            agent.run_turn(self.parent.messages, "Delegate the fixture", lambda action: True, self.events.append,
                           agent_state=self.parent, main_hidden_tools=("fixture__read",))
        self.addCleanup(self.parent.manager.close)
        self.assertIn("delegate", observed[0][1])
        self.assertNotIn("fixture__read", observed[0][1])
        self.assertIn("fixture__read", observed[1][1])
        self.assertNotIn("delegate", observed[1][1])
        self.assertNotIn("CHILD_ONLY_RAW_DATA", json.dumps(observed[-1][0]))
        self.assertIn("One-line fixture report", json.dumps(observed[-1][0]))
        self.assertEqual((self.parent.child_tokens, self.parent.tokens), (32, 64))

    def test_fabricated_child_control_and_shell_calls_are_blocked(self):
        forged = [call("delegate", {"agent": "reader", "task": "Nested"}, "nested"), call("bash", {"command": "never run"}, "shell")]
        with patch.object(agent, "call_model", side_effect=[response(calls=forged), response("No forbidden actions")]), patch.object(agent, "run_bash") as shell:
            result = self.manager.delegate("reader", "Test tool restrictions")
        shell.assert_not_called()
        self.assertEqual(result["report"], "No forbidden actions")
        self.assertFalse(self.approvals)

    def test_max_turns_is_failed_with_complete_tool_result(self):
        self.runtime.agent_types["reader"] = AgentType("reader", "One turn", ("fixture__read",), "Prompt", 1)
        with patch.object(agent, "call_model", return_value=response(calls=[call("fixture__read", {})])) as model:
            result = self.manager.delegate("reader", "Requires another round")
        self.assertEqual(model.call_count, 1)
        self.assertEqual(result["state"], "failed")
        self.assertIn("max_turns", result["failure_reason"])
        self.assertEqual(self.manager.agents[result["id"]].messages[-1]["role"], "tool")

    def test_deadline_discards_late_model_actions(self):
        original = self.manager._create

        def short_lived(kind, task):
            child = original(kind, task)
            child.max_seconds = 0.005
            return child

        def slow_model(*args, **kwargs):
            time.sleep(0.02)
            return response(calls=[call("fixture__read", {})])

        with patch.object(self.manager, "_create", side_effect=short_lived), patch.object(agent, "call_model", side_effect=slow_model):
            result = self.manager.delegate("reader", "Test deadline")
        self.assertEqual(result["state"], "failed")
        self.assertIn("max_seconds", result["failure_reason"])
        self.assertFalse(self.approvals)

    def test_four_running_slots_reject_another_job(self):
        for _ in range(4):
            self.assertTrue(RUNNING_SLOTS.acquire(blocking=False))
        try:
            with patch.object(agent, "call_model") as model:
                self.assertIn("4 subagents", self.manager.delegate("reader", "Task")["error"])
            model.assert_not_called()
        finally:
            for _ in range(4):
                RUNNING_SLOTS.release()

    def test_type_model_override_is_passed_to_shared_model_client(self):
        self.runtime.agent_types["reader"] = AgentType("reader", "Override", (), "Prompt", model="synthetic-other-model")
        with patch.object(agent, "call_model", return_value=response("Done")) as model:
            result = self.manager.delegate("reader", "Task")
        self.assertEqual(result["state"], "idle")
        self.assertEqual(model.call_args.kwargs["model"], "synthetic-other-model")


if __name__ == "__main__":
    unittest.main()
