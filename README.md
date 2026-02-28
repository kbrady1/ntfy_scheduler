# ntfy_scheduler

A lightweight CLI for sending and scheduling push notifications via [ntfy.sh](https://ntfy.sh). Built to integrate with [Claude Code](https://claude.ai/code) hooks so you get notified on your phone or desktop when Claude needs your attention — and the notification is automatically cancelled if you respond before it fires.

---

## How it works

Two Claude Code hooks work together:

1. **Notification hook** — when Claude needs your input, a notification is *scheduled* with a configurable delay. If you don't respond in time, it fires.
2. **UserPromptSubmit hook** — when you submit a new prompt, any pending notification for that session is cancelled before it sends.

This prevents notification spam when you're already at your keyboard, while still alerting you on your phone when you've walked away.

---

## Requirements

- Python 3 (no third-party dependencies)
- An [ntfy.sh](https://ntfy.sh) topic (free, no account required)

---

## Install the ntfy app

Download the ntfy app to receive notifications on your devices:

- **iOS / Android**: [https://ntfy.sh/app](https://ntfy.sh/app)
- **Web**: [https://ntfy.sh](https://ntfy.sh)
- **macOS / Windows / Linux desktop**: [https://docs.ntfy.sh/subscribe/phone/](https://docs.ntfy.sh/subscribe/phone/)

Once installed, subscribe to a topic name of your choosing (e.g. `your_name_alerts`). Use the same topic name in the commands below.

---

## Installation

```sh
git clone https://github.com/kbrady1/ntfy_scheduler.git
cd ntfy_scheduler
make install
```

This symlinks `ntfy.py` into `/usr/local/bin/ntfyScheduler` so it's available globally.

To uninstall:

```sh
make uninstall
```

---

## Commands

### `send`

Send a notification immediately or schedule one for later.

```sh
ntfyScheduler send <topic> <message> [options]
```

| Argument | Description |
|---|---|
| `topic` | Your ntfy.sh topic name (used as the URL path) |
| `message` | Notification body. Pass `-` to read from Claude Code hook stdin JSON |
| `--title`, `-t` | Notification title |
| `--priority`, `-p` | One of: `min`, `low`, `default`, `high`, `urgent` |
| `--tags` | Comma-separated emoji tags (e.g. `warning,skull`) — see [ntfy.sh emoji list](https://docs.ntfy.sh/emojis/) |
| `--delay SECONDS` | Schedule the notification instead of sending immediately |
| `--session-id` | Session ID used to track and cancel the pending notification |

**Examples:**

```sh
# Send immediately
ntfyScheduler send my_topic "Deployment finished" --title "CI" --priority high --tags "white_check_mark"

# Schedule for 30 seconds from now
ntfyScheduler send my_topic "Still waiting on you" --delay 30 --session-id abc123

# Read message and session_id from Claude Code hook stdin
ntfyScheduler send my_topic - --title "Claude Code" --tags "hammer_and_wrench" --delay 30
```

---

### `cancel`

Cancel a pending scheduled notification by session ID.

```sh
ntfyScheduler cancel <session-id>
```

Pass `-` to read the `session_id` from Claude Code hook stdin JSON:

```sh
ntfyScheduler cancel -
```

If no notification is pending for the session, the command exits silently (safe to call unconditionally from a hook).

---

### `enable` / `disable`

Toggle notifications globally. State is persisted in `~/.ntfy_scheduler.json`.

```sh
ntfyScheduler enable
ntfyScheduler disable
```

When disabled, `send` exits silently without making any network request.

---

## Claude Code integration

### Hook configuration

The easiest way to configure hooks is interactively inside Claude Code. Run `/hooks` in any Claude Code session and it will walk you through adding, editing, and removing hooks via a menu-driven UI — no need to edit JSON by hand.

Alternatively, add the following directly to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "ntfyScheduler send your_topic_here - --title \"Claude Code\" --tags \"hammer_and_wrench\" --delay 30"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "ntfyScheduler cancel -"
          }
        ]
      }
    ]
  }
}
```

Replace `your_topic_here` with your ntfy.sh topic name. Adjust `--delay` to your preferred grace period in seconds.

### How the hooks use stdin

Claude Code passes a JSON payload via stdin to each hook. `ntfyScheduler` reads this automatically when you pass `-` as the message or session ID argument.

**Notification hook payload:**
```json
{
  "session_id": "abc123",
  "hook_event_name": "Notification",
  "message": "Claude needs your approval to run a Bash command",
  "title": "Permission needed",
  "cwd": "/Users/you/project"
}
```

**UserPromptSubmit hook payload:**
```json
{
  "session_id": "abc123",
  "hook_event_name": "UserPromptSubmit"
}
```

The `send` command extracts `message`, `title`, and `session_id` from the payload. The `cancel` command extracts `session_id`. Any field explicitly passed as a flag takes precedence over the stdin value.

### Notification lifecycle

```
Claude needs attention
        │
        ▼
ntfyScheduler send ... --delay 30
        │
        ├── Spawns background process (sleeps 30s)
        └── Stores PID in ~/.ntfy_scheduler_state.json

        │
        ├── [You respond within 30s]
        │         │
        │         ▼
        │   ntfyScheduler cancel -
        │         │
        │         └── Kills background process → no notification sent
        │
        └── [You don't respond within 30s]
                  │
                  ▼
            Background process wakes → sends notification to ntfy.sh
```

---

## State files

| File | Purpose |
|---|---|
| `~/.ntfy_scheduler.json` | Global enabled/disabled setting |
| `~/.ntfy_scheduler_state.json` | Pending notifications keyed by session ID |
