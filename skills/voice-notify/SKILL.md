---
name: voice-notify
description: Turn spoken notifications on or off, play a test, list voices, pick a voice or program, or show the status.
argument-hint: "[on [voice] | off | test | voices | status | lang <en|pt-BR|auto> | voice <name|auto> | command <program|off>]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh"*)
disable-model-invocation: true
---

!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" $ARGUMENTS`

The output above comes from the voice-notify plugin. Show it to the user as it is, then stop.
Do not run any other command.
