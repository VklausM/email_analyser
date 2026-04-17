from typing import Dict, List, Any, Optional
from schemas.email_models import EmailInput, EmailAnalysis
from services.llm_service import get_llm_service
from services.guardrail_service import get_guardrail_service
from services.embedding_service import get_sender_profile_service
from config import settings
import logging

logger = logging.getLogger(__name__)


class EmailAnalysisAgent:
    
    ANALYSIS_PROMPT = """Analyze this email for BFSI compliance risks.
    
From: {from_address}
To: {to_address}
Subject: {subject}
Body:
{body}

Detect these issues: malicious, money_laundering, insider_trading, secrecy_breach, bribery,
fraud, phishing, scam, market_manipulation, quid_pro_quo, none

Return JSON with:
- classifications: List[str]
- confidence: float (0-1)
- tone: str (neutral/aggressive/secretive/pressuring)
- evidence_lines: List[object with line_number, text, risk_level, reason]
- reasoning: str
"""
    
    def __init__(self):
        self.llm_service = get_llm_service()
        self.guardrails = get_guardrail_service()
        self.sender_profiles = get_sender_profile_service()
    
    def analyze(self, email: EmailInput) -> EmailAnalysis:
        try:
            prompt = self.ANALYSIS_PROMPT.format(
                from_address=email.from_address,
                to_address=email.to_address,
                subject=email.subject,
                body=self.guardrails.sanitize_text(email.body)
            )
            
            logger.info(f"Analyzing email {email.email_id}")
            response = self.llm_service.call_with_json(prompt, temperature=0.2)
            
            analysis_data = self._process_llm_response(response, email.email_id)
            
            tone_deviation = self.sender_profiles.calculate_tone_deviation(
                email.from_address,
                email.body
            )
            analysis_data["tone_deviation"] = tone_deviation
            
            confidence = analysis_data["confidence"]
            if confidence < settings.CONFIDENCE_THRESHOLD or tone_deviation > settings.TONE_DEVIATION_THRESHOLD:
                analysis_data["manual_review_required"] = True
                analysis_data["manual_review_reason"] = f"Low confidence or unusual tone"
            else:
                analysis_data["manual_review_required"] = False
                analysis_data["manual_review_reason"] = None
            
            analysis = self.guardrails.validate_email_analysis(analysis_data, strict=False)
            return analysis or self._create_fallback_analysis(email.email_id)
        
        except Exception as e:
            logger.error(f"Error analyzing {email.email_id}: {str(e)}")
            return self._create_fallback_analysis(email.email_id, str(e))
    
    def _process_llm_response(self, response: Dict[str, Any], email_id: str) -> Dict[str, Any]:
        if not response.get("classifications"):
            response["classifications"] = ["unknown"]
        if not response.get("confidence"):
            response["confidence"] = 0.5
        if not response.get("tone"):
            response["tone"] = "neutral"
        if not response.get("evidence_lines"):
            response["evidence_lines"] = []
        if not response.get("reasoning"):
            response["reasoning"] = "Analysis completed"
        
        response["confidence"] = self.guardrails.ensure_valid_confidence(response["confidence"])
        response["email_id"] = email_id
        return response
    
    def _create_fallback_analysis(self, email_id: str, error_msg: Optional[str] = None) -> EmailAnalysis:
        return EmailAnalysis(
            email_id=email_id,
            classifications=["unknown"],
            confidence=0.3,
            tone="neutral",
            tone_deviation=0.0,
            evidence_lines=[],
            reasoning=f"Analysis failed: {error_msg or 'Error'}",
            manual_review_required=True,
            manual_review_reason="Analysis failed"
        )