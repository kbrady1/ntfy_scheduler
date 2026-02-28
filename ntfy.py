#!/usr/bin/env python3

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error

CONFIG_PATH = os.path.expanduser("~/.ntfy_scheduler.json")
STATE_PATH = os.path.expanduser("~/.ntfy_scheduler_state.json")


# ---------------------------------------------------------------------------
# Config / state helpers
# ---------------------------------------------------------------------------

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"enabled": True}


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Core HTTP send
# ---------------------------------------------------------------------------

def do_send(topic, message, title=None, priority=None, tags=None):
    url = f"https://ntfy.sh/{topic}"
    headers = {}
    if title:
        headers["Title"] = title
    if priority:
        headers["Priority"] = priority
    if tags:
        headers["Tags"] = tags

    body = message.encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status != 200:
                print(f"Unexpected response: {resp.status}", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Request failed: {e.reason}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Stdin JSON parsing (Claude Code hook payload)
# ---------------------------------------------------------------------------

def parse_hook_stdin():
    """Read and parse Claude Code hook JSON from stdin."""
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"message": raw}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

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
        print("Notifications are disabled. Run 'ntfyScheduler enable' to re-enable.")
        return

    message = args.message
    session_id = args.session_id
    title = args.title

    cwd = None

    # Read Claude Code hook JSON from stdin when message is "-"
    if message == "-":
        payload = parse_hook_stdin()
        message = payload.get("message") or ""
        if not session_id:
            session_id = payload.get("session_id")
        if not title:
            title = payload.get("title")
        # Prepend project name (basename of cwd) to title for easy identification
        # when running multiple agents, e.g. "ntfy_scheduler - Permission needed"
        cwd = payload.get("cwd")
        if cwd:
            project = os.path.basename(cwd)
            title = f"{project} - {title}" if title else project

    if not message:
        print("No message provided.", file=sys.stderr)
        sys.exit(1)

    if args.delay and session_id:
        # Spawn a detached background process that will sleep then send.
        cmd = [
            sys.executable, os.path.abspath(__file__), "_deliver",
            args.topic, message,
            "--delay", str(args.delay),
            "--session-id", session_id,
        ]
        if title:
            cmd += ["--title", title]
        if args.priority:
            cmd += ["--priority", args.priority]
        if args.tags:
            cmd += ["--tags", args.tags]

        proc = subprocess.Popen(
            cmd,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        state = load_state()
        state[session_id] = {
            "pid": proc.pid,
            "scheduled_at": time.time(),
            "delay": args.delay,
            "cwd": cwd,
        }
        save_state(state)
        print(f"Notification scheduled in {args.delay}s for session {session_id} (PID {proc.pid}).")
    else:
        do_send(args.topic, message, title, args.priority, args.tags)
        print(f"Notification sent to ntfy.sh/{args.topic}.")


def cmd_cancel(args):
    session_id = args.session_id

    # Read session_id from Claude Code hook JSON when "-" is passed
    if session_id == "-":
        payload = parse_hook_stdin()
        session_id = payload.get("session_id")

    if not session_id:
        print("No session_id provided.", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    entry = state.get(session_id)

    if entry is None:
        # Nothing pending — silently succeed so the hook doesn't error
        return

    pid = get_pid(entry)
    killed = kill_session(session_id, entry, state)
    save_state(state)
    if killed:
        print(f"Cancelled notification for session {session_id} (PID {pid}).")
    else:
        print(f"Already fired: {session_id}.")


def get_pid(entry):
    """Return PID from a state entry (supports legacy int and current dict format)."""
    return entry["pid"] if isinstance(entry, dict) else entry


def kill_session(session_id, entry, state):
    """Kill a pending process and remove it from state. Returns True if killed."""
    pid = get_pid(entry)
    try:
        os.kill(pid, signal.SIGTERM)
        killed = True
    except ProcessLookupError:
        killed = False
    del state[session_id]
    return killed


def cmd_list(args):
    state = load_state()
    if not state:
        print("No pending notifications.")
        return
    print(f"{'SESSION ID':<40} {'PID':<8} {'TTL':<8} {'STATUS':<14} DIR")
    print("-" * 90)
    for session_id, entry in state.items():
        pid = get_pid(entry)
        try:
            os.kill(pid, 0)  # signal 0 checks existence without killing
            status = "pending"
        except ProcessLookupError:
            status = "already fired"

        if isinstance(entry, dict) and status == "pending":
            remaining = int(entry["scheduled_at"] + entry["delay"] - time.time())
            ttl = f"{max(0, remaining)}s"
        else:
            ttl = "-"

        cwd = entry.get("cwd", "") if isinstance(entry, dict) else ""
        print(f"{session_id:<40} {pid:<8} {ttl:<8} {status:<14} {cwd}")


def cmd_cancel_all(args):
    state = load_state()
    if not state:
        print("No pending notifications.")
        return
    for session_id, entry in list(state.items()):
        pid = get_pid(entry)
        killed = kill_session(session_id, entry, state)
        if killed:
            print(f"Cancelled {session_id} (PID {pid}).")
        else:
            print(f"Already fired: {session_id}.")
    save_state(state)


def cmd_deliver(args):
    """Hidden command: sleep, then send. Runs as a detached background process."""
    time.sleep(args.delay)

    # Remove ourselves from state before sending
    state = load_state()
    if args.session_id in state:
        del state[args.session_id]
        save_state(state)

    config = load_config()
    if config.get("enabled", True):
        do_send(args.topic, args.message, args.title, args.priority, args.tags)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="ntfyScheduler",
        description="Send and schedule notifications via ntfy.sh.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # send
    send_parser = subparsers.add_parser("send", help="Send or schedule a notification.")
    send_parser.add_argument("topic", help="ntfy.sh topic name (used as URL path).")
    send_parser.add_argument(
        "message",
        help="Notification message body. Pass '-' to read from Claude Code hook stdin JSON.",
    )
    send_parser.add_argument("--title", "-t", help="Notification title.")
    send_parser.add_argument(
        "--priority", "-p",
        choices=["min", "low", "default", "high", "urgent"],
        help="Notification priority.",
    )
    send_parser.add_argument("--tags", help="Comma-separated tags (e.g. 'warning,skull').")
    send_parser.add_argument(
        "--delay", "-d", type=int, metavar="SECONDS",
        help="Delay in seconds before sending. Requires --session-id or stdin JSON.",
    )
    send_parser.add_argument(
        "--session-id", dest="session_id",
        help="Session ID used to track and cancel pending notifications.",
    )
    send_parser.set_defaults(func=cmd_send)

    # cancel
    cancel_parser = subparsers.add_parser(
        "cancel", help="Cancel a pending scheduled notification."
    )
    cancel_parser.add_argument(
        "session_id",
        help="Session ID to cancel. Pass '-' to read from Claude Code hook stdin JSON.",
    )
    cancel_parser.set_defaults(func=cmd_cancel)

    # list
    list_parser = subparsers.add_parser("list", help="List all pending scheduled notifications.")
    list_parser.set_defaults(func=cmd_list)

    # cancel-all
    cancel_all_parser = subparsers.add_parser("cancel-all", help="Cancel all pending scheduled notifications.")
    cancel_all_parser.set_defaults(func=cmd_cancel_all)

    # enable
    enable_parser = subparsers.add_parser("enable", help="Enable notifications globally.")
    enable_parser.set_defaults(func=cmd_enable)

    # disable
    disable_parser = subparsers.add_parser("disable", help="Disable notifications globally.")
    disable_parser.set_defaults(func=cmd_disable)

    # _deliver (hidden — invoked by background subprocess only)
    deliver_parser = subparsers.add_parser("_deliver")
    deliver_parser.add_argument("topic")
    deliver_parser.add_argument("message")
    deliver_parser.add_argument("--delay", type=int, default=0)
    deliver_parser.add_argument("--session-id", dest="session_id")
    deliver_parser.add_argument("--title")
    deliver_parser.add_argument("--priority")
    deliver_parser.add_argument("--tags")
    deliver_parser.set_defaults(func=cmd_deliver)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
