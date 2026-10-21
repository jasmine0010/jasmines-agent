# Jasmine's Telegram plugin

An MCP stdio server using the official Python SDK 2.3.0 and Telegram long polling.
Two tools: `send_message(text)` sends plain text to one configured private chat;
`wait_for_messages(seconds=30)` waits for new owner text (capped at 50 seconds).
No publicly reachable server is needed.

## Configure

Install Python 3.11+ and uv. Create a bot with Telegram's @BotFather, then enter
these settings locally in your harness's ignored `.env` file:

```dotenv
TELEGRAM_BOT_TOKEN=replace_with_your_bot_token
TELEGRAM_CHAT_ID=replace_with_your_positive_private_chat_id
```

Send `/start` to your bot first. Never paste the token into an AI conversation or
commit it. If it leaks, revoke it with `/revoke` in BotFather. Messages to bots
are not end-to-end encrypted; use public or synthetic research data.

The server reads environment variables, not `.env` automatically. The host must
load `.env` or pass the two variables to the subprocess. It fails at startup
when settings are missing, skips queued messages on each start, and logs dropped
foreign-chat updates to stderr without their text or IDs. stdout is only MCP.
Sending has a fixed recipient; tools cannot choose another chat.

## Load in Claude Code

With both variables exported in the shell, from the harness repository:

```sh
claude --plugin-dir ./plugins/jasmine0010-telegram
claude plugin validate ./plugins/jasmine0010-telegram
```

Check `/mcp`, then request a short test message. `uv` must be on PATH.
The manifest's `${CLAUDE_PLUGIN_ROOT}` expands to this plugin's directory.

## Load in another MCP host

Launch `uv run --script /absolute/path/to/server.py` as a stdio MCP server,
passing just the two Telegram environment variables. Use an absolute path on
Windows too. Do not place the token in command arguments or tracked configs.
An SDK client can list and call the same tools independently of the harness.

### Codex

With both variables exported in the shell, set a stdio server in your local
Codex configuration (replace the example path with your plugin's absolute path):

```toml
[mcp_servers.telegram]
command = "uv"
args = ["run", "--script", "C:/absolute/path/to/jasmine0010-telegram/server.py"]
env_vars = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
startup_timeout_sec = 60
required = true
```

Keep credentials out of this configuration. `env_vars` forwards the values from
the launching shell. Alternatively, from the harness folder run
`uv run --env-file .env codex` to load its ignored `.env` before Codex starts.
In a fresh Codex session, ask it to send a short hello and approve the tool.
Do not keep two hosts polling the same bot simultaneously.

[Official OpenAI documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
describes the stdio environment and timeout settings.

## Harness integration status

This plugin is installed in `plugins/jasmine0010-telegram/`. The harness expands
`.mcp.json`, discovers these tools and lists this plugin's skill metadata in the
system prompt. The model then chooses tool calls; the host enforces permissions
and handles secrets outside the model context. The owner's `settings.json` allows
the three read-only PSP research tools. Every other model-requested MCP call asks
for approval, as does every bash command. Terminal, web chat, and Telegram mode support plugins.

Only one process should poll the bot. In Telegram mode the harness owns polling
and must withhold wait_for_messages from the model so it cannot swallow replies.
Every shell command still requires an explicit approval in the user's chat.

From the harness directory, stop other instances using this bot, then run:

```sh
uv run --locked --env-file .env python agent.py --telegram
```

The harness handles polling, progress, approval prompts and final-answer delivery
through the same MCP client. These interface operations do not recursively ask
for approval. Every model-requested action still uses the normal approval policy;
the model is offered send_message but cannot call wait_for_messages in this mode.

Use Telegram's **Reply** action on the approval request (the final part if split),
then type **yes** or **no**. Only an exact yes, ignoring case and surrounding
spaces, approves; every other reply declines. Requests expire after three minutes.
Old replies and an unlinked yes never approve a new action. Unrelated questions
are queued. `/new` resets the in-memory conversation. Ctrl+C stops the harness.
The server's send result includes message IDs and its incoming records include
reply_to_message_id, allowing approvals to be tied to one specific request.

## Validation

From a directory with this plugin's dependencies available:

```sh
uv run --with mcp==2.3.0 --with 'httpx>=0.28,<0.29' python -m unittest discover -s tests -v
```

Tests use mocked HTTP traffic, including wrong-chat rejection, startup backlog,
offset advancement, message splitting, polling limits, and redacted API errors.
Live phone delivery and a second-host check must be recorded separately.

On October 21, 2026, all eight offline checks passed on Windows. A separate SDK
client launched the real server over stdio, discovered both tools, and called
wait_for_messages successfully. Codex then launched the same server and called
send_message once; Telegram returned `status=sent, parts=1`. The phone receipt
checkpoint was confirmed by the owner. Claude Code is not installed
on the test machine, so its manifest validator has not been run.

To repeat the real stdio test from the harness folder (this skips pending messages
when it starts, as the server normally does):

```sh
uv run --env-file .env --script plugins/jasmine0010-telegram/tests/smoke_stdio.py
```

Add `--send` only when a fixed SDK connection-test message is desired.

References: [MCP SDK](https://py.sdk.modelcontextprotocol.io/),
[Telegram Bot API](https://core.telegram.org/bots/api),
[plugin layout](https://code.claude.com/docs/en/plugins-reference).
