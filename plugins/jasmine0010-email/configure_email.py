"""Enter a new Gmail app password locally without exposing it in chat or argv."""

import argparse
from getpass import getpass, GetPassWarning
import os
from pathlib import Path
import re
import sys
import tempfile
import warnings


def normalize_password(value):
    password = value.replace(" ", "")
    if not re.fullmatch(r"[A-Za-z]{16}", password):
        raise ValueError("Enter the 16-letter password generated on Google's App passwords page.")
    return password


def existing_address(source):
    matches = re.findall(r"(?m)^\s*(?:export\s+)?EMAIL_ADDRESS\s*=\s*(.*?)\s*$", source)
    value = matches[-1].strip().strip("\"'") if matches else ""
    return value if valid_address(value) else ""


def valid_address(value):
    return bool(re.fullmatch(r"[A-Za-z0-9.+_-]+@gmail\.com", value)) and not value.startswith("replace_")


def updated_environment(source, address, password):
    if not valid_address(address):
        raise ValueError("Use the dedicated agent's bare Gmail address.")
    password = normalize_password(password)
    address = address.lower()
    values = {"EMAIL_ADDRESS": address, "EMAIL_APP_PASSWORD": password,
              "EMAIL_ALLOWED_RECIPIENTS": "lingtai2026@gmail.com," + address}
    output, written = [], set()
    for line in source.splitlines():
        match = re.match(r"^\s*(?:export\s+)?(EMAIL_ADDRESS|EMAIL_APP_PASSWORD|EMAIL_ALLOWED_RECIPIENTS)\s*=", line)
        if match:
            key = match.group(1)
            if key not in written:
                output.append(key + '="' + values[key] + '"')
                written.add(key)
        elif re.fullmatch(r"(?:[A-Za-z]{4}[ ]*){4}", line.strip()):
            # Remove an orphaned app-password line without echoing it.
            continue
        else:
            output.append(line)
    for key, value in values.items():
        if key not in written:
            output.append(key + '="' + value + '"')
    return "\n".join(output) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).resolve().parent / ".env")
    args = parser.parse_args()
    path = args.env_file.resolve()
    source = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    default = existing_address(source)
    print("Create an app password for the dedicated agent account at https://myaccount.google.com/apppasswords.")
    address = input("Dedicated agent Gmail address" + (" [" + default + "]" if default else "") + ": ").strip() or default
    if not valid_address(address):
        raise ValueError("Enter the dedicated agent's Gmail address; no settings were changed.")
    # Refuse a non-masking fallback rather than echo a credential in a terminal.
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        password = normalize_password(getpass("New app password (hidden; paste is supported): "))
        confirmation = normalize_password(getpass("Repeat new app password (hidden): "))
    if password != confirmation:
        raise ValueError("The entries did not match; no settings were changed.")
    updated = updated_environment(source, address, password)
    # Replace atomically. Do not create a backup containing the old credential.
    fd, temporary = tempfile.mkstemp(prefix=".email-config-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(updated)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Saved email settings without displaying the password.")
    print("Recipients are limited to this agent account and the class agent.")
    print("Return to the homework chat and say done. No email was sent.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError, GetPassWarning):
        print("Secure entry cancelled or unavailable. No settings were changed.", file=sys.stderr)
        sys.exit(1)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except OSError:
        print("Could not update the local .env file. Check its path and write permissions.", file=sys.stderr)
        sys.exit(1)
