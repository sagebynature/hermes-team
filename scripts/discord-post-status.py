#!/usr/bin/env python3
"""Post compact Team Nexus status updates to Discord webhooks.

The script intentionally never prints webhook URLs. Use --dry-run for safe tests.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

MAX_MESSAGE_CHARS = 1800
MAX_EMBED_DESCRIPTION_CHARS = 4096


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post a Team Nexus status update to Discord")
    parser.add_argument("--message", help="Plain message to send. Defaults to stdin when --payload-json is omitted.")
    parser.add_argument("--payload-json", help="Complete Discord webhook JSON payload. Defaults to stdin when set to '-'.")
    parser.add_argument("--channel", choices=("status", "handoffs"), default="status")
    parser.add_argument("--thread-id", help="Discord thread/forum post ID to deliver into via webhook thread_id query parameter")
    parser.add_argument("--dry-run", action="store_true", help="Print payload instead of posting")
    return parser.parse_args()


def read_message(args: argparse.Namespace) -> str:
    message = args.message if args.message is not None else sys.stdin.read()
    message = message.strip()
    if not message:
        raise SystemExit("message is required via --message or stdin")
    if len(message) > MAX_MESSAGE_CHARS:
        raise SystemExit(f"message too long: {len(message)} chars > {MAX_MESSAGE_CHARS}")
    return message


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["allowed_mentions"] = {"parse": []}
    if "content" in payload and payload["content"] is not None:
        payload["content"] = str(payload["content"])
        if len(payload["content"]) > MAX_MESSAGE_CHARS:
            raise SystemExit(f"payload content too long: {len(payload['content'])} chars > {MAX_MESSAGE_CHARS}")
    embeds = payload.get("embeds")
    if embeds is not None:
        if not isinstance(embeds, list):
            raise SystemExit("payload embeds must be a list")
        for embed in embeds:
            if not isinstance(embed, dict):
                raise SystemExit("payload embed entries must be objects")
            description = embed.get("description")
            if description is not None and len(str(description)) > MAX_EMBED_DESCRIPTION_CHARS:
                embed["description"] = str(description)[: MAX_EMBED_DESCRIPTION_CHARS - 1] + "…"
    return payload


def read_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_json is not None:
        raw = sys.stdin.read() if args.payload_json == "-" else args.payload_json
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid --payload-json: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SystemExit("--payload-json must decode to a JSON object")
        return sanitize_payload(parsed)
    message = read_message(args)
    return sanitize_payload({"content": message})


def webhook_env(channel: str) -> str:
    return "DISCORD_HANDOFFS_WEBHOOK_URL" if channel == "handoffs" else "DISCORD_STATUS_WEBHOOK_URL"


def webhook_url_with_thread(webhook_url: str, thread_id: str | None) -> str:
    if not thread_id:
        return webhook_url
    parts = urllib.parse.urlsplit(webhook_url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "thread_id"]
    query.append(("thread_id", thread_id))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def main() -> int:
    args = parse_args()
    payload = read_payload(args)
    env_name = webhook_env(args.channel)
    webhook_url = os.environ.get(env_name, "").strip()

    if args.dry_run:
        print(json.dumps({"env": env_name, "thread_id": args.thread_id, "payload": payload}, indent=2))
        return 0

    if not webhook_url:
        raise SystemExit(f"{env_name} is required unless --dry-run is used")

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url_with_thread(webhook_url, args.thread_id),
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "team-nexus-discord-status/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status not in (200, 204):
                raise SystemExit(f"Discord webhook returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Discord webhook returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Discord webhook request failed: {exc.reason}") from exc

    print(f"posted Discord {args.channel} update")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
