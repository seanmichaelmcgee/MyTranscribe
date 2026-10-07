"""One explicitly selected blind OpenRouter audio comparison in the existing queue."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import ssl
import time
import urllib.request

import frontier_audio_queue as shared

MODEL = 'google/gemini-3.5-transcribe'
MODELS = (MODEL, 'openai/gpt-transcribe', 'openai/gpt-4o-transcribe')
PROTOCOL = 'blind-openrouter-stt-v1'
ENDPOINT = 'https://openrouter.ai/api/v1/audio/transcriptions'
DEFAULT_ROOT = shared.ROOT/'results_1060/accuracy_program_20261004/frontier_bridge/data'


def remote(path, key, ca_bundle=None, *, model=MODEL):
    if model not in MODELS:
        raise ValueError('Select a documented transcription model')
    path = Path(path)
    data = path.read_bytes()
    if path.suffix.lower() != '.wav' or not 0 < len(data) <= shared.MAX_BYTES:
        raise ValueError('Bounded local WAV required')
    payload = dict(model=model, input_audio=dict(data=base64.b64encode(data).decode('ascii'), format='wav'))
    request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode('utf-8'), method='POST',
        headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json',
                 'User-Agent': 'MyTranscribe-fictional-baseline/1'})
    context = ssl.create_default_context(cafile=str(ca_bundle) if ca_bundle else None)
    opener = urllib.request.build_opener(shared.NoRedirects(), urllib.request.HTTPSHandler(context=context))
    started = time.monotonic()
    with opener.open(request, timeout=90) as response:
        raw = response.read(shared.MAX_RESPONSE+1)
        if len(raw) > shared.MAX_RESPONSE:
            raise ValueError('Response size limit')
        result = json.loads(raw)
        if not isinstance(result, dict) or not isinstance(result.get('text'), str) or not result['text'].strip():
            raise ValueError('No valid independent transcript')
        return dict(response=result, request_id=response.headers.get('x-request-id'),
            uploaded_audio_sha256=hashlib.sha256(data).hexdigest(), requested_model=model,
            returned_model=result.get('model'), duration_s=time.monotonic()-started,
            endpoint=ENDPOINT, protocol=PROTOCOL, model_snapshot_known=False,
            provider_adapter_sha256=shared.sha256(Path(__file__)),
            request_options=dict(prompt=None, keywords=None, context=None, reference=None))


class Queue(shared.Queue):
    def __init__(self, folder=DEFAULT_ROOT, *, model=MODEL):
        if model not in MODELS:
            raise ValueError('Select a documented transcription model')
        super().__init__(folder, model=model, protocol=PROTOCOL)

    def enqueue(self, source, fictional=False):
        if Path(source).suffix.lower() != '.wav':
            raise ValueError('This comparison requires the captured WAV')
        return super().enqueue(source, fictional)

    def once(self, transport=None, env=None, ca_bundle=None, job_id=None):
        if job_id is None:
            raise ValueError('Select one saved headset job; no queue draining')
        env = os.environ if env is None else env
        # Reuse local durability bookkeeping; this key reaches only remote above.
        auth = {'OPENAI_API_KEY': env.get('OPENROUTER_API_KEY')}
        if transport is None:
            transport = lambda path, key, ca: remote(path, key, ca, model=self.model)
        return super().once(transport=transport, env=auth, ca_bundle=ca_bundle, job_id=job_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--model', choices=MODELS, default=MODEL)
    commands = parser.add_subparsers(dest='command', required=True)
    enqueue = commands.add_parser('enqueue')
    enqueue.add_argument('file', type=Path)
    enqueue.add_argument('--fictional', action='store_true')
    commands.add_parser('status')
    run = commands.add_parser('run')
    run.add_argument('--execute', action='store_true')
    run.add_argument('--id', dest='job_id', required=True)
    run.add_argument('--ca-bundle', type=Path)
    args = parser.parse_args()
    queue = Queue(args.root, model=args.model)
    try:
        if args.command == 'enqueue':
            print(json.dumps(queue.enqueue(args.file, args.fictional)))
        elif args.command == 'status':
            print(json.dumps([r for r in queue.statuses() if (r['model'],r['protocol']) == (args.model,PROTOCOL)], indent=2))
        else:
            if not args.execute:
                raise ValueError('Upload execution must be explicitly selected')
            print(json.dumps(queue.once(job_id=args.job_id, ca_bundle=args.ca_bundle)))
    finally:
        queue.close()


if __name__ == '__main__':
    main()
