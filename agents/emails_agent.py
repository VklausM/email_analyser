import json
from typing import List
from schemas.email_models import EmailInput, EmailAnalysis
from services.llm_service import get_llm_service
from services.guardrail_service import get_guardrail_service
from services.embedding_service import get_sender_profile_service
from services.cache_service import CacheService
from config import settings

class EmailAnalysisAgent:
    SYSTEM_PROMPT = """You are a BFSI Compliance Expert. Analyze these emails for compliance issues. 
Return a JSON object with a key "results" containing a list of analysis objects, one for each email in order.
Each analysis object must have:
- email_id: str
- classifications: list
- confidence: float
- tone: str
- evidence_lines: list of { "line_number": int, "text": str, "risk_level": str, "reason": str }
- reasoning: str"""

    def __init__(self):
        self.llm = get_llm_service()
        self.guardrails = get_guardrail_service()
        self.profiles = get_sender_profile_service()
        self.cache = CacheService()

    def analyze_batch(self, emails: List[EmailInput], batch_size: int = 5) -> List[EmailAnalysis]:
        all_results = []
        to_process = []
        
        for email in emails:
            cached = self.cache.get(email.body, email.from_address)
            if cached:
                all_results.append(EmailAnalysis(**cached))
            else:
                to_process.append(email)
        
        for i in range(0, len(to_process), batch_size):
            chunk = to_process[i:i + batch_size]
            prompt_data = []
            for email in chunk:
                prompt_data.append(f"ID: {email.email_id}\nFrom: {email.from_address}\nSubject: {email.subject}\nBody: {email.body}")
            
            full_prompt = f"{self.SYSTEM_PROMPT}\n\nEmails to analyze:\n\n" + "\n---\n".join(prompt_data)
            
            try:
                response = self.llm.call_with_json(full_prompt)
                batch_results = response.get("results", [])
                
                for email, res_dict in zip(chunk, batch_results):
                    deviation = self.profiles.calculate_tone_deviation(email.from_address, email.body)
                    res_dict["email_id"] = email.email_id # Ensure ID matches
                    res_dict["tone_deviation"] = deviation
                    res_dict["manual_review_required"] = res_dict.get("confidence", 0) < settings.CONFIDENCE_THRESHOLD or deviation > settings.TONE_DEVIATION_THRESHOLD
                    
                    analysis = self.guardrails.validate_email_analysis(res_dict)
                    if analysis:
                        self.cache.set(email.body, email.from_address, analysis.model_dump())
                        all_results.append(analysis)
                    else:
                        all_results.append(self._fallback(email.email_id))
            except:
                for email in chunk:
                    all_results.append(self._fallback(email.email_id))
                    
        return all_results

    def _fallback(self, email_id: str) -> EmailAnalysis:
        return EmailAnalysis(
            email_id=email_id,
            classifications=["unknown"],
            confidence=0.0,
            tone="neutral",
            tone_deviation=0.0,
            evidence_lines=[],
            reasoning="Analysis failed",
            manual_review_required=True,
            manual_review_reason="System error"
        )