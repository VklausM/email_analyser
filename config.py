import json
from pydantic_settings import BaseSettings
from typing import Dict
from pathlib import Path

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    MODEL_NAME: str = "gpt-4o-mini"
    CONFIDENCE_THRESHOLD: float = 0.6
    CONFIDENCE_FLOOR: float = 0.5
    
    TONE_WEIGHTS: Dict[str, float] = {
        "neutral": 1.0,
        "aggressive": 1.3,
        "secretive": 1.5,
        "pressuring": 1.4,
    }

    CRITICALITY_WEIGHTS: Dict[str, float] = {}
    
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    
    TONE_DEVIATION_THRESHOLD: float = 0.4
    
    TONE_DEVIATION_WEIGHTS: Dict[str, float] = {
        "low": 0.8,
        "normal": 1.0,
        "high": 1.2,
        "very_high": 1.5,
    }
    
    TONE_DEVIATION_THRESHOLDS: Dict[str, float] = {
        "low": 0.2,
        "normal": 0.4,
        "high": 0.6,
    }
    
    CRITICALITY_LEVEL_THRESHOLDS: Dict[str, float] = {
        "critical": 75.0,
        "high": 50.0,
        "medium": 25.0,
    }
    
    RISK_SCORE_SCALE: float = 100.0
    CHROMA_PERSIST_DIR: str = ".chroma_db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

def load_weights():
    matrix_file = Path("scoring_matrix.json")
    if matrix_file.exists():
        with open(matrix_file, "r") as f:
            settings.CRITICALITY_WEIGHTS = json.load(f)
            if "none" not in settings.CRITICALITY_WEIGHTS:
                settings.CRITICALITY_WEIGHTS["none"] = 0.0

load_weights()