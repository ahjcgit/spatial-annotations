"""Trial plans, immutable frame capture, ground-truth scoring and fair model replay."""
import base64
import csv
import hashlib
import io
import json
import math
import platform
import random
import statistics
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

OBJECTS = {'sanitizer': 'bottle', 'toy_motorcycle': 'motorcycle', 'empty_scene': None}

def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n'); temporary.replace(path)

def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]

def plan(profile='pilot', seed=20261110):
    trials = []
    repeats = 1 if profile == 'pilot' else 3
    for repeat in range(1, repeats + 1):
        block = []
        for obj in ('sanitizer', 'toy_motorcycle'):
            conditions = [('near','front','still'),('middle','front','still'),('far','front','still'),('middle','oblique','still')]
            if profile == 'full': conditions += [('middle','side','still')]
            conditions += [('middle','front','slow_pan')]
            if profile == 'full': conditions += [('middle','front','fast_pan'),('middle','front','exit_reenter')]
            for distance, view, motion in conditions:
                block.append({'object_id': obj, 'expected_label': OBJECTS[obj], 'distance_condition': distance,
                              'view_condition': view, 'motion': motion, 'repeat': repeat,
                              'duration_s': 8 if motion != 'still' else 5, 'distance_cm': None, 'yaw_deg': None,
                              'geometry_quality': 'ordinal', 'lighting': 'same indoor lighting', 'notes': '',
                              'front_definition': 'printed front label faces camera' if obj == 'sanitizer' else 'broad side of toy faces camera'})
        block.append({'object_id':'empty_scene','expected_label':None,'distance_condition':'none','view_condition':'none',
                      'motion':'still','repeat':repeat,'duration_s':5,'distance_cm':None,'yaw_deg':None,
                      'geometry_quality':'ordinal','lighting':'same indoor lighting','notes':'Remove both test objects.'})
        random.Random(seed + repeat).shuffle(block)
        trials += block
    for i, trial in enumerate(trials): trial['id'] = f't{i+1:03d}'
    return {'schema':1,'profile':profile,'seed':seed,'units':{'boxes':'normalized xyxy','times':'milliseconds'},
            'note':'Ordinal positions are not measured distance or angle. Reposition between repetitions. One physical instance per category.', 'trials':trials}

def record(root, condition, source, progress=lambda value: None):
    import httpx
    root = Path(root)
    trial_id = condition['id'] + '_' + uuid.uuid4().hex[:8]
    folder = root / 'trials' / trial_id
    (folder / 'frames').mkdir(parents=True)
    meta = {**condition, 'trial_id':trial_id,'started_utc':datetime.now(timezone.utc).isoformat(),
            'source':source,'capture_scope':'sampled analyzed physical-camera frames, not every sensor frame',
            'status':'recording','frames':0,'source_errors':0}
    write_json(folder / 'meta.json', meta)
    seen = set(); rows = []; events = []; last_source_time = None; active_run = None
    with httpx.Client(base_url=source, timeout=5, trust_env=False) as client, (folder/'frames.jsonl').open('w') as output:
        # Exclude the cached frame that existed before recording began.
        try:
            initial = client.get('/api/status').json()
            seen.add((initial.get('runId'), initial.get('frameId')))
        except Exception: pass
        started = time.monotonic(); deadline = started + float(condition['duration_s'])
        while time.monotonic() < deadline:
            request_started = time.monotonic()
            try:
                response = client.get('/api/status'); response.raise_for_status(); packet = response.json()
                key = (packet.get('runId'), packet.get('frameId'))
                if packet.get('phase') not in ('live','no_match') or not packet.get('image') or key in seen:
                    time.sleep(.08); continue
                if active_run is not None and key[0] != active_run:
                    events.append({'elapsed_ms':(time.monotonic()-started)*1000,'error':'App restarted during trial; review setup before including'})
                    break
                active_run = key[0]
                seen.add(key)
                raw = base64.b64decode(packet['image'].split(',',1)[1], validate=True)
                from PIL import Image
                with Image.open(io.BytesIO(raw)) as image: width,height = image.size
                index = len(rows)
                name = f'{index:05d}.jpg'; (folder/'frames'/name).write_bytes(raw)
                sensor = packet.get('sourceFrameTimestampNs')
                row = {'index':index,'frame_key':f'{key[0]}:{key[1]}','image':'frames/'+name,
                       'sha256':hashlib.sha256(raw).hexdigest(),'width':width,'height':height,
                       'host_elapsed_ms':(time.monotonic()-started)*1000,
                       'status_read_ms':(time.monotonic()-request_started)*1000,
                       'source_timestamp_ns':sensor,'source_gap_ms':(sensor-last_source_time)/1e6 if sensor is not None and last_source_time is not None else None,
                       'accepted_at_elapsed_ms':packet.get('acceptedAtElapsedMs'),
                       'result_at_elapsed_ms':packet.get('resultAtElapsedMs'),
                       'live_pipeline_ms':packet.get('pipelineMs'),'live_inference_ms':packet.get('inferenceMs'),
                       'live_model':packet.get('model','NanoDet Plus 416'), 'detections':packet.get('detections',[]),
                       'live_annotation_count':len(packet.get('notes',[])),
                       'live_target':packet.get('target'),'live_label_present':bool(packet.get('label'))}
                last_source_time = sensor; rows.append(row)
                output.write(json.dumps(row)+'\n');output.flush()
                progress({'frames':len(rows),'elapsed_s':round(time.monotonic()-started,1),'trial_id':trial_id})
            except Exception as error:
                events.append({'elapsed_ms':(time.monotonic()-started)*1000,'error':str(error)})
            time.sleep(.08)
    meta.update(status='captured' if rows else 'failed', frames=len(rows), source_errors=len(events),
                elapsed_s=time.monotonic()-started, include=True,
                completed_duration=time.monotonic()>=deadline)
    write_json(folder/'meta.json',meta);write_json(folder/'events.json',events)
    write_json(folder/'annotations.json',{})
    return meta

def validate_annotation(value):
    visibility = value.get('visibility')
    if visibility not in ('visible','absent','uncertain'): raise ValueError('Choose visible, absent or uncertain')
    box = value.get('box')
    if visibility == 'visible':
        if not isinstance(box,list) or len(box)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=1 for v in box):
            raise ValueError('Draw a normalized box on the actual object')
        if box[2]<=box[0] or box[3]<=box[1]: raise ValueError('Box must have positive area')
    else: box = None
    return {'visibility':visibility,'box':box,'reviewed':True,'updated_utc':datetime.now(timezone.utc).isoformat()}

def iou(a,b):
    intersection = max(0,min(a[2],b[2])-max(a[0],b[0])) * max(0,min(a[3],b[3])-max(a[1],b[1]))
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union>0 else 0.

def score_frame(row, annotation, expected, detections, threshold=.35):
    result={'reviewed':False,'visible':False,'hit':None,'false_positive':None,'iou':None,'center_error_pct':None,
            'anchor_error_pct':None,'object_height_pct':None,'error_x':None,'error_y':None}
    if not annotation or annotation.get('visibility')=='uncertain': return result
    result['reviewed']=True
    labels = {expected} if expected else {'bottle','motorcycle'}
    candidates=[d for d in detections if d['label'] in labels and d['confidence']>=threshold]
    if annotation['visibility']=='absent':
        result['false_positive']=bool(candidates);return result
    result['visible']=True;gt=annotation['box'];result['object_height_pct']=(gt[3]-gt[1])*100
    # Select the highest-confidence prediction, not an oracle-selected best-IoU box.
    prediction=max(candidates,key=lambda d:d['confidence'],default=None)
    result['hit']=False
    if not prediction:return result
    box=prediction['box'];result['iou']=iou(box,gt);result['hit']=result['iou']>=.5
    dx=(box[0]+box[2]-gt[0]-gt[2])/2;dy=(box[1]+box[3]-gt[1]-gt[3])/2
    width,height=row['width'],row['height'];diagonal=math.hypot(width,height)
    result.update(error_x=dx*width/diagonal,error_y=dy*height/diagonal,
                  center_error_pct=math.hypot(dx*width,dy*height)/diagonal*100,
                  anchor_error_pct=math.hypot(dx*width,(box[1]-gt[1])*height)/diagonal*100)
    return result

def quantile(values, q):
    values=sorted(v for v in values if v is not None)
    if not values:return None
    p=(len(values)-1)*q;lo=int(p);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(p-lo)

def csv_write(path, rows):
    if not rows:
        Path(path).write_text(''); return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def replay(root, models=('nanodet','yolox_s'), threshold=.35, repeats=1):
    from eval_models import EvaluationModel
    if repeats < 1: raise ValueError('repeats must be positive')
    root=Path(root); loaded={name:EvaluationModel(name,threshold) for name in models}
    trials=sorted((root/'trials').glob('*/meta.json'));images=[]
    for meta_path in trials:
        meta=json.loads(meta_path.read_text())
        if meta.get('status')!='captured' or not meta.get('include',True):continue
        for row in read_rows(meta_path.parent/'frames.jsonl'):images.append((meta_path.parent,row))
    if not images:raise ValueError('Record frames first')
    raw=(images[0][0]/images[0][1]['image']).read_bytes()
    for model in loaded.values():
        for _ in range(3):model.infer(raw)
    output=root/'replay';output.mkdir(exist_ok=True)
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex[:4]
    file=output/(run_id+'.jsonl')
    with file.open('w') as out:
        # Alternate model order on the same image to reduce consistent warm/cache order bias.
        for index,(folder,row) in enumerate(images):
            raw=(folder/row['image']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Recorded frame changed: '+str(folder/row['image']))
            names=list(models)
            if index%2:names.reverse()
            for name in names:
                for repeat in range(repeats):
                    result=loaded[name].infer(raw)
                    out.write(json.dumps({'trial_id':folder.name,'frame_index':row['index'],'sha256':row['sha256'],
                                          'model':name,'repeat':repeat,**result})+'\n');out.flush()
            print(f'Replayed frame {index+1}/{len(images)}',flush=True)
    metadata={'run_id':run_id,'file':file.name,'frames':len(images),'timing_repeats':repeats,'warmup_per_model':3,
              'models':[m.metadata for m in loaded.values()],'platform':platform.platform(),'processor':platform.processor(),
              'source':'Recorded physical-camera replay, not a live test of the alternative model',
              'comparison':'Same original image bytes; each model retains its native input size and preprocessing. Fixed confidence and IoU thresholds; not calibration-matched mAP.'}
    write_json(output/(run_id+'.json'),metadata);write_json(output/'latest.json',metadata)
    return metadata

def analyze(root, threshold=.35):
    root=Path(root);output=root/'report';output.mkdir(exist_ok=True)
    predictions={};replay_meta=None
    if (root/'replay/latest.json').exists():
        replay_meta=json.loads((root/'replay/latest.json').read_text())
        if any(m['confidence_threshold'] > threshold for m in replay_meta['models']):
            raise ValueError('Replay confidence filter is higher than scoring threshold; rerun replay')
        for r in read_rows(root/'replay'/replay_meta['file']):
            predictions.setdefault((r['trial_id'],r['frame_index'],r['model']),[]).append(r)
    scores=[];trial_summaries=[];inventory=[]
    for meta_path in sorted((root/'trials').glob('*/meta.json')):
        meta=json.loads(meta_path.read_text());folder=meta_path.parent
        inventory.append(meta)
        if meta.get('status')!='captured' or not meta.get('include',True):continue
        annotations=json.loads((folder/'annotations.json').read_text())
        rows=read_rows(folder/'frames.jsonl')
        models=['live_nanodet']+([m['name'] for m in replay_meta['models']] if replay_meta else [])
        for model in models:
            group=[]
            for row in rows:
                replay_rows=predictions.get((folder.name,row['index'],model),[])
                if model!='live_nanodet' and not replay_rows:continue
                if replay_rows and any(r['sha256']!=row['sha256'] for r in replay_rows):raise ValueError('Replay/frame checksum mismatch')
                detections=row['detections'] if model=='live_nanodet' else replay_rows[0]['detections']
                sc=score_frame(row,annotations.get(str(row['index'])),meta['expected_label'],detections,threshold)
                sc.update(trial_id=folder.name,frame_index=row['index'],elapsed_ms=row['host_elapsed_ms'],model=model,
                          object_id=meta['object_id'],distance_condition=meta['distance_condition'],view_condition=meta['view_condition'],motion=meta['motion'],
                          model_call_ms=row['live_inference_ms'] if model=='live_nanodet' else statistics.median(r['model_call_ms'] for r in replay_rows),
                          total_ms=row['live_pipeline_ms'] if model=='live_nanodet' else statistics.median(r['total_ms'] for r in replay_rows))
                group.append(sc);scores.append(sc)
            if not group:continue
            visible=[r for r in group if r['visible']];absent=[r for r in group if r['false_positive'] is not None]
            # Consecutive reviewed frames only: uncertainty/unreviewed frames break temporal segments.
            jitter=[];reacquisition=[];previous=None;return_start=None;had_absent=False;drop_count=longest=0;returns=0
            for r in group:
                if not r['reviewed']:previous=None;return_start=None;had_absent=False;drop_count=0;continue
                if not r['visible']:had_absent=True;previous=None;return_start=None;drop_count=0;continue
                if had_absent and return_start is None:
                    return_start=r['elapsed_ms'];returns+=1
                if r['hit']:
                    if return_start is not None:reacquisition.append(r['elapsed_ms']-return_start);return_start=None;had_absent=False
                    drop_count=0
                else:drop_count+=1;longest=max(longest,drop_count)
                if previous and previous['error_x'] is not None and r['error_x'] is not None and r['frame_index']==previous['frame_index']+1:
                    jitter.append(math.hypot(r['error_x']-previous['error_x'],r['error_y']-previous['error_y'])*100)
                previous=r
            trial_summaries.append({'trial_id':folder.name,'model':model,'object_id':meta['object_id'],
                'distance_condition':meta['distance_condition'],'view_condition':meta['view_condition'],'motion':meta['motion'],
                'geometry_quality':meta.get('geometry_quality'),'distance_cm':meta.get('distance_cm'),'yaw_deg':meta.get('yaw_deg'),
                'frames':len(group),'reviewed_frames':sum(r['reviewed'] for r in group),'visible_frames':len(visible),'absent_frames':len(absent),
                'hit_rate_iou50':sum(bool(r['hit']) for r in visible)/len(visible) if visible else None,
                'false_positive_rate':sum(r['false_positive'] for r in absent)/len(absent) if absent else None,
                'median_iou':quantile([r['iou'] for r in visible],.5),
                'median_center_error_pct':quantile([r['center_error_pct'] for r in visible],.5),
                'median_anchor_error_pct':quantile([r['anchor_error_pct'] for r in visible],.5),
                'median_object_height_pct':quantile([r['object_height_pct'] for r in visible],.5),
                'median_residual_jitter_pct':quantile(jitter,.5),'longest_miss_run_frames':longest,
                'return_events':returns,'reacquired_events':len(reacquisition),
                'unreacquired_or_censored_events':returns-len(reacquisition),'median_reacquisition_ms':quantile(reacquisition,.5),
                'median_model_call_ms':quantile([r['model_call_ms'] for r in group],.5),
                'p95_model_call_ms':quantile([r['model_call_ms'] for r in group],.95),
                'median_total_ms':quantile([r['total_ms'] for r in group],.5),
                'median_source_gap_ms':quantile([r.get('source_gap_ms') for r in rows],.5),
                'captured_frames':len(rows),'capture_complete':meta.get('completed_duration',True),
                'fully_reviewed':len(group)==len(rows) and all(r['reviewed'] for r in group)})
    csv_write(output/'frame_metrics.csv',scores);csv_write(output/'trial_metrics.csv',trial_summaries)
    groups=defaultdict(list)
    for r in trial_summaries:
        if r['fully_reviewed'] and r['capture_complete']:groups[(r['model'],r['object_id'],r['distance_condition'],r['view_condition'],r['motion'])].append(r)
    grouped=[]
    for key,values in groups.items():
        row=dict(zip(('model','object_id','distance_condition','view_condition','motion'),key));row['trials']=len(values)
        for metric in ('hit_rate_iou50','false_positive_rate','median_anchor_error_pct','median_residual_jitter_pct','median_model_call_ms'):
            v=[x[metric] for x in values if x[metric] is not None];row['mean_trial_'+metric]=statistics.mean(v) if v else None
        grouped.append(row)
    csv_write(output/'condition_metrics.csv',grouped)
    summary={'trials':trial_summaries,'conditions':grouped,'replay':replay_meta,'capture_inventory':inventory,
             'warnings':['One physical instance per class; not general class accuracy.','Frames within a trial are correlated. Use trial-level averages and report trial count.',
                         'Unreviewed and uncertain frames are excluded; condition averages require full review.','Ordinal near/middle/far and front/oblique/side are not centimeters or degrees.',
                         'Anchor error is top-center box error in camera-image coordinates, not optical/world alignment.',
                         'Placement metrics are detector-box proxies, not rendered label bounds or optical registration. Errors are conditional on a prediction; report hit rate alongside them.',
                         'Reacquisition medians include successful returns only; also report unreacquired or censored events.',
                         'Model replay timings exclude capture/network/display. Live pipeline includes conditional note retrieval.',
                         'Miss-run and reacquisition use sampled recorded frames; sensor frames between samples are not observed.'],
             'definitions':{'hit':'Correct expected class, confidence >= threshold, highest-score class box IoU >= 0.5 with manual box',
                            'anchor_error':'Top-center predicted box to top-center manual box, percent image diagonal',
                            'residual_jitter':'Consecutive changes in predicted-minus-ground-truth center, percent image diagonal',
                            'reacquisition':'First reviewed present frame after reviewed absence to first IoU50 hit (observed-frame timing)'},'threshold':threshold}
    write_json(output/'summary.json',summary)
    return summary
