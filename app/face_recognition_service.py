"""Real local face detection + recognition using OpenCV.

Detection : Haar cascade (frontal face).
Recognition: LBPH (Local Binary Patterns Histograms, opencv-contrib).
LBPH predict() returns a DISTANCE (lower = more similar). A match is accepted
only if distance <= RECOGNITION_THRESHOLD. This is a match distance, not accuracy.
"""
import base64
import threading

import cv2
import numpy as np

from .models import FaceProfile, Student
from .utils import BASE_DIR, BLUR_MIN, DATA_DIR

_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_lock = threading.Lock()
_recognizer = None
_dirty = True


def decode_image(data_url: str):
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    try:
        raw = base64.b64decode(data_url, validate=False)
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        img = None
    if img is None:
        raise ValueError("Invalid image data.")
    return img


def preprocess(gray_crop):
    return cv2.equalizeHist(cv2.resize(gray_crop, (100, 100)))


def analyse(img):
    """Returns (result_dict, gray_face_crop_or_None). result['ok'] is True only for one valid face."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = _cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        return {"ok": False, "code": "no_face", "message": "No face detected.", "box": None}, None
    if len(faces) > 1:
        return {"ok": False, "code": "multiple_faces",
                "message": "Multiple faces detected. Please make sure only one person is in front of the camera.",
                "box": None, "faces": [[int(v) for v in f] for f in faces]}, None
    x, y, fw, fh = [int(v) for v in faces[0]]
    res = {"ok": False, "box": [x, y, fw, fh], "image_size": [w, h]}
    ratio = fw / w
    cx, cy = (x + fw / 2) / w, (y + fh / 2) / h
    crop = gray[y:y + fh, x:x + fw]
    small = cv2.resize(crop, (100, 100))
    if ratio < 0.18:
        res.update(code="too_far", message="Move closer.")
    elif ratio > 0.60:
        res.update(code="too_close", message="Move farther.")
    elif abs(cx - 0.5) > 0.2 or abs(cy - 0.5) > 0.25:
        res.update(code="off_center", message="Center your face.")
    elif cv2.Laplacian(small, cv2.CV_64F).var() < BLUR_MIN:
        res.update(code="blurry", message="Image is too blurry. Hold still and improve focus.")
    elif not 50 <= float(small.mean()) <= 210:
        res.update(code="bad_light", message="Lighting is too dark or too bright.")
    else:
        res.update(ok=True, code="face_ok", message="Face detected.")
        return res, crop
    return res, None


def invalidate():
    global _dirty
    _dirty = True


def _ensure_trained(db):
    global _recognizer, _dirty
    with _lock:
        if not _dirty:
            return
        rows = (db.query(FaceProfile).join(Student)
                .filter(FaceProfile.status == "active", Student.status == "active").all())
        imgs, labels = [], []
        for p in rows:
            im = cv2.imread(str(BASE_DIR / p.face_image_path), cv2.IMREAD_GRAYSCALE)
            if im is not None:
                imgs.append(im)
                labels.append(p.student_id)
        if not imgs:
            _recognizer = None
        else:
            rec = cv2.face.LBPHFaceRecognizer_create()
            rec.train(imgs, np.array(labels, dtype=np.int32))
            rec.save(str(DATA_DIR / "models" / "lbph.yml"))
            _recognizer = rec
        _dirty = False


def recognize(gray_crop, db):
    """Returns (student_id, distance) or (None, None) when no faces are registered."""
    _ensure_trained(db)
    if _recognizer is None:
        return None, None
    label, dist = _recognizer.predict(preprocess(gray_crop))
    return int(label), float(dist)
