# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0"]
# ///
"""Check the real stdio transport; loads credentials only from environment."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil

from mcp import Client, StdioServerParameters


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Send one fixed connection test to the owner.")
    args = parser.parse_args()
    env = {key: os.environ[key] for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    params = StdioServerParameters(
        command=shutil.which("uv") or str(Path.home() / ".local/bin/uv.exe"),
        args=["run", "--script", str(Path(__file__).resolve().parents[1] / "server.py")],
        env=env,
    )
    async with Client(params) as client:
        tools = (await client.list_tools()).tools
        print(json.dumps({"tools": [tool.name for tool in tools]}))
        result = await client.call_tool("wait_for_messages", {"seconds": 0})
        if result.is_error:
            raise RuntimeError("Polling tool failed the stdio smoke test.")
        print("Real stdio polling call succeeded.")
        if args.send:
            result = await client.call_tool("send_message", {"text": "Hello Jasmine! Your Telegram MCP server passed its SDK connection test."})
            if result.is_error:
                raise RuntimeError("Sending tool failed the stdio smoke test.")
            print("Fixed connection-test message sent to the configured owner.")


if __name__ == "__main__":
    asyncio.run(main())
