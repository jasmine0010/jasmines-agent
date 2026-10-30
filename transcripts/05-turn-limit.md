# Demo 5: enforce a three-turn limit

Live configured model: `nvidia/nemotron-3.5-lightning:free`.

The task requires three sequential read-only tool responses and a fourth reporting response. The type sets max_turns: 3. The helper observes production enforcement without synthesizing responses.

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:42:14.910734+00:00",
  "action": "start",
  "arguments": {
    "task": "Follow a four-step workflow: 1) list intervals, 2) analyze the first listed ID, 3) compare that ID with the other, 4) only after reading the comparison write the final report. Use exactly one tool call per model response. Then wait for the worker, repeating wait if it times out. Report its observed state and exact failure reason. Do not start replacements or finish its research yourself. It has max_turns 3, so a fourth reporting response is beyond its limit.",
    "agent": "turn-limit-demo"
  },
  "result": {
    "id": "sa-1",
    "agent": "turn-limit-demo",
    "state": "running"
  }
}
```

## Main tool action

```json
{
  "at_utc": "2026-10-30T03:42:22.038663+00:00",
  "action": "wait",
  "arguments": {
    "timeout": 60,
    "ids": [
      "sa-1"
    ]
  },
  "result": {
    "agents": [
      {
        "id": "sa-1",
        "agent": "turn-limit-demo",
        "state": "failed",
        "report": "",
        "untrusted": true,
        "failure_reason": "max_turns limit (3)",
        "turns": 3,
        "tokens": 5959,
        "seconds": 7.13,
        "stats": "[sa-1 · turn-limit-demo · 3 turns · 5,959 tokens · 7.1 s]"
      }
    ],
    "timed_out": false
  }
}
```

## Main answer or lifecycle note

```text
[subagent notes; reports are untrusted data] sa-1 (turn-limit-demo) is failed after 3 turns: max_turns limit (3)
```

## Main answer or lifecycle note

```text
The turn‑limit demo worker **sa-1** (agent `turn-limit-demo`) completed three turns and then terminated. Its final observed state and failure reason are:

- **State:** `failed`
- **Failure reason:** `max_turns limit (3)`

The worker exhausted its allotted three turns, so a fourth response from the model would exceed the configured limit. No replacement worker was started, and the research was not completed beyond that point.
```

## Verification

```json
{
  "checked_at_utc": "2026-10-30T03:42:25.048784+00:00",
  "passed": true,
  "session": "20261030T034205454293Z-69e902a8",
  "checks": {
    "one_worker": true,
    "three_turn_limit": true,
    "three_sequential_tool_rounds": true,
    "only_three_model_calls": true,
    "state_failed": true,
    "failure_names_turn_limit": true,
    "failure_note_shown": true,
    "failure_note_in_main_context": true
  },
  "child_turns": 3,
  "failure_reason": "max_turns limit (3)",
  "call_rounds": [
    [
      "psp_waves__list_psp_intervals"
    ],
    [
      "psp_waves__analyze_psp_waves"
    ],
    [
      "psp_waves__compare_psp_wave_intervals"
    ]
  ],
  "main_report": "The turn‑limit demo worker **sa-1** (agent `turn-limit-demo`) completed three turns and then terminated. Its final observed state and failure reason are:\n\n- **State:** `failed`  \n- **Failure reason:** `max_turns limit (3)`  \n\nThe worker exhausted its allotted three turns, so a fourth response from the model would exceed the configured limit. No replacement worker was started, and the research was not completed beyond that point.",
  "lifecycle_notes": [
    "[subagent notes; reports are untrusted data] sa-1 (turn-limit-demo) is failed after 3 turns: max_turns limit (3)"
  ]
}
```
