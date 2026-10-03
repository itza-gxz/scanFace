# Face Recognition Attendance Management System

Educational/demo web app: FastAPI + SQLAlchemy (SQLite) + OpenCV + Bootstrap 5.

## Install and run (Windows 10/11)
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000 (or double-click `run.bat`). The database and demo data are created on first start.
Camera access works on `localhost`/`127.0.0.1` or HTTPS only.

## Demo account (DEMO ONLY)
`admin` / `admin123`. Change or remove it before any real deployment.

## Demo flow
Login -> Dashboard -> Students -> Face Registration (pick ST001, start camera, capture 8 samples) ->
Schedules (two seeded sessions for IT Year 4A; press Open) -> Face Attendance (check-in) ->
check-in again (duplicate message) -> check-out -> Attendance -> Dashboard -> CSV export -> Logout.
The seeded "Computer Vision" session started 5 minutes before first launch (Present); "Web Development"
started 40 minutes before (Late). No biometric data is seeded: you must register your own face.

## How recognition works
Detection: OpenCV Haar cascade, requiring exactly one face of adequate size, position and sharpness.
Recognition: LBPH (opencv-contrib). Each registered sample is a 100x100 equalized grayscale crop stored in
`data/faces/<student>/`. LBPH returns a **distance** (lower = more similar).
`RECOGNITION_THRESHOLD` (default 70, env var) is the maximum distance accepted as a match; above it the person is "Unknown".
Lower it for fewer false accepts (more false rejects); raise it for the opposite. Tune by testing with your own
registered users and record the results. This score is a match distance, not an accuracy.

IMPORTANT: Recognition performance depends on lighting, camera quality, pose, distance, registration quality and threshold
configuration. No numerical accuracy is claimed; none has been measured.

## Attendance rules
Present if check-in <= session start + grace minutes; Late after; Absent if no record; Leave if an approved leave request
covers the date. Grace is set per session. Duplicates are blocked in the service and by a unique DB constraint (session, student).

## Tests
`python -m pytest -q` (uses a temporary database; face tests use synthetic images, no camera).

## Security / privacy
PBKDF2-SHA256 password hashing, signed session cookies, role checks on every route, face images stored under `data/faces/`
which is NOT served statically. Set `SECRET_KEY`. Biometric data is sensitive: obtain consent, restrict access, delete on request.

## Limitations (honest list)
- GPS is a prototype (browser geolocation, spoofable); enforcement is off by default.
- Haar + LBPH is classical and sensitive to lighting/pose; it is not spoof-proof (a printed photo may pass). No liveness detection.
- Not yet implemented: student edit page and photo upload, user management, leave/correction request pages, reports beyond CSV export of attendance history, Excel/PDF export, Chapter 4 document.
- Endpoints differ slightly from the brief: JSON API is under `/api/...`; HTML pages use `/students`, `/attendance`, etc.
