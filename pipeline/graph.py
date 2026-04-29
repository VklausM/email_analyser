import uuid
import pandas as pd
from pathlib import Path
from typing import List, Optional, TypedDict
from datetime import datetime

from langgraph.graph import StateGraph, START, END

from schemas.models import EmailInput, EmailAnalysis, EmailScoringResult, PipelineOutput
from agents.analysis_agent import AnalysisAgent
from agents.scoring_agent import ScoringAgent
from db import save_batch, save_email, save_analysis
from utils.logger import get_logger

log = get_logger("pipeline")


class PipelineState(TypedDict):
    batch_id: str
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
        batch_id = str(uuid.uuid4())[:8]
        log.info("Starting batch %s — %s", batch_id, file_path)
        state = self._graph.invoke({
            "batch_id": batch_id,
            "file_path": file_path,
            "emails": [],
            "analyses": [],
            "results": [],
            "output": None,
        })
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

    def _load(self, state: PipelineState) -> PipelineState:
        emails = load_emails(state["file_path"])
        batch_id = state["batch_id"]
        filename = Path(state["file_path"]).name

        # Create batch record first to satisfy foreign key constraints
        save_batch(batch_id, filename, {"total": len(emails)})

        for e in emails:
            save_email(
                batch_id=batch_id,
                email_id=e.email_id,
                from_addr=e.from_address,
                to_addr=e.to_address,
                subject=e.subject,
                body=e.body,
                date=str(e.date) if e.date else None,
            )

        log.info("Loaded %d emails", len(emails))
        return {**state, "emails": emails}

    def _analyze(self, state: PipelineState) -> PipelineState:
        analyses = self.analysis_agent.analyze_batch(state["emails"])
        return {**state, "analyses": analyses}

    def _score(self, state: PipelineState) -> PipelineState:
        results = self.scoring_agent.score_batch(state["emails"], state["analyses"])
        return {**state, "results": results}

    def _finalize(self, state: PipelineState) -> PipelineState:
        results = state["results"]
        batch_id = state["batch_id"]
        filename = Path(state["file_path"]).name

        manual = [r for r in results if r.analysis.manual_review_required]

        summary = {
            "total": len(results),
            "critical": sum(1 for r in results if r.criticality_level == "critical"),
            "high": sum(1 for r in results if r.criticality_level == "high"),
            "medium": sum(1 for r in results if r.criticality_level == "medium"),
            "low": sum(1 for r in results if r.criticality_level == "low"),
            "manual": len(manual),
        }

        save_batch(batch_id, filename, summary)
        for r in results:
            save_analysis(batch_id, r)

        log.info(
            "Batch %s done — total=%d, critical=%d, manual=%d",
            batch_id, summary["total"], summary["critical"], summary["manual"]
        )

        output = PipelineOutput(
            batch_id=batch_id,
            results=results,
            manual_review_emails=manual,
            summary=summary,
            processing_timestamp=datetime.utcnow(),
        )
        return {**state, "output": output}


def load_emails(path: str) -> List[EmailInput]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if file_path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    elif file_path.suffix.lower() == ".csv":
        df = pd.read_csv(file_path)
    else:
        raise ValueError(f"Unsupported format: {file_path.suffix}")

    df.columns = df.columns.str.lower().str.strip()
    df = df.fillna("")

    emails = []
    for idx, row in df.iterrows():
        data = {k: str(v).strip() for k, v in row.to_dict().items()}

        if not data.get("email_id"):
            data["email_id"] = f"E{idx + 1}"

        if "from" not in data and "from_address" in data:
            data["from"] = data["from_address"]
        if "to" not in data and "to_address" in data:
            data["to"] = data["to_address"]

        if not data.get("from") or not data.get("to"):
            log.warning("Row %d: missing from/to — skipping", idx + 1)
            continue

        try:
            emails.append(EmailInput(**data))
        except Exception as e:
            log.warning("Row %d invalid: %s", idx + 1, e)

    if not emails:
        raise ValueError("No valid emails found in file")

    return emails
