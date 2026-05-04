from typing import List
from schemas.models import EmailInput, EmailAnalysis, EmailScoringResult, ScoringFactors
from config import settings
from db import get_sender_modifier
from services.llm_service import get_llm_service
from prompts.prompts import SCORING_PROMPT, CAT_MAP, CATEGORY_SCORES, REVERSE_CAT_MAP
from utils.logger import get_logger

log = get_logger("scoring_specialist")

LABELS = {
    "critical": "Critical Risk",
    "high": "High Risk",
    "medium": "Medium Risk",
    "low": "Normal"
}


class ScoringAgent:
    def __init__(self):
        self.llm = get_llm_service()

    def score_batch(self, emails: List[EmailInput], analyses: List[EmailAnalysis]) -> List[EmailScoringResult]:
        if not emails:
            return []

        results = []
        email_map = {e.email_id: e for e in emails}

        for a in analyses:
            email = email_map.get(a.email_id)
            log.debug(f"Analysing email: {a.email_id}")

            if not email:
                continue

            try:
                res = self._calculate_risk(email, a)
                log.debug(f"score for email {a.email_id}: {res.risk_score}")
                results.append(res)
            except Exception as err:
                log.debug(f"Error scoring {a.email_id}: {err}")

        results.sort(key=lambda r: r.risk_score, reverse=True)

        for i, r in enumerate(results, 1):
            r.rank = i

        return results

    def _calculate_risk(self, email: EmailInput, a: EmailAnalysis) -> EmailScoringResult:
        if not a.classifications:
            return self._build_result(email, a, 0, 1.0)

        evidence_count = len(a.evidence_lines)

        det_score = self._det_score(
            a.classifications,
            a.confidence,
            evidence_count
        )

        gen_score = det_score

        try:
            readable_categories = [
                CAT_MAP.get(cid, cid) for cid in a.classifications
            ]

            prompt = SCORING_PROMPT.format(
                classifications=", ".join(readable_categories),
                reasoning=a.reasoning or "No significant findings",
                evidence_count=evidence_count,
                confidence=a.confidence
            )

            res = self.llm.call_json(prompt)
            gen_score = float(res.get("score", det_score))

        except Exception as err:
            log.debug(f"LLM scoring failed: {err}")

        sender_mod = get_sender_modifier(email.from_address)

        det_score_adj = det_score * sender_mod
        gen_score_adj = gen_score * sender_mod

        final_score = round(
            0.6 * det_score_adj +
            0.4 * gen_score_adj
        , 2) if det_score_adj != 0 else round(gen_score_adj, 2)

        final_score = max(0, min(100, final_score))

        log.debug(f"det: {det_score}, gen: {gen_score}, final: {final_score}")

        return self._build_result(email, a, final_score, sender_mod)

    def _build_result(self, email, a, final_score, sender_mod):
        level = self._get_risk_level(final_score)

        if level in ["critical", "high", "medium"]:
            a.manual_review_required = False
        elif level == "low" and a.confidence < settings.CONFIDENCE_THRESHOLD:
            a.manual_review_required = True
        else:
            a.manual_review_required = False

        return EmailScoringResult(
            email_id=email.email_id,
            analysis=a,
            risk_score=final_score,
            criticality_level=level,
            display_label=LABELS.get(level, "Normal"),
            scoring_factors=ScoringFactors(
                confidence_score=a.confidence,
                criticality_score=final_score / 100,
                evidence_contribution=float(len(a.evidence_lines)),
                sender_modifier=sender_mod
            )
        )

    def _get_risk_level(self, score: float):
        t = settings.CRITICALITY_THRESHOLDS

        if score >= t.get("critical", 75):
            return "critical"
        if score >= t.get("high", 50):
            return "high"
        if score >= t.get("medium", 25):
            return "medium"

        return "low"

    def _det_score(self, classifications, confidence, evidence_count):
        if not classifications:
            return 0

        scores = []

        for cat in classifications:
            cid = REVERSE_CAT_MAP.get(cat)
            category = CAT_MAP.get(cid)
            if not category:
                continue

            scores.append(CATEGORY_SCORES.get(category, 0))

        if not scores or max(scores) == 0:
            return 0

        base_score = max(scores)

        confidence_weight = max(0, min(confidence, 1))
        evidence_weight = min(evidence_count / 5, 1)

        final_score = base_score * 100 * (
            0.6 +
            0.3 * confidence_weight +
            0.1 * evidence_weight
        )

        return min(round(final_score), 100)