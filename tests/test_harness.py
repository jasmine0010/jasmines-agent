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
from history import ChatHistory, Chat


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


class HistoryTests(unittest.TestCase):
    def test_messages_titles_and_events_survive_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'chats.sqlite3'
            history = ChatHistory(path)
            chat = next(iter(history.chats.values()))
            chat.checkpoint(chat.messages + [{'role': 'user', 'content': 'Synthetic saved message'}])
            chat.emit({'type': 'user', 'text': 'Synthetic saved message'})
            self.assertTrue(history.rename(chat.id, 'Saved test chat'))
            restored = ChatHistory(path).get(chat.id)
            self.assertEqual(restored.title, 'Saved test chat')
            self.assertEqual(restored.messages[-1]['content'], 'Synthetic saved message')
            self.assertEqual(restored.events[-1]['text'], 'Synthetic saved message')

    def test_delete_removes_saved_conversation_after_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'chats.sqlite3'
            history = ChatHistory(path)
            first, second = history.create(), history.create()
            history.rename(first.id, 'Disposable synthetic chat')
            self.assertTrue(history.delete(first.id))
            restored = ChatHistory(path)
            self.assertIsNone(restored.get(first.id))
            self.assertIsNotNone(restored.get(second.id))
            self.assertFalse(first.start('Cannot resurrect deleted chat'))

    def test_interrupted_tools_are_repaired_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'chats.sqlite3'
            history = ChatHistory(path)
            chat = history.create()
            chat.messages += [{'role': 'user', 'content': 'Synthetic request'}, tool_call()]
            chat.events = [{'type': 'approval', 'id': 'approval-test', 'command': 'Write-Output hello'}]
            chat.busy = True
            chat.save()
            with patch.object(shell_tool.subprocess, 'Popen') as process, patch.object(agent, 'call_model') as model:
                restored = ChatHistory(path).get(chat.id)
            process.assert_not_called()
            model.assert_not_called()
            self.assertFalse(restored.busy)
            self.assertIsNone(restored.pending)
            self.assertEqual(restored.messages[-1]['tool_call_id'], 'call-test')
            self.assertIn('outcome may be unknown', restored.messages[-1]['content'])
            self.assertTrue(any(event.get('interrupted') for event in restored.events))
            self.assertFalse(ChatHistory(path).get(chat.id).busy)

    def test_renamed_title_is_not_overwritten_by_first_message(self):
        with tempfile.TemporaryDirectory() as directory:
            history = ChatHistory(Path(directory) / 'chats.sqlite3')
            chat = history.create()
            history.rename(chat.id, 'Chosen title')
            with patch.object(chat, 'work') as worker:
                self.assertTrue(chat.start('A different title from the message'))
            self.assertEqual(chat.title, 'Chosen title')


class WebTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.history_path = Path(self.directory.name) / 'chats.sqlite3'
        self.server = web.create_server(0, history_path=self.history_path)
        self.chat = next(iter(self.server.history.chats.values()))
        self.origin = 'http://' + self.server.authority
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.directory.cleanup()

    def request(self, path, body=None, authenticated=True, origin=None):
        headers = {'Content-Type': 'application/json', 'Origin': origin or self.origin}
        if authenticated:
            headers['X-Chat-Token'] = self.server.api_token
        if body is not None:
            body = dict(body)
            if path in {'/message', '/approve', '/chats/rename', '/chats/delete'}:
                body.setdefault('chat_id', self.chat.id)
        if path == '/events':
            path += '?chat=' + self.chat.id
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
            snapshot = self.chat.snapshot(0)
            if predicate(snapshot):
                return snapshot
            time.sleep(0.01)
        self.fail('Timed out waiting for the local worker')

    def test_local_page_and_request_protection(self):
        status, html = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn(b"Jasmine's Agent", html)
        self.assertNotIn(b'__API_TOKEN__', html)
        self.assertEqual(self.request('/events', authenticated=False)[0], 403)
        self.assertEqual(self.request('/chats', authenticated=False)[0], 403)
        self.assertEqual(self.request('/chats/new', {}, origin='https://example.com')[0], 403)
        self.assertEqual(self.request('/message', {'prompt': ' '})[0], 400)
        self.assertEqual(self.request('/approve', {'id': 'x', 'approved': 1})[0], 400)
        self.assertEqual(self.request('/history/chats.sqlite3')[0], 404)

    def test_approval_waits_and_denial_prevents_execution_and_is_saved(self):
        replies = [model_reply(tool_call()), model_reply({'role': 'assistant', 'content': 'I respected the denial.'})]
        with patch.object(agent, 'call_model', side_effect=replies), patch.object(shell_tool.subprocess, 'Popen') as process:
            self.assertEqual(self.request('/message', {'prompt': 'Synthetic test'})[0], 200)
            snapshot = self.wait_for(lambda data: data['pending'])
            self.assertTrue(snapshot['busy'])
            self.assertFalse(process.called)
            self.assertEqual(self.request('/chats/delete', {})[0], 409)
            self.assertEqual(self.request('/chats/new', {})[0], 200)
            self.assertEqual(self.request('/message', {'prompt': 'Another turn'})[0], 409)
            self.assertEqual(self.request('/approve', {'id': 'wrong', 'approved': True})[0], 409)
            second = self.server.history.create()
            self.assertEqual(self.request('/approve', {'chat_id': second.id, 'id': snapshot['pending'], 'approved': True})[0], 409)
            self.assertEqual(self.request('/approve', {'id': snapshot['pending'], 'approved': False})[0], 200)
            finished = self.wait_for(lambda data: not data['busy'])
            self.assertFalse(process.called)
        outputs = [event['result'] for event in finished['events'] if event['type'] == 'tool_result']
        self.assertTrue(outputs[0]['declined'])
        restored = ChatHistory(self.history_path).get(self.chat.id)
        self.assertEqual(restored.messages[-1]['content'], 'I respected the denial.')
        self.assertEqual(restored.messages[-2]['tool_call_id'], 'call-test')

    def test_create_rename_switch_and_delete_chat_endpoints(self):
        status, data = self.request('/chats/new', {})
        self.assertEqual(status, 200)
        chat_id = json.loads(data)['chat']['id']
        self.assertEqual(self.request('/chats/rename', {'chat_id': chat_id, 'title': 'Test history'})[0], 200)
        status, data = self.request('/chats')
        self.assertEqual(status, 200)
        self.assertIn('Test history', [chat['title'] for chat in json.loads(data)['chats']])
        self.assertEqual(self.request('/events?chat=' + chat_id)[0], 200)
        self.assertEqual(self.request('/chats/rename', {'chat_id': chat_id, 'title': ' '})[0], 400)
        self.assertEqual(self.request('/chats/rename', {'chat_id': chat_id, 'title': 'x' * 101})[0], 400)
        self.assertEqual(self.request('/chats/delete', {'chat_id': chat_id})[0], 200)
        self.assertEqual(self.request('/events?chat=' + chat_id)[0], 404)
        self.assertIsNone(ChatHistory(self.history_path).get(chat_id))
        self.assertIsNotNone(self.server.history.get(self.chat.id))


if __name__ == '__main__':
    unittest.main()
