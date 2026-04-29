import logging
from typing import List
from schemas.email_models import EmailInput, EmailAnalysis, EmailScoringResult, ScoringFactors
from config import settings

logger = logging.getLogger(__name__)


class ScoringAgent:
    def _compute_score(self, analysis: EmailAnalysis) -> float:
        if not analysis:
            logger.warning("Null analysis provided to scorer")
            return 0.0
        
        classifications = analysis.classifications or ["none"]
        confidence = analysis.confidence or 0.0
        evidence_lines = analysis.evidence_lines or []
        
        # Validate confidence
        confidence = max(0.0, min(1.0, confidence))
        
        # Calculate base risk from classifications
        classification_weights = [
            settings.CRITICALITY_WEIGHTS.get(c, 0.1)
            for c in classifications
        ]
        
        if not classification_weights:
            base_risk = 0.0
        else:
            base_risk = max(classification_weights)
        
        base_score = base_risk * 50.0
        
        # Calculate evidence contribution
        risk_thresholds = settings.CRITICALITY_LEVEL_THRESHOLDS
        
        evidence_score = 0.0
        for line in evidence_lines:
            risk_level = line.risk_level if hasattr(line, 'risk_level') else 'low'
            risk_level = risk_level.lower()
            
            # Map risk level to score contribution
            level_scores = {
                'critical': 35.0,
                'high': 25.0,
                'medium': 15.0,
                'low': 5.0
            }
            evidence_score += level_scores.get(risk_level, 5.0)
        
        # Confidence factor: reduces uncertainty
        confidence_factor = 0.6 + (confidence * 0.4)  # Range: 0.6 - 1.0
        
        # Uncertainty boost for low confidence findings
        uncertainty_boost = 0.0
        if confidence < settings.CONFIDENCE_THRESHOLD:
            uncertainty_boost = (settings.CONFIDENCE_THRESHOLD - confidence) * 40.0
        
        # Final score calculation
        score = (
            base_score +
            evidence_score
        ) * confidence_factor + uncertainty_boost
        
        # Cap at maximum
        final_score = min(100.0, max(0.0, score))
        
        
        return round(final_score, 2)

    def _get_criticality_level(self, score: float) -> str:
        thresholds = settings.CRITICALITY_LEVEL_THRESHOLDS
        
        score = max(0.0, min(100.0, score))
        
        if score >= thresholds.get("critical", 75.0):
            return "critical"
        elif score >= thresholds.get("high", 50.0):
            return "high"
        elif score >= thresholds.get("medium", 25.0):
            return "medium"
        else:
            return "low"

    def score_email(
        self,
        email: EmailInput,
        analysis: EmailAnalysis
    ) -> EmailScoringResult:
        if not email or not analysis:
            raise ValueError("Email and analysis must not be None")
        
        if email.email_id != analysis.email_id:
            logger.warning(
                f"Email ID mismatch: {email.email_id} vs {analysis.email_id}"
            )
        
        # Compute risk score
        risk_score = self._compute_score(analysis)
        
        # Determine criticality level
        criticality_level = self._get_criticality_level(risk_score)
        
        # Extract criticality weights for classifications
        weights = [
            settings.CRITICALITY_WEIGHTS.get(c, 0.1)
            for c in analysis.classifications
        ]
        criticality_score = max(weights) if weights else 0.0
        
        # Build scoring factors for audit trail
        scoring_factors = ScoringFactors(
            confidence_score=analysis.confidence,
            criticality_score=criticality_score,
            baseline_floor=settings.CONFIDENCE_FLOOR,
            evidence_contribution=len(analysis.evidence_lines) * 5.0
        )
        
        # Create scoring result
        result = EmailScoringResult(
            email_id=email.email_id,
            analysis=analysis,
            risk_score=risk_score,
            criticality_level=criticality_level,
            scoring_factors=scoring_factors,
            rank=0
        )
        
        logger.debug(
            f"Scored {email.email_id}: score={risk_score:.2f}, "
            f"level={criticality_level}, confidence={analysis.confidence:.2f}"
        )
        
        return result

    def score_batch(
        self,
        emails: List[EmailInput],
        analyses: List[EmailAnalysis]
    ) -> List[EmailScoringResult]:
        if not emails or not analyses:
            logger.warning("Empty email or analysis list")
            return []
        
        if len(emails) != len(analyses):
            raise ValueError(
                f"Email count ({len(emails)}) != analysis count ({len(analyses)})"
            )
        
        logger.info(f"Scoring {len(emails)} emails")
        
        results = []
        errors = []
        
        # Score each email
        for email, analysis in zip(emails, analyses):
            try:
                scored = self.score_email(email, analysis)
                results.append(scored)
            except Exception as e:
                logger.error(f"Failed to score {email.email_id}: {e}")
                errors.append({
                    'email_id': email.email_id,
                    'error': str(e)
                })
        
        if errors:
            logger.warning(f"Failed to score {len(errors)} emails")
        

        results.sort(key=lambda x: x.risk_score, reverse=True)
        
        # Assign ranks
        for rank, result in enumerate(results, start=1):
            result.rank = rank
        

        if results:
            critical = len([r for r in results if r.criticality_level == "critical"])
            high = len([r for r in results if r.criticality_level == "high"])
            logger.info(
                f"Scoring complete: {len(results)} scored, "
                f"{critical} critical, {high} high, {len(errors)} errors"
            )
        
        return results