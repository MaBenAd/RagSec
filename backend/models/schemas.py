"""
Pydantic schemas — modèles de requêtes et réponses de l'API.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


# ─────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=200)
    password: str = Field(..., min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=200)
    password: str = Field(..., min_length=6, max_length=200)
    class_label: Optional[str] = None
    language: Optional[str] = "fr"
    # Backward-compatible default for older clients/tests that do not send this field.
    accepted_privacy: bool = Field(default=True, description="User accepted privacy policy")


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    class_label: Optional[str] = None
    language: str = "fr"


class LanguageUpdateRequest(BaseModel):
    language: str = Field(..., pattern="^(fr|en|ar)$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ─────────────────────────────────────────────────
# CHAT
# ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    class_label: Optional[str] = None
    conversation_id: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    conversation_id: Optional[int] = None
    class_label: Optional[str] = None
    requires_class_selection: bool = False
    available_classes: List[str] = []
    source_file: Optional[str] = None
    timetable: Optional[dict] = None
    rag_confidence: Optional[str] = None
    rag_score: Optional[float] = None
    sentiment: Optional[str] = None
    sentiment_confidence: Optional[float] = None


class ClassChangeRequestCreate(BaseModel):
    requested_class_label: str = Field(..., min_length=2, max_length=120)
    reason: Optional[str] = Field(default=None, max_length=1000)


class ClassChangeDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    note: Optional[str] = Field(default=None, max_length=1000)


class ClassChangeRequestOut(BaseModel):
    id: int
    user_id: int
    user_email: Optional[str] = None
    current_class_label: Optional[str] = None
    requested_class_label: str
    reason: Optional[str] = None
    status: str
    review_note: Optional[str] = None
    reviewed_by: Optional[int] = None
    created_at: str
    updated_at: str


# ─────────────────────────────────────────────────
# EDT
# ─────────────────────────────────────────────────

class ClassInfo(BaseModel):
    label: str
    has_calendrier: bool


class ClassesResponse(BaseModel):
    classes: List[ClassInfo]


class RevisionPlanModule(BaseModel):
    id: str
    name: str = Field(..., min_length=1, max_length=120)
    exam_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")


class RevisionAvailabilitySlot(BaseModel):
    day: str = Field(..., min_length=3, max_length=20)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class RevisionPlanSession(BaseModel):
    id: str
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_label: str = Field(..., min_length=3, max_length=80)
    session_window: str = Field(..., min_length=9, max_length=24)
    duration_hours: float
    module_id: str
    module_name: str = Field(..., min_length=1, max_length=120)
    focus: str = Field(..., min_length=1, max_length=280)
    note: Optional[str] = Field(default=None, max_length=280)
    is_exam_day: bool = False


class RevisionPlanCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    modules: List[RevisionPlanModule] = Field(..., min_length=1, max_length=12)
    availability: List[RevisionAvailabilitySlot] = Field(default_factory=list, max_length=42)
    sessions: List[RevisionPlanSession] = Field(..., min_length=1, max_length=240)


class TimetableSlotCreate(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    subject: str = Field(..., min_length=1, max_length=255)
    professor: Optional[str] = Field(default=None, max_length=255)
    room: Optional[str] = Field(default=None, max_length=100)
    type: Optional[str] = Field(default=None, max_length=50)


class TimetablePublishRequest(BaseModel):
    class_label: str = Field(..., min_length=2, max_length=120)
    academic_year: str = Field(..., pattern=r"^\d{4}-\d{4}$")
    semester: str = Field(..., pattern=r"^S\d+$")
    slots: List[TimetableSlotCreate] = Field(..., min_length=1, max_length=120)


# ─────────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────────

class StatsResponse(BaseModel):
    total_users: int
    total_conversations: int
    total_messages: int
    top_questions: List[dict] = []
    weak_questions: List[dict] = []
    feedback_stats: dict = {"positive": 0, "negative": 0}


class UploadResponse(BaseModel):
    success: bool
    message: str
    filename: str


class QuestionReviewRequest(BaseModel):
    question: str
    status: str = Field(..., pattern="^(pending|treated)$")
    note: Optional[str] = Field(default=None, max_length=1000)


class FeedbackRequest(BaseModel):
    feedback: int = Field(..., ge=-1, le=1)  # -1, 0, 1
