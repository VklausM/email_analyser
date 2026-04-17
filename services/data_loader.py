import pandas as pd
from typing import List, Dict, Any, Optional
from pathlib import Path
from schemas.email_models import EmailInput, EmailScoringResult, PipelineOutput
from services.guardrail_service import get_guardrail_service
import logging

logger = logging.getLogger(__name__)


class DataLoaderService:
    REQUIRED_COLUMNS = ["from", "to", "subject", "body"]
    OPTIONAL_COLUMNS = ["date", "cc", "bcc", "email_id"]
    
    def __init__(self):
        self.guardrails = get_guardrail_service()
    
    def load_emails_from_excel(self, file_path: str, validate: bool = True, skip_errors: bool = False) -> List[EmailInput]:
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            df = pd.read_excel(file_path)
            missing = set(self.REQUIRED_COLUMNS) - set(df.columns)
            if missing:
                raise ValueError(f"Missing required columns: {missing}")
            df.columns = df.columns.str.lower().str.strip()
            emails = []
            for idx, row in df.iterrows():
                try:
                    email_data = row.to_dict()
                    if "email_id" not in email_data or pd.isna(email_data["email_id"]):
                        email_data["email_id"] = f"email_{idx}"
                    email_data = {k: v for k, v in email_data.items() if pd.notna(v)}
                    if validate:
                        email = self.guardrails.validate_email_input(email_data, strict=not skip_errors)
                        if email is not None:
                            emails.append(email)
                    else:
                        emails.append(EmailInput(**email_data))
                except Exception as e:
                    if skip_errors:
                        logger.warning(f"Skipping invalid email at row {idx}: {e}")
                        continue
                    else:
                        raise ValueError(f"Error processing row {idx}: {e}")
            logger.info(f"Loaded {len(emails)} valid emails from {file_path}")
            return emails
        except Exception as e:
            logger.error(f"Failed to load emails: {str(e)}")
            raise
    
    def save_results_to_excel(self, output: PipelineOutput, file_path: str, include_evidence: bool = True, include_factors: bool = True) -> None:
        try:
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                results_data = []
                for result in output.results:
                    row = {"Email ID": result.email_id, "From": result.analysis.email_id, "Subject": "", "Classifications": ",".join(result.analysis.classifications), "Risk Score": result.risk_score}
                    results_data.append(row)
                results_df = pd.DataFrame(results_data)
                results_df.to_excel(writer, sheet_name="Analysis Results", index=False)
            logger.info(f"Results saved to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save results: {str(e)}")
            raise
    
    def load_emails_from_csv(self, file_path: str, validate: bool = True, skip_errors: bool = False) -> List[EmailInput]:
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            df = pd.read_csv(file_path)
            missing = set(self.REQUIRED_COLUMNS) - set(df.columns)
            if missing:
                raise ValueError(f"Missing required columns: {missing}")
            df.columns = df.columns.str.lower().str.strip()
            emails = []
            for idx, row in df.iterrows():
                try:
                    email_data = row.to_dict()
                    if "email_id" not in email_data or pd.isna(email_data["email_id"]):
                        email_data["email_id"] = f"email_{idx}"
                    email_data = {k: v for k, v in email_data.items() if pd.notna(v)}
                    if validate:
                        email = self.guardrails.validate_email_input(email_data, strict=not skip_errors)
                        if email is not None:
                            emails.append(email)
                    else:
                        emails.append(EmailInput(**email_data))
                except Exception as e:
                    if skip_errors:
                        logger.warning(f"Skipping invalid email at row {idx}: {e}")
                        continue
                    else:
                        raise
            return emails
        except Exception as e:
            logger.error(f"Failed to load emails from CSV: {str(e)}")
            raise


_data_loader: Optional[DataLoaderService] = None


def get_data_loader_service() -> DataLoaderService:
    global _data_loader
    if _data_loader is None:
        _data_loader = DataLoaderService()
    return _data_loader


def load_emails(file_path):
    df = pd.read_excel(file_path)
    return df.to_dict(orient="records")
