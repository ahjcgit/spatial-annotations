#!/usr/bin/env python3
"""Local experiment collection, manual ground truth, paired replay and CSV reports."""
import argparse
import json
from pathlib import Path
import threading
import time

from eval_core import analyze, plan, read_rows, record, replay, validate_annotation, write_json

ROOT = Path(__file__).resolve().parents[1]


def create_app(root, source='http://127.0.0.1:8014'):
    import httpx
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    app = FastAPI(docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
    root = Path(root).resolve()
    state = {'busy': False, 'message': 'Ready', 'error': None}
    lock = threading.Lock()

    def folder(trial_id):
        value = (root/'trials'/trial_id).resolve()
        if value.parent != root/'trials' or not (value/'meta.json').is_file():
            raise HTTPException(404, 'Unknown trial')
        return value

    def origin(request):
        if request.headers.get('origin') != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Use the local evaluation page')

    def start_job(action):
        with lock:
            if state['busy']: raise HTTPException(409, 'Wait for the current operation')
            state.update(busy=True, error=None, message='Starting', progress={})
        def worker():
            try:
                action()
            except Exception as error:
                state.update(error=str(error), message='Operation failed')
            finally:
                state['busy'] = False
        threading.Thread(target=worker, daemon=True).start()
        return {'ok': True}

    @app.get('/')
    def home(): return FileResponse(ROOT/'demo/evaluation.html')

    @app.get('/api/state')
    def status():
        trials = []
        for path in sorted((root/'trials').glob('*/meta.json')):
            meta = json.loads(path.read_text())
            annotations = path.parent/'annotations.json'
            values = json.loads(annotations.read_text()) if annotations.exists() else {}
            meta['annotated'] = len(values)
            trials.append(meta)
        return {**state, 'plan': json.loads((root/'plan.json').read_text()), 'trials': trials, 'root': str(root)}

    @app.get('/api/preview')
    def preview():
        try:
            with httpx.Client(timeout=6, trust_env=False) as client:
                result = client.get(source+'/api/status'); result.raise_for_status(); packet = result.json()
            return {k: packet.get(k) for k in ('phase', 'image', 'frameId', 'pipelineMs')}
        except Exception as error:
            raise HTTPException(503, str(error))

    @app.post('/api/record/{plan_id}')
    async def capture(plan_id: str, request: Request):
        origin(request)
        body = await request.json()
        condition = next((t for t in json.loads((root/'plan.json').read_text())['trials'] if t['id'] == plan_id), None)
        if not condition: raise HTTPException(404, 'Unknown planned condition')
        condition = {**condition, 'notes': str(body.get('notes', ''))[:2000]}
        def action():
            for seconds in (3, 2, 1):
                state['message'] = f'Get ready — recording in {seconds}'; time.sleep(1)
            state['message'] = 'Recording — keep performing the specified condition'
            result = record(root, condition, source, lambda p: state.update(progress=p))
            state.update(message=f"{result['status']}: {result['frames']} fresh frames", last_trial=result['trial_id'])
        return start_job(action)

    @app.get('/api/trial/{trial_id}')
    def trial(trial_id: str):
        path = folder(trial_id)
        return {'meta': json.loads((path/'meta.json').read_text()), 'frames': read_rows(path/'frames.jsonl'),
                'annotations': json.loads((path/'annotations.json').read_text())}

    @app.get('/api/image/{trial_id}/{index}')
    def image(trial_id: str, index: int):
        path = folder(trial_id)/'frames'/f'{index:05d}.jpg'
        if not path.is_file(): raise HTTPException(404)
        return FileResponse(path, media_type='image/jpeg')

    @app.post('/api/annotation/{trial_id}/{index}')
    async def annotation(trial_id: str, index: int, request: Request):
        origin(request); path = folder(trial_id)
        if not (path/'frames'/f'{index:05d}.jpg').is_file(): raise HTTPException(404)
        try: value = validate_annotation(await request.json())
        except ValueError as error: raise HTTPException(422, str(error))
        with lock:
            if state['busy']: raise HTTPException(409, 'Wait for recording or analysis to finish')
            values = json.loads((path/'annotations.json').read_text()); values[str(index)] = value
            write_json(path/'annotations.json', values)
        return value

    @app.post('/api/include/{trial_id}')
    async def include(trial_id: str, request: Request):
        origin(request); path = folder(trial_id); body = await request.json()
        if not isinstance(body.get('include'), bool) or not str(body.get('reason', '')).strip():
            raise HTTPException(422, 'Provide include true/false and a reason; retain failed detections')
        with lock:
            if state['busy']: raise HTTPException(409, 'Wait for the current operation')
            meta = json.loads((path/'meta.json').read_text())
            meta.update(include=body['include'], exclusion_reason=str(body['reason'])[:2000]); write_json(path/'meta.json', meta)
        return {'ok': True}

    @app.post('/api/replay')
    def benchmark(request: Request):
        origin(request)
        def action():
            state['message'] = 'Pausing live inference, then replaying both models…'
            with httpx.Client(timeout=15, trust_env=False, headers={'Origin': source.rstrip('/')}) as client:
                current = client.get(source+'/api/status'); current.raise_for_status()
                resume = current.json().get('phase') in ('live', 'no_match', 'capturing', 'stalled')
                result = client.post(source+'/api/action/stop'); result.raise_for_status()
                try:
                    time.sleep(1)
                    replay(root)
                    analyze(root)
                    state['message'] = 'Replay complete. Review ground truth, then export the report.'
                finally:
                    if resume: client.post(source+'/api/action/run').raise_for_status()
        return start_job(action)

    @app.post('/api/analyze')
    def report(request: Request):
        origin(request)
        def action():
            result = analyze(root)
            from eval_plots import plots
            plots(root)
            state['message'] = f"Report exported: {len(result['conditions'])} fully reviewed condition/model groups"
        return start_job(action)

    @app.get('/api/report')
    def latest():
        file = root/'report/summary.json'
        return json.loads(file.read_text()) if file.exists() else {'message': 'No report yet'}

    @app.get('/report/{name}')
    def artifact(name: str):
        if name not in ('frame_metrics.csv', 'trial_metrics.csv', 'condition_metrics.csv', 'summary.json', 'detection.png', 'timing.png', 'placement.png'):
            raise HTTPException(404)
        file = root/'report'/name
        if not file.is_file(): raise HTTPException(404, 'Generate the report after reviewing frames')
        return FileResponse(file)
    return app


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['plan', 'serve', 'replay', 'analyze'])
    p.add_argument('--root', type=Path, default=ROOT/'artifacts/evaluation/pilot')
    p.add_argument('--profile', choices=['pilot', 'full'], default='pilot')
    p.add_argument('--source', default='http://127.0.0.1:8014')
    p.add_argument('--port', type=int, default=8017)
    p.add_argument('--repeats', type=int, default=1)
    a = p.parse_args()
    if a.repeats < 1: p.error('--repeats must be positive')
    a.root.mkdir(parents=True, exist_ok=True)
    if a.command in ('plan', 'serve') and not (a.root/'plan.json').exists(): write_json(a.root/'plan.json', plan(a.profile))
    if a.command == 'plan': print(a.root/'plan.json')
    elif a.command == 'replay':
        print('Offline replay: stop live inference and other CPU workloads before timing. The UI Replay button pauses the demo automatically.', flush=True)
        print(json.dumps(replay(a.root, repeats=a.repeats), indent=2))
    elif a.command == 'analyze':
        analyze(a.root)
        from eval_plots import plots
        plots(a.root); print(a.root/'report')
    else:
        import uvicorn
        uvicorn.run(create_app(a.root, a.source.rstrip('/')), host='127.0.0.1', port=a.port, access_log=False)

if __name__ == '__main__': main()
