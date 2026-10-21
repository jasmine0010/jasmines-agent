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

The loop-understanding checkpoint is complete. The local web interface includes saved conversations, rename/delete controls, and default sans-serif typography throughout. Windows checks verified approval, denial, saved-chat recovery across a server restart, and conversation context after reopening.

All 12 offline tests pass. Four live model checks also passed: synthetic file listing, two separately approved commands in sequential tool rounds, a real missing-program failure explained by the model, and denial without shell execution. Every API call reported token usage. The filesystem checks used a disposable fixture rather than scanning the home directory.

An MIT license and the installation-skill draft are prepared locally. The skill is in the class checkout at `week-2/submissions/jasmine0010/SKILL.md`, on the local `week-2-jasmine0010` branch. Publication checks found no configured API key or recognized access-token pattern in tracked files or Git history; private `.env`, chat history, and workspace files remain ignored.

The installation workflow passed in a fresh temporary local clone: locked dependency setup, configuration via inherited environment settings, all 12 offline tests, localhost web launch, approved listing, denial, deliberate failed-command recovery in an independent chat, token usage, saved-chat rename/reopening, and the credential scan. Receipts are in `validation/live-checks.json` and `validation/fresh-install.json`. The temporary clone and its test server were removed.

The user has explicitly withheld permission to push, publish, or submit. No remote repository has been created, no push has been made, and no submission PR exists. All currently permitted local checks are complete. Next: hold for review and explicit publication approval; then verify a clone from the public URL. Pushing the class branch and opening a PR also require the user's permission.

## Week 2 comparison check (October 21, 2026)

Reviewed the nine open Week 2 installation-skill submissions (class PRs #9–#17), and inspected the core code of AI Study Agent, Research agent, and Pedro Agent at commits preceding their Week 2 PRs. Jasmine's Agent uses the same direct API / conversation / approved shell / tool-result loop, with the required token usage, timeout, and output limit. Saved chat history and rename/delete controls extend the assignment's basic requirements.

All 12 offline checks passed both in this working copy and in a fresh temporary local clone without the private .env or chat database. Testing was on Windows; peer applications were inspected rather than executed. This comparison is not an instructor grade or a cross-platform runtime certification.

The implementation matches the functional requirements. The license and installation skill have now been prepared locally and the remaining live loop checks have passed. Public-repository and submission verification remain pending the user's explicit publication approval.

Peer code snapshots:
- https://github.com/WenyuZhang2001/ai-study-agent/blob/991acd66f7811150ed88bbcc539fddd2957fc5d8/agent.py
- https://github.com/hleinweber/research-agent/blob/8228d8fe161152aa2e29391107d2e7a71ac72af9/agent.py
- https://github.com/Caltz27/pedro-agent/blob/71964397106065588bcc1e6bcf8cd77ac0182358/agent.py

## Tests

```sh
uv run python -m unittest discover -s tests -v
```

The tests use synthetic data and a mock model; they never contact a provider or require an API key.

## Optional live and publication checks

These commands use the locally configured key; live checks contact the model provider and approve only exact synthetic test commands:

```sh
uv run --env-file .env python tests/live_checks.py
uv run --env-file .env python tests/check_publication.py
```

Receipts are under `validation/`. The publication check reports filenames and counts, never credential values. It checks tracked files and Git history for the configured API key, recognized token patterns, and accidentally tracked runtime data.

## License

MIT; see `LICENSE`.

Instructor guide: https://github.com/huangzesen/ai-in-research-homework/blob/main/.agents/skills/build-a-harness/SKILL.md
