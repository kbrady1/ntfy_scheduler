#!/usr/bin/env python3

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

CONFIG_PATH = os.path.expanduser("~/.ntfy_scheduler.json")


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"enabled": True}


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def cmd_enable(args):
    config = load_config()
    config["enabled"] = True
    save_config(config)
    print("ntfy notifications enabled.")


def cmd_disable(args):
    config = load_config()
    config["enabled"] = False
    save_config(config)
    print("ntfy notifications disabled.")


def cmd_send(args):
    config = load_config()
    if not config.get("enabled", True):
        print("Notifications are disabled. Run 'ntfy enable' to re-enable.")
        return

    message = args.message

    # When message is "-", read Claude Code hook JSON from stdin and extract
    # the "message" field (falls back to raw stdin if not valid JSON).
    if message == "-":
        raw = sys.stdin.read().strip()
        try:
            payload = json.loads(raw)
            message = payload.get("message") or raw
            # Use hook title as fallback if --title not provided
            if not args.title:
                args.title = payload.get("title")
        except json.JSONDecodeError:
            message = raw

    url = f"https://ntfy.sh/{args.topic}"
    headers = {}

    if args.title:
        headers["Title"] = args.title
    if args.priority:
        headers["Priority"] = args.priority
    if args.tags:
        headers["Tags"] = args.tags

    body = message.encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 200:
                print(f"Notification sent to ntfy.sh/{args.topic}.")
            else:
                print(f"Unexpected response: {resp.status}", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Request failed: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="ntfy",
        description="Send notifications via ntfy.sh.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # send
    send_parser = subparsers.add_parser("send", help="Send a notification.")
    send_parser.add_argument("topic", help="ntfy.sh topic name (used as URL path).")
    send_parser.add_argument(
        "message",
        help="Notification message body. Pass '-' to read from stdin (Claude Code hook JSON).",
    )
    send_parser.add_argument("--title", "-t", help="Notification title.")
    send_parser.add_argument(
        "--priority",
        "-p",
        choices=["min", "low", "default", "high", "urgent"],
        help="Notification priority.",
    )
    send_parser.add_argument(
        "--tags",
        help="Comma-separated tags (e.g. 'warning,skull').",
    )
    send_parser.set_defaults(func=cmd_send)

    # enable
    enable_parser = subparsers.add_parser("enable", help="Enable notifications globally.")
    enable_parser.set_defaults(func=cmd_enable)

    # disable
    disable_parser = subparsers.add_parser("disable", help="Disable notifications globally.")
    disable_parser.set_defaults(func=cmd_disable)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
