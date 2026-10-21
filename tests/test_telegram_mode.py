"""Offline phone tests: approval binding, denial, queues, and model routing."""
from collections import deque
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent
from plugin_runtime import PluginRuntime
from telegram_mode import TelegramMode, SEND, WAIT


def message(text, reply=None):
    return {"text": text, "reply_to_message_id": reply}


class PhoneRuntime:
    def __init__(self, batches=()):
        self.routes = {SEND: None, WAIT: None}
        self.batches = deque(batches)
        self.sent = []
        self.tools = [{"type": "function", "function": {"name": name}} for name in (SEND, WAIT)]

    def skill_prompt(self):
        return "synthetic skill metadata"

    def channel_call(self, name, arguments):
        if name == SEND:
            self.sent.append(arguments["text"])
            return {"status": "sent", "message_ids": [100 + len(self.sent)]}
        return {"messages": self.batches.popleft()}


class PhoneTests(unittest.TestCase):
    def test_yes_must_reply_to_this_request_and_questions_survive(self):
        runtime = PhoneRuntime([[message("yes"), message("yes", 99), message("next question"), message(" YeS ", 101)]])
        mode = TelegramMode(runtime)
        mode.approval_ids.add(99)
        self.assertTrue(mode.approve("Read a public fixture"))
        self.assertEqual([m["text"] for m in mode.pending], ["next question"])
        self.assertIn("unlinked", runtime.sent[-1])

    def test_only_first_reply_counts_and_anything_except_yes_denies(self):
        for answer in ("no", "y", "maybe", "yes please"):
            runtime = PhoneRuntime([[message(answer, 101), message("yes", 101)]])
            mode = TelegramMode(runtime)
            self.assertFalse(mode.approve("Synthetic action"))
            self.assertFalse(mode.pending)

    def test_timeout_and_missing_message_id_fail_closed(self):
        runtime = PhoneRuntime()
        mode = TelegramMode(runtime, approval_seconds=0)
        self.assertFalse(mode.approve("Synthetic action"))
        self.assertIn("timed out", runtime.sent[-1])
        with patch.object(runtime, "channel_call", return_value={"status": "sent"}):
            with self.assertRaisesRegex(RuntimeError, "no action was approved"):
                mode.approve("Synthetic action")

    def test_old_approval_reply_is_not_a_new_model_turn(self):
        mode = TelegramMode(PhoneRuntime())
        mode.approval_ids.add(101)
        with patch.object(agent, "run_turn") as run:
            mode.handle(message("yes", 101))
        run.assert_not_called()

    def test_model_cannot_poll_even_if_it_fabricates_a_call(self):
        runtime = PhoneRuntime()
        replies = [{"choices": [{"message": {"role": "assistant", "content": None,
                    "tool_calls": [{"id": "x", "function": {"name": WAIT, "arguments": "{}"}}]}}]},
                   {"choices": [{"message": {"role": "assistant", "content": "Finished"}}]}]
        with patch.object(agent, "PLUGINS", runtime), patch.object(agent, "call_model", side_effect=replies) as model:
            mode = TelegramMode(runtime)
            mode.handle(message("A synthetic question"))
        offered = [t["function"]["name"] for t in model.call_args_list[0].args[1]]
        self.assertNotIn(WAIT, offered)
        self.assertIn(SEND, offered)
        self.assertIn("unavailable", mode.messages[-2]["content"])
        self.assertEqual(runtime.sent[-1], "Finished")

    def test_denied_shell_never_starts_and_result_reaches_model(self):
        runtime = PhoneRuntime([[message("no", 102)]])  # progress is message 101
        replies = [{"choices": [{"message": {"role": "assistant", "content": None,
                    "tool_calls": [{"id": "x", "function": {"name": "bash", "arguments": '{"command":"never run this"}'}}]}}]},
                   {"choices": [{"message": {"role": "assistant", "content": "You declined; I did not run it."}}]}]
        with patch.object(agent, "PLUGINS", runtime), patch.object(agent, "call_model", side_effect=replies), patch("shell_tool.subprocess.Popen") as process:
            mode = TelegramMode(runtime)
            mode.handle(message("Synthetic denial test"))
        process.assert_not_called()
        self.assertIn('"declined": true', mode.messages[-2]["content"])
        self.assertIn("declined", runtime.sent[-1])

    def test_conversation_persists_then_new_resets(self):
        runtime = PhoneRuntime()
        def turn(messages, prompt, approve, emit, **kwargs):
            messages.append({"role": "user", "content": prompt})
            emit({"type": "assistant", "text": "Answer"})
        with patch.object(agent, "run_turn", side_effect=turn):
            mode = TelegramMode(runtime)
            mode.handle(message("one"))
            mode.handle(message("two"))
            self.assertEqual(len(mode.messages), 3)
            mode.handle(message("/new"))
            self.assertEqual(len(mode.messages), 1)

    def test_channel_cannot_dispatch_arbitrary_tools_and_model_still_asks(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = PluginRuntime(Path(folder))
            runtime.routes = {SEND: None, WAIT: None, "research__read": None}
            with patch.object(runtime, "_dispatch", return_value={"status": "sent"}) as dispatch:
                self.assertEqual(runtime.channel_call(SEND, {"text": "approval prompt"}), {"status": "sent"})
                with self.assertRaises(ValueError):
                    runtime.channel_call("research__read", {})
                result = runtime.call_tool(SEND, {"text": "model message"}, lambda action: False)
                self.assertTrue(result["declined"])
                self.assertEqual(dispatch.call_count, 1)

    def test_failed_turn_explains_error_redacts_credentials_and_resets(self):
        runtime = PhoneRuntime()
        mode = TelegramMode(runtime)
        with patch.dict("os.environ", {"API_KEY": "synthetic-secret"}), patch.object(agent, "run_turn", side_effect=RuntimeError("Service unavailable synthetic-secret")):
            mode.handle(message("Synthetic failure"))
        self.assertIn("Service unavailable", runtime.sent[-1])
        self.assertNotIn("synthetic-secret", runtime.sent[-1])
        self.assertEqual(len(mode.messages), 1)


if __name__ == "__main__":
    unittest.main()
