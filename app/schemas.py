from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class DetectIn(BaseModel):
    image: str


class RegisterIn(BaseModel):
    student_id: int
    images: List[str] = Field(min_length=1, max_length=20)


class RecognizeIn(BaseModel):
    image: str
    session_id: int
    action: Literal["check-in", "check-out"] = "check-in"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
