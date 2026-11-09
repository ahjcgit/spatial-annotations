#!/usr/bin/env python3
"""Idempotently add cup categories to the two owned demo mugs; preserve other metadata."""
import argparse
import io
import json
from pathlib import Path
import httpx
from PIL import Image


def configure(data_path, report_path):
    data=json.loads(data_path.read_text())
    with httpx.Client(base_url=data['backend'],trust_env=False,timeout=30) as client:
        r=client.get('/vision/status');r.raise_for_status()
        if not r.json()['configured']: raise RuntimeError('Model not configured. Run setup_vision.py and set VISION_MODEL_PATH.')
        user=data['users'][0]
        r=client.post('/auth/login',json={key:user[key] for key in ('username','password')});r.raise_for_status()
        headers={'Authorization':'Bearer '+r.json()['access_token']}
        report={'model_ready':False,'objects':[]}
        try:
            # Exercise model loading too: a path existing alone is not a readiness test.
            blank=io.BytesIO();Image.new('RGB',(320,240),'white').save(blank,format='PNG')
            r=client.post('/vision/detect',headers={**headers,'Content-Type':'image/png'},content=blank.getvalue());r.raise_for_status()
            if r.json()['detections']: raise RuntimeError('Unexpected detections on blank model-readiness frame')
            report['model_ready']=True;report['blank_inference_ms']=r.json()['inference_ms']
            for expected in data['objects']:
                r=client.get('/objects/'+expected['id']);r.raise_for_status();obj=r.json()
                if obj['creator_id']!=user['id'] or obj['marker_id']!=expected['marker_id']:
                    raise RuntimeError('Demo object ownership/identity mismatch; refusing to modify it')
                metadata=obj.get('spatial_metadata') or {}
                if metadata.get('detection_label')!='cup':
                    r=client.patch('/objects/'+obj['id'],headers=headers,json={'spatial_metadata':{**metadata,'detection_label':'cup'}});r.raise_for_status()
                report['objects'].append({'id':obj['id'],'name':obj['name'],'category':'cup'})
            r=client.get('/vision/candidates?label=cup',headers=headers);r.raise_for_status()
            if not {o['id'] for o in data['objects']}.issubset({o['id'] for o in r.json()}):
                raise RuntimeError('Prepared demo objects missing from candidates')
        finally: client.post('/auth/logout',headers=headers).raise_for_status()
    report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: model readiness and demo cup associations; metadata preserved; '+str(report_path))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();configure(a.data,a.report)
