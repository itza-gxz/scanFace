import math
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
for _d in ("faces", "captures", "models"):
    (DATA_DIR / _d).mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'attendance.db').as_posix()}")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

# Single place to tune recognition. LBPH returns a DISTANCE: lower = more similar.
RECOGNITION_THRESHOLD = float(os.getenv("RECOGNITION_THRESHOLD", "70"))
MIN_FACE_SAMPLES = int(os.getenv("MIN_FACE_SAMPLES", "5"))
BLUR_MIN = float(os.getenv("BLUR_MIN", "40"))

GPS_ENFORCE = os.getenv("GPS_ENFORCE", "false").lower() == "true"
GPS_LAT = float(os.getenv("GPS_LAT", "11.5564"))
GPS_LON = float(os.getenv("GPS_LON", "104.9282"))
GPS_RADIUS_M = float(os.getenv("GPS_RADIUS_M", "300"))

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", value)


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
