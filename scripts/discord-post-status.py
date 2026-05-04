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
import urllib.request

MAX_MESSAGE_CHARS = 1800


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Post a Team Nexus status update to Discord")
    parser.add_argument("--message", help="Message to send. Defaults to stdin.")
    parser.add_argument("--channel", choices=("status", "handoffs"), default="status")
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


def webhook_env(channel: str) -> str:
    return "DISCORD_HANDOFFS_WEBHOOK_URL" if channel == "handoffs" else "DISCORD_STATUS_WEBHOOK_URL"


def main() -> int:
    args = parse_args()
    message = read_message(args)
    env_name = webhook_env(args.channel)
    webhook_url = os.environ.get(env_name, "").strip()
    payload = {"content": message, "allowed_mentions": {"parse": []}}

    if args.dry_run:
        print(json.dumps({"env": env_name, "payload": payload}, indent=2))
        return 0

    if not webhook_url:
        raise SystemExit(f"{env_name} is required unless --dry-run is used")

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
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
