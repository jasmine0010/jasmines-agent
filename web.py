"""A local web interface with saved, independent chats (no frameworks)."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import sqlite3
from urllib.parse import parse_qs, urlsplit

import agent
from agent import ROOT
from plugin_runtime import PluginRuntime
from history import ChatHistory


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

    def authenticated(self):
        return self.headers.get("X-Chat-Token") == self.server.api_token

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"error": "Invalid host."})
        target = urlsplit(self.path)
        if target.path == "/":
            html = (ROOT / "index.html").read_text(encoding="utf-8-sig")
            return self.reply(200, html.replace("__API_TOKEN__", self.server.api_token), "text/html; charset=utf-8")
        if target.path not in {"/chats", "/events"}:
            return self.reply(404, {"error": "Not found."})
        if not self.authenticated():
            return self.reply(403, {"error": "Refresh the page to reconnect."})
        if target.path == "/chats":
            return self.reply(200, {"chats": self.server.history.summaries(), "model": os.environ.get("MODEL", "not configured")})
        query = parse_qs(target.query)
        chat = self.server.history.get(query.get("chat", [None])[0])
        if not chat:
            return self.reply(404, {"error": "This chat no longer exists."})
        try:
            after = max(0, int(query.get("after", ["0"])[0]))
        except ValueError:
            return self.reply(400, {"error": "Invalid event cursor."})
        return self.reply(200, chat.snapshot(after))

    def do_POST(self):
        origin = "http://" + self.server.authority
        if not self.valid_host() or self.headers.get("Origin") != origin or not self.authenticated():
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
        try:
            self.dispatch(body)
        except (OSError, sqlite3.Error):
            self.reply(503, {"error": "Could not save chat history. Check free disk space and folder permissions."})

    def dispatch(self, body):
        history = self.server.history
        if self.path == "/chats/new":
            return self.reply(200, {"chat": history.create().summary()})
        if self.path not in {"/message", "/approve", "/chats/rename", "/chats/delete"}:
            return self.reply(404, {"error": "Not found."})
        chat = history.get(body.get("chat_id"))
        if not chat:
            return self.reply(404, {"error": "This chat no longer exists."})
        if self.path == "/message":
            prompt = body.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
                return self.reply(400, {"error": "Enter a message of at most 8,000 characters."})
            ok = chat.start(prompt.strip())
        elif self.path == "/approve":
            if not isinstance(body.get("approved"), bool):
                return self.reply(400, {"error": "Choose Approve or Deny."})
            ok = chat.decide(body.get("id"), body["approved"])
        elif self.path == "/chats/rename":
            title = body.get("title")
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 100:
                return self.reply(400, {"error": "Enter a title of 1–100 characters."})
            ok = history.rename(chat.id, title.strip())
        else:
            ok = history.delete(chat.id)
        self.reply(200 if ok else 409, {"ok": ok, "error": None if ok else "Wait for this chat to finish, or check whether the command was already answered."})


def create_server(port=8765, history=None, history_path=None):
    history = history or ChatHistory(history_path or ROOT / "history" / "chats.sqlite3")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.authority = "127.0.0.1:" + str(server.server_port)
    server.api_token = secrets.token_urlsafe(32)
    server.history = history
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with PluginRuntime(ROOT) as runtime:
        agent.PLUGINS = runtime
        runtime.describe()
        try:
            with create_server(args.port) as server:
                print("Open http://" + server.authority, flush=True)
                print("Chat history is saved locally. Press Ctrl+C to stop.", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        finally:
            from subagents import shutdown_all
            shutdown_all()
            agent.PLUGINS = None


if __name__ == "__main__":
    main()
