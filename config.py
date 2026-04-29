import json
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore")
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_CHAT_DEPLOYMENT: str
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    CONFIDENCE_THRESHOLD: float = 0.6
    MAX_BATCH_SIZE: int = 5
    MAX_RETRIES: int = 3
    INITIAL_RETRY_DELAY: float = 1.0
    MAX_RETRY_DELAY: float = 60.0
    CRITICALITY_THRESHOLDS: Dict[str, float] = {"critical": 75.0, "high": 50.0, "medium": 25.0, "low": 0.0}
    SCORING_WEIGHTS: Dict[str, float] = {}

settings = Settings()

def load_scoring_weights():
    p = Path("scoring_matrix.json")
    if p.exists():
        with open(p) as f:
            w = json.load(f)
            settings.SCORING_WEIGHTS = {k: max(0.0, min(1.0, float(v))) for k, v in w.items() if isinstance(v, (int, float))}

load_scoring_weights()