from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Literal
from datetime import datetime
import re


class EmailInput(BaseModel):
    email_id: Optional[str] = None
    date: Optional[datetime] = None
    from_address: str = Field(..., alias="from")
    to_address: str = Field(..., alias="to")
    subject: str
    body: str
    cc: Optional[str] = None
    bcc: Optional[str] = None
    
    @field_validator('from_address', 'to_address')
    @classmethod
    def validate_email(cls, v):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v):
            raise ValueError(f'Invalid email address: {v}')
        return v
    
    @field_validator('body')
    @classmethod
    def validate_body_not_empty(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Email body cannot be empty')
        return v

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
    tone: Literal["neutral", "aggressive", "secretive", "pressuring"]
    tone_deviation: float = Field(ge=0.0, le=1.0)
    evidence_lines: List[EvidenceLine] = []
    reasoning: str
    manual_review_required: bool
    manual_review_reason: Optional[str] = None


class ScoringFactors(BaseModel):
    confidence_score: float
    criticality_score: float
    tone_weight: float
    tone_deviation_weight: float
    baseline_floor: float


class EmailScoringResult(BaseModel):
    email_id: str
    analysis: EmailAnalysis
    risk_score: float = Field(ge=0.0)
    criticality_level: Literal["critical", "high", "medium", "low"]
    scoring_factors: ScoringFactors
    rank: int = 0


class PipelineInput(BaseModel):
    emails: List[EmailInput]
    custom_criticalities: Optional[Dict[str, float]] = None


class PipelineOutput(BaseModel):
    results: List[EmailScoringResult]
    manual_review_emails: List[EmailScoringResult] = []
    summary: Dict[str, any] = {}
    processing_timestamp: datetime = None


class SenderProfile(BaseModel):
    sender_email: str
    email_count: int = 0
    average_tone_embedding: Optional[List[float]] = None
    tone_history: List[str] = []
    classification_history: List[str] = []
    risk_score_history: List[float] = []
    last_updated: datetime = None
