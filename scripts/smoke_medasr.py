"""Offline runtime/API smoke test with tiny RANDOM weights, never an accuracy test.

Validates CUDA, audio preprocessing, CTC generation and decoding while gated model
access is pending. No downloads, microphone input or practice recordings are used.
"""
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
import argparse
import numpy as np
import torch
from transformers import LasrCTCConfig, LasrEncoderConfig, LasrFeatureExtractor, LasrForCTC, LasrProcessor, LasrTokenizer


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    args = ap.parse_args()
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    encoder = LasrEncoderConfig(hidden_size=32, num_hidden_layers=2,
        num_attention_heads=4, intermediate_size=64, subsampling_conv_channels=8)
    tokenizer = LasrTokenizer(extra_ids=0)
    processor = LasrProcessor(LasrFeatureExtractor(), tokenizer)
    model = LasrForCTC(LasrCTCConfig(encoder_config=encoder,
        vocab_size=len(tokenizer))).to(args.device).eval()
    samples = .05 * np.sin(2*np.pi*220*np.arange(32000,dtype=np.float32)/16000)
    inputs = processor(audio=samples, sampling_rate=16000, return_tensors="pt", padding=True)
    inputs = {k:v.to(args.device) for k,v in inputs.items()}
    with torch.inference_mode():
        tokens = model.generate(**inputs)
    text = processor.batch_decode(tokens, skip_special_tokens=True)
    assert tokens.ndim == 2 and tokens.shape[0] == 1 and isinstance(text[0],str)
    if args.device == "cuda":
        torch.cuda.synchronize()
    print("PASS: random-weight LASR preprocessing/generation/CTC decode on", args.device)
    print("This is an API smoke check; it says nothing about trained MedASR accuracy or speed.")


if __name__ == "__main__":
    main()
