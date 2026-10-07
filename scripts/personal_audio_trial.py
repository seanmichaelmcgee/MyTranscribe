"""Opt-in exact-PCM replay and isolated vocabulary-prompt trial; no microphone/API."""
import argparse
import hashlib
from pathlib import Path
import sys
import wave

from asr_trial_common import ROOT, load_corpus, local_result_path, sha256
import trial_asr


def prompt_only_pipeline(factory, style, *, count=None, correction_files=None,
                         candidate=None, topics=None):
    """Keep baseline correction rules even when the prompt lexicon changes."""
    builder, post = factory(style, count=count, env={}, correction_files=correction_files)
    if candidate is not None:
        builder, _ = factory(style, count=count, correction_files=correction_files,
            env={'MYTRANSCRIBE_VOCAB_FILES': str(candidate), 'MYTRANSCRIBE_VOCAB_TOPICS': topics})
    return builder, post


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('whisper','medasr'), default='whisper')
    parser.add_argument('--manifest', action='append', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--chunk-seconds', type=int, choices=(20,30), default=30)
    parser.add_argument('--candidate-vocabulary', type=Path)
    parser.add_argument('--candidate-topics')
    args, remaining = parser.parse_known_args(argv)
    if any(flag in remaining for flag in ('--repeats','--only','--engine','--realtime')):
        parser.error('One offline pass over the explicitly frozen manifest scope required')
    if bool(args.candidate_vocabulary) != bool(args.candidate_topics):
        parser.error('Candidate vocabulary and topics must be specified together')
    if args.backend != 'whisper' and args.candidate_vocabulary:
        parser.error('Prompt vocabulary candidate applies only to Whisper')
    out = local_result_path(args.out)
    if out.exists():
        raise ValueError('Preserve prior trial; choose a new output')
    entries, corpus = load_corpus(args.manifest)
    inputs = []
    for entry in entries:
        with wave.open(str(entry['_path']), 'rb') as w:
            if (w.getframerate(),w.getnchannels(),w.getsampwidth()) != (16000,1,2):
                raise ValueError('Original 16-kHz mono PCM16 recording required')
            pcm = w.readframes(w.getnframes())
        inputs.append(dict(clip_id=entry['clip_id'], path=entry['_path'],
            audio_sha256=entry['audio_sha256'], pcm=pcm,
            pcm_sha256=hashlib.sha256(pcm).hexdigest(), frames=len(pcm)//2))
    candidate = local_result_path(args.candidate_vocabulary) if args.candidate_vocabulary else None
    candidate_sha = sha256(candidate) if candidate else None
    adapter_sha = sha256(Path(__file__))
    stream_calls = []
    original_stream, original_write = trial_asr.ReplayStream, trial_asr.write_json
    sys.path.insert(0,str(ROOT/'src'))
    import vocab
    import chunked_transcriber
    original_pipeline = vocab.build_text_pipeline
    original_transcriber = chunked_transcriber.ChunkedTranscriber

    class ExactStream(original_stream):
        def __init__(self, historical_pcm, realtime=False):
            if len(stream_calls) >= len(inputs):
                raise ValueError('Unexpected repeated or extra waveform')
            item = inputs[len(stream_calls)]
            if realtime or len(historical_pcm) != len(item['pcm']) or sha256(item['path']) != item['audio_sha256']:
                raise ValueError('Waveform scope or identity changed')
            stream_calls.append({k:item[k] for k in ('clip_id','audio_sha256','pcm_sha256','frames')})
            super().__init__(item['pcm'], realtime=False)

    def pipeline(style, count=None, env=None, correction_files=None):
        return prompt_only_pipeline(original_pipeline, style, count=count,
            correction_files=correction_files, candidate=candidate, topics=args.candidate_topics)

    def transcriber(*positional, **kwargs):
        kwargs['chunk_target_s'] = float(args.chunk_seconds)
        return original_transcriber(*positional, **kwargs)

    def checkpoint(path, record):
        if record.get('completed'):
            if len(stream_calls) != len(inputs) or record['corpus_sha256'] != corpus:
                raise ValueError('Incomplete or changed replay scope')
            if sha256(Path(__file__)) != adapter_sha or (candidate and sha256(candidate) != candidate_sha):
                raise ValueError('Candidate/adapter changed during trial')
            if load_corpus(args.manifest)[1] != corpus:
                raise ValueError('Corpus changed during trial')
        record['personal_audio_trial'] = dict(adapter_sha256=adapter_sha,
            original_pcm=True, streams=list(stream_calls),
            candidate_vocabulary_sha256=candidate_sha, candidate_topics=args.candidate_topics,
            adaptation='prompt vocabulary only' if candidate else 'unchanged bundled pipeline',
            baseline_postprocessor_preserved=True, reference_supplied_to_recognizer=False)
        record['chunk_target_s'] = args.chunk_seconds
        record['config']['chunk_target_s'] = args.chunk_seconds
        original_write(path,record)

    trial_asr.ReplayStream, trial_asr.write_json = ExactStream, checkpoint
    if candidate:
        vocab.build_text_pipeline = pipeline
    try:
        common = [arg for path in args.manifest for arg in ('--manifest',str(path))]
        common.extend(['--out',str(out)])
        if args.backend == 'whisper':
            import whisper_runtime_trial
            return whisper_runtime_trial.main(['--chunk-seconds',str(args.chunk_seconds),*common,*remaining])
        import medasr_decoder_trial
        chunked_transcriber.ChunkedTranscriber = transcriber
        return medasr_decoder_trial.main([*common,*remaining])
    finally:
        trial_asr.ReplayStream, trial_asr.write_json = original_stream, original_write
        vocab.build_text_pipeline = original_pipeline
        chunked_transcriber.ChunkedTranscriber = original_transcriber


if __name__ == '__main__':
    raise SystemExit(main())
