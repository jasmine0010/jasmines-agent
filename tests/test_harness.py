"""Offline behavioral checks; these never contact a model provider."""

import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import agent
import shell_tool
import web


def model_reply(message):
    return {"choices": [{"message": message}], "usage": {"prompt_tokens": 12, "completion_tokens": 4}}


def tool_call(command="Write-Output hello"):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "call-test", "type": "function", "function": {"name": "bash", "arguments": json.dumps({"command": command})},
    }]}


class LoopTests(unittest.TestCase):
    def test_denial_is_returned_to_model_with_matching_id(self):
        messages, events = agent.conversation(), []
        replies = [model_reply(tool_call()), model_reply({"role": "assistant", "content": "Command declined."})]
        with patch.object(agent, "call_model", side_effect=replies) as model, patch.object(shell_tool.subprocess, "Popen") as process:
            agent.run_turn(messages, "Synthetic test", lambda command: False, events.append)
        self.assertFalse(process.called)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(messages[-2]["tool_call_id"], "call-test")
        self.assertTrue(json.loads(messages[-2]["content"])["declined"])

    def test_bad_arguments_and_unknown_tools_cannot_execute(self):
        for function in [{"name": "bash", "arguments": "not json"}, {"name": "other", "arguments": "{}"}, {"name": "bash", "arguments": '{"command":"hello","extra":true}'}]:
            with self.subTest(function=function), patch.object(agent, "run_bash") as run:
                self.assertIn("error", agent.execute_tool({"function": function}, lambda command: True))
                run.assert_not_called()

    def test_round_limit_leaves_complete_tool_messages(self):
        messages, events = agent.conversation(), []
        with patch.object(agent, "MAX_TOOL_ROUNDS", 2), patch.object(agent, "call_model", return_value=model_reply(tool_call())) as model:
            agent.run_turn(messages, "Synthetic loop", lambda command: False, events.append)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(messages[-1]["role"], "tool")
        self.assertEqual(events[-1]["type"], "error")

    def test_missing_cached_usage_is_not_reported_as_zero(self):
        self.assertIn("cached input=not reported", agent.usage_text(model_reply({})))


class ShellTests(unittest.TestCase):
    def test_output_exit_status_timeout_and_truncation(self):
        windows = os.name == "nt"
        with tempfile.TemporaryDirectory() as directory, patch.object(shell_tool, "WORKSPACE", Path(directory)):
            result = shell_tool.run_bash("Write-Output hello" if windows else "printf hello", lambda command: True)
            self.assertEqual((result["stdout"].strip(), result["exit_code"]), ("hello", 0))
            result = shell_tool.run_bash("Write-Error deliberate; exit 7" if windows else "printf deliberate >&2; exit 7", lambda command: True)
            self.assertEqual(result["exit_code"], 7)
            self.assertIn("deliberate", result["stderr"])
            result = shell_tool.run_bash("Start-Sleep -Seconds 5" if windows else "sleep 5", lambda command: True, timeout=0.5)
            self.assertTrue(result["timed_out"])
            result = shell_tool.run_bash("Write-Output ('x' * 20000)" if windows else "printf '%20000s' x", lambda command: True)
            self.assertTrue(result["truncated"])
            self.assertLessEqual(len(result["stdout"]) + len(result["stderr"]), shell_tool.OUTPUT_LIMIT)


class WebTests(unittest.TestCase):
    def setUp(self):
        self.server = web.create_server(0)
        self.origin = "http://" + self.server.authority
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)

    def request(self, path, body=None, authenticated=True, origin=None):
        headers = {"Content-Type": "application/json", "Origin": origin or self.origin}
        if authenticated:
            headers["X-Chat-Token"] = self.server.api_token
        request = Request(self.origin + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, response.read()
        except HTTPError as error:
            with error:
                return error.code, error.read()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            snapshot = self.server.chat.snapshot(0)
            if predicate(snapshot):
                return snapshot
            time.sleep(0.01)
        self.fail("Timed out waiting for the local worker")

    def test_local_page_and_request_protection(self):
        status, html = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Jasmine's Agent", html)
        self.assertNotIn(b"__API_TOKEN__", html)
        self.assertEqual(self.request("/events", authenticated=False)[0], 403)
        self.assertEqual(self.request("/reset", {}, origin="https://example.com")[0], 403)
        self.assertEqual(self.request("/message", {"prompt": " "})[0], 400)
        self.assertEqual(self.request("/approve", {"id": "x", "approved": 1})[0], 400)

    def test_approval_waits_and_denial_prevents_execution(self):
        replies = [model_reply(tool_call()), model_reply({"role": "assistant", "content": "I respected the denial."})]
        with patch.object(agent, "call_model", side_effect=replies), patch.object(shell_tool.subprocess, "Popen") as process:
            self.assertEqual(self.request("/message", {"prompt": "Synthetic test"})[0], 200)
            snapshot = self.wait_for(lambda data: data["pending"])
            self.assertTrue(snapshot["busy"])
            self.assertFalse(process.called)
            self.assertEqual(self.request("/reset", {})[0], 409)
            self.assertEqual(self.request("/message", {"prompt": "Another turn"})[0], 409)
            self.assertEqual(self.request("/approve", {"id": "wrong", "approved": True})[0], 409)
            self.assertEqual(self.request("/approve", {"id": snapshot["pending"], "approved": False})[0], 200)
            finished = self.wait_for(lambda data: not data["busy"])
            self.assertFalse(process.called)
        outputs = [event["result"] for event in finished["events"] if event["type"] == "tool_result"]
        self.assertTrue(outputs[0]["declined"])
        self.assertEqual(finished["events"][-1]["text"], "I respected the denial.")
        self.assertEqual(self.request("/reset", {})[0], 200)
        self.assertEqual(self.server.chat.snapshot(0)["events"], [])


if __name__ == "__main__":
    unittest.main()
