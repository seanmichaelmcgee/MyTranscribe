"""
make_random_whisper.py — build a faster-whisper (CTranslate2) model directory
with the exact architecture of a real Whisper model but RANDOM weights.

Purpose: stress-test the real faster-whisper / CTranslate2 / VAD pipeline
(memory, threading, timing, API compatibility) on machines that cannot
download real weights (e.g. sandboxed CI). The output is gibberish text;
never use it for accuracy measurements.

Needs (dev-only, not app requirements):  pip install tiktoken
plus the openai-whisper source tree for its tokenizer assets:
    curl the sdist from PyPI and extract it; pass --whisper-src <dir>/whisper

Usage:
    python scripts/make_random_whisper.py --shape turbo --out /tmp/rand-turbo \
        --whisper-src /tmp/openai-whisper-20240930/whisper
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

# d_model, n_mels, enc_layers, enc_heads, dec_layers, dec_heads, n_languages
SHAPES = {
    "tiny": (384, 80, 4, 6, 4, 6, 99),
    "small": (768, 80, 12, 12, 12, 12, 99),
    "turbo": (1280, 128, 32, 20, 4, 20, 100),      # large-v3-turbo
    "large-v3": (1280, 128, 32, 20, 32, 20, 100),
}
N_AUDIO_CTX = 1500
N_TEXT_CTX = 448


def load_whisper_encoding(whisper_src: Path, num_languages: int):
    """Import openai-whisper's tokenizer.py by path (avoids importing torch)."""
    spec = importlib.util.spec_from_file_location("ow_tokenizer", whisper_src / "tokenizer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.get_encoding("multilingual", num_languages=num_languages)


def _bytes_to_unicode():
    """GPT-2's reversible byte -> printable-unicode map (used by ByteLevel BPE)."""
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) \
        + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, map(chr, cs)))


def build_tokenizer_json(encoding, out_dir: Path):
    """
    Write a HF `tokenizers` tokenizer.json equivalent to the tiktoken encoding
    (vocab + merges recovered from BPE ranks, same algorithm transformers uses).
    """
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers

    ranks = encoding._mergeable_ranks
    byte_map = _bytes_to_unicode()
    to_str = lambda b: "".join(byte_map[x] for x in b)
    vocab, merges = {}, []
    for token, rank in ranks.items():
        vocab[to_str(token)] = rank
        if len(token) == 1:
            continue
        local = [(token[:i], token[i:], rank) for i in range(1, len(token))
                 if token[:i] in ranks and token[i:] in ranks]
        local.sort(key=lambda m: (ranks[m[0]], ranks[m[1]]))
        merges.extend(local)
    merges.sort(key=lambda m: m[2])
    merges = [(to_str(a), to_str(b)) for a, b, _ in merges]

    tok = Tokenizer(models.BPE(vocab, merges, fuse_unk=False))
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    specials = sorted(encoding._special_tokens.items(), key=lambda kv: kv[1])
    tok.add_special_tokens([name for name, _ in specials])
    tok.save(str(out_dir / "tokenizer.json"))

    # Sanity: every special token id must match openai's numbering.
    for name, want in specials:
        got = tok.token_to_id(name)
        if got != want:
            raise SystemExit(f"tokenizer mismatch for {name}: {got} != {want}")
    sample = " Dear Dr. Patel, apixaban 5 mg b.i.d."
    if tok.encode(sample, add_special_tokens=False).ids != encoding.encode(sample):
        raise SystemExit("tokenizer does not reproduce tiktoken encoding")
    return tok


def rand(rng, *shape, scale=0.02):
    return (rng.standard_normal(shape, dtype=np.float32) * scale)


def fill_spec(spec, d, n_mels, vocab, rng):
    """Assign random arrays to every weight in a ctranslate2 WhisperSpec."""
    ones, zeros = (lambda n: np.ones(n, np.float32)), (lambda n: np.zeros(n, np.float32))

    def ln(s):
        s.gamma, s.beta = ones(d), zeros(d)

    def lin(s, o, i):
        s.weight, s.bias = rand(rng, o, i), zeros(o)

    def ffn(s):
        ln(s.layer_norm)
        lin(s.linear_0, 4 * d, d)
        lin(s.linear_1, d, 4 * d)

    enc = spec.encoder
    enc.conv1.weight, enc.conv1.bias = rand(rng, d, n_mels, 3), zeros(d)
    enc.conv2.weight, enc.conv2.bias = rand(rng, d, d, 3), zeros(d)
    enc.position_encodings.encodings = rand(rng, N_AUDIO_CTX, d)
    ln(enc.layer_norm)
    for layer in enc.layer:
        ln(layer.self_attention.layer_norm)
        lin(layer.self_attention.linear[0], 3 * d, d)
        lin(layer.self_attention.linear[1], d, d)
        ffn(layer.ffn)

    dec = spec.decoder
    dec.embeddings.weight = rand(rng, vocab, d)
    dec.position_encodings.encodings = rand(rng, N_TEXT_CTX, d)
    ln(dec.layer_norm)
    dec.projection.weight = dec.embeddings.weight
    for layer in dec.layer:
        ln(layer.self_attention.layer_norm)
        lin(layer.self_attention.linear[0], 3 * d, d)
        lin(layer.self_attention.linear[1], d, d)
        ln(layer.attention.layer_norm)
        lin(layer.attention.linear[0], d, d)
        lin(layer.attention.linear[1], 2 * d, d)
        lin(layer.attention.linear[2], d, d)
        ffn(layer.ffn)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--shape", choices=sorted(SHAPES), default="tiny")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--whisper-src", required=True, type=Path,
                    help="openai-whisper 'whisper' package dir (contains tokenizer.py, assets/)")
    ap.add_argument("--quantization", default="int8", help="weights stored as (int8/float16/float32)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    from ctranslate2.specs import whisper_spec

    d, n_mels, el, eh, dl, dh, n_lang = SHAPES[args.shape]
    args.out.mkdir(parents=True, exist_ok=True)
    encoding = load_whisper_encoding(args.whisper_src, n_lang)
    tok = build_tokenizer_json(encoding, args.out)
    vocab = encoding.n_vocab
    tokens = [tok.id_to_token(i) for i in range(vocab)]
    if any(t is None for t in tokens):
        raise SystemExit("tokenizer has holes in its id space")

    spec = whisper_spec.WhisperSpec(el, eh, dl, dh)
    fill_spec(spec, d, n_mels, vocab, np.random.default_rng(args.seed))
    spec.register_vocabulary(tokens)
    sot = encoding.encode_single_token("<|startoftranscript|>")
    spec.config.lang_ids = list(range(sot + 1, sot + 1 + n_lang))
    spec.config.suppress_ids = []
    spec.config.suppress_ids_begin = [220, encoding.eot_token]
    spec.config.alignment_heads = [(dl // 2 + i, h) for i in range(dl - dl // 2) for h in range(dh)]
    spec.validate()
    spec.optimize(quantization=args.quantization)
    spec.save(str(args.out))

    (args.out / "preprocessor_config.json").write_text(json.dumps({
        "feature_size": n_mels, "sampling_rate": 16000, "hop_length": 160,
        "chunk_length": 30, "n_fft": 400, "n_samples": 480000, "nb_max_frames": 3000,
    }))
    print(f"Wrote random-weight '{args.shape}' model to {args.out}")


if __name__ == "__main__":
    sys.exit(main())
