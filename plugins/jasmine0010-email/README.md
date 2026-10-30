# Dedicated agent Gmail plugin

Three tools provide IMAP inbox headers, a bounded plain-text message, and SMTP
sending. It uses Python's standard mail libraries and the official MCP Python
SDK pinned to 2.3.0. The server name is `email`, so the harness exposes
`email__check_inbox`, `email__read_message`, and `email__send_message`.

## Configure locally

Create a new Gmail account dedicated to the agent. Enable 2-Step Verification
and create an app password at https://myaccount.google.com/apppasswords.
Put the variables in `.env.example` into the harness's ignored `.env`, filling
them in locally. Never use a personal/school inbox or put passwords in chat.
Add the agent's address to `EMAIL_ALLOWED_RECIPIENTS` for the self-mail test.
Sending is restricted to exact entries in this comma-separated list; an empty
list blocks all sending. Adding a recipient does not authorize arbitrary mail:
the agent skill still requires the owner's request and review of the hello.

For masked local setup, run `python configure_email.py --env-file PATH_TO_ENV`
in a real terminal. This helper asks for the dedicated Gmail address and a new
Google app password without echoing it, removes the display spaces, and writes
quoted dotenv values. It sets the recipient list to the agent account and class
agent only. It does not send mail. Never put the password in a command argument.

Copy this directory to `plugins/jasmine0010-email/` in Jasmine's Agent. Its
existing plugin loader expands `.mcp.json` without shell evaluation and runs
`uv run --script server.py`. Restart the harness after configuration. Keep the
send tool off the harness's general tool allow list; the server's recipient
restriction also applies in automatic Telegram mode.

For a standalone stdio launch from the harness directory:

```powershell
uv run --env-file .env --script plugins/jasmine0010-email/server.py
```

stdout is reserved for MCP JSON-RPC. Use an MCP client rather than typing email
requests into the server's terminal. Do not put passwords in command arguments.

## Behavior and limits

- `check_inbox(unread_only=True, limit=10)` returns newest INBOX UIDs first,
  with sender, subject, date and Message-ID. Limit is 1-20; listing uses PEEK
  and a read-only mailbox so it does not mark mail read.
- `read_message(id)` prefers text/plain and strips HTML otherwise, excluding
  attachments. It downloads at most 1 MiB, returns at most 5000 body characters
  plus a truncation notice, and marks that UID read. UIDs apply to this INBOX;
  list again after moving messages or recreating a mailbox.
- `send_message(to, subject, body)` accepts one bare allow-listed recipient,
  a subject up to 200 characters and plain-text body up to 20000 characters.
  It rejects header injection and never adds CC/BCC or attachments. It returns
  a Message-ID after Gmail SMTP accepts the message, not proof of delivery.

Connections use verified TLS (IMAP 993, SMTP 465) and 20-second socket timeouts.
No send is retried automatically. Check Gmail Sent if delivery is uncertain.
No mail content, credentials or raw provider exceptions are printed by the
server. Mail returned to the model is explicitly labeled untrusted; see the
skill for instruction-handling rules. An allow list is a recipient restriction,
not a substitute for those rules.

## Verification status

All 18 synthetic offline tests passed on Windows on October 28, 2026. An
independent SDK client also passed stdio initialization, tool discovery, UID
injection rejection and missing-credential handling. The subprocess protocol
check required normal Windows process access outside the restricted sandbox.

From this plugin directory, using a Python environment with `mcp==2.3.0`:

```powershell
python -m unittest discover -s tests -v
python tests/check_stdio.py
```

Seven additional synthetic configuration checks passed on October 29, 2026.
Live IMAP and SMTP authentication also passed that day. A separate ephemeral
Codex session sent one self-test email and read it back, verifying the exact
subject and body marker; the owner confirmed seeing the message. The plugin
is installed in Jasmine's Agent and its real model loop successfully called
both inbox read tools. Nine relevant harness permission checks passed,
including exclusion of the app password from shell-child environments.
The owner reviewed and approved the agent-authored hello. The harness sent
the exact saved draft once; SMTP accepted it on October 29, 2026 at
6:59:57 p.m. PDT. The class welcome reply was received and read by the harness
at about 7:07 p.m. PDT. A send-attempt receipt prevents duplicate class mail;
no acknowledgement or other follow-up email was sent.

`launch_local.py --env-file PATH_TO_ENV` loads only the three email fields
without echoing malformed dotenv values. `--self-test-only` restricts the
recipient to this agent account and permits only one send attempt per process.
`tests/check_codex.py --env-file PATH_TO_ENV --receipt PATH_TO_RECEIPT` performs
a live test in an ephemeral Codex session with shell tools disabled, a read-only
sandbox and automatic approval review. It sends one self-mail, searches for its
unique subject and reads that message only. This is an explicitly live check;
do not run it as part of offline unit tests or automatically retry an uncertain
send. Its receipt contains test metadata and the agent's report, not raw inbox
contents or credential values.

`tests/check_harness.py --harness PATH_TO_HARNESS` is a separate live check.
The owner must approve sending dedicated-inbox data through the configured
model provider before running it. It uses the real harness loader and model
loop, starts the email and research servers for agent-type validation while
leaving Telegram polling alone,
reads the matching self-test, and asks the agent for its hello draft. Sending
and shell tools are disabled for this check. The draft and full conversation
are saved under the harness's ignored `validation/week-4-private/` folder;
only metadata appears in its integration receipt.

`tests/send_hello.py --harness PATH_TO_HARNESS --approved` is a live,
one-time workflow requiring explicit owner review of the saved draft. The
agent invokes a send action bound to that draft; the harness supplies its exact
recipient, subject and body rather than asking the model to regenerate them.
An exclusive attempt file is written before SMTP dispatch, so a model repeat,
restart or uncertain outcome cannot automatically resend the class hello.
Do not remove the attempt record to retry a send.

`tests/check_reply.py --harness PATH_TO_HARNESS` uses the actual agent loop to
read the class reply with sending and shell tools disabled. Both workflows
retain raw conversations and mail only under the harness's ignored private
validation directory. They use the dedicated-inbox/model data flow approved
by the owner.
