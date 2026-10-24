# claude-voice-notify

Claude Code plugin `voice-notify`: spoken notifications on macOS. What it does and why: `README.md`.

- **Stack:** Python 3.9+ standard library, one script (`scripts/voice_notify.py`). No dependencies, no network.
- **Layout:** the repo root is the plugin and its own marketplace (`.claude-plugin/`). Hooks in `hooks/hooks.json` call `scripts/run.sh` (finds Python, then runs the script); the `/voice-notify` command in `skills/voice-notify/SKILL.md` (the name `/voice` belongs to the built-in voice dictation). This file lives in `.claude/` because a `CLAUDE.md` at the plugin root makes `claude plugin validate` warn.
- **Check before a commit:**
  - `python3 -m unittest discover -s tests`, and again with `/usr/bin/python3` (the 3.9 that ships with macOS).
  - `claude plugin validate . --strict` and `claude plugin validate .claude-plugin/plugin.json --strict`.
- **Testing a hook by hand:** build the JSON with Python and pipe it with `printf '%s'`. The zsh `echo` turns `\n` inside the JSON into a real newline and the hook gets invalid input.
- **Public repo:** no personal names, machine paths, hostnames or e-mails in code, docs or tests.
