import csv
import io
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import current_user, log, require_role, verify_password
from ..database import get_db
from ..models import (ActivityLog, Attendance, AttendanceSession, Schedule, Student, User)
from ..utils import BASE_DIR, EMAIL_RE, GPS_ENFORCE, RECOGNITION_THRESHOLD

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
staff = require_role("admin", "staff")
admin = require_role("admin")


def render(request, name, user, **ctx):
    flash = request.session.pop("flash", None)
    return templates.TemplateResponse(request, name, {"user": user, "flash": flash, **ctx})


def back(request, url, msg, kind="success"):
    request.session["flash"] = {"msg": msg, "kind": kind}
    return RedirectResponse(url, status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "login.html", None)


@router.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form(""), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username.strip()).first()
    err = None
    if not username.strip() or not password:
        err = "Username and password are required."
    elif not user or not verify_password(password, user.password_hash):
        err = "Invalid username or password."
    elif user.status != "active":
        err = "This account is inactive."
    if err:
        return templates.TemplateResponse(request, "login.html", {"user": None, "flash": {"msg": err, "kind": "danger"}},
                                          status_code=401)
    request.session["uid"] = user.id
    log(db, user, "login", user.username)
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    log(db, user, "logout", user.username)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(staff)):
    return render(request, "dashboard.html", user, active="dashboard")


# ---- Students ----
@router.get("/students", response_class=HTMLResponse)
def students(request: Request, q: str = "", status: str = "", page: int = 1,
             db: Session = Depends(get_db), user: User = Depends(staff)):
    query = db.query(Student)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Student.full_name.like(like), Student.student_code.like(like)))
    if status:
        query = query.filter(Student.status == status)
    per = 10
    total = query.count()
    rows = query.order_by(Student.student_code).offset((max(page, 1) - 1) * per).limit(per).all()
    return render(request, "students.html", user, active="students", students=rows, q=q, status=status,
                  page=page, pages=max((total + per - 1) // per, 1))


@router.post("/students/add")
def add_student(request: Request, student_code: str = Form(...), full_name: str = Form(...),
                gender: str = Form(""), email: str = Form(""), phone: str = Form(""),
                class_name: str = Form(""), department: str = Form(""),
                db: Session = Depends(get_db), user: User = Depends(admin)):
    code = student_code.strip().upper()
    if not code or not full_name.strip():
        return back(request, "/students", "Student ID and full name are required.", "danger")
    if email and not EMAIL_RE.match(email):
        return back(request, "/students", "Invalid email address.", "danger")
    if db.query(Student).filter(Student.student_code == code).first():
        return back(request, "/students", f"Student ID {code} already exists.", "danger")
    db.add(Student(student_code=code, full_name=full_name.strip(), gender=gender, email=email or None,
                   phone=phone or None, class_name=class_name or None, department=department or None))
    db.commit()
    log(db, user, "student_created", code)
    return back(request, "/students", f"Student {code} added.")


@router.post("/students/{sid}/toggle")
def toggle_student(sid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    s = db.get(Student, sid)
    if s:
        s.status = "inactive" if s.status == "active" else "active"
        db.commit()
        log(db, user, "student_edited", f"{s.student_code} -> {s.status}")
        from .. import face_recognition_service as face
        face.invalidate()
    return back(request, "/students", "Student status updated.")


@router.post("/students/{sid}/delete")
def delete_student(sid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    s = db.get(Student, sid)
    if s:
        for p in s.face_profiles:
            (BASE_DIR / p.face_image_path).unlink(missing_ok=True)
        code = s.student_code
        db.delete(s)
        db.commit()
        from .. import face_recognition_service as face
        face.invalidate()
        log(db, user, "student_deleted", code)
    return back(request, "/students", "Student deleted.")


# ---- Face pages ----
@router.get("/face-registration", response_class=HTMLResponse)
def face_registration(request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    return render(request, "face_registration.html", user, active="face_reg",
                  students=db.query(Student).order_by(Student.student_code).all())


@router.get("/face-attendance", response_class=HTMLResponse)
def face_attendance(request: Request, db: Session = Depends(get_db), user: User = Depends(staff)):
    sessions = (db.query(AttendanceSession).filter(AttendanceSession.status == "OPEN")
                .order_by(AttendanceSession.id.desc()).all())
    return render(request, "face_attendance.html", user, active="face_att", sessions=sessions,
                  threshold=RECOGNITION_THRESHOLD, gps=GPS_ENFORCE)


# ---- Schedules & sessions ----
@router.get("/schedules", response_class=HTMLResponse)
def schedules(request: Request, q: str = "", db: Session = Depends(get_db), user: User = Depends(staff)):
    query = db.query(Schedule)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Schedule.subject.like(like), Schedule.class_name.like(like)))
    classes = [c[0] for c in db.query(Student.class_name).distinct() if c[0]]
    return render(request, "schedules.html", user, active="schedules", q=q, classes=classes,
                  schedules=query.order_by(Schedule.date.desc(), Schedule.start_time).all())


@router.post("/schedules/add")
def add_schedule(request: Request, date_: str = Form(..., alias="date"), start_time: str = Form(...),
                 end_time: str = Form(...), class_name: str = Form(...), department: str = Form(""),
                 subject: str = Form(...), lecturer: str = Form(""), room: str = Form(""),
                 grace: int = Form(15), db: Session = Depends(get_db), user: User = Depends(staff)):
    try:
        d = date.fromisoformat(date_)
        st, en = time.fromisoformat(start_time), time.fromisoformat(end_time)
    except ValueError:
        return back(request, "/schedules", "Invalid date or time.", "danger")
    if en <= st:
        return back(request, "/schedules", "End time must be after start time.", "danger")
    if grace < 0 or grace > 180:
        return back(request, "/schedules", "Grace period must be 0-180 minutes.", "danger")
    sch = Schedule(date=d, day=d.strftime("%A"), start_time=st, end_time=en, class_name=class_name,
                   department=department, subject=subject, lecturer=lecturer, room=room)
    sch.sessions.append(AttendanceSession(session_date=d, grace_period_minutes=grace, status="CLOSED"))
    db.add(sch)
    db.commit()
    log(db, user, "schedule_created", f"{subject} {d}")
    return back(request, "/schedules", "Schedule and session created.")


@router.post("/schedules/{sid}/delete")
def delete_schedule(sid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    s = db.get(Schedule, sid)
    if s:
        db.delete(s)
        db.commit()
    return back(request, "/schedules", "Schedule deleted.")


@router.post("/sessions/{sid}/{action}")
def session_action(sid: int, action: str, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(staff)):
    s = db.get(AttendanceSession, sid)
    if not s or action not in ("open", "close"):
        return back(request, "/schedules", "Session not found.", "danger")
    if action == "open":
        s.status, s.opened_at, s.closed_at = "OPEN", datetime.now(), None
    else:
        s.status, s.closed_at = "CLOSED", datetime.now()
    db.commit()
    log(db, user, f"session_{action}", f"session {sid}")
    return back(request, "/schedules", f"Session {action}ed." if action == "close" else "Session opened.")


# ---- Attendance history ----
def _history_query(db, q, date_from, date_to, class_name, subject, status):
    query = (db.query(Attendance).join(Student).join(AttendanceSession).join(Schedule))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Student.full_name.like(like), Student.student_code.like(like)))
    if date_from:
        query = query.filter(AttendanceSession.session_date >= date.fromisoformat(date_from))
    if date_to:
        query = query.filter(AttendanceSession.session_date <= date.fromisoformat(date_to))
    if class_name:
        query = query.filter(Schedule.class_name == class_name)
    if subject:
        query = query.filter(Schedule.subject == subject)
    if status:
        query = query.filter(Attendance.status == status)
    return query.order_by(Attendance.check_in_time.desc())


@router.get("/attendance", response_class=HTMLResponse)
def history(request: Request, q: str = "", date_from: str = "", date_to: str = "", class_name: str = "",
            subject: str = "", status: str = "", db: Session = Depends(get_db), user: User = Depends(staff)):
    try:
        rows = _history_query(db, q, date_from, date_to, class_name, subject, status).limit(500).all()
    except ValueError:
        rows = []
    return render(request, "attendance_history.html", user, active="attendance", rows=rows,
                  f=dict(q=q, date_from=date_from, date_to=date_to, class_name=class_name, subject=subject, status=status),
                  classes=[c[0] for c in db.query(Schedule.class_name).distinct()],
                  subjects=[c[0] for c in db.query(Schedule.subject).distinct()])


@router.get("/attendance/export.csv")
def export_csv(q: str = "", date_from: str = "", date_to: str = "", class_name: str = "", subject: str = "",
               status: str = "", db: Session = Depends(get_db), user: User = Depends(staff)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Student ID", "Name", "Date", "Class", "Subject", "Check-in", "Check-out", "Status",
                "Match distance", "Location"])
    for a in _history_query(db, q, date_from, date_to, class_name, subject, status).all():
        w.writerow([a.student.student_code, a.student.full_name, a.session.session_date, a.session.schedule.class_name,
                    a.session.schedule.subject, a.check_in_time, a.check_out_time or "", a.status,
                    a.recognition_score, a.location or ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=attendance.csv"})


@router.get("/logs", response_class=HTMLResponse)
def logs(request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    rows = db.query(ActivityLog).order_by(ActivityLog.id.desc()).limit(300).all()
    return render(request, "logs.html", user, active="logs", rows=rows)
