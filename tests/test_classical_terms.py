"""classical_terms.py: misheard classical terms put right where their last word is heard."""

from types import SimpleNamespace

import pytest

import classical_terms as ct
import text_fixes
import vocab


@pytest.fixture(scope="module")
def fix():
    fixer = ct.default_fixer()
    assert fixer is not None, "rapidfuzz and jellyfish are in requirements"
    return fixer


@pytest.mark.parametrize("heard, written", [
    ("Phelan's test was positive.", "Phalen's test was positive."),
    ("Her centaur score was 3.", "Her Centor score was 3."),
    ("He has a charcoal foot with a warm midfoot.", "He has a Charcot foot with a warm midfoot."),
    ("Hoffman sign was present.", "Hoffmann's sign was present."),
    ("She has Ramsey Hunt syndrome.", "She has Ramsay Hunt syndrome."),
    ("A Graham Steele murmur was heard.", "A Graham Steell murmur was heard."),
    ("This is Bud Chiari syndrome.", "This is Budd-Chiari syndrome."),
    ("Ogilvy syndrome was considered.", "Ogilvie syndrome was considered."),
    ("Sperling's test reproduced the pain.", "Spurling's test reproduced the pain."),
])
def test_misheard_terms_are_put_right(fix, heard, written):
    assert fix(heard) == written


@pytest.mark.parametrize("text", [
    "He has inflammatory bowel disease.",                 # "bowel" is a known word, not Bowen's
    "She had a second fracture of the wrist.",             # an ordinal, not Segond
    "We think she will score well.",                       # "score" as a verb
    "Carpal tunnel syndrome is likely.",
    "There was a Gray Turner's sign.",                     # another accepted spelling
    "Berger's disease is another name for IgA nephropathy.",
    "Activated charcoal was given.",                       # no "foot" after it
    "His blood test was normal and his vital signs were stable.",
    "Coronary artery disease, chronic kidney disease and a stress test.",
    "It was a true fracture.",
])
def test_ordinary_text_is_left_alone(fix, text):
    assert fix(text) == text


def test_a_term_starting_a_sentence_gets_a_capital(fix):
    assert fix("Pain on hip rotation. Obturater sign was positive.") == "Pain on hip rotation. Obturator sign was positive."


@pytest.mark.parametrize("word, folded", [("Ogilvie's", "ogilvie"), ("bodies", "body"), ("Homans'", "homan"),
                                          ("Homan's", "homan"), ("Phalens", "phalen"), ("tumor", "tumour"),
                                          ("Sjögren's", "sjogren")])
def test_fold(word, folded):
    assert ct.fold(word) == folded


def test_list_is_consistent():
    terms = ct.load_terms()
    assert len(terms) > 400
    seen = {}
    for spellings in terms:
        for s in spellings:
            key = " ".join(ct.fold(w) for w in ct._WORD.findall(s))
            assert seen.setdefault(key, spellings[0]) == spellings[0], f"{s!r} also spells {seen[key]!r}"


def engine_on(device):
    return SimpleNamespace(config=SimpleNamespace(device=device))


def test_on_for_the_processor_only_until_approved_for_the_graphics_card(monkeypatch):
    assert ct.on_for(engine_on("cpu"))
    assert not ct.on_for(engine_on("cuda"))
    assert not ct.on_for(SimpleNamespace())                # MedASR and other recognisers
    monkeypatch.setattr(ct, "GRAPHICS_CARD_TOO", True)
    assert ct.on_for(engine_on("cuda"))


def test_finish_applies_it_only_when_asked():
    heard = "Phelan's test was positive."
    assert text_fixes.finish(heard, True) == heard
    assert text_fixes.finish(heard, True, classical=True) == "Phalen's test was positive."
    assert text_fixes.finish(heard, False, classical=True) == heard     # Extra corrections off


def test_spelling_corrector_learns_classical_words_only_when_asked():
    _, plain = vocab.build_text_pipeline("", env={})
    _, knowing = vocab.build_text_pipeline("", env={}, classical=True)
    assert "equinovarus" not in plain.corrector.canonical
    assert knowing.corrector.canonical.get("equinovarus") == "equinovarus"
