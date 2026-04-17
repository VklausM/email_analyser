import json
import logging
from typing import List
from schemas.email_models import EmailInput, EmailAnalysis, EvidenceLine
from services.llm_service import get_llm_service
from services.cache_service import CacheService
from config import settings

logger = logging.getLogger(__name__)

class EmailAnalysisAgent:
    SYSTEM_PROMPT = """You are a BFSI security domain AI expert. Analyze the emails for actual compliance, security, and financial risk issues.
Return a JSON object with a key "results" containing a list of analysis objects, one for each email in order.
Each analysis object must have:
- email_id: str
- classifications: list
- confidence: float
- evidence_lines: list of { "line_number": int, "text": str, "risk_level": str, "reason": str }
- reasoning: str
- manual_review_required: bool
- manual_review_reason: str or null

Use the following BFSI risk categories when relevant:
- malicious
- fraud
- money_laundering
- market_manipulation
- bribery
- insider_trading
- secrecy_breach
- phishing
- scam
- quid_pro_quo
- none

Only use ["none"] when the email clearly contains no compliance, security, or financial risk issue.
Only mark manual_review_required true when the email is ambiguous, complex, has high-risk compliance concerns, or requires human verification.
If the email appears routine or clearly low-risk, set manual_review_required false and keep evidence_lines concise.
For emails with no compliance issue, use classifications: ["none"] and confidence close to 1.0.
"""

    def __init__(self):
        self.llm = get_llm_service()
        self.cache = CacheService()

    def analyze_batch(self, emails: List[EmailInput], batch_size: int = 5) -> List[EmailAnalysis]:
        all_results = []
        to_process = []
        
        for email in emails:
            if not email.body.strip():
                all_results.append(
                    EmailAnalysis(
                        email_id=email.email_id,
                        classifications=["unknown"],
                        confidence=0.0,
                        evidence_lines=[],
                        reasoning="Empty email body; skipping automated analysis.",
                        manual_review_required=False,
                        manual_review_reason="Empty body"
                    )
                )
                continue

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
                batch_results = []
                if isinstance(response, dict) and "results" in response:
                    batch_results = response["results"]
                elif isinstance(response, list):
                    batch_results = response
                else:
                    raise RuntimeError("Unexpected analysis response format")

                for email, res_dict in zip(chunk, batch_results):
                    res_dict["email_id"] = email.email_id
                    if "manual_review_required" not in res_dict:
                        res_dict["manual_review_required"] = res_dict.get("confidence", 0) < settings.CONFIDENCE_THRESHOLD
                    else:
                        res_dict["manual_review_required"] = bool(res_dict["manual_review_required"])

                    if res_dict["manual_review_required"] and "manual_review_reason" not in res_dict:
                        res_dict["manual_review_reason"] = (
                            "Low confidence or ambiguous compliance risk"
                            if res_dict.get("confidence", 0) < settings.CONFIDENCE_THRESHOLD
                            else "Requires human review"
                        )
                    elif not res_dict["manual_review_required"]:
                        res_dict["manual_review_reason"] = None

                    try:
                        evidence_lines = res_dict.get("evidence_lines", [])
                        if evidence_lines and isinstance(evidence_lines[0], dict):
                            evidence_lines = [EvidenceLine(**line) for line in evidence_lines]
                        res_dict["evidence_lines"] = evidence_lines
                        analysis = EmailAnalysis(**res_dict)
                        self.cache.set(email.body, email.from_address, analysis.model_dump())
                        all_results.append(analysis)
                    except Exception as e:
                        logger.error("Error creating analysis for %s: %s", email.email_id, e)
                        all_results.append(self._fallback(email.email_id))
            except Exception as e:
                logger.error("LLM batch analysis failed for emails %s-%s: %s", chunk[0].email_id, chunk[-1].email_id, e)
                for email in chunk:
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
            evidence_lines=[],
            reasoning="Analysis failed",
            manual_review_required=True,
            manual_review_reason="System error"
        )