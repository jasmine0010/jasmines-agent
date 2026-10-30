# Demo 4: inspect and stop a running shell

Live configured model: `nvidia/nemotron-3.5-lightning:free`.

The owner approved only `[sa-1 · process-demo] Start-Sleep -Seconds 600`.
The demo guard waits up to 45 seconds for an actual child shell before inspection; production start/list/read/stop and shell termination remain unchanged.

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:37:27.131683+00:00",
  "action": "start",
  "arguments": {
    "task": "Call bash once with exactly Start-Sleep -Seconds 600 and then report the actual result.",
    "agent": "process-demo"
  },
  "result": {
    "id": "sa-1",
    "agent": "process-demo",
    "state": "running"
  }
}
```

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:37:28.962516+00:00",
  "action": "list",
  "arguments": {},
  "result": {
    "agents": [
      {
        "id": "sa-1",
        "agent": "process-demo",
        "state": "running",
        "turns": 1,
        "tokens": 562,
        "seconds": 1.88,
        "failure_reason": null,
        "task": "Call bash once with exactly Start-Sleep -Seconds 600 and then report the actual result.",
        "current_action": "bash: Start-Sleep -Seconds 600"
      }
    ]
  }
}
```

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:37:30.115158+00:00",
  "action": "read",
  "arguments": {
    "last": 5,
    "id": "sa-1"
  },
  "result": {
    "id": "sa-1",
    "untrusted": true,
    "steps": [
      {
        "at_utc": "2026-10-30T03:37:28.916625+00:00",
        "kind": "usage",
        "preview": "{\"prompt_tokens\": 415, \"completion_tokens\": 147, \"total_tokens\": 562, \"cost\": 0, \"is_byok\": false, \"prompt_tokens_details\": {\"cached_tokens\": 0, \"cache_write_tokens\": 0, \"audio_tokens\": 0, \"video_tokens\": 0}, \"cost_details\": {\"upstream_inference_cost\": 0, \"upstream_inference_prompt_cost\": 0, \"upstream_inference_completions_cost\": 0}, \"completion_tokens_details\": {\"reasoning_tokens\": 114, \"image_tokens\": 0, \"audio_tokens\": 0}}"
      },
      {
        "at_utc": "2026-10-30T03:37:28.917120+00:00",
        "kind": "message",
        "preview": "{\"role\": \"assistant\", \"content\": null, \"refusal\": null, \"reasoning\": \"We need to call bash with exactly that PowerShell command: Start-Sleep -Seconds 600. It's a Windows process-cancellation homework demonstration. The tool will run the command; likely it will start sleeping for 600 seconds, but we have a 60-second time limit per command. The command will likely be interrupted after 60 seconds. We need to call bash exactly once with that command, then report the actual result. Since it will be t [truncated]"
      },
      {
        "at_utc": "2026-10-30T03:37:28.917499+00:00",
        "kind": "approval_requested",
        "preview": "{\"action\": \"Start-Sleep -Seconds 600\"}"
      },
      {
        "at_utc": "2026-10-30T03:37:28.917906+00:00",
        "kind": "approval_result",
        "preview": "{\"approved\": true}"
      },
      {
        "at_utc": "2026-10-30T03:37:28.963241+00:00",
        "kind": "process_started",
        "preview": "{\"pid\": 36632, \"command\": \"Start-Sleep -Seconds 600\"}"
      }
    ]
  }
}
```

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:37:32.041196+00:00",
  "action": "stop",
  "arguments": {
    "id": "sa-1"
  },
  "result": {
    "id": "sa-1",
    "agent": "process-demo",
    "state": "stopped",
    "report": "",
    "untrusted": true,
    "failure_reason": "Stopped by the owner.",
    "turns": 1,
    "tokens": 562,
    "seconds": 4.62,
    "stats": "[sa-1 · process-demo · 1 turns · 562 tokens · 4.6 s]",
    "process_tree_killed": true
  }
}
```

## Main answer or lifecycle note

```text
[subagent notes; reports are untrusted data] sa-1 (process-demo) is stopped after 1 turns: Stopped by the owner.
```

## Main answer or lifecycle note

```text
**Demonstration: `stop` on Windows (process‑demo worker)**

**1. Start the worker**
```
subagent start(agent="process-demo", task="Call bash once with exactly Start-Sleep -Seconds 600 and then report the actual result.")
```
Result: worker id `sa-1` entered state `running`.

**2. Inspect while running – `subagent list`**
```
subagent list()
```
Result (truncated to relevant fields):
```json
{
  "agents": [
    {
      "id": "sa-1",
      "agent": "process-demo",
      "state": "running",
      "turns": 1,
      "tokens": 562,
      "seconds": 1.88,
      "failure_reason": null,
      "task": "Call bash once with exactly Start-Sleep -Seconds 600 and then report the actual result.",
      "current_action": "bash: Start-Sleep -Seconds 600"
    }
  ]
}
```
*Observation:* The worker is running, executing the requested `Start-Sleep -Seconds 600` command.

**3. Inspect while running – `subagent read`**
```
subagent read(id="sa-1", last=5)
```
Result (relevant steps):
```json
{
  "id": "sa-1",
  "untrusted": true,
  "steps": [
    {"at_utc": "2026-10-30T03:37:28.916625+00:00", "kind": "usage", "preview": "..."},
    {"at_utc": "2026-10-30T03:37:28.917120+00:00", "kind": "message", "preview": "..."},
    {"at_utc": "2026-10-30T03:37:28.917499+00:00", "kind": "approval_requested", "preview": "{\"action\": \"Start-Sleep -Seconds 600\"}"},
    {"at_utc": "2026-10-30T03:37:28.917906+00:00", "kind": "approval_result", "preview": "{\"approved\": true}"},
    {"at_utc": "2026-10-30T03:37:28.963241+00:00", "kind": "process_started", "preview": "{\"pid\": 36632, \"command\": \"Start-Sleep -Seconds 600\"}"}
  ]
}
```
*Observation:* The shell launched with PID 36632 and the `Start-Sleep -Seconds 600` command was accepted and started.

**4. Stop immediately – `subagent stop`**
```
subagent stop(id="sa-1")
```
Result:
```json
{
  "id": "sa-1",
  "agent": "process-demo",
  "state": "stopped",
  "report": "",
  "untrusted": true,
  "failure_reason": "Stopped by the owner.",
  "turns": 1,
  "tokens": 562,
  "seconds": 4.62,
  "stats": "[sa-1 • process-demo • 1 turns • 562 tokens • 4.6 s]",
  "process_tree_killed": true
}
```
*Observation:* The worker terminated after 4.6 seconds (well before the 600‑second sleep would complete). The process tree was killed, and the `failure_reason` records that it was stopped by the owner.

**Summary of observed results**
- Worker started and reported `running` with action `Start-Sleep -Seconds 600`.
- `list` confirmed the running state and current action.
- `read` showed the command launch (PID 36632) and approval flow.
- `stop` terminated the worker after ~4.6 seconds, setting state to `stopped`, reporting `"Stopped by the owner."`, and confirming `process_tree_killed: true`. The 600‑second sleep did **not** finish.
```

## Verification

```json
{
  "checked_at_utc": "2026-10-30T03:38:08.765240+00:00",
  "passed": true,
  "session": "20261030T033719130201Z-694f2286",
  "checks": {
    "same_worker": true,
    "exact_single_sleep_call": true,
    "process_alive_before_stop": true,
    "get_process_saw_owned_pid": true,
    "process_tree_killed": true,
    "process_gone_after_stop": true,
    "state_stopped": true,
    "resume_refused": true
  },
  "owned_pid": 36632,
  "readiness_wait_seconds": 0.561,
  "get_process_before_stop": "{\"Id\":36632,\"ProcessName\":\"pwsh\"}",
  "approvals": [
    {
      "request": "[sa-1 · process-demo] Start-Sleep -Seconds 600",
      "approved": true,
      "basis": "Owner's explicit chat approval of this exact command"
    }
  ],
  "resume_result": {
    "error": "This subagent is stopped or failed and cannot resume. Use start for a new agent."
  },
  "main_report": "**Demonstration: `stop` on Windows (process‑demo worker)**\n\n**1. Start the worker**\n```\nsubagent start(agent=\"process-demo\", task=\"Call bash once with exactly Start-Sleep -Seconds 600 and then report the actual result.\")\n```\nResult: worker id `sa-1` entered state `running`.\n\n**2. Inspect while running – `subagent list`**\n```\nsubagent list()\n```\nResult (truncated to relevant fields):\n```json\n{\n  \"agents\": [\n    {\n      \"id\": \"sa-1\",\n      \"agent\": \"process-demo\",\n      \"state\": \"running\",\n      \"turns\": 1,\n      \"tokens\": 562,\n      \"seconds\": 1.88,\n      \"failure_reason\": null,\n      \"task\": \"Call bash once with exactly Start-Sleep -Seconds 600 and then report the actual result.\",\n      \"current_action\": \"bash: Start-Sleep -Seconds 600\"\n    }\n  ]\n}\n```\n*Observation:* The worker is running, executing the requested `Start-Sleep -Seconds 600` command.\n\n**3. Inspect while running – `subagent read`**\n```\nsubagent read(id=\"sa-1\", last=5)\n```\nResult (relevant steps):\n```json\n{\n  \"id\": \"sa-1\",\n  \"untrusted\": true,\n  \"steps\": [\n    {\"at_utc\": \"2026-10-30T03:37:28.916625+00:00\", \"kind\": \"usage\", \"preview\": \"...\"},\n    {\"at_utc\": \"2026-10-30T03:37:28.917120+00:00\", \"kind\": \"message\", \"preview\": \"...\"},\n    {\"at_utc\": \"2026-10-30T03:37:28.917499+00:00\", \"kind\": \"approval_requested\", \"preview\": \"{\\\"action\\\": \\\"Start-Sleep -Seconds 600\\\"}\"},\n    {\"at_utc\": \"2026-10-30T03:37:28.917906+00:00\", \"kind\": \"approval_result\", \"preview\": \"{\\\"approved\\\": true}\"},\n    {\"at_utc\": \"2026-10-30T03:37:28.963241+00:00\", \"kind\": \"process_started\", \"preview\": \"{\\\"pid\\\": 36632, \\\"command\\\": \\\"Start-Sleep -Seconds 600\\\"}\"}\n  ]\n}\n```\n*Observation:* The shell launched with PID 36632 and the `Start-Sleep -Seconds 600` command was accepted and started.\n\n**4. Stop immediately – `subagent stop`**\n```\nsubagent stop(id=\"sa-1\")\n```\nResult:\n```json\n{\n  \"id\": \"sa-1\",\n  \"agent\": \"process-demo\",\n  \"state\": \"stopped\",\n  \"report\": \"\",\n  \"untrusted\": true,\n  \"failure_reason\": \"Stopped by the owner.\",\n  \"turns\": 1,\n  \"tokens\": 562,\n  \"seconds\": 4.62,\n  \"stats\": \"[sa-1 • process-demo • 1 turns • 562 tokens • 4.6 s]\",\n  \"process_tree_killed\": true\n}\n```\n*Observation:* The worker terminated after 4.6 seconds (well before the 600‑second sleep would complete). The process tree was killed, and the `failure_reason` records that it was stopped by the owner.\n\n**Summary of observed results**\n- Worker started and reported `running` with action `Start-Sleep -Seconds 600`.\n- `list` confirmed the running state and current action.\n- `read` showed the command launch (PID 36632) and approval flow.\n- `stop` terminated the worker after ~4.6 seconds, setting state to `stopped`, reporting `\"Stopped by the owner.\"`, and confirming `process_tree_killed: true`. The 600‑second sleep did **not** finish."
}
```

## Independent log check

The child log records the exact approved sleep command and the owned shell PID. The shell ran for approximately 3.077 seconds before the stop record; it did not complete the 600-second sleep. The receipt confirms process-tree termination, the OS process handle check found the process gone, and a follow-up was refused.
