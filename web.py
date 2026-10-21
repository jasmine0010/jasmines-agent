"""A local, single-chat web interface around agent.run_turn (no frameworks)."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import threading
from urllib.parse import parse_qs, urlsplit

from agent import ROOT, conversation, run_turn


class Chat:
    def __init__(self):
        self.lock = threading.Lock()
        self.messages = conversation()
        self.events = []
        self.busy = False
        self.pending = None

    def emit(self, event):
        with self.lock:
            self.events.append(event)

    def approve(self, command):
        pending = {"id": secrets.token_hex(12), "command": command, "ready": threading.Event(), "decision": False}
        with self.lock:
            self.pending = pending
            self.events.append({"type": "approval", "id": pending["id"], "command": command})
        pending["ready"].wait()  # The model worker pauses; HTTP requests remain responsive.
        with self.lock:
            self.pending = None
        return pending["decision"]

    def work(self, prompt):
        try:
            run_turn(self.messages, prompt, self.approve, self.emit)
        except RuntimeError as error:
            self.emit({"type": "error", "text": str(error)})
        except Exception as error:
            # Do not expose tracebacks, environment variables, or API credentials.
            self.emit({"type": "error", "text": "The turn failed. Start a new chat and try again."})
            print("Turn failed:", type(error).__name__)
        finally:
            with self.lock:
                self.busy = False

    def start(self, prompt):
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            self.events.append({"type": "user", "text": prompt})
        threading.Thread(target=self.work, args=(prompt,), daemon=True).start()
        return True

    def decide(self, approval_id, approved):
        with self.lock:
            pending = self.pending
            if not pending or pending["id"] != approval_id or pending["ready"].is_set():
                return False
            pending["decision"] = approved
            self.events.append({"type": "decision", "id": approval_id, "approved": approved})
            pending["ready"].set()
        return True

    def reset(self):
        with self.lock:
            if self.busy:
                return False
            self.messages = conversation()
            self.events = []
        return True

    def snapshot(self, after):
        with self.lock:
            reset = after > len(self.events)
            return {
                "events": self.events[0 if reset else after:], "cursor": len(self.events),
                "busy": self.busy, "reset": reset, "model": os.environ.get("MODEL", "not configured"),
                "pending": self.pending["id"] if self.pending else None,
            }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body, content_type="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def valid_host(self):
        return self.headers.get("Host") == self.server.authority

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"error": "Invalid host."})
        target = urlsplit(self.path)
        if target.path == "/":
            html = (ROOT / "index.html").read_text(encoding="utf-8-sig")
            return self.reply(200, html.replace("__API_TOKEN__", self.server.api_token), "text/html; charset=utf-8")
        if target.path == "/events":
            if self.headers.get("X-Chat-Token") != self.server.api_token:
                return self.reply(403, {"error": "Refresh the page to reconnect."})
            try:
                after = max(0, int(parse_qs(target.query).get("after", ["0"])[0]))
            except ValueError:
                return self.reply(400, {"error": "Invalid event cursor."})
            return self.reply(200, self.server.chat.snapshot(after))
        return self.reply(404, {"error": "Not found."})

    def do_POST(self):
        origin = "http://" + self.server.authority
        if not self.valid_host() or self.headers.get("Origin") != origin or self.headers.get("X-Chat-Token") != self.server.api_token:
            return self.reply(403, {"error": "Refresh this local page before trying again."})
        if self.headers.get_content_type() != "application/json":
            return self.reply(415, {"error": "Expected JSON."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 40_000:
                return self.reply(413, {"error": "Request is empty or too large."})
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            return self.reply(400, {"error": "Invalid JSON request."})
        chat = self.server.chat
        if self.path == "/message":
            prompt = body.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
                return self.reply(400, {"error": "Enter a message of at most 8,000 characters."})
            ok = chat.start(prompt.strip())
        elif self.path == "/approve":
            if not isinstance(body.get("approved"), bool):
                return self.reply(400, {"error": "Choose Approve or Deny."})
            ok = chat.decide(body.get("id"), body["approved"])
        elif self.path == "/reset":
            ok = chat.reset()
        else:
            return self.reply(404, {"error": "Not found."})
        self.reply(200 if ok else 409, {"ok": ok, "error": None if ok else "Chat is busy or this approval has already been answered."})


def create_server(port=8765, chat=None):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.authority = "127.0.0.1:" + str(server.server_port)
    server.api_token = secrets.token_urlsafe(32)
    server.chat = chat or Chat()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with create_server(args.port) as server:
        print("Open http://" + server.authority, flush=True)
        print("This server shares one chat between its tabs. Press Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
