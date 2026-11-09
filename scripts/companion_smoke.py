#!/usr/bin/env python3
"""Exercise the actual browser companion; optionally verify its edit on the installed Android APK."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('artifacts/demo/demo-data.json'))
    p.add_argument('--output',type=Path,default=Path('artifacts/companion'))
    p.add_argument('--android-serial');a=p.parse_args()
    data=json.loads(a.data.read_text());a.output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        alice=browser.new_page(viewport={'width':1280,'height':1000})
        bob=browser.new_page(viewport={'width':1280,'height':1000})
        def login(page,user):
            page.goto(data['backend']);page.locator('#username').fill(user['username']);page.locator('#password').fill(user['password'])
            page.locator('#auth button[type=submit]').click();expect(page.locator('#identity')).to_contain_text(user['username'])
        def lookup(page,index):
            page.locator('#marker').fill('spatial:v1:'+data['objects'][index]['marker_id'])
            page.locator('#lookup button').first.click();expect(page.locator('#object-status')).to_contain_text(data['objects'][index]['name'])
        login(alice,data['users'][0]);login(bob,data['users'][1]);lookup(alice,0);lookup(bob,0)
        expect(alice.locator('#note-count')).to_contain_text('3 authorized')
        expect(bob.locator('#note-count')).to_contain_text('2 authorized')
        expect(bob.locator('#notes')).not_to_contain_text('private note')
        assert bob.evaluate("""async id => (await fetch('/annotations/'+id,{headers:{Authorization:'Bearer '+token}})).status""",data['annotations']['private']['id'])==404
        lookup(bob,1);expect(bob.locator('#note-count')).to_contain_text('0 authorized');lookup(bob,0)
        alice.locator('#groups button').filter(has_text='Remove').click()
        expect(alice.locator('#status')).to_have_text('Membership removed.')
        bob.locator('#refresh').click();expect(bob.locator('#note-count')).to_contain_text('1 authorized')
        if a.android_serial:
            from android_ui import AndroidUI
            android=AndroidUI(a.android_serial);android.login(data,data['users'][1]);android.manual(data['objects'][0]['marker_id'])
            android.expect('1 authorized notes')
            assert 'private note on mug A' not in android.device.dump_hierarchy()
        alice.locator('#member-name').fill(data['users'][1]['username']);alice.locator('#member-form button').click()
        expect(alice.locator('#status')).to_have_text('Member added.')
        bob.locator('#refresh').click();expect(bob.locator('#note-count')).to_contain_text('2 authorized')
        if a.android_serial:
            android.click('REFRESH SELECTED OBJECT');android.expect('2 authorized notes')
            print('PASS: Bob Android membership revocation/restoration and privacy',flush=True)
        print('PASS: Browser Alice/Bob permissions, B isolation, direct private-ID rejection and membership revocation',flush=True)
        changed='public note on mug A · edited in browser companion'
        public=alice.locator('#notes article').filter(has=alice.locator('.badge').filter(has_text='PUBLIC'))
        public.get_by_role('button',name='Edit',exact=True).click()
        original=alice.locator('#content').input_value()
        try:
            alice.locator('#content').fill(changed);alice.locator('#save-note').click()
            expect(alice.locator('#notes')).to_contain_text(changed)
            bob.locator('#refresh').click();expect(bob.locator('#notes')).to_contain_text(changed)
            if a.android_serial:
                from android_ui import AndroidUI
                android=AndroidUI(a.android_serial);android.login(data,data['users'][0]);android.manual(data['objects'][0]['marker_id'])
                android.expect('3 authorized notes');android.expect(changed)
                # A second browser edit proves refresh of an already selected Android object.
                public.get_by_role('button',name='Edit',exact=True).click()
                alice.locator('#content').fill(changed+' · refreshed');alice.locator('#save-note').click()
                expect(alice.locator('#notes')).to_contain_text(changed+' · refreshed')
                android.click('REFRESH SELECTED OBJECT');android.expect(changed+' · refreshed')
                android.screenshot(a.output/'android-browser-refresh.png')
                print('PASS: Browser edit → Android production client → existing object refresh',flush=True)
            alice.screenshot(path=str(a.output/'alice-browser.png'),full_page=True)
            bob.screenshot(path=str(a.output/'bob-browser.png'),full_page=True)
        finally:
            public.get_by_role('button',name='Edit',exact=True).click()
            alice.locator('#content').fill(original);alice.locator('#save-note').click()
            expect(alice.locator('#notes')).to_contain_text(original)
        bob.locator('#logout').click();expect(bob.locator('#identity')).to_have_text('Browsing as guest')
        expect(bob.locator('#note-count')).to_contain_text('1 authorized')
        assert not bob.locator('#notes').get_by_text('private note on mug A',exact=True).count()
        print('PASS: Browser sign-out clears group/private content; edit restored',flush=True)
        if a.android_serial:
            import socket
            from urllib.parse import urlsplit
            with socket.socket() as unavailable:
                unavailable.bind(('0.0.0.0',0))  # Intentionally not listening: real connection refusal.
                endpoint=urlsplit(data['backend'])
                bad_url=f'{endpoint.scheme}://{endpoint.hostname}:{unavailable.getsockname()[1]}'
                android.click('SETTINGS / ACCOUNT');android.top()
                android.device(className='android.widget.EditText')[0].set_text(bad_url)
                android.click('SAVE SERVER');android.click('SCAN / VIEW ANNOTATIONS')
                android.manual(data['objects'][0]['marker_id'])
                android.expect('Failed to connect');android.expect('No authorized annotations loaded')
                android.screenshot(a.output/'android-network-error.png')
            android.login(data,data['users'][0]);android.manual(data['objects'][1]['marker_id'])
            android.expect('0 authorized notes');android.expect(data['objects'][1]['name'])
            print('PASS: Android real network refusal clears content; reconnect and object B lookup recover',flush=True)
        browser.close()

if __name__=='__main__': main()
