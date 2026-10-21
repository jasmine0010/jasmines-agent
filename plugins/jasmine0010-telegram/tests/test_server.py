import importlib.util
from pathlib import Path
import unittest

import httpx
from mcp import Client

spec = importlib.util.spec_from_file_location("telegram_server", Path(__file__).resolve().parents[1] / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def update(number, chat_id=42, text="hello", chat_type="private"):
    return {"update_id": number, "message": {"message_id": number, "chat": {"id": chat_id, "type": chat_type}, "from": {"is_bot": False}, "text": text, "date": 1_700_000_000}}


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    async def test_foreign_chat_dropped_and_offset_advanced(self):
        batches = [[update(1, 99, "malicious command"), update(2), update(3, 99)], []]
        payloads = []

        def handler(request):
            import json
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": batches.pop(0)})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            bot = server.OwnerTelegram("synthetic-token", "42", client)
            with self.assertLogs("owner_telegram", level="WARNING") as logs:
                result = await bot.wait()
            self.assertEqual([m["text"] for m in result["messages"]], ["hello"])
            self.assertNotIn("malicious command", " ".join(logs.output))
            self.assertEqual(bot.offset, 4)
            self.assertEqual((await bot.wait())["messages"], [])
            self.assertEqual(payloads[-1]["offset"], 4)

    async def test_startup_skips_old_messages_and_accepts_fresh_once(self):
        batches = [[update(400, text="old command")], [update(400, text="old command"), update(401, text="fresh")]]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True, "result": batches.pop(0)}))) as client:
            bot = server.OwnerTelegram("synthetic-token", "42", client)
            await bot.skip_backlog()
            self.assertEqual(bot.offset, 401)
            result = await bot.wait()
            self.assertEqual([m["text"] for m in result["messages"]], ["fresh"])

    async def test_send_has_only_fixed_destination_and_splits_emoji(self):
        import json
        payloads = []
        def handler(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            bot = server.OwnerTelegram("synthetic-token", "42", client)
            text = "🌞" * 3000
            result = await bot.send(text)
        self.assertEqual(result["parts"], 2)
        self.assertEqual(result["message_ids"], [1, 1])
        self.assertEqual("".join(p["text"] for p in payloads), text)
        self.assertTrue(all(p["chat_id"] == 42 for p in payloads))
        self.assertTrue(all(len(p["text"].encode("utf-16-le")) // 2 <= 4096 for p in payloads))

    async def test_api_errors_cannot_include_token_or_url(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401))) as client:
            bot = server.OwnerTelegram("do-not-print-this-token", "42", client)
            with self.assertRaises(RuntimeError) as caught:
                await bot.send("hello")
            self.assertIn("401", str(caught.exception))
            self.assertNotIn("do-not-print-this-token", str(caught.exception))
            self.assertNotIn("https://", str(caught.exception))

    async def test_reply_target_is_preserved_for_bound_approvals(self):
        item = update(7, text="yes")
        item["message"]["reply_to_message"] = {"message_id": 123, "text": "do not forward original text"}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True, "result": [item]}))) as client:
            bot = server.OwnerTelegram("synthetic-token", "42", client)
            result = await bot.wait()
        self.assertEqual(result["messages"][0]["reply_to_message_id"], 123)
        self.assertNotIn("do not forward", str(result))

    async def test_polling_duration_capped_and_negative_rejected(self):
        import json
        payloads = []
        def handler(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": []})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            bot = server.OwnerTelegram("synthetic-token", "42", client)
            await bot.wait(500)
            self.assertEqual(payloads[0]["timeout"], 50)
            with self.assertRaises(ValueError):
                await bot.wait(-1)

    async def test_protocol_schemas_hide_context_and_recipient(self):
        # Replace the live lifespan: this check uses the real MCP protocol
        # without contacting Telegram or requiring a real token.
        from contextlib import asynccontextmanager
        from mcp.server import MCPServer
        @asynccontextmanager
        async def offline_lifespan(instance):
            yield {"telegram": None}
        instance = MCPServer("schema-check", lifespan=offline_lifespan)
        instance.tool()(server.send_message)
        instance.tool()(server.wait_for_messages)
        async with Client(instance) as client:
            tools = (await client.list_tools()).tools
        schemas = {tool.name: tool.input_schema for tool in tools}
        self.assertEqual(set(schemas["send_message"]["properties"]), {"text"})
        self.assertEqual(set(schemas["wait_for_messages"]["properties"]), {"seconds"})

    def test_missing_configuration_fails_closed(self):
        for token, chat in [("", "42"), ("synthetic-token", ""), ("synthetic-token", "-42")]:
            with self.assertRaises(ValueError):
                server.OwnerTelegram(token, chat, None)
        with self.assertRaises(ValueError):
            list(server.message_parts("  "))


if __name__ == "__main__":
    unittest.main()
