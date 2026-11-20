"""Rules for validation/term_set_en_v1.txt and how scripts/term_bench.py finds a term."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import term_bench as tb  # noqa: E402

HINTS, ITEMS = tb.load_set()


def test_items_are_well_formed():
    ids = [it["id"] for it in ITEMS]
    assert len(ids) == len(set(ids)) and len(ITEMS) >= 40
    assert {it["split"] for it in ITEMS} == {"tune", "check"}
    for it in ITEMS:
        assert it["topic"] and it["targets"], it["id"]
        assert "[[" not in it["reference"] and "]]" not in it["reference"], it["id"]


@pytest.mark.parametrize("item", ITEMS, ids=lambda it: it["id"])
def test_each_term_is_said_once_in_its_item(item):
    words = tb.tokens(item["reference"])
    for term in item["targets"]:
        want = tb.tokens(term)
        count = sum(words[i:i + len(want)] == want for i in range(len(words)))
        assert count == 1, (item["id"], term, count)


def test_every_pronunciation_hint_is_used():
    text = " " + " ".join(" ".join(tb.tokens(it["reference"])) for it in ITEMS) + " "
    unused = [t for t in HINTS if " " + " ".join(tb.tokens(t)) + " " not in text]
    assert not unused


@pytest.mark.parametrize("term, text", [
    ("Reynolds' pentad", "this becomes Reynold's pentad."),
    ("Homans' sign", "but Homans sign is unreliable"),
    ("Guillain-Barré syndrome", "admitted with Guillain Barre syndrome after"),
    ("Sjögren's syndrome", "suggest Sjogren's syndrome."),
    ("peau d'orange", "had a peau d orange appearance"),
    ("Dix-Hallpike", "The Dixhallpike test reproduced"),
])
def test_spelling_variants_count_as_found(term, text):
    assert tb.found(term, text)


@pytest.mark.parametrize("term, text", [
    ("Charcot foot", "He has a charcoal foot with a warm midfoot."),
    ("ceftriaxone", "She was given subteraxone 1 g intravenously."),
    ("acyclovir", "Valacyclovir was prescribed for the shingles."),
    ("Lewy body dementia", "suggest Louie body dementia"),
])
def test_wrong_words_are_not_found(term, text):
    assert not tb.found(term, text)


def test_an_accepted_spelling_counts_and_is_not_said():
    item = next(it for it in ITEMS if "Cephalexin" in it["targets"])
    assert tb.written(item, "Cephalexin", "Cefalexin 500 mg four times daily")
    assert "cefalexin" not in item["reference"].lower() and "|" not in item["reference"]


def test_heard_as_shows_what_was_written_instead():
    ref = "He has a Charcot foot, with a warm, swollen midfoot."
    assert tb.heard_as(ref, "Charcot foot", "He has a charcoal foot, with a warm, swollen midfoot.") == "charcoal foot"


def test_voice_gets_hints_only_for_its_own_terms():
    item = next(it for it in ITEMS if it["id"] == "t10")
    said = dict(tb.hints_for(item, HINTS))
    assert said.get("Charcot") == "shar-KOH" and "Lisfranc" in said and "Kussmaul" not in said
