#!/usr/bin/env python3
"""
Komilion signup automation script.

Features:
- Randomly generates name, email, and password
- Sends POST request to https://www.komilion.com/api/signup
- Prints request and response details
"""

import json
import random
import secrets
import string
import time

import names
import requests


SIGNUP_PAGE_URL = "https://www.komilion.com/auth/signup"
SIGNUP_API_URL = "https://www.komilion.com/api/signup"
PASSWORD_CHARS = string.ascii_letters + string.digits + "!@#$%^&*_-+="


def random_name() -> str:
    return names.get_full_name()


def random_email(full_name: str) -> str:
    local = full_name.lower().replace(" ", ".")
    return f"{local}.{int(time.time())}{random.randint(1000, 9999)}@outlook.com"


def random_password(length: int = 16) -> str:
    if length < 12:
        raise ValueError("Password length must be at least 12")
    required = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*_-+="),
    ]
    password = required + [secrets.choice(PASSWORD_CHARS) for _ in range(length - len(required))]
    random.shuffle(password)
    return "".join(password)


def build_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.komilion.com",
        "Referer": SIGNUP_PAGE_URL,
    }


def signup() -> dict:
    credentials = {
        "name": random_name(),
        "password": random_password(),
    }
    credentials["email"] = random_email(credentials["name"])
    payload = {**credentials, "acceptTerms": True}

    response = requests.post(
        SIGNUP_API_URL,
        headers=build_headers(),
        json=payload,
        timeout=30,
    )

    try:
        response_body = response.json()
    except ValueError:
        response_body = response.text

    return {
        "generated_credentials": credentials,
        "request": {
            "url": SIGNUP_API_URL,
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
    result = signup()

    print("=== Generated Credentials ===")
    print(json.dumps(result["generated_credentials"], ensure_ascii=False, indent=2))

    print("\n=== Request ===")
    print(json.dumps(
        {
            "url": result["request"]["url"],
            "method": result["request"]["method"],
            "headers": result["request"]["headers"],
            "body": result["request"]["body"],
        },
        ensure_ascii=False,
        indent=2,
    ))

    print("\n=== Response ===")
    print(json.dumps(
        {
            "status_code": result["response"]["status_code"],
            "headers": result["response"]["headers"],
            "body": result["response"]["body"],
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()