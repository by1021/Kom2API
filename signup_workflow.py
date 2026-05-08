#!/usr/bin/env python3
"""
End-to-end Komilion signup workflow.

Flow:
1. Create a random mailbox from mail.ziiys.com
2. Generate signup name and password
3. Use the created mailbox email for Komilion signup
4. Save account information to a local JSONL file
5. Poll latest mailbox message every 3 seconds, up to 3 attempts
"""

from __future__ import annotations

import json
import os
import random
import re
import secrets
import string
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import names
import requests


MAILBOX_API_URL = "https://mail.ziiys.com/api/mailboxes"
MAILBOX_API_BASE_URL = "https://mail.ziiys.com/api/mailboxes"
SIGNUP_PAGE_URL = "https://www.komilion.com/auth/signup"
SIGNUP_API_URL = "https://www.komilion.com/api/signup"
ENV_FILE = Path(".env")
OUTPUT_FILE = Path("accounts.jsonl")
PASSWORD_CHARS = string.ascii_letters + string.digits + "!@#$%^&*_-+="
MAIL_POLL_INTERVAL_SECONDS = 3
MAIL_POLL_MAX_RETRIES = 5
REQUEST_TIMEOUT = 30
VERIFY_EMAIL_URL_HINT = "/api/auth/verify-email?token="
URL_PATTERN = r"https?://[^\s\"'<>]+"
DEBUG_ENV_NAME = "SIGNUP_WORKFLOW_DEBUG"


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


def parse_json_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def is_debug_enabled() -> bool:
    return os.getenv(DEBUG_ENV_NAME, "").strip().lower() in {"1", "true", "yes", "on"}


def format_duration(seconds: float) -> str:
    return f"{seconds:.3f}s"


def print_step(title: str, started_at: float, extra: str | None = None) -> None:
    now_text = utc_now_iso().replace("T", " ")
    message = f"[{now_text}] {title} | 当前运行时间: {format_duration(time.perf_counter() - started_at)}"
    if extra:
        message = f"{message} | {extra}"
    print(message)


def print_debug_block(title: str, payload: Any) -> None:
    if not is_debug_enabled():
        return

    print(f"\n=== DEBUG: {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def extract_message_text(message_body: Any) -> str:
    if isinstance(message_body, str):
        return message_body

    if isinstance(message_body, dict):
        preferred_keys = (
            "text",
            "body",
            "message",
            "content",
            "html",
            "plain",
            "plain_text",
            "plainText",
        )
        collected_parts: list[str] = []

        for key in preferred_keys:
            value = message_body.get(key)
            if isinstance(value, str) and value.strip():
                collected_parts.append(value)

        for nested_value in message_body.values():
            nested_text = extract_message_text(nested_value)
            if nested_text.strip():
                collected_parts.append(nested_text)

        unique_parts: list[str] = []
        seen_parts: set[str] = set()
        for part in collected_parts:
            normalized_part = part.strip()
            if normalized_part and normalized_part not in seen_parts:
                seen_parts.add(normalized_part)
                unique_parts.append(normalized_part)

        return "\n".join(unique_parts)

    if isinstance(message_body, list):
        parts = [extract_message_text(item) for item in message_body]
        return "\n".join(part for part in parts if part)

    return ""


def extract_verify_email_url(message_body: Any) -> str | None:
    message_text = extract_message_text(message_body)
    normalized_text = (
        message_text.replace("\\/", "/")
        .replace("&", "&")
        .replace("\r", "\n")
    )

    url_candidates = re.findall(URL_PATTERN, normalized_text, re.IGNORECASE)
    for candidate in url_candidates:
        cleaned_candidate = candidate.rstrip('"\'>.,;)')
        if VERIFY_EMAIL_URL_HINT in cleaned_candidate:
            return cleaned_candidate

    return None


def build_mailbox_headers(token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def build_latest_message_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }


def build_signup_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.komilion.com",
        "Referer": SIGNUP_PAGE_URL,
    }


def random_name() -> str:
    return names.get_full_name()


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


def build_latest_message_url(email: str) -> str:
    return f"{MAILBOX_API_BASE_URL}/{quote(email, safe='')}/latest-message"


def _search_email(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("email", "address", "mailbox", "username"):
            candidate = value.get(key)
            if isinstance(candidate, str) and "@" in candidate:
                return candidate

        local_part = value.get("local_part") or value.get("localPart") or value.get("name")
        domain = value.get("domain")
        if isinstance(local_part, str) and isinstance(domain, str) and local_part and domain:
            return f"{local_part}@{domain}"

        for nested_value in value.values():
            result = _search_email(nested_value)
            if result:
                return result

    if isinstance(value, list):
        for item in value:
            result = _search_email(item)
            if result:
                return result

    return None


def extract_mailbox_email(mailbox_response_body: Any) -> str:
    email = _search_email(mailbox_response_body)
    if not email:
        raise ValueError("Unable to extract mailbox email from mailbox API response")
    return email


def create_mailbox() -> dict[str, Any]:
    token = get_required_env("MAIL_ZIIYS_TOKEN")
    domain = get_required_env("MAIL_ZIIYS_DOMAIN")

    payload = {
        "domain": domain,
        "random": True,
    }

    response = requests.post(
        MAILBOX_API_URL,
        headers=build_mailbox_headers(token),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response_body = parse_json_response(response)
    response.raise_for_status()

    mailbox_email = extract_mailbox_email(response_body)

    return {
        "mailbox_email": mailbox_email,
        "request": {
            "url": MAILBOX_API_URL,
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


def build_summary(account_record: dict[str, Any], workflow_started_at: float) -> dict[str, Any]:
    latest_message = account_record["latest_message_poll"].get("latest_message")
    latest_message_body = None
    if isinstance(latest_message, dict):
        latest_message_body = latest_message.get("response", {}).get("body")

    verify_email_url = extract_verify_email_url(latest_message_body)

    return {
        "created_at": account_record["created_at"],
        "execution_time_seconds": round(time.perf_counter() - workflow_started_at, 2),
        "mailbox_email": account_record["credentials"]["email"],
        "name": account_record["credentials"]["name"],
        "password": account_record["credentials"]["password"],
        "signup_status_code": account_record["signup"]["response"]["status_code"],
        "mail_poll_success": account_record["latest_message_poll"]["success"],
        "mail_poll_attempt_count": len(account_record["latest_message_poll"]["attempts"]),
        "verify_email_url": verify_email_url,
    }


def signup(credentials: dict[str, str]) -> dict[str, Any]:
    payload = {
        "name": credentials["name"],
        "email": credentials["email"],
        "password": credentials["password"],
        "acceptTerms": True,
    }

    response = requests.post(
        SIGNUP_API_URL,
        headers=build_signup_headers(),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    response_body = parse_json_response(response)

    return {
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


def get_latest_message(email: str) -> dict[str, Any]:
    token = get_required_env("MAIL_ZIIYS_TOKEN")
    url = build_latest_message_url(email)

    response = requests.get(
        url,
        headers=build_latest_message_headers(token),
        timeout=REQUEST_TIMEOUT,
    )
    response_body = parse_json_response(response)

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


def poll_latest_message(
    email: str,
    retries: int = MAIL_POLL_MAX_RETRIES,
    interval_seconds: int = MAIL_POLL_INTERVAL_SECONDS,
    workflow_started_at: float | None = None,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []

    for attempt in range(1, retries + 1):
        if workflow_started_at is not None:
            print_step(
                "获取邮箱最新邮件",
                workflow_started_at,
                extra=f"第 {attempt}/{retries} 次尝试，轮询间隔 {interval_seconds}s",
            )

        latest_message_result = get_latest_message(email)
        status_code = latest_message_result["response"]["status_code"]
        response_body = latest_message_result["response"]["body"]
        verify_email_url = extract_verify_email_url(response_body)

        attempts.append(
            {
                "attempt": attempt,
                "timestamp": utc_now_iso(),
                "status_code": status_code,
                "response_body": response_body,
                "verify_email_url": verify_email_url,
            }
        )

        print_debug_block(f"latest_message_attempt_{attempt}", latest_message_result)

        if status_code < 400 and response_body not in (None, "", [], {}):
            return {
                "success": True,
                "attempts": attempts,
                "latest_message": latest_message_result,
                "verify_email_url": verify_email_url,
            }

        if attempt < retries:
            time.sleep(interval_seconds)

    latest_message_result = get_latest_message(email)

    return {
        "success": False,
        "attempts": attempts,
        "latest_message": latest_message_result,
        "verify_email_url": extract_verify_email_url(latest_message_result["response"]["body"]),
    }


def build_credentials(mailbox_email: str) -> dict[str, str]:
    return {
        "name": random_name(),
        "email": mailbox_email,
        "password": random_password(),
    }


def build_output_record(account_record: dict[str, Any]) -> dict[str, str | None]:
    summary = account_record["summary"]
    return {
        "email": summary["mailbox_email"],
        "password": summary["password"],
        "url": summary["verify_email_url"],
    }


def append_account_record(record: dict[str, str | None], path: Path = OUTPUT_FILE) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_workflow() -> dict[str, Any]:
    workflow_started_at = time.perf_counter()
    load_dotenv(ENV_FILE)

    print_step("创建邮箱", workflow_started_at)
    mailbox_result = create_mailbox()
    print(f"  邮箱: {mailbox_result['mailbox_email']}")
    print_debug_block("create_mailbox", mailbox_result)

    print_step("生成注册资料", workflow_started_at)
    credentials = build_credentials(mailbox_result["mailbox_email"])
    print(f"  Name: {credentials['name']}")
    print(f"  Email: {credentials['email']}")
    print(f"  Password: {credentials['password']}")

    print_step("执行注册请求", workflow_started_at)
    signup_result = signup(credentials)
    print(f"  注册响应状态: {signup_result['response']['status_code']}")
    print_debug_block("signup", signup_result)

    latest_message_poll = poll_latest_message(credentials["email"], workflow_started_at=workflow_started_at)

    account_record = {
        "created_at": utc_now_iso(),
        "credentials": credentials,
        "mailbox": {
            "email": mailbox_result["mailbox_email"],
            "create_request": mailbox_result["request"],
            "create_response": mailbox_result["response"],
        },
        "signup": signup_result,
        "latest_message_poll": latest_message_poll,
    }

    summary = build_summary(account_record, workflow_started_at)
    account_record["summary"] = summary

    output_record = build_output_record(account_record)

    print_step("写入账号信息文件", workflow_started_at, extra=f"输出文件: {OUTPUT_FILE}")
    append_account_record(output_record)

    return account_record


def main() -> None:
    result = run_workflow()
    summary = result["summary"]

    print("\n=== 执行摘要 ===")
    print(f"创建时间: {summary['created_at']}")
    print(f"执行耗时: {summary['execution_time_seconds']}s")
    print(f"邮箱: {summary['mailbox_email']}")
    print(f"姓名: {summary['name']}")
    print(f"密码: {summary['password']}")
    print(f"注册状态码: {summary['signup_status_code']}")
    print(f"取信成功: {summary['mail_poll_success']}")
    print(f"取信尝试次数: {summary['mail_poll_attempt_count']}")
    print(f"验证链接: {summary['verify_email_url'] or '未提取到'}")

    if is_debug_enabled():
        print("\n=== DEBUG: full_result ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()