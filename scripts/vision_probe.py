#!/usr/bin/env python3
"""Call the same detector used by Android on a supplied photo or one webcam frame."""
import argparse,json,time
from pathlib import Path
import httpx

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('artifacts/vision/demo-data.json'))
    source=p.add_mutually_exclusive_group(required=True);source.add_argument('--image',type=Path);source.add_argument('--webcam',type=int)
    p.add_argument('--output',type=Path,default=Path('artifacts/vision/probe.json'));a=p.parse_args()
    data=json.loads(a.data.read_text())
    if a.image:
        from PIL import Image,ImageOps
        import io
        image=ImageOps.exif_transpose(Image.open(a.image)).convert('RGB');image.thumbnail((1600,1600))
        buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=90);raw=buffer.getvalue()
        environment='offline_photo'
    else:
        import cv2
        camera=cv2.VideoCapture(a.webcam)
        try:
            if not camera.isOpened(): raise SystemExit('Webcam unavailable; no camera test claimed.')
            frame=None
            for _ in range(20):
                ok,frame=camera.read()
                if not ok: raise SystemExit('Webcam read failed.')
            ok,encoded=cv2.imencode('.jpg',frame)
            if not ok: raise SystemExit('Frame encode failed.')
            raw=encoded.tobytes();environment='real_webcam_frame'
        finally: camera.release()
    with httpx.Client(base_url=data['backend'],trust_env=False,timeout=30) as client:
        user=data['users'][0]
        r=client.post('/auth/login',json={k:user[k] for k in ['username','password']});r.raise_for_status()
        headers={'Authorization':'Bearer '+r.json()['access_token'],'Content-Type':'image/jpeg'}
        started=time.monotonic_ns();r=client.post('/vision/detect',headers=headers,content=raw);r.raise_for_status()
        report={'environment':environment,'http_ms':(time.monotonic_ns()-started)/1e6,**r.json()}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__': main()
