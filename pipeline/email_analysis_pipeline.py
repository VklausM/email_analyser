from typing import List, Optional, TypedDict
from langgraph.graph import StateGraph, START, END
from datetime import datetime
from schemas.email_models import EmailInput, EmailAnalysis, EmailScoringResult, PipelineOutput
from agents.emails_agent import EmailAnalysisAgent
from agents.scoring_agent import ScoringAgent
from services.data_loader import get_data_loader_service

class PipelineState(TypedDict):
    file_path: str
    emails: List[EmailInput]
    analyses: List[EmailAnalysis]
    scored_results: List[EmailScoringResult]
    manual_review: List[EmailScoringResult]
    output: Optional[PipelineOutput]

class EmailAnalysisPipeline:
    def __init__(self):
        self.analysis_agent = EmailAnalysisAgent()
        self.scoring_agent = ScoringAgent()
        self.data_loader = get_data_loader_service()

    def create_workflow(self):
        graph = StateGraph(PipelineState)
        graph.add_node("load", self._load_node)
        graph.add_node("analyze", self._analyze_node)
        graph.add_node("score", self._score_node)
        graph.add_node("finalize", self._finalize_node)
        
        graph.add_edge(START, "load")
        graph.add_edge("load", "analyze")
        graph.add_edge("analyze", "score")
        graph.add_edge("score", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def process(self, file_path: str) -> PipelineOutput:
        workflow = self.create_workflow()
        state = workflow.invoke({"file_path": file_path})
        return state["output"]

    def _load_node(self, state: PipelineState):
        emails = self.data_loader.load_emails_from_excel(state["file_path"])
        return {**state, "emails": emails}

    def _analyze_node(self, state: PipelineState):
        # Using batch analysis to reduce calls
        analyses = self.analysis_agent.analyze_batch(state["emails"])
        return {**state, "analyses": analyses}

    def _score_node(self, state: PipelineState):
        scored = self.scoring_agent.score_batch(state["emails"], state["analyses"])
        return {**state, "scored_results": scored}

    def _finalize_node(self, state: PipelineState):
        scored = state["scored_results"]
        manual = [r for r in scored if r.analysis.manual_review_required]
        
            
        summary = {
            "total": len(scored),
            "critical": len([r for r in scored if r.criticality_level == "critical"]),
            "manual": len(manual)
        }
        
        output = PipelineOutput(
            results=scored,
            manual_review_emails=manual,
            summary=summary,
            processing_timestamp=datetime.now()
        )
        return {**state, "output": output}

def create_pipeline():
    return EmailAnalysisPipeline()
