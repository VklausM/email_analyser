import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from schemas.email_models import EmailInput, EmailAnalysis, EvidenceLine
from services.llm_service import get_llm_service, LLMServiceError
from config import settings
from prompts.EMAIL_AGENT_PROMPT import EMAIL_AGENT_PROMPT
from prompts.FALLBACK_PROMPT import FALLBACK_PROMPT

logger = logging.getLogger(__name__)


class EmailAnalysisError(Exception):
    """Exception for email analysis failures."""
    pass


class EmailAnalysisAgent:
    def __init__(self):
        try:
            self.llm = get_llm_service()
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {e}")
            raise EmailAnalysisError(f"Agent initialization failed: {e}") from e

    @staticmethod
    def _fallback(email_id: str) -> EmailAnalysis:
        logger.warning(f"Creating fallback analysis for email {email_id}")
        
        return EmailAnalysis(
            email_id=email_id,
            classifications=["none"],
            confidence=0.0,
            evidence_lines=[],
            reasoning="Fallback analysis due to processing error. Manual review required.",
            manual_review_required=True,
            manual_review_reason="Processing failed - unable to analyze email",
            processing_duration_ms=0
        )

    @staticmethod
    def _should_manual_review(analysis: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        classifications = analysis.get("classifications", [])
        confidence = analysis.get("confidence", 0)
        evidence_lines = analysis.get("evidence_lines", [])
        
        # Get high-risk classifications
        high_risk_weights = {
            k: v for k, v in settings.CRITICALITY_WEIGHTS.items()
            if v >= 0.8
        }
        high_risk = any(c in high_risk_weights for c in classifications)
        
        # Check for strong evidence
        strong_evidence = any(
            (line.get("risk_level") if isinstance(line, dict) else getattr(line, "risk_level", None))
            in settings.CRITICALITY_LEVEL_THRESHOLDS.keys()
            for line in evidence_lines
        )
        
        # Strong signal + high confidence → no review needed
        if high_risk and confidence >= settings.CONFIDENCE_THRESHOLD:
            return False, None
        
        # Low confidence → needs review
        if confidence < settings.CONFIDENCE_THRESHOLD:
            return True, f"Low confidence score: {confidence:.2f}"
        
        # No strong evidence despite classification → needs review
        if not strong_evidence and classifications != ["none"]:
            return True, "Classifications without strong evidence"
        
        # Ambiguous case
        if not classifications or classifications == ["none"]:
            return False, None
        
        return False, None

    @staticmethod
    def _process_evidence_lines(
        evidence_lines: List[Dict[str, Any]]
    ) -> List[EvidenceLine]:
        validated = []
        
        for idx, line in enumerate(evidence_lines):
            if not isinstance(line, dict):
                logger.warning(f"Skipping non-dict evidence line {idx}")
                continue
            
            try:
                # Extract and validate fields
                line_number = line.get("line_number", idx + 1)
                if not isinstance(line_number, int) or line_number < 1:
                    line_number = idx + 1
                
                text = line.get("text", "").strip()
                if not text:
                    logger.warning(f"Skipping empty evidence text at {line_number}")
                    continue
                
                # Normalize risk level
                risk_level = line.get("risk_level", "low").lower()
                if risk_level not in settings.CRITICALITY_LEVEL_THRESHOLDS.keys():
                    logger.warning(f"Invalid risk level '{risk_level}', defaulting to 'low'")
                    risk_level = "low"
                
                reason = line.get("reason", "").strip()
                if not reason:
                    reason = f"Evidence at line {line_number}"
                
                confidence = float(line.get("confidence", 0.5))
                confidence = max(0.0, min(1.0, confidence))
                
                # Create validated evidence line
                evidence = EvidenceLine(
                    line_number=line_number,
                    text=text[:5000],  # Truncate if too long
                    risk_level=risk_level,
                    reason=reason[:500],
                    confidence=confidence
                )
                validated.append(evidence)
                
            except Exception as e:
                logger.warning(f"Failed to process evidence line {idx}: {e}")
                continue
        
        return validated

    @staticmethod
    def _process_classifications(
        classifications: List[str]
    ) -> List[str]:
        if not classifications or not isinstance(classifications, list):
            return ["none"]
        
        validated = []
        for c in classifications:
            if isinstance(c, str):
                c = c.strip().lower()
                if c and c not in validated:
                    validated.append(c)
        
        if not validated:
            return ["none"]
        
        return validated

    def _process_email_result(
        self,
        email: EmailInput,
        res_dict: Dict[str, Any],
        processing_duration_ms: int = 0
    ) -> EmailAnalysis:
        if not isinstance(res_dict, dict):
            raise ValueError("Response must be a dictionary")
        
        # Extract and validate basic fields
        email_id = email.email_id
        
        classifications = self._process_classifications(
            res_dict.get("classifications", ["none"])
        )
        
        confidence = float(res_dict.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        
        reasoning = res_dict.get("reasoning", "No reasoning provided").strip()
        reasoning = reasoning[:2000]  # Truncate if too long
        
        # Process evidence lines
        evidence_lines_raw = res_dict.get("evidence_lines", [])
        evidence_lines = self._process_evidence_lines(
            evidence_lines_raw if isinstance(evidence_lines_raw, list) else []
        )
        
        # Boost confidence if we have strong evidence despite non-'none' classification
        if classifications != ["none"] and not evidence_lines:
            logger.warning(f"{email_id}: Classifications without evidence, lowering confidence")
            confidence = min(confidence, settings.CONFIDENCE_THRESHOLD - 0.1)
        elif classifications != ["none"] and evidence_lines:
            # Boost confidence if we have multiple strong evidence pieces
            if len(evidence_lines) > 1:
                confidence = max(confidence, settings.CONFIDENCE_THRESHOLD)
        
        # Determine manual review requirement
        manual_review_required, manual_review_reason = self._should_manual_review({
            "classifications": classifications,
            "confidence": confidence,
            "evidence_lines": evidence_lines
        })
        
        # Create analysis object
        analysis = EmailAnalysis(
            email_id=email_id,
            classifications=classifications,
            confidence=confidence,
            evidence_lines=evidence_lines,
            reasoning=reasoning,
            manual_review_required=manual_review_required,
            manual_review_reason=manual_review_reason,
            processing_duration_ms=processing_duration_ms
        )
        
        return analysis

    def analyze_batch(
        self,
        emails: List[EmailInput],
        batch_size: int = 5
    ) -> List[EmailAnalysis]:
        if not emails:
            logger.warning("Empty email list provided")
            return []
        
        # Validate and limit batch size
        batch_size = min(max(batch_size, 1), settings.MAX_BATCH_SIZE)
        
        all_results = []
        to_process = []
        
        # Filter emails with empty bodies
        for email in emails:
            if not email.body or not email.body.strip():
                logger.warning(f"Email {email.email_id} has empty body, using fallback")
                all_results.append(self._fallback(email.email_id))
            else:
                to_process.append(email)
        
        print(f"Processing {len(to_process)} emails in batches of {batch_size}")
        logger.info(f"Processing {len(to_process)} emails in batches of {batch_size}")
        
        # Process in batches
        for batch_idx in range(0, len(to_process), batch_size):
            chunk = to_process[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1
            total_batches = (len(to_process) + batch_size - 1) // batch_size
            
            try:
                print(f"Processing batch {batch_num}/{total_batches} ({len(chunk)} emails)")
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(chunk)} emails)")
                batch_start = time.time()
                
                # Prepare batch prompt
                batch_analyses = self._process_batch(chunk)
                
                batch_duration_ms = int((time.time() - batch_start) * 1000)
                logger.info(f"Batch {batch_num} completed in {batch_duration_ms}ms")
                
                all_results.extend(batch_analyses)
                
            except LLMServiceError as e:
                logger.error(f"LLM service error for batch {batch_num}: {e}")
                # Add fallback analyses for entire batch
                for email in chunk:
                    all_results.append(self._fallback(email.email_id))
                    
            except Exception as e:
                print(f"Unexpected error processing batch {batch_num}: {e}")
                logger.error(f"Unexpected error processing batch {batch_num}: {e}")
                # Add fallback analyses for entire batch
                for email in chunk:
                    all_results.append(self._fallback(email.email_id))
        
        print(f"Completed analysis of {len(all_results)} emails")
        logger.info(f"Completed analysis of {len(all_results)} emails")
        return all_results

    def _process_response(self, response: Dict[str, Any], emails: List[EmailInput]) -> List[EmailAnalysis]:
        if not response:
                raise ValueError("Empty response from LLM")
            
        results = response.get("results", [])
            
        if not isinstance(results, list):
            raise ValueError(f"Expected list of results, got {type(results)}")
            
        if len(results) != len(emails):
            logger.warning(
                f"Result count mismatch: expected {len(emails)}, got {len(results)}"
            )
            
            # Process each result
        all_analyses = []
        for email, res_dict in zip(emails, results):
            try:
                analysis = self._process_email_result(email, res_dict)
                all_analyses.append(analysis)
                    
            except Exception as e:
                logger.error(f"Failed to process result for {email.email_id}: {e}")
                all_analyses.append(self._fallback(email.email_id))
            
        return all_analyses

    def _process_batch(self, emails: List[EmailInput]) -> List[EmailAnalysis]:
        # Build prompt with email data
        prompt_data = []
        for email in emails:
            # Sanitize content for prompt
            email_block = f"ID: {email.email_id}\nFrom: {email.from_address}\nSubject: {email.subject}\nBody: {email.body}"
            prompt_data.append(email_block)
    
        
        full_prompt = f"{EMAIL_AGENT_PROMPT}\n\n---EMAILS TO ANALYZE---\n\n" + "\n---\n".join(prompt_data)
        
        # Call LLM
        try:
            response = self.llm.call_with_json(full_prompt)
            return self._process_response(response, emails)
            
        except LLMServiceError as e:
            logger.warning("Primary prompt failed, retrying with safe prompt")
            safe_prompt = f"{FALLBACK_PROMPT}\n\n---EMAILS TO ANALYZE---\n\n" + "\n---\n".join(prompt_data)
            try:
                response = self.llm.call_with_json(safe_prompt)
                return self._process_response(response, emails)
            except Exception as e2:
                logger.error(f"Fallback prompt also failed: {e2}")
            raise
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            raise LLMServiceError(f"Batch processing error: {e}") from e


    def create_email_analysis_agent() -> EmailAnalysis:
        return EmailAnalysisAgent()


    def _fallback(self, email_id: str) -> EmailAnalysis:
        return EmailAnalysis(
            email_id=email_id,
            classifications=["unknown"],
            confidence=0.0,
            evidence_lines=[],
            reasoning="Analysis failed",
            manual_review_required=True,
            manual_review_reason="System error"
        )