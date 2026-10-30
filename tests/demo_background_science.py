"""Live demos 2/3, retaining worker contexts across the owner's checkpoint.

Only the configured model and public bundled PSP measurements are used.
This process stays idle after each demo until a local control-file command.
Raw logs/conversations remain ignored; public transcripts contain research only.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent
from plugin_runtime import PluginRuntime
from subagents import SubagentManager

PARTS = [
    "[part-a] Use psp_waves__analyze_psp_waves(interval_id='interval-a'). Report its half-open UTC coverage, total 1-30 mHz vector trace PSD energy in nT^2, and five-minute (2.5-4.5 mHz) and two-minute (6-12 mHz) fractions as percentages of that total. Include one relevant interpretation limit. Do not analyze interval-b or compare intervals for this part.",
    "[part-b] Use psp_waves__analyze_psp_waves(interval_id='interval-b'). Report its half-open UTC coverage, total 1-30 mHz vector trace PSD energy in nT^2, five-minute and two-minute fractions as percentages, and the five-minute-band peak period rounded appropriately for about 0.222 mHz resolution. Include one relevant interpretation limit. Do not analyze interval-a or compare intervals for this part.",
    "[part-c] Use psp_waves__compare_psp_wave_intervals(first_interval_id='interval-a', second_interval_id='interval-b'). Report signed five-minute and two-minute cross helicity in both intervals using z_plus=deltaV+deltab and z_minus=deltaV-deltab, with deltab in velocity units. Explain the dominant Elsasser sign without inferring propagation direction or flipping signs with field polarity. Mention density-proxy/field-of-view limits. Focus this report on cross helicity.",
]


class ScienceDemo:
    def __init__(self, runtime):
        self.runtime = runtime
        self.worker = agent.Agent(runtime=runtime, max_seconds=None)
        self.manager = SubagentManager(self.worker, ROOT)
        self.worker.manager = self.manager
        self.phase = "fanout_running"
        self.messages, self.events, self.actions = [], [], []
        self.write_lock = threading.RLock()
        self.private = ROOT / "validation/week-4-private"
        self.private.mkdir(parents=True, exist_ok=True)
        self.control_file = self.private / "science-demo-control.json"
        self.state_file = self.private / "science-demo-state.json"
        self.target = None
        original = self.manager.control

        def control(action, **arguments):
            if self.phase == "fanout_running":
                if action not in {"start", "list", "wait"}:
                    return {"error": "This demo allows only three research starts, list and wait."}
                if action == "start" and (arguments.get("agent") != "psp-wave-analyst" or len(self.manager.agents) >= 3):
                    return {"error": "Start exactly three psp-wave-analyst jobs, one per assigned part."}
            elif self.phase == "followup_running":
                if action not in {"send", "list", "wait"}:
                    return {"error": "Continue the existing child with send and wait; no new agents or reading tools."}
                if action == "send" and arguments.get("id") != self.target:
                    return {"error": "Send this follow-up only to the selected existing interval-a worker."}
            else:
                return {"error": "This live demo is waiting at an owner checkpoint."}
            result = original(action, **arguments)
            with self.write_lock:
                self.actions.append({"at_utc": datetime.now(timezone.utc).isoformat(), "action": action,
                                     "arguments": arguments, "result": result})
            return result

        self.manager.control = control

    def save_state(self):
        with self.write_lock:
            self.state_file.write_text(json.dumps({"pid": os.getpid(), "phase": self.phase,
                "session": self.manager.session, "agents": self.manager.list()["agents"],
                "control_file": str(self.control_file)}, indent=2) + "\n", encoding="utf-8")

    def emit(self, event):
        with self.write_lock:
            self.events.append({"at_utc": datetime.now(timezone.utc).isoformat(), **event})
        if event.get("type") in {"usage", "subagent_note"}:
            print(event["text"], flush=True)
        self.save_state()

    def run_main(self, prompt):
        self.manager.configure(lambda request: False, lambda request: False, self.emit,
                               {"email__send_message", "telegram__wait_for_messages"})
        agent.run_turn(self.messages, prompt, lambda request: False, self.emit, agent_state=self.worker,
                       hidden_tools=("email__send_message", "telegram__wait_for_messages"),
                       main_hidden_tools=("bash", "delegate", *(tool["function"]["name"] for tool in self.runtime.tools)))

    def child_records(self, child):
        return [json.loads(line) for line in child.log_path.read_text(encoding="utf-8").splitlines()]

    @staticmethod
    def calls(messages):
        return [call["function"] for message in messages for call in message.get("tool_calls", [])]

    def save_transcript(self, number, title, action_start, event_start, checks):
        lines = [f"# Demo {number}: {title}", "", "Live configured model: `" + os.environ["MODEL"] + "`.",
                 "Public bundled PSP measurements only. Full private logs remain under the harness's ignored logs/ directory.", ""]
        for item in self.actions[action_start:]:
            lines += ["## Main tool action", "", "```json", json.dumps(item, ensure_ascii=False, indent=2), "```", ""]
        for event in self.events[event_start:]:
            if event.get("type") in {"assistant", "subagent_note"}:
                lines += ["## " + ("Main answer" if event["type"] == "assistant" else "Completion note"),
                          "", "```text", event["text"], "```", ""]
        lines += ["## Verified evidence", "", "```json", json.dumps(checks, ensure_ascii=False, indent=2), "```", ""]
        filename = "02-research-fanout.md" if number == 2 else "03-research-followup.md"
        transcript = "\n".join(lines)
        (ROOT / "transcripts" / filename).write_text(transcript, encoding="utf-8")
        public = Path("C:/Users/Jasmi/ai-in-research-homework/week-4/submissions/jasmine0010/transcripts")
        public.mkdir(parents=True, exist_ok=True)
        (public / filename).write_text(transcript, encoding="utf-8")

    def fanout(self):
        action_start, event_start = len(self.actions), len(self.events)
        prompt = (
            "Run three independent parts of a PSP research question in parallel. Your next response should contain THREE "
            "subagent(action='start', agent='psp-wave-analyst', task=...) calls, one per part below, before any wait or analysis. "
            "Include each part tag and all its requirements in its task; the children see none of this conversation. "
            "After all three start calls return, use subagent(action='wait', ids=[all three ids], timeout=60), "
            "waiting again only if needed. Combine their three reports in at most 180 words of plain text, without a table. "
            "Keep all four cross-helicity values when available. Positive sigma_c means z_plus energy dominance only; "
            "never label it forward/backward propagation or an energy percentage. Do not infer precision beyond the tool metadata. "
            "Do not delegate synchronously, start a fourth agent, send follow-ups, stop agents or directly use research tools. "
            "The main model should only schedule and combine the reports.\n\n" + "\n\n".join(PARTS)
        )
        self.run_main(prompt)
        children = list(self.manager.agents.values())
        windows, tools = [], {}
        for child in children:
            records = self.child_records(child)
            started = next((item["at_utc"] for item in records if item["kind"] == "model_call_started"), None)
            ended = next((item["at_utc"] for item in reversed(records) if item["kind"] == "message" and
                          item["payload"].get("role") == "assistant" and not item["payload"].get("tool_calls")), None)
            calls = self.calls(child.messages)
            tools[child.id] = calls
            windows.append({"id": child.id, "first_model_call_utc": started, "report_utc": ended,
                            "state": child.state, "turns": child.turns, "tokens": child.tokens,
                            "thread": self.manager.threads[child.id].name})
            if any(call["name"] == "psp_waves__analyze_psp_waves" and json.loads(call["arguments"]).get("interval_id") == "interval-a" for call in calls):
                self.target = child.id
        overlap = 0
        if len(windows) == 3 and all(item["first_model_call_utc"] and item["report_utc"] for item in windows):
            overlap = (min(datetime.fromisoformat(item["report_utc"]) for item in windows)
                       - max(datetime.fromisoformat(item["first_model_call_utc"]) for item in windows)).total_seconds()
        actions = self.actions[action_start:]
        first_wait = next((index for index, item in enumerate(actions) if item["action"] == "wait"), -1)
        starts_before_wait = sum(item["action"] == "start" for item in actions[:first_wait]) if first_wait >= 0 else 0
        names = [call["name"] for calls in tools.values() for call in calls]
        coverage = {json.loads(call["arguments"]).get("interval_id") for calls in tools.values() for call in calls if call["name"] == "psp_waves__analyze_psp_waves"}
        passed = (len(children) == 3 and all(child.state == "idle" and child.report for child in children)
                  and overlap > 0 and starts_before_wait == 3 and coverage >= {"interval-a", "interval-b"}
                  and "psp_waves__compare_psp_wave_intervals" in names and self.target is not None)
        receipt = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "passed": bool(passed),
                   "session": self.manager.session, "windows": windows, "common_overlap_seconds": round(overlap, 3),
                   "three_starts_before_wait": starts_before_wait == 3, "child_tool_calls": tools,
                   "main_total_tokens": self.worker.tokens, "child_tokens": self.worker.child_tokens,
                   "followup_target": self.target, "main_report": self.worker.report}
        self.phase = "fanout_complete" if passed else "fanout_incomplete"
        (ROOT / "validation/week-4-demo-2.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        (self.private / "demo-2-main-conversation.json").write_text(json.dumps(self.messages, indent=2) + "\n", encoding="utf-8")
        self.save_transcript(2, "three research jobs in parallel", action_start, event_start, receipt)
        self.save_state()
        print(json.dumps({"demo_2": receipt, "phase": self.phase}, ensure_ascii=True, indent=2), flush=True)

    def followup(self):
        if self.phase != "fanout_complete":
            print("Follow-up requires a completed fan-out and the owner's checkpoint confirmation.", flush=True)
            return
        self.phase = "followup_running"
        action_start, event_start = len(self.actions), len(self.events)
        child = self.manager.agents[self.target]
        prefix = json.loads(json.dumps(child.messages))
        old_calls, old_ids = len(self.calls(child.messages)), set(self.manager.agents)
        old_thread, old_turns = self.manager.threads[self.target], child.turns
        prompt = (
            "The owner confirmed the parallel research demo. Continue the existing interval-a child " + self.target
            + " with subagent(action='send', id='" + self.target + "', message=...). Ask it: Using ONLY the measurements "
            "already in your conversation, add your five-minute and two-minute fractions, calculate the remaining "
            "percentage of 1-30 mHz power outside those two bands, and explain why that remainder does not prove "
            "a separate wave population. Do not call any tools or reread data. Then wait for that SAME id and summarize "
            "its answer. Do not start new agents, reread logs or call research tools."
        )
        self.run_main(prompt)
        new_calls = self.calls(child.messages)[old_calls:]
        sent = [item for item in self.actions[action_start:] if item["action"] == "send"]
        passed = (child.state == "idle" and child.turns > old_turns and not new_calls
                  and child.messages[:len(prefix)] == prefix and set(self.manager.agents) == old_ids
                  and self.manager.threads[self.target] is old_thread and len(sent) == 1)
        receipt = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "passed": passed,
                   "session": self.manager.session, "id": self.target, "same_worker_thread": self.manager.threads[self.target] is old_thread,
                   "old_context_preserved": child.messages[:len(prefix)] == prefix, "new_tool_calls": new_calls,
                   "new_agent_ids": sorted(set(self.manager.agents) - old_ids), "turns_before": old_turns,
                   "turns_after": child.turns, "child_report": child.report, "main_report": self.worker.report}
        self.phase = "followup_complete" if passed else "followup_incomplete"
        (ROOT / "validation/week-4-demo-3.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        (self.private / "demo-3-main-conversation.json").write_text(json.dumps(self.messages, indent=2) + "\n", encoding="utf-8")
        self.save_transcript(3, "follow up with an existing worker", action_start, event_start, receipt)
        self.save_state()
        print(json.dumps({"demo_3": receipt, "phase": self.phase}, ensure_ascii=True, indent=2), flush=True)


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
        session = ScienceDemo(runtime)
        try:
            session.save_state()
            session.fanout()
            print("Research session retained. Waiting for the owner's checkpoint before follow-up; no model calls occur while idle.", flush=True)
            while True:
                if session.control_file.exists():
                    command = json.loads(session.control_file.read_text(encoding="utf-8"))
                    session.control_file.unlink()
                    if command.get("action") == "close":
                        break
                    if command.get("action") == "followup":
                        session.followup()
                time.sleep(0.5)
        finally:
            session.manager.close()
            session.phase = "closed"
            session.save_state()
            agent.PLUGINS = None


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError):
        print("Live research demo stopped. Check the sanitized state/receipts; credential values were not displayed.", file=sys.stderr)
        sys.exit(1)
