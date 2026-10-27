# Jasmine's Agent

A small Python agent harness for the AI in Research week 2 homework. It calls an OpenAI-compatible Chat Completions API directly, maintains a conversation, and offers a built-in tool named `bash`, plus tools loaded from local MCP plugins. On Windows this tool runs PowerShell; on macOS and Linux it runs bash.

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

The harness is released under the MIT license, and its installation skill is prepared for the Week 2 class submission. The skill is in the class checkout at `week-2/submissions/jasmine0010/SKILL.md`, on the local `week-2-jasmine0010` branch. Publication checks found no configured API key or recognized access-token pattern in tracked files or Git history; private `.env`, chat history, and workspace files remain ignored.

The installation workflow passed in a fresh temporary local clone: locked dependency setup, configuration via inherited environment settings, all 12 offline tests, localhost web launch, approved listing, denial, deliberate failed-command recovery in an independent chat, token usage, saved-chat rename/reopening, and the credential scan. Receipts are in `validation/live-checks.json` and `validation/fresh-install.json`. The temporary clone and its test server were removed.

The owner authorized Week 1 and Week 2 publication on October 21, 2026. The tested Week 2 version is public at https://github.com/jasmine0010/jasmines-agent, and its installation skill is submitted in https://github.com/huangzesen/ai-in-research-homework/pull/23. A fresh public clone passed locked setup, all 12 Week 2 offline checks, and localhost web startup. Earlier live checks passed on the same implementation; they were not repeated because the free-model quota was exhausted. The public-clone receipt is validation/public-install.json.

This branch contains the Week 3 extension. The public main branch retains the tested Week 2 version; use the week-3 branch for Telegram and PSP plugins. Week 3 publication is awaiting final phone verification and owner approval. The Week 1 submission is waiting for the class tool's instruction/window/publication records in the student's own terminal.

## Week 2 comparison check (October 21, 2026)

Reviewed the nine open Week 2 installation-skill submissions (class PRs #9–#17), and inspected the core code of AI Study Agent, Research agent, and Pedro Agent at commits preceding their Week 2 PRs. Jasmine's Agent uses the same direct API / conversation / approved shell / tool-result loop, with the required token usage, timeout, and output limit. Saved chat history and rename/delete controls extend the assignment's basic requirements.

All 12 offline checks passed both in this working copy and in a fresh temporary local clone without the private .env or chat database. Testing was on Windows; peer applications were inspected rather than executed. This comparison is not an instructor grade or a cross-platform runtime certification.

The implementation matches the functional requirements. The license and installation skill have now been prepared locally and the remaining live loop checks have passed. The Week 2 repository is now public and the installation skill is submitted as PR #23.

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

## Week 3 status

Both MCP plugins are implemented: jasmine0010-telegram and jasmine0010-psp-waves. The owner confirmed delivery from Codex and from the normal harness web chat, and completed the tool/skill context checkpoint. All 11 research measurements fall within the Week 1 acceptance ranges, satisfying the owner's scientific-review criterion; see validation/week-3-scientific-review.json.

The loader and Telegram mode are implemented. All 30 harness tests and eight Telegram plugin tests pass; the eight research tests previously passed. Both plugins have worked through independent stdio clients and Codex. The owner explicitly authorized the three read-only PSP tools in settings.json: list_psp_intervals, analyze_psp_waves, and compare_psp_wave_intervals. These run without repeated approval; every bash command and other model-requested MCP action still asks.

The owner confirmed phone command approval, denial, and free-space reporting. Live owner filtering passed with a temporary wrong receiver ID, and restart checks discarded an old message and delivered a fresh message once. The remaining check is a PSP research answer from the phone. The provider quota and Telegram DNS issues from earlier sessions have cleared; the bot is running for this check on October 26, 2026. The local class submission is prepared. Publication and the Week 3 PR await the owner's final review.


## Plugins and approvals

Run `uv sync --locked` after updating, then use the existing web or terminal commands with `--env-file .env`. On startup the harness reports plugins, tool names and skills. It shows each model call's usage; the first call of each turn is also printed to the server terminal.

`plugin_runtime.py` discovers `plugins/*/.claude-plugin/plugin.json`, expands each stdio server's `.mcp.json`, and keeps official MCP SDK clients open until shutdown. The OpenAI-compatible API receives each MCP input schema as a function tool named `server__tool`. Skill names, descriptions and absolute SKILL.md paths enter the system prompt; bodies are read through an approved bash call only when needed. Reopened web chats refresh this metadata on their next turn.

`settings.json` allows only the three owner-approved read-only PSP tools: `psp_waves__list_psp_intervals`, `psp_waves__analyze_psp_waves`, and `psp_waves__compare_psp_wave_intervals`. Other model-requested MCP actions ask for approval; bash always asks regardless of that list. Shell children do not inherit the configured model API key or Telegram bot token. This is a working-directory and approval boundary, not an operating-system sandbox.

The research server reads only its bundled public measurement snapshot. See each plugin README for its environment settings, units, conventions, and second-host setup. Use the Telegram-mode command below to receive questions and approvals on your phone.

## Telegram mode

Stop other instances of this bot first; only one host should poll it. From the harness directory:

```sh
uv run --locked --env-file .env python agent.py --telegram
```

Send a question to the configured bot. For each proposed command or MCP action, use Telegram's Reply action on its approval request (the final part if split) and type yes or no. Only yes approves, ignoring case and whitespace; another reply declines. Approval expires after three minutes. A reply to an older request or an unlinked yes cannot approve a new action. The full action is shown without truncation.

The three trusted PSP tools run directly; shell commands and other model-requested tools still ask. The harness owns polling and sends its progress, approval requests and final answers through fixed Telegram MCP channel methods. These interface operations do not ask for approval recursively. The model retains send_message under the ordinary permission policy, but wait_for_messages is withheld from its schemas and blocked in dispatch. Unrelated questions received while awaiting approval are queued for later turns.

Conversation history stays in memory across phone messages. Send /new to start fresh; Ctrl+C in the terminal stops the harness. On startup the Telegram server discards the old update backlog. On a failed model/tool turn the phone conversation resets rather than automatically retrying an uncertain action. The web interface's saved chats are separate.

The bot accepts only the configured private owner chat. Its token stays in the ignored .env and the Telegram server environment; it is not added to model context. Approved commands still run with your account's permissions and can access files, so approval is not a security sandbox. Telegram bot messages are not end-to-end encrypted: do not send secrets or private research data.
