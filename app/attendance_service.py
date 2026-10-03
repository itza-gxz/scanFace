from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .models import Attendance, AttendanceSession, LeaveRequest, Schedule, Student
from .utils import GPS_ENFORCE, GPS_LAT, GPS_LON, GPS_RADIUS_M, haversine_m


class AttendanceError(Exception):
    pass


def session_start(session: AttendanceSession) -> datetime:
    return datetime.combine(session.schedule.date, session.schedule.start_time)


def classify(session: AttendanceSession, when: datetime) -> str:
    """Present if check-in <= start + grace, otherwise Late."""
    deadline = session_start(session) + timedelta(minutes=session.grace_period_minutes)
    return "Present" if when <= deadline else "Late"


def on_leave(db, student_id: int, day: date) -> bool:
    return db.query(LeaveRequest).filter(
        LeaveRequest.student_id == student_id, LeaveRequest.status == "approved",
        LeaveRequest.start_date <= day, LeaveRequest.end_date >= day).first() is not None


def status_for(db, session: AttendanceSession, student: Student) -> str:
    rec = db.query(Attendance).filter_by(session_id=session.id, student_id=student.id).first()
    if rec:
        return rec.status
    return "Leave" if on_leave(db, student.id, session.session_date) else "Absent"


def _location(lat, lon):
    if lat is None or lon is None:
        if GPS_ENFORCE:
            raise AttendanceError("Location is required but was not provided.")
        return None
    if GPS_ENFORCE and haversine_m(lat, lon, GPS_LAT, GPS_LON) > GPS_RADIUS_M:
        raise AttendanceError("You are outside the allowed attendance location.")
    return f"{lat:.5f},{lon:.5f}"


def check_in(db, student, session, score=None, lat=None, lon=None, now=None):
    """Returns (record, created). created=False means it was a duplicate."""
    if session.status != "OPEN":
        raise AttendanceError("Session closed.")
    if student.status != "active":
        raise AttendanceError("Student account is inactive.")
    if student.class_name != session.schedule.class_name:
        raise AttendanceError("Student does not belong to this class.")
    existing = db.query(Attendance).filter_by(session_id=session.id, student_id=student.id).first()
    if existing:
        return existing, False
    location = _location(lat, lon)
    now = now or datetime.now()
    rec = Attendance(session_id=session.id, student_id=student.id, check_in_time=now,
                     status=classify(session, now), recognition_score=score, location=location)
    db.add(rec)
    try:
        db.commit()  # unique constraint (session_id, student_id) is the final guard
    except IntegrityError:
        db.rollback()
        return db.query(Attendance).filter_by(session_id=session.id, student_id=student.id).first(), False
    return rec, True


def check_out(db, student, session, now=None):
    rec = db.query(Attendance).filter_by(session_id=session.id, student_id=student.id).first()
    if not rec:
        raise AttendanceError("No check-in found for this session.")
    if rec.check_out_time:
        return rec, False
    rec.check_out_time = now or datetime.now()
    db.commit()
    return rec, True


def _class_students(db, class_name):
    return db.query(Student).filter(Student.class_name == class_name, Student.status == "active").all()


def dashboard_stats(db):
    today = date.today()
    now = datetime.now()
    total = db.query(Student).filter(Student.status == "active").count()
    counts = dict(db.query(Attendance.status, func.count()).join(AttendanceSession)
                  .filter(AttendanceSession.session_date == today).group_by(Attendance.status).all())
    absent = leave = 0
    for s in db.query(AttendanceSession).filter(AttendanceSession.session_date == today).all():
        ended = s.status == "CLOSED" and s.closed_at is not None or \
            now > datetime.combine(s.schedule.date, s.schedule.end_time)
        if not ended:
            continue
        for st in _class_students(db, s.schedule.class_name):
            r = status_for(db, s, st)
            absent += r == "Absent"
            leave += r == "Leave"
    from .models import ActivityLog
    failures = db.query(ActivityLog).filter(ActivityLog.action == "recognition_failure",
                                            func.date(ActivityLog.created_at) == today.isoformat()).count()
    by_day = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        c = dict(db.query(Attendance.status, func.count()).join(AttendanceSession)
                 .filter(AttendanceSession.session_date == d).group_by(Attendance.status).all())
        by_day.append({"date": d.isoformat(), "present": c.get("Present", 0), "late": c.get("Late", 0)})
    required = present_all = 0
    for s in db.query(AttendanceSession).filter(AttendanceSession.session_date <= today).all():
        required += len(_class_students(db, s.schedule.class_name))
        present_all += db.query(Attendance).filter_by(session_id=s.id, status="Present").count()
    return {"total_students": total, "present_today": counts.get("Present", 0),
            "late_today": counts.get("Late", 0), "absent_today": absent, "leave_today": leave,
            "recognition_failures": failures, "by_day": by_day,
            "attendance_rate": round(present_all / required * 100, 1) if required else None}
