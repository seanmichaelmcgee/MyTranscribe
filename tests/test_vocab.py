"""vocab: lexicon parsing, topic detection, prompt budget/rotation, pipeline wiring."""

import re

import pytest

import vocab
from vocab import (Lexicon, PromptBuilder, build_text_pipeline, load_lexicon,
                   parse_lexicon_text, parse_tsv_terms, score_topics)

SAMPLE = """
# comment
## core | letter
other: referral, follow-up
## diabetes | diabetes, sugar, A1c
drug: metformin (Glucophage), empagliflozin (Jardiance), insulin glargine (Lantus)
lab: HbA1c, lipoprotein(a)
## asthma | wheeze, inhaler
drug: salbutamol (Ventolin), budesonide-formoterol (Symbicort)
dx: hand-foot-and-mouth disease, croup
"""


def words(n):
    return lambda text: len(text.split())


def test_parse_topics_brands_and_parentheses():
    lex = parse_lexicon_text(SAMPLE)
    assert set(lex.topics) == {"core", "diabetes", "asthma"}
    d = [t.text for t in lex.topics["diabetes"].terms]
    assert d[:4] == ["metformin", "Glucophage", "empagliflozin", "Jardiance"]
    assert "lipoprotein(a)" in d                      # lowercase parens are not a brand
    assert lex.topics["diabetes"].triggers == ["diabetes", "sugar", "a1c"]
    assert {t.category for t in lex.topics["asthma"].terms} == {"drug", "dx"}


def test_topics_merge_across_files():
    lex = parse_lexicon_text(SAMPLE)
    parse_lexicon_text("## diabetes | glucose\ndrug: tirzepatide (Mounjaro)\n", lex)
    names = [t.text for t in lex.topics["diabetes"].terms]
    assert "Mounjaro" in names and "glucose" in lex.topics["diabetes"].triggers


def test_parse_tsv():
    terms = parse_tsv_terms("# hdr\ndrug\tapixaban\nacronym\tHbA1c\nbad line\n")
    assert [(t.category, t.text) for t in terms] == [("drug", "apixaban"), ("acronym", "HbA1c")]


def test_bundled_vocabulary_loads():
    lex = load_lexicon(env={})
    assert {"core", "diabetes", "peds-acute", "peds-wellchild", "immunization",
            "respiratory", "womens-health"} <= set(lex.topics)
    prompt_terms = sum(len(t.terms) for t in lex.topics.values())
    assert prompt_terms > 800 and len(lex.extra_terms) == 966
    all_text = {t.text for t in lex.all_terms()}
    for must in ("semaglutide", "Ozempic", "salbutamol", "albuterol", "Shingrix", "bronchiolitis",
                 "nirsevimab", "PHQ-9", "Rourke Baby Record", "apixaban"):
        assert must in all_text, must
    # No term may contain a stray comma or empty brand
    assert not any("," in t or t.strip() != t or not t for t in all_text)


def test_user_vocab_file_added(tmp_path):
    f = tmp_path / "mine.txt"
    f.write_text("## core | x\nother: Dr. Okonkwo-Bailey\n", encoding="utf-8")
    lex = load_lexicon(env={"MYTRANSCRIBE_VOCAB_FILES": str(f)})
    assert "Dr. Okonkwo-Bailey" in [t.text for t in lex.topics["core"].terms]
    load_lexicon(env={"MYTRANSCRIBE_VOCAB_FILES": str(tmp_path / "missing.txt")})   # logged, no crash


def test_score_topics():
    lex = parse_lexicon_text(SAMPLE)
    assert score_topics(lex, "") == []
    ranked = score_topics(lex, "Her sugar is up; we started empagliflozin. Mild wheeze too.")
    assert [n for n, _ in ranked] == ["diabetes", "asthma"]       # term hits weigh double
    assert score_topics(lex, "wheezes") == []                      # whole words only


def test_prompt_respects_budget_and_layout():
    lex = load_lexicon(env={})
    b = PromptBuilder("Dear Dr. Patel,", lex, budget=120)
    ctx = "x " * 50 + "the child had a barking cough and stridor overnight, now settled."
    p = b(ctx)
    assert vocab.estimate_tokens(p) <= 120
    assert p.startswith("Dear Dr. Patel, Vocabulary: ")
    assert p.endswith("now settled.")                               # recent words last
    assert "peds-acute" in b.last_topics


def test_prompt_skips_terms_already_said_and_rotates():
    lex = parse_lexicon_text(SAMPLE)
    b = PromptBuilder("", lex, count=words(1), budget=10)
    p1 = b("metformin and sugar")
    assert "metformin" not in p1.split("Vocabulary:")[1].split(".")[0]
    p2 = b("metformin and sugar")
    v1 = re.search(r"Vocabulary: (.*?)\.", p1).group(1)
    v2 = re.search(r"Vocabulary: (.*?)\.", p2).group(1)
    assert v1 != v2                                                 # rotation


def test_prompt_first_chunk_uses_default_topics_else_no_list():
    lex = parse_lexicon_text(SAMPLE)
    b = PromptBuilder("", lex, count=words(1), budget=50, default_topics=["asthma"])
    b("")
    assert b.last_topics == ["asthma"]
    # Nothing said and no default topics: no generic "sample of everything" list (distractors).
    b2 = PromptBuilder("Style text.", lex, count=words(1), budget=50)
    assert b2("") == "Style text." and b2.last_topics == []


def test_common_terms_skipped():
    lex = parse_lexicon_text("## t | x\nother: car seat, Rourke Baby Record\n")
    b = PromptBuilder("", lex, count=words(1), is_common=lambda t: t == "car seat", budget=50,
                      default_topics=["t"])
    p = b("")
    assert "Rourke" in p and "car seat" not in p


def test_tiny_budget_gives_no_vocabulary_but_valid_prompt():
    lex = parse_lexicon_text(SAMPLE)
    b = PromptBuilder("Style text here.", lex, count=words(1), budget=3)
    assert b("") == "Style text here."


def test_pipeline_switches():
    b, c = build_text_pipeline("Style.", env={"MYTRANSCRIBE_VOCAB": "off", "MYTRANSCRIBE_AUTOCORRECT": "off"})
    assert b is None and c is None
    b, c = build_text_pipeline("Style.", env={"MYTRANSCRIBE_AUTOCORRECT": "0"})
    assert isinstance(b, PromptBuilder) and c is None
    b, c = build_text_pipeline("Style.", env={"MYTRANSCRIBE_VOCAB_TOPICS": "diabetes"})
    b("")
    assert b.last_topics == ["diabetes"]
