"""Text clean-up before the natural voice reads it (clearer TTS).

English ("en") and Filipino ("fil"):
- numbers as words where it helps ("3" → "three" / "tatlo"), "1,500" too;
  long digit strings (phone numbers) are read digit by digit;
- times ("3:30 PM" → "three thirty P M" / "alas tres y medya ng hapon");
- pesos ("₱50" → "fifty pesos" / "limampung piso");
- common abbreviations ("Dr." → "Doctor", "St." → "Street", "pls" → "please",
  "Brgy." → "Barangay");
- emojis removed, repeated punctuation collapsed ("!!!" → "!"), a missing
  space after a sentence added, and a line break becomes a sentence break so
  the voice pauses there.

Only what is read aloud changes; the message on screen and in history stays as typed.
"""

import re

# --- Numbers: English -----------------------------------------------------------------------

_EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
            "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
            "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _en_under_1000(n: int) -> str:
    words = []
    if n >= 100:
        words.append(f"{_EN_ONES[n // 100]} hundred")
        n %= 100
    if n >= 20:
        words.append(_EN_TENS[n // 10] + (f"-{_EN_ONES[n % 10]}" if n % 10 else ""))
    elif n or not words:
        words.append(_EN_ONES[n])
    return " ".join(words)


def en_number(n: int) -> str:
    if n < 1000:
        return _en_under_1000(n)
    thousands, rest = divmod(n, 1000)
    return f"{_en_under_1000(thousands)} thousand" + (f" {_en_under_1000(rest)}" if rest else "")


# --- Numbers: Filipino (Tagalog) ------------------------------------------------------------

_FIL_ONES = ["sero", "isa", "dalawa", "tatlo", "apat", "lima", "anim", "pito", "walo", "siyam"]
_FIL_TENS = {2: "dalawampu", 3: "tatlumpu", 4: "apatnapu", 5: "limampu", 6: "animnapu", 7: "pitumpu",
             8: "walumpu", 9: "siyamnapu"}


def _linked(word: str, noun: str) -> str:
    """"isang daan", "apat na raan": -ng after a vowel, "na" after a consonant."""
    if word[-1] in "aeiou":
        return f"{word}ng {noun}"
    return f"{word} na {'raan' if noun == 'daan' else noun}"


def _fil_under_100(n: int) -> str:
    if n < 10:
        return _FIL_ONES[n]
    if n == 10:
        return "sampu"
    if n < 20:
        return f"labing-{_FIL_ONES[n - 10]}"
    tens, ones = divmod(n, 10)
    return _FIL_TENS[tens] + (f"'t {_FIL_ONES[ones]}" if ones else "")


def fil_number(n: int) -> str:
    if n < 100:
        return _fil_under_100(n)
    parts = []
    thousands, n = divmod(n, 1000)
    hundreds, rest = divmod(n, 100)
    if thousands:
        parts.append(_linked(fil_number(thousands), "libo"))
    if hundreds:
        parts.append(_linked(_FIL_ONES[hundreds], "daan"))
    if rest:
        parts.append(f"at {_fil_under_100(rest)}")
    return " ".join(parts)


def number_words(n: int, language: str) -> str:
    return fil_number(n) if language == "fil" else en_number(n)


def _peso_words(n: int, language: str) -> str:
    if language == "fil":
        return _linked(fil_number(n), "piso") if n != 1 else "isang piso"
    return f"{en_number(n)} {'peso' if n == 1 else 'pesos'}"


# --- Times ------------------------------------------------------------------------------------

_SPANISH_HOURS = ["dose", "una", "dos", "tres", "kwatro", "singko", "sais", "siyete", "otso", "nuwebe",
                  "diyes", "onse", "dose"]
TIME = re.compile(r"\b(\d{1,2}):([0-5]\d)(?:\s*([AaPp])\.?\s*[Mm]\b\.?)?")


def _time_words(hour: int, minute: int, half: str | None, language: str) -> str:
    if language == "fil":
        if half is None:
            period = "ng umaga" if hour < 12 else "ng hapon" if hour < 18 else "ng gabi"
        elif half == "a":
            period = "ng hatinggabi" if hour == 12 else "ng madaling-araw" if hour < 5 else "ng umaga"
        else:
            period = "ng tanghali" if hour == 12 else "ng hapon" if hour < 6 else "ng gabi"
        spoken = f"alas {_SPANISH_HOURS[hour % 12]}"
        if minute == 30:
            spoken += " y medya"
        elif minute:
            spoken += f" at {_linked(fil_number(minute), 'minuto')}"
        return f"{spoken} {period}"
    shown = hour % 12 or 12 if half else hour
    words = en_number(shown)
    if minute == 0:
        words += " o'clock" if not half else ""
    elif minute < 10:
        words += f" oh {en_number(minute)}"
    else:
        words += f" {en_number(minute)}"
    return f"{words} {'A M' if half == 'a' else 'P M'}" if half else words


def _times(text: str, language: str) -> str:
    def replace(m: re.Match) -> str:
        hour, minute = int(m.group(1)), int(m.group(2))
        if hour > 23 or (m.group(3) and not 1 <= hour <= 12):
            return m.group(0)
        return _time_words(hour, minute, m.group(3).lower() if m.group(3) else None, language)
    return TIME.sub(replace, text)


# --- Abbreviations ----------------------------------------------------------------------------

_COMMON = [  # (pattern, English, Filipino); matched case-insensitively unless noted
    (r"\bBrgy\.?(?=\s)", "Barangay", "Barangay"),
    (r"\bDr\.(?=\s)", "Doctor", "Doktor"),
    (r"\bMr\.(?=\s)", "Mister", "Mister"),
    (r"\bMrs\.(?=\s)", "Missus", "Missus"),
    (r"\bMs\.(?=\s)", "Miz", "Miz"),
    (r"\bSt\.(?=\s)", "Street", "Street"),
    (r"\bAve\.(?=\s)", "Avenue", "Avenue"),
    (r"\bRd\.(?=\s)", "Road", "Road"),
    (r"\bJr\.(?=\s|$)", "Junior", "Junior"),
    (r"\bSr\.(?=\s|$)", "Senior", "Senior"),
    (r"\bGng\.(?=\s)", "Missus", "Ginang"),
    (r"\bBb\.(?=\s)", "Miss", "Binibini"),
    (r"\bapprox\.(?=\s)", "approximately", "humigit-kumulang"),
    (r"\be\.g\.(?=\s|,)", "for example", "halimbawa"),
    (r"\betc\.(?=\s|$)", "et cetera", "at iba pa"),
    (r"\bpls\b|\bplz\b|\bpls\.", "please", "please"),
    (r"\bthx\b|\bthnx\b", "thanks", "salamat"),
    (r"\bw/(?=\s)", "with", "kasama ang"),
    (r"\s&\s", " and ", " at "),
]


def _abbreviations(text: str, language: str) -> str:
    for pattern, en, fil in _COMMON:
        text = re.sub(pattern, fil if language == "fil" else en, text, flags=re.IGNORECASE)
    return text


# --- Numbers in text --------------------------------------------------------------------------

PESO = re.compile(r"(?:₱|\bPHP\s?|\bP(?=\d))\s?(\d{1,3}(?:,\d{3})+|\d+)\b", re.IGNORECASE)
PERCENT = re.compile(r"\b(\d{1,3})\s?%")
GROUPED = re.compile(r"(?<![\d.])\b(\d{1,3}(?:,\d{3})+)\b(?![.,]\d)")
LONG_DIGITS = re.compile(r"(?<![\d.])\+?\d[\d -]{5,}\d(?![\d.])")
PLAIN = re.compile(r"(?<![\d.,:/])\b([1-9]\d{0,5}|0)\b(?![.,:/]\d)")


def _numbers(text: str, language: str) -> str:
    text = PESO.sub(lambda m: _peso_words(int(m.group(1).replace(",", "")), language)
                    if int(m.group(1).replace(",", "")) < 1_000_000 else m.group(0), text)
    text = PERCENT.sub(lambda m: f"{number_words(int(m.group(1)), language)} "
                       f"{'porsiyento' if language == 'fil' else 'percent'}", text)

    def digits(m: re.Match) -> str:  # phone numbers and IDs: digit by digit
        raw = m.group(0)
        plus = "plus " if raw.startswith("+") and language != "fil" else ""
        return plus + " ".join(ch for ch in raw if ch.isdigit())
    text = LONG_DIGITS.sub(digits, text)
    text = GROUPED.sub(lambda m: number_words(int(m.group(1).replace(",", "")), language)
                       if int(m.group(1).replace(",", "")) < 1_000_000 else m.group(0), text)
    if language != "fil":
        return PLAIN.sub(lambda m: en_number(int(m.group(1))), text)

    def fil(m: re.Match) -> str:
        words = fil_number(int(m.group(1)))
        after = text[m.end():]
        # Before a noun Filipino links the number: "tatlong tableta", "apat na tableta".
        if re.match(r"\s+[^\W\d_]", after) and not re.match(r"\s+(na|ng|at|o|y)\b", after, re.IGNORECASE):
            return f"{words}ng" if words[-1] in "aeiou" else f"{words} na"
        return words
    return PLAIN.sub(fil, text)


# --- Emojis and punctuation -------------------------------------------------------------------

EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF‍️⃣]")


def _punctuation(text: str) -> str:
    text = EMOJI.sub("", text)
    text = re.sub(r"[ \t]*\n+[ \t]*", lambda m: "\n", text.strip())
    text = re.sub(r"(?<![.?!,;:])\n", ". ", text).replace("\n", " ")
    text = re.sub(r"([?!])[?!]+", r"\1", text)     # "?!?!" / "!!!" → one mark
    text = re.sub(r"\.{2,}\s*", ". ", text)          # "..." is a pause: "Hello...how" → "Hello. how"
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r"\s+([.,?!])", r"\1", text)       # "hello ." → "hello."
    text = re.sub(r"([.?!])(?=[A-Z])", r"\1 ", text)  # "Hi.How" → "Hi. How"
    text = re.sub(r";", ",", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def prepare(text: str, language: str = "en") -> str:
    language = "fil" if language == "fil" else "en"
    text = _punctuation(text or "")
    text = _abbreviations(text, language)
    text = _times(text, language)
    text = _numbers(text, language)
    return re.sub(r"\s{2,}", " ", text).strip()
