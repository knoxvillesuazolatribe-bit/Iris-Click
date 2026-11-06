"""Text clean-up before the natural voice reads it (English and Filipino)."""

import pytest

from app.services.tts_text_prep import en_number, fil_number, prepare


@pytest.mark.parametrize("n, words", [(0, "zero"), (7, "seven"), (15, "fifteen"), (21, "twenty-one"),
                                      (100, "one hundred"), (305, "three hundred five"),
                                      (1500, "one thousand five hundred"), (2024, "two thousand twenty-four")])
def test_english_numbers(n, words):
    assert en_number(n) == words


@pytest.mark.parametrize("n, words", [(1, "isa"), (3, "tatlo"), (10, "sampu"), (14, "labing-apat"),
                                      (21, "dalawampu't isa"), (40, "apatnapu"), (100, "isang daan"),
                                      (400, "apat na raan"), (105, "isang daan at lima"),
                                      (1000, "isang libo"), (2024, "dalawang libo at dalawampu't apat")])
def test_filipino_numbers(n, words):
    assert fil_number(n) == words


@pytest.mark.parametrize("language, text, spoken", [
    ("en", "I need 3 pills", "I need three pills"),
    ("fil", "Kailangan ko ng 3 tableta", "Kailangan ko ng tatlong tableta"),
    ("fil", "4 na baso at 2 tableta", "apat na baso at dalawang tableta"),
    ("en", "It is 1,500 steps", "It is one thousand five hundred steps"),
    ("en", "at 3:30 PM", "at three thirty P M"),
    ("en", "at 12:05 AM", "at twelve oh five A M"),
    ("en", "at 7:00 PM", "at seven P M"),
    ("fil", "sa 3:30 PM", "sa alas tres y medya ng hapon"),
    ("fil", "sa 7:00 AM", "sa alas siyete ng umaga"),
    ("fil", "sa 10:15 PM", "sa alas diyes at labing-limang minuto ng gabi"),
    ("en", "costs ₱250", "costs two hundred fifty pesos"),
    ("fil", "₱20 lang", "dalawampung piso lang"),
    ("en", "45% done", "forty-five percent done"),
    ("en", "Call 0917 808 2488", "Call zero nine one seven eight zero eight two four eight eight"),
    ("en", "Dr. Cruz on Rizal St. pls", "Doctor Cruz on Rizal Street please"),
    ("fil", "si Dr. Reyes sa Brgy. Pusok", "si Doktor Reyes sa Barangay Pusok"),
    ("en", "thx w/ love & care", "thanks with love and care"),
    ("en", "Help!!! Now???", "Help! Now?"),
    ("en", "Wait...ok", "Wait. ok"),
    ("en", "I am happy 😀👍", "I am happy"),
    ("fil", "Salamat po\nMahal kita", "Salamat po. Mahal kita"),
    ("en", "2.5 km and room 1st", "2.5 km and room 1st"),  # decimals and ordinals left to the voice
    ("en", "", ""),
])
def test_prepare(language, text, spoken):
    assert prepare(text, language) == spoken
