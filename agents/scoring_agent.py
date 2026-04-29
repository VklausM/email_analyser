from typing import List

from schemas.models import EmailInput, EmailAnalysis, EmailScoringResult, ScoringFactors
from config import settings
from db import get_sender_modifier
from utils.logger import get_logger

log = get_logger("scoring_agent")

EVIDENCE_LEVEL_SCORES = {
    "critical": 30.0,
    "high": 20.0,
    "medium": 10.0,
    "low": 3.0,
}

DISPLAY_LABELS = {
    "critical": "Critical Risk",
    "high": "High Risk",
    "medium": "Medium Risk",
    "low": "Normal Email",
}


class ScoringAgent:
    def score_batch(
        self,
        emails: List[EmailInput],
        analyses: List[EmailAnalysis]
    ) -> List[EmailScoringResult]:
        if not emails or not analyses:
            return []

        results = []
        email_map = {e.email_id: e for e in emails}

        for analysis in analyses:
            email = email_map.get(analysis.email_id)
            if email is None:
                log.warning("No matching email for analysis %s", analysis.email_id)
                continue
            try:
                results.append(self._score(email, analysis))
            except Exception as e:
                log.error("Scoring failed for %s: %s", analysis.email_id, e)

        results.sort(key=lambda r: r.risk_score, reverse=True)

        for rank, result in enumerate(results, start=1):
            result.rank = rank

        return results

    def _score(self, email: EmailInput, analysis: EmailAnalysis) -> EmailScoringResult:
        weights = settings.SCORING_WEIGHTS

        classification_weights = [weights.get(c, 0.05) for c in analysis.classifications]
        base_weight = max(classification_weights) if classification_weights else 0.0

        if analysis.classifications == ["normal_email"]:
            base_weight = 0.0

        base_score = base_weight * 50.0

        evidence_score = sum(
            EVIDENCE_LEVEL_SCORES.get(line.risk_level, 3.0) * line.confidence
            for line in analysis.evidence_lines
        )
        evidence_score = min(evidence_score, 40.0)

        confidence_factor = 0.5 + (analysis.confidence * 0.5)

        raw_score = (base_score + evidence_score) * confidence_factor

        sender_modifier = get_sender_modifier(email.from_address)

        final_score = min(100.0, max(0.0, raw_score * sender_modifier))
        final_score = round(final_score, 2)

        criticality_level = self._get_level(final_score)
        display_label = DISPLAY_LABELS.get(criticality_level, criticality_level.title())

        factors = ScoringFactors(
            confidence_score=analysis.confidence,
            criticality_score=base_weight,
            evidence_contribution=round(evidence_score, 2),
            sender_modifier=round(sender_modifier, 3),
        )

        log.debug(
            "%s → score=%.2f, level=%s, sender_mod=%.3f",
            email.email_id, final_score, criticality_level, sender_modifier
        )

        return EmailScoringResult(
            email_id=email.email_id,
            analysis=analysis,
            risk_score=final_score,
            criticality_level=criticality_level,
            display_label=display_label,
            scoring_factors=factors,
        )

    @staticmethod
    def _get_level(score: float) -> str:
        t = settings.CRITICALITY_THRESHOLDS
        if score >= t.get("critical", 75.0):
            return "critical"
        if score >= t.get("high", 50.0):
            return "high"
        if score >= t.get("medium", 25.0):
            return "medium"
        return "low"