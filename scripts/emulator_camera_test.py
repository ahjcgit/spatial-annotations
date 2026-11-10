#!/usr/bin/env python3
"""Actual Camera2 → ZXing → HTTP → frozen UI using a GENERATED emulator scene; no physical-camera claim."""
import argparse
import json
import subprocess
import time
from pathlib import Path
from PIL import Image
import qrcode
from android_ui import AndroidUI
from emulator_scene import set_scene


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--serial',required=True)
    p.add_argument('--data',type=Path,default=Path('artifacts/demo/demo-data.json'))
    p.add_argument('--output',type=Path,default=Path('artifacts/emulator-camera'))
    p.add_argument('--container');p.add_argument('--token-file',type=Path)
    p.add_argument('--camera-image-file',type=Path,help='Shared path supplied to emulator -camera-back imagefile:PATH; replaces file before each camera open')
    p.add_argument('--fixture-x',type=float,default=.25,help='Horizontal image fraction; .25 fits this API-30 imagefile camera crop')
    p.add_argument('--trials',type=int,default=5);p.add_argument('--negatives',action='store_true')
    p.add_argument('--rapid-rescan',action='store_true',help='Exercise repeated camera start/stop and recovery')
    args=p.parse_args()
    if args.trials < 1 or not 0 < args.fixture_x < 1: p.error('Use positive trials and fixture-x between 0 and 1')
    if not args.serial.startswith('emulator-'): p.error('This test requires a disposable Android emulator')
    data=json.loads(args.data.read_text());args.output.mkdir(parents=True,exist_ok=True)
    ui=AndroidUI(args.serial);ui.login(data,data['users'][0]);rows=[]
    def scene(image):
        if args.camera_image_file:
            import shutil
            shutil.copyfile(image,args.camera_image_file)
        else: set_scene(args.serial,image,args.container,args.token_file)
    apk_path=ui.device.shell('pm path org.spatial.annotations').output.strip().split('package:')[-1]
    apk_sha256=ui.device.shell('sha256sum '+apk_path).output.split()[0]
    started=time.time()
    try:
        for trial in range(args.trials):
            for obj in data['objects']:
                image=args.output/(obj['marker_id']+'.png')
                patch=qrcode.make('spatial:v1:'+obj['marker_id'],box_size=8,border=4).convert('RGB')
                canvas=Image.new('RGB',(1280,1280),'white');canvas.paste(patch,(int(1280*args.fixture_x)-patch.width//2,(1280-patch.height)//2));canvas.save(image)
                scene(image)
                ui.click('START CAMERA / SCAN NEXT OBJECT')
                if ui.device(text='While using the app').wait(timeout=1): ui.device(text='While using the app').click()
                ui.expect('Camera QR detected',timeout=18)
                ui.expect(obj['name'])
                ui.expect('3 authorized notes' if obj==data['objects'][0] else '0 authorized notes')
                assert ui.device(descriptionContains='Frozen recognized frame.').exists
                if obj==data['objects'][1]: assert 'private note on mug A' not in ui.device.dump_hierarchy()
                ui.screenshot(args.output/f'{trial}-{obj["name"].replace(" ","-")}.png')
                rows.append(dict(trial=trial,object=obj['name'],environment='android_emulator_generated_camera',passed=True))
                print(f'PASS: generated Camera2 scan {trial+1} {obj["name"]}, frozen feature highlights and correct HTTP result',flush=True)
        if args.negatives:
            for label in ('blank','unrelated'):
                path=args.output/(label+'.png')
                canvas=Image.new('RGB',(1280,1280),'white')
                if label=='unrelated':
                    patch=qrcode.make('https://example.org').convert('RGB');canvas.paste(patch,(int(1280*args.fixture_x)-patch.width//2,(1280-patch.height)//2))
                canvas.save(path)
                scene(path)
                ui.click('START CAMERA / SCAN NEXT OBJECT');ui.expect('No marker detected in 15 seconds',timeout=20)
                assert 'private note on mug A' not in ui.device.dump_hierarchy()
                ui.screenshot(args.output/(label+'-timeout.png'))
                rows.append(dict(trial=label,environment='android_emulator_generated_camera',passed=True,expected='recognition_timeout'))
                print('PASS: '+label+' correctly rejected; recoverable timeout',flush=True)
        if args.rapid_rescan:
            blank=args.output/'rapid-blank.png';Image.new('RGB',(1280,1280),'white').save(blank);scene(blank)
            for attempt in range(8):
                ui.click('START CAMERA / SCAN NEXT OBJECT');ui.click('STOP CAMERA')
                assert ui.device(text='Camera stopped').wait(timeout=3)
                assert not ui.device(descriptionContains='Frozen recognized frame.').exists
            rows.append(dict(trial='rapid-rescan',environment='android_emulator_generated_camera',passed=True,cycles=8))
            scene(args.output/(data['objects'][0]['marker_id']+'.png'))
            ui.click('START CAMERA / SCAN NEXT OBJECT');ui.expect('Camera QR detected');ui.expect('3 authorized notes')
            ui.expect(data['objects'][0]['name']);ui.screenshot(args.output/'after-rapid-rescan.png')
            rows.append(dict(trial='rescan-recovery',environment='android_emulator_generated_camera',passed=True))
            print('PASS: eight rapid start/stop cycles clear frames; subsequent camera QR lookup recovers',flush=True)
    except Exception:
        ui.device.screenshot(str(args.output/'failure.png'))
        rows.append(dict(environment='android_emulator_generated_camera',passed=False,failure='UI assertion failed; see log and failure.png'))
        raise
    finally:
        (args.output/'results.json').write_text(json.dumps(dict(started=started,apk_sha256=apk_sha256,trials=rows),indent=2)+'\n')
        result=subprocess.run(['adb','-s',args.serial,'logcat','-d','-v','raw','-s','SpatialTelemetry:I'],capture_output=True,text=True,check=True)
        # Keep only this invocation's actual application telemetry and explicitly identify the camera source.
        from datetime import datetime
        records=[]
        for line in result.stdout.splitlines():
            if not line.startswith('{'): continue
            row=json.loads(line)
            if datetime.fromisoformat(row['timestamp'].replace('Z','+00:00')).timestamp() < started: continue
            row['environment']='android_emulator_generated_camera'
            records.append(row)
        (args.output/'telemetry.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))

if __name__=='__main__': main()
