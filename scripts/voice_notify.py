#!/usr/bin/env python3
"""claude-voice-notify: spoken notifications for Claude Code.

One file, standard library only, Python 3.9+. Claude Code runs it as a hook:

  UserPromptSubmit  (sync)   asks Claude to end its reply with one "🔊 ..." summary line
  Stop              (async)  queues "<repo> is done." plus that summary
  Notification      (async)  queues "<repo> needs you." when a permission prompt or question waits

and the /voice-notify command runs it with on, off, test, voices, status, lang, voice or command.

It speaks with the system's own engine: AVSpeech on macOS (reaches the Siri voices), speech-dispatcher or
eSpeak NG on Linux, System.Speech on Windows. Or with a program you choose (/voice-notify command).
Nothing leaves this machine unless that program sends it somewhere.
"""
import datetime
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

STATE = Path(os.environ.get("CLAUDE_VOICE_NOTIFY_HOME") or Path.home() / ".claude" / "voice-notify")
ENABLED = STATE / "enabled"      # exists = speak
CONFIG = STATE / "config.json"   # {"language": "auto" | "en" | "pt-BR", "voice": "" (auto) | name, "command": ""}
QUEUE = STATE / "queue.jsonl"    # announcements waiting their turn, one JSON per line
LOG = STATE / "voice.log"        # last 50 hook events, including the silent ones
LOG_LINES = 50

LANGUAGES = ("en", "pt-BR")

# The summary is written by the same Claude that did the work, so it costs nothing extra and knows what matters.
INSTRUCTION = {
    "en": "Voice notifications are on (claude-voice-notify): at the end of your final reply this turn, if there is "
          "something the user needs to know, close with ONE line starting with 🔊 and 2 to 4 short sentences in "
          "English, written to be heard: what was done and what you need from the user (approve, review, decide). "
          "No code, file paths, markdown or links, and don't repeat the project name (the voice already says it). "
          "If nothing is worth saying, leave the line out.",
    "pt-BR": "Voz ligada (claude-voice-notify): no fim da resposta final deste turno, se houver algo que a pessoa "
             "precise saber, feche com UMA linha começando com 🔊 e 2 a 4 frases curtas em português, escritas para "
             "serem ouvidas: o que foi feito e o que precisa dela (aprovar, olhar, decidir). Sem código, caminho de "
             "arquivo, markdown nem link, e sem repetir o nome do projeto (a voz já diz). Se não houver nada que "
             "valha falar, não escreva a linha.",
}

# How a person would tell you: the repository name (never the session title), then the 🔊 summary if there is one.
PHRASES = {
    "en": {
        "done": ("{p} is done.", "{p} finished.", "{p} is done, take a look when you can.", "All done in {p}."),
        "done_summary": ("{p} is done.", "{p} finished.", "All done in {p}."),
        "approval": ("{p} needs you.", "{p} is waiting for your approval."),
        "question": ("{p} has a question for you.",),
        "on": "Voice on.",
        "test": "This is how the summary will sound.",
    },
    "pt-BR": {
        "done": ("{p} terminou.", "Pronto, {p} acabou.", "{p} terminou, dá uma olhada quando puder.", "Terminei no {p}."),
        "done_summary": ("{p} terminou.", "Pronto, {p} acabou.", "Terminei no {p}."),
        "approval": ("{p} precisa de você.", "{p} está esperando sua aprovação."),
        "question": ("{p} tem uma pergunta pra você.",),
        "on": "Voz ligada.",
        "test": "É assim que o resumo vai soar.",
    },
}

# macOS: AVSpeech through JavaScript for Automation reaches the Siri and premium voices; `say` does not.
SPEAK_JS = """ObjC.import("AVFoundation");
function run(argv) {
  const s = $.AVSpeechSynthesizer.alloc.init, u = $.AVSpeechUtterance.speechUtteranceWithString(argv[2]);
  let v = argv[0] ? $.AVSpeechSynthesisVoice.voiceWithIdentifier(argv[0]) : $();
  if (v.isNil()) v = $.AVSpeechSynthesisVoice.voiceWithLanguage(argv[1]);
  u.voice = v;
  s.speakUtterance(u); delay(0.3);
  while (s.speaking) delay(0.1);   // without this wait the process exits mid-sentence
}"""
VOICES_JS = """ObjC.import("AVFoundation");
const v = $.AVSpeechSynthesisVoice.speechVoices, r = [];
for (let i = 0; i < v.count; i++) { const x = v.objectAtIndex(i);
  r.push([x.identifier.js, x.name.js, x.language.js, x.quality].join("\\t")); }
r.join("\\n")"""
QUALITY = {1: "default", 2: "enhanced", 3: "premium"}

# Windows: System.Speech ships with Windows PowerShell 5.1 (powershell.exe; PowerShell 7 doesn't have it).
# The text and the voice travel in environment variables, so nothing is ever quoted into a command line.
SAPI_PS = """Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo }
$p = if ($env:VOICE_NOTIFY_VOICE) { $v | Where-Object { $_.Name -eq $env:VOICE_NOTIFY_VOICE } }
     else { $v | Where-Object { $_.Culture.Name -like "$($env:VOICE_NOTIFY_LANG)*" } }
if ($p) { $s.SelectVoice(@($p)[0].Name) }
$s.Speak($env:VOICE_NOTIFY_TEXT)"""
SAPI_VOICES_PS = """Add-Type -AssemblyName System.Speech
(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | Where-Object { $_.Enabled } |
  ForEach-Object { $_.VoiceInfo.Name + "`t" + $_.VoiceInfo.Name + "`t" + $_.VoiceInfo.Culture.Name + "`t1" }"""

ESPEAK_VOICE = {"en": "en-us", "pt-BR": "pt-br"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # Windows: no console window flashing up


def system():
    """"mac", "linux", "windows" or another sys.platform value."""
    if sys.platform == "darwin":
        return "mac"
    if os.name == "nt":
        return "windows"
    return "linux" if sys.platform.startswith("linux") else sys.platform


def run(cmd, cwd=None, timeout=10, env=None):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, env=env, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


# --- configuration -------------------------------------------------------------------------------------------

def load_config():
    try:
        c = json.loads(CONFIG.read_text(encoding="utf-8"))
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(**changes):
    c = load_config()
    c.update(changes)
    STATE.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def windows_ui_language():
    import ctypes
    import locale
    return locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")


def system_language():
    """The interface language (macOS AppleLanguages, Windows UI language), then the POSIX locale. "" if unknown."""
    try:
        if system() == "mac":
            m = re.search(r'\(\s*"?([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*)',
                          run(["defaults", "read", "-g", "AppleLanguages"]).stdout)
            if m:
                return m.group(1)
        elif system() == "windows":
            tag = windows_ui_language()
            if tag:
                return tag
    except Exception:
        pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(var, "") not in ("", "C", "POSIX"):
            return os.environ[var]
    return ""


def language(config=None):
    lang = (config if config is not None else load_config()).get("language") or "auto"
    if lang in LANGUAGES:
        return lang
    return "pt-BR" if system_language().lower().startswith("pt") else "en"


# --- speech engines ------------------------------------------------------------------------------------------

def system_engine():
    """The system's own speech engine: "avspeech", "sapi", "spd-say", "espeak-ng", or "" if there is none."""
    s = system()
    if s == "mac":
        return "avspeech"
    if s == "windows":
        return "sapi" if shutil.which("powershell") else ""
    if s == "linux":
        return next((e for e in ("spd-say", "espeak-ng") if shutil.which(e)), "")
    return ""


def can_speak(config=None):
    return bool((config if config is not None else load_config()).get("command")) or bool(system_engine())


def installed_voices():
    """[(identifier, name, language, quality)] on macOS (AVSpeech) and Windows (System.Speech). [] elsewhere:
    on Linux the engine picks a voice for the language."""
    engine = system_engine()
    if engine == "avspeech":
        out = run(["osascript", "-l", "JavaScript", "-e", VOICES_JS]).stdout
    elif engine == "sapi":
        out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", SAPI_VOICES_PS], timeout=30).stdout
    else:
        return []
    voices = []
    for line in out.splitlines():
        f = line.strip("\r").split("\t")
        if len(f) == 4:
            voices.append((f[0], f[1], f[2], int(f[3]) if f[3].isdigit() else 1))
    return voices


ODD_VOICES = re.compile(r"speech\.synthesis\.voice|eloquence|personalvoice")   # novelty, Eloquence, Personal Voice


def voice_rank(voice, lang):
    """Higher is better: Siri voices, then premium > enhanced > default, then the main region, then not compact."""
    ident, _, vlang, quality = voice
    main_region = {"en": "en-us", "pt-BR": "pt-br"}[lang]
    return (".siri." in ident, quality, vlang.lower() == main_region, not ODD_VOICES.search(ident),
            "compact" not in ident)


def best_voice(lang, voices):
    """The best installed voice for the language, or None. Novelty, Eloquence and Personal Voice are left out."""
    tag = lang.lower()
    usable = [v for v in voices if v[2].lower().startswith(tag) and not ODD_VOICES.search(v[0])]
    return max(usable, key=lambda v: voice_rank(v, lang)) if usable else None


def chosen_voice(lang, config=None):
    """The configured voice, or the best installed one for the language ("" lets the engine pick)."""
    v = (config if config is not None else load_config()).get("voice") or ""
    if v:
        return v
    best = best_voice(lang, installed_voices())
    return best[0] if best else ""


def speech_env(text, voice, lang):
    return dict(os.environ, VOICE_NOTIFY_TEXT=text, VOICE_NOTIFY_LANG=lang, VOICE_NOTIFY_VOICE=voice or "")


def run_command(command, text, voice, lang):
    """Your own speech program. It runs in the system shell with the text in VOICE_NOTIFY_TEXT (plus _LANG and
    _VOICE); on macOS and Linux the text is also its last argument. True if it exited with 0."""
    env = speech_env(text, voice, lang)
    try:
        if system() == "windows":
            r = subprocess.run(command, shell=True, env=env, timeout=300, creationflags=NO_WINDOW,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            r = subprocess.run(["/bin/sh", "-c", command + ' "$VOICE_NOTIFY_TEXT"'], env=env, timeout=300,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def speak(text, voice, lang, command=""):
    """Says the text and returns when it's done. Your program goes first; if it fails, the system voice speaks."""
    if command and run_command(command, text, voice, lang):
        return
    engine = system_engine()
    if engine == "avspeech":
        # A dotted identifier goes through AVSpeech (reaches Siri), a short name through `say -v`.
        if voice and "." not in voice:
            r = run(["say", "-v", voice, text], timeout=180)
        else:
            r = run(["osascript", "-l", "JavaScript", "-e", SPEAK_JS, voice or "", lang, text], timeout=180)
        if r.returncode:
            run(["say", text], timeout=180)
    elif engine == "sapi":
        run(["powershell", "-NoProfile", "-NonInteractive", "-Command", SAPI_PS], timeout=180,
            env=speech_env(text, voice, lang))
    elif engine == "spd-say":   # -w waits until the sentence is spoken
        run(["spd-say", "-w", "-l", lang] + (["-y", voice] if voice else []) + [text], timeout=180)
    elif engine == "espeak-ng":
        run(["espeak-ng", "-v", voice or ESPEAK_VOICE[lang], text], timeout=180)


# --- queue ---------------------------------------------------------------------------------------------------
# A hook runs inside Claude Code's hook lifecycle, and two hooks speaking at once talk over each other.
# So the hook only appends to a queue and starts a detached speaker; one speaker at a time reads it in order.

class FileLock:
    """An exclusive lock on a file in STATE: flock on macOS and Linux, msvcrt on Windows."""

    def __init__(self, f):
        self.f = f

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()

    def release(self):
        if os.name == "nt":
            import msvcrt
            try:
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        self.f.close()   # closing also releases a flock


def lock(name, wait=True):
    """Returns a FileLock, or None if the lock is busy and wait=False."""
    STATE.mkdir(parents=True, exist_ok=True)
    f = open(STATE / name, "a+")
    try:
        if os.name == "nt":
            import msvcrt   # LK_LOCK retries for about 10 s, then raises
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        return FileLock(f)
    except OSError:
        f.close()
        return None


def start_speaker():
    """A speaker process that outlives the hook: its own session on macOS and Linux, detached on Windows."""
    argv = [sys.executable, os.path.abspath(__file__), "--speak-queue"]
    quiet = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.name != "nt":
        subprocess.Popen(argv, start_new_session=True, **quiet)
        return
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:   # leave Claude Code's job object, if it lets us, so closing the hook doesn't take the speaker along
        subprocess.Popen(argv, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **quiet)
    except OSError:
        subprocess.Popen(argv, creationflags=flags, **quiet)


def enqueue(text, lang, spawn=True):
    with lock("queue.lock"):
        with open(QUEUE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"text": text, "lang": lang}, ensure_ascii=False) + "\n")
    if spawn:
        start_speaker()


def dequeue():
    """The oldest announcement, or None when the queue is empty. A broken line is dropped."""
    while True:
        with lock("queue.lock"):
            lines = QUEUE.read_text(encoding="utf-8").splitlines() if QUEUE.exists() else []
            QUEUE.write_text("".join(line + "\n" for line in lines[1:]), encoding="utf-8")
        if not lines:
            return None
        try:
            item = json.loads(lines[0])
            if isinstance(item, dict) and item.get("text"):
                return item
        except ValueError:
            pass


def speak_queue(say=None):
    """One speaker at a time. If something arrived between emptying the queue and releasing the lock, go again."""
    config, voices = load_config(), {}
    say = say or (lambda text, voice, lang: speak(text, voice, lang, config.get("command") or ""))
    while True:
        held = lock("speaker.lock", wait=False)
        if not held:
            return   # another speaker is running and will read this announcement too
        with held:
            while True:
                item = dequeue()
                if not item:
                    break
                lang = item.get("lang") if item.get("lang") in LANGUAGES else language(config)
                if lang not in voices:
                    voices[lang] = chosen_voice(lang, config)
                say(item["text"], voices[lang], lang)
        if not (QUEUE.exists() and QUEUE.stat().st_size):
            return


# --- what to say ---------------------------------------------------------------------------------------------

SUMMARY_MARK = re.compile(r"(?m)^[ \t>*_-]*🔊️?[ \t:]*")


def spoken_summary(text, limit=420):
    """From the last line that STARTS with 🔊 to the end of the reply, without markdown or links. "" if none."""
    marks = list(SUMMARY_MARK.finditer(text or ""))
    if not marks:
        return ""
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text[marks[-1].end():])   # [label](url) -> label
    t = " ".join(re.sub(r"https?://\S+|[`*_#>|]", " ", t).split())
    t = re.sub(r" ([,.;:!?])", r"\1", t)
    if len(t) <= limit:
        return t
    return t[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "."


def spoken_name(folder):
    """The project as you would say it: the repository (a worktree counts as its main repo), else the folder."""
    path = Path(folder)
    if path.is_dir():
        common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=str(path)).stdout.strip()
        if common.endswith(".git"):
            path = Path(common).parent
    return " ".join(re.sub(r"[-_.]+", " ", path.name).split()) or "Claude"


def desktop_session_folder():
    """Folder the session started in, from the Claude desktop app's own session record (macOS).

    This file is internal to the app and has no contract: if it moves or changes, the other sources take over.
    """
    sid = os.environ.get("CLAUDE_CODE_HOST_SESSION_ID")
    base = Path.home() / "Library" / "Application Support" / "Claude" / "claude-code-sessions"
    for f in (base.glob(f"*/*/{sid}.json") if sid and re.fullmatch(r"[\w-]+", sid) else []):
        try:
            return json.loads(f.read_text(encoding="utf-8")).get("originCwd") or ""
        except (ValueError, OSError, AttributeError):
            pass
    return ""


def session_folder(payload):
    """Where the session started. A `cd` in a Bash call moves the hook's `cwd`, so stable sources come first."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or desktop_session_folder() or payload.get("cwd") or os.getcwd()


def announcement(event, payload, project, lang, rng=random):
    """The sentence to speak for a hook event, or None to stay quiet."""
    p = PHRASES[lang]
    if event == "Stop":
        summary = spoken_summary(payload.get("last_assistant_message"))
        if summary:
            return f"{rng.choice(p['done_summary']).format(p=project)} {summary}"
        return rng.choice(p["done"]).format(p=project)
    if event == "Notification":
        kind = payload.get("notification_type") or payload.get("message") or ""
        if "permission" in kind.lower():
            return rng.choice(p["approval"]).format(p=project)
        if re.search(r"elicitation|question", kind, re.I):
            return rng.choice(p["question"]).format(p=project)
    return None   # idle reminders and anything new stay quiet; the log shows them


def write_log(line):
    with lock("queue.lock"):   # two hooks at once must not drop each other's line
        lines = LOG.read_text(encoding="utf-8").splitlines()[-(LOG_LINES - 1):] if LOG.exists() else []
        LOG.write_text("\n".join(lines + [line]) + "\n", encoding="utf-8")


def hook(stdin_text):
    """Hook entry point. Returns what to print (only UserPromptSubmit prints). Never raises: a failing hook
    shows up in the session, and a notification is not worth that."""
    try:
        payload = json.loads(stdin_text or "{}")
        if not ENABLED.exists() or payload.get("stop_hook_active") \
                or os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").startswith("sdk"):   # claude -p and the SDK stay quiet
            return ""
        config = load_config()
        if not can_speak(config):   # no engine and no program: no instruction either, so no tokens are spent
            return ""
        lang = language(config)
        event = payload.get("hook_event_name", "")
        if event == "UserPromptSubmit":
            # ASCII-only JSON: the 🔊 travels as an escape, safe on any console encoding
            return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": INSTRUCTION[lang]}})
        project = spoken_name(session_folder(payload))
        text = announcement(event, payload, project, lang)
        kind = payload.get("notification_type") or ""
        write_log(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {event} [{kind}] {project}: {text or '(quiet)'}")
        if text:
            enqueue(text, lang)
    except Exception:
        pass
    return ""


# --- /voice-notify -------------------------------------------------------------------------------------------

NO_ENGINE = {
    "linux": "No speech engine found. Install speech-dispatcher (spd-say) or espeak-ng, or set your own program "
             "with /voice-notify command <program>.",
    "windows": "Windows PowerShell (powershell.exe) was not found. Set your own program with "
               "/voice-notify command <program>.",
}


def engine_line(config):
    if config.get("command"):
        return f"speaks with: your program `{config['command']}` (falls back to {system_engine() or 'nothing'})"
    return f"speaks with: {system_engine() or 'nothing'}"


def status():
    config = load_config()
    lang = language(config)
    out = [f"voice notifications: {'ON' if ENABLED.exists() else 'off'}",
           f"language: {lang}" + ("" if config.get("language") in LANGUAGES else " (auto, from the system)"),
           f"voice: {config.get('voice') or (chosen_voice(lang, config) or 'engine default') + ' (auto)'}",
           engine_line(config)]
    if not can_speak(config):
        out.append(NO_ENGINE.get(system(), "Nothing can speak here. Set a program with /voice-notify command <program>."))
    if QUEUE.exists() and QUEUE.stat().st_size:
        out.append(f"queued: {len(QUEUE.read_text(encoding='utf-8').splitlines())}")
    if LOG.exists():
        out.append("last events:\n  " + "\n  ".join(LOG.read_text(encoding="utf-8").splitlines()[-5:]))
    return "\n".join(out)


def list_voices():
    config = load_config()
    lang = language(config)
    engine = system_engine()
    if engine in ("spd-say", "espeak-ng"):
        listing = run(["spd-say", "-L"] if engine == "spd-say" else ["espeak-ng", f"--voices={lang.split('-')[0]}"])
        return "\n".join([f"{engine} voices (the engine picks one for {lang} unless you choose):",
                          listing.stdout.rstrip() or "  (none listed)", "",
                          "Pick one with: /voice-notify voice <name>   (or /voice-notify voice auto)"])
    voices = sorted((v for v in installed_voices() if v[2].lower().startswith(lang.lower())),
                    key=lambda v: voice_rank(v, lang), reverse=True)
    current = chosen_voice(lang, config)
    rows = [f"{'*' if v[0] == current else ' '} {v[0]}  ({v[1]}, {v[2]}, {QUALITY.get(v[3], v[3])})" for v in voices]
    more = {"avspeech": "More voices: System Settings > Accessibility > Spoken Content > System voice > Manage Voices.",
            "sapi": "More voices: Settings > Time & language > Speech > Manage voices > Add voices."}.get(engine, "")
    return "\n".join([f"voices for {lang} (* = in use):"] + (rows or ["  none found"]) + [
        "", more, "Pick one with: /voice-notify voice <identifier>   (or /voice-notify voice auto)"]).replace("\n\n\n", "\n\n")


def join_args(args):
    """Rebuilds a command line from the words the shell split, quoting for the shell that will run it."""
    return subprocess.list2cmdline(args) if system() == "windows" else " ".join(shlex.quote(a) for a in args)


USAGE = ("usage: /voice-notify [on [voice] | off | test | voices | status | lang <en|pt-BR|auto> | "
         "voice <name|auto> | command <program...|off>]")


def command(args):
    """The /voice-notify command. Returns the text the command shows."""
    action, rest = (args[0].lower(), args[1:]) if args else ("status", [])
    if action == "on":
        STATE.mkdir(parents=True, exist_ok=True)
        if rest:
            save_config(voice=" ".join(rest))
        ENABLED.write_text("", encoding="utf-8")
        if not can_speak():
            return status()
        lang = language()
        enqueue(PHRASES[lang]["on"], lang)
        return status() + "\n\nApplies from your next message, in every open session."
    if action == "off":
        ENABLED.unlink(missing_ok=True)
        return status()
    if action == "test":
        if not can_speak():
            return status()
        lang = language()
        enqueue(f"{random.choice(PHRASES[lang]['done_summary']).format(p=spoken_name(session_folder({})))} "
                f"{PHRASES[lang]['test']}", lang)
        return "Speaking a test announcement" + ("." if ENABLED.exists() else " (notifications are off: /voice-notify on).")
    if action == "voices":
        return list_voices()
    if action == "lang" and rest and (rest[0] in LANGUAGES or rest[0] == "auto"):
        save_config(language=rest[0])
        return status()
    if action == "voice" and rest:
        save_config(voice="" if rest == ["auto"] else " ".join(rest))
        return status()
    if action == "command" and rest:
        save_config(command="" if rest == ["off"] else join_args(rest))
        return status()
    if action == "status":
        return status()
    return USAGE


def main(argv):
    if argv[:1] == ["hook"]:
        # Read bytes: the hook input is UTF-8 whatever the console encoding (Windows uses a code page)
        out = hook(sys.stdin.buffer.read().decode("utf-8", "replace"))
        if out:
            print(out)
    elif argv[:1] == ["--speak-queue"]:
        speak_queue()
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        print(command(argv))


if __name__ == "__main__":
    main(sys.argv[1:])
