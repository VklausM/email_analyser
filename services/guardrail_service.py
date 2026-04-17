import json
import re
from typing import List, Dict, Any, Optional
from pydantic import ValidationError
from schemas.email_models import EmailInput, EmailAnalysis, EvidenceLine, EmailScoringResult
from config import settings

class GuardrailService:
    VALID_CLASSIFICATIONS = {
        "malicious", "money_laundering", "insider_trading", "secrecy_breach", 
        "bribery", "fraud", "phishing", "scam", "market_manipulation", 
        "quid_pro_quo", "none", "unknown"
    }
    
    VALID_TONES = {"neutral", "aggressive", "secretive", "pressuring"}
    VALID_RISK_LEVELS = {"high", "medium", "low"}

    def validate_email_input(self, data: Dict[str, Any]) -> Optional[EmailInput]:
        try:
            if "from" in data: data["from_address"] = data.pop("from")
            if "to" in data: data["to_address"] = data.pop("to")
            return EmailInput(**data)
        except:
            return None

    def validate_email_analysis(self, data: Dict[str, Any]) -> Optional[EmailAnalysis]:
        try:
            if "classifications" in data:
                data["classifications"] = [
                    c for c in data["classifications"] if c in self.VALID_CLASSIFICATIONS
                ]
                if not data["classifications"]: data["classifications"] = ["none"]
                
            if data.get("tone") not in self.VALID_TONES:
                data["tone"] = "neutral"
                
            if "evidence_lines" in data:
                valid_lines = []
                for line in data["evidence_lines"]:
                    if line.get("risk_level") not in self.VALID_RISK_LEVELS:
                        line["risk_level"] = "medium"
                    try:
                        valid_lines.append(EvidenceLine(**line))
                    except:
                        continue
                data["evidence_lines"] = valid_lines
                
            return EmailAnalysis(**data)
        except:
            return None

    def sanitize_text(self, text: str) -> str:
        if not text: return ""
        return text.replace("\x00", "").strip()

_service = None

def get_guardrail_service():
    global _service
    if _service is None:
        _service = GuardrailService()
    return _service
