"""Optional CPU detector. Category detection never asserts physical instance identity."""
import io
import os
import threading
import time
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from .models import PhysicalObject
from .schemas import ObjectOut
from .security import require_user, db_session

LABELS = ('person,bicycle,car,motorcycle,airplane,bus,train,truck,boat,traffic light,fire hydrant,stop sign,parking meter,bench,bird,cat,dog,horse,sheep,cow,elephant,bear,zebra,giraffe,backpack,umbrella,handbag,tie,suitcase,frisbee,skis,snowboard,sports ball,kite,baseball bat,baseball glove,skateboard,surfboard,tennis racket,bottle,wine glass,cup,fork,knife,spoon,bowl,banana,apple,sandwich,orange,broccoli,carrot,hot dog,pizza,donut,cake,chair,couch,potted plant,bed,dining table,toilet,tv,laptop,mouse,remote,keyboard,cell phone,microwave,oven,toaster,sink,refrigerator,book,clock,vase,scissors,teddy bear,hair drier,toothbrush').split(',')
MAX_BYTES = 2 * 1024 * 1024

class Detector:
    def __init__(self, path):
        self.path = path
        self.model = None
        self.lock = threading.Lock()

    @property
    def configured(self):
        return bool(self.path and Path(self.path).is_file())

    def detect(self, raw):
        if not self.configured:
            raise HTTPException(503, 'Model unavailable. Run scripts/setup_vision.py and set VISION_MODEL_PATH.')
        if not self.lock.acquire(blocking=False):
            raise HTTPException(429, 'Detector busy. Try again.')
        try:
            from PIL import Image, ImageOps, UnidentifiedImageError
            import numpy as np
            import cv2
            from .vendor.nanodet.nanodet import NanoDet
            try:
                with Image.open(io.BytesIO(raw)) as source:
                    if source.format not in ('JPEG', 'PNG') or source.width * source.height > 4_000_000:
                        raise HTTPException(422, 'Use JPEG/PNG with at most 4 million pixels.')
                    rgb = ImageOps.exif_transpose(source).convert('RGB')
                    image = np.array(rgb)[:, :, ::-1].copy()
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                raise HTTPException(422, 'Invalid JPEG/PNG image.')
            h, w = image.shape[:2]
            if self.model is None:
                cv2.setNumThreads(2)
                self.model = NanoDet(self.path)
            # Letterbox preserves aspect ratio; reverse padding/scale before normalization.
            scale = min(416 / w, 416 / h)
            rw, rh = max(1, round(w * scale)), max(1, round(h * scale))
            left, top = (416-rw)//2, (416-rh)//2
            padded = np.full((416,416,3), 114, dtype=np.uint8)
            padded[top:top+rh,left:left+rw] = cv2.resize(image,(rw,rh))
            start = time.monotonic_ns()
            predictions = self.model.infer(padded)
            elapsed = (time.monotonic_ns()-start)/1e6
            detections = []
            for x1,y1,x2,y2,score,category in predictions:
                box = [max(0.,min(1.,float((x1-left)/rw))), max(0.,min(1.,float((y1-top)/rh))),
                       max(0.,min(1.,float((x2-left)/rw))), max(0.,min(1.,float((y2-top)/rh)))]
                if box[2] > box[0] and box[3] > box[1]:
                    detections.append(dict(label=LABELS[int(category)], confidence=float(score), box=box))
            return dict(model='NanoDet Plus 416 / OpenCV CPU', width=w, height=h,
                        inference_ms=elapsed, detections=detections[:20], identity_requires_confirmation=True)
        except ImportError:
            raise HTTPException(503, 'Install backend/requirements-vision.txt to enable detection.')
        finally:
            self.lock.release()


def router(detector):
    routes = APIRouter(prefix='/vision')

    @routes.get('/status')
    def status():
        return dict(configured=detector.configured, model='NanoDet Plus 416', labels=LABELS,
                    identity_requires_confirmation=True)

    @routes.post('/detect')
    async def detect(request: Request, user=Depends(require_user)):
        if request.headers.get('content-type','').split(';')[0] not in ('image/jpeg','image/png'):
            raise HTTPException(415, 'Send a JPEG or PNG image body.')
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw)+len(chunk) > MAX_BYTES:
                raise HTTPException(413, 'Image exceeds 2 MiB.')
            raw.extend(chunk)
        # No images are persisted. CPU work never blocks the event loop.
        return await run_in_threadpool(detector.detect, bytes(raw))

    @routes.get('/candidates', response_model=list[ObjectOut])
    def candidates(label: str, user=Depends(require_user), db=Depends(db_session)):
        if label not in LABELS:
            raise HTTPException(422, 'Unknown detector category.')
        return list(db.scalars(select(PhysicalObject).where(
            PhysicalObject.spatial_metadata['detection_label'].as_string() == label
        ).order_by(PhysicalObject.created_at,PhysicalObject.id).limit(100)))
    return routes
