from typing import List, Dict, Any
from schemas.models import EmailInput, EmailAnalysis, EmailScoringResult, ScoringFactors
from config import settings
from db import get_sender_modifier
from services.llm_service import get_llm_service
from prompts.prompts import SCORING_PROMPT
from utils.logger import get_logger

log = get_logger("scoring_specialist")

LABELS = {"critical": "Critical Risk", "high": "High Risk", "medium": "Medium Risk", "low": "Normal"}

class ScoringAgent:
    def __init__(self):
        self.llm = get_llm_service()

    def score_batch(self, emails: List[EmailInput], analyses: List[EmailAnalysis]) -> List[EmailScoringResult]:
        if not emails: return []
        results, email_map = [], {e.email_id: e for e in emails}
        for a in analyses:
            e = email_map.get(a.email_id)
            if e:
                try: results.append(self._calculate_risk(e, a))
                except: pass
        results.sort(key=lambda r: r.risk_score, reverse=True)
        for i, r in enumerate(results, 1): r.rank = i
        return results

    def _calculate_risk(self, email: EmailInput, a: EmailAnalysis) -> EmailScoringResult:
        # Step 1: Gen AI Risk Assessment
        try:
            prompt = SCORING_PROMPT.format(
                classifications=", ".join(a.classifications),
                reasoning=a.reasoning,
                evidence_count=len(a.evidence_lines),
                confidence=a.confidence
            )
            res = self.llm.call_json(prompt)
            gen_score = float(res.get("score", 0))
        except:
            gen_score = self._formula_fallback(a)

        # Step 2: Apply human-defined weights and modifiers
        sender_mod = get_sender_modifier(email.from_address)
        final_score = round(max(0, min(100, gen_score * sender_mod)), 2)
        
        level = self._get_risk_level(final_score)
        if final_score < 30: a.manual_review_required = False
        
        return EmailScoringResult(
            email_id=email.email_id,
            analysis=a,
            risk_score=final_score,
            criticality_level=level,
            display_label=LABELS.get(level, "Low Risk"),
            scoring_factors=ScoringFactors(
                confidence_score=a.confidence,
                criticality_score=gen_score / 100,
                evidence_contribution=float(len(a.evidence_lines)),
                sender_modifier=sender_mod
            )
        )

    def _formula_fallback(self, a: EmailAnalysis) -> float:
        weights = settings.SCORING_WEIGHTS
        base = max([weights.get(c, 0.1) for c in a.classifications]) if a.classifications != ["none"] else 0.0
        evidence = min(len(a.evidence_lines) * 10, 40)
        return (base * 60) + evidence

    def _get_risk_level(self, score: float):
        t = settings.CRITICALITY_THRESHOLDS
        if score >= t.get("critical", 75): return "critical"
        if score >= t.get("high", 50): return "high"
        if score >= t.get("medium", 25): return "medium"
        return "low"