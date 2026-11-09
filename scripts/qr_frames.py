#!/usr/bin/env python3
"""Deterministic synthetic camera fixtures, or real webcam captures for Kotlin/ZXing replay.
No desktop decoder is used. manifest.json is consumed by ReplayTest in Android JVM tests.
"""
import argparse
import json
import time
from pathlib import Path
from uuid import UUID

from PIL import Image, ImageEnhance
import qrcode

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'


def save_frame(output, image, name, expected, environment, rotation=0, **metadata):
    output.mkdir(parents=True, exist_ok=True)
    filename = name + '.png'
    gray = image.convert('L')
    gray.save(output / filename)
    (output / (name+'.gray')).write_bytes(gray.tobytes())
    return dict(file=filename, luminance_file=name+'.gray', width=image.width, height=image.height, rotation=rotation,
                expected_marker=expected, environment=environment, **metadata)


def synthetic(output, markers):
    records = []
    def save(image, name, expected, rotation=0):
        records.append(save_frame(output, image, name, expected, 'synthetic_image_jvm', rotation))
    for label, marker in zip(('A','B'), markers):
        qr = qrcode.make('spatial:v1:' + marker, box_size=8, border=4).convert('L')
        for side in (140, 280):
            patch = qr.resize((side,side), Image.Resampling.NEAREST)
            frame = Image.new('L',(640,480),255); frame.paste(patch,((640-side)//2,(480-side)//2))
            for rotation in (0,90,180,270):
                save(frame.rotate(rotation,expand=True),f'{label}-{side}-r{rotation}',marker,rotation)
        frame = Image.new('L',(800,600),255); frame.paste(qr,((800-qr.width)//2,(600-qr.height)//2))
        save(frame.rotate(18,fillcolor=255),f'{label}-angle18',marker)
        save(ImageEnhance.Brightness(frame).enhance(.35),f'{label}-dim',marker)
    save(Image.new('L',(640,480),255),'blank',None)
    for name, payload in [('unrelated','https://example.org'),('invalid','spatial:v2:'+A),('bare-uuid',A)]:
        save(qrcode.make(payload).convert('L'),name,None)
    (output / 'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
    print(f'Generated {len(records)} synthetic fixtures in {output}')


def webcam(args):
    try:
        import cv2
    except ImportError:
        raise SystemExit('Install optional capture dependency: pip install opencv-python')
    camera = cv2.VideoCapture(args.device)
    if not camera.isOpened():
        camera.release()
        raise SystemExit(f'Webcam {args.device} unavailable; no real-camera samples recorded. Use synthetic mode.')
    records = []
    manifest = args.output / 'manifest.json'
    if manifest.exists(): records = json.loads(manifest.read_text())
    try:
        for index in range(args.frames):
            deadline = time.monotonic()+args.interval
            while True:
                ok, frame = camera.read()
                if not ok: raise RuntimeError('Webcam frame acquisition failed')
                if not args.headless:
                    cv2.imshow('QR replay capture - q cancels, space captures',frame)
                    key = cv2.waitKey(20) & 255
                    if key == ord('q'): return
                    if key == ord(' '): break
                if time.monotonic() >= deadline: break
            gray = cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
            name = f'{args.label}-{time.time_ns()}-{index:03d}'
            records.append(save_frame(args.output,Image.fromarray(gray),name,args.expected,
                'offline_real_webcam',args.rotation,captured_at=time.time(),conditions=args.conditions))
            manifest.write_text(json.dumps(records,indent=2)+'\n')
            print(f'Captured {name}: {gray.shape[1]}x{gray.shape[0]}')
    finally:
        camera.release()
        if not args.headless: cv2.destroyAllWindows()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['synthetic','webcam'])
    p.add_argument('--output',type=Path,default=Path('artifacts/qr-frames'))
    p.add_argument('--data',type=Path,help='demo-data.json: use its registered marker UUIDs')
    p.add_argument('--device',type=int,default=0)
    p.add_argument('--frames',type=int,default=5)
    p.add_argument('--interval',type=float,default=2)
    p.add_argument('--label',default='webcam')
    p.add_argument('--expected',type=lambda x:str(UUID(x)),help='omit for blank/unrelated QR')
    p.add_argument('--conditions',default='unspecified; record distance and lighting')
    p.add_argument('--rotation',type=int,choices=[0,90,180,270],default=0,help='clockwise display rotation; pixels remain raw')
    p.add_argument('--headless',action='store_true')
    args=p.parse_args()
    if args.frames < 1 or args.interval < 0 or Path(args.label).name != args.label: p.error('Invalid capture arguments')
    if args.mode == 'webcam': webcam(args)
    else:
        markers=[o['marker_id'] for o in json.loads(args.data.read_text())['objects']] if args.data else [A,B]
        synthetic(args.output,markers)

if __name__=='__main__': main()
