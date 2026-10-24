---
name: voice
description: Turn spoken notifications on or off, play a test, list voices or show the status (macOS).
argument-hint: "[on [voice] | off | test | voices | status | lang <en|pt-BR|auto> | voice <id|auto>]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/voice_notify.py" *)
disable-model-invocation: true
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/voice_notify.py" $ARGUMENTS`

The output above comes from the voice-notify plugin. Show it to the user as it is, then stop.
Do not run any other command.
