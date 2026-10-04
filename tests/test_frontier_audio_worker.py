"""Offline worker checks; no real child or provider calls."""
import datetime as dt
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('frontier_worker',Path(__file__).resolve().parents[1]/'scripts'/'frontier_audio_worker.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

TEST_ROOT=Path(__file__).resolve().parents[1]/'results_1060'/'frontier_queue_tests'
TEST_ROOT.mkdir(parents=True,exist_ok=True)

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='worker_test_',dir=TEST_ROOT))
        self.clock_value=dt.datetime(2026,10,4,18,tzinfo=dt.timezone.utc)
    def tearDown(self):
        assert self.root.parent==TEST_ROOT and self.root.name.startswith('worker_test_')
        shutil.rmtree(self.root)
    def clock(self):return self.clock_value
    def sleep(self,seconds):self.clock_value+=dt.timedelta(seconds=seconds)
    def forbidden(self,*args):raise AssertionError('Unapproved provider call')
    def watch(self,**kwargs):
        return module.watch(self.root/'data','test',1,2,clock=self.clock,sleep=self.sleep,
            request=kwargs.pop('request',self.forbidden),**kwargs)
    def test_missing_auth_never_calls_provider(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            self.assertEqual(self.watch()['phase'],'blocked_auth')
    def test_restart_preserves_original_deadline(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):first=self.watch()
        self.clock_value+=dt.timedelta(minutes=2)
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'}):second=self.watch()
        self.assertEqual(first['deadline_utc'],second['deadline_utc'])
        self.assertEqual(second['phase'],'deadline_reached')
    def test_stop_file_prevents_processing(self):
        data=self.root/'data';data.mkdir();(data/'STOP').touch()
        self.assertEqual(self.watch()['phase'],'stopped')
    def test_duplicate_watcher_cannot_acquire_ownership(self):
        data=self.root/'data'
        with module.qmod.RunLock(data/'.watch.lock'):
            with self.assertRaises(RuntimeError):self.watch()
    def test_timeout_terminates_only_created_child(self):
        class Child:
            returncode=None
            terminated=False
            def poll(self):return self.returncode
            def terminate(self):self.terminated=True;self.returncode=-1
            def wait(self,timeout):return self.returncode
            def kill(self):raise AssertionError('Normal termination should be sufficient')
        child=Child()
        with patch.object(module.subprocess,'Popen',return_value=child) as launch, \
             patch.object(module,'kill_owned_tree',side_effect=lambda proc:proc.terminate()) as cleanup:
            outcome=module.owned_request(self.root,None,module.now()-dt.timedelta(seconds=1))
        self.assertEqual(outcome,'interrupted_owned_child');self.assertTrue(child.terminated)
        self.assertEqual(launch.call_count,1);cleanup.assert_called_once_with(child)
    def test_idle_wait_ends_at_deadline(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'}):result=self.watch()
        self.assertEqual(result['phase'],'deadline_reached')
    def test_budget_stops_at_two_requests(self):
        q=module.qmod.Queue(self.root/'data')
        for index in range(3):
            path=self.root/(str(index)+'.wav');path.write_bytes(('fixture'+str(index)).encode())
            q.enqueue(path,True)
        q.close();calls=[]
        def fake_request(folder,ca,deadline):
            calls.append(1);q=module.qmod.Queue(folder)
            try:q.once(lambda *args:dict(response=dict(text='test-only')),{'OPENAI_API_KEY':'test-only'})
            finally:q.close()
            return 'finished'
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'}):
            result=self.watch(request=fake_request)
        self.assertEqual(result['phase'],'request_budget_reached');self.assertEqual(len(calls),2)

if __name__=='__main__':unittest.main()
