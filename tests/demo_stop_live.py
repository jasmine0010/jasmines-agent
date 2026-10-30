"""Live stop demo. Run only after the owner approves the exact sleep command.

Uses the actual configured model and production manager/shell implementation.
The demo guard waits for a real process before list/read/stop, so model latency
cannot turn this into cancellation of a model request instead of a shell.
"""
from datetime import datetime, timezone
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent
from plugin_runtime import PluginRuntime
from subagents import SubagentManager

COMMAND = "Start-Sleep -Seconds 600"
APPROVAL = "[sa-1 · process-demo] " + COMMAND


def alive(pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
            raise OSError("Could not inspect the owned process.")
        return code.value == 259
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


class StopDemo:
    def __init__(self, runtime):
        self.runtime = runtime
        self.worker = agent.Agent(runtime=runtime, max_seconds=None)
        self.manager = SubagentManager(self.worker, ROOT)
        self.worker.manager = self.manager
        self.events, self.actions, self.approvals = [], [], []
        self.lock = threading.RLock()
        self.owned_pid = None
        self.before = None
        self.inspection = None
        self.ready_wait = 0
        original = self.manager.control

        def control(action, **arguments):
            if action not in {"start", "list", "read", "stop"}:
                return {"error": "Use start, list, read, stop for this demonstration."}
            if action == "start" and (arguments.get("agent") != "process-demo" or self.manager.agents):
                return {"error": "Start exactly one process-demo worker."}
            if action != "start" and not self.manager.agents:
                return {"error": "Start the process-demo worker first."}
            if action in {"list", "read", "stop"} and self.owned_pid is None:
                self.await_process()
            if action == "stop":
                seen = {item["action"] for item in self.actions}
                if not {"list", "read"} <= seen:
                    return {"error": "Inspect the running worker using both list and read before stop."}
                self.before = alive(self.owned_pid)
                self.inspection = subprocess.run(
                    ["pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                     f"Get-Process -Id {self.owned_pid} | Select-Object Id,ProcessName | ConvertTo-Json -Compress"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            result = original(action, **arguments)
            with self.lock:
                self.actions.append({"at_utc": datetime.now(timezone.utc).isoformat(),
                                     "action": action, "arguments": arguments, "result": result})
            return result

        self.manager.control = control

    def await_process(self):
        start = time.monotonic()
        while time.monotonic() - start < 45:
            child = self.manager.agents.get("sa-1")
            if child:
                with child.process_lock:
                    process = child.process
                    if process is not None and process.poll() is None:
                        self.owned_pid = process.pid
                        self.ready_wait = round(time.monotonic() - start, 3)
                        return
                if child.state in {"failed", "idle", "stopped"}:
                    break
            time.sleep(0.1)
        raise RuntimeError("No running child shell observed; cannot claim a process-stop demonstration.")

    def approve(self, request):
        with self.lock:
            approved = request == APPROVAL and not any(item["approved"] for item in self.approvals)
            self.approvals.append({"request": request, "approved": approved,
                                   "basis": "Owner's explicit chat approval of this exact command"})
        return approved

    def emit(self, event):
        with self.lock:
            self.events.append(event)
        if event.get("type") in {"usage", "subagent_note"}:
            print(event["text"], flush=True)

    def run(self):
        messages = []
        try:
            agent.run_turn(messages,
                "Demonstrate stop on Windows. Start exactly one process-demo worker with task: "
                "Call bash once with exactly Start-Sleep -Seconds 600 and then report the actual result. "
                "Then use subagent list and read on that same worker while running, then stop it immediately. "
                "Do not wait for the sleep to finish. The demonstration guard may wait briefly for the shell "
                "to launch before inspection. Report only observed results, including the stop outcome.",
                lambda request: False, self.emit, agent_state=self.worker, child_approve=self.approve,
                hidden_tools=("email__send_message", "telegram__wait_for_messages"),
                main_hidden_tools=("bash", "delegate", *(tool["function"]["name"] for tool in self.runtime.tools)))
            child = self.manager.agents.get("sa-1")
            end = time.monotonic() + 5
            while self.owned_pid and alive(self.owned_pid) and time.monotonic() < end:
                time.sleep(0.1)
            gone = bool(self.owned_pid and not alive(self.owned_pid))
            stopped = [item for item in self.actions if item["action"] == "stop"]
            refusal = None
            # Bypass only the demo action filter to check the production refusal.
            if child:
                try:
                    refusal = self.manager.send("sa-1", "Should not resume")
                except ValueError as error:
                    refusal = {"error": str(error)}
            calls = [call["function"] for message in (child.messages if child else [])
                     for call in message.get("tool_calls", [])]
            shell_calls = [call for call in calls if call["name"] == "bash"]
            exact = len(shell_calls) == 1 and json.loads(shell_calls[0]["arguments"]).get("command") == COMMAND
            checked = {"same_worker": len(self.manager.agents) == 1,
                       "exact_single_sleep_call": exact, "process_alive_before_stop": self.before is True,
                       "get_process_saw_owned_pid": bool(self.inspection and self.inspection.returncode == 0),
                       "process_tree_killed": bool(stopped and stopped[-1]["result"].get("process_tree_killed")),
                       "process_gone_after_stop": gone, "state_stopped": bool(child and child.state == "stopped"),
                       "resume_refused": bool(refusal and "error" in refusal)}
            receipt = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "passed": all(checked.values()),
                       "session": self.manager.session, "checks": checked, "owned_pid": self.owned_pid,
                       "readiness_wait_seconds": self.ready_wait,
                       "get_process_before_stop": self.inspection.stdout.strip() if self.inspection else None,
                       "approvals": self.approvals, "resume_result": refusal,
                       "main_report": self.worker.report}
            (ROOT / "validation/week-4-demo-4.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            private = ROOT / "validation/week-4-private"
            (private / "demo-4-main-conversation.json").write_text(json.dumps(messages, indent=2) + "\n", encoding="utf-8")
            lines = ["# Demo 4: inspect and stop a running shell", "",
                     "Live configured model: `" + os.environ["MODEL"] + "`.", "",
                     "The owner approved only `[sa-1 · process-demo] Start-Sleep -Seconds 600`.",
                     "The demo guard waits up to 45 seconds for an actual child shell before inspection; "
                     "production start/list/read/stop and shell termination remain unchanged.", ""]
            for item in self.actions:
                lines += ["## Main tool action", "", "```json", json.dumps(item, ensure_ascii=False, indent=2), "```", ""]
            for event in self.events:
                if event.get("type") in {"assistant", "subagent_note"}:
                    lines += ["## Main answer or lifecycle note", "", "```text", event["text"], "```", ""]
            lines += ["## Verification", "", "```json", json.dumps(receipt, ensure_ascii=False, indent=2), "```", ""]
            for directory in (ROOT / "transcripts",):
                (directory / "04-stop-process.md").write_text("\n".join(lines), encoding="utf-8")
            print(json.dumps(receipt, ensure_ascii=True, indent=2), flush=True)
        finally:
            self.manager.close()


def main():
    if sys.argv[1:] != ["--owner-approved-sleep"]:
        raise RuntimeError("Run only after the owner approves the exact sleep command.")
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
            StopDemo(runtime).run()
        finally:
            agent.PLUGINS = None


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError):
        print("Stop demo failed; do not claim success. Credential values were not displayed.", file=sys.stderr)
        sys.exit(1)
