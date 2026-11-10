#!/usr/bin/env python3
"""Real browser pagination/revocation check on an isolated disposable SQLite backend."""
import json,os,socket,subprocess,sys,tempfile,time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'artifacts/browser-pagination';output.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='spatial-pagination-') as temporary:
    temp=Path(temporary)
    with socket.socket() as sock:
        sock.bind(('0.0.0.0',0));port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}'
    with (output/'backend.log').open('w') as log:
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--app-dir',str(ROOT/'backend'),'--host','0.0.0.0','--port',str(port)],env={**os.environ,'DATABASE_URL':'sqlite:///'+str(temp/'test.db')},stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if process.poll() is not None: raise RuntimeError('Temporary backend exited')
                try:
                    if httpx.get(url+'/health',trust_env=False,timeout=1).status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.1)
            else: raise RuntimeError('Temporary backend did not become ready')
            subprocess.run([sys.executable,str(ROOT/'scripts/e2e.py'),'--url',url,'--output',str(temp/'data.json')],check=True,stdout=subprocess.DEVNULL)
            data=json.loads((temp/'data.json').read_text());alice,bob=data['users']
            with httpx.Client(base_url=url,trust_env=False) as api:
                token=api.post('/auth/login',json={k:alice[k] for k in ['username','password']}).json()['access_token'];headers={'Authorization':'Bearer '+token}
                obj=data['objects'][1]
                r=api.post('/annotations',headers=headers,json={'object_id':obj['id'],'content':'revocable pagination group note','visibility':'group','group_id':data['group_id']});r.raise_for_status()
                for index in range(100):
                    r=api.post('/annotations',headers=headers,json={'object_id':obj['id'],'content':f'Pagination public {index}','visibility':'public'});r.raise_for_status()
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page();page.goto(url)
                    page.locator('#username').fill(bob['username']);page.locator('#password').fill(bob['password']);page.locator('#auth button[type=submit]').click()
                    expect(page.locator('#identity')).to_contain_text(bob['username'])
                    page.locator('#marker').fill(obj['marker_id']);page.locator('#lookup button').first.click()
                    expect(page.locator('#notes article')).to_have_count(100)
                    expect(page.locator('#notes')).to_contain_text('revocable pagination group note')
                    # Membership changes between the first and next retrieval.
                    api.delete(f"/groups/{data['group_id']}/members/{bob['id']}",headers=headers).raise_for_status()
                    page.locator('#more').click();expect(page.locator('#notes article')).to_have_count(100)
                    expect(page.locator('#notes')).not_to_contain_text('revocable pagination group note')
                    expect(page.locator('#more')).to_be_hidden()
                    assert page.locator('#notes .badge').count()==100
                    assert all('PUBLIC' in label for label in page.locator('#notes .badge').all_text_contents())
                    # A page-two error must leave no stale first-page notes visible.
                    api.post(f"/groups/{data['group_id']}/members",headers=headers,json={'username':bob['username']}).raise_for_status()
                    page.locator('#refresh').click();expect(page.locator('#notes')).to_contain_text('revocable pagination group note')
                    page.route('**/annotations?limit=100&offset=100',lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"Test page unavailable"}'))
                    page.locator('#more').click();expect(page.locator('#status')).to_have_text('Test page unavailable')
                    expect(page.locator('#notes article')).to_have_count(0)
                    page.unroute('**/annotations?limit=100&offset=100');page.locator('#refresh').click()
                    expect(page.locator('#notes article')).to_have_count(100)
                    browser.close()
            (output/'results.json').write_text(json.dumps({'environment':'browser_real_http_isolated_sqlite','seeded_notes':101,'passed':['pagination revalidates revoked group access','page failure clears partial content','refresh recovers'],'production_dataset_modified':False},indent=2))
            print('PASS: 101-note real pagination, revoked group removed, page error clears content, refresh recovers; demo database untouched')
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
