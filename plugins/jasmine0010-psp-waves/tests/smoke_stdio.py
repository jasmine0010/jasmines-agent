# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.3.0"]
# ///
"""Exercise public-data calculations through an independent stdio client."""

import asyncio
import json
import os
from pathlib import Path
import shutil

from mcp import Client, StdioServerParameters


async def main():
    params = StdioServerParameters(
        command=shutil.which("uv") or str(Path.home() / ".local/bin/uv.exe"),
        args=["run", "--script", str(Path(__file__).resolve().parents[1] / "server.py")],
        env={"UV_PYTHON": os.environ.get("PSP_PYTHON", "3.13")},
    )
    async with Client(params) as client:
        tools = (await client.list_tools()).tools
        print(json.dumps({"tools": [tool.name for tool in tools]}))
        result = await client.call_tool("compare_psp_wave_intervals", {})
        if result.is_error:
            raise RuntimeError("PSP comparison failed over stdio.")
        for content in result.content:
            if content.type == "text":
                print(content.text)


if __name__ == "__main__":
    asyncio.run(main())
