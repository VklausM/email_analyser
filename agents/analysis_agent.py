import time
from typing import List, Dict, Any
from schemas.models import EmailInput, EmailAnalysis, EvidenceLine
from services.llm_service import get_llm_service, LLMError
from config import settings
from prompts.prompts import ANALYSIS_PROMPT, FALLBACK_PROMPT
from utils.logger import get_logger

log = get_logger("analysis_agent")

class AnalysisAgent:
    def __init__(self):
        self.llm = get_llm_service()

    def analyze_batch(self, emails: List[EmailInput]) -> List[EmailAnalysis]:
        if not emails: return []
        batch_size, results = min(settings.MAX_BATCH_SIZE, 10), []
        valid = [e for e in emails if e.body and e.body.strip()]
        for e in [e for e in emails if not (e.body and e.body.strip())]:
            results.append(self._fallback(e.email_id))
        for i in range(0, len(valid), batch_size):
            chunk = valid[i:i + batch_size]
            try: results.extend(self._process_batch(chunk))
            except: results.extend([self._fallback(e.email_id) for e in chunk])
        return results

    def _process_batch(self, emails: List[EmailInput]) -> List[EmailAnalysis]:
        blocks = [f"ID: {e.email_id}\nFrom: {e.from_address}\nSubject: {e.subject}\nBody:\n{e.body}" for e in emails]
        prompt = ANALYSIS_PROMPT + "\n\n---\n".join(blocks)
        try: response = self.llm.call_json(prompt)
        except LLMError: response = self.llm.call_json(FALLBACK_PROMPT + "\n\n---\n".join(blocks))
        return self._parse_response(response, emails)

    def _parse_response(self, response: Dict[str, Any], emails: List[EmailInput]) -> List[EmailAnalysis]:
        raw = response.get("results", [])
        analyses = []
        for email, res in zip(emails, raw + [{}] * (len(emails) - len(raw))):
            try: analyses.append(self._build_analysis(email, res))
            except: analyses.append(self._fallback(email.email_id))
        return analyses

    def _build_analysis(self, email: EmailInput, res: Dict[str, Any]) -> EmailAnalysis:
        cls = [str(c).strip().lower() for c in res.get("classifications", ["normal_email"]) if c] or ["normal_email"]
        conf = max(0.0, min(1.0, float(res.get("confidence", 0.5))))
        ev = self._parse_evidence(res.get("evidence_lines", []))
        if cls != ["normal_email"] and not ev: conf = min(conf, settings.CONFIDENCE_THRESHOLD - 0.05)
        rev, reason = bool(res.get("manual_review_required", False)), res.get("manual_review_reason")
        if conf < settings.CONFIDENCE_THRESHOLD and cls != ["normal_email"]:
            rev, reason = True, reason or f"Low confidence: {conf:.2f}"
        return EmailAnalysis(email_id=email.email_id, classifications=cls, tags=[t.strip().lower() for t in res.get("tags", []) if isinstance(t, str)], confidence=conf, evidence_lines=ev, reasoning=str(res.get("reasoning", ""))[:2000], manual_review_required=rev, manual_review_reason=reason)

    def _parse_evidence(self, raw: Any) -> List[EvidenceLine]:
        if not isinstance(raw, list): return []
        lines = []
        for idx, item in enumerate(raw):
            if not isinstance(item, dict) or not str(item.get("text", "")).strip(): continue
            risk = str(item.get("risk_level", "low")).lower()
            if risk not in {"low", "medium", "high", "critical"}: risk = "low"
            try: lines.append(EvidenceLine(line_number=int(item.get("line_number", idx+1)), text=str(item.get("text", ""))[:2000], risk_level=risk, reason=str(item.get("reason", ""))[:500], confidence=max(0.0, min(1.0, float(item.get("confidence", 0.5))))))
            except: pass
        return lines

    def _fallback(self, email_id: str):
        return EmailAnalysis(email_id=email_id, classifications=["normal_email"], confidence=0.0, reasoning="Analysis failed — manual review required.", manual_review_required=True, manual_review_reason="Processing error")
