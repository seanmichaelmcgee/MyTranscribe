"""No remote calls: durable recovery, duplicate suppression and blind payload tests."""
import json, shutil, tempfile, unittest, wave
from pathlib import Path
import importlib.util
spec=importlib.util.spec_from_file_location('frontier_queue',Path(__file__).resolve().parents[1]/'scripts'/'frontier_audio_queue.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

TEST_ROOT=Path(__file__).resolve().parents[1]/'results_1060'/'frontier_queue_tests'
TEST_ROOT.mkdir(parents=True,exist_ok=True)

class DurableQueueTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='queue_test_',dir=TEST_ROOT))
        self.audio=self.root/'fixture.wav'
        with wave.open(str(self.audio),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x00\x00'*1600)
        self.queue=module.Queue(self.root/'data')
    def tearDown(self):
        self.queue.close()
        # Explicit checked test-owned path, same shell/runtime end to end.
        assert self.root.parent==TEST_ROOT and self.root.name.startswith('queue_test_')
        shutil.rmtree(self.root)
    def test_deduplicate_preserve_and_require_fictional(self):
        with self.assertRaises(ValueError):self.queue.enqueue(self.audio)
        first=self.queue.enqueue(self.audio,True);second=self.queue.enqueue(self.audio,True)
        self.assertEqual(first['id'],second['id']);self.assertEqual(len(self.queue.statuses()),1)
    def test_auth_block_survives_reopen_without_network(self):
        self.queue.enqueue(self.audio,True)
        def forbidden(*args):raise AssertionError('Network attempted without credentials')
        self.assertEqual(self.queue.once(transport=forbidden,env={})['state'],'blocked_auth')
        self.queue.close();self.queue=module.Queue(self.root/'data')
        self.assertEqual(self.queue.statuses()[0]['state'],'blocked_auth')
    def test_success_is_saved_and_not_resubmitted(self):
        row=self.queue.enqueue(self.audio,True);calls=[]
        def fake(path,key,ca):
            calls.append((path,key,ca));return dict(response=dict(text='Independent test text'),request_id='test-request')
        self.assertEqual(self.queue.once(fake,{'OPENAI_API_KEY':'test-key'})['state'],'complete')
        self.assertEqual(self.queue.once(fake,{'OPENAI_API_KEY':'test-key'})['state'],'idle')
        self.assertEqual(len(calls),1)
        saved=json.loads((self.root/'data'/'results'/(row['id']+'.json')).read_text())
        self.assertEqual(saved['audio_sha256'],row['audio_sha'])
        self.assertNotIn('test-key',json.dumps(saved))
    def test_ambiguous_crash_requires_explicit_retry(self):
        row=self.queue.enqueue(self.audio,True)
        self.queue._update(row['id'],'in_flight')
        def forbidden(*args):raise AssertionError('Duplicate remote request')
        self.assertEqual(self.queue.once(forbidden,{'OPENAI_API_KEY':'test-key'})['state'],'idle')
        self.assertEqual(self.queue.statuses()[0]['state'],'uncertain')
        self.queue.retry(row['id']);self.assertEqual(self.queue.statuses()[0]['state'],'queued')
    def test_changed_audio_is_never_sent(self):
        row=self.queue.enqueue(self.audio,True)
        (self.root/'data'/'audio'/(row['id']+'.wav')).write_bytes(b'changed')
        def forbidden(*args):raise AssertionError('Tampered audio uploaded')
        self.assertEqual(self.queue.once(forbidden,{'OPENAI_API_KEY':'test-key'})['state'],'failed')
    def test_saved_response_recovers_without_reupload(self):
        row=self.queue.enqueue(self.audio,True);self.queue._update(row['id'],'in_flight')
        target=self.root/'data'/'results'/(row['id']+'.json');target.parent.mkdir()
        target.write_text(json.dumps(dict(schema=module.PROTOCOL,requested_model=module.MODEL,
            audio_sha256=row['audio_sha'],remote=dict(response=dict(text='saved')))))
        self.assertEqual(self.queue.once(env={})['state'],'idle')
        self.assertEqual(self.queue.statuses()[0]['state'],'complete')

    def test_wrong_config_saved_response_is_never_accepted(self):
        row=self.queue.enqueue(self.audio,True);self.queue._update(row['id'],'in_flight')
        target=self.root/'data'/'results'/(row['id']+'.json');target.parent.mkdir()
        target.write_text(json.dumps(dict(schema=module.PROTOCOL,requested_model='different-model',
            audio_sha256=row['audio_sha'],remote=dict(response=dict(text='saved')))))
        self.assertEqual(self.queue.once(env={})['state'],'idle')
        self.assertEqual(self.queue.statuses()[0]['state'],'uncertain')

    def test_deleted_audio_is_visible_failure_not_upload(self):
        row=self.queue.enqueue(self.audio,True)
        (self.root/'data'/'audio'/(row['id']+'.wav')).unlink()
        def forbidden(*args):raise AssertionError('Missing audio uploaded')
        self.assertEqual(self.queue.once(forbidden,{'OPENAI_API_KEY':'test-key'})['state'],'failed')

    def test_config_change_cannot_submit_old_queued_model(self):
        row=self.queue.enqueue(self.audio,True)
        with self.queue.db:
            self.queue.db.execute('UPDATE jobs SET model=? WHERE id=?',('different-model',row['id']))
        def forbidden(*args):raise AssertionError('Wrong configuration submitted')
        self.assertEqual(self.queue.once(forbidden,{'OPENAI_API_KEY':'test-only'})['state'],'failed')

    def test_upload_identity_mismatch_stays_uncertain(self):
        self.queue.enqueue(self.audio,True)
        def fake(*args):return dict(response=dict(text='saved'),uploaded_audio_sha256='wrong')
        self.assertEqual(self.queue.once(fake,{'OPENAI_API_KEY':'test-only'})['state'],'uncertain')

    def test_remote_payload_is_blind_and_request_is_bounded(self):
        from unittest.mock import patch
        class Response:
            headers={'x-request-id':'fake-request'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):
                self.limit=limit;return b'{"text":"fake independent transcript"}'
        response=Response();captured=[]
        class Opener:
            def open(self,request,timeout):
                captured.append((request,timeout));return response
        with patch.object(module.urllib.request,'build_opener',return_value=Opener()):
            result=module.remote(self.audio,'synthetic-secret')
        request,timeout=captured[0]
        self.assertEqual(request.full_url,module.ENDPOINT)
        self.assertEqual(timeout,90)
        self.assertEqual(response.limit,module.MAX_RESPONSE+1)
        self.assertEqual(result['uploaded_audio_sha256'],module.sha256(self.audio))
        self.assertIn(b'name="model"',request.data)
        self.assertIn(b'name="file"',request.data)
        for forbidden in (b'name="prompt"',b'name="context"',b'name="keywords"'):
            self.assertNotIn(forbidden,request.data)
        self.assertNotIn('synthetic-secret',json.dumps(result))

    def test_redirect_never_carries_auth_to_another_host(self):
        with self.assertRaises(module.urllib.error.URLError):
            module.NoRedirects().redirect_request(None,None,None,None,None,None)

if __name__=='__main__':unittest.main()
