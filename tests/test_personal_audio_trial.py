"""Candidate isolation and original multi-file PCM, without microphone or GPU."""
import hashlib
from pathlib import Path
import sys
import wave

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import personal_audio_trial as module


def test_prompt_candidate_does_not_replace_baseline_correction_pipeline():
    base_builder, base_post, candidate_builder, candidate_post = object(),object(),object(),object()
    calls=[]
    def factory(style,**kwargs):
        calls.append(kwargs)
        return (candidate_builder,candidate_post) if kwargs['env'] else (base_builder,base_post)
    builder,post=module.prompt_only_pipeline(factory,'frozen style',candidate=Path('personal.txt'),topics='personal_core')
    assert builder is candidate_builder and post is base_post
    assert calls[0]['env']=={}
    assert calls[1]['env']=={'MYTRANSCRIBE_VOCAB_FILES':'personal.txt','MYTRANSCRIBE_VOCAB_TOPICS':'personal_core'}


def test_multi_file_replay_restores_original_pcm_and_preserves_scope(tmp_path,monkeypatch):
    import whisper_runtime_trial
    entries=[]
    for index,pcm in enumerate((b'\xff\x7f\x00\x80',b'\x01\x00\xfe\xff')):
        path=tmp_path/f'{index}.wav'
        with wave.open(str(path),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(pcm)
        entries.append(dict(clip_id=str(index),_path=path,audio_sha256=module.sha256(path)))
    monkeypatch.setattr(module,'load_corpus',lambda *args:(entries,'frozen-corpus'))
    monkeypatch.setattr(module,'local_result_path',lambda p:p)
    saved=[]
    monkeypatch.setattr(module.trial_asr,'write_json',lambda path,record:saved.append(record))
    original=module.trial_asr.ReplayStream
    def runtime(args):
        assert '--chunk-seconds' in args
        for index,expected in enumerate((b'\xff\x7f\x00\x80',b'\x01\x00\xfe\xff')):
            stream=module.trial_asr.ReplayStream(b'\x00'*4)
            assert stream.read(2)==expected
        module.trial_asr.write_json(tmp_path/'out.json',dict(completed=True,corpus_sha256='frozen-corpus',config={}))
        return 0
    monkeypatch.setattr(whisper_runtime_trial,'main',runtime)
    assert module.main(['--manifest',str(tmp_path/'manifest.json'),'--out',str(tmp_path/'out.json')])==0
    assert module.trial_asr.ReplayStream is original
    metadata=saved[0]['personal_audio_trial']
    assert [s['clip_id'] for s in metadata['streams']]==['0','1']
    assert metadata['streams'][0]['pcm_sha256']==hashlib.sha256(b'\xff\x7f\x00\x80').hexdigest()


def test_med_asr_chunk_override_is_scoped_and_explicit(tmp_path,monkeypatch):
    import medasr_decoder_trial
    import chunked_transcriber
    monkeypatch.setattr(module,'load_corpus',lambda *args:([],'empty-test-only'))
    monkeypatch.setattr(module,'local_result_path',lambda p:p)
    captured=[]
    def original(*args,**kwargs):captured.append(kwargs);return object()
    monkeypatch.setattr(chunked_transcriber,'ChunkedTranscriber',original)
    def decoder(args):
        chunked_transcriber.ChunkedTranscriber(chunk_target_s=20)
        return 0
    monkeypatch.setattr(medasr_decoder_trial,'main',decoder)
    module.main(['--backend','medasr','--manifest','frozen.json','--out',str(tmp_path/'out.json'),'--chunk-seconds','30'])
    assert captured[0]['chunk_target_s']==30
    assert chunked_transcriber.ChunkedTranscriber is original


def test_med_asr_rejects_prompt_candidate_before_loading_audio(tmp_path):
    with pytest.raises(SystemExit):
        module.main(['--backend','medasr','--manifest','unused.json','--out',str(tmp_path/'out.json'),
            '--candidate-vocabulary','candidate.txt','--candidate-topics','personal_core'])
