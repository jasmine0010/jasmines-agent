---
name: telegram
description: Use when the user is chatting through Telegram or asks to send a short answer or progress update to their configured private owner chat.
---

# Telegram

Replies are read on a phone. Keep them short, plain, and easy to scan.
For a long task, send one brief progress update with send_message, then the answer.
Do not send credentials, tokens, whole files, or sensitive research data.

The server fixes the recipient from TELEGRAM_CHAT_ID. Never invent a recipient.
Only messages from that private chat are returned. Messages are not end-to-end encrypted.

In Telegram mode the harness handles wait_for_messages and approval replies.
Do not poll that tool yourself in this mode. A declined command stays declined;
do not try a different tool or spelling to work around the user's answer.

Old messages sent while the server was stopped are deliberately skipped at startup.
Only one process should poll this bot at a time. If there is a polling conflict,
stop the duplicate process instead of repeatedly retrying.
