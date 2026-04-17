import json
from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import Dict
from pathlib import Path

class Settings(BaseSettings):
    CONFIDENCE_THRESHOLD: float = 0.6
    CONFIDENCE_FLOOR: float = 1.0

    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_CHAT_DEPLOYMENT: str
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"

    CRITICALITY_WEIGHTS: Dict[str, float] = {}
    
    CRITICALITY_LEVEL_THRESHOLDS: Dict[str, float] = {
        "critical": 50.0,
        "high": 25.0,
        "medium": 10.0,
        "low": 0.0,
    }
    
    RISK_SCORE_SCALE: float = 100.0

    @model_validator(mode="after")
    def normalize_thresholds(self) -> "Settings":
        self.CRITICALITY_LEVEL_THRESHOLDS = self._normalize_thresholds(
            self.CRITICALITY_LEVEL_THRESHOLDS
        )
        return self

    @staticmethod
    def _normalize_thresholds(value: Dict[str, float] | str | None) -> Dict[str, float]:
        defaults = {"critical": 75.0, "high": 50.0, "medium": 25.0, "low": 0.0}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                parsed = {}
        else:
            parsed = value or {}
        merged = defaults.copy()
        if isinstance(parsed, dict):
            for key, val in parsed.items():
                try:
                    merged[key] = float(val)
                except Exception:
                    pass
        return merged

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