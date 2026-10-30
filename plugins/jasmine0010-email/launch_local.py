"""Launch stdio MCP with only email settings loaded from a private .env file.

Unlike a generic dotenv runner, this never echoes a malformed credential line.
Pass paths, never secret values, on the command line.
"""

import argparse
import os
from pathlib import Path
import sys


def email_settings(source):
    keys = {"EMAIL_ADDRESS", "EMAIL_APP_PASSWORD", "EMAIL_ALLOWED_RECIPIENTS"}
    result = {}
    for line in source.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() in keys:
            value = value.strip()
            if len(value) > 1 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            result[key.strip()] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--self-test-only", action="store_true")
    args = parser.parse_args()
    try:
        settings = email_settings(args.env_file.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError):
        raise SystemExit("Cannot read the local email configuration; values were not displayed.") from None
    for name in ("EMAIL_ADDRESS", "EMAIL_APP_PASSWORD", "EMAIL_ALLOWED_RECIPIENTS"):
        os.environ[name] = settings.get(name, "")
    import server
    try:
        address, _, _ = server.configuration()
    except server.MailError:
        raise SystemExit("Email settings are incomplete or invalid. Check them locally; values were not displayed.") from None
    if args.self_test_only:
        # The second-agent test cannot send to the class or any third party.
        os.environ["EMAIL_ALLOWED_RECIPIENTS"] = address
        original_send = server._send_message
        attempted = False

        def send_once(to, subject, body):
            nonlocal attempted
            if attempted:
                raise server.MailError("The self-mail test already attempted one send. Check the inbox; do not resend.")
            attempted = True
            return original_send(to, subject, body)

        server._send_message = send_once
    server.mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
