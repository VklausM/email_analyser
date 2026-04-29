from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime
import re


class EmailInput(BaseModel):
    email_id: str
    from_address: str = Field(alias="from")
    to_address: str = Field(alias="to")
    subject: str = ""
    body: str = ""
    cc_address: Optional[str] = None
    date: Optional[datetime] = None

    class Config:
        populate_by_name = True

    @field_validator("from_address", "to_address")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError(f"Invalid email: {v}")
        return v.lower()


class EvidenceLine(BaseModel):
    line_number: int = 1
    text: str
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    reason: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class EmailAnalysis(BaseModel):
    email_id: str
    classifications: List[str] = ["none"]
    tags: List[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_lines: List[EvidenceLine] = []
    reasoning: str
    manual_review_required: bool = False
    manual_review_reason: Optional[str] = None
    processing_duration_ms: int = 0

    @field_validator("classifications")
    @classmethod
    def clean_classifications(cls, v: List[str]) -> List[str]:
        cleaned = list({c.strip().lower() for c in v if c and isinstance(c, str)})
        return cleaned or ["none"]


class ScoringFactors(BaseModel):
    confidence_score: float
    criticality_score: float
    evidence_contribution: float = 0.0
    sender_modifier: float = 1.0


class EmailScoringResult(BaseModel):
    email_id: str
    analysis: EmailAnalysis
    risk_score: float = Field(ge=0.0, le=100.0)
    criticality_level: Literal["critical", "high", "medium", "low"]
    display_label: str = ""
    scoring_factors: ScoringFactors
    rank: int = 0


class PipelineOutput(BaseModel):
    batch_id: str
    results: List[EmailScoringResult] = []
    manual_review_emails: List[EmailScoringResult] = []
    summary: dict = {}
    processing_timestamp: datetime = Field(default_factory=datetime.utcnow)
