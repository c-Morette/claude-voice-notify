# claude-voice-notify

Spoken notifications for [Claude Code](https://code.claude.com) on macOS.

When a session finishes, your Mac says the repository name and reads a short summary that Claude itself wrote at the end of its reply. When a session is waiting for your approval or has a question, it tells you that too. You can work in another window, or away from the screen, and still know which session needs you.

> *"acme web is done. The tests pass and the migration is ready. Approve the push when you can."*

- One Python script, standard library only. No dependencies, no API key, no second model.
- Everything runs on your Mac. Nothing goes over the network.
- English and Brazilian Portuguese.

**Unofficial.** This is a community plugin, not affiliated with or endorsed by Anthropic.

[Português abaixo](#português)

## Install

Two commands in a terminal:

```bash
claude plugin marketplace add c-Morette/claude-voice-notify
```

```bash
claude plugin install voice-notify@voice-notify
```

Or, inside a session: `/plugin marketplace add c-Morette/claude-voice-notify`, then `/plugin install voice-notify@voice-notify`.

Then open a new session (or run `/reload-plugins`) and turn it on:

```
/voice-notify on
```

It is off until you do. Requirements: macOS, a Claude Code version with plugins, and `python3` 3.9 or newer (the one from the Xcode Command Line Tools is enough). Built on macOS 27 with Claude Code 2.1.287 (CLI) and 2.1.299 (desktop app).

## Usage

| Command | What it does |
|---|---|
| `/voice-notify on [voice]` | Turn on. Applies to every open session from its next message. |
| `/voice-notify off` | Turn off. |
| `/voice-notify test` | Speak a sample announcement. |
| `/voice-notify voices` | List the installed voices for your language, best first. |
| `/voice-notify status` | On or off, language, voice, and the last five events. |
| `/voice-notify lang en\|pt-BR\|auto` | Choose the language. `auto` follows the macOS language. |
| `/voice-notify voice <id>\|auto` | Choose a voice from `voices`, or a `say` name like `Samantha`. |

The full name is `/voice-notify:voice-notify`. It is not `/voice` because Claude Code already has a built-in `/voice` (voice dictation), and the built-in wins.

**Get a good voice.** The default macOS voices sound robotic. The Siri voices sound human. Download one in System Settings > Accessibility > Spoken Content > System voice > Manage Voices, then run `/voice-notify voices`. With `voice` on `auto`, the plugin picks the best installed voice for the language by itself.

## How it works

Three hooks call the same script, [`scripts/voice_notify.py`](scripts/voice_notify.py):

1. **`UserPromptSubmit`** (synchronous, 10 s timeout). When the voice is on, it adds one instruction to the turn: end the final reply with one line that starts with 🔊, with 2 to 4 short sentences written to be heard (what was done, what is needed from you), and no code, paths, markdown or links. That costs about 100 tokens per prompt while on, and nothing while off.
2. **`Stop`** (async). It takes `last_assistant_message` from the hook input and finds the last line that **starts** with 🔊. A 🔊 in the middle of a sentence doesn't count. It strips markdown and links, caps the text at 420 characters, and queues *"&lt;repo&gt; is done. &lt;summary&gt;"*. Without a 🔊 line it just says *"&lt;repo&gt; is done."*
3. **`Notification`** (async). A permission prompt becomes *"&lt;repo&gt; needs you."* A question (`elicitation_dialog`) becomes *"&lt;repo&gt; has a question for you."* Idle reminders and unknown types stay quiet, but still go to the log.

The summary comes from the Claude that did the work, in the same reply. It knows what matters and costs no extra call. Other tools send the transcript to a second model to summarize it.

The name you hear is the repository, never the session title. It comes from `git rev-parse --git-common-dir`, so a worktree speaks as its main repository. Dashes, dots and underscores become spaces, so `acme-web` is read as "acme web". Outside a repository, the folder name is used.

Hooks never speak by themselves. They append to a queue and start a detached speaker. Only one speaker runs at a time: it reads the queue in order and speaks one announcement after another. The hook returns in milliseconds.

Two cases are skipped on purpose. `stop_hook_active` means Claude is continuing because of a Stop hook, so the session hasn't really finished. `CLAUDE_CODE_ENTRYPOINT=sdk*` means `claude -p` and SDK scripts, which nobody is listening to.

## Configuration

State lives in `~/.claude/voice-notify/`:

| File | Purpose |
|---|---|
| `enabled` | Exists = on. Every hook checks it, so on and off apply to open sessions right away. |
| `config.json` | `{"language": "auto" \| "en" \| "pt-BR", "voice": "" (auto) \| identifier \| say name}` |
| `queue.jsonl` | Announcements waiting to be spoken. |
| `voice.log` | The last 50 hook events, including the quiet ones. It shows what the plugin heard and what it said. |
| `queue.lock`, `speaker.lock` | `flock` files. |

The state is deliberately outside the plugin folder, so it survives updates and reinstalls. The hooks and the command also find it without any environment variable. Set `CLAUDE_VOICE_NOTIFY_HOME` to move it; the tests use this.

- **Language:** `auto` reads the macOS interface language (`AppleLanguages`), then `LANG`. Any Portuguese becomes `pt-BR`, anything else becomes English.
- **Voice:** `auto` picks Siri voices first, then premium > enhanced > default quality, the main region (`en-US`, `pt-BR`), and non-compact voices. Novelty, Eloquence and Personal Voice voices are never picked automatically.

## Pitfalls that became decisions

These all came up while building this, and each one shaped the code.

1. **`say` can't reach the Siri voices.** `say -v '?'` lists only the classic voices. The Siri voices are available through `AVSpeechSynthesizer`, so the plugin calls AVSpeech from JavaScript for Automation (`osascript -l JavaScript`), with no compiled helper. The script must keep waiting while the synthesizer speaks, or `osascript` exits in the middle of a sentence. Short voice names like `Samantha` still go through `say`.
2. **A hook timeout must not cut a sentence short, so there is a queue.** A hook runs inside Claude Code's hook lifecycle and has a timeout (60 s here). A long summary, or three sessions finishing together, can take longer than that, and two hooks speaking at once talk over each other. So the hook only appends to a queue and starts a speaker in its own session (`start_new_session`), which outlives the hook. Current docs say a running async hook has no enforced timeout, but the plugin doesn't depend on that.
3. **`cd` moves the hook's `cwd`.** The `cwd` in the hook input is the session's *current* directory. After Claude runs `cd ../other-repo` in a Bash call, it would announce the wrong project. The plugin first uses `CLAUDE_PROJECT_DIR` (where the session started). Then it tries the desktop app's session record, then `cwd`.
   - The record is `~/Library/Application Support/Claude/claude-code-sessions/*/*/<CLAUDE_CODE_HOST_SESSION_ID>.json`, field `originCwd`.
   - That file is **internal to the app and has no contract**. Reading it is optional: if it moves or changes, the other sources take over.
4. **The zsh `echo` breaks JSON when you test a hook by hand.** The built-in `echo` in zsh turns `\n` into a real newline, even inside a JSON string. The hook then gets invalid JSON and, by design, does nothing silently. Build the JSON with Python and pipe it with `printf '%s'`:

   ```bash
   printf '%s' "$(python3 -c 'import json; print(json.dumps({"hook_event_name": "Stop", "last_assistant_message": "ok\n🔊 It works."}))')" | python3 scripts/voice_notify.py hook
   ```
5. **On and off apply to sessions that are already open; installing does not.** Every hook call reads the `enabled` flag, so `/voice-notify on` works in every open session from its next message, with no restart. A freshly installed or updated plugin is different: its hooks load at the next session start, or after `/reload-plugins`.
6. **`/voice` is taken.** Claude Code has a built-in `/voice` for dictation, and a plugin command with the same short name loses to it. That is why the command is `/voice-notify`.
7. **A notification must never break a session.** Every error in the hook is swallowed: bad input, a missing `git`, a full disk. A hook error shows up in the session, and a spoken notification is not worth that. If nothing speaks, look at `/voice-notify status` and `~/.claude/voice-notify/voice.log`.

## Privacy

Everything stays on your Mac. There are no network calls, no telemetry, no API key and no second model.

- **Reads:** the hook input on stdin, the git metadata of the session folder, and, optionally, the desktop app's session record (see pitfall 3).
- **Speaks:** with the macOS speech engine.
- **Writes:** only to `~/.claude/voice-notify/`. The log keeps the last 50 announcements, summaries included.

## Limitations

- macOS only in v0.1. On other systems the hooks do nothing and `/voice-notify` says so.
- English and Brazilian Portuguese only.
- Notification only. There is no voice input.
- The summary depends on Claude following the instruction. Without the 🔊 line you just hear *"&lt;repo&gt; is done."*
- The 🔊 line also shows in the chat.
- A new prompt doesn't interrupt an announcement that is already playing.
- It relies on `last_assistant_message` in the Stop hook input, which recent Claude Code versions send.
- `CLAUDE_CODE_ENTRYPOINT` isn't documented. If it changes, `claude -p` runs might start speaking.
- If you already have hooks that speak, you will hear both.

## Development

```bash
python3 -m unittest discover -s tests
```

```bash
claude plugin validate . --strict
```

`claude --plugin-dir .` loads the working copy for one session without installing it. Run the tests with `/usr/bin/python3` too: it is the 3.9 that ships with macOS.

## Prior art

The `narrator` plugin in [midudev/better-claude](https://github.com/midudev/better-claude) (MIT) also speaks summaries through AVSpeech, and it asks a second model to write them. This plugin asks the Claude that did the work instead. No code was copied from it.

## Português

**claude-voice-notify** é um plugin para o Claude Code no macOS que **fala** quando uma sessão termina ou precisa de você. Ele diz o nome do repositório e lê um resumo de 2 a 4 frases. Quem escreve esse resumo é o próprio Claude, no fim da resposta. Tudo fica no seu Mac: sem rede, sem chave de API e sem outro modelo. É um projeto não oficial, sem vínculo com a Anthropic.

**Instalação:**

```bash
claude plugin marketplace add c-Morette/claude-voice-notify
```

```bash
claude plugin install voice-notify@voice-notify
```

Depois, numa sessão nova, rode `/voice-notify on`. Os comandos são:

- `on`, `off` e `test`.
- `voices`: lista as vozes instaladas.
- `status`.
- `lang en|pt-BR|auto`.
- `voice <id>|auto`.

O nome não é `/voice` porque o Claude Code já tem um `/voice` próprio, de ditado.

**Voz boa:** as vozes da Siri são bem mais naturais que as padrão. Baixe uma em Ajustes do Sistema > Acessibilidade > Conteúdo Falado > Voz do sistema > Gerenciar Vozes. Com `voice auto`, o plugin escolhe sozinho a melhor voz instalada para o idioma.

**Como funciona:**

- `UserPromptSubmit`: pede ao Claude que termine a resposta com uma linha 🔊.
- `Stop`: põe na fila "*repo* terminou" e o resumo.
- `Notification`: avisa quando há aprovação ou pergunta esperando você.

Um falador solto lê a fila em ordem, um aviso por vez. As armadilhas, a configuração e as limitações estão nas seções em inglês acima. O estado fica em `~/.claude/voice-notify/`.

## License

[MIT](LICENSE)
