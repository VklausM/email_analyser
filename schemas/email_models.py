from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Literal, Any
from datetime import datetime
import math
import re

class EmailInput(BaseModel):
    email_id: Optional[str] = None
    date: Optional[datetime] = None
    from_address: str = Field(..., alias="from")
    to_address: str = Field(..., alias="to")
    subject: str = Field(default="")
    body: str = Field(default="")

    class Config:
        populate_by_name = True

class EvidenceLine(BaseModel):
    line_number: int
    text: str
    risk_level: Literal["high", "medium", "low"]
    reason: str

class EmailAnalysis(BaseModel):
    email_id: str
    classifications: List[str]
    confidence: float = Field(ge=0.0, le=1.0)
    tone: str = Field(default="neutral")
    evidence_lines: List[EvidenceLine] = Field(default_factory=list)
    reasoning: str
    manual_review_required: bool
    manual_review_reason: Optional[str] = None
    sender_profile_summary: Optional[str] = None

class ScoringFactors(BaseModel):
    confidence_score: float
    criticality_score: float
    baseline_floor: float

class EmailScoringResult(BaseModel):
    email_id: str
    analysis: EmailAnalysis
    risk_score: float = Field(ge=0.0)
    criticality_level: Literal["critical", "high", "medium", "low"]
    scoring_factors: ScoringFactors
    rank: int = 0

class PipelineOutput(BaseModel):
    results: List[EmailScoringResult]
    manual_review_emails: List[EmailScoringResult] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    processing_timestamp: datetime = None

class SenderProfile(BaseModel):
    sender_email: str
    email_count: int = 0
    classification_history: List[str] = []
    risk_score_history: List[float] = []
    last_updated: datetime = None
