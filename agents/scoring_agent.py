from typing import List
from schemas.models import EmailInput, EmailAnalysis, EmailScoringResult, ScoringFactors
from config import settings
from db import get_sender_modifier
from utils.logger import get_logger

log = get_logger("scoring_agent")

RISK_VALUES = {"critical": 35, "high": 20, "medium": 10, "low": 2}
LABELS = {"critical": "Critical Risk", "high": "High Risk", "medium": "Medium Risk", "low": "Normal"}

class ScoringAgent:
    def score_batch(self, emails: List[EmailInput], analyses: List[EmailAnalysis]) -> List[EmailScoringResult]:
        if not emails: return []
        results, email_map = [], {e.email_id: e for e in emails}
        for a in analyses:
            e = email_map.get(a.email_id)
            if e:
                try: results.append(self._calculate(e, a))
                except: pass
        results.sort(key=lambda r: r.risk_score, reverse=True)
        for i, r in enumerate(results, 1): r.rank = i
        return results

    def _calculate(self, email: EmailInput, a: EmailAnalysis) -> EmailScoringResult:
        weights = settings.SCORING_WEIGHTS
        base_risk = max([weights.get(c, 0.1) for c in a.classifications]) if a.classifications != ["normal_email"] else 0.0
        
        evidence_score = sum(RISK_VALUES.get(line.risk_level, 2) for line in a.evidence_lines)
        evidence_score = min(evidence_score, 45)

        sender_mod = get_sender_modifier(email.from_address)
        
        # Combined score calculation
        score = (base_risk * 50) + (evidence_score * 1.2)
        score *= (0.7 + (a.confidence * 0.3))
        score *= sender_mod
        
        # Final normalization to ensure it fits 0-100 and feels balanced
        final_score = round(max(0, min(100, score)), 2)
        level = self._get_level(final_score)
        
        # Reduce manual work: suppress flags for low-medium risk emails
        if final_score < 30: a.manual_review_required = False
        
        return EmailScoringResult(
            email_id=email.email_id,
            analysis=a,
            risk_score=final_score,
            criticality_level=level,
            display_label=LABELS.get(level, "Low Risk"),
            scoring_factors=ScoringFactors(
                confidence_score=a.confidence,
                criticality_score=base_risk,
                evidence_contribution=evidence_score,
                sender_modifier=sender_mod
            )
        )

    def _get_level(self, score: float):
        t = settings.CRITICALITY_THRESHOLDS
        if score >= t.get("critical", 75): return "critical"
        if score >= t.get("high", 50): return "high"
        if score >= t.get("medium", 25): return "medium"
        return "low"