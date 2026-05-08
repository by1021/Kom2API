#!/usr/bin/env python3
"""
Get the latest message details for a mailbox via
https://mail.ziiys.com/api/mailboxes/{email}/latest-message.

Configuration is loaded from a local .env file:
- MAIL_ZIIYS_TOKEN
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests


API_BASE_URL = "https://mail.ziiys.com/api/mailboxes"
MAILBOX_EMAIL = "e570syhz6dnb@ziiy.eu.cc"
ENV_FILE = Path(".env")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing environment file: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def build_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }


def build_latest_message_url(email: str) -> str:
    return f"{API_BASE_URL}/{quote(email, safe='')}/latest-message"


def get_latest_message(email: str = MAILBOX_EMAIL) -> dict:
    load_dotenv(ENV_FILE)

    token = get_required_env("MAIL_ZIIYS_TOKEN")
    url = build_latest_message_url(email)

    response = requests.get(
        url,
        headers=build_headers(token),
        timeout=30,
    )

    try:
        response_body = response.json()
    except ValueError:
        response_body = response.text

    return {
        "request": {
            "url": url,
            "method": "GET",
            "headers": dict(response.request.headers),
            "body": None,
        },
        "response": {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response_body,
        },
    }


def resolve_mailbox_email() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1].strip()

    env_email = os.getenv("MAIL_ZIIYS_MAILBOX_EMAIL", "").strip()
    if env_email:
        return env_email

    return MAILBOX_EMAIL


def main() -> None:
    email = resolve_mailbox_email()
    result = get_latest_message(email)

    print("=== Request ===")
    print(json.dumps(result["request"], ensure_ascii=False, indent=2))

    print("\n=== Response ===")
    print(json.dumps(result["response"], ensure_ascii=False, indent=2))

    status_code = result["response"]["status_code"]
    if status_code >= 400:
        raise SystemExit(f"Request failed with status {status_code}")


if __name__ == "__main__":
    main()