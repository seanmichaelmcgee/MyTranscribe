"""Offline tests: blind audio, correct provider, immutable results and selected scope."""
import base64
import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import openrouter_audio_queue as module


class OpenRouterAudioTests(unittest.TestCase):
    def setUp(self):
        self.parent = module.shared.ROOT/'results_1060/frontier_queue_tests'
        self.parent.mkdir(parents=True, exist_ok=True)
        self.folder = Path(tempfile.mkdtemp(prefix='router_test_', dir=self.parent))
        self.audio = self.folder/'fixture.wav'
        with wave.open(str(self.audio),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x01\x00'*1600)
        self.queue = module.Queue(self.folder/'data')

    def tearDown(self):
        self.queue.close()
        assert self.folder.parent == self.parent and self.folder.name.startswith('router_test_')
        shutil.rmtree(self.folder)

    def test_blind_stt_payload_contains_exact_wav_no_reference(self):
        class Response:
            headers = {'x-request-id':'test-request'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'{"text":"Independent audio transcript","usage":{"cost":0.001}}'
        captured=[]
        class Opener:
            def open(self,request,timeout):
                captured.append((request,timeout));return Response()
        with patch.object(module.urllib.request,'build_opener',return_value=Opener()):
            result=module.remote(self.audio,'synthetic-only')
        request,timeout=captured[0]
        payload=json.loads(request.data)
        self.assertEqual(request.full_url,module.ENDPOINT)
        self.assertEqual(set(payload),{'model','input_audio'})
        self.assertEqual(base64.b64decode(payload['input_audio']['data']),self.audio.read_bytes())
        self.assertEqual(timeout,90)
        self.assertNotIn('synthetic-only',json.dumps(result))

    def test_same_queue_skips_openai_jobs_and_preserves_completed_router_result(self):
        other=module.shared.Queue(self.folder/'data')
        try:
            older=other.enqueue(self.audio,True)
            selected=self.queue.enqueue(self.audio,True)
            self.assertNotEqual(older['id'],selected['id'])
            calls=[]
            def fake(path,key,ca):
                calls.append(key);return dict(response=dict(text='Independent router text'))
            result=self.queue.once(fake,{'OPENROUTER_API_KEY':'router-test','OPENAI_API_KEY':'wrong-test'},job_id=selected['id'])
            self.assertEqual(result['state'],'complete')
            self.assertEqual(self.queue.once(fake,{'OPENROUTER_API_KEY':'router-test'},job_id=selected['id'])['state'],'complete')
            self.assertEqual(calls,['router-test'])
            historical=next(r for r in other.statuses() if r['id']==older['id'])
            self.assertEqual((historical['state'],historical['attempts']),('queued',0))
            self.assertEqual(other.once(env={})['state'],'blocked_auth')
            with self.assertRaises(ValueError):self.queue.once(fake,env={},job_id=older['id'])
        finally:
            other.close()

    def test_openai_key_alone_cannot_authorize_router_and_no_fifo_execution(self):
        selected=self.queue.enqueue(self.audio,True)
        def forbidden(*args):raise AssertionError('Wrong provider credential used')
        self.assertEqual(self.queue.once(forbidden,{'OPENAI_API_KEY':'wrong'},job_id=selected['id'])['state'],'blocked_auth')
        with self.assertRaises(ValueError):self.queue.once(forbidden,env={})
        with self.assertRaises(ValueError):module.shared.Queue.once(self.queue,env={},job_id=selected['id'])

    def test_openai_selection_preserves_gemini_job_and_binds_request_model(self):
        gemini = self.queue.enqueue(self.audio,True)
        openai = module.Queue(self.folder/'data',model='openai/gpt-transcribe')
        try:
            selected = openai.enqueue(self.audio,True)
            self.assertNotEqual(selected['id'],gemini['id'])
            calls=[]
            def fake(path,key,ca,*,model):
                calls.append(model);return dict(response=dict(text='Independent OpenAI transcript'))
            with patch.object(module,'remote',side_effect=fake):
                self.assertEqual(openai.once(env={'OPENROUTER_API_KEY':'test'},job_id=selected['id'])['state'],'complete')
            self.assertEqual(calls,['openai/gpt-transcribe'])
            with self.assertRaises(ValueError):openai.once(env={},job_id=gemini['id'])
            preserved=next(r for r in self.queue.statuses() if r['id']==gemini['id'])
            self.assertEqual((preserved['state'],preserved['attempts']),('queued',0))
        finally:
            openai.close()
        with self.assertRaises(ValueError):module.Queue(self.folder/'data',model='unapproved/model')

    def test_openai_payload_uses_selected_model_with_same_blind_audio(self):
        class Response:
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):return b'{"text":"OpenAI test transcript"}'
        captured=[]
        class Opener:
            def open(self,request,timeout):captured.append(request);return Response()
        with patch.object(module.urllib.request,'build_opener',return_value=Opener()):
            saved=module.remote(self.audio,'test-only',model='openai/gpt-transcribe')
        payload=json.loads(captured[0].data)
        self.assertEqual(payload['model'],'openai/gpt-transcribe')
        self.assertEqual(set(payload),{'model','input_audio'})
        self.assertEqual(base64.b64decode(payload['input_audio']['data']),self.audio.read_bytes())
        self.assertEqual(saved['requested_model'],'openai/gpt-transcribe')
