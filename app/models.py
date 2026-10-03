from datetime import datetime

from sqlalchemy import (Column, Date, DateTime, Float, ForeignKey, Integer, String,
                        Text, Time, UniqueConstraint)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    email = Column(String(120))
    role = Column(String(20), nullable=False, default="staff")  # admin | staff | student
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.now)


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    student_code = Column(String(20), unique=True, nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    gender = Column(String(10))
    date_of_birth = Column(Date)
    phone = Column(String(30))
    email = Column(String(120))
    address = Column(String(200))
    class_name = Column(String(50), index=True)
    department = Column(String(80))
    profile_photo = Column(String(200))
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.now)
    face_profiles = relationship("FaceProfile", back_populates="student", cascade="all, delete-orphan")
    attendance = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")

    @property
    def face_status(self):
        profiles = self.face_profiles
        if not profiles:
            return "Not Registered"
        return "Registered" if any(p.status == "active" for p in profiles) else "Inactive"


class FaceProfile(Base):
    """One row per stored face sample (cropped, grayscale 100x100 image on disk)."""
    __tablename__ = "face_profiles"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    face_image_path = Column(String(255), nullable=False)
    model_info = Column(String(100), default="LBPH 100x100 gray equalized")
    registered_at = Column(DateTime, default=datetime.now)
    status = Column(String(20), default="active")
    student = relationship("Student", back_populates="face_profiles")


class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    day = Column(String(15))
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    class_name = Column(String(50), nullable=False)
    department = Column(String(80))
    subject = Column(String(100), nullable=False)
    lecturer = Column(String(100))
    room = Column(String(50))
    sessions = relationship("AttendanceSession", back_populates="schedule", cascade="all, delete-orphan")


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    id = Column(Integer, primary_key=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=False)
    session_date = Column(Date, nullable=False, index=True)
    opened_at = Column(DateTime)
    closed_at = Column(DateTime)
    grace_period_minutes = Column(Integer, nullable=False, default=15)
    status = Column(String(10), nullable=False, default="CLOSED")  # OPEN | CLOSED
    schedule = relationship("Schedule", back_populates="sessions")
    records = relationship("Attendance", back_populates="session", cascade="all, delete-orphan")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_attendance_session_student"),)
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    check_in_time = Column(DateTime)
    check_out_time = Column(DateTime)
    status = Column(String(15), nullable=False)  # Present | Late
    recognition_score = Column(Float)  # LBPH distance (lower = closer). NOT an accuracy.
    location = Column(String(60))
    created_at = Column(DateTime, default=datetime.now)
    session = relationship("AttendanceSession", back_populates="records")
    student = relationship("Student", back_populates="attendance")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    reason = Column(Text, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(15), default="pending")  # pending | approved | rejected
    created_at = Column(DateTime, default=datetime.now)


class CorrectionRequest(Base):
    __tablename__ = "correction_requests"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    attendance_id = Column(Integer, ForeignKey("attendance.id"))
    reason = Column(Text, nullable=False)
    status = Column(String(15), default="pending")
    requested_at = Column(DateTime, default=datetime.now)


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(50), nullable=False, index=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    user = relationship("User")
