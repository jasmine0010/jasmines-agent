"""Opt-in live acceptance checks. Uses API requests; approves only exact synthetic commands."""

import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent
import shell_tool

WINDOWS = os.name == 'nt'
LIST = 'Get-ChildItem -Name' if WINDOWS else 'ls -1'
FIRST = 'Write-Output first-step' if WINDOWS else 'printf first-step'
SECOND = 'Write-Output second-step' if WINDOWS else 'printf second-step'
DENIED = 'Write-Output denied-test' if WINDOWS else 'printf denied-test'


def scenario(name, prompt, allowed):
    events, decisions, calls = [], [], []
    real_call = agent.call_model

    def model(messages, tools=None):
        result = real_call(messages, tools)
        calls.append({'model': result.get('model'), 'usage': result.get('usage'),
                      'message_count': len(messages)})
        return result

    def approve(command):
        approved = command.strip() in allowed
        decisions.append({'command': command, 'approved': approved})
        print(('APPROVE: ' if approved else 'DENY: ') + command)
        return approved

    messages = agent.conversation()
    with patch.object(agent, 'call_model', side_effect=model):
        agent.run_turn(messages, prompt, approve, events.append)
    outputs = [event['result'] for event in events if event['type'] == 'tool_result']
    assert messages[-1]['role'] == 'assistant' and not messages[-1].get('tool_calls'), 'The model did not finish with a text answer'
    assert not any(event['type'] == 'error' for event in events), 'The loop reported an error'
    for call in calls:
        assert call['usage'] and 'prompt_tokens' in call['usage'] and 'completion_tokens' in call['usage'], 'Missing token usage'
    return {'name': name, 'model_calls': calls, 'decisions': decisions, 'outputs': outputs,
            'answer': messages[-1].get('content') or ''}


def main():
    records = []
    workspace = ROOT / 'workspace'
    workspace.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='acceptance-', dir=workspace) as folder:
        fixture = Path(folder).resolve()
        assert fixture.is_relative_to(workspace.resolve()) and fixture != workspace.resolve()
        (fixture / 'alpha.txt').write_text('Synthetic acceptance fixture.\n', encoding='utf-8')
        (fixture / 'beta.csv').write_text('x,y\n1,2\n', encoding='utf-8')
        with patch.object(shell_tool, 'WORKSPACE', fixture):
            result = scenario('file_listing', f'Actually call bash exactly once with command {LIST}. Then report the filenames from its output. Do not guess or read file contents.', {LIST})
            assert len(result['outputs']) == 1 and result['outputs'][0].get('exit_code') == 0
            assert all(name in result['outputs'][0]['stdout'] for name in ('alpha.txt', 'beta.csv'))
            records.append(result)
            print('PASS: live file listing')

            result = scenario('sequential_commands', f'First call bash with exactly {FIRST}. Wait until its tool result is returned. Only then, in a later model reply, call bash with exactly {SECOND}. Do not batch both calls in one reply. After both results, state both outputs. Use no other commands.', {FIRST, SECOND})
            successful = [output for output in result['outputs'] if output.get('exit_code') == 0]
            assert len(successful) == 2 and len(result['model_calls']) >= 3, 'Expected two sequential tool rounds'
            assert successful[0]['stdout'].strip() == 'first-step' and successful[1]['stdout'].strip() == 'second-step'
            assert len(result['decisions']) == 2 and all(item['approved'] for item in result['decisions'])
            records.append(result)
            print('PASS: separately approved sequential commands')

            result = scenario('failed_command_recovery', 'Actually call bash once with exactly doesnotexist. After the result, explain the failure in plain text. Do not install anything or run another command; this is an intentional missing-program test.', {'doesnotexist'})
            assert len(result['outputs']) == 1 and result['outputs'][0].get('exit_code') not in (None, 0)
            assert result['outputs'][0].get('stderr') and result['answer'].strip()
            records.append(result)
            print('PASS: real failed-command output returned to the model and explained')

            with patch.object(shell_tool.subprocess, 'Popen') as process:
                result = scenario('denial', f'Actually call bash once with exactly {DENIED}. If declined, respect that decision and answer without another command.', set())
                assert not process.called, 'A denied command reached process execution'
            assert len(result['outputs']) == 1 and result['outputs'][0].get('declined')
            records.append(result)
            print('PASS: live denial without command execution')
        # Verify the recursive-cleanup target before TemporaryDirectory removes it.
        assert fixture.resolve().is_relative_to(workspace.resolve()) and fixture.resolve() != workspace.resolve()
    output = ROOT / 'validation' / 'live-checks.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({'checked_at': datetime.now(timezone.utc).isoformat(),
                                 'platform': 'Windows' if WINDOWS else sys.platform,
                                 'scope': 'Synthetic fixture; no home-directory scan; exact test-command approvals only.',
                                 'checks': records}, indent=2) + '\n', encoding='utf-8')
    print('PASS: all four live checks; token usage recorded for every call.')


if __name__ == '__main__':
    main()
