# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0", "httpx>=0.28,<0.29"]
# ///
"""Live owner-filter check. Stop other bot hosts before running this script."""
import asyncio
import importlib.util
import json
import logging
import os
from pathlib import Path
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("telegram_server", ROOT / "plugins/jasmine0010-telegram/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


async def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    owner_id = int(os.environ["TELEGRAM_CHAT_ID"])
    async with httpx.AsyncClient(timeout=httpx.Timeout(65, connect=10)) as client:
        # Override only the receiver in this disposable instance. The .env
        # stays unchanged; nothing is sent to the deliberately wrong ID.
        receiver = server.OwnerTelegram(token, owner_id + 1, client)
        sender = server.OwnerTelegram(token, owner_id, client)
        await receiver.skip_backlog()
        seen_marker = False
        original = receiver.request

        async def observe(method, payload):
            nonlocal seen_marker
            result = await original(method, payload)
            for update in result if method == "getUpdates" else []:
                msg = update.get("message") or {}
                if msg.get("chat", {}).get("id") == owner_id and msg.get("text", "").strip() == "FOREIGN CHECK":
                    seen_marker = True
            return result

        receiver.request = observe
        await sender.send("Owner-filter test ready. Send FOREIGN CHECK now. The temporary receiver uses a wrong chat ID and should ignore it; no model or commands run in this test.")
        print("Ready for FOREIGN CHECK from the owner's phone.", flush=True)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            result = await receiver.wait(30)
            if result["messages"]:
                raise RuntimeError("Unexpected accepted message during wrong-ID test; check failed.")
            if seen_marker:
                receipt = {"live_owner_message_rejected_with_wrong_configured_id": True,
                           "accepted_messages": 0, "env_file_changed": False,
                           "model_requests": 0}
                (ROOT / "validation/week-3-owner-filter.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                print("PASS: actual owner message was dropped with the wrong receiver ID; .env is unchanged.", flush=True)
                await sender.send("Owner-filter check passed. The test receiver is stopping; the normal owner setting remains unchanged.")
                return
        raise RuntimeError("No test marker received before timeout; live check remains pending.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
