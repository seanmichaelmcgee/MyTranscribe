"""
lang_packs.py — what the text layer needs to know about a dictation language.

English keeps its own tuned code (voice_commands.py, spoken_numbers.py, the
vocabulary corrector). Every other language is data here, read by
lang_commands.py: the phrases that are formatting commands, the words that are
punctuation marks, when such a word is an ordinary word instead, and a short
style prompt so Whisper writes in that language's conventions.

Status of each pack is stated in its `reviewed` field. None has been checked
against recordings of a clinician dictating in that language: the phrases are
the standard dictation terms, and the "ordinary word" guards are word lists
like the English ones. Swahili has not been reviewed by a native speaker.
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Tuple


@dataclass(frozen=True)
class Guard:
    """A mark word stays an ordinary word after `prev` or before `next` (same clause)."""
    prev: FrozenSet[str] = frozenset()
    next: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class LanguagePack:
    code: str                                  # Whisper language code
    name: str                                  # shown in Options
    reviewed: str
    paragraph: Tuple[str, ...] = ()
    line: Tuple[str, ...] = ()
    open_quote: Tuple[str, ...] = ()
    close_quote: Tuple[str, ...] = ()
    open_paren: Tuple[str, ...] = ()
    close_paren: Tuple[str, ...] = ()
    quotes: Tuple[str, str] = ('"', '"')
    marks: Dict[str, str] = field(default_factory=dict)        # phrase -> mark; "\n\n" allowed after it
    guards: Dict[str, Guard] = field(default_factory=dict)     # phrase -> when it is a noun
    over: Tuple[str, ...] = ()                                 # "140 <over> 90" -> 140/90
    per: Tuple[str, ...] = ()                                  # "g <per> L" -> g/L
    units: Dict[str, str] = field(default_factory=dict)        # spoken unit -> abbreviation (after a digit)
    per_units: Dict[str, str] = field(default_factory=dict)    # spoken denominator -> abbreviation
    prompt: str = ""                                           # style example in the language
    # A few words of dictation with the commands spoken. Whisper treats its prompt as
    # what came before; without this example it tends to leave a spoken "nuevo párrafo"
    # out as if it were an aside (layout right in 26 of 40 synthetic Spanish readings;
    # 40 of 40 with it). Used when Spoken punctuation is on.
    dictation_prompt: str = ""
    space_before: str = ""                                     # marks written with a space before (French : ; ? !)
    say: Dict[str, str] = field(default_factory=dict)          # how to dictate each mark and break (reading sets)
    titles: Tuple[str, ...] = ()                               # abbreviations whose dot is not dictated
    # Recognition slips with one obvious reading, as (regex, replacement): applied to every text.
    fixes: Tuple[Tuple[str, str], ...] = ()
    # Lines the model invents over silence or a trailing "euh" (regexes, matched to the end of the text).
    phantoms: Tuple[str, ...] = ()
    vocab_file: str = ""                                       # src/vocab/<file>: terms for the spelling corrector
    number_words: Dict[str, str] = field(default_factory=dict)  # small number words written as digits ...
    counted: Tuple[str, ...] = ()                              # ... in front of these (regex alternatives)
    needs_tuned_model: bool = False                            # standard Whisper is too weak in this language
    tuned_model_repo: str = ""                                 # a fine-tuned Whisper to install for it


_F = frozenset

SPANISH = LanguagePack(
    code="es", name="Español (Spanish)",
    reviewed="Drafted from standard Spanish dictation terms; not yet checked with a Spanish-dictating clinician.",
    phantoms=(r"subt[ií]tulos\s+(?:realizados|por la comunidad)\b[^\n]*", r"gracias por ver(?: el v[ií]deo)?[^\n]*"),
    paragraph=("punto y aparte", "nuevo párrafo", "nuevo parrafo", "párrafo nuevo", "parrafo nuevo"),
    line=("nueva línea", "nueva linea", "línea nueva", "linea nueva", "salto de línea", "salto de linea"),
    open_quote=("abrir comillas", "abre comillas", "comillas de apertura"),
    close_quote=("cerrar comillas", "cierra comillas", "comillas de cierre"),
    open_paren=("abrir paréntesis", "abrir parentesis", "abre paréntesis", "abre parentesis"),
    close_paren=("cerrar paréntesis", "cerrar parentesis", "cierra paréntesis", "cierra parentesis"),
    marks={"punto y coma": ";", "punto y seguido": ".", "punto final": ".", "dos puntos": ":", "punto": ".",
           "coma": ",", "signo de interrogación": "?", "signo de interrogacion": "?",
           "cerrar interrogación": "?", "cerrar interrogacion": "?", "abrir interrogación": "¿",
           "abrir interrogacion": "¿", "cerrar exclamación": "!", "cerrar exclamacion": "!",
           "abrir exclamación": "¡", "abrir exclamacion": "¡", "guion": "-", "guión": "-"},
    guards={
        # "coma" is also a coma: "en coma", "estado de coma", "coma diabético".
        "coma": Guard(prev=_F({"en", "el", "un", "del", "al", "estado", "de", "su", "este", "ese", "entró", "entro"}),
                      next=_F({"diabético", "diabetico", "hepático", "hepatico", "profundo", "inducido", "etílico",
                               "etilico", "hiperosmolar", "mixedematoso", "urémico", "uremico", "barbitúrico",
                               "farmacológico", "farmacologico", "vigil"})),
        # "punto" is also a point, a stitch, a spot: "un punto de sutura", "a punto de", "punto doloroso".
        "punto": Guard(prev=_F({"un", "el", "este", "ese", "del", "al", "cada", "mismo", "a", "primer", "segundo",
                                "tercer", "último", "ultimo", "algún", "algun", "ningún", "ningun", "otro", "su",
                                "en", "hasta", "desde"}),
                       next=_F({"de", "doloroso", "gatillo", "máximo", "maximo", "medio", "ciego", "negro"})),
        "dos puntos": Guard(next=_F({"de", "en", "por", "más", "mas", "menos", "porcentuales"})),
    },
    dictation_prompt="Paciente estable, punto. Nuevo párrafo. Sin fiebre, coma, sin disnea, punto. Nueva línea. "
                     "Abrir comillas, reposo, cerrar comillas, punto y aparte.",
    say={".": "punto", ",": "coma", ":": "dos puntos", ";": "punto y coma", "?": "cerrar interrogación",
         "\n\n": "nuevo párrafo", "\n": "nueva línea", "open": "abrir comillas", "close": "cerrar comillas"},
    titles=("Sr", "Sra", "Srta", "Dr", "Dra"),
    # TEME dialogues, development half: the model writes the old accented adverb; the academy's
    # spelling since 2010 is "solo" in every use.
    fixes=((r"\b([sS])ólo\b", r"\1olo"),
           # "la tensión" is heard as "la atención" after a verb of measuring (8 times in 45 dialogues).
           (r"(?i)\b((?:tom|med|mid|control|vigil|mir)\w*) la atención\b", r"\1 la tensión"),
           (r"(?i)\batención arterial\b", "tensión arterial"),
           # "TAC" (a CT scan) is written "tag", which is not a Spanish word.
           (r"\b([Ee]l|[Uu]n|[Dd]el|[Aa]l|[Ee]ste|[Ee]se|[Oo]tro) [Tt]ag\b", r"\1 TAC")),
    vocab_file="medical_es.txt",
    number_words={"dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6", "siete": "7", "ocho": "8",
                  "nueve": "9", "diez": "10", "once": "11", "doce": "12", "quince": "15", "veinte": "20",
                  "treinta": "30"},
    counted=("mg", "mcg", "g", "ml", "miligramos?", "gramos?", "mililitros?", "comprimidos?", "cápsulas?",
             "capsulas?", "gotas", "inhalaciones", "días?", "dias?", "semanas?", "mes(?:es)?", "años?", "horas?",
             "minutos?", "veces", "manzanas", "kilos?", "centímetros?", "centimetros?", "milímetros?", "milimetros?"),
    over=("sobre",), per=("por",),
    units={"miligramos": "mg", "miligramo": "mg", "microgramos": "mcg", "microgramo": "mcg", "gramos": "g",
           "gramo": "g", "mililitros": "mL", "mililitro": "mL", "kilogramos": "kg", "kilogramo": "kg",
           "kilos": "kg", "milimoles": "mmol", "milímetros": "mm", "milimetros": "mm",
           "centímetros": "cm", "centimetros": "cm", "por ciento": "%",
           "latidos por minuto": "lpm", "respiraciones por minuto": "rpm"},
    # Concentrations and weight-based doses only: "10 mg por día" stays words.
    per_units={"litro": "L", "decilitro": "dL", "mililitro": "mL", "kilo": "kg", "kilogramo": "kg"},
    prompt="Gracias por valorar a la Sra. Gómez, mujer de 67 años con dolor de rodilla derecha de 6 semanas de "
           "evolución. Antecedentes: hipertensión arterial, diabetes mellitus tipo 2. Tratamiento: metformina "
           "850 mg cada 12 horas, enalapril 10 mg al día. Exploración: tensión arterial 142/86 mmHg, frecuencia "
           "cardíaca 74 lpm. "
           # By analogy with French (where a prescription line was measured to help); not measured in Spanish.
           "Receta: paracetamol 1 g, 1 comprimido cada 8 horas durante 5 días. Omeprazol 20 mg, 1 cápsula al día.",
)

FRENCH = LanguagePack(
    code="fr", name="Français (French)",
    reviewed="Drafted from standard French dictation terms; not yet checked with a French-dictating clinician.",
    paragraph=("nouveau paragraphe", "nouvel alinéa", "nouvel alinea", "point à la ligne paragraphe"),
    line=("à la ligne", "a la ligne", "nouvelle ligne", "retour à la ligne", "retour a la ligne"),
    open_quote=("ouvrez les guillemets", "ouvrir les guillemets", "ouvre les guillemets", "ouvrez guillemets"),
    close_quote=("fermez les guillemets", "fermer les guillemets", "ferme les guillemets", "fermez guillemets"),
    open_paren=("ouvrez la parenthèse", "ouvrez la parenthese", "ouvrir la parenthèse", "ouvrir la parenthese",
                "ouvre la parenthèse", "ouvre la parenthese"),
    close_paren=("fermez la parenthèse", "fermez la parenthese", "fermer la parenthèse", "fermer la parenthese",
                 "ferme la parenthèse", "ferme la parenthese"),
    quotes=("« ", " »"),
    marks={"point-virgule": ";", "point virgule": ";", "deux-points": ":", "deux points": ":",
           "point d'interrogation": "?", "point d’interrogation": "?", "point d'exclamation": "!",
           "point d’exclamation": "!", "point final": ".", "point": ".", "virgule": ",",
           "trait d'union": "-", "trait d’union": "-", "tiret": "-"},
    guards={
        # "point" is also a point, a stitch, a negation: "un point de suture", "au point de", "point de côté".
        "point": Guard(prev=_F({"un", "le", "ce", "du", "au", "de", "à", "a", "chaque", "même", "meme", "premier",
                                "second", "dernier", "bon", "mauvais", "quel", "son", "en", "ne", "n'est", "tout"}),
                       next=_F({"de", "d", "du", "sur", "que", "douloureux", "gâchette", "gachette", "zéro",
                                "zero"})),
        "deux points": Guard(next=_F({"de", "d", "du", "sur", "en"})),
        "deux-points": Guard(next=_F({"de", "d", "du", "sur", "en"})),
        "tiret": Guard(prev=_F({"un", "le", "du"})),
    },
    space_before=":;?!",
    dictation_prompt="Patient stable, point. Nouveau paragraphe. Pas de fièvre, virgule, pas de dyspnée, point. "
                     "À la ligne. Ouvrez les guillemets, repos, fermez les guillemets, point.",
    say={".": "point", ",": "virgule", ":": "deux points", ";": "point-virgule", "?": "point d'interrogation",
         "\n\n": "nouveau paragraphe", "\n": "à la ligne", "open": "ouvrez les guillemets",
         "close": "fermez les guillemets"},
    titles=("M", "Dr", "Pr"),
    # PxCorpus development recordings: "un comprimé" is heard as "incomprimé" in about one prescription in ten.
    fixes=((r"\b[iI]ncomprim(ée?s?|és?)\b", r"1 comprim\1"),),
    phantoms=(r"sous[- ]titrage\b[^\n]*", r"sous[- ]titres?\s+(?:réalisés?|faits?)\b[^\n]*",
              r"merci d['’]avoir regardé[^\n]*"),
    vocab_file="medical_fr.txt",
    number_words={"deux": "2", "trois": "3", "quatre": "4", "cinq": "5", "six": "6", "sept": "7", "huit": "8",
                  "neuf": "9", "dix": "10", "onze": "11", "douze": "12", "quinze": "15", "vingt": "20",
                  "trente": "30"},
    counted=("mg", "µg", "g", "ml", "milligrammes?", "grammes?", "millilitres?", "comprimés?", "comprimes?",
             "gélules?", "gelules?", "gouttes?", "bouffées?", "bouffees?", "jours?", "semaines?", "mois", "ans?",
             "heures?", "minutes?", "fois", "mètres?", "metres?", "kilos?", "centimètres?", "centimetres?",
             "millimètres?", "millimetres?"),
    over=("sur",), per=("par",),
    units={"milligrammes": "mg", "milligramme": "mg", "microgrammes": "µg", "microgramme": "µg",
           "grammes": "g", "gramme": "g", "millilitres": "mL", "millilitre": "mL", "kilogrammes": "kg",
           "kilogramme": "kg", "kilos": "kg", "millimoles": "mmol", "millimètres": "mm", "millimetres": "mm",
           "centimètres": "cm", "centimetres": "cm", "pour cent": " %"},
    per_units={"litre": "L", "décilitre": "dL", "decilitre": "dL", "millilitre": "mL", "kilo": "kg",
               "kilogramme": "kg"},
    prompt="Je vous remercie de recevoir Mme Lefèvre, 67 ans, pour une gonalgie droite évoluant depuis 6 semaines. "
           "Antécédents : hypertension artérielle, diabète de type 2. Traitement : metformine 850 mg matin et soir, "
           "ramipril 5 mg par jour. À l'examen : tension artérielle 14/8, fréquence cardiaque 74/min. "
           # A prescription line: without it the model drops or mangles a brand name that opens the
           # recording and hears "un comprimé" as "incomprimé" (PxCorpus development: 11.5% -> 9.1%).
           "Ordonnance : Kardégic 75 mg, 1 comprimé par jour pendant 1 mois. Doliprane 1 g, 1 comprimé "
           "3 fois par jour pendant 5 jours. Ventoline, 2 bouffées si besoin.",
)

SWAHILI = LanguagePack(
    code="sw", name="Kiswahili (Swahili)",
    reviewed="NOT reviewed by a Swahili speaker. Phrases are the standard punctuation terms as far as the "
             "author knows them; verify every one with a clinician who dictates in Swahili before relying on it.",
    paragraph=("aya mpya", "ibara mpya", "haya mpya"),      # "haya mpya" is how the model often hears it
    line=("mstari mpya",),
    open_quote=("fungua nukuu", "fungua alama za nukuu"),
    close_quote=("funga nukuu", "funga alama za nukuu"),
    open_paren=("fungua mabano",), close_paren=("funga mabano",),
    marks={"nukta mkato": ";", "nukta mbili": ":", "nukta pacha": ":", "nukta": ".", "kituo kikuu": ".",
           "koma": ",", "mkato": ",", "alama ya kuuliza": "?", "kiulizo": "?", "alama ya mshangao": "!"},
    guards={
        # "mkato" also means a cut / shortcut, "nukta" a point or dot.
        "mkato": Guard(prev=_F({"njia", "wa", "ya", "kwa"}), next=_F({"wa", "mdogo", "mkubwa"})),
        "nukta": Guard(prev=_F({"hii", "hiyo", "moja", "kila", "ya"}), next=_F({"ya", "hii", "muhimu"})),
    },
    dictation_prompt="Mgonjwa yuko imara, nukta. Aya mpya. Hana homa, koma, hana kikohozi, nukta. Mstari mpya. "
                     "Fungua nukuu, pumzika, funga nukuu, nukta.",
    say={".": "nukta", ",": "koma", ":": "nukta mbili", ";": "nukta mkato", "?": "alama ya kuuliza",
         "\n\n": "aya mpya", "\n": "mstari mpya", "open": "fungua nukuu", "close": "funga nukuu"},
    titles=("Dkt", "Bw", "Bi"),
    needs_tuned_model=True, tuned_model_repo="cdli/whisper-large-v3-swahili-afrivoice-cv",
    over=("kwa",),                                   # "120 kwa 80"; "kwa" is too common to use as "per"
    units={"miligramu": "mg", "gramu": "g", "mililita": "mL", "kilogramu": "kg", "kilo": "kg",
           "sentimita": "cm", "milimita": "mm"},
    prompt="",
)

PACKS = {p.code: p for p in (SPANISH, FRENCH, SWAHILI)}
LANGUAGES = (("en", "English"),) + tuple((p.code, p.name) for p in PACKS.values())


def get(code: str):
    """The pack for a language code, or None for English and unknown codes."""
    return PACKS.get(code)
