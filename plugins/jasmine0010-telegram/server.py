# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0", "httpx>=0.28,<0.29"]
# ///
"""Telegram transport for one owner; stdout belongs exclusively to MCP."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os
import sys

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver import Context

# HTTP request logs contain the bot token in the URL. Never enable them.
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("httpcore").setLevel(logging.CRITICAL)
LOG = logging.getLogger("owner_telegram")


def message_parts(text):
    """Respect 4096 even when a character occupies two UTF-16 code units."""
    if not text.strip():
        raise ValueError("Message text is empty. Provide a nonempty plain-text reply.")
    start, units = 0, 0
    for index, character in enumerate(text):
        size = 2 if ord(character) > 0xFFFF else 1
        if units + size > 4096:
            yield text[start:index]
            start, units = index, 0
        units += size
    yield text[start:]


class OwnerTelegram:
    def __init__(self, token, chat_id, client):
        if not token or token.startswith("replace_"):
            raise ValueError("Set TELEGRAM_BOT_TOKEN locally before starting the server.")
        try:
            self.chat_id = int(chat_id)
        except (TypeError, ValueError):
            raise ValueError("Set TELEGRAM_CHAT_ID to your numeric private chat ID.") from None
        if self.chat_id <= 0:
            raise ValueError("Use your own positive private chat ID, not a group or channel.")
        self._base_url = "https://api.telegram.org/bot" + token
        self._client = client
        self.offset = 0
        self._poll_lock = asyncio.Lock()

    async def request(self, method, payload):
        try:
            response = await self._client.post(self._base_url + "/" + method, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            hint = {
                401: "Check the bot token locally in .env.",
                403: "Open the bot, tap Start, and check the configured private chat ID.",
                409: "Stop other pollers or remove the bot webhook, then retry.",
                429: "Wait for Telegram's rate limit to clear before retrying.",
            }.get(status, "Check the bot settings and retry.")
            raise RuntimeError(f"Telegram HTTP {status}. {hint}") from None
        except (httpx.RequestError, ValueError):
            raise RuntimeError("Telegram could not be reached or returned invalid JSON. Check your connection and retry.") from None
        if not isinstance(data, dict) or not data.get("ok"):
            raise RuntimeError("Telegram rejected the request. Check the local token and chat ID, then retry.")
        return data["result"]

    async def skip_backlog(self):
        # Telegram forgets earlier updates with a negative offset. The last old
        # update is skipped as well; the next poll acknowledges it with +1.
        updates = await self.request("getUpdates", {"offset": -1, "limit": 1, "timeout": 0, "allowed_updates": ["message"]})
        for update in updates:
            self.offset = max(self.offset, update["update_id"] + 1)

    async def send(self, text):
        message_ids = []
        for part in message_parts(text):
            message = await self.request("sendMessage", {"chat_id": self.chat_id, "text": part})
            message_ids.append(message["message_id"])
        return {"status": "sent", "parts": len(message_ids), "message_ids": message_ids}

    async def wait(self, seconds=30):
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0:
            raise ValueError("seconds must be a nonnegative integer; use 30 for normal polling.")
        async with self._poll_lock:
            updates = await self.request("getUpdates", {"offset": self.offset, "timeout": min(seconds, 50), "allowed_updates": ["message"]})
            messages = []
            for update in updates:
                update_id = update["update_id"]
                if update_id < self.offset:
                    continue
                self.offset = update_id + 1  # Advance for rejected updates too.
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                sender = message.get("from") or {}
                if chat.get("id") != self.chat_id or chat.get("type") != "private" or sender.get("is_bot"):
                    LOG.warning("Dropped update outside the configured private owner chat.")
                    continue
                if isinstance(message.get("text"), str):
                    messages.append({
                        "update_id": update_id,
                        "message_id": message["message_id"],
                        "reply_to_message_id": (message.get("reply_to_message") or {}).get("message_id"),
                        "text": message["text"],
                        "date_utc": datetime.fromtimestamp(message["date"], timezone.utc).isoformat(),
                    })
            return {"messages": messages, "status": "received" if messages else "No new messages."}


@asynccontextmanager
async def lifespan(server):
    # Longer than the maximum Telegram long poll, with finite connect time.
    async with httpx.AsyncClient(timeout=httpx.Timeout(65, connect=10)) as client:
        telegram = OwnerTelegram(os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"), client)
        await telegram.skip_backlog()
        yield {"telegram": telegram}


mcp = MCPServer("jasmine0010-telegram", lifespan=lifespan)


@mcp.tool()
async def send_message(text: str, ctx: Context) -> dict:
    """Send a plain-text message to the configured owner's private Telegram chat.

    Use for a short answer or progress update, e.g. text='The calculation is complete.'
    Long replies are split into messages of at most 4096 UTF-16 units.
    The destination is fixed by TELEGRAM_CHAT_ID; no other recipient is accepted.
    Never include tokens, credentials, private files, or sensitive research data.
    """
    return await ctx.request_context.lifespan_context["telegram"].send(text)


@mcp.tool()
async def wait_for_messages(ctx: Context, seconds: int = 30) -> dict:
    """Wait for new text from the configured owner's private Telegram chat.

    seconds is an integer duration in seconds (default 30, capped at 50).
    Example: seconds=30. Return short message records with UTC timestamps,
    or status='No new messages.'. Other chats and startup backlog are dropped.
    Only one process may poll a bot. In phone mode the harness owns this tool;
    the model must not call it or it could consume an approval reply.
    """
    return await ctx.request_context.lifespan_context["telegram"].wait(seconds)


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    mcp.run(transport="stdio")
