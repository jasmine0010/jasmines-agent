"""Deterministic background checks; model responses are synthetic, not demos."""

from concurrent.futures import Future
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import agent
from agent_types import AgentType
from history import ChatHistory
from plugin_runtime import PluginRuntime
import shell_tool
from subagents import SubagentManager
from test_delegate import FixtureRuntime, response, call
from telegram_mode import TelegramMode
from test_telegram_mode import PhoneRuntime, message


def eventually(predicate, seconds=3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    raise AssertionError("Expected condition did not become true.")


def alive(pid):
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        kernel.CloseHandle(ctypes.c_void_p(handle))
        return code.value == 259
    try:
        os.kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat")
        return not (stat.exists() and stat.read_text().split()[2] == "Z")
    except ProcessLookupError:
        return False


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.runtime = FixtureRuntime()
        self.parent = agent.Agent(runtime=self.runtime, max_seconds=None)
        self.manager = SubagentManager(self.parent, self.root)
        self.events = []
        self.manager.configure(lambda request: True, lambda request: True, self.events.append, ())
        self.addCleanup(self.manager.close)

    def test_three_jobs_overlap_and_four_slots_are_enforced(self):
        entered, gate = [], threading.Event()

        def model(messages, tools, **kwargs):
            entered.append(threading.current_thread().name)
            gate.wait(3)
            return response("Finished fixture")

        with patch.object(agent, "call_model", side_effect=model):
            try:
                ids = [self.manager.start("reader", f"Task {index}")["id"] for index in range(4)]
                eventually(lambda: len(entered) == 4)
                self.assertEqual(len(set(entered)), 4)
                self.assertIn("4 subagents", self.manager.start("reader", "Fifth")["error"])
                self.assertTrue(all(item["state"] == "running" for item in self.manager.list()["agents"]))
                self.assertTrue(self.manager.wait(ids, timeout=0)["timed_out"])
            finally:
                gate.set()
            result = self.manager.wait(ids, timeout=3)
            self.assertFalse(result["timed_out"])
            self.assertTrue(all(item["state"] == "idle" for item in result["agents"]))
            self.assertEqual((self.parent.child_tokens, self.parent.tokens), (64, 64))

    def test_idle_send_reuses_thread_context_and_does_not_read_again(self):
        seen = []

        def model(messages, tools, **kwargs):
            seen.append(json.loads(json.dumps(messages)))
            return response("Original finding" if len(seen) == 1 else "Follow-up from existing finding")

        with patch.object(agent, "call_model", side_effect=model):
            identity = self.manager.start("reader", "Original task")["id"]
            self.manager.wait([identity], 3)
            thread = self.manager.threads[identity]
            self.manager.send(identity, "Explain the existing finding")
            result = self.manager.wait([identity], 3)["agents"][0]
        self.assertIs(self.manager.threads[identity], thread)
        self.assertIn("Original finding", json.dumps(seen[-1]))
        self.assertEqual(result["report"], "Follow-up from existing finding")
        self.assertEqual(result["turns"], 2)
        self.assertFalse(any(item.get("tool_calls") for item in seen[-1]))

    def test_running_send_is_not_lost_after_final_model_response(self):
        entered, gate = threading.Event(), threading.Event()
        seen = []

        def model(messages, tools, **kwargs):
            seen.append(json.loads(json.dumps(messages)))
            if len(seen) == 1:
                entered.set()
                gate.wait(3)
            return response("First" if len(seen) == 1 else "Follow-up handled")

        with patch.object(agent, "call_model", side_effect=model):
            identity = self.manager.start("reader", "Task")["id"]
            self.assertTrue(entered.wait(2))
            self.manager.send(identity, "Arrived during the model request")
            gate.set()
            result = self.manager.wait([identity], 3)["agents"][0]
        self.assertEqual(len(seen), 2)
        self.assertIn("Arrived during", json.dumps(seen[1]))
        self.assertEqual(result["report"], "Follow-up handled")

    def test_completion_note_is_visible_and_injected_once_before_next_main_call(self):
        with patch.object(agent, "call_model", return_value=response("Child report")):
            identity = self.manager.start("reader", "Task")["id"]
            self.manager.wait([identity], 3)
            eventually(lambda: any(event.get("type") == "subagent_note" for event in self.events))
        self.parent.manager = self.manager
        seen = []

        def model(messages, tools):
            seen.append(json.loads(json.dumps(messages)))
            return response("Main response")

        with patch.object(agent, "PLUGINS", self.runtime), patch.object(agent, "conversation", return_value=[{"role": "system", "content": "Main prompt"}]), patch.object(agent, "call_model", side_effect=model):
            agent.run_turn([], "Next question", lambda request: True, self.events.append, agent_state=self.parent)
            agent.run_turn(self.parent.messages, "Another question", lambda request: True, self.events.append, agent_state=self.parent)
        self.assertEqual(sum("subagent notes" in item.get("content", "") for item in seen[0]), 1)
        self.assertEqual(sum("subagent notes" in item.get("content", "") for item in seen[1]), 1)
        self.assertIn("Child report", json.dumps(seen[0]))

    def test_stop_discards_late_model_action_and_cannot_resume(self):
        entered, gate = threading.Event(), threading.Event()

        def model(*args, **kwargs):
            entered.set()
            gate.wait(3)
            return response(calls=[call("bash", {"command": "never execute"})])

        with patch.object(agent, "call_model", side_effect=model), patch.object(agent, "run_bash") as shell:
            identity = self.manager.start("reader", "Task")["id"]
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.manager.stop(identity)["state"], "stopped")
            self.assertIn("cannot resume", self.manager.control("send", id=identity, message="Continue")["error"])
            gate.set()
            self.manager.threads[identity].join(2)
        shell.assert_not_called()
        self.assertEqual(self.manager.agents[identity].state, "stopped")
        self.assertEqual(len([e for e in self.events if e.get("type") == "subagent_note" and e["state"] == "stopped"]), 1)

    def test_deadline_fails_blocked_request_and_late_result_cannot_revive_it(self):
        self.manager.max_seconds = 0.03
        gate = threading.Event()

        def model(*args, **kwargs):
            gate.wait(3)
            return response("Too late")

        with patch.object(agent, "call_model", side_effect=model):
            identity = self.manager.start("reader", "Task")["id"]
            result = self.manager.wait([identity], 2)["agents"][0]
            self.assertEqual(result["state"], "failed")
            self.assertIn("max_seconds", result["failure_reason"])
            gate.set()
            self.manager.threads[identity].join(2)
        self.assertEqual(self.manager.agents[identity].state, "failed")

    def test_turn_limit_is_cumulative_across_followups_and_notifies_failure(self):
        self.runtime.agent_types["reader"] = AgentType("reader", "One turn", (), "Prompt", 1)
        with patch.object(agent, "call_model", return_value=response("First answer")) as model:
            identity = self.manager.start("reader", "Task")["id"]
            self.manager.wait([identity], 2)
            self.manager.send(identity, "Needs another model call")
            result = self.manager.wait([identity], 2)["agents"][0]
        self.assertEqual(model.call_count, 1)
        self.assertEqual(result["state"], "failed")
        self.assertIn("max_turns", result["failure_reason"])
        eventually(lambda: any(e.get("state") == "failed" for e in self.events))

    def test_idle_time_does_not_consume_active_time_budget(self):
        self.manager.max_seconds = 0.15
        with patch.object(agent, "call_model", return_value=response("Done")):
            identity = self.manager.start("reader", "Task")["id"]
            self.manager.wait([identity], 2)
            time.sleep(0.2)
            self.assertEqual(self.manager.agents[identity].state, "idle")
            self.manager.send(identity, "Follow-up")
            self.assertEqual(self.manager.wait([identity], 2)["agents"][0]["state"], "idle")

    def test_delegated_idle_agent_can_resume_as_background_job(self):
        with patch.object(agent, "call_model", return_value=response("Done")):
            identity = self.manager.delegate("reader", "Task")["id"]
            self.manager.send(identity, "Follow-up")
            result = self.manager.wait([identity], 2)["agents"][0]
        self.assertEqual((result["state"], result["turns"]), ("idle", 2))

    def test_read_truncates_each_step_and_validates_action_arguments(self):
        with patch.object(agent, "call_model", return_value=response("x" * 5000)):
            identity = self.manager.start("reader", "Task")["id"]
            self.manager.wait([identity], 2)
        steps = self.manager.read(identity, last=5)["steps"]
        self.assertTrue(any("[truncated]" in item["preview"] for item in steps))
        self.assertTrue(all(len(item["preview"]) <= 512 for item in steps))
        for action, options in (("wait", {"ids": [identity], "timeout": -1}), ("read", {"id": identity, "last": True}), ("stop", {"id": "missing"}), ("list", {"message": "extra"})):
            self.assertIn("error", self.manager.control(action, **options))

    def test_cancelled_mcp_request_cancels_only_its_future(self):
        runtime = PluginRuntime(self.root)
        future = Future()
        event = threading.Event()
        runtime.routes["fixture__read"] = (None, "read")

        def schedule(coroutine, loop):
            coroutine.close()
            event.set()
            return future

        with patch("plugin_runtime.asyncio.run_coroutine_threadsafe", side_effect=schedule):
            result = runtime.call_tool("fixture__read", {}, lambda request: True, cancel_event=event)
        self.assertTrue(future.cancelled())
        self.assertIn("stopped", result["error"])

    def test_close_stops_idle_threads_and_rejects_new_work(self):
        with patch.object(agent, "call_model", return_value=response("Done")):
            identity = self.manager.start("reader", "Task")["id"]
            self.manager.wait([identity], 2)
        self.manager.close()
        self.assertFalse(self.manager.threads[identity].is_alive())
        self.assertEqual(self.manager.agents[identity].state, "stopped")
        self.assertIn("closed", self.manager.start("reader", "Task")["error"])

    def test_stop_kills_real_shell_and_grandchild_process(self):
        self._assert_owned_processes_stop()

    @unittest.skipUnless(os.name == "nt", "Windows taskkill exit-race regression")
    def test_taskkill_exit_race_is_verified_with_process_handles(self):
        original = shell_tool.subprocess.run

        def ambiguous_status(*args, **kwargs):
            result = original(*args, **kwargs)
            if args and args[0][0] == "taskkill":
                # Still run the real kill, then simulate the ambiguous error
                # status seen when a descendant exits during tree traversal.
                result.returncode = 255
            return result

        with patch.object(shell_tool.subprocess, "run", side_effect=ambiguous_status):
            self._assert_owned_processes_stop()

    def _assert_owned_processes_stop(self):
        self.runtime.agent_types["shell-worker"] = AgentType("shell-worker", "Owned fixture", ("bash",), "Run only the assigned fixture.", 3)
        script = self.root / "nested_fixture.py"
        pid_file = self.root / "nested_pid.txt"
        script.write_text("import subprocess,sys,time\nfrom pathlib import Path\nchild=subprocess.Popen([sys.executable,'-c','import time;time.sleep(600)'])\nPath(" + repr(str(pid_file)) + ").write_text(str(child.pid))\ntime.sleep(600)\n", encoding="utf-8")
        if os.name == "nt":
            quote = lambda value: "'" + value.replace("'", "''") + "'"
            command = "& " + quote(sys.executable) + " " + quote(str(script))
        else:
            import shlex
            command = shlex.quote(sys.executable) + " " + shlex.quote(str(script))
        approvals = []
        self.manager.configure(lambda request: False, lambda request: approvals.append(request) or True, self.events.append, ())
        with patch.object(agent, "call_model", return_value=response(calls=[call("bash", {"command": command})])), patch.object(shell_tool, "WORKSPACE", self.root):
            identity = self.manager.start("shell-worker", "Run the owned nested process fixture")["id"]
            try:
                eventually(lambda: pid_file.exists(), 5)
                grandchild = int(pid_file.read_text())
                child = self.manager.agents[identity]
                shell_pid = child.process.pid
                self.assertTrue(alive(grandchild))
                self.assertTrue(approvals[0].startswith("[sa-1 · shell-worker]"))
                self.assertEqual(self.manager.list()["agents"][0]["state"], "running")
                self.assertTrue(self.manager.read(identity)["steps"])
                result = self.manager.stop(identity)
                self.assertEqual(result["state"], "stopped")
                self.assertTrue(result["process_tree_killed"])
                eventually(lambda: not alive(grandchild), 3)
                self.assertFalse(alive(shell_pid))
                self.manager.threads[identity].join(3)
            finally:
                self.manager.stop(identity)

    def test_main_model_invokes_start_list_and_wait_through_tool_dispatch(self):
        observed = []
        main_calls = 0

        def model(messages, tools, **kwargs):
            nonlocal main_calls
            if messages[0]["content"] == "Main fixture":
                main_calls += 1
                observed.append(json.loads(json.dumps(messages)))
                if main_calls == 1:
                    return response(calls=[call("subagent", {"action": "start", "agent": "reader", "task": "Fixture task"}, "start"),
                                           call("subagent", {"action": "list"}, "list"),
                                           call("subagent", {"action": "wait", "ids": ["sa-1"], "timeout": 2}, "wait")])
                return response("Combined fixture report")
            return response("Child fixture report")

        self.parent.manager = self.manager
        with patch.object(agent, "PLUGINS", self.runtime), patch.object(agent, "conversation", return_value=[{"role": "system", "content": "Main fixture"}]), patch.object(agent, "call_model", side_effect=model):
            agent.run_turn([], "Start the fixture", lambda action: True, self.events.append, agent_state=self.parent)
        results = [json.loads(item["content"]) for item in observed[-1] if item["role"] == "tool"]
        self.assertEqual(results[0]["id"], "sa-1")
        self.assertEqual(results[-1]["agents"][0]["report"], "Child fixture report")
        self.assertEqual(sum("subagent notes" in (item.get("content") or "") for item in observed[-1]), 1)
        self.assertEqual(self.parent.tokens, 48)

    def test_child_cannot_invoke_background_controls_even_with_fabricated_call(self):
        with patch.object(agent, "call_model", side_effect=[response(calls=[call("subagent", {"action": "start", "agent": "reader", "task": "Nested"})]), response("Blocked")]):
            identity = self.manager.start("reader", "Task")["id"]
            self.manager.wait([identity], 2)
        child = self.manager.agents[identity]
        self.assertEqual(len(self.manager.agents), 1)
        self.assertIn("error", json.loads(child.messages[-2]["content"]))
        self.assertEqual(child.state, "idle")

    def test_parallel_children_serialize_approval_questions(self):
        approvals_active, maximum = 0, 0
        counter_lock = threading.Lock()

        def approve(action):
            nonlocal approvals_active, maximum
            with counter_lock:
                approvals_active += 1
                maximum = max(maximum, approvals_active)
            time.sleep(0.03)
            with counter_lock:
                approvals_active -= 1
            return True

        def model(messages, tools, **kwargs):
            return response("Done") if any(item.get("role") == "tool" for item in messages) else response(calls=[call("fixture__read", {})])

        self.manager.configure(lambda action: True, approve, self.events.append, ())
        with patch.object(agent, "call_model", side_effect=model):
            ids = [self.manager.start("reader", str(index))["id"] for index in range(3)]
            self.assertFalse(self.manager.wait(ids, 3)["timed_out"])
        self.assertEqual(maximum, 1)

    def test_followup_racing_a_model_failure_never_restarts_failed_worker(self):
        entered, release, failure_recorded = threading.Event(), threading.Event(), threading.Event()

        def model(*args, **kwargs):
            entered.set()
            release.wait(3)
            raise RuntimeError("Synthetic model failure")

        with patch.object(agent, "call_model", side_effect=model) as calls:
            identity = self.manager.start("reader", "Task")["id"]
            self.assertTrue(entered.wait(2))
            child = self.manager.agents[identity]
            original_put, original_record = child.inbox.put, child.record

            def record(kind, payload):
                if kind == "failed":
                    failure_recorded.set()
                return original_record(kind, payload)

            def put(message):
                release.set()
                failure_recorded.wait(0.1)
                return original_put(message)

            with patch.object(child, "record", side_effect=record), patch.object(child.inbox, "put", side_effect=put):
                self.manager.send(identity, "Follow-up arriving at failure")
                result = self.manager.wait([identity], 2)["agents"][0]
            self.manager.threads[identity].join(2)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(calls.call_count, 1)


class InterfaceBackgroundTests(unittest.TestCase):
    def test_web_approval_cancel_resolves_and_deleted_chat_cannot_resurrect(self):
        with tempfile.TemporaryDirectory() as directory:
            history = ChatHistory(Path(directory) / "chats.sqlite3")
            chat = history.create()
            stop = threading.Event()
            decisions = []
            thread = threading.Thread(target=lambda: decisions.append(chat.approve("[sa-1] fixture", cancel_event=stop)), daemon=True)
            thread.start()
            eventually(lambda: chat.pending)
            stop.set()
            thread.join(2)
            self.assertEqual(decisions, [False])
            self.assertIsNone(chat.pending)
            self.assertTrue(history.delete(chat.id))
            chat.emit({"type": "subagent_note", "text": "Late note"})
            self.assertIsNone(ChatHistory(history.store.path).get(chat.id))

    def test_web_agents_command_does_not_call_model(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = ChatHistory(Path(directory) / "chats.sqlite3").create()
            with patch.object(agent, "call_model") as model:
                self.assertTrue(chat.start("/agents"))
            model.assert_not_called()
            self.assertEqual(chat.events[-1]["result"], {"agents": []})

    def test_phone_can_cancel_a_child_approval_before_polling(self):
        runtime = PhoneRuntime()
        mode = TelegramMode(runtime, auto_approve=True)
        mode.pending.append(message("Keep my queued question"))
        stop = threading.Event()
        stop.set()
        self.assertFalse(mode.approve_subagent("[sa-1] fixture", cancel_event=stop))
        self.assertTrue(any("stopped" in text.lower() for text in runtime.sent))
        self.assertEqual(mode.pending[0]["text"], "Keep my queued question")

    def test_main_web_turn_completion_keeps_background_approval_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = ChatHistory(Path(directory) / "chats.sqlite3").create()
            pending = {"id": "child-approval", "ready": threading.Event(), "decision": False}
            chat.pending = pending
            with patch("history.run_turn"):
                chat.work("Fixture question")
            self.assertIs(chat.pending, pending)

    def test_phone_approval_uses_reply_already_queued_by_main_poller(self):
        runtime = PhoneRuntime()
        mode = TelegramMode(runtime, auto_approve=True)
        mode.pending.append(message("yes", 101))
        self.assertTrue(mode.approve_subagent("[sa-1] fixture"))


if __name__ == "__main__":
    unittest.main()
