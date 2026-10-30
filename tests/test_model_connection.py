"""Transient model retries must never rerun a completed tool action."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import agent

SETTINGS = {'BASE_URL': 'https://synthetic.invalid/v1', 'API_KEY': 'synthetic-key', 'MODEL': 'synthetic-model'}


def response(message):
    return io.StringIO(json.dumps({'choices': [{'message': message}]}))


class ModelConnectionTests(unittest.TestCase):
    def test_retry_resends_model_request_without_reexecuting_completed_shell(self):
        first = {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'action', 'function': {'name': 'bash', 'arguments': '{"command":"synthetic command"}'}}]}
        responses = [response(first), TimeoutError(), response({'role': 'assistant', 'content': 'Done'})]
        with patch.dict('os.environ', SETTINGS), patch.object(agent, 'urlopen', side_effect=responses) as request, patch.object(agent.time, 'sleep'), patch.object(agent, 'run_bash', return_value={'stdout': 'saved result', 'exit_code': 0}) as shell:
            messages = agent.conversation()
            agent.run_turn(messages, 'Synthetic test', lambda action: True, lambda event: None)
        shell.assert_called_once()
        self.assertEqual(request.call_count, 3)
        self.assertEqual(request.call_args_list[1].args[0].data, request.call_args_list[2].args[0].data)
        self.assertIn('saved result', messages[-2]['content'])
        self.assertEqual(messages[-1]['content'], 'Done')

    def test_repeated_network_error_is_bounded_and_does_not_expose_provider_detail(self):
        with patch.dict('os.environ', SETTINGS), patch.object(agent, 'urlopen', side_effect=URLError('synthetic-key should not leak')) as request, patch.object(agent.time, 'sleep'):
            with self.assertRaises(agent.ModelUnavailable) as caught:
                agent.call_model([])
        self.assertEqual(request.call_count, 2)
        self.assertNotIn('synthetic-key', str(caught.exception))

    def test_auth_and_quota_errors_are_not_retried(self):
        for code in (401, 429):
            with self.subTest(code=code), patch.dict('os.environ', SETTINGS), patch.object(agent, 'urlopen', side_effect=HTTPError('https://synthetic.invalid', code, 'test', {}, None)) as request, patch.object(agent.time, 'sleep') as sleep:
                with self.assertRaisesRegex(RuntimeError, str(code)):
                    agent.call_model([])
                self.assertEqual(request.call_count, 1)
                sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
