#!/usr/bin/env python3
"""Actual Android Camera2 -> local NanoDet -> explicit instance confirmation -> authorized notes.
Camera uses a public-domain photograph fixture, not a host webcam or RayNeo device.
"""
import argparse,json,shutil,subprocess,time
from pathlib import Path
from PIL import Image
from android_ui import AndroidUI

def main():
    p=argparse.ArgumentParser();p.add_argument('--serial',default='emulator-5554');p.add_argument('--data',type=Path,default=Path('artifacts/vision/demo-data.json'))
    p.add_argument('--photo',type=Path,default=Path('artifacts/vision/coffee.png'));p.add_argument('--camera-image-file',type=Path,required=True)
    p.add_argument('--output',type=Path,default=Path('artifacts/vision/emulator'));a=p.parse_args()
    if not a.serial.startswith('emulator-'): p.error('Disposable emulator required')
    a.output.mkdir(parents=True,exist_ok=True);data=json.loads(a.data.read_text());ui=AndroidUI(a.serial)
    canvas=Image.new('RGB',(1280,1280),'white');photo=Image.open(a.photo).convert('RGB');photo.thumbnail((600,500))
    canvas.paste(photo,(320-photo.width//2,640-photo.height//2));scene=a.output/'photo-scene.png';canvas.save(scene)
    ui.login(data,data['users'][0]);shutil.copyfile(scene,a.camera_image_file)
    remote='/sdcard/model-demo.mp4'
    recording=subprocess.Popen(['adb','-s',a.serial,'shell','screenrecord','--time-limit','175',remote])
    apk_path=ui.device.shell('pm path org.spatial.annotations').output.strip().split('package:')[-1]
    apk_sha256=ui.device.shell('sha256sum '+apk_path).output.split()[0]
    started=time.time();rows=[]
    try:
        time.sleep(2)
        for obj,count in zip(data['objects'],[3,0]):
            ui.click('DETECT OBJECTS · MODEL')
            assert ui.device(text='Select detected category').wait(timeout=25)
            assert ui.device(textStartsWith='cup ·').exists
            ui.device(textStartsWith='cup ·').click()
            assert ui.device(text='Confirm which cup').wait(timeout=15)
            assert ui.device(textStartsWith='Mug A ·').exists and ui.device(textStartsWith='Mug B ·').exists
            ui.device(textStartsWith=obj['name']+' ·').click()
            ui.expect(f'{count} authorized notes');ui.expect('MODEL + YOUR CONFIRMATION');ui.expect(obj['name'])
            assert ui.device(descriptionContains='Frozen model frame. 1 detected object boxes.').exists
            ui.screenshot(a.output/(obj['name'].replace(' ','-')+'.png'));time.sleep(6)
            rows.append({'object':obj['name'],'notes':count,'passed':True,'identity':'explicit_user_confirmation'})
        blank=a.output/'blank.png';Image.new('RGB',(1280,1280),'white').save(blank);shutil.copyfile(blank,a.camera_image_file)
        ui.click('DETECT OBJECTS · MODEL');ui.expect('No confident object found',timeout=25)
        assert not ui.device(text='Confirm which cup').exists
        ui.screenshot(a.output/'blank-result.png');rows.append({'case':'blank','passed':True});time.sleep(5)
    except Exception:
        ui.device.screenshot(str(a.output/'failure.png'));rows.append({'passed':False});raise
    finally:
        result=subprocess.run(['adb','-s',a.serial,'shell','pidof','screenrecord'],capture_output=True,text=True)
        if result.stdout.strip(): subprocess.run(['adb','-s',a.serial,'shell','kill','-2',result.stdout.strip()],check=True)
        recording.wait(timeout=20)
        subprocess.run(['adb','-s',a.serial,'pull',remote,str(a.output/'model-demo-raw.mp4')],check=True)
        (a.output/'results.json').write_text(json.dumps({'apk_sha256':apk_sha256,'environment':'android_emulator_photo_camera','photo':'scikit-image coffee CC0 Rachel Michetti','tests':rows},indent=2))
        logs=subprocess.run(['adb','-s',a.serial,'logcat','-d','-v','raw','-s','SpatialVision:I'],capture_output=True,text=True,check=True)
        from datetime import datetime
        events=[]
        for line in logs.stdout.splitlines():
            if not line.startswith('{'): continue
            event=json.loads(line)
            if 'timestamp' in event and datetime.fromisoformat(event['timestamp'].replace('Z','+00:00')).timestamp() >= started:
                event['environment']='android_emulator_photo_camera';events.append(event)
        (a.output/'model-log.txt').write_text(''.join(json.dumps(event)+'\n' for event in events))
    caption=a.output/'caption.txt';caption.write_text('Camera2 -> local NanoDet -> human-confirmed object -> notes\nAndroid emulator / CC0 photo replay / no physical glasses or webcam')
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(a.output/'model-demo-raw.mp4'),'-vf',f'pad=iw:ih+100:0:100:black,drawtext=textfile={caption}:fontcolor=white:fontsize=19:x=12:y=12','-r','30','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p',str(a.output/'model-demo.mp4')],check=True)
    print('PASS: model-camera Mug A 3 / Mug B 0 / blank rejected; actual model inference, explicit confirmation')
if __name__=='__main__': main()
