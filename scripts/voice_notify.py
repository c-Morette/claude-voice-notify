#!/usr/bin/env python3
"""claude-voice-notify: spoken notifications for Claude Code on macOS.

One file, standard library only, Python 3.9+. Claude Code runs it as a hook:

  UserPromptSubmit  (sync)   asks Claude to end its reply with one "🔊 ..." summary line
  Stop              (async)  queues "<repo> is done." plus that summary
  Notification      (async)  queues "<repo> needs you." when a permission prompt or question waits

and the /voice-notify command runs it with on, off, test, voices, status, lang or voice.
Everything stays on this machine: no network, no API calls, no extra model.
"""
import datetime
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

STATE = Path(os.environ.get("CLAUDE_VOICE_NOTIFY_HOME") or Path.home() / ".claude" / "voice-notify")
ENABLED = STATE / "enabled"      # exists = speak
CONFIG = STATE / "config.json"   # {"language": "auto" | "en" | "pt-BR", "voice": "" (auto) | identifier | say name}
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

# AVSpeech through JavaScript for Automation reaches the Siri and premium voices; `say` does not.
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


def is_mac():
    return sys.platform == "darwin"


def run(cmd, cwd=None, timeout=10):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
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


def system_language():
    """The macOS interface language (AppleLanguages), then the POSIX locale. Empty if neither says."""
    if is_mac():
        m = re.search(r'\(\s*"?([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*)', run(["defaults", "read", "-g", "AppleLanguages"]).stdout)
        if m:
            return m.group(1)
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(var, "") not in ("", "C", "POSIX"):
            return os.environ[var]
    return ""


def language(config=None):
    lang = (config if config is not None else load_config()).get("language") or "auto"
    if lang in LANGUAGES:
        return lang
    return "pt-BR" if system_language().lower().startswith("pt") else "en"


# --- voices --------------------------------------------------------------------------------------------------

def installed_voices():
    """[(identifier, name, language, quality)] from AVSpeech. Empty off macOS or if osascript fails."""
    voices = []
    for line in run(["osascript", "-l", "JavaScript", "-e", VOICES_JS]).stdout.splitlines():
        f = line.split("\t")
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
    """The configured voice, or the best installed one for the language ("" lets macOS pick)."""
    v = (config if config is not None else load_config()).get("voice") or ""
    if v:
        return v
    best = best_voice(lang, installed_voices())
    return best[0] if best else ""


def speak(text, voice, lang):
    """A dotted identifier goes through AVSpeech (reaches Siri), a short name through `say -v`. Blocks until done."""
    if voice and "." not in voice:
        r = run(["say", "-v", voice, text], timeout=180)
    else:
        r = run(["osascript", "-l", "JavaScript", "-e", SPEAK_JS, voice or "", lang, text], timeout=180)
    if r.returncode:
        run(["say", text], timeout=180)


# --- queue ---------------------------------------------------------------------------------------------------
# An async hook still has a timeout, and a long summary or two sessions finishing together can outlast it.
# So the hook only appends to a queue and starts a detached speaker; one speaker at a time reads it in order.

def lock(name, wait=True):
    """flock on a file in STATE. Returns the open file (closing it releases) or None if busy and wait=False."""
    import fcntl   # macOS/Linux only; callers checked is_mac()
    STATE.mkdir(parents=True, exist_ok=True)
    f = open(STATE / name, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        return f
    except OSError:
        f.close()
        return None


def enqueue(text, lang, spawn=True):
    with lock("queue.lock"):
        with open(QUEUE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"text": text, "lang": lang}, ensure_ascii=False) + "\n")
    if spawn:
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--speak-queue"], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
    say = say or speak
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
    """Folder the session started in, from the Claude desktop app's own session record.

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
        if not is_mac() or not ENABLED.exists() or payload.get("stop_hook_active") \
                or os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").startswith("sdk"):   # claude -p and the SDK stay quiet
            return ""
        config = load_config()
        lang = language(config)
        event = payload.get("hook_event_name", "")
        if event == "UserPromptSubmit":
            return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": INSTRUCTION[lang]}},
                              ensure_ascii=False)
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

def status():
    config = load_config()
    lang = language(config)
    out = [f"voice notifications: {'ON' if ENABLED.exists() else 'off'}",
           f"language: {lang}" + ("" if config.get("language") in LANGUAGES else " (auto, from the system)"),
           f"voice: {config.get('voice') or (chosen_voice(lang, config) or 'system default') + ' (auto)'}"]
    if QUEUE.exists() and QUEUE.stat().st_size:
        out.append(f"queued: {len(QUEUE.read_text(encoding='utf-8').splitlines())}")
    if LOG.exists():
        out.append("last events:\n  " + "\n  ".join(LOG.read_text(encoding="utf-8").splitlines()[-5:]))
    return "\n".join(out)


def list_voices():
    config = load_config()
    lang = language(config)
    voices = sorted((v for v in installed_voices() if v[2].lower().startswith(lang.lower())),
                    key=lambda v: voice_rank(v, lang), reverse=True)
    current = chosen_voice(lang, config)
    rows = [f"{'*' if v[0] == current else ' '} {v[0]}  ({v[1]}, {v[2]}, {QUALITY.get(v[3], v[3])})" for v in voices]
    return "\n".join([f"voices for {lang} (* = in use):"] + (rows or ["  none installed"]) + [
        "",
        "More voices: System Settings > Accessibility > Spoken Content > System voice > Manage Voices.",
        "Pick one with: /voice-notify voice <identifier>   (or /voice-notify voice auto)"])


USAGE = """usage: /voice-notify [on [voice] | off | test | voices | status | lang <en|pt-BR|auto> | voice <identifier|auto>]"""


def command(args):
    """The /voice-notify command. Returns the text the command shows."""
    if not is_mac():
        return ("claude-voice-notify speaks through the macOS speech engine, so v0.1 works on macOS only. "
                "On this system the hooks do nothing.")
    action, rest = (args[0].lower(), args[1:]) if args else ("status", [])
    if action == "on":
        STATE.mkdir(parents=True, exist_ok=True)
        if rest:
            save_config(voice=rest[0])
        ENABLED.write_text("", encoding="utf-8")
        lang = language()
        enqueue(PHRASES[lang]["on"], lang)
        return status() + "\n\nApplies from your next message, in every open session."
    if action == "off":
        ENABLED.unlink(missing_ok=True)
        return status()
    if action == "test":
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
        save_config(voice="" if rest[0] == "auto" else rest[0])
        return status()
    if action == "status":
        return status()
    return USAGE


def main(argv):
    if argv[:1] == ["hook"]:
        out = hook(sys.stdin.read())
        if out:
            print(out)
    elif argv[:1] == ["--speak-queue"]:
        if is_mac():
            speak_queue()
    else:
        print(command(argv))


if __name__ == "__main__":
    main(sys.argv[1:])
