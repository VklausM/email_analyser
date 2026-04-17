from typing import List, Dict, Any, Optional
from pydantic import ValidationError
from schemas.email_models import (
    EmailInput, EmailAnalysis, EvidenceLine, EmailScoringResult
)
import json


class GuardrailService:
    VALID_CLASSIFICATIONS = {
        "malicious",
        "money_laundering",
        "insider_trading",
        "secrecy_breach",
        "bribery",
        "fraud",
        "phishing",
        "scam",
        "market_manipulation",
        "quid_pro_quo",
        "none",
    }
    
    VALID_TONES = {"neutral", "aggressive", "secretive", "pressuring"}
    VALID_RISK_LEVELS = {"high", "medium", "low"}
    
    def __init__(self):
        self.validation_errors: List[Dict[str, Any]] = []
    
    def validate_email_input(self, email_data: Dict[str, Any], strict: bool = False) -> Optional[EmailInput]:
        try:
            normalized = self._normalize_email_input(email_data)
            email_input = EmailInput(**normalized)
            return email_input
        except ValidationError as e:
            error_info = {
                "email_id": email_data.get("email_id"),
                "errors": e.errors(),
                "type": "email_input_validation"
            }
            self.validation_errors.append(error_info)
            if strict:
                raise ValueError(f"Email validation failed: {e}")
            return None
    
    def validate_email_analysis(self, analysis_data: Dict[str, Any], strict: bool = False) -> Optional[EmailAnalysis]:
        try:
            if "classifications" in analysis_data:
                invalid = set(analysis_data["classifications"]) - self.VALID_CLASSIFICATIONS
                if invalid:
                    analysis_data["classifications"] = [
                        c for c in analysis_data["classifications"] 
                        if c in self.VALID_CLASSIFICATIONS
                    ]
                    analysis_data["classifications"].append("unknown")
            if analysis_data.get("tone") not in self.VALID_TONES:
                analysis_data["tone"] = "neutral"
            if "evidence_lines" in analysis_data:
                validated_lines = []
                for line_data in analysis_data["evidence_lines"]:
                    try:
                        if line_data.get("risk_level") not in self.VALID_RISK_LEVELS:
                            line_data["risk_level"] = "medium"
                        validated_lines.append(EvidenceLine(**line_data))
                    except ValidationError:
                        continue
                analysis_data["evidence_lines"] = validated_lines
            return EmailAnalysis(**analysis_data)
        except ValidationError as e:
            error_info = {
                "email_id": analysis_data.get("email_id"),
                "errors": e.errors(),
                "type": "email_analysis_validation"
            }
            self.validation_errors.append(error_info)
            if strict:
                raise ValueError(f"Analysis validation failed: {e}")
            return None
    
    def validate_json_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            if "`json" in response_text:
                try:
                    start = response_text.find("`json") + 7
                    end = response_text.find("`", start)
                    json_str = response_text[start:end].strip()
                    return json.loads(json_str)
                except (json.JSONDecodeError, ValueError):
                    pass
            error_info = {
                "type": "json_parse_error",
                "response_sample": response_text[:200]
            }
            self.validation_errors.append(error_info)
            return None
    
    def ensure_valid_score(self, score: float) -> float:
        return max(0.0, min(100.0, float(score)))
    
    def ensure_valid_confidence(self, confidence: float) -> float:
        return max(0.0, min(1.0, float(confidence)))
    
    def get_validation_errors(self) -> List[Dict[str, Any]]:
        return self.validation_errors.copy()
    
    def clear_validation_errors(self) -> None:
        self.validation_errors.clear()
    
    @staticmethod
    def _normalize_email_input(email_data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = email_data.copy()
        if "from" in normalized and "from_address" not in normalized:
            normalized["from_address"] = normalized.pop("from")
        if "to" in normalized and "to_address" not in normalized:
            normalized["to_address"] = normalized.pop("to")
        return normalized
    
    def sanitize_text(self, text: str, max_length: int = 10000) -> str:
        if not text:
            return ""
        text = text.replace("\x00", "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if len(text) > max_length:
            text = text[:max_length] + "...[truncated]"
        return text.strip()


_guardrail_service: Optional[GuardrailService] = None


def get_guardrail_service() -> GuardrailService:
    global _guardrail_service
    if _guardrail_service is None:
        _guardrail_service = GuardrailService()
    return _guardrail_service
