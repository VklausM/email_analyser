from typing import List
from schemas.email_models import EmailInput, EmailAnalysis, EmailScoringResult, ScoringFactors
from config import settings

class ScoringAgent:
    def score_email(self, email: EmailInput, analysis: EmailAnalysis) -> EmailScoringResult:
        weights = settings.CRITICALITY_WEIGHTS
        
        c_scores = [weights.get(c, 0.0) for c in analysis.classifications]
        criticality_score = max(c_scores) if c_scores else 0.0
        
        tone_weight = settings.TONE_WEIGHTS.get(analysis.tone, 1.0)
        
        d_weights = settings.TONE_DEVIATION_WEIGHTS
        d_thresholds = settings.TONE_DEVIATION_THRESHOLDS
        
        if analysis.tone_deviation < d_thresholds["low"]:
            d_weight = d_weights["low"]
        elif analysis.tone_deviation < d_thresholds["normal"]:
            d_weight = d_weights["normal"]
        elif analysis.tone_deviation < d_thresholds["high"]:
            d_weight = d_weights["high"]
        else:
            d_weight = d_weights["very_high"]
            
        floor = settings.CONFIDENCE_FLOOR
        
        risk_score = (
            analysis.confidence * 
            criticality_score * 
            tone_weight * 
            d_weight * 
            floor * 
            settings.RISK_SCORE_SCALE
        )
        
        risk_score = min(100.0, risk_score)
        
        level = "low"
        if risk_score >= settings.CRITICALITY_LEVEL_THRESHOLDS["critical"]:
            level = "critical"
        elif risk_score >= settings.CRITICALITY_LEVEL_THRESHOLDS["high"]:
            level = "high"
        elif risk_score >= settings.CRITICALITY_LEVEL_THRESHOLDS["medium"]:
            level = "medium"
            
        return EmailScoringResult(
            email_id=email.email_id,
            analysis=analysis,
            risk_score=risk_score,
            criticality_level=level,
            scoring_factors=ScoringFactors(
                confidence_score=analysis.confidence,
                criticality_score=criticality_score,
                tone_weight=tone_weight,
                tone_deviation_weight=d_weight,
                baseline_floor=floor
            )
        )

    def score_batch(self, emails: List[EmailInput], analyses: List[EmailAnalysis]) -> List[EmailScoringResult]:
        results = [self.score_email(e, a) for e, a in zip(emails, analyses)]
        results.sort(key=lambda x: x.risk_score, reverse=True)
        for i, r in enumerate(results, 1):
            r.rank = i
        return results