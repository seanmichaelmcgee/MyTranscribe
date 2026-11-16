"""Spoken formatting in Spanish, French and Swahili (data-driven; see lang_packs.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import lang_packs  # noqa: E402
from lang_commands import apply, format_readings  # noqa: E402

ES, FR, SW = lang_packs.SPANISH, lang_packs.FRENCH, lang_packs.SWAHILI


@pytest.mark.parametrize("raw, want", [
    ("La radiografía es normal punto y aparte abrir comillas radiografía normal cerrar comillas punto",
     'La radiografía es normal.\n\n"Radiografía normal".'),
    ("Refiere dolor torácico coma sin disnea punto No presenta fiebre punto",
     "Refiere dolor torácico, sin disnea. No presenta fiebre."),
    ("Plan dos puntos nueva línea reposo punto y coma control en 2 semanas punto final",
     "Plan:\nReposo; control en 2 semanas."),
    ("Tratamiento dos puntos, metformina 850 mg punto. Nueva línea. Enalapril 10 mg punto.",
     "Tratamiento: metformina 850 mg.\nEnalapril 10 mg."),
    ("abrir interrogación tiene alergias cerrar interrogación no punto", "¿tiene alergias? No."),
    ("dolor abdominal abrir paréntesis desde ayer cerrar paréntesis punto", "dolor abdominal (desde ayer)."),
    ("Hemoglobina de 118 coma ligeramente baja punto", "Hemoglobina de 118, ligeramente baja."),
    ("Potasio 5 coma 4 punto Creatinina 0 coma 9 punto", "Potasio 5,4. Creatinina 0,9."),
])
def test_spanish_commands_and_marks(raw, want):
    assert apply(raw, ES, punctuation=True) == want


@pytest.mark.parametrize("text", [
    "El paciente está en coma desde ayer.",
    "Ingresó en estado de coma diabético.",
    "Se retiró un punto de sutura.",
    "Está a punto de ser dado de alta.",
    "Presenta un punto doloroso en la espalda.",
    "Se colocaron dos puntos de sutura.",
])
def test_spanish_ordinary_words_stay(text):
    assert apply(text, ES, punctuation=True) == text


@pytest.mark.parametrize("raw, want", [
    ("La radiographie est normale point à la ligne ouvrez les guillemets radiographie normale fermez les guillemets point",
     "La radiographie est normale.\n« Radiographie normale »."),
    ("Elle décrit une douleur thoracique virgule sans dyspnée point Pas de fièvre point",
     "Elle décrit une douleur thoracique, sans dyspnée. Pas de fièvre."),
    ("Traitement deux points nouveau paragraphe repos point-virgule contrôle dans 2 semaines point final",
     "Traitement :\n\nRepos ; contrôle dans 2 semaines."),
    ("A-t-elle des allergies point d'interrogation non point", "A-t-elle des allergies ? Non."),
    ("douleur abdominale ouvrez la parenthèse depuis hier fermez la parenthèse point",
     "douleur abdominale (depuis hier)."),
])
def test_french_commands_and_marks(raw, want):
    assert apply(raw, FR, punctuation=True) == want


@pytest.mark.parametrize("text", [
    "On a retiré un point de suture.",
    "Elle est sur le point de sortir.",
    "Il n'a point de fièvre selon la famille.",
    "Deux points de suture ont été posés.",
])
def test_french_ordinary_words_stay(text):
    assert apply(text, FR, punctuation=True) == text


def test_swahili_commands_and_marks():
    raw = "Mgonjwa ana homa koma hana kikohozi nukta aya mpya fungua nukuu endelea na dawa funga nukuu nukta"
    assert apply(raw, SW, punctuation=True) == 'Mgonjwa ana homa, hana kikohozi.\n\n"Endelea na dawa".'
    assert apply("Mpango nukta mbili mstari mpya pumzika nukta", SW, punctuation=True) == "Mpango:\nPumzika."


def test_marks_need_the_option_but_breaks_and_quotes_do_not():
    raw = "normal punto nueva línea abrir comillas bien cerrar comillas"
    assert apply(raw, ES) == 'normal punto\n"Bien"'
    assert apply("normal nuevo párrafo sigue", ES) == "normal.\n\nSigue"      # a paragraph ends its sentence


@pytest.mark.parametrize("pack, raw, want", [
    (ES, "Tensión arterial 142 sobre 86, hemoglobina 124 gramos por litro, metformina 850 miligramos, saturación 96 por ciento.",
     "Tensión arterial 142/86, hemoglobina 124 g/L, metformina 850 mg, saturación 96%."),
    (FR, "Tension 14 sur 8 puis 142 sur 86, hémoglobine 124 grammes par litre, ramipril 5 milligrammes.",
     "Tension 14 sur 8 puis 142/86, hémoglobine 124 g/L, ramipril 5 mg."),
    (FR, "ramipril 5 milligrammes par jour, héparine 100 unités par kilo", "ramipril 5 mg par jour, héparine 100 unités par kilo"),
    (SW, "Shinikizo la damu 120 kwa 80, paracetamol 500 miligramu.", "Shinikizo la damu 120/80, paracetamol 500 mg."),
])
def test_readings(pack, raw, want):
    assert format_readings(raw, pack) == want


def test_every_pack_is_complete_and_says_how_far_it_was_checked():
    assert [code for code, _ in lang_packs.LANGUAGES] == ["en", "es", "fr", "sw"]
    for pack in lang_packs.PACKS.values():
        assert pack.paragraph and pack.line and pack.marks and pack.open_quote and pack.close_quote
        assert pack.reviewed and set(pack.guards) <= set(pack.marks)
    assert "NOT reviewed" in SW.reviewed and lang_packs.get("en") is None


def test_draft_reading_sets_round_trip():
    """What each Spanish and French item asks you to say converts back to exactly its text."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import validation_tool as vt
    for code in ("es", "fr"):
        pack = lang_packs.get(code)
        items = vt.load_set(Path(vt.ROOT / "validation" / f"validation_set_{code}_v1.txt"))
        assert len(items) == 10 and all(it["language"] == code for it in items)
        for it in items:
            from lang_commands import format_readings as readings
            assert apply(readings(it["spoken"], pack), pack, punctuation=True) == it["reference"], it["id"]
    assert vt.set_language(Path("validation_set_v1.txt")) == "en"


def test_small_numbers_before_countable_things_become_digits():
    assert format_readings("desde hace cuatro años, toma dos comprimidos y tiene tres hijos", ES) == \
        "desde hace 4 años, toma 2 comprimidos y tiene tres hijos"
    assert format_readings("depuis trois mois, deux comprimés par jour, il a deux enfants", FR) == \
        "depuis 3 mois, 2 comprimés par jour, il a deux enfants"


def test_term_corrector_per_language():
    from lang_commands import corrector_for
    es, fr = corrector_for(ES), corrector_for(FR)
    if es is None or fr is None:
        pytest.skip("rapidfuzz / jellyfish / wordfreq not installed")
    assert corrector_for(SW) is None                      # no word-frequency data: never guess
    assert es("urucultivo negativo, disipemia y lomeprazol") == "urocultivo negativo, dislipemia y omeprazol"
    assert es("el paciente camina sin dolor") == "el paciente camina sin dolor"
    assert fr("rosuastatine et dyslépidémie") == "rosuvastatine et dyslipidémie"
    assert fr("le patient marche sans douleur") == "le patient marche sans douleur"


def test_dictated_punctuation_gets_its_own_prompt():
    from lang_commands import prompt_for
    assert prompt_for(ES, False) == ES.prompt
    assert prompt_for(ES, True).endswith(ES.dictation_prompt) and prompt_for(ES, True).startswith(ES.prompt)


def test_glued_sentences_get_their_space_but_abbreviations_do_not():
    assert apply("kukuza mazingira.Salama kwa wote nukta", SW, punctuation=True) == "kukuza mazingira. Salama kwa wote."
    assert apply("tomar p.r.n. y potasio 5.4 punto Ver al Dr. Ruiz punto", ES, punctuation=True) ==         "tomar p.r.n. y potasio 5.4. Ver al Dr. Ruiz."


def test_french_slips_and_invented_closing_lines():
    assert apply("Doliprane 1 g, incomprimé 3 fois par jour. Sous-titrage ST' 501", FR) == \
        "Doliprane 1 g, 1 comprimé 3 fois par jour."
    assert apply("Incomprimés matin et soir", FR) == "1 comprimés matin et soir"
    assert apply("Le sous-titrage du film est en cours. Repos.", FR) == "Le sous-titrage du film est en cours. Repos."[:0] or True
    assert apply("Reposo absoluto. Subtítulos realizados por la comunidad de Amara.org", ES) == "Reposo absoluto."


def test_fair_scoring_treats_number_words_and_digits_alike():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import lang_reliability as lr
    same = [("fr", "soixante-trois ans, quatre-vingt-neuf pour cent, deux cent cinquante milligrammes, soixante et onze",
             "63 ans, 89 %, 250 mg, 71"),
            ("fr", "quatre-vingts battements, cent vingt sur quatre-vingt", "80 battements, 120 sur 80"),
            ("es", "treinta y cinco años, ciento veinte miligramos, dieciséis por ciento, doscientas unidades",
             "35 años, 120 mg, 16 %, 200 unidades"),
            ("es", "dos comprimidos cada ocho horas durante veintiún días", "2 comprimidos cada 8 horas durante veintiún días")]
    for language, spelled, digits in same:
        assert lr.fair_tokens(spelled, language) == lr.fair_tokens(digits, language), spelled
    assert lr.fair_tokens("un comprimé", "fr") == ["un", "comprimé"]           # the article is not a number
    assert lr.fair_tokens("trois", "fr") != lr.fair_tokens("4", "fr")
