import pandas as pd
from pathlib import Path
from typing import List, Optional, TypedDict
from langgraph.graph import StateGraph, START, END
from schemas.models import EmailInput, EmailAnalysis, EmailScoringResult, PipelineOutput
from agents.analysis_agent import AnalysisAgent
from agents.scoring_agent import ScoringAgent
from db import save_email, save_analysis, set_meta
from utils.logger import get_logger

log = get_logger("pipeline")

class PipelineState(TypedDict):
    file_path: str
    emails: List[EmailInput]
    analyses: List[EmailAnalysis]
    results: List[EmailScoringResult]
    output: Optional[PipelineOutput]

class EmailPipeline:
    def __init__(self):
        self.analysis_agent = AnalysisAgent()
        self.scoring_agent = ScoringAgent()
        self._graph = self._build_graph()

    def run(self, file_path: str) -> PipelineOutput:
        log.info("Starting analysis: %s", file_path)
        state = self._graph.invoke({"file_path": file_path, "emails": [], "analyses": [], "results": [], "output": None})
        return state["output"]

    def _build_graph(self):
        graph = StateGraph(PipelineState)
        graph.add_node("load", self._load)
        graph.add_node("analyze", self._analyze)
        graph.add_node("score", self._score)
        graph.add_node("finalize", self._finalize)
        graph.add_edge(START, "load")
        graph.add_edge("load", "analyze")
        graph.add_edge("analyze", "score")
        graph.add_edge("score", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def _load(self, state: PipelineState):
        emails = load_emails(state["file_path"])
        set_meta("total_emails", str(len(emails)))
        for e in emails:
            save_email(e.email_id, e.from_address, e.to_address, e.subject, e.body, str(e.date) if e.date else None)
        return {**state, "emails": emails}

    def _analyze(self, state: PipelineState):
        return {**state, "analyses": self.analysis_agent.analyze_batch(state["emails"])}

    def _score(self, state: PipelineState):
        return {**state, "results": self.scoring_agent.score_batch(state["emails"], state["analyses"])}

    def _finalize(self, state: PipelineState):
        res = state["results"]
        manual = [r for r in res if r.analysis.manual_review_required]
        summary = {"total": len(res), "critical": sum(1 for r in res if r.criticality_level == "critical"), "high": sum(1 for r in res if r.criticality_level == "high"), "medium": sum(1 for r in res if r.criticality_level == "medium"), "low": sum(1 for r in res if r.criticality_level == "low"), "manual": len(manual)}
        for r in res: save_analysis(r)
        return {**state, "output": PipelineOutput(batch_id="current", results=res, manual_review_emails=manual, summary=summary)}

def load_emails(path: str) -> List[EmailInput]:
    p = Path(path)
    df = pd.read_excel(p) if p.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(p)
    df.columns = df.columns.str.lower().str.strip()
    df = df.fillna("")
    emails = []
    for idx, row in df.iterrows():
        d = {k: str(v).strip() for k, v in row.to_dict().items()}
        if not d.get("email_id"): d["email_id"] = f"E{idx + 1}"
        # Robust column mapping
        f = d.get("from") or d.get("from_address") or d.get("sender")
        t = d.get("to") or d.get("to_address") or d.get("recipient")
        s = d.get("subject") or d.get("email_subject") or ""
        b = d.get("body") or d.get("email_body") or d.get("content") or ""
        
        if not f or not t: continue
        try: emails.append(EmailInput(email_id=d["email_id"], from_address=f, to_address=t, subject=s, body=b))
        except: pass
    if not emails: raise ValueError("No valid emails found")
    return emails
