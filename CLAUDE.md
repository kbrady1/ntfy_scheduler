# ntfy_scheduler — Claude Instructions

## Validating changes

Always validate changes using the installed `ntfyScheduler` command, not via direct Python invocation. This ensures the symlink, PATH resolution, and installed version are all exercised correctly.

```sh
# Correct
ntfyScheduler send my_topic "Test message" --title "Test"
ntfyScheduler list
ntfyScheduler cancel-all

# Wrong — do not use
python3 ntfy.py send ...
```

If `ntfyScheduler` is not found, run `make install` from the repo root first.

## Keeping README.md up to date

Update `README.md` any time you change:

- A command name, argument, or flag
- Command output format (e.g. columns in `list`)
- The state file schema
- Default behavior or hook integration details

The README is the primary reference for other users. It should always reflect the current behavior of the installed CLI.
