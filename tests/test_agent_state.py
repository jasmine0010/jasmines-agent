"""Offline checks for independent Agent state and the shared loop."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent


def reply(text, calls=None):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = calls
    return {"choices": [{"message": message}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4,
                      "prompt_tokens_details": {"cached_tokens": 5}}}


class AgentStateTests(unittest.TestCase):
    def test_two_agents_never_receive_each_others_context_or_inbox(self):
        left = agent.Agent(id="sa-left", type_name="reader", system_prompt="Only left context", tools=[])
        right = agent.Agent(id="sa-right", type_name="reader", system_prompt="Only right context", tools=[])
        left.inbox.put("Left follow-up")
        observed = []

        def model(messages, tools, **kwargs):
            observed.append(json.loads(json.dumps(messages)))
            return reply("Independent report")

        with patch.object(agent, "call_model", side_effect=model):
            left.run("Left task", lambda request: False, lambda event: None)
            right.run("Right task", lambda request: False, lambda event: None)
        self.assertIn("Left follow-up", json.dumps(observed[0]))
        self.assertNotIn("Left", json.dumps(observed[1]))
        self.assertNotIn("Right", json.dumps(observed[0]))
        self.assertIsNot(left.stop_event, right.stop_event)
        self.assertIsNot(left.token_usage, right.token_usage)
        self.assertEqual((left.state, right.state), ("idle", "idle"))

    def test_main_object_keeps_conversation_and_usage_between_turns(self):
        state = agent.Agent(max_seconds=None)
        messages = agent.conversation()
        with patch.object(agent, "call_model", side_effect=[reply("First answer"), reply("Second answer")]):
            self.assertIs(agent.run_turn(messages, "First question", lambda action: False, lambda event: None, agent_state=state), state)
            agent.run_turn(messages, "Second question", lambda action: False, lambda event: None, agent_state=state)
        self.assertEqual(state.turns, 2)
        self.assertEqual(state.tokens, 32)
        self.assertEqual(state.token_usage["cached_tokens"], 10)
        self.assertEqual(state.report, "Second answer")
        self.assertIn("First question", json.dumps(state.messages))

    def test_child_cannot_fabricate_bash_when_it_has_no_tools(self):
        child = agent.Agent(id="sa-1", type_name="reader", tools=[])
        call = {"id": "blocked", "function": {"name": "bash", "arguments": '{"command":"never run"}'}}
        with patch.object(agent, "call_model", side_effect=[reply(None, [call]), reply("Blocked safely")]), patch.object(agent, "run_bash") as shell:
            child.run("Synthetic task", lambda request: True, lambda event: None)
        shell.assert_not_called()
        self.assertIn("not permitted", child.messages[-2]["content"])

    def test_agent_uses_its_own_runtime_instead_of_global_runtime(self):
        from unittest.mock import Mock
        own, unrelated = Mock(), Mock()
        own.call_tool.return_value = {"value": "own fixture"}
        tool = {"type": "function", "function": {"name": "fixture__read"}}
        child = agent.Agent(id="sa-1", type_name="reader", tools=[tool], runtime=own)
        call = {"function": {"name": "fixture__read", "arguments": "{}"}}
        with patch.object(agent, "PLUGINS", unrelated):
            self.assertEqual(agent.execute_tool(call, lambda request: True, worker=child), {"value": "own fixture"})
        own.call_tool.assert_called_once()
        unrelated.call_tool.assert_not_called()

    def test_log_records_tool_result_with_matching_id_and_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = agent.Agent(log_path=Path(directory) / "main.jsonl", max_seconds=None)
            call = {"id": "fixture-call", "function": {"name": "bash", "arguments": '{"command":"synthetic"}'}}
            with patch.object(agent, "call_model", side_effect=[reply(None, [call]), reply("Done")]):
                agent.run_turn(agent.conversation(), "Task", lambda request: False, lambda event: None, agent_state=worker)
            records = [json.loads(line) for line in worker.log_path.read_text(encoding="utf-8").splitlines()]
            results = [item["payload"] for item in records if item["kind"] == "message" and item["payload"].get("role") == "tool"]
            self.assertEqual(results[0]["tool_call_id"], "fixture-call")
            self.assertTrue(json.loads(results[0]["content"])["declined"])
            self.assertEqual(len([item for item in records if item["kind"] == "usage"]), 2)

    def test_limit_marks_failed_and_retains_complete_tool_history(self):
        worker = agent.Agent(max_seconds=None)
        call = {"id": "fixture-call", "function": {"name": "bash", "arguments": '{"command":"synthetic"}'}}
        with patch.object(agent, "MAX_TOOL_ROUNDS", 1), patch.object(agent, "call_model", return_value=reply(None, [call])):
            agent.run_turn(agent.conversation(), "Task", lambda request: False, lambda event: None, agent_state=worker)
        self.assertEqual(worker.state, "failed")
        self.assertIn("max_turns", worker.failure_reason)
        self.assertEqual(worker.messages[-1]["role"], "tool")


if __name__ == "__main__":
    unittest.main()
