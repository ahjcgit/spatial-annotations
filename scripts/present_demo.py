#!/usr/bin/env python3
"""Local, no-login presentation dashboard controlling the explicit USB demo device."""
import argparse
import json
import subprocess
from urllib.parse import urlsplit
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

ROOT = Path(__file__).resolve().parents[1]

def create_app(adb, serial, package):
    app = FastAPI(docs_url=None, redoc_url=None)
    def device(*args):
        return subprocess.run([adb, '-s', serial, *args], capture_output=True, timeout=12, check=True).stdout
    @app.get('/')
    def home(): return FileResponse(ROOT/'demo/index.html')
    @app.get('/api/status')
    def status():
        try:
            result = json.loads(device('exec-out', 'run-as', package, 'cat', 'files/demo-result.json'))
            result['deviceConnected'] = True
            return result
        except (subprocess.SubprocessError, ValueError):
            return {'phase':'offline', 'message':'Connect the glasses, then run the demo.', 'deviceConnected':False}
    @app.get('/api/frame')
    def frame():
        try: return Response(device('exec-out','run-as',package,'cat','files/demo-frame.jpg'),media_type='image/jpeg',headers={'Cache-Control':'no-store'})
        except subprocess.SubprocessError: raise HTTPException(404,'No camera image yet')
    @app.post('/api/action/{command}')
    def action(command: str, request: Request):
        if request.headers.get('origin') not in (str(request.base_url).rstrip('/'),):
            raise HTTPException(403,'Open the local demo page to control the glasses')
        if command not in ('run','stop','mug-a','mug-b','alice','bob','fallback','optical','left','right','up','down','larger','smaller','eyes-in','eyes-out','reset'): raise HTTPException(404)
        try:
            if command == 'run':
                device('shell','input','keyevent','KEYCODE_WAKEUP')
                device('shell','wm','dismiss-keyguard')
            if command == 'run':
                device('shell','am','start','-n',package+'/org.spatial.annotations.DemoActivity','--es','command',command)
            else:
                device('shell','am','broadcast','-a','org.spatial.annotations.DEMO_COMMAND','-p',package,'--es','command',command)
            return {'ok':True}
        except subprocess.SubprocessError: raise HTTPException(503,'Could not reach the glasses. Check the USB connection.')
    app.mount('/static',StaticFiles(directory=ROOT/'demo'),name='static')
    return app

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb',default='adb');p.add_argument('--serial',required=True)
    p.add_argument('--package',default='org.spatial.annotations.branchdemo');p.add_argument('--port',type=int,default=8014)
    p.add_argument('--data',type=Path,help='Provision local demo accounts and USB backend from this private dataset file')
    p.add_argument('--install-apk',type=Path,help='Install the separate presentation APK, preserving existing apps')
    a=p.parse_args()
    def adb(*args, **kwargs):
        return subprocess.run([a.adb,'-s',a.serial,*args],check=True,timeout=30,**kwargs)
    if a.install_apk:
        adb('install','-r',str(a.install_apk))
    if a.data:
        data=json.loads(a.data.read_text())
        endpoint=urlsplit(data['backend'])
        if endpoint.scheme != 'http' or not endpoint.port:
            p.error('Presentation setup expects a local HTTP backend with an explicit port')
        data['backend']=f'http://127.0.0.1:{endpoint.port}'
        adb('reverse',f'tcp:{endpoint.port}',f'tcp:{endpoint.port}')
        adb('shell','run-as',a.package,'mkdir','-p','files')
        # Credentials travel on stdin into app-private storage, never command arguments or public assets.
        adb('shell','run-as',a.package,'sh','-c',"'cat > files/demo-config.json'",input=json.dumps(data).encode())
        adb('shell','input','keyevent','KEYCODE_WAKEUP')
        adb('shell','wm','dismiss-keyguard')
        adb('shell','am','start','-n',a.package+'/org.spatial.annotations.DemoActivity')
    uvicorn.run(create_app(a.adb,a.serial,a.package),host='127.0.0.1',port=a.port,access_log=False)
