# Jasmine's Agent

A small Python agent harness for the AI in Research week 2 homework. It calls an OpenAI-compatible Chat Completions API directly, maintains a conversation, and offers exactly one tool named `bash`. On Windows this tool runs PowerShell; on macOS and Linux it runs bash.

## Configure

Install uv, copy `.env.example` to `.env`, and enter your own API key locally. Set `BASE_URL`, `API_KEY`, and `MODEL`. Never paste keys into chat or commit `.env`. The example uses OpenRouter's free model router; model availability and rate limits vary.

## Run the web interface

From this directory:

```sh
uv run --env-file .env python web.py
```

Open http://127.0.0.1:8765 in your browser. The server binds only to this computer. Each proposed command has Approve and Deny buttons; token counts and command results appear in the chat. The sidebar opens saved chats. New chat creates a separate conversation without clearing earlier ones. Use Rename and Delete in the chat header; deletion asks for confirmation. Chats survive page refreshes and server restarts. Press Ctrl+C in the server terminal to stop it.

One global CSS rule enforces the browser's default sans-serif font for every element and its pseudo-elements, including branding, headings, chat history, dialogs, buttons, inputs, command output, and token usage. Semibold and bold weights provide emphasis.

To use a different port: `uv run --env-file .env python web.py --port 8766`.

## Saved chats

The web interface saves titles, messages, command approvals/results, and token usage automatically in `history/chats.sqlite3`. This folder is excluded from Git. The API key is read from the environment and is not included in chat records.

Select a conversation in the sidebar to continue it. Chats receive a title from the first message; Rename lets you choose your own title. New chat leaves existing conversations intact. Delete removes the selected conversation's saved record after confirmation. A running chat must finish before it can be deleted; you can switch chats while a command waits for approval.

If the server stops during a turn, reopening the chat marks that turn as interrupted and completes any missing tool-result records. Commands are never automatically resumed; an interrupted command's outcome may be unknown. You can send a new message to continue the conversation.

## Run the current terminal version

From this directory:

```sh
uv run --env-file .env python agent.py --chat
```

Type `/quit` to exit. Every proposed command asks `Run this command? [y/N]`; pressing Enter declines. Shell commands run inside `workspace/`, which is ignored by Git. Each command has a 60-second time limit and at most 10,000 characters of captured output. Each question stops after at most 20 tool rounds. The tool runs with your user permissions; its workspace is a working directory, not a security sandbox.

Edit `system_prompt.md` to change the assistant's instructions. The terminal version keeps history in memory for its current session; the web interface saves chat history locally.

## How the loop works

`agent.py` contains `run_turn`: append the user's message, send the complete conversation and tool definition, append the model's reply, and inspect `tool_calls`. If there are calls, validate their arguments, ask for approval, execute approved commands, append each result with its matching `tool_call_id`, and call the model again. A reply without tool calls ends the turn.

`shell_tool.py` implements approval, shell execution, output capture, timeout, and truncation. The interface supplies the approval function, so a terminal prompt or web buttons can drive the same loop.

## Status

The student explained the agent loop correctly, including why each call resends the conversation. OpenRouter plain chat, conversation memory, tool-call format, and a full model/tool/model turn are verified. The chosen local web interface is implemented and running; browser tests confirmed that Approve executes the displayed command and Deny sends a refusal back to the model without execution. Input, cached-input, and output usage appear per API call.

All 12 offline tests pass. Coverage includes chat persistence, renaming, deletion after reopening storage, recovery without command execution, independent approvals, invalid arguments, the round limit, shell failures/timeouts/output limits, and web request protection. Browser checks verified chat creation, switching, renaming, refresh, and a full server restart; a follow-up model request successfully used its saved conversation context.

The student requested the Jasmine's Agent name and persistent chats with rename/delete controls; these are implemented. The updated interface is available for the instructor's interface-review checkpoint. Next: finish the assignment's interactive test checklist, add a license, review and approve publishing, then publish the harness and prepare and test its installation skill and submission PR. Nothing has been published and no submission PR exists yet.

## Tests

```sh
uv run python -m unittest discover -s tests -v
```

The tests use synthetic data and a mock model; they never contact a provider or require an API key.

## This computer

uv: `C:\Users\Jasmi\.local\bin\uv.exe`

GitHub CLI: `C:\Program Files\GitHub CLI\gh.exe`

Class checkout: `C:\Users\Jasmi\ai-in-research-homework`

Instructor guide: https://github.com/huangzesen/ai-in-research-homework/blob/main/.agents/skills/build-a-harness/SKILL.md
