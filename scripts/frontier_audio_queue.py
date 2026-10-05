"""Development-only durable audio baseline queue; no expected transcript inputs.

This opt-in tool uses the documented OpenAI file-transcription endpoint.
No network is used by enqueue/status/tests. Upload execution is explicit and
requires an environment key. It never watches or uploads ordinary-app capture.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from overnight_medasr import RunLock
from asr_trial_common import sha256,write_json,local_result_path
DEFAULT_ROOT=ROOT/'results_1060'/'frontier_baselines'
ENDPOINT='https://api.openai.com/v1/audio/transcriptions'
MODEL='gpt-transcribe'
PROTOCOL='blind-file-transcription-v1'
MAX_BYTES=25_000_000
MAX_RESPONSE=2_000_000
EXTENSIONS={'.m4a','.mp3','.wav','.webm','.mp4','.mpeg','.mpga'}

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise urllib.error.URLError('Redirect prohibited')

def remote(file_path, key, ca_bundle=None):
    """Fixed TLS endpoint, no redirect, no hints, bounded file and response."""
    path=Path(file_path)
    data=path.read_bytes()
    if not 0<len(data)<=MAX_BYTES:raise ValueError('Upload size limit')
    boundary='frontier_'+uuid.uuid4().hex
    fields=(f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{MODEL}\r\n'
       f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio{path.suffix}"\r\n'
       'Content-Type: application/octet-stream\r\n\r\n').encode('ascii')
    body=fields+data+f'\r\n--{boundary}--\r\n'.encode('ascii')
    context=ssl.create_default_context(cafile=str(ca_bundle) if ca_bundle else None)
    opener=urllib.request.build_opener(NoRedirects(),urllib.request.HTTPSHandler(context=context))
    request=urllib.request.Request(ENDPOINT,data=body,method='POST',headers={
       'Authorization':'Bearer '+key,'Content-Type':'multipart/form-data; boundary='+boundary,
       'User-Agent':'MyTranscribe-fictional-baseline/1'})
    started=time.monotonic()
    with opener.open(request,timeout=90) as response:
        raw=response.read(MAX_RESPONSE+1)
        if len(raw)>MAX_RESPONSE:raise ValueError('Response size limit')
        result=json.loads(raw)
        if not isinstance(result,dict) or not isinstance(result.get('text'),str) or not result['text'].strip():
            raise ValueError('No valid remote transcript')
        return dict(response=result,request_id=response.headers.get('x-request-id'),
           uploaded_audio_sha256=hashlib.sha256(data).hexdigest(),
           requested_model=MODEL,returned_model=result.get('model'),
           duration_s=time.monotonic()-started,endpoint=ENDPOINT,protocol=PROTOCOL,
           request_options=dict(prompt=None,keywords=None,context=None),
           model_snapshot_known=False)

class Queue:
    def __init__(self,folder=DEFAULT_ROOT,*,model=MODEL,protocol=PROTOCOL):
        self.model,self.protocol=model,protocol
        self.folder=local_result_path(Path(folder));self.folder.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.folder/'queue.sqlite',timeout=15)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, audio_sha TEXT NOT NULL, suffix TEXT NOT NULL,
          model TEXT NOT NULL, protocol TEXT NOT NULL, state TEXT NOT NULL,
          created TEXT NOT NULL, updated TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
          outcome TEXT, result_sha TEXT, UNIQUE(audio_sha,model,protocol))''')
        self.db.commit()

    def close(self):
        self.db.close()

    def enqueue(self,source,fictional=False):
        if not fictional:raise ValueError('Only explicitly identified fictional development audio may be queued')
        source=Path(source).resolve(strict=True)
        source.relative_to(ROOT.parent)
        if source.drive.startswith('\\\\') or not source.is_file() or source.suffix.lower() not in EXTENSIONS:
            raise ValueError('Supported local development audio required')
        if not 0<source.stat().st_size<=MAX_BYTES:raise ValueError('Audio size limit')
        digest=sha256(source)
        identifier=hashlib.sha256((digest+'|'+self.model+'|'+self.protocol).encode()).hexdigest()
        existing=self.db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone()
        if existing:return dict(existing)
        copied=self.folder/'audio'/(identifier+source.suffix.lower());copied.parent.mkdir(exist_ok=True)
        if not copied.exists():
            temporary=copied.with_suffix(copied.suffix+'.partial')
            with source.open('rb') as incoming,temporary.open('xb') as output:shutil.copyfileobj(incoming,output)
            if sha256(source)!=digest or sha256(temporary)!=digest:
                temporary.unlink();raise ValueError('Audio changed during copy')
            os.replace(temporary,copied)
        if sha256(copied)!=digest:raise ValueError('Saved audio fingerprint mismatch')
        stamp=utc()
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO jobs(id,audio_sha,suffix,model,protocol,state,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                (identifier,digest,source.suffix.lower(),self.model,self.protocol,'queued',stamp,stamp))
        return dict(self.db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone())

    def statuses(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM jobs ORDER BY created,id')]

    def _update(self,identifier,state,outcome=None,result_sha=None):
        with self.db:
            self.db.execute('UPDATE jobs SET state=?,updated=?,outcome=?,result_sha=? WHERE id=?',
                (state,utc(),outcome,result_sha,identifier))

    def _validate_saved(self,row,saved):
        payload=json.loads(saved.read_text(encoding='utf-8'))
        if (payload.get('schema')!=row['protocol'] or
            payload.get('audio_sha256')!=row['audio_sha'] or
            payload.get('requested_model')!=row['model']):
            raise ValueError('Result identity mismatch')
        text=payload.get('remote',{}).get('response',{}).get('text')
        if not isinstance(text,str) or not text.strip():raise ValueError('Invalid saved transcript')

    def once(self,transport=None,env=None,ca_bundle=None,job_id=None):
        env=os.environ if env is None else env
        if transport is None:
            if (self.model,self.protocol)!=(MODEL,PROTOCOL):
                raise ValueError('A different provider requires its explicit transport')
            transport=remote
        if job_id is not None and not re.fullmatch(r'[0-9a-f]{64}',job_id):
            raise ValueError('Invalid selected job identity')
        with RunLock(self.folder/'.worker.lock'):
            # A process crash can leave an uncertain paid request. Never silently
            # resubmit it. A saved response can safely finish local bookkeeping.
            if job_id is None:
                recovery=self.db.execute("SELECT * FROM jobs WHERE state='in_flight' AND model=? AND protocol=?",(self.model,self.protocol)).fetchall()
            else:
                recovery=self.db.execute("SELECT * FROM jobs WHERE state='in_flight' AND id=? AND model=? AND protocol=?",(job_id,self.model,self.protocol)).fetchall()
            for row in recovery:
                saved=self.folder/'results'/(row['id']+'.json')
                if saved.exists():
                    try:
                        self._validate_saved(row,saved)
                    except (ValueError,TypeError,AttributeError):
                        self._update(row['id'],'uncertain','saved response invalid; review required')
                    else:self._update(row['id'],'complete','recovered saved result',sha256(saved))
                else:self._update(row['id'],'uncertain','interrupted request; explicit retry required')
            if job_id is None:
                row=self.db.execute("SELECT * FROM jobs WHERE state IN ('queued','blocked_auth') AND model=? AND protocol=? ORDER BY created,id LIMIT 1",(self.model,self.protocol)).fetchone()
            else:
                row=self.db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
                if row is None:raise ValueError('Selected job does not exist')
                if row['model']!=self.model or row['protocol']!=self.protocol:
                    raise ValueError('Selected job belongs to another model/protocol; unchanged')
                if row['state'] not in ('queued','blocked_auth'):
                    return dict(id=row['id'],state=row['state'])
            if row is None:return dict(state='idle')
            if row['model']!=self.model or row['protocol']!=self.protocol:
                if job_id is not None:
                    raise ValueError('Selected job belongs to another model/protocol; unchanged')
                self._update(row['id'],'failed','queued model/protocol differs from configured transport; review required')
                return dict(id=row['id'],state='failed')
            key=env.get('OPENAI_API_KEY')
            if not key:
                pending_rows=([row] if job_id is not None else self.db.execute("SELECT id FROM jobs WHERE state IN ('queued','blocked_auth') AND model=? AND protocol=?",(self.model,self.protocol)).fetchall())
                for pending in pending_rows:
                    self._update(pending['id'],'blocked_auth','missing configured API key')
                return dict(id=row['id'],state='blocked_auth')
            if row['attempts']>=3:
                self._update(row['id'],'failed','three-attempt maximum reached')
                return dict(id=row['id'],state='failed')
            audio=self.folder/'audio'/(row['id']+row['suffix'])
            if not audio.is_file() or sha256(audio)!=row['audio_sha']:
                self._update(row['id'],'failed','audio integrity mismatch')
                return dict(id=row['id'],state='failed')
            with self.db:
                self.db.execute("UPDATE jobs SET state='in_flight',updated=?,attempts=attempts+1 WHERE id=?",(utc(),row['id']))
            try:
                response=transport(audio,key,ca_bundle)
                if not isinstance(response,dict) or not isinstance(response.get('response',{}).get('text'),str) or not response['response']['text'].strip():
                    raise ValueError('Invalid transcript')
                if response.get('uploaded_audio_sha256',row['audio_sha'])!=row['audio_sha']:
                    raise ValueError('Uploaded audio fingerprint differs from queued input')
                saved=self.folder/'results'/(row['id']+'.json')
                if saved.exists():raise ValueError('Refusing to overwrite result')
                write_json(saved,dict(schema=row['protocol'],audio_sha256=row['audio_sha'],requested_model=row['model'],
                     returned_at_utc=utc(),prototype_sha256=sha256(Path(__file__)),remote=response,
                     note='Independent remote comparator, not human-certified ground truth. No expected wording was supplied.'))
                self._update(row['id'],'complete',result_sha=sha256(saved))
                return dict(id=row['id'],state='complete')
            except urllib.error.HTTPError as exc:
                # Save no server body, headers, request credentials or transcript to logs.
                state='blocked_auth' if exc.code in (401,403) else 'failed'
                self._update(row['id'],state,'HTTP status '+str(exc.code)+'; no automatic resubmission')
                return dict(id=row['id'],state=state)
            except Exception as exc:
                self._update(row['id'],'uncertain','request/local-save outcome unknown: '+type(exc).__name__)
                return dict(id=row['id'],state='uncertain')

    def retry(self,identifier):
        row=self.db.execute('SELECT * FROM jobs WHERE id=?',(identifier,)).fetchone()
        if row is None or row['state'] not in ('failed','uncertain'):raise ValueError('No retryable job')
        if row['attempts']>=3:raise ValueError('Three-attempt maximum')
        self._update(identifier,'queued','explicit retry requested')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    commands=parser.add_subparsers(dest='command',required=True)
    enqueue=commands.add_parser('enqueue');enqueue.add_argument('file',type=Path);enqueue.add_argument('--fictional',action='store_true')
    commands.add_parser('status')
    run=commands.add_parser('run');run.add_argument('--execute',action='store_true');run.add_argument('--ca-bundle',type=Path)
    run.add_argument('--max-jobs',type=int,default=1)
    run.add_argument('--id',dest='job_id',help='Only this saved job; leave historical queued audio untouched')
    retry=commands.add_parser('retry');retry.add_argument('id');retry.add_argument('--accept-possible-duplicate',action='store_true')
    args=parser.parse_args();queue=Queue(args.root)
    try:
        if args.command=='enqueue':print(json.dumps(queue.enqueue(args.file,args.fictional)))
        elif args.command=='status':print(json.dumps(queue.statuses(),indent=2))
        elif args.command=='retry':
            if not args.accept_possible_duplicate:raise ValueError('Explicit acknowledgement required for ambiguous retry')
            queue.retry(args.id);print('Retry queued')
        else:
            if not args.execute:raise ValueError('Upload execution must be explicitly selected')
            if not 1<=args.max_jobs<=10:raise ValueError('Bounded 1..10 jobs per run required')
            if args.job_id and args.max_jobs!=1:raise ValueError('A selected job requires --max-jobs 1')
            for _ in range(args.max_jobs):
                status=queue.once(ca_bundle=args.ca_bundle,job_id=args.job_id);print(json.dumps(status))
                if status['state']!='complete':break
    finally:queue.close()

if __name__=='__main__':main()
