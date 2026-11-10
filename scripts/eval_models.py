"""Pinned OpenCV CPU adapters for replaying the same real frames through both models."""
import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.vision import LABELS

MODELS = {
    'nanodet': {'file': 'nanodet.onnx', 'size': 416, 'sha256': '4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186'},
    'yolox_s': {'file': 'yolox_s.onnx', 'size': 640, 'sha256': 'c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063'},
}

class EvaluationModel:
    def __init__(self, name, threshold=.35, threads=2):
        import cv2
        self.cv2 = cv2
        self.name = name
        info = MODELS[name]
        self.size = info['size']
        path = ROOT / 'artifacts/models' / info['file']
        if not path.exists():
            raise ValueError('Run .venv/bin/python scripts/setup_vision.py --yolox first')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != info['sha256']:
            raise ValueError('Model checksum mismatch: ' + name)
        cv2.setNumThreads(threads)
        started = time.perf_counter_ns()
        if name == 'nanodet':
            from app.vendor.nanodet.nanodet import NanoDet
            self.model = NanoDet(str(path), prob_threshold=threshold)
        else:
            from app.vendor.yolox.yolox import YoloX
            self.model = YoloX(str(path), confThreshold=threshold)
        self.metadata = {'name': name, 'input_size': self.size, 'sha256': digest, 'confidence_threshold': threshold,
                         'runtime': 'OpenCV CPU', 'opencv_version': cv2.__version__, 'threads': threads,
                         'nms_threshold': .6 if name == 'nanodet' else .5,
                         'input_color': 'BGR' if name == 'nanodet' else 'RGB',
                         'load_ms': (time.perf_counter_ns() - started) / 1e6,
                         'timing': 'model_call_ms includes vendor preprocessing, DNN forward and NMS; total_ms includes decode and outer resize too; no network/camera/display'}

    def infer(self, raw):
        import numpy as np
        cv2 = self.cv2
        started = time.perf_counter_ns()
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Invalid image')
        height, width = image.shape[:2]
        ratio = min(self.size / width, self.size / height)
        if self.name == 'nanodet':
            rw, rh = max(1, round(width * ratio)), max(1, round(height * ratio))
            left, top = (self.size - rw) // 2, (self.size - rh) // 2
        else:
            # Official YOLOX demo uses RGB, top-left letterboxing, floor-rounded dimensions.
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            rw, rh = max(1, int(width * ratio)), max(1, int(height * ratio))
            left = top = 0
        padded = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
        padded[top:top+rh, left:left+rw] = cv2.resize(image, (rw, rh))
        begin = time.perf_counter_ns()
        predictions = self.model.infer(padded)
        model_ms = (time.perf_counter_ns() - begin) / 1e6
        detections = []
        for x1, y1, x2, y2, score, category in predictions:
            if self.name == 'yolox_s':
                # YOLOX adapter returns x, y, width, height; NanoDet returns xyxy.
                x2 += x1; y2 += y1
                box = [x1 / ratio / width, y1 / ratio / height, x2 / ratio / width, y2 / ratio / height]
            else:
                box = [(x1-left)/rw, (y1-top)/rh, (x2-left)/rw, (y2-top)/rh]
            box = [min(1., max(0., float(v))) for v in box]
            if box[2] > box[0] and box[3] > box[1]:
                detections.append({'label': LABELS[int(category)], 'confidence': float(score), 'box': box})
        return {'detections': detections, 'model_call_ms': model_ms, 'total_ms': (time.perf_counter_ns()-started)/1e6}
