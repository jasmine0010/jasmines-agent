"""Agent type validation must fail before an unknown tool can be offered."""

from pathlib import Path
import tempfile
import unittest

from agent_types import AgentTypeError, load_agent_types, type_prompt
from plugin_runtime import PluginRuntime

TOOLS = [{"type": "function", "function": {"name": name}} for name in ("bash", "email__check_inbox", "email__read_message", "delegate", "subagent")]


class AgentTypeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "agents").mkdir()

    def write(self, fields="tools: email__check_inbox, email__read_message\n", body="PRIVATE_CHILD_PROMPT"):
        path = self.root / "agents/reader.md"
        path.write_text("---\nname: reader\ndescription: Read mail\n" + fields + "---\n" + body, encoding="utf-8")
        return path

    def test_comma_tools_and_metadata_without_prompt_body(self):
        self.write()
        types = load_agent_types(self.root, TOOLS)
        self.assertEqual(types["reader"].tools, ("email__check_inbox", "email__read_message"))
        self.assertEqual(types["reader"].max_turns, 20)
        self.assertIn("reader: Read mail", type_prompt(types))
        self.assertNotIn("PRIVATE_CHILD_PROMPT", type_prompt(types))

    def test_yaml_list_model_and_max_turns(self):
        self.write("tools:\n  - email__read_message\nmodel: synthetic-model\nmax_turns: 3\n")
        kind = load_agent_types(self.root, TOOLS)["reader"]
        self.assertEqual(kind.tools, ("email__read_message",))
        self.assertEqual((kind.model, kind.max_turns), ("synthetic-model", 3))

    def test_missing_tools_means_all_except_agent_controls(self):
        self.write("")
        kind = load_agent_types(self.root, TOOLS)["reader"]
        self.assertEqual(set(kind.tools), {"bash", "email__check_inbox", "email__read_message"})

    def test_explicit_empty_list_has_no_tools(self):
        self.write("tools: []\n")
        self.assertEqual(load_agent_types(self.root, TOOLS)["reader"].tools, ())

    def test_controls_are_removed_even_if_requested(self):
        self.write("tools: delegate, subagent, email__read_message\n")
        self.assertEqual(load_agent_types(self.root, TOOLS)["reader"].tools, ("email__read_message",))

    def test_unknown_name_reports_file_and_tool(self):
        self.write("tools: missing__tool\n")
        with self.assertRaisesRegex(AgentTypeError, "reader.md: unknown tool missing__tool"):
            load_agent_types(self.root, TOOLS)

    def test_unknown_tool_also_fails_runtime_startup(self):
        self.write("tools: missing__tool\n")
        with self.assertRaisesRegex(AgentTypeError, "reader.md: unknown tool missing__tool"):
            with PluginRuntime(self.root):
                self.fail("Runtime started with an unknown tool")

    def test_invalid_limits_and_null_tools_fail_closed(self):
        for field in ("tools: null\n", "tools: []\nmax_turns: true\n", "tools: []\nmax_turns: 0\n", "tools: []\nmax_turns: 101\n"):
            with self.subTest(field=field):
                self.write(field)
                with self.assertRaises(AgentTypeError):
                    load_agent_types(self.root, TOOLS)

    def test_duplicate_type_names_are_rejected(self):
        first = self.write()
        (self.root / "agents/duplicate.md").write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaisesRegex(AgentTypeError, "duplicated"):
            load_agent_types(self.root, TOOLS)


if __name__ == "__main__":
    unittest.main()
