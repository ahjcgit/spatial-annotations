#!/usr/bin/env python3
"""Measured human/agent-assisted snapshot loop; no implicit model API calls.

serve exposes localhost capture/submit. Codex reviews the returned image and submits
structured proposals. Device elapsed time and host monotonic time stay separate.
"""
import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator
import uvicorn

PACKAGE = 'org.spatial.annotations.branchdemo'
ACTIVITY = PACKAGE + '/org.spatial.annotations.CodexProbeActivity'


def stamp():
    return time.monotonic_ns()


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def proc_values(raw, hz, page_size):
    # comm can contain spaces; fields after the closing parenthesis start at state.
    values = raw.rsplit(')', 1)[1].split()
    return {'cpu_seconds': (int(values[11]) + int(values[12])) / hz,
            'rss_bytes': int(values[21]) * page_size}


class Label(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    identity: Literal['A', 'B']
    label: str = Field(min_length=1, max_length=48)
    uncertain: StrictBool
    box: list[StrictInt] = Field(min_length=4, max_length=4)
    evidence: str = Field(min_length=1, max_length=300)

    @model_validator(mode='after')
    def valid(self):
        l, t, r, b = self.box
        if not 0 <= l < r <= 1000 or not 0 <= t < b <= 1000:
            raise ValueError('invalid normalized visible box')
        if any(ord(c) < 32 or ord(c) == 127 for c in self.label):
            raise ValueError('control characters in label')
        return self


class Submission(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    requestId: str
    sourceSha256: str
    labels: list[Label] = Field(max_length=2)
    reasoning_summary: str = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def unique(self):
        ids = [label.identity for label in self.labels]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate identity')
        return self


def metrics(host, device):
    def ms(mapping, end, start):
        a, b = mapping.get(end), mapping.get(start)
        return (a - b) / 1e6 if a is not None and b is not None else None
    return {
        'device_capture_command_to_frame_callback_ms': ms(device, 'frameCallbackReceivedNs', 'captureCommandReceivedNs'),
        'device_frame_to_jpeg_ms': ms(device, 'frameSavedNs', 'frameCallbackReceivedNs'),
        'host_capture_to_image_ready_ms': ms(host, 'handoffReadyNs', 'captureStartNs'),
        'host_jpeg_transfer_ms': ms(host, 'imageReceivedNs', 'imagePullStartNs'),
        'codex_assisted_review_turnaround_ms': ms(host, 'submitReceivedNs', 'handoffReadyNs'),
        'host_submit_to_commit_observed_ms': ms(host, 'commitObservedNs', 'submitReceivedNs'),
        'host_response_file_transfer_ms': ms(host, 'responseFileWrittenNs', 'responseFileWriteStartNs'),
        'device_apply_to_draw_start_ms': ms(device, 'firstDrawStartNs', 'applyReceivedNs'),
        'device_draw_recording_ms': ms(device, 'firstDrawEndNs', 'firstDrawStartNs'),
        'device_apply_to_frame_commit_ms': ms(device, 'frameCommittedNs', 'applyReceivedNs'),
        'device_frame_to_frame_commit_ms': ms(device, 'frameCommittedNs', 'frameCallbackReceivedNs'),
        'host_capture_to_commit_observed_ms': ms(host, 'commitObservedNs', 'captureStartNs'),
        'isolated_model_inference_ms': None,
        'optical_display_latency_ms': None,
    }


class Bench:
    def __init__(self, adb, serial, root):
        self.adb, self.serial, self.root = adb, serial, root
        if (root / 'run-metadata.json').exists() or any(root.glob('trial-*')):
            raise ValueError('Run directory already contains evidence; choose a new --out directory')
        root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.current = None
        self.samples = []
        self.sampler_stop = threading.Event()
        self.device_pid = None
        self.device_hz = int(self.device('shell', 'getconf', 'CLK_TCK').strip())
        self.device_page = int(self.device('shell', 'getconf', 'PAGESIZE').strip())
        self.host_hz = os.sysconf('SC_CLK_TCK')
        self.host_page = os.sysconf('SC_PAGE_SIZE')
        metadata = {
            'schema_version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
            'provider_kind': 'codex_conversation_vision', 'exact_model_version': None,
            'operator_confirmed_identities': {'A': 'silver bottle', 'B': 'orange bottle'},
            'identity_confirmation_source': 'User confirmation in this session; boxes and optical readability not yet verified.',
            'device': {k: self.device('shell', 'getprop', v).decode().strip() for k,v in {
                'model':'ro.product.model','product':'ro.product.name','android':'ro.build.version.release','sdk':'ro.build.version.sdk','firmware':'ro.build.display.id'}.items()},
            'host': {'platform':platform.platform(),'python':platform.python_version(),'logical_cpus':os.cpu_count()},
            'transport':'USB ADB, app-private JSON files',
            'resource_sampling': {'interval_s':.5,'device_hz':self.device_hz,'device_page_bytes':self.device_page,
                'scope':'App process CPU/RSS and Python bench process CPU/RSS; host child CPU includes ADB sampling overhead. Remote Codex compute is unavailable.'},
            'display': {'kind':'head_locked_snapshot_labels_in_both_eyes','variant':'large_text_with_snapshot_side','expires_ms':30000,'max_snapshot_age_ms':120000,
                'commit_measurement':'Android frame commit callback; not optical visibility or binocular comfort'},
            'timing_definitions': {
                'review_turnaround':'Host image-ready to submit-handler receipt; includes Codex conversation, tool operations and orchestration. Not isolated inference.',
                'device_frame_to_commit':'Camera callback receipt to frame commit, both Android elapsedRealtimeNanos. Sensor timestamp not subtracted.',
                'host_commit_observed':'Polling observation after device commit; includes polling/transport delay.',
                'device_draw_recording':'CPU wall time recording Canvas commands, not GPU or optical presentation.',
            },
            'design':'Repeated assistant-assisted captures with operator-confirmed A/B identities. Actual views may vary; record no-label scenes separately. Technical timing trials, not independent accuracy trials.',
        }
        apk=Path('android/app/build/outputs/apk/debug/app-debug.apk')
        if apk.exists(): metadata['apk_sha256']=hashlib.sha256(apk.read_bytes()).hexdigest()
        write(root/'run-metadata.json',metadata)

    def device(self, *args, input=None, timeout=15):
        result=subprocess.run([self.adb,'-s',self.serial,*args],input=input,capture_output=True,timeout=timeout)
        if result.returncode:
            raise RuntimeError('ADB operation failed: '+result.stderr.decode(errors='replace')[:200])
        return result.stdout

    def status(self):
        try:
            return json.loads(self.device('exec-out','run-as',PACKAGE,'cat','files/codex-probe-status.json'))
        except (RuntimeError,ValueError):
            return {}

    def sample(self):
        row={'hostMonotonicNs':stamp(),'phase':self.current['phase'] if self.current else 'idle'}
        row['host']=proc_values(Path('/proc/self/stat').read_text(),self.host_hz,self.host_page)
        child=resource.getrusage(resource.RUSAGE_CHILDREN)
        row['host']['child_cpu_seconds']=child.ru_utime+child.ru_stime
        if self.device_pid:
            try:
                raw=self.device('exec-out','run-as',PACKAGE,'cat',f'/proc/{self.device_pid}/stat',timeout=3).decode()
                row['device']=proc_values(raw,self.device_hz,self.device_page)
            except Exception as error:
                row['device_error']=type(error).__name__
        self.samples.append(row)

    def sampling_loop(self):
        while not self.sampler_stop.is_set():
            self.sample()
            self.sampler_stop.wait(.5)

    def finish_sampling(self):
        self.sampler_stop.set()
        self.sampler.join(timeout=4)
        with (self.current['folder']/'resources.jsonl').open('w') as f:
            for row in self.samples:f.write(json.dumps(row)+'\n')

    def capture(self):
        if self.current and self.current['phase'] not in ('finished','failed'):
            raise ValueError('A capture is already awaiting submission')
        number=len(list(self.root.glob('trial-*')))+1
        trial_id=f'trial-{number:02d}'
        folder=self.root/trial_id;folder.mkdir()
        request_id=trial_id+'-'+uuid.uuid4().hex[:12]
        host={'captureStartNs':stamp()}
        self.current={'folder':folder,'id':trial_id,'requestId':request_id,'host':host,'phase':'capture'}
        self.samples=[];self.sampler_stop.clear()
        self.sampler=threading.Thread(target=self.sampling_loop,daemon=True);self.sampler.start()
        try:
            self.device('shell','input','keyevent','KEYCODE_WAKEUP')
            self.device('shell','wm','dismiss-keyguard')
            self.device('shell','am','start','-n',ACTIVITY,'--es','command','capture','--es','request_id',request_id)
            host['captureCommandReturnedNs']=stamp()
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                status=self.status()
                if status.get('requestId')==request_id:
                    if status.get('phase')=='captured':break
                    if status.get('phase') in ('error','rejected'):raise RuntimeError(status.get('error','device error'))
                time.sleep(.1)
            else:raise TimeoutError('Capture did not complete')
            # am start can return before the new app process is visible to pidof.
            # A completed, matching capture establishes that the process is ready.
            self.device_pid=int(self.device('shell','pidof',PACKAGE).strip().split()[0])
            host['frameReadyObservedNs']=stamp();host['imagePullStartNs']=stamp()
            raw=self.device('exec-out','run-as',PACKAGE,'cat','files/codex-probe-frame.jpg')
            host['imageReceivedNs']=stamp()
            digest=hashlib.sha256(raw).hexdigest()
            if digest!=status['sourceSha256']:raise ValueError('Camera image checksum mismatch')
            (folder/'source.jpg').write_bytes(raw)
            self.current.update(capture=status,sourceSha256=digest,phase='review',jpeg_bytes=len(raw))
            host['handoffReadyNs']=stamp()
            write(folder/'capture.json',{'host':host,'device':status,'captured_at':datetime.now(timezone.utc).isoformat(),'jpeg_bytes':len(raw)})
            return {'trial':trial_id,'requestId':request_id,'sourceSha256':digest,'image':str((folder/'source.jpg').resolve()),
                'instruction':'Review this exact image and submit structured labels. Turnaround includes tools/orchestration; not pure model inference.'}
        except Exception as error:
            self.current['phase']='failed';write(folder/'failure.json',{'stage':'capture','error':str(error),'host':host})
            self.finish_sampling();raise

    def submit(self, response):
        received=stamp()
        current=self.current
        if not current or current['phase']!='review':raise ValueError('No pending capture')
        if response.requestId!=current['requestId'] or response.sourceSha256!=current['sourceSha256']:
            raise ValueError('Response does not match the pending image')
        host=current['host'];folder=current['folder'];host['submitReceivedNs']=received
        current['phase']='delivery'
        write(folder/'codex-proposal.json',response.model_dump())
        delivered={'requestId':response.requestId,'sourceSha256':response.sourceSha256,
                   'labels':[{**label.model_dump(include={'identity','label','uncertain'}),
                              'side':'left' if (label.box[0]+label.box[2])/2<450 else 'right' if (label.box[0]+label.box[2])/2>550 else 'center'} for label in response.labels]}
        payload=json.dumps(delivered).encode()
        try:
            host['responseFileWriteStartNs']=stamp()
            self.device('shell','run-as',PACKAGE,'sh','-c',"'cat > files/codex-probe-input.json'",input=payload)
            host['responseFileWrittenNs']=stamp()
            # A singleTop am start can still pause/resume an activity on this firmware.
            # Deliver results without triggering a lifecycle transition that clears them.
            self.device('shell','am','broadcast','-a','org.spatial.annotations.CODEX_PROBE_COMMAND','-p',PACKAGE,'--es','command','apply')
            host['applyCommandReturnedNs']=stamp()
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                status=self.status()
                if status.get('requestId')==response.requestId:
                    if status.get('phase')=='rejected':raise ValueError('Device rejected: '+status.get('error','unknown'))
                    if status.get('frameCommittedNs'):
                        host['commitObservedNs']=stamp();break
                time.sleep(.05)
            else:raise TimeoutError('No device frame commit acknowledgement')
            current['phase']='display_hold'
            (folder/'display.png').write_bytes(self.device('exec-out','screencap','-p'))
            host['screenshotReceivedNs']=stamp()
            # Capture the display hold and automatic label-clear phase for resource comparison.
            deadline=time.monotonic()+32
            while time.monotonic()<deadline:
                final=self.status()
                if final.get('phase')=='expired' and final.get('requestId')==response.requestId:
                    status=final;host['expiryObservedNs']=stamp();break
                time.sleep(.4)
            current['phase']='finished';self.finish_sampling()
            values=metrics(host,status)
            summary={'trial':current['id'],'status':'completed','requestId':response.requestId,'host':host,'device':status,
                'display_hold':{'auto_expiry_observed':'expiryObservedNs' in host,'last_device_status':final},
                'metrics':values,'transfer_bytes':{'camera_jpeg':current['jpeg_bytes'],'device_label_json':len(payload)},
                'provider_kind':'codex_conversation_vision','isolated_inference_measured':False,'optical_visibility_verified':False,
                'resource_summary':resource_summary(self.samples),
                'operator_confirmed_identities':{'A':'silver bottle','B':'orange bottle'}}
            write(folder/'result.json',summary)
            return summary
        except Exception as error:
            current['phase']='failed';write(folder/'failure.json',{'stage':'delivery','error':str(error),'host':host,'device':self.status()})
            self.finish_sampling();raise


def resource_summary(samples):
    result={}
    for name in ('device','host'):
        rows=[(s['hostMonotonicNs'],s[name]) for s in samples if name in s]
        if len(rows)<2:continue
        duration=(rows[-1][0]-rows[0][0])/1e9
        cpu=rows[-1][1]['cpu_seconds']-rows[0][1]['cpu_seconds']
        result[name]={'sample_count':len(rows),'span_s':duration,'cpu_seconds_delta':cpu,
            'mean_cpu_percent_one_core':cpu/duration*100 if duration else None,
            'peak_rss_mib':max(r['rss_bytes'] for _,r in rows)/1048576}
        if name=='host':result[name]['child_cpu_seconds_delta']=rows[-1][1]['child_cpu_seconds']-rows[0][1]['child_cpu_seconds']
    return result


def create_app(bench):
    app=FastAPI(docs_url=None,redoc_url=None)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
    def origin(request):
        if request.headers.get('origin') and request.headers['origin']!=str(request.base_url).rstrip('/'):
            raise HTTPException(403,'Use the local bench')
    @app.get('/health')
    def health():return {'status':'ok','phase':bench.current['phase'] if bench.current else 'idle'}
    @app.post('/capture')
    def capture(request:Request):
        origin(request)
        if not bench.lock.acquire(blocking=False):raise HTTPException(409,'Bench busy')
        try:return bench.capture()
        except ValueError as e:raise HTTPException(409,str(e))
        finally:bench.lock.release()
    @app.post('/submit')
    def submit(response:Submission,request:Request):
        origin(request)
        if not bench.lock.acquire(blocking=False):raise HTTPException(409,'Bench busy')
        try:return bench.submit(response)
        except ValueError as e:raise HTTPException(409,str(e))
        finally:bench.lock.release()
    return app


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb',default='adb');p.add_argument('--serial',required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--port',type=int,default=8028)
    args=p.parse_args()
    uvicorn.run(create_app(Bench(args.adb,args.serial,args.out)),host='127.0.0.1',port=args.port,access_log=False)
