#!/bin/sh
# Runs voice_notify.py with the first Python 3.9+ found. Claude Code runs hooks with sh on macOS and Linux and
# with Git Bash on Windows, where `python3` may be missing or be the Microsoft Store placeholder.
here="${0%[/\\]*}"   # this folder; the path may use \ on Windows
[ "$here" = "$0" ] && here=.
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 &&
     "$py" -I -S -c 'import sys; sys.exit(sys.version_info < (3, 9))' </dev/null >/dev/null 2>&1; then
    exec "$py" "$here/voice_notify.py" "$@"
  fi
done
msg="voice-notify: no Python 3.9 or newer found (tried python3, python and py)"
if [ "$1" = hook ]; then echo "$msg" >&2; else echo "$msg"; fi   # a hook's stdout would become Claude's context
exit 0
