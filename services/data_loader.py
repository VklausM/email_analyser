import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
from rich.progress import Progress, BarColumn, SpinnerColumn, TextColumn, TimeElapsedColumn
from schemas.email_models import EmailInput, EmailScoringResult, PipelineOutput

logger = logging.getLogger(__name__)

class DataLoaderService:
    def __init__(self):
        pass

    def load_emails_from_excel(self, path: str) -> List[EmailInput]:
        df = pd.read_excel(path)
        df.columns = df.columns.str.lower().str.strip()
        df = df.fillna("")
        logger.info("Loading %s email rows from %s", len(df), path)

        emails = []
        print(f"Loading {len(df)} emails from {path}...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            transient=False,
        ) as progress:
            task = progress.add_task("Processing emails", total=len(df))
            for idx, row in df.iterrows():
                data = {k.lower().strip(): v for k, v in row.to_dict().items()}
                if not data.get("email_id"):
                    data["email_id"] = f"E_{idx+1}"
                data["subject"] = data.get("subject", "")
                data["body"] = data.get("body", "")
                if not data.get("from") and data.get("from_address"):
                    data["from"] = data["from_address"]
                if not data.get("to") and data.get("to_address"):
                    data["to"] = data["to_address"]

                try:
                    email = EmailInput(**data)
                    emails.append(email)
                except Exception as e:
                    logger.error("Skipping row %s during load: %s", idx, e)
                finally:
                    progress.advance(task)
        return emails

    def save_results_to_excel(self, output: PipelineOutput, path: str):
        with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
            # Sheet 1: Ranked Results
            main_data = []
            for r in output.results:
                main_data.append({
                    "Rank": r.rank,
                    "Email ID": r.email_id,
                    "Classifications": ", ".join(r.analysis.classifications),
                    "Risk Score": round(r.risk_score, 2),
                    "Level": r.criticality_level,
                    "Manual": "YES" if r.analysis.manual_review_required else "NO"
                })
            pd.DataFrame(main_data).to_excel(writer, sheet_name="Ranked Results", index=False)
            
            # Sheet 2: Evidence Lines
            evidence_data = []
            for r in output.results:
                for line in r.analysis.evidence_lines:
                    evidence_data.append({
                        "Email ID": r.email_id,
                        "Line": line.line_number,
                        "Level": line.risk_level,
                        "Text": line.text,
                        "Reason": line.reason
                    })
            pd.DataFrame(evidence_data).to_excel(writer, sheet_name="Evidence Lines", index=False)
            
            # Sheet 3: Scoring Factors
            factors_data = []
            for r in output.results:
                f = r.scoring_factors
                factors_data.append({
                    "Email ID": r.email_id,
                    "Confidence": f.confidence_score,
                    "Criticality": f.criticality_score,
                    "Floor": f.baseline_floor,
                    "Final": round(r.risk_score, 2)
                })
            pd.DataFrame(factors_data).to_excel(writer, sheet_name="Scoring Factors", index=False)
            
            # Sheet 4: Manual Review
            if output.manual_review_emails:
                manual_data = []
                for r in output.manual_review_emails:
                    manual_data.append({
                        "Email ID": r.email_id,
                        "Reason": r.analysis.manual_review_reason,
                        "Score": round(r.risk_score, 2)
                    })
                pd.DataFrame(manual_data).to_excel(writer, sheet_name="Manual Review", index=False)

_service = None

def get_data_loader_service():
    global _service
    if _service is None:
        _service = DataLoaderService()
    return _service
