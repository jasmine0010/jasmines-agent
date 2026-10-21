"""The harness's built-in tool: approved shell commands with bounded output."""

import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / "workspace"
OUTPUT_LIMIT = 10_000
TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Run a shell command after the user approves it. "
            + ("Commands use PowerShell on Windows. " if os.name == "nt" else "Commands use bash. ")
            + "The working folder is the harness's workspace directory. "
            "Commands have a 60-second time limit; long output is truncated. "
            "Do not access credentials or .env files."
        ),
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}


def tail(stream):
    size = stream.tell()
    stream.seek(max(0, size - OUTPUT_LIMIT * 4))
    return stream.read().decode("utf-8", errors="replace")[-OUTPUT_LIMIT:], size


def run_bash(command, approve, timeout=60):
    """Approval happens inside the tool, so every caller must obtain it."""
    if not isinstance(command, str) or not command.strip():
        return {"exit_code": None, "error": "command must be a nonempty string"}
    if not approve(command):
        return {"exit_code": None, "stdout": "", "stderr": "The user declined to run this command.", "declined": True}
    WORKSPACE.mkdir(exist_ok=True)
    if os.name == "nt":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        args = [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command] if shell else None
    else:
        shell = shutil.which("bash")
        args = [shell, "-c", command] if shell else None
    if not args:
        return {"exit_code": 127, "stdout": "", "stderr": "The required shell is not installed."}
    # Shell children do not need the harness's model API credential.
    environment = {key: value for key, value in os.environ.items() if key not in {"API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"}}
    timed_out = False
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            args, cwd=WORKSPACE, stdout=stdout, stderr=stderr,
            stdin=subprocess.DEVNULL, env=environment,
            start_new_session=(os.name != "nt"),
        )
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
        stdout_text, stdout_size = tail(stdout)
        stderr_text, stderr_size = tail(stderr)
    # Keep the end of each stream, sharing the total output budget.
    stderr_text = stderr_text[-OUTPUT_LIMIT:]
    remaining = OUTPUT_LIMIT - len(stderr_text)
    stdout_text = stdout_text[-remaining:] if remaining else ""
    return {
        "stdout": stdout_text,
        "stderr": stderr_text,
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "truncated": stdout_size + stderr_size > len((stdout_text + stderr_text).encode("utf-8")),
    }
