#!/usr/bin/env python3
"""Record both authenticated Android users, excluding credential entry from footage."""
import argparse,json,subprocess,time
from pathlib import Path
import httpx
from android_ui import AndroidUI

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('artifacts/demo/demo-data.json'));p.add_argument('--serial',default='emulator-5554');p.add_argument('--output',type=Path,default=Path('artifacts/sharing-video'));a=p.parse_args()
    data=json.loads(a.data.read_text());a.output.mkdir(parents=True,exist_ok=True)
    ui=AndroidUI(a.serial); clips=[]; results=[]
    def adb(*args,**kw): return subprocess.run(['adb','-s',a.serial,*args],check=True,**kw)
    def record(name,caption,action):
        remote=f'/sdcard/{name}.mp4'
        process=subprocess.Popen(['adb','-s',a.serial,'shell','screenrecord','--time-limit','175',remote],stdout=subprocess.DEVNULL)
        time.sleep(2)
        try: action();ui.top();time.sleep(5);ui.screenshot(a.output/f'{name}.png')
        finally:
            pid=adb('shell','pidof','screenrecord',capture_output=True,text=True).stdout.strip()
            if pid: adb('shell','kill','-2',pid)
            process.wait(timeout=20)
            adb('pull',remote,str(a.output/f'{name}-raw.mp4'),stdout=subprocess.DEVNULL)
        caption_file=a.output/f'{name}.txt';caption_file.write_text(caption+'\nAndroid emulator | manual identity simulation | real HTTP permissions')
        out=a.output/f'{name}.mp4'
        subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(a.output/f'{name}-raw.mp4'),'-vf',f"pad=iw:ih+100:0:100:black,drawtext=textfile={caption_file}:fontcolor=white:fontsize=19:x=12:y=12",'-r','30','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p',str(out)],check=True)
        clips.append(out.resolve());results.append({'chapter':name,'passed':True})
    with httpx.Client(base_url=data['backend'],trust_env=False) as client:
        r=client.post('/auth/login',json={k:data['users'][0][k] for k in ['username','password']});r.raise_for_status()
        headers={'Authorization':'Bearer '+r.json()['access_token']}
        group=f"/groups/{data['group_id']}/members"
        client.post(group,headers=headers,json={'username':data['users'][1]['username']}).raise_for_status()
        ui.login(data,data['users'][0])
        def alice():
            ui.manual(data['objects'][0]['marker_id']);ui.expect('3 authorized notes');ui.top();time.sleep(4)
            for label in ['PRIVATE','GROUP']:
                ui.click('NEXT ANNOTATION');ui.expect(label);ui.top();time.sleep(4)
        record('01-alice','Alice: public + private + group = 3 notes',alice)
        ui.login(data,data['users'][1])
        def bob():
            ui.manual(data['objects'][0]['marker_id']);ui.expect('2 authorized notes');ui.top();time.sleep(4)
            ui.click('NEXT ANNOTATION');ui.expect('GROUP')
            assert 'private note on mug A' not in ui.device.dump_hierarchy()
            r=client.get('/annotations/'+data['annotations']['private']['id'],headers={'Authorization':'Bearer '+client.post('/auth/login',json={k:data['users'][1][k] for k in ['username','password']}).json()['access_token']})
            assert r.status_code==404
        record('02-bob','Bob: public + group = 2 notes; private note denied',bob)
        try:
            client.delete(group+'/'+data['users'][1]['id'],headers=headers).raise_for_status()
            def revoked():
                ui.click('REFRESH SELECTED OBJECT');ui.expect('1 authorized notes');ui.expect('PUBLIC')
            record('03-bob-revoked','Bob after Alice removes group membership: only 1 public note',revoked)
        finally: client.post(group,headers=headers,json={'username':data['users'][1]['username']}).raise_for_status()
        def object_b():
            ui.manual(data['objects'][1]['marker_id']);ui.expect('0 authorized notes');ui.expect(data['objects'][1]['name'])
        record('04-bob-object-b','Bob selects Mug B: 0 notes; Mug A notes stay with Mug A',object_b)
    listing=a.output/'clips.txt';listing.write_text(''.join(f"file '{x}'\n" for x in clips))
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(a.output/'alice-bob-demo.mp4')],check=True)
    (a.output/'results.json').write_text(json.dumps({'environment':'android_emulator','identification':'manual_simulation','chapters':results,'membership_restored':True},indent=2))
    print('PASS: Recorded Alice, Bob, revocation and Mug B; membership restored.',flush=True)
if __name__=='__main__': main()
