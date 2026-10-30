"""Local SQLite chat storage and the per-chat worker; no external services."""

from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time

from agent import Agent, conversation, run_turn


def now():
    return datetime.now(timezone.utc).isoformat()


class ChatStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    @contextmanager
    def connection(self):
        # Each operation owns its connection, and each write is a transaction.
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("PRAGMA secure_delete = ON")
            with db:
                yield db

    def load(self):
        with self.lock, self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM chats")]

    def save(self, record):
        with self.lock, self.connection() as db:
            db.execute("INSERT OR REPLACE INTO chats VALUES (?, ?)", (record["id"], json.dumps(record)))

    def delete(self, chat_id):
        with self.lock, self.connection() as db:
            db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


class Chat:
    def __init__(self, store, record=None):
        self.store = store
        self.lock = threading.RLock()
        record = record or {"id": secrets.token_hex(16), "title": "New chat", "created_at": now(), "messages": conversation(), "events": []}
        self.id = record["id"]
        self.title = record["title"]
        self.created_at = record["created_at"]
        self.updated_at = record.get("updated_at", self.created_at)
        self.messages = record["messages"]
        self.agent_state = Agent(max_seconds=None)
        self.events = record["events"]
        self.renamed = record.get("renamed", False)
        self.busy = False
        self.pending = None
        self.deleted = False
        if record.get("busy"):
            self.recover()

    def record(self):
        return {"id": self.id, "title": self.title, "created_at": self.created_at,
                "updated_at": self.updated_at, "messages": self.messages,
                "events": self.events, "busy": self.busy, "renamed": self.renamed}

    def save(self):
        self.updated_at = now()
        self.store.save(self.record())

    def recover(self):
        """Complete interrupted tool messages without running any commands."""
        repaired, index = [], 0
        while index < len(self.messages):
            message = self.messages[index]
            repaired.append(message)
            index += 1
            calls = message.get("tool_calls") or []
            if message.get("role") != "assistant" or not calls:
                continue
            present = set()
            while index < len(self.messages) and self.messages[index].get("role") == "tool":
                present.add(self.messages[index].get("tool_call_id"))
                repaired.append(self.messages[index])
                index += 1
            for call in calls:
                if call["id"] not in present:
                    output = {"exit_code": None, "error": "The previous turn was interrupted. This command was not resumed automatically; its outcome may be unknown."}
                    repaired.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(output)})
                    self.events.append({"type": "tool_result", "result": output})
        self.messages = repaired
        answered = {event["id"] for event in self.events if event["type"] == "decision"}
        for event in list(self.events):
            if event["type"] == "approval" and event["id"] not in answered:
                self.events.append({"type": "decision", "id": event["id"], "approved": False, "interrupted": True})
        self.events.append({"type": "error", "text": "The server stopped during the previous turn. No commands were resumed. You can send a new message to continue."})

    def checkpoint(self, messages):
        with self.lock:
            self.messages = deepcopy(messages)
            self.save()

    def emit(self, event):
        with self.lock:
            if self.deleted:
                return
            self.events.append(event)
            self.save()

    def approve(self, command, *, cancel_event=None, deadline=None):
        pending = {"id": secrets.token_hex(12), "command": command, "ready": threading.Event(), "decision": False}
        with self.lock:
            self.pending = pending
            self.emit({"type": "approval", "id": pending["id"], "command": command})
        while not pending["ready"].wait(0.1):
            if ((cancel_event is not None and cancel_event.is_set())
                    or (deadline is not None and time.monotonic() >= deadline)):
                with self.lock:
                    if not pending["ready"].is_set():
                        pending["decision"] = False
                        pending["ready"].set()
                        self.emit({"type": "decision", "id": pending["id"], "approved": False, "cancelled": True})
                break
        with self.lock:
            if self.pending is pending:
                self.pending = None
        return pending["decision"]

    def work(self, prompt):
        try:
            with self.lock:
                messages = deepcopy(self.messages)
            run_turn(messages, prompt, self.approve, self.emit, checkpoint=self.checkpoint, agent_state=self.agent_state)
        except RuntimeError as error:
            self.emit({"type": "error", "text": str(error)})
        except Exception as error:
            print("Turn failed:", type(error).__name__)
            try:
                self.emit({"type": "error", "text": "The turn failed. Check local storage and try again."})
            except OSError:
                pass
        finally:
            with self.lock:
                self.busy = False
                self.save()

    def start(self, prompt):
        with self.lock:
            if self.busy or self.deleted:
                return False
            if prompt.strip() == "/agents":
                manager = self.agent_state.manager
                self.emit({"type": "user", "text": prompt})
                self.emit({"type": "tool_result", "result": manager.list() if manager else {"agents": []}})
                return True
            if not self.renamed and not any(event["type"] == "user" for event in self.events):
                self.title = prompt.splitlines()[0][:60]
            self.busy = True
            self.events.append({"type": "user", "text": prompt})
            try:
                self.save()
            except Exception:
                self.busy = False
                self.events.pop()
                raise
        threading.Thread(target=self.work, args=(prompt,), daemon=True).start()
        return True

    def decide(self, approval_id, approved):
        with self.lock:
            pending = self.pending
            if not pending or pending["id"] != approval_id or pending["ready"].is_set():
                return False
            self.events.append({"type": "decision", "id": approval_id, "approved": approved})
            try:
                self.save()
            except Exception:
                self.events.pop()
                raise
            pending["decision"] = approved
            pending["ready"].set()
        return True

    def summary(self):
        with self.lock:
            return {"id": self.id, "title": self.title, "created_at": self.created_at,
                    "updated_at": self.updated_at, "busy": self.busy,
                    "pending": self.pending["id"] if self.pending else None}

    def snapshot(self, after):
        with self.lock:
            reset = after > len(self.events)
            return {**self.summary(), "events": deepcopy(self.events[0 if reset else after:]),
                    "cursor": len(self.events), "reset": reset}


class ChatHistory:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.store = ChatStore(path)
        self.chats = {}
        for record in self.store.load():
            chat = Chat(self.store, record)
            self.chats[chat.id] = chat
            if record.get("busy"):
                chat.save()
        if not self.chats:
            self.create()

    def create(self):
        with self.lock:
            chat = Chat(self.store)
            chat.save()
            self.chats[chat.id] = chat
            return chat

    def get(self, chat_id):
        with self.lock:
            return self.chats.get(chat_id) if isinstance(chat_id, str) else None

    def summaries(self):
        with self.lock:
            return sorted((chat.summary() for chat in self.chats.values()), key=lambda item: item["updated_at"], reverse=True)

    def rename(self, chat_id, title):
        with self.lock:
            chat = self.get(chat_id)
            if not chat:
                return False
            with chat.lock:
                old_title, old_renamed = chat.title, chat.renamed
                chat.title, chat.renamed = title, True
                try:
                    chat.save()
                except Exception:
                    chat.title, chat.renamed = old_title, old_renamed
                    raise
            return True

    def delete(self, chat_id):
        with self.lock:
            chat = self.get(chat_id)
            if not chat:
                return False
            with chat.lock:
                if chat.busy:
                    return False
                self.store.delete(chat_id)
                chat.deleted = True
                del self.chats[chat_id]
        if chat.agent_state.manager is not None:
            chat.agent_state.manager.close()
        return True
