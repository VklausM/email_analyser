from typing import List
from schemas.email_models import EmailInput, EmailAnalysis, EmailScoringResult, ScoringFactors
from config import settings

class ScoringAgent:
    def score_email(self, email: EmailInput, analysis: EmailAnalysis) -> EmailScoringResult:
        weights = settings.CRITICALITY_WEIGHTS
        c_scores = [weights.get(c, 0.1) for c in analysis.classifications]
        criticality_score = max(c_scores) if c_scores else 0.0
        floor = settings.CONFIDENCE_FLOOR

        risk_score = (
            analysis.confidence *
            criticality_score *
            floor *
            settings.RISK_SCORE_SCALE
        )

        risk_score = min(100.0, risk_score)

        thresholds = settings.CRITICALITY_LEVEL_THRESHOLDS
        critical_threshold = thresholds.get("critical", 75.0)
        high_threshold = thresholds.get("high", 50.0)
        medium_threshold = thresholds.get("medium", 25.0)

        level = "low"
        if risk_score >= critical_threshold:
            level = "critical"
        elif risk_score >= high_threshold:
            level = "high"
        elif risk_score >= medium_threshold:
            level = "medium"

        return EmailScoringResult(
            email_id=email.email_id,
            analysis=analysis,
            risk_score=risk_score,
            criticality_level=level,
            scoring_factors=ScoringFactors(
                confidence_score=analysis.confidence,
                criticality_score=criticality_score,
                baseline_floor=floor,
            )
        )

    def score_batch(self, emails: List[EmailInput], analyses: List[EmailAnalysis]) -> List[EmailScoringResult]:
        results = [self.score_email(e, a) for e, a in zip(emails, analyses)]
        results.sort(key=lambda x: x.risk_score, reverse=True)
        for i, r in enumerate(results, 1):
            r.rank = i
        return results