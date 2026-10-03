import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import NotAuthenticated, hash_password
from .database import Base, SessionLocal, engine
from .models import AttendanceSession, Schedule, Student, User
from .routers import api, pages
from .utils import BASE_DIR, SECRET_KEY

logging.basicConfig(level=logging.INFO, filename=str(BASE_DIR / "data" / "app.log"),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("attendance")

DEMO_STUDENTS = [("ST001", "Sok Dara", "Male", "IT Year 4A"), ("ST002", "Srey Leak", "Female", "IT Year 4A"),
                 ("ST003", "Chan Vannak", "Male", "IT Year 4A"), ("ST004", "Kim Sopheak", "Male", "IT Year 4B"),
                 ("ST005", "Lim Sreymom", "Female", "IT Year 4B")]


def seed(db):
    """Demo data only. No biometric data is created: register real faces via the webcam."""
    if db.query(User).count():
        return
    db.add(User(username="admin", password_hash=hash_password("admin123"), full_name="System Administrator",
                email="admin@example.edu", role="admin"))
    for code, name, gender, cls in DEMO_STUDENTS:
        db.add(Student(student_code=code, full_name=name, gender=gender, class_name=cls,
                       department="Information Technology"))
    now = datetime.now()
    for subject, offset in (("Computer Vision", 5), ("Web Development", 40)):  # 5 min in -> Present; 40 min in -> Late
        start = now - timedelta(minutes=offset)
        sch = Schedule(date=start.date(), day=start.strftime("%A"), start_time=start.time().replace(second=0, microsecond=0),
                       end_time=(start + timedelta(hours=2)).time().replace(second=0, microsecond=0),
                       class_name="IT Year 4A", department="Information Technology", subject=subject,
                       lecturer="Dr. Demo Lecturer", room="Lab 3")
        sch.sessions.append(AttendanceSession(session_date=start.date(), grace_period_minutes=15, status="CLOSED"))
        db.add(sch)
    db.commit()


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="Face Recognition Attendance Management System", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
app.include_router(pages.router)
app.include_router(api.router, prefix="/api")


@app.exception_handler(NotAuthenticated)
async def not_authenticated(request: Request, exc):
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": "Not authenticated."}, status_code=401)
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Something went wrong. Please try again."}, status_code=500)
