"""A small agent loop: messages -> model -> approved tool -> messages."""

import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from shell_tool import TOOL, run_bash

ROOT = Path(__file__).resolve().parent
MAX_TOOL_ROUNDS = 20


def call_model(messages, tools=None):
    """Send the complete conversation to the configured model API."""
    settings = {name: os.environ.get(name, "") for name in ("BASE_URL", "API_KEY", "MODEL")}
    missing = [name for name, value in settings.items() if not value or value.startswith("replace_")]
    if missing:
        raise RuntimeError("Configure " + ", ".join(missing) + " in .env first.")
    payload = {"model": settings["MODEL"], "messages": messages, "max_tokens": 2048}
    if tools:
        payload["tools"] = tools
    request = Request(
        settings["BASE_URL"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + settings["API_KEY"], "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Model API returned HTTP {error.code}. Check the key, model, credits, or rate limits.") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Could not reach the model API, or the request timed out.") from None
    if result.get("error") or not result.get("choices"):
        raise RuntimeError("The model API returned an error or no choices.")
    return result


def usage_text(result):
    """Cached tokens are a subset of input tokens; absent counts stay unknown."""
    usage = result.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    return (
        f"Tokens: input={usage.get('prompt_tokens', 'not reported')}, "
        f"cached input={details.get('cached_tokens', 'not reported')}, "
        f"output={usage.get('completion_tokens', 'not reported')}"
    )


def conversation():
    return [{"role": "system", "content": (ROOT / "system_prompt.md").read_text(encoding="utf-8-sig")}]


def execute_tool(call, approve):
    """Validate model-written arguments before reaching the shell tool."""
    try:
        function = call["function"]
        arguments = json.loads(function["arguments"])
        if function["name"] != "bash":
            return {"error": "Unknown tool; only bash is available."}
        if not isinstance(arguments, dict) or set(arguments) != {"command"}:
            return {"error": "Expected exactly one argument: command."}
        return run_bash(arguments["command"], approve)
    except (KeyError, TypeError, ValueError):
        return {"error": "Invalid tool arguments. Provide a JSON object with one string command."}
    except OSError:
        return {"error": "The shell could not be started or its working folder is unavailable."}


def run_turn(messages, prompt, approve, emit):
    """The agent loop. The interface supplies approval and displays events."""
    messages.append({"role": "user", "content": prompt})
    for round_number in range(MAX_TOOL_ROUNDS):
        result = call_model(messages, [TOOL])  # 1. Resend the conversation and tool.
        emit({"type": "usage", "text": usage_text(result), "model": result.get("model")})
        message = result["choices"][0]["message"]
        messages.append(message)  # 2. Remember the model's reply, including tool IDs.
        if message.get("content"):
            emit({"type": "assistant", "text": message["content"]})
        calls = message.get("tool_calls") or []
        if not calls:  # 3. Plain text ends this turn; wait for the next user message.
            return
        for call in calls:  # 4. Execute each tool only after the user approves it.
            output = execute_tool(call, approve)
            emit({"type": "tool_result", "result": output})
            messages.append({  # 5. Give the result back using the same tool-call ID.
                "role": "tool", "tool_call_id": call["id"],
                "content": json.dumps(output),
            })
        # 6. Repeat so the model can use the results or request another command.
    emit({"type": "error", "text": "Stopped at the 20-round limit. Send a new message to continue."})


def terminal_approve(command):
    print("\nProposed command:\n" + command)
    try:
        return input("Run this command? [y/N] ").strip().lower() in {"y", "yes"}
    except EOFError:
        return False


def terminal_emit(event):
    if event["type"] == "tool_result":
        print(json.dumps(event["result"], indent=2))
    else:
        print(event["text"])
        if event.get("model"):
            print("Model:", event["model"])


def main():
    messages = conversation()
    if sys.argv[1:] == ["--chat"]:
        print("Chat with HelioPhysics Agent. Type /quit to finish.")
        while True:
            try:
                prompt = input("You: ").strip()
            except EOFError:
                break
            if prompt == "/quit":
                break
            if prompt:
                try:
                    run_turn(messages, prompt, terminal_approve, terminal_emit)
                except RuntimeError as error:
                    print(f"Error: {error}")
    else:
        run_turn(messages, " ".join(sys.argv[1:]) or "Say hello in one sentence.", terminal_approve, terminal_emit)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


