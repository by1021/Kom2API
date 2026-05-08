#!/usr/bin/env python3
"""
Create a random mailbox via https://mail.ziiys.com/api/mailboxes.

Configuration is loaded from a local .env file:
- MAIL_ZIIYS_TOKEN
- MAIL_ZIIYS_DOMAIN
"""

import json
import os
from pathlib import Path

import requests


API_URL = "https://mail.ziiys.com/api/mailboxes"
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
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def create_mailbox() -> dict:
    load_dotenv(ENV_FILE)

    token = get_required_env("MAIL_ZIIYS_TOKEN")
    domain = get_required_env("MAIL_ZIIYS_DOMAIN")

    payload = {
        "domain": domain,
        "random": True,
    }

    response = requests.post(
        API_URL,
        headers=build_headers(token),
        json=payload,
        timeout=30,
    )

    try:
        response_body = response.json()
    except ValueError:
        response_body = response.text

    response.raise_for_status()

    return {
        "request": {
            "url": API_URL,
            "method": "POST",
            "headers": dict(response.request.headers),
            "body": payload,
        },
        "response": {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response_body,
        },
    }


def main() -> None:
    result = create_mailbox()

    print("=== Request ===")
    print(json.dumps(result["request"], ensure_ascii=False, indent=2))

    print("\n=== Response ===")
    print(json.dumps(result["response"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()