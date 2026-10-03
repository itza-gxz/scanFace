import logging

import cv2
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import attendance_service as svc
from .. import face_recognition_service as face
from ..auth import log, require_role
from ..database import get_db
from ..models import AttendanceSession, FaceProfile, Student
from ..schemas import DetectIn, RecognizeIn, RegisterIn
from ..utils import BASE_DIR, DATA_DIR, MIN_FACE_SAMPLES, RECOGNITION_THRESHOLD, safe_name

router = APIRouter()
logger = logging.getLogger("attendance")
staff = require_role("admin", "staff")
admin = require_role("admin")


def _image(data: str):
    try:
        return face.decode_image(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/face/detect")
def detect(body: DetectIn, user=Depends(staff)):
    res, _ = face.analyse(_image(body.image))
    return res


@router.post("/face/register")
def register(body: RegisterIn, db: Session = Depends(get_db), user=Depends(admin)):
    student = db.get(Student, body.student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    crops, last = [], None
    for data in body.images:
        res, crop = face.analyse(_image(data))
        last = res
        if res["ok"]:
            crops.append(crop)
        elif res["code"] == "multiple_faces":
            raise HTTPException(status_code=422, detail=res["message"] + " Nothing was saved.")
    if len(crops) < MIN_FACE_SAMPLES:
        raise HTTPException(status_code=422, detail=(
            f"Only {len(crops)} valid sample(s); at least {MIN_FACE_SAMPLES} required. "
            f"Last issue: {last['message'] if last else 'none'}"))
    # Re-registration: replace old samples
    folder = DATA_DIR / "faces" / safe_name(student.student_code)
    folder.mkdir(parents=True, exist_ok=True)
    for old in list(student.face_profiles):
        (BASE_DIR / old.face_image_path).unlink(missing_ok=True)
        db.delete(old)
    for i, crop in enumerate(crops):
        path = folder / f"sample_{i + 1}.png"
        cv2.imwrite(str(path), face.preprocess(crop))
        db.add(FaceProfile(student_id=student.id, face_image_path=str(path.relative_to(BASE_DIR)), status="active"))
    db.commit()
    face.invalidate()
    log(db, user, "face_registered", f"{student.student_code}: {len(crops)} samples")
    return {"message": "Face registration completed.", "samples": len(crops)}


@router.post("/face/{student_id}/toggle")
def toggle_face(student_id: int, db: Session = Depends(get_db), user=Depends(admin)):
    student = db.get(Student, student_id)
    if not student or not student.face_profiles:
        raise HTTPException(status_code=404, detail="No face data for this student.")
    new = "inactive" if student.face_status == "Registered" else "active"
    for p in student.face_profiles:
        p.status = new
    db.commit()
    face.invalidate()
    log(db, user, "face_status", f"{student.student_code} -> {new}")
    return {"status": student.face_status}


@router.delete("/face/{student_id}")
def delete_face(student_id: int, db: Session = Depends(get_db), user=Depends(admin)):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    for p in list(student.face_profiles):
        (BASE_DIR / p.face_image_path).unlink(missing_ok=True)
        db.delete(p)
    db.commit()
    face.invalidate()
    log(db, user, "face_deleted", student.student_code)
    return {"message": "Face data deleted."}


@router.post("/face/recognize")
def recognize(body: RecognizeIn, db: Session = Depends(get_db), user=Depends(staff)):
    session = db.get(AttendanceSession, body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Attendance session not found.")
    res, crop = face.analyse(_image(body.image))
    if not res["ok"]:  # never mark attendance without exactly one valid face
        return {"recognized": False, **res}
    label, dist = face.recognize(crop, db)
    if label is None:
        return {"recognized": False, "code": "no_registered_faces", "box": res["box"],
                "image_size": res["image_size"], "message": "No registered faces yet. Register a face first."}
    score = round(dist, 1)
    if dist > RECOGNITION_THRESHOLD:
        log(db, user, "recognition_failure", f"Unknown face, distance {score}")
        return {"recognized": False, "code": "unknown", "message": "Unknown person.", "score": score,
                "box": res["box"], "image_size": res["image_size"]}
    student = db.get(Student, label)
    out = {"recognized": True, "box": res["box"], "image_size": res["image_size"], "score": score,
           "student": {"name": student.full_name, "code": student.student_code, "class_name": student.class_name}}
    try:
        if body.action == "check-in":
            rec, created = svc.check_in(db, student, session, score, body.latitude, body.longitude)
            if created:
                log(db, user, "check_in", f"{student.student_code} {rec.status}")
            out.update(status=rec.status, check_in=rec.check_in_time.strftime("%I:%M %p"), created=created,
                       message="Attendance recorded." if created else "Attendance already recorded.")
        else:
            rec, created = svc.check_out(db, student, session)
            if created:
                log(db, user, "check_out", student.student_code)
            out.update(status=rec.status, check_in=rec.check_in_time.strftime("%I:%M %p"),
                       check_out=rec.check_out_time.strftime("%I:%M %p"), created=created,
                       message="Check-out recorded." if created else "Check-out already recorded.")
    except svc.AttendanceError as e:
        out.update(status=None, created=False, message=str(e), code="rejected")
    return out


@router.get("/dashboard/stats")
def stats(db: Session = Depends(get_db), user=Depends(staff)):
    return svc.dashboard_stats(db)
