
from typing import Dict, List, Optional
from schemas.email_models import EmailInput, EmailAnalysis, EmailScoringResult, ScoringFactors
from config import settings
import logging

logger = logging.getLogger(__name__)


class ScoringAgent:
    
    def __init__(self):
        pass
    
    def score_email(self, email: EmailInput, analysis: EmailAnalysis) -> EmailScoringResult:
        try:
            criticality_score = self._calculate_criticality(analysis.classifications)
            tone_weight = settings.TONE_WEIGHTS.get(analysis.tone, 1.0)
            tone_deviation_weight = self._calculate_tone_deviation_weight(analysis.tone_deviation)
            baseline_floor = settings.CONFIDENCE_FLOOR
            
            risk_score = (
                analysis.confidence 
                * criticality_score 
                * tone_weight 
                * tone_deviation_weight 
                * baseline_floor
            )
            
            risk_score = min(100.0, risk_score * settings.RISK_SCORE_SCALE)
            criticality_level = self._categorize_criticality_level(risk_score)
            
            scoring_factors = ScoringFactors(
                confidence_score=analysis.confidence,
                criticality_score=criticality_score,
                tone_weight=tone_weight,
                tone_deviation_weight=tone_deviation_weight,
                baseline_floor=baseline_floor
            )
            
            logger.info(
                f"Scored {email.email_id}: {risk_score:.2f} - {criticality_level}"
            )
            
            return EmailScoringResult(
                email_id=email.email_id,
                analysis=analysis,
                risk_score=risk_score,
                criticality_level=criticality_level,
                scoring_factors=scoring_factors
            )
        
        except Exception as e:
            logger.error(f"Error scoring {email.email_id}: {str(e)}")
            return self._create_default_score(email.email_id, analysis)
    
    def _calculate_criticality(self, classifications: List[str]) -> float:
        if not classifications:
            return 0.0
        criticalities = [
            settings.CRITICALITY_WEIGHTS.get(c, 0.0) 
            for c in classifications
        ]
        return max(criticalities) if criticalities else 0.0
    
    def _calculate_tone_deviation_weight(self, tone_deviation: float) -> float:
        thresholds = settings.TONE_DEVIATION_THRESHOLDS
        weights = settings.TONE_DEVIATION_WEIGHTS
        
        if tone_deviation < thresholds["low"]:
            return weights["low"]
        elif tone_deviation < thresholds["normal"]:
            return weights["normal"]
        elif tone_deviation < thresholds["high"]:
            return weights["high"]
        else:
            return weights["very_high"]
    
    def _categorize_criticality_level(self, score: float) -> str:
        thresholds = settings.CRITICALITY_LEVEL_THRESHOLDS
        
        if score >= thresholds["critical"]:
            return "critical"
        elif score >= thresholds["high"]:
            return "high"
        elif score >= thresholds["medium"]:
            return "medium"
        else:
            return "low"
    
    def score_batch(self, emails: List[EmailInput], analyses: List[EmailAnalysis]) -> List[EmailScoringResult]:
        results = []
        for email, analysis in zip(emails, analyses):
            result = self.score_email(email, analysis)
            results.append(result)
        
        results.sort(key=lambda x: x.risk_score, reverse=True)
        
        for rank, result in enumerate(results, start=1):
            result.rank = rank
        
        return results
    
    def _create_default_score(self, email_id: str, analysis: EmailAnalysis) -> EmailScoringResult:
        return EmailScoringResult(
            email_id=email_id,
            analysis=analysis,
            risk_score=0.0,
            criticality_level="low",
            scoring_factors=ScoringFactors(
                confidence_score=0.0,
                criticality_score=0.0,
                tone_weight=1.0,
                tone_deviation_weight=1.0,
                baseline_floor=settings.CONFIDENCE_FLOOR
            ),
            rank=0
        )