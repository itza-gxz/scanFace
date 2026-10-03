from datetime import date, datetime, time, timedelta

import numpy as np
import cv2
import pytest

from app import attendance_service as svc
from app import face_recognition_service as face
from app.database import SessionLocal
from app.models import Attendance, AttendanceSession, LeaveRequest, Schedule, Student


def _session(db, start, grace=15, status="OPEN"):
    sch = Schedule(date=start.date(), day="x", start_time=start.time(), end_time=(start + timedelta(hours=2)).time(),
                   class_name="IT Year 4A", subject="T")
    sch.sessions.append(AttendanceSession(session_date=start.date(), grace_period_minutes=grace, status=status))
    db.add(sch); db.commit()
    return sch.sessions[0]


# --- authentication ---
def test_login_valid(client):
    assert client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False).status_code == 303

def test_login_invalid(client):
    assert client.post("/login", data={"username": "admin", "password": "bad"}).status_code == 401

def test_unauthorized_redirect(client):
    assert client.get("/students", follow_redirects=False).status_code == 303
    assert client.get("/api/dashboard/stats").status_code == 401

def test_logout(admin_client):
    admin_client.post("/logout", follow_redirects=False)
    assert admin_client.get("/students", follow_redirects=False).status_code == 303

# --- students ---
def test_student_add_and_duplicate(admin_client):
    admin_client.post("/students/add", data={"student_code": "ST900", "full_name": "Test One"})
    admin_client.post("/students/add", data={"student_code": "ST900", "full_name": "Dup"})
    with SessionLocal() as db:
        assert db.query(Student).filter_by(student_code="ST900").count() == 1

def test_student_delete(admin_client):
    admin_client.post("/students/add", data={"student_code": "ST901", "full_name": "Del"})
    with SessionLocal() as db:
        sid = db.query(Student).filter_by(student_code="ST901").one().id
    admin_client.post(f"/students/{sid}/delete")
    with SessionLocal() as db:
        assert db.get(Student, sid) is None

# --- face detection (no camera needed: synthetic images) ---
def test_no_face_on_blank_image():
    res, crop = face.analyse(np.full((480, 640, 3), 128, np.uint8))
    assert res["code"] == "no_face" and crop is None

def test_invalid_image_rejected(admin_client):
    assert admin_client.post("/api/face/detect", json={"image": "not-an-image"}).status_code == 400

def test_register_requires_valid_faces(admin_client):
    ok, buf = cv2.imencode(".jpg", np.full((480, 640, 3), 128, np.uint8))
    import base64
    img = "data:image/jpeg;base64," + base64.b64encode(buf).decode()
    r = admin_client.post("/api/face/register", json={"student_id": 1, "images": [img] * 5})
    assert r.status_code == 422

def test_recognize_without_registered_faces_never_marks_attendance(admin_client):
    with SessionLocal() as db:
        s = _session(db, datetime.now())
        sid = s.id
    import base64
    ok, buf = cv2.imencode(".jpg", np.full((480, 640, 3), 128, np.uint8))
    r = admin_client.post("/api/face/recognize", json={"image": base64.b64encode(buf).decode(), "session_id": sid}).json()
    assert r["recognized"] is False
    with SessionLocal() as db:
        assert db.query(Attendance).filter_by(session_id=sid).count() == 0

# --- attendance rules ---
def test_present_late_boundary():
    with SessionLocal() as db:
        start = datetime(2030, 1, 7, 8, 0)
        s = _session(db, start, 15)
        assert svc.classify(s, start + timedelta(minutes=15)) == "Present"
        assert svc.classify(s, start + timedelta(minutes=16)) == "Late"

def test_checkin_duplicate_checkout_absent_leave():
    with SessionLocal() as db:
        now = datetime.now()
        s = _session(db, now - timedelta(minutes=5))
        st = db.query(Student).filter_by(student_code="ST001").one()
        other = db.query(Student).filter_by(student_code="ST002").one()
        rec, created = svc.check_in(db, st, s, 40.0)
        assert created and rec.status == "Present"
        rec2, created2 = svc.check_in(db, st, s, 40.0)
        assert not created2 and rec2.id == rec.id
        assert db.query(Attendance).filter_by(session_id=s.id, student_id=st.id).count() == 1
        assert svc.check_out(db, st, s)[1] is True
        assert svc.status_for(db, s, other) == "Absent"
        db.add(LeaveRequest(student_id=other.id, reason="x", start_date=s.session_date, end_date=s.session_date, status="approved"))
        db.commit()
        assert svc.status_for(db, s, other) == "Leave"

def test_late_checkin_and_closed_session():
    with SessionLocal() as db:
        st = db.query(Student).filter_by(student_code="ST003").one()
        late = _session(db, datetime.now() - timedelta(minutes=40))
        assert svc.check_in(db, st, late)[0].status == "Late"
        closed = _session(db, datetime.now(), status="CLOSED")
        with pytest.raises(svc.AttendanceError):
            svc.check_in(db, st, closed)

def test_export_csv(admin_client):
    r = admin_client.get("/attendance/export.csv")
    assert r.status_code == 200 and r.text.startswith("Student ID")
