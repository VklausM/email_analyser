import json
import logging
from pydantic import model_validator, Field, field_validator
from pydantic_settings import BaseSettings
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    
    AZURE_OPENAI_API_KEY: str = Field(..., min_length=1)
    AZURE_OPENAI_ENDPOINT: str = Field(..., min_length=1)
    AZURE_OPENAI_CHAT_DEPLOYMENT: str = Field(..., min_length=1)
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    
    # Scoring Configuration with proper validation
    CONFIDENCE_THRESHOLD: float = Field(default=0.6, ge=0.0, le=1.0)
    CONFIDENCE_FLOOR: float = Field(default=0.0, ge=0.0, le=1.0)
    CRITICALITY_WEIGHTS: Dict[str, float] = Field(default_factory=dict)
    CRITICALITY_LEVEL_THRESHOLDS: Dict[str, float] = Field(
        default_factory=lambda: {
            "critical": 75.0,
            "high": 50.0,
            "medium": 25.0,
            "low": 0.0,
        }
    )
    
    RISK_SCORE_SCALE: float = Field(default=100.0, gt=0)
    MAX_EMAIL_BODY_SIZE: int = Field(default=1_000_000, gt=0)
    MAX_SUBJECT_LENGTH: int = Field(default=1000, gt=0)
    MAX_EMAIL_ADDRESS_LENGTH: int = Field(default=254, gt=0)
    MAX_BATCH_SIZE: int = Field(default=10, gt=0)
    MAX_RETRIES: int = Field(default=3, ge=1)
    INITIAL_RETRY_DELAY: float = Field(default=1.0, gt=0)
    MAX_RETRY_DELAY: float = Field(default=60.0, gt=0)
    AUDIT_LOG_RETENTION_DAYS: int = Field(default=2555, gt=0)
    TEMPORARY_FILE_RETENTION_DAYS: int = Field(default=30, gt=0)
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    ENABLE_AUDIT_LOGGING: bool = True
    MASK_SENSITIVE_DATA: bool = True
    ENABLE_ENCRYPTION: bool = True
    STRICT_VALIDATION: bool = True
    
    @field_validator("CONFIDENCE_THRESHOLD", "CONFIDENCE_FLOOR")
    @classmethod
    def validate_confidence_scores(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Confidence scores must be between 0.0 and 1.0")
        return v
    
    @field_validator("CRITICALITY_LEVEL_THRESHOLDS")
    @classmethod
    def validate_thresholds(cls, v: Dict[str, float]) -> Dict[str, float]:
        if not v:
            return {"critical": 75.0, "high": 50.0, "medium": 25.0, "low": 0.0}
        for key, val in v.items():
            if val < 0:
                raise ValueError(f"Threshold '{key}' cannot be negative")
        return v
    
    @model_validator(mode="after")
    def normalize_thresholds(self) -> "Settings":
        self.CRITICALITY_LEVEL_THRESHOLDS = self._normalize_thresholds(
            self.CRITICALITY_LEVEL_THRESHOLDS
        )
        return self
    
    @model_validator(mode="after")
    def validate_consistency(self) -> "Settings":
        if self.INITIAL_RETRY_DELAY > self.MAX_RETRY_DELAY:
            raise ValueError("Initial retry delay cannot exceed max retry delay")
        return self

    @staticmethod
    def _normalize_thresholds(value: Dict[str, float] | str | None) -> Dict[str, float]:
        defaults = {"critical": 75.0, "high": 50.0, "medium": 25.0, "low": 0.0}
        
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                logger.warning("Failed to parse thresholds JSON, using defaults")
                parsed = {}
        else:
            parsed = value or {}
        
        merged = defaults.copy()
        if isinstance(parsed, dict):
            for key, val in parsed.items():
                try:
                    merged[key] = float(val)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid threshold value for '{key}', skipping")
        
        return merged

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Initialize settings with validation
try:
    settings = Settings()
except Exception as e:
    logger.error(f"Failed to load configuration: {e}")
    raise


def load_weights() -> None:
    matrix_file = Path("scoring_matrix.json")
    
    if not matrix_file.exists():
        logger.info("scoring_matrix.json not found, using default weights")
        settings.CRITICALITY_WEIGHTS = {"none": 0.0}
        return
    
    try:
        with open(matrix_file, "r", encoding="utf-8") as f:
            weights = json.load(f)
        
        if not isinstance(weights, dict):
            raise ValueError("scoring_matrix.json must contain a dictionary")
        
        for key, val in weights.items():
            if not isinstance(val, (int, float)):
                raise ValueError(f"Weight for '{key}' must be numeric, got {type(val)}")
            if not 0.0 <= val <= 1.0:
                logger.warning(f"Weight '{key}={val}' outside [0, 1] range, normalizing")
                weights[key] = max(0.0, min(1.0, val))
        
        settings.CRITICALITY_WEIGHTS = weights
        
        if "none" not in settings.CRITICALITY_WEIGHTS:
            settings.CRITICALITY_WEIGHTS["none"] = 0.0
        
        logger.info(f"Loaded {len(weights)} criticality weights from scoring_matrix.json")
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in scoring_matrix.json: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to load weights: {e}")
        raise


try:
    load_weights()
except Exception as e:
    logger.error(f"Configuration error: {e}")