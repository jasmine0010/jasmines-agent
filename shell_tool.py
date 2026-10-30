"""The harness's built-in tool: approved shell commands with bounded output."""

import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

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


def _terminate_windows_tree(process):
    """Retain process handles so taskkill exit races cannot masquerade as failure.

    A nonzero taskkill status may mean a descendant exited during traversal.
    Verify the observed tree through stable OS handles, never by parsing its
    localized output or assuming that a dead root proves its children died.
    """
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("pid", wintypes.DWORD), ("heap", ctypes.c_size_t),
                    ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("parent", wintypes.DWORD), ("priority", wintypes.LONG),
                    ("flags", wintypes.DWORD), ("exe", wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ("Process32FirstW", "Process32NextW"):
        function = getattr(kernel, name)
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        function.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    parents = {}
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
            raise ctypes.WinError(ctypes.get_last_error())
        while True:
            parents[entry.pid] = entry.parent
            if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    raise ctypes.WinError(ctypes.get_last_error())
                break
    finally:
        kernel.CloseHandle(snapshot)
    owned = {process.pid}
    while True:
        found = {pid for pid, parent in parents.items() if parent in owned} - owned
        if not found:
            break
        owned.update(found)
    handles = []
    try:
        for pid in owned:
            handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE only
            if handle:
                handles.append(handle)
            elif ctypes.get_last_error() not in {87, 1168}:  # Already gone
                raise ctypes.WinError(ctypes.get_last_error())
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=10,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        end = time.monotonic() + 10
        for handle in handles:
            remaining_ms = max(0, int((end - time.monotonic()) * 1000))
            if kernel.WaitForSingleObject(handle, remaining_ms) != 0:
                return False
        return process.poll() is not None
    finally:
        for handle in handles:
            kernel.CloseHandle(handle)


def terminate_process_tree(process):
    """Kill this owned command and its descendants; never use shell text."""
    if process.poll() is not None:
        return True
    try:
        if os.name == "nt":
            return _terminate_windows_tree(process)
        else:
            os.killpg(process.pid, signal.SIGKILL)
            tree_killed = True
        if process.poll() is None:
            process.wait(timeout=10)
        return tree_killed and process.poll() is not None
    except ProcessLookupError:
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def stop_running_process(worker):
    # Serialize timeout, owner stop and shutdown so a stale PID is never reused.
    with worker.process_lock:
        return worker.process is None or terminate_process_tree(worker.process)


def run_bash(command, approve, timeout=60, *, worker=None):
    """Approval happens inside the tool, so every caller must obtain it."""
    if not isinstance(command, str) or not command.strip():
        return {"exit_code": None, "error": "command must be a nonempty string"}
    if not approve(command):
        return {"exit_code": None, "stdout": "", "stderr": "The user declined to run this command.", "declined": True}
    if worker is not None:
        worker.current_action = "bash: " + command[:160]
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
    environment = {key: value for key, value in os.environ.items() if key not in {"API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "EMAIL_APP_PASSWORD"}}
    timed_out = stopped = False
    end = time.monotonic() + timeout
    if worker is not None and worker.deadline is not None:
        end = min(end, worker.deadline)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        def launch():
            return subprocess.Popen(
                args, cwd=WORKSPACE, stdout=stdout, stderr=stderr,
                stdin=subprocess.DEVNULL, env=environment,
                start_new_session=(os.name != "nt"),
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0,
            )
        if worker is not None:
            with worker.process_lock:
                if worker.stop_event.is_set() or time.monotonic() >= end:
                    return {"exit_code": None, "stopped": True, "error": "Agent stopped or reached its deadline; command was not started."}
                process = launch()
                worker.process = process
            worker.record("process_started", {"pid": process.pid, "command": command})
        else:
            process = launch()
        try:
            while process.poll() is None:
                stopped = worker is not None and worker.stop_event.is_set()
                timed_out = time.monotonic() >= end
                if stopped or timed_out:
                    killed = stop_running_process(worker) if worker is not None else terminate_process_tree(process)
                    if not killed:
                        raise OSError("Owned command process tree could not be terminated.")
                    break
                try:
                    process.wait(timeout=min(0.1, max(0.001, end - time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
        finally:
            stopped = stopped or (worker is not None and worker.stop_event.is_set())
            if worker is not None:
                with worker.process_lock:
                    if worker.process is process and process.poll() is not None:
                        worker.process = None
                worker.record("process_finished", {"pid": process.pid, "exit_code": process.poll(),
                                                   "stopped": stopped, "timed_out": timed_out})
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
        "stopped": stopped,
        "truncated": stdout_size + stderr_size > len((stdout_text + stderr_text).encode("utf-8")),
    }
