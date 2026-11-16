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
    space_before: str = ""                                     # marks written with a space before (French : ; ? !)
    say: Dict[str, str] = field(default_factory=dict)          # how to dictate each mark and break (reading sets)
    titles: Tuple[str, ...] = ()                               # abbreviations whose dot is not dictated


_F = frozenset

SPANISH = LanguagePack(
    code="es", name="Español (Spanish)",
    reviewed="Drafted from standard Spanish dictation terms; not yet checked with a Spanish-dictating clinician.",
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
    say={".": "punto", ",": "coma", ":": "dos puntos", ";": "punto y coma", "?": "cerrar interrogación",
         "\n\n": "nuevo párrafo", "\n": "nueva línea", "open": "abrir comillas", "close": "cerrar comillas"},
    titles=("Sr", "Sra", "Srta", "Dr", "Dra"),
    over=("sobre",), per=("por",),
    units={"miligramos": "mg", "miligramo": "mg", "microgramos": "mcg", "microgramo": "mcg", "gramos": "g",
           "gramo": "g", "mililitros": "mL", "mililitro": "mL", "kilogramos": "kg", "kilogramo": "kg",
           "kilos": "kg", "milimoles": "mmol", "milímetros": "mm", "milimetros": "mm",
           "centímetros": "cm", "centimetros": "cm", "por ciento": "%"},
    # Concentrations and weight-based doses only: "10 mg por día" stays words.
    per_units={"litro": "L", "decilitro": "dL", "mililitro": "mL", "kilo": "kg", "kilogramo": "kg"},
    prompt="Gracias por valorar a la Sra. Gómez, mujer de 67 años con dolor de rodilla derecha de 6 semanas de "
           "evolución. Antecedentes: hipertensión arterial, diabetes mellitus tipo 2. Tratamiento: metformina "
           "850 mg cada 12 horas, enalapril 10 mg al día. Exploración: tensión arterial 142/86 mmHg, frecuencia "
           "cardíaca 74 lpm.",
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
    say={".": "point", ",": "virgule", ":": "deux points", ";": "point-virgule", "?": "point d'interrogation",
         "\n\n": "nouveau paragraphe", "\n": "à la ligne", "open": "ouvrez les guillemets",
         "close": "fermez les guillemets"},
    titles=("M", "Dr", "Pr"),
    over=("sur",), per=("par",),
    units={"milligrammes": "mg", "milligramme": "mg", "microgrammes": "µg", "microgramme": "µg",
           "grammes": "g", "gramme": "g", "millilitres": "mL", "millilitre": "mL", "kilogrammes": "kg",
           "kilogramme": "kg", "kilos": "kg", "millimoles": "mmol", "millimètres": "mm", "millimetres": "mm",
           "centimètres": "cm", "centimetres": "cm", "pour cent": " %"},
    per_units={"litre": "L", "décilitre": "dL", "decilitre": "dL", "millilitre": "mL", "kilo": "kg",
               "kilogramme": "kg"},
    prompt="Je vous remercie de recevoir Mme Lefèvre, 67 ans, pour une gonalgie droite évoluant depuis 6 semaines. "
           "Antécédents : hypertension artérielle, diabète de type 2. Traitement : metformine 850 mg matin et soir, "
           "ramipril 5 mg par jour. À l'examen : tension artérielle 14/8, fréquence cardiaque 74/min.",
)

SWAHILI = LanguagePack(
    code="sw", name="Kiswahili (Swahili)",
    reviewed="NOT reviewed by a Swahili speaker. Phrases are the standard punctuation terms as far as the "
             "author knows them; verify every one with a clinician who dictates in Swahili before relying on it.",
    paragraph=("aya mpya", "ibara mpya"),
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
    say={".": "nukta", ",": "koma", ":": "nukta mbili", ";": "nukta mkato", "?": "alama ya kuuliza",
         "\n\n": "aya mpya", "\n": "mstari mpya", "open": "fungua nukuu", "close": "funga nukuu"},
    titles=("Dkt", "Bw", "Bi"),
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
