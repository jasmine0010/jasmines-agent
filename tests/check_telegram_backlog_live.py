# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0", "httpx>=0.28,<0.29"]
# ///
"""Verify a real pre-start marker is skipped and a fresh marker is delivered."""
import asyncio
import json
import os
import time

import httpx
from check_telegram_owner_live import ROOT, server


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(65, connect=10)) as client:
        bot = server.OwnerTelegram(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"], client)
        original = bot.request
        saw_backlog = False

        async def observe(method, payload):
            nonlocal saw_backlog
            result = await original(method, payload)
            if method == "getUpdates" and payload.get("offset") == -1:
                saw_backlog = any((item.get("message") or {}).get("text", "").strip() == "BACKLOG CHECK" for item in result)
            return result

        bot.request = observe
        await bot.skip_backlog()
        if not saw_backlog:
            raise RuntimeError("Startup did not observe the expected old marker; check is inconclusive.")
        first = await bot.wait(0)
        if any(item["text"].strip() == "BACKLOG CHECK" for item in first["messages"]):
            raise RuntimeError("Old marker was replayed; backlog check failed.")
        print("PASS: startup saw and skipped the pre-start BACKLOG CHECK message.", flush=True)
        await bot.send("Backlog was correctly skipped. Now send FRESH CHECK to confirm new messages still arrive. This test does not call the model or execute commands.")
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            result = await bot.wait(30)
            if any(item["text"].strip() == "FRESH CHECK" for item in result["messages"]):
                duplicate = await bot.wait(0)
                if any(item["text"].strip() == "FRESH CHECK" for item in duplicate["messages"]):
                    raise RuntimeError("Fresh marker was returned twice; check failed.")
                receipt = {"old_marker_observed_at_startup": True, "old_marker_replayed": False,
                           "fresh_marker_received_once": True, "model_requests": 0}
                (ROOT / "validation/week-3-backlog.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                await bot.send("Restart check passed: the old message was skipped and the fresh message arrived once. Tests are finished. The agent will stay stopped until the free model quota is available.")
                print("PASS: fresh owner message arrived once; no model or command was run.", flush=True)
                return
        raise RuntimeError("Fresh-marker check timed out; it remains pending.")


if __name__ == "__main__":
    asyncio.run(main())
