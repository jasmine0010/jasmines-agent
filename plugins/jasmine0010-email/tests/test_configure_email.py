"""Synthetic-only checks for masked local setup and dotenv formatting."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configure_email import existing_address, normalize_password, updated_environment
from launch_local import email_settings


class ConfigurationTests(unittest.TestCase):
    def test_removes_display_spaces_and_quotes_value(self):
        result = updated_environment("MODEL=example\n", "test.agent@gmail.com", "abcd efgh ijkl mnop")
        self.assertIn('EMAIL_APP_PASSWORD="abcdefghijklmnop"\n', result)
        self.assertIn("MODEL=example\n", result)

    def test_preserves_unrelated_values_without_copying_password_lines(self):
        source = 'API_KEY="synthetic-only"\nEMAIL_APP_PASSWORD=bad format\nEMAIL_APP_PASSWORD=duplicate\n'
        result = updated_environment(source, "test.agent@gmail.com", "abcdefghijklmnop")
        self.assertIn('API_KEY="synthetic-only"', result)
        self.assertEqual(result.count("EMAIL_APP_PASSWORD="), 1)
        self.assertNotIn("bad format", result)

    def test_rejects_bad_password_without_including_its_value(self):
        with self.assertRaises(ValueError) as error:
            normalize_password("synthetic-invalid-value")
        self.assertNotIn("synthetic-invalid-value", str(error.exception))

    def test_extracts_only_valid_nonplaceholder_address(self):
        self.assertEqual(existing_address('EMAIL_ADDRESS="test.agent@gmail.com"\n'), "test.agent@gmail.com")
        self.assertEqual(existing_address("EMAIL_ADDRESS=replace_with_dedicated_agent@gmail.com\n"), "")

    def test_limits_recipients_to_self_and_class(self):
        result = updated_environment("EMAIL_ALLOWED_RECIPIENTS=other@example.org\n", "test.agent@gmail.com", "abcdefghijklmnop")
        self.assertIn('EMAIL_ALLOWED_RECIPIENTS="lingtai2026@gmail.com,test.agent@gmail.com"', result)
        self.assertNotIn("other@example.org", result)

    def test_launcher_loads_email_fields_only(self):
        fields = email_settings('API_KEY="synthetic-private"\nEMAIL_ADDRESS="test.agent@gmail.com"\nEMAIL_APP_PASSWORD=abcd efgh ijkl mnop\n')
        self.assertEqual(set(fields), {"EMAIL_ADDRESS", "EMAIL_APP_PASSWORD"})
        self.assertEqual(fields["EMAIL_APP_PASSWORD"], "abcd efgh ijkl mnop")

    def test_launcher_does_not_evaluate_shell_syntax(self):
        fields = email_settings('EMAIL_APP_PASSWORD="$(synthetic-command)"\n')
        self.assertEqual(fields["EMAIL_APP_PASSWORD"], "$(synthetic-command)")


if __name__ == "__main__":
    unittest.main()
