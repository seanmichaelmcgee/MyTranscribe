"""
pause_flow.py — word-timing logic for the "pause-aware" dictation pipeline.

Used by ChunkedTranscriber when pause_aware=True (off by default; the classic
pipeline never imports this). It works on the word timings faster-whisper
returns for a chunk, [(word, start_s, end_s)], and fixes two things that
thinking pauses break:

1. A chunk is cut at the quietest moment near its target length. A thinking
   pause is the quietest moment, so the cut often lands mid-sentence; Whisper
   then ends the chunk with a full stop and starts the next with a capital
   ("atenolol 50 mg daily. Was started in March"). split_for_carry() keeps only
   the complete sentences of a non-final chunk and hands the audio of the
   unfinished one to the next chunk, where it is decoded together with its end.

2. Whisper sometimes leaves a spoken command ("new paragraph") out of the text
   altogether, as if it were filler. The words on either side are then further
   apart than a pause explains. rescue_holes() lists such holes and
   command_in_hole() recognises a command in the re-decoded hole, so it can be
   put back. Only a command is ever inserted; any other text found in a hole
   is ignored.

Pure functions; nothing is logged.
"""

import re
from typing import List, Optional, Sequence, Tuple

Word = Tuple[str, float, float]      # a second listen adds a 4th value: probability

TERMINAL = ".?!"
CARRY_MIN_GAP_S = 0.12       # a sentence end must have at least this much air to cut in
RESCUE_MIN_GAP_S = 0.6       # "new line" takes ~0.6 s to say; fast dictation leaves no more
RESCUE_MARGIN_S = 0.35       # the neighbours' timings smear into the hole: listen a bit wider
RESCUE_NEIGHBOURS = 4        # words either side checked for a command that is already there
RESCUE_MAX_STRAYS = 4        # other words a second listen may hear (the neighbours, in part)
RESCUE_MIN_SOUND_S = 0.4     # a hole needs this much sound in it to be worth a second listen
# ...and the model must be this sure of the command's clearest word. (The first word
# after a prompt always scores low, so it is the best word that tells heard from guessed.)
RESCUE_MIN_PROBABILITY = 0.7
# Prompt for the second listen: the commands as they should be written. It makes a
# quick (greedy) decode hear "New paragraph." rather than a near-homophone.
LISTEN_PROMPT = "New paragraph. New line. Open quote, close quote."
# What goes back into the text for a recovered command, written the way Whisper
# writes a spoken command (set off by punctuation) so voice_commands converts it.
_COMMANDS = {
    "new paragraph": "New paragraph.", "next paragraph": "New paragraph.",
    "new line": "New line.", "next line": "New line.",
    "open quote": "Open quote,", "open quotes": "Open quote,",
    "close quote": "close quote.", "close quotes": "close quote.",
    "end quote": "close quote.", "end quotes": "close quote.", "unquote": "close quote.",
}
_COMMAND_RE = re.compile(r"\b(" + "|".join(sorted(_COMMANDS, key=len, reverse=True)).replace(" ", r"\s+") + r")\b")
_ENGLISH = (LISTEN_PROMPT, _COMMANDS, _COMMAND_RE)


def set_language(pack=None) -> None:
    """
    Use another language's command phrases (a lang_packs.LanguagePack), or
    English again with None. The pause-aware pipeline keeps a chunk that ends
    on a spoken command whole and listens again for a command the model
    skipped; both need to know what a command sounds like in the language.
    One language at a time per process, like the app.
    """
    global LISTEN_PROMPT, _COMMANDS, _COMMAND_RE
    if pack is None:
        LISTEN_PROMPT, _COMMANDS, _COMMAND_RE = _ENGLISH
        return
    commands = {}
    for phrases, ending in ((pack.paragraph, "."), (pack.line, "."), (pack.open_quote, ","), (pack.close_quote, ".")):
        if phrases:
            written = phrases[0][0].upper() + phrases[0][1:] + ending if ending == "." and phrases is not pack.close_quote \
                else phrases[0] + ending
            for phrase in phrases:
                commands[" ".join(_norm(phrase).split())] = written
    _COMMANDS = commands
    _COMMAND_RE = re.compile(r"(?<!\w)(" + "|".join(re.escape(k).replace(r"\ ", r"\s+")
                                                    for k in sorted(commands, key=len, reverse=True)) + r")(?!\w)")
    firsts = [p[0] for p in (pack.paragraph, pack.line, pack.open_quote, pack.close_quote) if p]
    LISTEN_PROMPT = ". ".join(f[0].upper() + f[1:] for f in firsts) + "."


def _norm(text: str) -> str:
    """Lower-case letters and spaces only (any alphabet)."""
    return re.sub(r"[^\w ]+|[\d_]+", " ", text.lower())


def words_text(words: Sequence[Word]) -> str:
    """The text of a word list (faster-whisper words carry their own leading space)."""
    return " ".join("".join(w[0] for w in words).split())


def _ends_sentence(word: str) -> bool:
    return word.rstrip("\"')").endswith(tuple(TERMINAL))


def split_for_carry(words: Sequence[Word], audio_s: float,
                    max_carry_s: float) -> Tuple[List[Word], Optional[float]]:
    """
    For a chunk that is NOT the end of the recording: (words to keep, carry_from_s).

    carry_from_s is where the unfinished last sentence starts; audio from there
    on belongs to the next chunk. None means keep everything (no sentence end
    with a usable pause inside the last max_carry_s seconds, or nothing after it).
    The chunk's own final full stop is never trusted: it is where the audio
    was cut, not necessarily where the sentence ended. The exception is a chunk
    that ends on a spoken command ("... New paragraph."): that is a complete
    thought, and carrying it over would put it at the very start of the next
    chunk, where the model is most likely to leave it out.
    """
    words = list(words)
    tail = [_key(w[0]) for w in words[-3:]]                # commands are one to three words long
    if any(" ".join(tail[i:]) in _COMMANDS for i in range(len(tail))):
        return words, None
    for k in range(len(words) - 2, -1, -1):
        gap_start, gap_end = words[k][2], words[k + 1][1]
        if audio_s - gap_end > max_carry_s:
            break
        if _ends_sentence(words[k][0]) and gap_end - gap_start >= CARRY_MIN_GAP_S:
            return words[:k + 1], (gap_start + gap_end) / 2
    return words, None


def speech_gaps(words: Sequence[Word], audio_s: float,
                min_gap_s: float = RESCUE_MIN_GAP_S) -> List[Tuple[int, float, float]]:
    """
    Holes of at least min_gap_s between consecutive words (and before the first
    / after the last), as (index of the word after the hole, start_s, end_s).
    """
    gaps, prev = [], 0.0
    for i, (_w, start, end) in enumerate(words):
        if start - prev >= min_gap_s:
            gaps.append((i, prev, start))
        prev = max(prev, end)
    if audio_s - prev >= min_gap_s:
        gaps.append((len(words), prev, audio_s))
    return gaps


def _key(word: str) -> str:
    return re.sub(r"[^\w]|_", "", word.lower())


def match_command(text: str) -> Optional[str]:
    """The canonical command if `text` contains a spoken command phrase; else None."""
    norm = " ".join(_norm(text).split())
    m = _COMMAND_RE.search(norm)
    return _COMMANDS[" ".join(m.group(1).split())] if m else None


def rescue_holes(words: Sequence[Word], audio_s: float) -> List[Tuple[int, float, float, float, float]]:
    """
    Holes that could hold a command, in time order: (word index after the
    hole, hole start_s, hole end_s, from_s, to_s). from/to is the hole widened
    by RESCUE_MARGIN_S: what to listen to. The hole itself is what must contain
    sound for the listen to be worth it.
    """
    return [(i, a, b, max(0.0, a - RESCUE_MARGIN_S), min(audio_s, b + RESCUE_MARGIN_S))
            for i, a, b in speech_gaps(words, audio_s)]


def command_near(words: Sequence[Word], index: int) -> bool:
    """True if the words around the hole before words[index] already contain a command."""
    near = words[max(0, index - RESCUE_NEIGHBOURS):index + RESCUE_NEIGHBOURS]
    return match_command(" ".join(_key(w[0]) for w in near)) is not None


def command_in_hole(hole_words: Sequence[Word], words: Sequence[Word],
                    index: int) -> Optional[Tuple[str, float, float]]:
    """
    Decide whether the re-decoded hole before words[index] holds a command the
    first pass left out: (canonical command, start_s, end_s) or None.

    Accepted only if the hole's text is a command phrase plus, at most, a few
    other words (the widened hole overlaps its neighbours, often mid-word), and
    the neighbours do not already contain that command (nothing was left out).
    """
    spoken = [w for w in hole_words if _key(w[0])]
    keys = [_key(w[0]) for w in spoken]
    for size in (2, 1):
        for i in range(len(keys) - size + 1):
            phrase = " ".join(keys[i:i + size])
            if phrase not in _COMMANDS:
                continue
            if command_near(words, index) or len(keys) - size > RESCUE_MAX_STRAYS:
                return None
            sure = [w[3] for w in spoken[i:i + size] if len(w) > 3]
            if sure and max(sure) < RESCUE_MIN_PROBABILITY:
                return None               # a guess prompted by LISTEN_PROMPT, not something heard
            return _COMMANDS[phrase], spoken[i][1], spoken[i + size - 1][2]
    return None


def insert_commands(words: Sequence[Word], found: Sequence[Tuple[int, float, float, str]]) -> List[Word]:
    """Put recovered commands (index, start_s, end_s, canonical text) back into the word list."""
    out = list(words)
    for index, start, end, command in sorted(found, reverse=True):
        out.insert(index, (" " + command, start, end))
    return out
