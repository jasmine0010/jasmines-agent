"""Independent MCP stdio client. Does not log into Gmail or send mail."""

import asyncio
import json
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters


async def main():
    server = Path(__file__).resolve().parents[1] / "server.py"
    params = StdioServerParameters(command=sys.executable, args=[str(server)],
                                  env={"EMAIL_ADDRESS": "", "EMAIL_APP_PASSWORD": "", "EMAIL_ALLOWED_RECIPIENTS": ""})
    async with Client(params) as client:
        result = await client.list_tools()
        names = sorted(tool.name for tool in result.tools)
        assert names == ["check_inbox", "read_message", "send_message"], names
        rejected = await client.call_tool("read_message", {"id": "1:*"})
        text = "\n".join(item.text for item in rejected.content if item.type == "text")
        assert "positive IMAP UID" in text, text
        missing = await client.call_tool("check_inbox", {})
        text = "\n".join(item.text for item in missing.content if item.type == "text")
        assert "Set EMAIL_ADDRESS" in text, text
    print(json.dumps({"status": "passed", "tools": names,
                      "checks": ["initialize", "list_tools", "reject_uid_injection", "missing_credentials"]}))


if __name__ == "__main__":
    async def bounded_check():
        async with asyncio.timeout(30):
            await main()
    asyncio.run(bounded_check())
