# Jasmine's Agent

A plain Python research-agent harness for AI in Research weeks 2-4. It calls
an OpenAI-compatible Chat Completions API directly, loads MCP plugins, and
uses the same loop for the main agent and its subagents. On Windows the
built-in `bash` tool runs PowerShell; on macOS/Linux it runs bash.

## Setup and run

Install Python 3.11+ and uv, copy `.env.example` to the ignored `.env`, and
enter your credentials locally. Configure `BASE_URL`, `API_KEY`, `MODEL`,
Telegram settings, `PSP_PYTHON`, and the dedicated agent Gmail settings as
needed. The PSP plugin uses Python 3.11-3.13; the example selects 3.13.
Never paste keys into chat or commit `.env`.

```sh
uv sync --locked
uv run --locked --env-file .env python web.py
uv run --locked --env-file .env python agent.py
uv run --locked --env-file .env python agent.py --telegram
```

Choose one interface command. The web interface binds to 127.0.0.1:8765 and
stores chats in ignored `history/`. Stop it with Ctrl+C. Only one Telegram
instance should poll the bot at a time. The web, terminal and Telegram
interfaces show usage, tool activity and subagent notes; `/agents` shows jobs.

## Plugins and approvals

`plugin_runtime.py` discovers `plugins/*/.claude-plugin/plugin.json`, expands
each `.mcp.json` without shell evaluation and keeps shared official MCP SDK
sessions on one asyncio loop. Tools use `server__tool` names. Skill names and
descriptions enter the prompt; an approved file read loads a skill's body.

The bundled plugins provide owner-only Telegram messaging, three read-only
PSP analysis tools over public measurement snapshots, and Gmail IMAP/SMTP.
See each plugin README for setup, units, conventions and limitations.
Email requires a dedicated agent account and a Google app password; run
`python configure_email.py` in a real terminal for masked local setup.
Incoming mail is untrusted data. Sending is restricted to exact configured
recipients, is absent from the general allow list and is never retried.

Published `settings.json` permits only the three read-only PSP tools without
repeated approval and sets `telegram_auto_approve` to false. Other shell/MCP
actions ask for approval. An owner can explicitly enable Telegram automatic
mode locally; child shell commands still ask with an agent label. Approvals
are serialized and cancelled on stop. Shell subprocesses exclude configured
model, Telegram and email credentials. Approvals and tool restrictions do not
provide an operating-system sandbox; commands run as the local user.

## Subagents

`agents/*.md` defines names, descriptions, tool lists, optional models and turn
limits. Missing tools means all plugin tools plus bash; an explicit empty list
means none. Unknown tools fail startup, and children never receive delegation
controls. The included types are `mail-reader`, `psp-wave-analyst`,
`process-demo` and `turn-limit-demo`.

`delegate(agent, task)` runs a fresh child synchronously and returns its
report/statistics. `subagent(action, ...)` supports `start`, `list`, `send`,
`wait`, `read` and `stop`. Each background child has a daemon thread, inbox
queue, stop event and its own messages, tools, state, usage and log. Model
configuration, MCP sessions, approvals and workspace are shared. Idle workers
retain their conversations and resume on `send`; stopped/failed workers
cannot resume. Child tools use the existing MCP asyncio loop.

At most four worker slots run across the harness. Turn limits accumulate
across follow-ups. The default 600-second active-time budget pauses while
idle. Completion, stop and failure notes enter the main agent's queue before
its next model call and appear in the interface. Full logs stay ignored under
`logs/<session>/<id>.jsonl`; `read` exposes bounded previews when requested.

`stop` sets the event and kills the owned shell process tree, using
CREATE_NEW_PROCESS_GROUP and `taskkill /T /F` on Windows, or a new session and
process-group kill on POSIX. A late model response cannot run tools or revive
a stopped child. Requests already sent may finish remotely; their worker slots
stay reserved until they unwind. Session shutdown stops retained workers.

## Verification

The root offline suite and plugin suites use synthetic fixtures rather than
live model or mail calls:

```sh
uv run --locked python -m unittest discover -s tests -v
uv run --locked python -m unittest discover -s plugins/jasmine0010-email/tests -v
uv run --no-project --with mcp==2.3.0 --with 'httpx>=0.28,<0.29' python -m unittest discover -s plugins/jasmine0010-telegram/tests -v
uv run --no-project --python 3.13 --with mcp==2.3.0 --with numpy==2.1.3 --with scipy==1.15.3 python -m unittest discover -s plugins/jasmine0010-psp-waves/tests -v
```

The 82 root checks include concurrency, context isolation, approvals, limits,
cancellation races and actual Windows shell/grandchild termination. Mail has
18 synthetic tests plus seven configuration checks. Separate stdio checks
validate MCP transport. Helpers named `demo_*` and `check_*live*`, and email
integration/send helpers, are explicitly live workflows; ordinary test
discovery does not run them. Do not rerun the class hello or delete its private
send-attempt record.

## Week 4 evidence and status

The owner confirmed self-mail delivery from Codex and approved dedicated
inbox data through OpenRouter for the actual harness. The reviewed hello was
accepted by SMTP once on October 29, 2026 at **6:59:57 p.m. PDT**. The class
welcome reply was dated 7:02:58 p.m. PDT and read at about 7:07 p.m. PDT.
No acknowledgement or further email was sent.

All five live demos used `nvidia/nemotron-3.5-lightning:free` through OpenRouter:

1. [Mail handoff](transcripts/01-mail-delegate.md): raw body stays with the
   child; the main gets its report.
2. [Three research workers](transcripts/02-research-fanout.md): 11.952 seconds
   of common overlap before the main combined the reports.
3. [Follow-up](transcripts/03-research-followup.md): the same thread/context,
   one more response and no new reading or agents.
4. [Process stop](transcripts/04-stop-process.md): the sleep ran for about
   3.1 seconds before termination; the OS confirmed its process was gone.
5. [Turn limit](transcripts/05-turn-limit.md): exactly three responses, then
   `failed` with `max_turns limit (3)` and a note in the main conversation.

The owner reviewed all five. Demos 2/3 preserve original generated scientific
claims alongside explicit corrections checked against actual tool outputs.
Their lifecycle checks do not certify every generated interpretation.
Sanitized receipts are under `validation/`; raw mail, drafts and conversations
stay ignored in `validation/week-4-private/` and `logs/`.

Implementation and demonstrations are complete. Publication review is pending.
Codex helped implement, explain, test and document the changes; the configured
NVIDIA model ran the live agent workflows. Licensed under MIT; see `LICENSE`.

Publication verification also fixed a Windows `taskkill` exit race: stop now
checks retained OS handles for the observed process tree, so a descendant
that exits during termination does not incorrectly mark a successful stop as
failed. The final 82-test harness suite includes that regression. Separate
Telegram and PSP offline suites each passed eight tests with their declared
dependencies; the public email plugin also passed its stdio protocol check.
