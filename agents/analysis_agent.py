import time
from typing import List, Dict, Any

from schemas.models import EmailInput, EmailAnalysis, EvidenceLine
from services.llm_service import get_llm_service, LLMError
from config import settings
from prompts.prompts import ANALYSIS_PROMPT, FALLBACK_PROMPT
from utils.logger import get_logger

log = get_logger("analysis_agent")


class AnalysisAgent:
    def __init__(self):
        self.llm = get_llm_service()

    def analyze_batch(self, emails: List[EmailInput]) -> List[EmailAnalysis]:
        if not emails:
            return []

        batch_size = min(settings.MAX_BATCH_SIZE, 10)
        results = []

        valid = [e for e in emails if e.body and e.body.strip()]
        skipped = [e for e in emails if not e.body or not e.body.strip()]

        for e in skipped:
            log.warning("Skipping %s — empty body", e.email_id)
            results.append(self._fallback(e.email_id))

        for i in range(0, len(valid), batch_size):
            chunk = valid[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(valid) + batch_size - 1) // batch_size
            log.info("Processing batch %d/%d (%d emails)", batch_num, total_batches, len(chunk))

            start = time.time()
            try:
                batch_results = self._process_batch(chunk)
            except Exception as e:
                log.error("Batch %d failed: %s — using fallback", batch_num, e)
                batch_results = [self._fallback(e.email_id) for e in chunk]

            elapsed_ms = int((time.time() - start) * 1000)
            log.info("Batch %d done in %dms", batch_num, elapsed_ms)
            results.extend(batch_results)

        return results

    def _process_batch(self, emails: List[EmailInput]) -> List[EmailAnalysis]:
        email_blocks = []
        for e in emails:
            email_blocks.append(
                f"ID: {e.email_id}\nFrom: {e.from_address}\nSubject: {e.subject}\nBody:\n{e.body}"
            )

        prompt = ANALYSIS_PROMPT + "\n\n---\n".join(email_blocks)

        try:
            response = self.llm.call_json(prompt)
        except LLMError:
            log.warning("Primary prompt failed, trying fallback")
            fallback_prompt = FALLBACK_PROMPT + "\n\n---\n".join(email_blocks)
            response = self.llm.call_json(fallback_prompt)

        return self._parse_response(response, emails)

    def _parse_response(self, response: Dict[str, Any], emails: List[EmailInput]) -> List[EmailAnalysis]:
        raw_results = response.get("results", [])

        if len(raw_results) != len(emails):
            log.warning("Result count mismatch: expected %d, got %d", len(emails), len(raw_results))

        analyses = []
        for email, res in zip(emails, raw_results):
            try:
                analyses.append(self._build_analysis(email, res))
            except Exception as e:
                log.error("Failed to parse result for %s: %s", email.email_id, e)
                analyses.append(self._fallback(email.email_id))

        return analyses

    def _build_analysis(self, email: EmailInput, res: Dict[str, Any]) -> EmailAnalysis:
        classifications = self._clean_classifications(res.get("classifications", ["normal_email"]))
        tags = [t.strip().lower() for t in res.get("tags", []) if isinstance(t, str)]

        confidence = float(res.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        evidence_lines = self._parse_evidence(res.get("evidence_lines", []))

        if classifications not in [["normal_email"], ["none"]] and not evidence_lines:
            confidence = min(confidence, settings.CONFIDENCE_THRESHOLD - 0.05)

        manual_review = bool(res.get("manual_review_required", False))
        manual_reason = res.get("manual_review_reason") or None

        if confidence < settings.CONFIDENCE_THRESHOLD and classifications != ["normal_email"]:
            manual_review = True
            manual_reason = manual_reason or f"Low confidence: {confidence:.2f}"

        return EmailAnalysis(
            email_id=email.email_id,
            classifications=classifications,
            tags=tags,
            confidence=confidence,
            evidence_lines=evidence_lines,
            reasoning=str(res.get("reasoning", "No reasoning provided"))[:2000],
            manual_review_required=manual_review,
            manual_review_reason=manual_reason,
        )

    @staticmethod
    def _clean_classifications(raw: Any) -> List[str]:
        if not isinstance(raw, list) or not raw:
            return ["normal_email"]
        cleaned = list({str(c).strip().lower() for c in raw if c})
        return cleaned or ["normal_email"]

    @staticmethod
    def _parse_evidence(raw: Any) -> List[EvidenceLine]:
        if not isinstance(raw, list):
            return []

        lines = []
        valid_levels = {"low", "medium", "high", "critical"}

        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue

            risk = str(item.get("risk_level", "low")).lower()
            if risk not in valid_levels:
                risk = "low"

            try:
                lines.append(EvidenceLine(
                    line_number=int(item.get("line_number", idx + 1)),
                    text=text[:2000],
                    risk_level=risk,
                    reason=str(item.get("reason", f"Evidence line {idx + 1}"))[:500],
                    confidence=max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
                ))
            except Exception:
                continue

        return lines

    @staticmethod
    def _fallback(email_id: str) -> EmailAnalysis:
        return EmailAnalysis(
            email_id=email_id,
            classifications=["normal_email"],
            tags=[],
            confidence=0.0,
            evidence_lines=[],
            reasoning="Analysis failed — manual review required.",
            manual_review_required=True,
            manual_review_reason="Processing error",
        )
