"""Bounded, stoppable background queue processor. Launch only after API setup."""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from overnight_medasr import kill_owned_tree

spec=importlib.util.spec_from_file_location('frontier_queue',Path(__file__).with_name('frontier_audio_queue.py'))
qmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(qmod)

def now():return dt.datetime.now(dt.timezone.utc)

def attempt_count(queue):return sum(row['attempts'] for row in queue.statuses())

def owned_request(folder,ca,deadline):
    command=[sys.executable,str(Path(__file__).with_name('frontier_audio_queue.py')),'--root',str(folder),
        'run','--execute','--max-jobs','1']
    if ca:command.extend(['--ca-bundle',str(ca)])
    process=subprocess.Popen(command,cwd=qmod.ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name=='nt' else 0,
        start_new_session=os.name!='nt')
    request_deadline=min(deadline,now()+dt.timedelta(seconds=120))
    try:
        while process.poll() is None:
            if (folder/'STOP').exists() or now()>=request_deadline:
                kill_owned_tree(process)
                return 'interrupted_owned_child'
            time.sleep(.5)
        return 'finished' if process.returncode==0 else 'child_failed'
    finally:
        if process.poll() is None:
            kill_owned_tree(process)

def watch(folder,session,minutes,max_requests,ca=None,clock=now,sleep=time.sleep,request=owned_request):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',session):raise ValueError('Invalid session name')
    if not 1<=minutes<=120 or not 1<=max_requests<=10:raise ValueError('Bounded 1..120 minutes and 1..10 requests required')
    queue=qmod.Queue(folder);state_path=queue.folder/('worker_'+session+'.json')
    identity=dict(worker_sha256=qmod.sha256(Path(__file__)),queue_sha256=qmod.sha256(Path(qmod.__file__)),
        model=qmod.MODEL,protocol=qmod.PROTOCOL)
    try:
        with qmod.RunLock(queue.folder/'.watch.lock'):
            if state_path.exists():
                state=json.loads(state_path.read_text(encoding='utf-8'))
                if state['max_requests']!=max_requests:raise ValueError('Cannot change the original request budget on resume')
                if state.get('identity')!=identity:raise ValueError('Worker/configuration changed; review before a new session')
            else:
                state=dict(schema='frontier-worker-v1',session=session,created_at_utc=clock().isoformat(),
                    deadline_utc=(clock()+dt.timedelta(minutes=minutes)).isoformat(),max_requests=max_requests,
                    attempt_cap=attempt_count(queue)+max_requests,queue=str(queue.folder),identity=identity)
            deadline=dt.datetime.fromisoformat(state['deadline_utc'])
            def save(phase):
                state.update(phase=phase,updated_at_utc=clock().isoformat(),owner_pid=os.getpid(),
                    attempts_total=attempt_count(queue))
                qmod.write_json(state_path,state)
                return dict(state)
            while True:
                if (queue.folder/'STOP').exists():return save('stopped')
                if clock()>=deadline:return save('deadline_reached')
                if attempt_count(queue)>=state['attempt_cap']:return save('request_budget_reached')
                rows=queue.statuses()
                if any(row['state']=='in_flight' for row in rows):
                    # Recover an orphaned result without authorizing another request.
                    queue.once(env={});rows=queue.statuses()
                if not os.environ.get('OPENAI_API_KEY'):
                    queue.once(env={});return save('blocked_auth')
                if not any(row['state'] in ('queued','blocked_auth') for row in rows):
                    save('waiting_for_approved_audio')
                    sleep(min(15,max(0,(deadline-clock()).total_seconds())))
                    continue
                save('processing_one_approved_audio')
                previous_attempts={row['id']:row['attempts'] for row in rows}
                outcome=request(queue.folder,ca,deadline)
                if outcome!='finished':return save(outcome)
                rows=queue.statuses()
                if any(row['state'] in ('failed','uncertain') or
                    (row['state']=='blocked_auth' and row['attempts']>previous_attempts.get(row['id'],0)) for row in rows):
                    return save('review_required')
    finally:queue.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=qmod.DEFAULT_ROOT)
    parser.add_argument('--session',required=True)
    parser.add_argument('--minutes',type=int,default=120)
    parser.add_argument('--max-requests',type=int,default=2)
    parser.add_argument('--ca-bundle',type=Path)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:raise ValueError('Execution must be explicitly selected')
    print(json.dumps(watch(args.root,args.session,args.minutes,args.max_requests,args.ca_bundle),indent=2))

if __name__=='__main__':main()
