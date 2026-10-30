"""Phone interface for the same agent loop, with approvals tied to replies."""

from collections import deque
import os
import time
import threading
import json

import agent

SEND = "telegram__send_message"
WAIT = "telegram__wait_for_messages"
PHONE_PROMPT = """
The user is communicating through Telegram. Keep replies short and plain text.
The harness owns polling, sends progress and your final answer automatically,
and obtains approval for every proposed action using a reply in Telegram.
Do not poll for input. Use send_message only for an additional progress update
that is needed, not to duplicate your final answer. A denied action must stay
denied: explain the limitation and do not try an alternative command or tool.
"""
AUTO_PHONE_PROMPT = """
The user is communicating through Telegram and explicitly enabled automatic
execution. The harness owns polling and delivers your final answer automatically.
Use the supplied tools directly without asking for confirmation. Read a needed
skill once and reuse it within the conversation. Do not repeat completed reads
or commands. Use the research MCP tools for calculations instead of shell scripts.
Keep replies short and plain.
For research comparisons, use plain lines instead of Markdown tables or LaTeX
and stay under 150 words. Use delta-b in velocity units for Elsasser variables;
do not infer physical propagation direction from signed cross helicity.
Do not poll for input or send a duplicate of your final answer. Never read or
expose credentials. Tool timeouts, output limits and the turn limit still apply.
"""


class TelegramMode:
    def __init__(self, runtime, approval_seconds=180, *, auto_approve=False):
        if not isinstance(auto_approve, bool):
            raise ValueError("telegram_auto_approve must be true or false.")
        self.runtime = runtime
        self.auto_approve = auto_approve
        self.approval_seconds = approval_seconds
        self.pending = deque()
        self.poll_lock = threading.RLock()
        self.approval_active = threading.Event()
        self.approval_ids = set()
        self.messages = agent.conversation()
        self.agent_state = agent.Agent(max_seconds=None)
        if not {SEND, WAIT}.issubset(runtime.routes):
            raise RuntimeError("Telegram mode needs the Telegram plugin's send and wait tools.")

    def channel(self, name, arguments):
        result = self.runtime.channel_call(name, arguments)
        if "error" in result:
            raise RuntimeError(result["error"])
        return result

    def send(self, text):
        return self.channel(SEND, {"text": text})

    def poll(self, seconds=30):
        return self.channel(WAIT, {"seconds": seconds}).get("messages", [])

    def approve(self, action, *, force_confirmation=False, cancel_event=None, deadline=None):
        if self.auto_approve and not force_confirmation:
            kind = action.splitlines()[0] if action.startswith("MCP tool ") else "shell"
            print("Phone automatic execution: " + kind, flush=True)
            return True
        self.approval_active.set()
        try:
            with self.poll_lock:
                return self._confirm(action, cancel_event=cancel_event, child_deadline=deadline)
        finally:
            self.approval_active.clear()

    def _confirm(self, action, *, cancel_event=None, child_deadline=None):
        if cancel_event is not None and cancel_event.is_set():
            self.send("Subagent stopped; its pending action was declined.")
            return False
        # Never truncate an action that the user is being asked to approve.
        # Splitting is handled by the server; reply to the final part.
        receipt = self.send("Run this action?\n\n" + action +
                            "\n\nUse Telegram Reply on this message (the last part if split). "
                            "Reply yes or no within 3 minutes. Only yes approves.")
        ids = receipt.get("message_ids") or []
        if not ids:
            raise RuntimeError("Telegram did not return an approval message ID; no action was approved.")
        target = ids[-1]
        self.approval_ids.update(ids)
        deadline = time.monotonic() + self.approval_seconds
        if child_deadline is not None:
            deadline = min(deadline, child_deadline)
        first_batch = list(self.pending)
        self.pending.clear()
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                self.pending.extendleft(reversed(first_batch))
                self.send("Subagent stopped; its pending action was declined.")
                return False
            batch = first_batch or self.poll(min(1 if cancel_event is not None else 30, max(1, int(deadline - time.monotonic()))))
            first_batch = []
            answer = None
            for message in batch:
                if message.get("reply_to_message_id") == target:
                    if answer is None:
                        answer = message["text"].strip().lower() == "yes"
                    # All further replies to the same prompt are consumed.
                elif message.get("reply_to_message_id") in self.approval_ids:
                    continue  # An old approval is never a new question.
                elif message["text"].strip().lower() in {"yes", "no"}:
                    self.send("Use Telegram Reply on the current approval request. This unlinked answer did not approve anything.")
                else:
                    self.pending.append(message)  # Preserve unrelated questions.
            if answer is not None:
                print("Phone approval: " + ("approved" if answer else "declined"), flush=True)
                return answer
        self.pending.extendleft(reversed(first_batch))
        self.send("Approval timed out. The action was declined.")
        print("Phone approval: timed out (declined)", flush=True)
        return False

    def approve_subagent(self, action, *, cancel_event=None, deadline=None):
        return self.approve(action, force_confirmation=True, cancel_event=cancel_event, deadline=deadline)

    def handle(self, message):
        text = message["text"].strip()
        if not text or message.get("reply_to_message_id") in self.approval_ids:
            return
        if text.lower() in {"yes", "no"}:
            self.send("There is no pending approval. Send a question to begin.")
            return
        if text == "/new":
            if self.agent_state.manager is not None:
                self.agent_state.manager.close()
            self.messages = agent.conversation()
            self.agent_state = agent.Agent(max_seconds=None)
            self.send("Started a new conversation.")
            return
        if text == "/start":
            self.send("Ready. Send a question; use /new to reset this conversation.")
            return
        if text == "/agents":
            manager = self.agent_state.manager
            self.send(json.dumps(manager.list(), ensure_ascii=False) if manager else "No subagents in this session.")
            return
        self.send("Working on your question. " + (
            "Automatic execution is enabled." if self.auto_approve else "I will ask before running actions."))
        answers, errors = [], []

        def emit(event):
            if event["type"] == "assistant":
                answers.append(event["text"])
            elif event["type"] == "error":
                errors.append(event["text"])
            elif event["type"] == "subagent_note":
                self.send(event["text"])

        try:
            agent.run_turn(self.messages, text, self.approve, emit,
                           hidden_tools={WAIT}, system_suffix=AUTO_PHONE_PROMPT if self.auto_approve else PHONE_PROMPT,
                           agent_state=self.agent_state, child_approve=self.approve_subagent)
        except agent.ModelUnavailable as error:
            self.send(str(error) + "\nI kept the conversation and completed tool results. Send continue to try again.")
            print("Phone model request unavailable; conversation and tool results retained.", flush=True)
            return
        except RuntimeError as error:
            # A failure could interrupt a tool batch; don't resend malformed
            # tool-call history or automatically retry an uncertain action.
            if self.agent_state.manager is not None:
                self.agent_state.manager.close()
            self.messages = agent.conversation()
            self.agent_state = agent.Agent(max_seconds=None)
            reason = str(error)
            for name in ("API_KEY", "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "EMAIL_APP_PASSWORD"):
                secret = os.environ.get(name)
                if secret:
                    reason = reason.replace(secret, "[redacted]")
            self.send("This turn failed: " + reason[:500] + "\nNo action will be retried automatically. "
                      "The conversation was reset; check the model/server connection before trying again.")
            print("Phone turn failed; conversation reset. " + reason[:500], flush=True)
            return
        self.send("\n".join(errors) if errors else (answers[-1] if answers else "The turn completed without a text answer."))
        print("Phone turn completed.", flush=True)

    def run(self):
        self.send("Jasmine's Agent is ready in Telegram mode. Send a question. "
                  + ("Automatic execution is enabled; commands and tools run without approval prompts. "
                     if self.auto_approve else "Use Telegram Reply on each approval request and type yes or no. ") +
                  "Use /new for a fresh conversation.")
        print("Telegram mode ready. Ctrl+C stops it. Phone history stays in memory.", flush=True)
        while True:
            if self.approval_active.is_set():
                time.sleep(0.05)
                continue
            with self.poll_lock:
                if not self.approval_active.is_set() and not self.pending:
                    self.pending.extend(self.poll(1))
                message = self.pending.popleft() if self.pending and not self.approval_active.is_set() else None
            if message is not None:
                self.handle(message)
