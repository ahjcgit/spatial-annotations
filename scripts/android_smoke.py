#!/usr/bin/env python3
"""Optional UIAutomator smoke test against an installed standard APK and scripts/e2e.py data.
This exercises explicit manual simulation, NOT physical QR scanning or RayNeo optics.
Run only on a disposable emulator; it signs in/out and creates one public annotation.
"""
import argparse
import atexit
import httpx
import json
import time
from pathlib import Path
import uiautomator2 as u2


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--serial', required=True)
    p.add_argument('--data', type=Path, default=Path('demo-data.json'))
    p.add_argument('--screenshots', type=Path, default=Path('artifacts/android-smoke'))
    args = p.parse_args()
    data = json.loads(args.data.read_text())
    device = u2.connect(args.serial)
    device.settings['wait_timeout'] = 8
    device.jsonrpc.setConfigurator({'waitForIdleTimeout':100,'waitForSelectorTimeout':1000})
    package = 'org.spatial.annotations'
    device.shell('cmd statusbar collapse')
    device.app_start(package, activity='.MainActivity', stop=True)
    assert device(text='Spatial Notes').wait(timeout=20), 'App did not reach settings'
    print('Android settings launched', flush=True)

    def top():
        device.shell('cmd statusbar collapse')
        for _ in range(4):
            device.swipe(0.5, 0.35, 0.5, 0.85, 0.15)

    def click(text):
        if not device(text=text).wait(timeout=2):
            top()
            for _ in range(8):
                if device(text=text).exists: break
                device.swipe(0.5, 0.85, 0.5, 0.3, 0.15)
        assert device(text=text).exists, f'Missing control {text}'
        device(text=text).click()

    def check(text):
        top()
        assert device(textContains=text).wait(timeout=10), f'Missing visible result {text}'

    def login(user):
        top()
        edits = device(className='android.widget.EditText')
        edits[0].set_text(data['backend'])
        click('SAVE SERVER')
        device(text='Username').set_text(user['username'])
        device(text='Password (at least 10 characters)').set_text(user['password'])
        click('SIGN IN')
        check('Signed in: ' + user['username'])

    def select_object():
        click('SCAN / VIEW ANNOTATIONS')
        click('Manual marker · SIMULATION'.upper())
        device(className='android.widget.EditText').set_text(data['objects'][0]['marker_id'])
        time.sleep(1)
        device.xpath('//*[@resource-id="android:id/button1"]').click(timeout=15)
        check('SIMULATION')
        check(data['objects'][0]['name'])

    alice, bob = data['users']
    # Only remove the exact disposable note this test owns, including on assertion failure.
    def cleanup():
        with httpx.Client(base_url=data['backend'],timeout=10) as client:
            response=client.post('/auth/login',json={k:alice[k] for k in ('username','password')})
            response.raise_for_status()
            headers={'Authorization':'Bearer '+response.json()['access_token']}
            for note in client.get('/objects/'+data['objects'][0]['id']+'/annotations',headers=headers).json():
                if note['author_id']==alice['id'] and note['content']=='Created through Android UI':
                    client.delete('/annotations/'+note['id'],headers=headers).raise_for_status()
            client.post('/auth/logout',headers=headers)
    cleanup()
    atexit.register(cleanup)
    login(alice)
    print('PASS: Android login over LAN', flush=True)
    select_object()
    check('3 authorized notes')
    print('PASS: Alice sees public/private/group notes in Android simulation', flush=True)
    click('CREATE ANNOTATION')
    device(className='android.widget.EditText').wait(timeout=10)
    device(className='android.widget.EditText').set_text('Created through Android UI')
    device(className='android.widget.Spinner')[0].click()
    device(text='public').click()
    click('SAVE')
    check('4 authorized notes')
    args.screenshots.mkdir(parents=True, exist_ok=True)
    device.screenshot(str(args.screenshots / 'android-alice.png'))
    print('PASS: Annotation created through Android UI and retrieved', flush=True)
    device.app_stop(package)
    device.app_start(package, activity='.MainActivity')
    check('Signed in: ' + alice['username'])
    print('PASS: Android Keystore session survives process restart', flush=True)
    click('SIGN OUT')
    check('Guest')
    login(bob)
    select_object()
    check('3 authorized notes')
    # Read each authorized card; Alice's private annotation must not appear.
    texts = []
    for _ in range(3):
        top(); texts.append(device.dump_hierarchy()); click('NEXT ANNOTATION')
    assert not any('private note on mug A' in x for x in texts)
    assert any('public note on mug A' in x for x in texts)
    assert any('group note on mug A' in x for x in texts)
    assert any('Created through Android UI' in x for x in texts)
    top(); device.screenshot(str(args.screenshots / 'android-bob.png'))
    print('PASS: Bob sees public/group/Android-created notes; Alice private content absent', flush=True)
    click('SETTINGS / ACCOUNT')
    click('SIGN OUT')
    check('Guest')
    click('SCAN / VIEW ANNOTATIONS')
    click('START CAMERA / SCAN NEXT OBJECT')
    if device(text='While using the app').wait(timeout=5): device(text='While using the app').click()
    top()
    assert device(textContains='Scanning QR').wait(timeout=5) or device(textContains='Camera QR detected').exists, 'No Camera2 stream/detection status'
    print('PASS: Runtime camera permission and Camera2 stream started in emulator (virtual scene, not physical marker)', flush=True)
    click('STOP CAMERA')
    print('PASS: Camera stopped cleanly', flush=True)


if __name__ == '__main__':
    main()
