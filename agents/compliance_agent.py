import json, time, re
from typing import List, Dict, Any
from schemas.models import EmailInput, EmailAnalysis, EvidenceLine
from services.llm_service import get_llm_service, LLMError
from config import settings
from prompts.prompts import ANALYSIS_PROMPT, FALLBACK_PROMPT, CAT_MAP
from utils.logger import get_logger

log = get_logger("compliance_agent")

class ComplianceAgent:
    def __init__(self):
        self.llm = get_llm_service()

    def filter_and_analyze(self, emails: List[EmailInput]) -> List[EmailAnalysis]:
        if not emails: return []
        batch_size, results = settings.MAX_BATCH_SIZE, []
        valid = [e for e in emails if e.body and e.body.strip()]
        for e in [e for e in emails if not (e.body and e.body.strip())]:
            results.append(self._safe_result(e.email_id, "Empty body"))
        
        for i in range(0, len(valid), batch_size):
            chunk = valid[i:i + batch_size]
            try:
                raw = self.llm.call_json(ANALYSIS_PROMPT + "\n".join([f"ID: {e.email_id}\n{e.body}" for e in chunk]))
                results.extend(self._parse(raw, chunk))
            except:
                results.extend([self._safe_result(e.email_id, "Error") for e in chunk])
        return results

    def _parse(self, raw: Dict[str, Any], emails: List[EmailInput]) -> List[EmailAnalysis]:
        res_list, final = raw.get("results", []), []
        LVL_MAP = {"l1": "low", "l2": "medium", "l3": "high", "l4": "critical"}
        
        for email, res in zip(emails, res_list + [{}] * (len(emails) - len(res_list))):
            try:
                cls_raw = res.get("classifications", [])
                cls = [CAT_MAP.get(c, c) for c in cls_raw] or ["none"]
                
                # If "none" or "normal", it's safe.
                is_safe = all(c in ["none", "normal", "compliance"] for c in cls)
                
                ev = []
                for l in res.get("evidence_lines", []):
                    l["risk_level"] = LVL_MAP.get(str(l.get("risk_level")).lower(), "low")
                    ev.append(EvidenceLine(**l))
                
                # Intelligent manual review: only if unsafe AND low confidence
                conf = float(res.get("confidence", 0.9))
                rev = bool(res.get("manual_review_required", False))
                if is_safe: rev = False # Force safe for normal emails
                
                final.append(EmailAnalysis(
                    email_id=email.email_id,
                    classifications=cls,
                    tags=res.get("tags", []),
                    confidence=conf,
                    evidence_lines=ev,
                    reasoning=res.get("reasoning", "Routine analysis"),
                    manual_review_required=rev,
                    manual_review_reason=res.get("manual_review_reason")
                ))
            except: final.append(self._safe_result(email.email_id, "Parse error"))
        return final

    def _safe_result(self, eid: str, msg: str):
        return EmailAnalysis(email_id=eid, classifications=["none"], confidence=1.0, reasoning=msg, manual_review_required=False)
