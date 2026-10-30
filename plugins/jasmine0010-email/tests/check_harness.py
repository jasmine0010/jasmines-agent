"""Live harness email check and hello draft; sending is disabled.

Requires owner approval to send dedicated-inbox data to the configured model.
Private conversations/drafts are saved only under the harness's ignored
validation/week-4-private directory, never in the class submission.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", type=Path, required=True)
    args = parser.parse_args()
    root = args.harness.resolve()
    sys.path.insert(0, str(root))
    import agent
    from plugin_runtime import PluginRuntime

    for line in (root / ".env").read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if separator and re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            if len(value) > 1 and value[0] == value[-1] and value[0] in {"\"", "'"}:
                value = value[1:-1]
            os.environ[key] = value
    runtime = PluginRuntime(root)
    assert "jasmine0010-email" in runtime.plugins
    # Use the real loader without starting another Telegram poller.
    runtime.servers = [entry for entry in runtime.servers if entry[0] in {"email", "psp_waves"}]
    fields = [
        "class: AI in Research 2026",
        "github: jasmine0010",
        "agent: Jasmine's Agent",
        "harness: https://github.com/jasmine0010/jasmines-agent",
        "model: " + os.environ["MODEL"],
        "plugins: telegram, jasmine0010-psp-waves, email",
        "research: I study Alfvénic wave energy and cross helicity in Parker Solar Probe magnetic-field and plasma measurements.",
        "reply-to: " + os.environ["EMAIL_ADDRESS"],
    ]
    subject = "[AIR-2026 hello] jasmine0010"
    skill = (root / "plugins/jasmine0010-email/skills/email/SKILL.md").read_text(encoding="utf-8")
    prompt = (
        "The owner approved this dedicated-inbox data flow through the configured OpenRouter model. "
        "First use email__check_inbox(unread_only=false, limit=10) to verify the plugin works in this harness. "
        "If the exact subject [AIR-2026 self-test] jasmine0010 f9937893 appears, read that message only to confirm its marker. "
        "Do not read other message bodies. Then write your class hello draft for owner review. Do not send any email. "
        "The final answer must consist only of Subject: " + subject + "\n\n" + "\n".join(fields) + "\n\n"
        "followed by a note of at most 100 words written in your own voice: who you are and what you can do for this research. "
        "Preserve the eight fields exactly, in order. No markdown fences or extra commentary. "
        "The owner has not approved the draft yet. The harness already loaded your email skill into this task."
    )
    events = []

    def emit(event):
        events.append(event)
        if event.get("type") == "usage":
            print(event["text"], flush=True)

    def approve(request):
        return any(request.startswith("MCP tool " + name + "\n")
                   for name in ("email__check_inbox", "email__read_message"))

    with runtime:
        agent.PLUGINS = runtime
        try:
            messages = agent.conversation()
            agent.run_turn(messages, prompt, approve, emit,
                           hidden_tools=("bash", "email__send_message", "delegate", "subagent"),
                           system_suffix="\n\nFull email skill, loaded by the harness for this task:\n" + skill)
        finally:
            agent.PLUGINS = None
    assistant = [event["text"] for event in events if event.get("type") == "assistant"]
    text = assistant[-1] if assistant else ""
    header, separator, candidate_body = text.partition("\n")
    candidate_body = candidate_body.lstrip("\n")
    prefix = "\n".join(fields) + "\n\n"
    valid = header == "Subject: " + subject and bool(separator) and candidate_body.startswith(prefix)
    note = candidate_body[len(prefix):].strip() if valid else ""
    valid = valid and 0 < len(note.split()) <= 100
    calls = [call["function"]["name"] for message in messages for call in message.get("tool_calls", [])]
    private = root / "validation/week-4-private"
    private.mkdir(parents=True, exist_ok=True)
    (private / "hello-draft-conversation.json").write_text(json.dumps(messages, indent=2) + "\n", encoding="utf-8")
    if valid:
        draft = {"to": "lingtai2026@gmail.com", "subject": subject, "body": "\n".join(fields) + "\n\n" + note}
        (private / "hello-draft.json").write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
    receipt = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
               "email_plugin_discovered": True, "email_tools": sorted(runtime.routes),
               "actual_model": os.environ["MODEL"], "model_tool_calls": calls,
               "draft_format_valid": valid, "note_word_count": len(note.split()), "email_sent": False}
    (root / "validation/week-4-email-integration.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    print(text if valid else "The draft needs a formatting correction; private conversation saved locally.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError):
        print("Live harness check could not finish. No email was sent and credential values were not displayed.", file=sys.stderr)
        sys.exit(1)
