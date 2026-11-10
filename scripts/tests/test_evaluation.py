"""Scientific validity checks for scoring, incomplete trials and local annotation."""
import io
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1]))
from eval_core import analyze, plan, read_rows, record, score_frame, validate_annotation, write_json
from evaluate_demo import create_app

BOX = [.2,.3,.4,.6]
GT = {'visibility':'visible','box':BOX}
ROW = {'width':480,'height':640}

def detection(box=BOX, label='bottle', confidence=.8):
    return {'box':box,'label':label,'confidence':confidence}


def test_scoring_uses_class_overlap_not_confidence_as_accuracy():
    assert score_frame(ROW,GT,'bottle',[detection()])['hit'] is True
    assert score_frame(ROW,GT,'bottle',[detection(label='cup')])['hit'] is False
    assert score_frame(ROW,GT,'bottle',[detection(confidence=.34)])['hit'] is False
    assert score_frame(ROW,GT,'bottle',[detection([.7,.7,.9,.9])])['hit'] is False
    assert score_frame(ROW,GT,'bottle',[])['hit'] is False
    # A lower-score good box must not hide a higher-score wrong target selection.
    assert score_frame(ROW,GT,'bottle',[detection(),detection([0,0,.1,.1],confidence=.9)])['hit'] is False


def test_localization_and_absence_are_distinct():
    perfect=score_frame(ROW,GT,'bottle',[detection()])
    assert perfect['iou']==1 and perfect['anchor_error_pct']==pytest.approx(0, abs=1e-12)
    shifted=score_frame(ROW,GT,'bottle',[detection([.3,.3,.5,.6])])
    assert shifted['center_error_pct']==pytest.approx(6)
    assert score_frame(ROW,{'visibility':'absent'},'bottle',[detection()])['false_positive'] is True
    assert score_frame(ROW,{'visibility':'absent'},None,[detection(label='motorcycle')])['false_positive'] is True
    assert score_frame(ROW,{'visibility':'uncertain'},'bottle',[])['reviewed'] is False
    assert score_frame(ROW,None,'bottle',[])['hit'] is None


@pytest.mark.parametrize('box', [[0,0,0,1],[-.1,0,1,1],[0,0,float('nan'),1],[0,0,1]])
def test_invalid_ground_truth_rejected(box):
    with pytest.raises(ValueError): validate_annotation({'visibility':'visible','box':box})


def test_protocol_is_ordinal_and_replicates_are_independent_blocks():
    pilot=plan();full=plan('full')
    assert len(pilot['trials'])==11 and len(full['trials'])==51
    assert pilot==plan()
    assert all(t['distance_cm'] is None and t['yaw_deg'] is None for t in full['trials'])
    assert {t['repeat'] for t in full['trials']}=={1,2,3}


def fixture_trial(root, name='test_trial'):
    folder=root/'trials'/name; (folder/'frames').mkdir(parents=True)
    meta={**plan()['trials'][0],'trial_id':name,'status':'captured','frames':4,'include':True,'completed_duration':True}
    write_json(folder/'meta.json',meta)
    rows=[]
    for i in range(4):
        Image.new('RGB',(48,64)).save(folder/'frames'/f'{i:05d}.jpg')
        rows.append({**ROW,'index':i,'image':f'frames/{i:05d}.jpg','sha256':'fixture','host_elapsed_ms':i*250,
                     'live_inference_ms':20,'live_pipeline_ms':100,'detections':[]})
    (folder/'frames.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    write_json(folder/'annotations.json',{})
    return folder,rows


def test_unreviewed_trials_do_not_create_false_accuracy_and_recovery_is_censored(tmp_path):
    folder,rows=fixture_trial(tmp_path)
    report=analyze(tmp_path)
    assert report['conditions']==[] and report['trials'][0]['hit_rate_iou50'] is None
    write_json(folder/'annotations.json',{'0':{'visibility':'absent'},**{str(i):GT for i in (1,2,3)}})
    report=analyze(tmp_path);trial=report['trials'][0]
    assert trial['hit_rate_iou50']==0 and trial['longest_miss_run_frames']==3
    assert trial['return_events']==1 and trial['unreacquired_or_censored_events']==1
    assert trial['median_reacquisition_ms'] is None
    rows[3]['detections']=[detection()]
    (folder/'frames.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    trial=analyze(tmp_path)['trials'][0]
    assert trial['median_reacquisition_ms']==500 and trial['unreacquired_or_censored_events']==0


def test_condition_averages_trials_not_correlated_frames(tmp_path):
    f,rows=fixture_trial(tmp_path,'one')
    write_json(f/'annotations.json',{str(i):GT for i in range(4)}) # four misses
    f2,rows2=fixture_trial(tmp_path,'two')
    rows2=rows2[:1];rows2[0]['detections']=[detection()]
    (f2/'frames.jsonl').write_text(json.dumps(rows2[0])+'\n')
    write_json(f2/'annotations.json',{'0':GT}) # one hit in a separate trial
    report=analyze(tmp_path)
    assert report['conditions'][0]['mean_trial_hit_rate_iou50']==.5
    # Changing an annotation back to uncertain must remove stale condition output.
    write_json(f/'annotations.json',{})
    write_json(f2/'annotations.json',{})
    assert analyze(tmp_path)['conditions']==[]
    assert (tmp_path/'report/condition_metrics.csv').read_text()==''


def test_api_records_manual_boxes_and_requires_local_origin(tmp_path):
    write_json(tmp_path/'plan.json',plan());folder,_=fixture_trial(tmp_path)
    client=TestClient(create_app(tmp_path));headers={'origin':'http://testserver'}
    assert client.get('/').status_code==200
    assert client.post('/api/annotation/test_trial/0',json=GT).status_code==403
    assert client.post('/api/annotation/test_trial/0',json=GT,headers=headers).status_code==200
    assert client.post('/api/annotation/test_trial/900',json=GT,headers=headers).status_code==404
    assert client.post('/api/include/test_trial',json={'include':False},headers=headers).status_code==422
    assert client.get('/api/trial/test_trial').json()['annotations']['0']['box']==BOX
    assert client.get('/report/secret.txt').status_code==404


def test_capture_deduplicates_cached_results_and_preserves_misses(tmp_path,monkeypatch):
    import base64
    import httpx
    import eval_core
    import time
    buffer=io.BytesIO();Image.new('RGB',(48,64)).save(buffer,format='JPEG')
    packets=[{'runId':'r','frameId':i,'phase':'no_match','image':'data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode(),
              'detections':[],'sourceFrameTimestampNs':i*250000000} for i in range(3)]
    calls=[0]
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,*args):
            calls[0]+=1
            packet=packets[min((calls[0]-1)//2,2)]
            return httpx.Response(200,json=packet,request=httpx.Request('GET','http://local/api/status'))
    monkeypatch.setattr(httpx,'Client',Client)
    # Test takes <1 s; controlled fake source includes repeated old frames and no detections.
    result=record(tmp_path,{**plan()['trials'][0],'duration_s':.65},'http://local')
    rows=read_rows(tmp_path/'trials'/result['trial_id']/'frames.jsonl')
    assert result['frames']==2
    assert [r['frame_key'] for r in rows]==['r:1','r:2']
    assert all(r['detections']==[] for r in rows)


def test_yolox_xywh_is_converted_and_padding_unmapped(monkeypatch):
    import numpy as np
    import cv2
    from eval_models import EvaluationModel
    model=object.__new__(EvaluationModel);model.cv2=cv2;model.name='yolox_s';model.size=640
    class Fake:
        def infer(self,image):
            assert image.shape==(640,640,3)
            return np.array([[100,200,100,200,.8,39]]) # bottle: x,y,width,height
    model.model=Fake()
    buf=io.BytesIO();Image.new('RGB',(480,640)).save(buf,format='JPEG')
    r=model.infer(buf.getvalue())['detections'][0]
    assert r['label']=='bottle'
    assert r['box']==pytest.approx([100/480,200/640,200/480,400/640])
