# HelioPhysics Agent

A small Python agent harness for the AI in Research week 2 homework. It calls an OpenAI-compatible Chat Completions API directly, maintains a conversation, and offers exactly one tool named `bash`. On Windows this tool runs PowerShell; on macOS and Linux it runs bash.

## Configure

Install uv, copy `.env.example` to `.env`, and enter your own API key locally. Set `BASE_URL`, `API_KEY`, and `MODEL`. Never paste keys into chat or commit `.env`. The example uses OpenRouter's free model router; model availability and rate limits vary.

## Run the current terminal version

From this directory:

```sh
uv run --env-file .env python agent.py --chat
```

Type `/quit` to exit. Every proposed command asks `Run this command? [y/N]`; pressing Enter declines. Shell commands run inside `workspace/`, which is ignored by Git. Each command has a 60-second time limit and at most 10,000 characters of captured output. Each question stops after at most 20 tool rounds. The tool runs with your user permissions; its workspace is a working directory, not a security sandbox.

Edit `system_prompt.md` to change the assistant's instructions. Conversation history lives in memory for the current chat.

## How the loop works

`agent.py` contains `run_turn`: append the user's message, send the complete conversation and tool definition, append the model's reply, and inspect `tool_calls`. If there are calls, validate their arguments, ask for approval, execute approved commands, append each result with its matching `tool_call_id`, and call the model again. A reply without tool calls ends the turn.

`shell_tool.py` implements approval, shell execution, output capture, timeout, and truncation. The interface supplies the approval function, so a terminal prompt or web buttons can drive the same loop.

## Status

OpenRouter is configured and verified. Plain chat, tool-call format, two-turn conversation memory, and one complete live model/tool/model turn passed. Local checks passed for approved execution, refusal without execution, failing commands, timeout, output limits, malformed arguments, and matching tool-call IDs.

We are at the instructor's loop-understanding checkpoint: the student should explain `run_turn` in their own words before proceeding. They chose a local web interface with Approve/Deny buttons; that interface is next, followed by the full interactive test checklist, a license, publishing approval, and an installation skill and submission PR.

The harness has not been published and no submission PR exists yet.

## This computer

uv: `C:\Users\Jasmi\.local\bin\uv.exe`

GitHub CLI: `C:\Program Files\GitHub CLI\gh.exe`

Class checkout: `C:\Users\Jasmi\ai-in-research-homework`

Instructor guide: https://github.com/huangzesen/ai-in-research-homework/blob/main/.agents/skills/build-a-harness/SKILL.md
