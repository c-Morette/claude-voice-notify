# claude-voice-notify

Spoken notifications for [Claude Code](https://code.claude.com) on **macOS**.

When a session finishes, your Mac says the repository name and reads a short summary that Claude itself wrote at the end of its reply. When a session is waiting for your approval or has a question, it tells you that too. You can work in another window, or away from the screen, and still know which session needs you.

> *"acme web is done. The tests pass and the migration is ready. Approve the push when you can."*

- One Python script, standard library only. No dependencies, no API key, no second model.
- Everything runs on your Mac. Nothing goes over the network.
- English and Brazilian Portuguese.
- **v0.1 is macOS only.** See [Not on a Mac?](#not-on-a-mac)

**Unofficial.** This is a community plugin, not affiliated with or endorsed by Anthropic.

[Português abaixo](#português)

## Contents

- [Quick start](#quick-start)
- [Requirements](#requirements)
- [What you will hear](#what-you-will-hear)
- [Commands](#commands)
- [Choosing a voice](#choosing-a-voice)
- [Language](#language)
- [Not on a Mac?](#not-on-a-mac)
- [Turning it off and uninstalling](#turning-it-off-and-uninstalling)
- [Troubleshooting](#troubleshooting)
- [How it works](#how-it-works)
- [Configuration files](#configuration-files)
- [Pitfalls that became decisions](#pitfalls-that-became-decisions)
- [Privacy](#privacy) · [Limitations](#limitations) · [Development](#development)

## Quick start

1. Add this repository as a plugin marketplace and install the plugin. In a terminal:

   ```bash
   claude plugin marketplace add c-Morette/claude-voice-notify
   ```

   ```bash
   claude plugin install voice-notify@voice-notify
   ```

   Inside a Claude Code session, the same thing is `/plugin marketplace add c-Morette/claude-voice-notify`, then `/plugin install voice-notify@voice-notify`.

2. Open a **new** session. A session that was already open loads the new plugin only after `/reload-plugins`.

3. Turn it on. The plugin is installed switched off, so nothing speaks until you do this:

   ```
   /voice-notify on
   ```

   You should hear *"Voice on."*

4. Ask Claude for anything. When it finishes, you hear the repository name and, when there is something worth saying, a short summary.

To hear a sample at any time, run `/voice-notify test`.

## Requirements

- **macOS.** Built and tested on macOS 27.
- **Claude Code with plugin support**, in the terminal or in the desktop app. Tested with 2.1.287 (CLI) and 2.1.299 (desktop app).
- **`python3`, version 3.9 or newer, on your `PATH`.** The `python3` from Apple's Command Line Tools is enough. If macOS asks you to install them the first time you run `python3`, accept, or run `xcode-select --install`.

## What you will hear

| When | English | Português |
|---|---|---|
| A session finished, with a summary | *"acme web is done. The tests pass. Approve the push when you can."* | *"Pronto, acme web acabou. Os testes passam. Falta você aprovar o envio."* |
| A session finished, nothing to add | *"acme web is done."* | *"acme web terminou."* |
| Claude needs permission for a tool | *"acme web is waiting for your approval."* | *"acme web está esperando sua aprovação."* |
| Claude asked you a question | *"acme web has a question for you."* | *"acme web tem uma pergunta pra você."* |

- **The opening sentence varies a little**, so it doesn't sound like a machine reading the same line.
- **The name is the repository**, never the session title. A worktree is announced by its main repository.
- **The summary is the last line of Claude's reply that starts with 🔊.** You will also see that line in the chat. Claude adds it only when there is something you need to know, so short replies often end without one.

## Commands

| Command | What it does |
|---|---|
| `/voice-notify on [voice]` | Turn on. Applies to every open session from its next message. |
| `/voice-notify off` | Turn off. |
| `/voice-notify test` | Speak a sample announcement with the current voice. |
| `/voice-notify voices` | List the installed voices for your language, best first, and mark the one in use. |
| `/voice-notify status` | On or off, language, voice, and the last five events. |
| `/voice-notify lang en\|pt-BR\|auto` | Choose the language. `auto` follows the macOS language. |
| `/voice-notify voice <id>\|auto` | Choose a voice by its identifier from `voices`, or a `say` name like `Samantha`. `auto` picks the best one. |

Without arguments, `/voice-notify` shows the status. The full name of the command is `/voice-notify:voice-notify`. It is not `/voice` because Claude Code already has a built-in `/voice` (voice dictation), and the built-in wins.

## Choosing a voice

Out of the box the plugin uses the best voice you have installed for your language. The voices that come with macOS sound robotic. The Siri voices sound human, so it is worth downloading one.

**1. See what you have:**

```
/voice-notify voices
```

```
voices for en (* = in use):
* com.apple.voice.compact.en-US.Samantha  (Samantha, en-US, default)
  com.apple.voice.super-compact.en-GB.Daniel  (Daniel, en-GB, default)
  ...
```

The last column is the quality, from best to worst: `premium`, `enhanced`, `default`.

**2. Download a better voice:**

1. Open System Settings > Accessibility > Spoken Content.
2. Open the System voice menu and choose Manage Voices.
3. Pick your language. Download a Siri voice if one is offered, or one marked Premium or Enhanced.

You don't have to make it the system voice. Run `/voice-notify voices` again and it shows up.

**3. Use it:**

- **Automatic:** leave the voice on `auto` (the default) and the plugin chooses for you. The order is Siri voices first, then premium, enhanced and default quality, then the main region (`en-US`, `pt-BR`). Novelty voices (Bells, Zarvox…), Eloquence voices (Eddy, Flo…) and your Personal Voice are never picked automatically.
- **A specific voice:** copy its identifier from `voices`:

  ```
  /voice-notify voice com.apple.siri.natural.Sandra
  ```

  `/voice-notify on <identifier>` turns the plugin on and sets the voice in one step.
- **A `say` voice name:** short names go through the `say` command (`say -v '?'` lists them):

  ```
  /voice-notify voice Samantha
  ```

  `say` can't reach the Siri voices. For those, use the identifier.
- **Back to automatic:** `/voice-notify voice auto`.

Try the result with `/voice-notify test`.

**Can I use any other voice?** Any voice that macOS can speak with works: the built-in voices, the downloaded Siri, premium and enhanced voices, and any `say` voice. A voice from another language also works, but it reads the English or Portuguese text with its own accent. The plugin doesn't call outside services, so a cloud voice (ElevenLabs, OpenAI and similar) isn't supported in v0.1. Speaking rate and volume follow the macOS defaults.

## Language

The language decides three things: the instruction Claude gets, the sentences you hear, and the voices `auto` chooses from.

- `auto` (default): the macOS interface language. Any Portuguese becomes `pt-BR`. Anything else becomes English.
- `/voice-notify lang en` or `/voice-notify lang pt-BR`: fixed, whatever the system says.

Claude writes the 🔊 summary in the language set here, even if you chat with it in another one.

## Not on a Mac?

v0.1 speaks through the macOS speech engine, so it works on **macOS only**.

On Linux or Windows the plugin installs, but it stays silent on purpose:

- The hooks exit at once.
- Claude gets no extra instruction, so no extra tokens are spent.
- `/voice-notify` only says that this system isn't supported.

On Windows, the hooks call `python3`, a command that may not exist there. If Claude Code shows a hook error, disable the plugin in `/plugin`.

Most of the script is portable: the hooks, the queue, the summary and the repository name. Only two pieces depend on the Mac: `speak()`, which uses AVSpeech, and the file lock, which uses `fcntl` on macOS and Linux. Support for other systems would mean a speaker for each one, such as `spd-say` or `espeak-ng` on Linux and `System.Speech` on Windows. Pull requests are welcome.

## Turning it off and uninstalling

- **Pause:** `/voice-notify off`. The plugin stays installed and adds nothing to your prompts.
- **Uninstall:**

  ```bash
  claude plugin uninstall voice-notify@voice-notify
  ```

  ```bash
  claude plugin marketplace remove voice-notify
  ```

  Then delete `~/.claude/voice-notify/` if you don't want to keep the settings and the log.

## Troubleshooting

- **Nothing speaks:**
  1. Run `/voice-notify status`. It must say `ON`.
  2. Did you open a new session after installing, or run `/reload-plugins`? A session that was already open doesn't have the hooks.
  3. Look at `last events` in the status:
     - **Events are listed:** the hooks work. Check the volume and the output device, then try `/voice-notify test`.
     - **No events:** the hooks didn't run. Check that the plugin is enabled in `/plugin`, and look for it in `/hooks`.
- **It never reads a summary.** Claude only writes the 🔊 line when there is something to tell you. If it never does, check that the plugin was on before you sent the message: the instruction goes with each prompt.
- **It says the wrong project.** The name comes from the folder where the session started, not from where Claude moved later with `cd`. Inside a git repository, it is the repository's folder name.
- **I hear two voices.** Another hook, yours or another plugin's, also speaks. Keep one of them.
- **The voice sounds robotic.** Install a Siri or premium voice. See [Choosing a voice](#choosing-a-voice).
- **`claude -p` and SDK scripts don't speak.** That is on purpose: nobody is listening to them.

## How it works

Three hooks call the same script, [`scripts/voice_notify.py`](scripts/voice_notify.py):

1. **`UserPromptSubmit`** (synchronous, 10 s timeout). When the voice is on, it adds one instruction to the turn: end the final reply with one line that starts with 🔊, with 2 to 4 short sentences written to be heard (what was done, what is needed from you), and no code, paths, markdown or links. That costs about 100 tokens per prompt while on, and nothing while off.
2. **`Stop`** (async). It takes `last_assistant_message` from the hook input and finds the last line that **starts** with 🔊. A 🔊 in the middle of a sentence doesn't count. It strips markdown and links, caps the text at 420 characters, and queues *"&lt;repo&gt; is done. &lt;summary&gt;"*. Without a 🔊 line it just says *"&lt;repo&gt; is done."*
3. **`Notification`** (async). A permission prompt becomes *"&lt;repo&gt; needs you."* A question (`elicitation_dialog`) becomes *"&lt;repo&gt; has a question for you."* Idle reminders and unknown types stay quiet, but still go to the log.

The summary comes from the Claude that did the work, in the same reply. It knows what matters and costs no extra call. Other tools send the transcript to a second model to summarize it.

The name you hear is the repository, never the session title. It comes from `git rev-parse --git-common-dir`, so a worktree speaks as its main repository. Dashes, dots and underscores become spaces, so `acme-web` is read as "acme web". Outside a repository, the folder name is used.

Hooks never speak by themselves. They append to a queue and start a detached speaker. Only one speaker runs at a time: it reads the queue in order and speaks one announcement after another. The hook returns in milliseconds.

Two cases are skipped on purpose. `stop_hook_active` means Claude is continuing because of a Stop hook, so the session hasn't really finished. `CLAUDE_CODE_ENTRYPOINT=sdk*` means `claude -p` and SDK scripts, which nobody is listening to.

## Configuration files

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

**claude-voice-notify** é um plugin para o Claude Code que **fala** quando uma sessão termina ou precisa de você. Ele diz o nome do repositório e lê um resumo de 2 a 4 frases. Quem escreve esse resumo é o próprio Claude, no fim da resposta. Tudo fica no seu Mac: sem rede, sem chave de API e sem outro modelo. É um projeto não oficial, sem vínculo com a Anthropic.

**Só macOS na v0.1.** No Linux e no Windows ele instala, mas fica calado (veja [Not on a Mac?](#not-on-a-mac)).

**Instalação**, no terminal:

```bash
claude plugin marketplace add c-Morette/claude-voice-notify
```

```bash
claude plugin install voice-notify@voice-notify
```

Depois, abra uma sessão **nova** e rode `/voice-notify on`. Você ouve *"Voz ligada."* Ele vem desligado, por isso esse passo é obrigatório.

**Comandos:**

- `/voice-notify on` e `/voice-notify off`.
- `/voice-notify test`: fala um aviso de exemplo.
- `/voice-notify voices`: lista as vozes instaladas do idioma, da melhor para a pior.
- `/voice-notify voice <identificador>`: escolhe uma voz. `voice auto` volta para a automática.
- `/voice-notify lang pt-BR|en|auto`: escolhe o idioma.
- `/voice-notify status`: mostra se está ligado, o idioma, a voz e os últimos avisos.

O nome não é `/voice` porque o Claude Code já tem um `/voice` próprio, de ditado.

**Voz boa:**

1. Abra Ajustes do Sistema > Acessibilidade > Conteúdo Falado.
2. No menu Voz do sistema, escolha Gerenciar Vozes.
3. Baixe uma voz da Siri, ou uma marcada como Premium ou Melhorada.

Não precisa colocá-la como voz do sistema. Com `voice auto`, o plugin escolhe sozinho a melhor voz instalada, e a Siri vem primeiro. Para fixar uma voz, copie o identificador do `voices`, por exemplo `/voice-notify voice com.apple.siri.natural.Sandra`.

**Como funciona:**

- `UserPromptSubmit`: pede ao Claude que termine a resposta com uma linha 🔊.
- `Stop`: põe na fila "*repo* terminou" e o resumo.
- `Notification`: avisa quando há aprovação ou pergunta esperando você.

Um falador solto lê a fila em ordem, um aviso por vez. Problemas, configuração, armadilhas e limitações estão nas seções em inglês acima. O estado fica em `~/.claude/voice-notify/`.

## License

[MIT](LICENSE)
