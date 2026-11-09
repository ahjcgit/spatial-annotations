import io
import os
from pathlib import Path
from uuid import uuid4
import pytest
from PIL import Image
from fastapi import HTTPException
from app.vision import Detector, MAX_BYTES


def test_detection_auth_limits_and_unavailable(client, users):
    headers=users['alice']['headers'] | {'Content-Type':'image/png'}
    assert client.post('/vision/detect',content=b'x',headers={'Content-Type':'image/png'}).status_code==401
    assert client.post('/vision/detect',content=b'x',headers=users['alice']['headers']).status_code==415
    assert client.post('/vision/detect',content=b'x'*(MAX_BYTES+1),headers=headers).status_code==413
    client.app.state.detector.path=''
    assert client.post('/vision/detect',content=b'x',headers=headers).status_code==503
    assert client.get('/vision/status').json()['identity_requires_confirmation'] is True


def test_candidates_require_confirmation_and_preserve_permissions(client,users):
    a,b=users['alice']['headers'],users['bob']['headers']
    objects=[]
    for name in ['Mug A','Mug B']:
        r=client.post('/objects',headers=a,json={'marker_id':str(uuid4()),'name':name,'spatial_metadata':{'detection_label':'cup'}})
        assert r.status_code==201;objects.append(r.json())
    r=client.post('/annotations',headers=a,json={'object_id':objects[0]['id'],'content':'secret','visibility':'private'})
    note=r.json()
    assert client.get('/vision/candidates?label=cup').status_code==401
    matches=client.get('/vision/candidates?label=cup',headers=b).json()
    assert {o['id'] for o in matches}=={o['id'] for o in objects}
    assert 'secret' not in str(matches)
    assert client.get('/objects/'+objects[0]['id']+'/annotations',headers=b).json()==[]
    assert client.get('/annotations/'+note['id'],headers=b).status_code==404
    assert client.get('/vision/candidates?label=made-up',headers=a).status_code==422
    assert client.patch('/objects/'+objects[0]['id'],headers=b,json={'spatial_metadata':{'detection_label':'bottle'}}).status_code==403
    assert client.patch('/objects/'+objects[0]['id'],headers=a,json={'spatial_metadata':{'detection_label':'bottle'}}).status_code==200
    assert len(client.get('/vision/candidates?label=cup',headers=b).json())==1


def test_real_model_photo_blank_exif_and_validation():
    root=Path(__file__).resolve().parents[2]
    model=Path(os.getenv('VISION_TEST_MODEL',str(root/'artifacts/models/nanodet.onnx')))
    photo=root/'artifacts/vision/coffee.png'
    if not model.exists() or not photo.exists():
        pytest.skip('Optional downloaded model/photo absent; run setup_vision.py and documented fixture download')
    pytest.importorskip('cv2')
    detector=Detector(str(model))
    image=Image.open(photo)
    for variant in [image,image.convert('L')]:
        raw=io.BytesIO();variant.save(raw,format='PNG')
        result=detector.detect(raw.getvalue())
        assert any(d['label']=='cup' for d in result['detections'])
        assert (result['width'],result['height'])==variant.size
        assert all(0<=v<=1 for d in result['detections'] for v in d['box'])
    rotated=image.transpose(Image.Transpose.ROTATE_90)
    exif=Image.Exif();exif[274]=6
    raw=io.BytesIO();rotated.save(raw,format='JPEG',exif=exif)
    result=detector.detect(raw.getvalue())
    assert (result['width'],result['height'])==image.size
    assert any(d['label']=='cup' for d in result['detections'])
    raw=io.BytesIO();Image.new('RGB',(320,240),'white').save(raw,format='PNG')
    assert detector.detect(raw.getvalue())['detections']==[]
    with pytest.raises(HTTPException) as e: detector.detect(b'not an image')
    assert e.value.status_code==422
    raw=io.BytesIO();Image.new('L',(2100,2000)).save(raw,format='PNG')
    with pytest.raises(HTTPException) as e: detector.detect(raw.getvalue())
    assert e.value.status_code==422
    detector.lock.acquire()
    try:
        with pytest.raises(HTTPException) as e: detector.detect(b'x')
        assert e.value.status_code==429
    finally: detector.lock.release()
