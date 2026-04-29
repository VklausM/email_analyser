from typing import List
from schemas.models import EmailInput, EmailAnalysis, EmailScoringResult, ScoringFactors
from config import settings
from db import get_sender_modifier
from utils.logger import get_logger

log = get_logger("scoring_agent")

EVIDENCE_LEVEL_SCORES = {"critical": 30.0, "high": 20.0, "medium": 10.0, "low": 3.0}
DISPLAY_LABELS = {"critical": "Critical Risk", "high": "High Risk", "medium": "Medium Risk", "low": "Normal Email"}

class ScoringAgent:
    def score_batch(self, emails: List[EmailInput], analyses: List[EmailAnalysis]) -> List[EmailScoringResult]:
        if not emails or not analyses: return []
        results, email_map = [], {e.email_id: e for e in emails}
        for a in analyses:
            e = email_map.get(a.email_id)
            if e:
                try: results.append(self._score(e, a))
                except: pass
        results.sort(key=lambda r: r.risk_score, reverse=True)
        for i, r in enumerate(results, 1): r.rank = i
        return results

    def _score(self, email: EmailInput, a: EmailAnalysis) -> EmailScoringResult:
        w = settings.SCORING_WEIGHTS
        base = max([w.get(c, 0.05) for c in a.classifications]) if a.classifications != ["normal_email"] else 0.0
        ev = min(sum(EVIDENCE_LEVEL_SCORES.get(l.risk_level, 3.0) * l.confidence for l in a.evidence_lines), 40.0)
        conf = 0.5 + (a.confidence * 0.5)
        mod = get_sender_modifier(email.from_address)
        final = round(min(100.0, max(0.0, (base * 50.0 + ev) * conf * mod)), 2)
        level = self._get_level(final)
        return EmailScoringResult(email_id=email.email_id, analysis=a, risk_score=final, criticality_level=level, display_label=DISPLAY_LABELS.get(level, level.title()), scoring_factors=ScoringFactors(confidence_score=a.confidence, criticality_score=base, evidence_contribution=round(ev, 2), sender_modifier=round(mod, 3)))

    def _get_level(self, score: float):
        t = settings.CRITICALITY_THRESHOLDS
        if score >= t.get("critical", 75.0): return "critical"
        if score >= t.get("high", 50.0): return "high"
        if score >= t.get("medium", 25.0): return "medium"
        return "low"