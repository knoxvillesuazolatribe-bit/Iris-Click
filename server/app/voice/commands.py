"""Valid-data identification for spoken input.

Every recognised phrase is sorted into exactly one kind before anything happens:

  NAVIGATE   "go to facebook", "open youtube": a known site, saved shortcut or app
  ACTION     "start typing", "send", "clear", "new line", "stop typing"
  DICTATION  any other clear speech while typing is on: text to type
  INVALID    empty, unsure, unknown site, no letters, or not a command: nothing happens

Only NAVIGATE and ACTION outside typing mode change anything on the computer, and
a NAVIGATE target is always re-checked (http/https website or a fixed app key), so
misheard speech can never open an arbitrary address or program.
"""

import re
import unicodedata
from dataclasses import dataclass

NAVIGATE, ACTION, DICTATION, INVALID = "navigate", "action", "dictation", "invalid"
START_TYPING, STOP_TYPING, SEND, CLEAR, NEW_LINE = "start_typing", "stop_typing", "send", "clear", "new_line"

# The recogniser's own confidence (0 to 1); below this the phrase is rejected, not guessed.
MIN_CONFIDENCE = 0.35
MAX_DICTATION_CHARS = 500

NAV_PREFIXES = ("go to", "open", "launch", "visit", "navigate to", "take me to", "show me", "start")
NAV_PREFIX = re.compile(r"^(?:please\s+)?(?:" + "|".join(re.escape(p) for p in NAV_PREFIXES) + r")\s+(?P<name>.+)$")
FILLER = re.compile(r"^(?:the|my)\s+|\s+(?:please|now|website|site|page|app|dot com)$")

ACTIONS_ANY_MODE = {
    "start typing": START_TYPING, "type message": START_TYPING, "type a message": START_TYPING,
    "start dictation": START_TYPING, "voice typing": START_TYPING,
}
ACTIONS_TYPING = {
    "send": SEND, "send message": SEND, "send it": SEND, "press enter": SEND, "enter": SEND,
    "clear": CLEAR, "clear all": CLEAR, "clear message": CLEAR, "clear text": CLEAR,
    "new line": NEW_LINE, "next line": NEW_LINE,
    "stop typing": STOP_TYPING, "stop dictation": STOP_TYPING, "stop voice typing": STOP_TYPING,
    "done typing": STOP_TYPING,
}


@dataclass(frozen=True)
class Classified:
    kind: str
    action: str | None = None     # START_TYPING, SEND, ... for ACTION
    name: str | None = None       # what the user asked for, for NAVIGATE
    text: str | None = None       # what to type, for DICTATION
    reason: str = ""              # short, user-facing: shown on screen

    @property
    def valid(self) -> bool:
        return self.kind != INVALID


def normalize(text: str | None) -> str:
    """Lowercase, accents and punctuation removed, single spaces: 'Go to Facebook!' -> 'go to facebook'."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[^\w\s.]", " ", text).replace("_", " ")
    text = re.sub(r"(?<!\w)\.|\.(?!\w)", " ", text)  # keep "facebook.com", drop sentence dots
    return " ".join(text.split())


def target_name(phrase: str) -> str:
    """'go to the facebook website please' -> 'facebook'."""
    name = phrase
    for _ in range(3):
        stripped = FILLER.sub("", name).strip()
        if stripped == name:
            break
        name = stripped
    return name


def clean_dictation(text: str | None) -> str:
    """Spoken text as it will be typed: single spaces, no control characters, capped."""
    text = "".join(ch for ch in (text or "") if ch == " " or unicodedata.category(ch)[0] != "C")
    return " ".join(text.split())[:MAX_DICTATION_CHARS]


def classify(text: str | None, confidence: float = 1.0, typing: bool = False,
             known_names: frozenset[str] | set[str] = frozenset()) -> Classified:
    """Sorts one recognised phrase. ``known_names`` are the normalised names "Go to" accepts."""
    phrase = normalize(text)
    if not phrase:
        return Classified(INVALID, reason="No speech heard")
    if confidence < MIN_CONFIDENCE:
        return Classified(INVALID, reason="Not sure what you said, please say it again")

    if typing and phrase in ACTIONS_TYPING:
        return Classified(ACTION, action=ACTIONS_TYPING[phrase], reason=_action_label(ACTIONS_TYPING[phrase]))
    if phrase in ACTIONS_ANY_MODE:
        if typing:
            return Classified(INVALID, reason="Voice typing is already on")
        return Classified(ACTION, action=START_TYPING, reason=_action_label(START_TYPING))

    if typing:
        typed = clean_dictation(text)
        if not re.search(r"\w", typed):
            return Classified(INVALID, reason="Nothing to type")
        return Classified(DICTATION, text=typed, reason=f'Typed "{typed}"')

    match = NAV_PREFIX.match(phrase)
    if match:
        spoken = match.group("name")
        name = spoken if spoken in known_names else target_name(spoken)  # "my school" stays a name
        if name in known_names:
            return Classified(NAVIGATE, name=name, reason=f"Opening {name.title()}")
        return Classified(INVALID, name=name, reason=f'No website or app called "{name}"')
    if phrase in ACTIONS_TYPING:
        return Classified(INVALID, reason='Say "Start typing" first')
    return Classified(INVALID, reason="Unrecognized command")


def _action_label(action: str) -> str:
    return {START_TYPING: "Voice typing on: speak your message", STOP_TYPING: "Voice typing off",
            SEND: "Sent (Enter)", CLEAR: "Message cleared", NEW_LINE: "New line"}[action]


def command_phrases(known_names: set[str] | frozenset[str]) -> list[str]:
    """Every exact phrase the command grammar listens for (helps the recogniser hear them)."""
    phrases = set(ACTIONS_ANY_MODE) | set(ACTIONS_TYPING)
    for name in known_names:
        phrases.update(f"{prefix} {name}" for prefix in ("go to", "open", "launch", "visit"))
    return sorted(phrases)
