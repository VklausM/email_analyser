from typing import List, Dict, Optional, Any
from langgraph.graph import StateGraph, START, END
from datetime import datetime
import logging

from schemas.email_models import (
    EmailInput, EmailAnalysis, EmailScoringResult, 
    PipelineInput, PipelineOutput
)
from agents.emails_agent import EmailAnalysisAgent
from agents.scoring_agent import ScoringAgent
from services.data_loader import get_data_loader_service
from services.embedding_service import get_sender_profile_service
from services.guardrail_service import get_guardrail_service
from config import settings

logger = logging.getLogger(__name__)


class PipelineState(dict):
    pass


class EmailAnalysisPipeline:
    def __init__(self):
        self.analysis_agent = EmailAnalysisAgent()
        self.scoring_agent = ScoringAgent()
        self.data_loader = get_data_loader_service()
        self.sender_profiles = get_sender_profile_service()
        self.guardrails = get_guardrail_service()
    
    def create_langgraph_workflow(self):
        workflow = StateGraph(PipelineState)
        workflow.add_node("load_emails", self._load_emails_node)
        workflow.add_node("validate_inputs", self._validate_inputs_node)
        workflow.add_node("analyze_emails", self._analyze_emails_node)
        workflow.add_node("score_emails", self._score_emails_node)
        workflow.add_node("filter_manual_review", self._filter_manual_review_node)
        workflow.add_node("format_output", self._format_output_node)
        workflow.add_edge(START, "load_emails")
        workflow.add_edge("load_emails", "validate_inputs")
        workflow.add_edge("validate_inputs", "analyze_emails")
        workflow.add_edge("analyze_emails", "score_emails")
        workflow.add_edge("score_emails", "filter_manual_review")
        workflow.add_edge("filter_manual_review", "format_output")
        workflow.add_edge("format_output", END)
        return workflow.compile()
    
    def process(self, file_path: str, custom_criticalities: Optional[Dict[str, float]] = None) -> PipelineOutput:
        try:
            logger.info(f"Starting email analysis pipeline for {file_path}")
            emails = self._load_emails(file_path)
            if not emails:
                logger.warning("No valid emails to process")
                return self._create_empty_output()
            logger.info(f"Loaded {len(emails)} emails")
            analyses = self._analyze_emails(emails)
            if custom_criticalities:
                settings.CRITICALITY_WEIGHTS.update(custom_criticalities)
            scored_results = self._score_emails(emails, analyses)
            manual_review = [r for r in scored_results if r.analysis.manual_review_required]
            self._update_sender_profiles(emails, analyses, scored_results)
            output = self._format_output(scored_results, manual_review)
            logger.info(f"Pipeline complete: {len(scored_results)} emails analyzed, {len(manual_review)} flagged for review")
            return output
        except Exception as e:
            logger.error(f"Pipeline error: {str(e)}", exc_info=True)
            raise
    
    def _load_emails(self, file_path: str) -> List[EmailInput]:
        try:
            if file_path.endswith(".xlsx") or file_path.endswith(".xls"):
                return self.data_loader.load_emails_from_excel(file_path, validate=True)
            elif file_path.endswith(".csv"):
                return self.data_loader.load_emails_from_csv(file_path, validate=True)
            else:
                raise ValueError(f"Unsupported file format: {file_path}")
        except Exception as e:
            logger.error(f"Failed to load emails: {str(e)}")
            raise
    
    def _analyze_emails(self, emails: List[EmailInput]) -> List[EmailAnalysis]:
        analyses = []
        for idx, email in enumerate(emails, 1):
            logger.info(f"Analyzing email {idx}/{len(emails)}: {email.email_id}")
            analysis = self.analysis_agent.analyze(email)
            analyses.append(analysis)
        return analyses
    
    def _score_emails(self, emails: List[EmailInput], analyses: List[EmailAnalysis]) -> List[EmailScoringResult]:
        return self.scoring_agent.score_batch(emails, analyses)
    
    def _update_sender_profiles(self, emails: List[EmailInput], analyses: List[EmailAnalysis], scored_results: List[EmailScoringResult]) -> None:
        for email, analysis, score in zip(emails, analyses, scored_results):
            self.sender_profiles.update_profile(
                sender_email=email.from_address,
                email_body=email.body,
                tone=analysis.tone,
                classifications=analysis.classifications,
                risk_score=score.risk_score
            )
    
    def _format_output(self, scored_results: List[EmailScoringResult], manual_review: List[EmailScoringResult]) -> PipelineOutput:
        summary = {
            "total_emails": len(scored_results),
            "manual_review_count": len(manual_review),
            "average_risk_score": sum(r.risk_score for r in scored_results) / len(scored_results) if scored_results else 0,
            "critical_count": sum(1 for r in scored_results if r.criticality_level == "critical"),
            "high_count": sum(1 for r in scored_results if r.criticality_level == "high"),
            "medium_count": sum(1 for r in scored_results if r.criticality_level == "medium"),
            "low_count": sum(1 for r in scored_results if r.criticality_level == "low"),
        }
        return PipelineOutput(
            results=scored_results,
            manual_review_emails=manual_review,
            summary=summary,
            processing_timestamp=datetime.now()
        )
    
    def _create_empty_output(self) -> PipelineOutput:
        return PipelineOutput(
            results=[],
            manual_review_emails=[],
            summary={"total_emails": 0, "error": True},
            processing_timestamp=datetime.now()
        )
    
    def _load_emails_node(self, state: PipelineState) -> PipelineState:
        file_path = state.get("file_path")
        state["emails"] = self._load_emails(file_path)
        return state
    
    def _validate_inputs_node(self, state: PipelineState) -> PipelineState:
        return state
    
    def _analyze_emails_node(self, state: PipelineState) -> PipelineState:
        emails = state.get("emails", [])
        state["analyses"] = self._analyze_emails(emails)
        return state
    
    def _score_emails_node(self, state: PipelineState) -> PipelineState:
        emails = state.get("emails", [])
        analyses = state.get("analyses", [])
        state["scored_results"] = self._score_emails(emails, analyses)
        return state
    
    def _filter_manual_review_node(self, state: PipelineState) -> PipelineState:
        scored_results = state.get("scored_results", [])
        state["manual_review"] = [r for r in scored_results if r.analysis.manual_review_required]
        return state
    
    def _format_output_node(self, state: PipelineState) -> PipelineState:
        emails = state.get("emails", [])
        analyses = state.get("analyses", [])
        scored_results = state.get("scored_results", [])
        manual_review = state.get("manual_review", [])
        self._update_sender_profiles(emails, analyses, scored_results)
        state["output"] = self._format_output(scored_results, manual_review)
        return state


def create_pipeline() -> EmailAnalysisPipeline:
    return EmailAnalysisPipeline()
