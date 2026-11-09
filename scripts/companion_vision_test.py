#!/usr/bin/env python3
"""Real browser -> CPU model -> explicit object confirmation -> real sharing API.
Optional fake-video file validates browser media plumbing, never a physical webcam.
"""
import argparse,json
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright,expect


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('artifacts/vision/demo-data.json'))
    p.add_argument('--output',type=Path,default=Path('artifacts/browser-vision'));p.add_argument('--fake-video',type=Path);a=p.parse_args()
    data=json.loads(a.data.read_text());a.output.mkdir(parents=True,exist_ok=True)
    photo=Path('artifacts/vision/coffee.png').resolve();blank=a.output/'blank.png';Image.new('RGB',(600,400),'white').save(blank)
    results=[]
    with sync_playwright() as pw:
        args=[] if not a.fake_video else ['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-video-capture='+str(a.fake_video.resolve())]
        browser=pw.chromium.launch(headless=True,args=args);page=browser.new_page(viewport={'width':1280,'height':1000})
        def login(page,user,url=None):
            page.goto(url or data['backend']);page.locator('#username').fill(user['username']);page.locator('#password').fill(user['password'])
            page.locator('#auth button[type=submit]').click();expect(page.locator('#identity')).to_contain_text(user['username'])
        def upload(page):
            page.locator('#vision-file').set_input_files(photo)
            expect(page.locator('#vision-detections button').filter(has_text='cup ·')).to_be_visible(timeout=30000)
            page.locator('#vision-detections button').filter(has_text='cup ·').first.click()
            expect(page.locator('#vision-candidates button')).to_have_count(2)
        def confirm(page,name,count):
            page.locator('#vision-candidates button').filter(has_text='Confirm '+name+' ·').click()
            expect(page.locator('#note-count')).to_contain_text(f'{count} authorized')
            expect(page.locator('#vision-status')).to_contain_text('your confirmation: '+name)
        login(page,data['users'][0]);upload(page);confirm(page,'Mug A',3);confirm(page,'Mug B',0);confirm(page,'Mug A',3)
        page.locator('#vision-detections button').filter(has_text='dining table ·').first.click()
        expect(page.locator('#vision-status')).to_contain_text('No registered dining table objects')
        expect(page.locator('#notes article')).to_have_count(0)
        page.locator('#vision-detections button').filter(has_text='cup ·').first.click();confirm(page,'Mug A',3)
        results.append('Selecting a different detection clears old notes even without matching objects')
        page.screenshot(path=str(a.output/'alice-model.png'),full_page=True)
        results.append('Alice photo -> cup -> A 3 / B 0 / A 3')
        # New input clears all old notes; blank does not invent an identity.
        page.locator('#vision-file').set_input_files(blank);expect(page.locator('#vision-status')).to_contain_text('No confident object',timeout=30000)
        expect(page.locator('#notes article')).to_have_count(0);expect(page.locator('#vision-candidates button')).to_have_count(0)
        results.append('Blank rejected and previous private content cleared')
        page.route('**/vision/detect',lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"Test backend unavailable"}'))
        page.locator('#vision-file').set_input_files(photo);expect(page.locator('#vision-status')).to_have_text('Test backend unavailable')
        page.unroute('**/vision/detect');upload(page);confirm(page,'Mug A',3)
        results.append('503 error surfaced; subsequent upload recovers')
        # Hold a real inference response across sign-out. Late detections must not reappear.
        held=[]
        def delay(route): held.append((route,route.fetch()))
        page.route('**/vision/detect',delay);page.locator('#vision-file').set_input_files(photo)
        expect(page.locator('#vision-status')).to_have_text('Detecting objects…')
        for _ in range(100):
            if held: break
            page.wait_for_timeout(50)
        assert held
        page.locator('#logout').click();expect(page.locator('#identity')).to_have_text('Browsing as guest')
        held[0][0].fulfill(response=held[0][1]);page.unroute('**/vision/detect');page.wait_for_timeout(300)
        expect(page.locator('#vision-detections button')).to_have_count(0);expect(page.locator('#vision-canvas')).to_be_hidden()
        results.append('Late inference after sign-out discarded')
        login(page,data['users'][1]);upload(page);confirm(page,'Mug A',2)
        expect(page.locator('#notes')).not_to_contain_text('private note')
        assert page.evaluate("async id => (await fetch('/annotations/'+id,{headers:{Authorization:'Bearer '+token}})).status",data['annotations']['private']['id'])==404
        page.screenshot(path=str(a.output/'bob-model.png'),full_page=True)
        results.append('Bob model selection -> 2 notes; direct private ID 404')
        # Late 401 from an old session must not sign out a new session.
        held=[];page.route('**/vision/detect',lambda route:held.append(route))
        page.locator('#vision-file').set_input_files(photo)
        for _ in range(100):
            if held: break
            page.wait_for_timeout(50)
        assert held
        page.locator('#username').fill(data['users'][0]['username']);page.locator('#password').fill(data['users'][0]['password']);page.locator('#auth button[type=submit]').click()
        expect(page.locator('#identity')).to_contain_text(data['users'][0]['username'])
        held[0].fulfill(status=401,content_type='application/json',body='{"detail":"old session expired"}')
        page.unroute('**/vision/detect');page.wait_for_timeout(300)
        expect(page.locator('#identity')).to_contain_text(data['users'][0]['username'])
        upload(page);confirm(page,'Mug A',3);results.append('Old session 401 cannot erase a newer login')
        if not page.evaluate('window.isSecureContext'):
            page.locator('#vision-camera').click()
            expect(page.locator('#vision-status')).to_contain_text('Webcam requires HTTPS or localhost')
            results.append('LAN HTTP webcam explains secure-context requirement; upload supported')
        if a.fake_video:
            from urllib.parse import urlsplit
            login(page,data['users'][0],f'http://localhost:{urlsplit(data["backend"]).port}')
            page.locator('#vision-camera').click();expect(page.locator('#vision-capture')).to_be_enabled(timeout=20000)
            page.locator('#vision-capture').click()
            expect(page.locator('#vision-detections button').filter(has_text='cup ·')).to_be_visible(timeout=30000)
            page.locator('#vision-detections button').filter(has_text='cup ·').first.click();confirm(page,'Mug A',3)
            expect(page.locator('#vision-video')).to_be_hidden()
            assert page.evaluate('visionStream===null')
            page.screenshot(path=str(a.output/'virtual-camera-model.png'),full_page=True)
            results.append('Browser virtual camera -> capture -> actual model -> A 3; camera released')
        browser.close()
    (a.output/'results.json').write_text(json.dumps({'environment':'desktop_browser_real_http','physical_webcam_tested':False,'passed':results},indent=2)+'\n')
    for result in results:print('PASS: '+result)
if __name__=='__main__':main()
