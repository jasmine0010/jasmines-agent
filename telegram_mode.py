"""Phone interface for the same agent loop, with approvals tied to replies."""

from collections import deque
import os
import time

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
skill once and reuse it within the conversation. Keep replies short and plain.
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
        self.approval_ids = set()
        self.messages = agent.conversation()
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

    def approve(self, action):
        if self.auto_approve:
            kind = action.splitlines()[0] if action.startswith("MCP tool ") else "shell"
            print("Phone automatic execution: " + kind, flush=True)
            return True
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
        while time.monotonic() < deadline:
            batch = self.poll(min(30, max(1, int(deadline - time.monotonic()))))
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
        self.send("Approval timed out. The action was declined.")
        print("Phone approval: timed out (declined)", flush=True)
        return False

    def handle(self, message):
        text = message["text"].strip()
        if not text or message.get("reply_to_message_id") in self.approval_ids:
            return
        if text.lower() in {"yes", "no"}:
            self.send("There is no pending approval. Send a question to begin.")
            return
        if text == "/new":
            self.messages = agent.conversation()
            self.send("Started a new conversation.")
            return
        if text == "/start":
            self.send("Ready. Send a question; use /new to reset this conversation.")
            return
        self.send("Working on your question. " + (
            "Automatic execution is enabled." if self.auto_approve else "I will ask before running actions."))
        answers, errors = [], []

        def emit(event):
            if event["type"] == "assistant":
                answers.append(event["text"])
            elif event["type"] == "error":
                errors.append(event["text"])

        try:
            agent.run_turn(self.messages, text, self.approve, emit,
                           hidden_tools={WAIT}, system_suffix=AUTO_PHONE_PROMPT if self.auto_approve else PHONE_PROMPT)
        except RuntimeError as error:
            # A failure could interrupt a tool batch; don't resend malformed
            # tool-call history or automatically retry an uncertain action.
            self.messages = agent.conversation()
            reason = str(error)
            for name in ("API_KEY", "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
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
            if not self.pending:
                self.pending.extend(self.poll())
            while self.pending:
                self.handle(self.pending.popleft())
