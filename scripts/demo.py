#!/usr/bin/env python3
"""Non-destructive demo: isolated persistent DB, tests, seed, QR fixtures, APK and evidence.
Keep this process running; Ctrl-C stops only its backend. Re-run to reuse the dataset.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8011)
    p.add_argument('--output',type=Path,default=ROOT/'artifacts/demo')
    p.add_argument('--skip-build',action='store_true',help='Use an already built APK; still run backend and HTTP checks')
    p.add_argument('--verify-and-exit',action='store_true')
    args=p.parse_args()
    if not 1024<=args.port<=65535 or args.port==5173: p.error('Use an unreserved port 1024..65535 (never 5173).')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    with socket.socket() as probe:
        try: probe.bind(('0.0.0.0',args.port))
        except OSError: p.error(f'Port {args.port} is occupied. Choose --port; no existing service was stopped.')
    def run(command, name, cwd=ROOT):
        with (output/(name+'.log')).open('w') as log:
            result=subprocess.run(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            print((output/(name+'.log')).read_text());raise RuntimeError(f'{name} failed; see {output}')
        print(f'PASS: {name}',flush=True)
    url=f'http://127.0.0.1:{args.port}'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(output/'demo.db')}
    server=None; log=(output/'backend.log').open('a')
    def start():
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--app-dir',str(ROOT/'backend'),
            '--host','0.0.0.0','--port',str(args.port),'--no-access-log'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        for _ in range(100):
            if process.poll() is not None: raise RuntimeError('Backend exited; inspect backend.log')
            try:
                if httpx.get(url+'/health',timeout=1).json()=={'status':'ok'}: return process
            except (httpx.HTTPError,ValueError): pass
            time.sleep(.1)
        process.terminate();process.wait(timeout=10);raise RuntimeError('Backend health timeout')
    def stop(process):
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill();process.wait()
    try:
        server=start();print(f'Backend listening on 0.0.0.0:{args.port}',flush=True)
        run([sys.executable,'-m','pytest','-q','--junitxml='+str(output/'backend-tests.xml')],'backend-tests',ROOT/'backend')
        run([sys.executable,'-m','pytest','-q','scripts/tests'],'script-tests')
        data=output/'demo-data.json'
        if not data.exists(): run([sys.executable,'scripts/e2e.py','--url',url,'--output',str(data)],'seed-e2e')
        else: print('Reusing existing local credentials and database; no reset.',flush=True)
        # Use a reachable LAN URL in the saved dataset, including emulator/browser tests.
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            try: sock.connect(('192.0.2.1',9));lan=sock.getsockname()[0]
            except OSError: lan='127.0.0.1'
        dataset=json.loads(data.read_text());dataset['backend']=f'http://{lan}:{args.port}'
        data.write_text(json.dumps(dataset,indent=2)+'\n');data.chmod(0o600)
        for obj in dataset['objects']:
            run([sys.executable,'scripts/generate_markers.py','--count','1','--marker-id',obj['marker_id'],'--output',str(output/'markers')],'marker-'+obj['name'].replace(' ','-'))
        run([sys.executable,'scripts/qr_frames.py','synthetic','--data',str(data),'--output',str(output/'qr-frames')],'qr-fixtures')
        run([sys.executable,'scripts/verify_markers.py','--data',str(data),'--markers',str(output/'markers'),'--output',str(output/'qr-frames')],'marker-png-fixtures')
        verify=[sys.executable,'scripts/e2e.py','--url',url,'--output',str(data),'--verify']
        run(verify+['--evidence',str(output/'http-before-restart.jsonl')],'http-before-restart')
        stop(server);server=start()
        run(verify+['--evidence',str(output/'http-after-restart.jsonl')],'http-after-restart')
        apk=ROOT/'android/app/build/outputs/apk/debug/app-debug.apk'
        if not args.skip_build:
            run([str(ROOT/'android/gradlew'),'-p',str(ROOT/'android'),'testDebugUnitTest','lintDebug','assembleDebug',
                '-PreplayDir='+str(output/'qr-frames'),'-PdemoData='+str(data),'--console=plain'],'android-checks')
        if not apk.is_file(): raise RuntimeError(f'APK missing: {apk}; run android/gradlew -p android assembleDebug')
        samples=list(output.glob('http-*.jsonl'))+list((output/'qr-frames').glob('replay-results.jsonl'))
        run([sys.executable,'scripts/summarize_telemetry.py',*map(str,samples),'--output',str(output/'summary.json')],'summary')
        print(f'\nCompanion: {dataset["backend"]}\nCredentials: {data}\nPrint: {output}/markers/print.html\nAPK: {apk}\nEvidence: {output}\nBackend restart persistence verified. Ctrl-C stops this backend; data is retained.',flush=True)
        if not args.verify_and_exit:
            while server.poll() is None: time.sleep(1)
            raise RuntimeError('Backend exited unexpectedly')
    except KeyboardInterrupt: print('\nStopping demo backend; keeping all data.')
    finally: stop(server);log.close()

if __name__=='__main__': main()
