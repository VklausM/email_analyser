from pydantic import BaseModel, Field, field_validator, EmailStr, model_validator
from typing import List, Dict, Optional, Literal, Any
from datetime import datetime
import re
import logging

logger = logging.getLogger(__name__)


class EmailInput(BaseModel):
    email_id: str = Field(
        ..., 
        min_length=1, 
        max_length=255,
        description="Unique email identifier"
    )
    date: Optional[datetime] = Field(
        default=None,
        description="Email date"
    )
    from_address: str = Field(
        ..., 
        alias="from",
        min_length=3,
        max_length=254,
        description="Sender email address"
    )
    to_address: str = Field(
        ..., 
        alias="to",
        min_length=3,
        max_length=254,
        description="Recipient email address"
    )
    subject: str = Field(
        default="",
        max_length=1000,
        description="Email subject line"
    )
    body: str = Field(
        default="",
        max_length=1_000_000,
        description="Email body content"
    )
    cc_address: Optional[str] = Field(
        default=None,
        max_length=500,
        description="CC recipients (comma-separated)"
    )
    bcc_address: Optional[str] = Field(
        default=None,
        max_length=500,
        description="BCC recipients (comma-separated)"
    )

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "email_id": "E001",
                "from": "user@bank.com",
                "to": "recipient@bank.com",
                "subject": "Account Review",
                "body": "Please review the attached account details...",
                "date": "2024-01-15T10:30:00Z"
            }
        }

    @field_validator("from_address", "to_address")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Validate email addresses format."""
        if not v or not isinstance(v, str):
            raise ValueError("Email address must be a non-empty string")
        
        # RFC 5322 simplified email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v.strip()):
            raise ValueError(f"Invalid email format: {v}")
        
        return v.strip().lower()
    
    @field_validator("email_id")
    @classmethod
    def validate_email_id(cls, v: str) -> str:
        """Validate email ID format."""
        if not v or not isinstance(v, str):
            raise ValueError("Email ID must be a non-empty string")
        
        # Allow alphanumeric, underscore, hyphen, dot
        if not re.match(r'^[a-zA-Z0-9._-]+$', v):
            raise ValueError(f"Invalid email ID format: {v}")
        
        return v.strip()
    
    @field_validator("subject", "body")
    @classmethod
    def sanitize_text_fields(cls, v: str) -> str:
        if not isinstance(v, str):
            return ""
        
        # Remove null bytes and other control characters (except newlines, tabs)
        v = ''.join(char for char in v if ord(char) >= 32 or char in '\n\t\r')
        return v.strip()
    
    @field_validator("cc_address", "bcc_address")
    @classmethod
    def validate_email_list(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        
        if not isinstance(v, str):
            raise ValueError("Email list must be a string")
        
        emails = [email.strip() for email in v.split(",")]
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        for email in emails:
            if email and not re.match(email_pattern, email):
                raise ValueError(f"Invalid email in list: {email}")
        
        return v.strip()


class EvidenceLine(BaseModel):
    """Risk evidence extracted from email."""
    
    line_number: int = Field(
        ..., 
        ge=1,
        description="Line number in email body"
    )
    text: str = Field(
        ..., 
        min_length=1,
        max_length=5000,
        description="Extracted evidence text"
    )
    risk_level: Literal["critical", "high", "medium", "low"] = Field(
        default="low",
        description="Risk level of this evidence"
    )
    reason: str = Field(
        ..., 
        min_length=1,
        max_length=500,
        description="Reason for risk classification"
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in this evidence classification"
    )

    @field_validator("text", "reason")
    @classmethod
    def sanitize_evidence(cls, v: str) -> str:
        """Sanitize evidence text."""
        if not isinstance(v, str):
            return ""
        
        v = ''.join(char for char in v if ord(char) >= 32 or char in '\n\t\r')
        return v.strip()


class EmailAnalysis(BaseModel):
    
    
    email_id: str = Field(
        ..., 
        min_length=1,
        description="Unique email identifier"
    )
    classifications: List[str] = Field(
        default_factory=list,
        description="Risk classifications applied to email"
    )
    confidence: float = Field(
        ..., 
        ge=0.0,
        le=1.0,
        description="Overall confidence in analysis"
    )
    evidence_lines: List[EvidenceLine] = Field(
        default_factory=list,
        description="Supporting evidence from email"
    )
    reasoning: str = Field(
        ..., 
        min_length=1,
        max_length=2000,
        description="Detailed reasoning for analysis"
    )
    manual_review_required: bool = Field(
        default=False,
        description="Whether manual review is needed"
    )
    manual_review_reason: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Reason for manual review requirement"
    )
    processing_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When analysis was performed"
    )
    processing_duration_ms: int = Field(
        default=0,
        ge=0,
        description="Time taken to process email"
    )

    @field_validator("classifications")
    @classmethod
    def validate_classifications(cls, v: List[str]) -> List[str]:
        
        if not v:
            return ["none"]
        
        # Remove duplicates and empty strings
        classifications = list(set(c.strip().lower() for c in v if c and isinstance(c, str)))
        
        if not classifications:
            return ["none"]
        
        return classifications
    
    @field_validator("reasoning")
    @classmethod
    def sanitize_reasoning(cls, v: str) -> str:
        
        if not isinstance(v, str):
            raise ValueError("Reasoning must be a string")
        
        v = ''.join(char for char in v if ord(char) >= 32 or char in '\n\t\r')
        return v.strip()


class ScoringFactors(BaseModel):
   
    confidence_score: float = Field(
        ..., 
        ge=0.0,
        le=1.0,
        description="LLM confidence in analysis"
    )
    criticality_score: float = Field(
        ..., 
        ge=0.0,
        le=1.0,
        description="Criticality weight of classifications"
    )
    baseline_floor: float = Field(
        ..., 
        ge=0.0,
        le=1.0,
        description="Baseline confidence floor"
    )
    evidence_contribution: float = Field(
        default=0.0,
        ge=0.0,
        description="Contribution from evidence"
    )


class EmailScoringResult(BaseModel):
    
    
    email_id: str = Field(..., description="Email identifier")
    analysis: EmailAnalysis = Field(..., description="Email analysis result")
    risk_score: float = Field(
        ..., 
        ge=0.0,
        le=100.0,
        description="Final risk score (0-100)"
    )
    criticality_level: Literal["critical", "high", "medium", "low"] = Field(
        ...,
        description="Risk severity level"
    )
    scoring_factors: ScoringFactors = Field(
        ...,
        description="Component scores"
    )
    rank: int = Field(
        default=0,
        ge=0,
        description="Ranking among all emails"
    )
    audit_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When scoring was performed"
    )
    scoring_version: str = Field(
        default="1.0",
        description="Version of scoring algorithm"
    )

    @model_validator(mode="after")
    def validate_consistency(self) -> "EmailScoringResult":
        
        score = self.risk_score
        level = self.criticality_level
        
        # Log if inconsistent
        if level == "critical" and score < 50:
            logger.warning(f"Email {self.email_id}: Critical level but score {score}")
        elif level == "low" and score > 25:
            logger.warning(f"Email {self.email_id}: Low level but score {score}")
        
        return self


class PipelineOutput(BaseModel):
    
    
    results: List[EmailScoringResult] = Field(
        default_factory=list,
        description="All scored emails"
    )
    manual_review_emails: List[EmailScoringResult] = Field(
        default_factory=list,
        description="Emails requiring manual review"
    )
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics"
    )
    processing_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Pipeline start time"
    )
    completion_timestamp: Optional[datetime] = Field(
        default=None,
        description="Pipeline completion time"
    )
    total_processing_time_ms: int = Field(
        default=0,
        ge=0,
        description="Total pipeline duration"
    )
    batch_id: str = Field(
        default="",
        description="Unique batch identifier for audit trail"
    )
    errors: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Processing errors (without sensitive data)"
    )
    
    @model_validator(mode="after")
    def validate_timestamps(self) -> "PipelineOutput":
       
        if self.completion_timestamp and self.processing_timestamp:
            if self.completion_timestamp < self.processing_timestamp:
                logger.warning("Completion timestamp before start timestamp")
        return self
