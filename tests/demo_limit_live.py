"""Live max_turns demo using the configured model and read-only PSP tools.

The type requests three sequential tool rounds followed by a fourth reporting
response. Production limits must stop it after the third model response.
No model responses, failures or lifecycle notes are synthesized by this helper.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent
from plugin_runtime import PluginRuntime
from subagents import SubagentManager


def run_demo(runtime):
    worker = agent.Agent(runtime=runtime, max_seconds=None)
    manager = SubagentManager(worker, ROOT)
    worker.manager = manager
    messages, events, actions = [], [], []
    lock = threading.RLock()
    original = manager.control

    def control(action, **arguments):
        if action not in {"start", "list", "wait", "read"}:
            return {"error": "This limit demo allows one start, list, wait and read."}
        if action == "start" and (arguments.get("agent") != "turn-limit-demo" or manager.agents):
            return {"error": "Start exactly one turn-limit-demo worker."}
        result = original(action, **arguments)
        with lock:
            actions.append({"at_utc": datetime.now(timezone.utc).isoformat(),
                            "action": action, "arguments": arguments, "result": result})
        return result

    manager.control = control

    def emit(event):
        with lock:
            events.append(event)
        if event.get("type") in {"usage", "subagent_note"}:
            print(event["text"], flush=True)

    try:
        agent.run_turn(messages,
            "Demonstrate the turn limit. Start exactly one turn-limit-demo worker with this task: "
            "Follow your four-step workflow: list intervals, analyze the first listed ID, compare that "
            "ID with the other, and only after reading the comparison write your final report. Use exactly "
            "one tool call per model response. Then wait for the worker, repeating wait if it times out. "
            "Report its observed state and exact failure reason. Do not start replacements or finish "
            "its research yourself. It has max_turns 3, so a fourth reporting response is beyond its limit.",
            lambda request: False, emit, agent_state=worker,
            hidden_tools=("email__send_message", "telegram__wait_for_messages"),
            main_hidden_tools=("bash", "delegate", *(tool["function"]["name"] for tool in runtime.tools)))
        child = manager.agents.get("sa-1")
        records = [json.loads(line) for line in child.log_path.read_text(encoding="utf-8").splitlines()] if child else []
        responses = [message for message in (child.messages if child else []) if message.get("role") == "assistant"]
        call_rounds = [[call["function"]["name"] for call in message.get("tool_calls", [])] for message in responses]
        expected = [["psp_waves__list_psp_intervals"], ["psp_waves__analyze_psp_waves"],
                    ["psp_waves__compare_psp_wave_intervals"]]
        notes = [event["text"] for event in events if event.get("type") == "subagent_note"]
        observed_notes = [message.get("content", "") for message in messages if message.get("role") == "user"
                          and "[subagent notes" in message.get("content", "")]
        checks = {"one_worker": len(manager.agents) == 1,
                  "three_turn_limit": bool(child and child.max_turns == 3 and child.turns == 3),
                  "three_sequential_tool_rounds": call_rounds == expected,
                  "only_three_model_calls": sum(record["kind"] == "model_call_started" for record in records) == 3,
                  "state_failed": bool(child and child.state == "failed"),
                  "failure_names_turn_limit": bool(child and "max_turns" in (child.failure_reason or "")),
                  "failure_note_shown": any("failed" in note and "max_turns" in note for note in notes),
                  "failure_note_in_main_context": any("failed" in note and "max_turns" in note for note in observed_notes)}
        receipt = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "passed": all(checks.values()),
                   "session": manager.session, "checks": checks, "child_turns": child.turns if child else None,
                   "failure_reason": child.failure_reason if child else None, "call_rounds": call_rounds,
                   "main_report": worker.report, "lifecycle_notes": notes}
        (ROOT / "validation/week-4-demo-5.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        (ROOT / "validation/week-4-private/demo-5-main-conversation.json").write_text(json.dumps(messages, indent=2) + "\n", encoding="utf-8")
        lines = ["# Demo 5: enforce a three-turn limit", "",
                 "Live configured model: `" + os.environ["MODEL"] + "`.", "",
                 "The task requires three sequential read-only tool responses and a fourth reporting response. "
                 "The type sets max_turns: 3. The helper observes production enforcement without synthesizing responses.", ""]
        for item in actions:
            lines += ["## Main tool action", "", "```json", json.dumps(item, ensure_ascii=False, indent=2), "```", ""]
        for event in events:
            if event.get("type") in {"assistant", "subagent_note"}:
                lines += ["## Main answer or lifecycle note", "", "```text", event["text"], "```", ""]
        lines += ["## Verification", "", "```json", json.dumps(receipt, ensure_ascii=False, indent=2), "```", ""]
        for directory in (ROOT / "transcripts",):
            (directory / "05-turn-limit.md").write_text("\n".join(lines), encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=True, indent=2), flush=True)
    finally:
        manager.close()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if separator and re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            if len(value) > 1 and value[0] == value[-1] and value[0] in {"\"", "'"}:
                value = value[1:-1]
            os.environ[key] = value
    runtime = PluginRuntime(ROOT)
    runtime.servers = [item for item in runtime.servers if item[0] in {"email", "psp_waves"}]
    with runtime:
        agent.PLUGINS = runtime
        try:
            run_demo(runtime)
        finally:
            agent.PLUGINS = None


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError):
        print("Limit demo failed; do not claim success. Credential values were not displayed.", file=sys.stderr)
        sys.exit(1)
