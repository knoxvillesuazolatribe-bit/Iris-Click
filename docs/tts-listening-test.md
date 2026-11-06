# IrisClick: text-to-speech listening test

Compares the **old** voice with the **new natural voice** on the presentation PC.
Do it as a team; each tester rates every sentence on their own.

## Setup

- [ ] Presentation PC, laptop speakers, normal volume (Voice volume 100 in Settings, Windows volume about 60%).
- [ ] Quiet room. Testers sit where an audience member would.
- [ ] Sign in as a test user. Open **Voice Communication**.
- [ ] **OLD voice:** make the natural voice unavailable on purpose by unplugging the network
      *and* using phrases that were never spoken before. The chip under the message must say
      **"Basic voice (offline)"**. (Do NOT change any code or `.env` for this.)
- [ ] **NEW voice:** network on. The chip must say **"Natural voice"**.
- [ ] Default voice settings (Settings → Voice → Reset voice to default): English Rosa,
      Filipino Blessica, Speed Normal (−10%), Pitch Normal.

Play each sentence with the OLD voice, then with the NEW voice. Do not say which is which
(one person operates the PC with their back to the testers).

## Rating: clarity 1–5

1 = could not understand · 2 = understood with effort · 3 = understood, sounds robotic ·
4 = clear and fairly natural · 5 = clear and natural, like a person

## English (language switch: ENGLISH)

| # | Sentence | Old | New |
|---|----------|-----|-----|
| 1 | I need help | | |
| 2 | Yes | | |
| 3 | No | | |
| 4 | Thank you | | |
| 5 | I'm hungry | | |
| 6 | I need water | | |
| 7 | Please call my caregiver | | |
| 8 | Please call Dr. Santos at 0917 808 2488. | | |
| 9 | My medicine is at 3:30 PM, 2 tablets with water. | | |
| 10 | Ana lives on Rizal St., Brgy. Pusok, Lapu-Lapu City. | | |

## Filipino (language switch: FILIPINO)

| # | Sentence | Old | New |
|---|----------|-----|-----|
| 1 | Tulungan mo ako | | |
| 2 | Oo | | |
| 3 | Hindi | | |
| 4 | Salamat | | |
| 5 | Gutom na ako | | |
| 6 | Gusto ko ng tubig | | |
| 7 | Pakitawag ang aking tagapag-alaga | | |
| 8 | Pakitawagan si Dr. Reyes sa 0917 808 2488. | | |
| 9 | Iinom ako ng 2 tableta sa 3:30 PM. | | |
| 10 | Nakatira si Ana sa Brgy. Pusok, Lapu-Lapu City. | | |

## Results

| Tester | English old avg | English new avg | Filipino old avg | Filipino new avg |
|--------|-----------------|-----------------|------------------|------------------|
| | | | | |
| | | | | |
| | | | | |
| **Average** | | | | |

Notes (words that were hard to understand, too fast/slow, too loud/quiet):

## Offline check

- [ ] With the network on, open Voice Communication and wait 30 seconds (Quick Phrases are
      prepared in both languages in the background).
- [ ] Unplug the network.
- [ ] Press each Quick Phrase in ENGLISH and in FILIPINO: each still plays with the chip
      **"Natural voice"** (from the saved audio).
- [ ] Type a new sentence and press Speak: it plays with **"Basic voice (offline)"**, or shows
      "Voice is unavailable right now" with the text still on screen. It must never be silent
      without a message.
- [ ] Plug the network back in.

## Controls check

- [ ] Speak a long message, press **Speak** again mid-way: the first stops, no two voices at once.
- [ ] **Stop** silences it immediately. **Replay** says the last message again.
- [ ] "Speaking…" shows while it talks, with the current word highlighted (natural voice).
- [ ] A message containing a blocked word says "beep" (or skips it), never the word itself.
