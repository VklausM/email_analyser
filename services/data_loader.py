import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from schemas.email_models import EmailInput, PipelineOutput
from config import settings

logger = logging.getLogger(__name__)


class DataLoaderError(Exception):
    """Exception for data loading failures."""
    pass


class DataValidationError(Exception):
    """Exception for data validation failures."""
    pass


class DataLoaderService:
    REQUIRED_COLUMNS = ["email_id", "from", "to", "subject", "body"]
    OPTIONAL_COLUMNS = ["date", "cc", "bcc"]

    def __init__(self):
        """Initialize data loader service."""
        pass

    @staticmethod
    def _validate_file_path(path: str) -> Path:
        if not path or not isinstance(path, str):
            raise DataLoaderError("File path must be a non-empty string")
        
        file_path = Path(path)
        
        if not file_path.exists():
            raise DataLoaderError(f"File not found: {path}")
        
        if not file_path.is_file():
            raise DataLoaderError(f"Path is not a file: {path}")
        
        # Check file extension
        valid_extensions = {'.xlsx', '.xls', '.csv'}
        if file_path.suffix.lower() not in valid_extensions:
            raise DataLoaderError(
                f"Unsupported file format: {file_path.suffix}. "
                f"Supported: {', '.join(valid_extensions)}"
            )
        
        return file_path

    @staticmethod
    def _read_excel_file(file_path: Path) -> pd.DataFrame:
        try:
            df = pd.read_excel(file_path)
            return df
        except Exception as e:
            logger.error(f"Failed to read Excel file: {e}")
            raise DataLoaderError(f"Failed to read Excel file: {e}") from e

    
    def _validate_dataframe(self, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            raise DataValidationError("Input file is empty")
        
        # Normalize column names
        df.columns = df.columns.str.lower().str.strip()
        
        # Check for at least one required column
        columns_found = set(df.columns) & set(self.REQUIRED_COLUMNS)
        if not columns_found:
            raise DataValidationError(
                f"No required columns found. Expected at least one of: "
                f"{', '.join(self.REQUIRED_COLUMNS)}"
            )
        
        if len(df) == 0:
            raise DataValidationError("DataFrame has no data rows")

    def load_emails_from_excel(self, path: str) -> List[EmailInput]:

        # Validate file path
        try:
            file_path = self._validate_file_path(path)
        except DataLoaderError:
            raise
        
        # Read file
        logger.info(f"Loading emails from {file_path}")
        
        try:
            df = self._read_excel_file(file_path)
        except DataLoaderError:
            raise
        
        # Validate DataFrame
        try:
            self._validate_dataframe(df)
        except DataValidationError:
            raise
        
        # Fill missing values
        df = df.fillna("")
        
        # Normalize column names
        df.columns = df.columns.str.lower().str.strip()
        
        logger.info(f"Loaded {len(df)} rows from {file_path.name}")
        
        emails = []
        skipped = 0
        
        # Process each row
        for idx, row in df.iterrows():
            try:
                # Normalize row data
                data = {k.lower().strip(): str(v).strip() for k, v in row.to_dict().items()}
                
                # Generate email_id if missing
                if not data.get("email_id") or data.get("email_id") == "":
                    data["email_id"] = f"E_{idx+1}"
                
                # Handle 'from' and 'to' aliases
                if not data.get("from"):
                    data["from"] = data.get("from_address", "")
                if not data.get("to"):
                    data["to"] = data.get("to_address", "")
                
                # Ensure required fields exist
                if not data.get("from"):
                    logger.warning(f"Row {idx+1}: Missing 'from' address, skipping")
                    skipped += 1
                    continue
                
                if not data.get("to"):
                    logger.warning(f"Row {idx+1}: Missing 'to' address, skipping")
                    skipped += 1
                    continue
                
                # Create and validate EmailInput
                email = EmailInput(**data)
                emails.append(email)
                
            except ValueError as e:
                logger.warning(f"Row {idx+1}: Validation error - {e}")
                skipped += 1
            except Exception as e:
                logger.warning(f"Row {idx+1}: Error processing row - {e}")
                skipped += 1
        
        if not emails:
            raise DataValidationError(
                f"No valid emails loaded from {path}"
            )
        
        logger.info(
            f"Successfully loaded {len(emails)} emails "
            f"(skipped {skipped} invalid rows)"
        )
        
        return emails

    def save_results_to_excel(self, output: PipelineOutput, path: str) -> None:
        if not output or not output.results:
            raise DataLoaderError("No results to save")
        
        try:
            output_path = Path(path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
                workbook = writer.book
                
                # Define formats
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#4472C4',
                    'font_color': 'white',
                    'border': 1
                })
                
                critical_format = workbook.add_format({
                    'bg_color': '#FF6B6B',
                    'font_color': 'white',
                    'border': 1
                })
                
                high_format = workbook.add_format({
                    'bg_color': '#FFA500',
                    'font_color': 'white',
                    'border': 1
                })
                
                medium_format = workbook.add_format({
                    'bg_color': '#FFD700',
                    'border': 1
                })
                
                low_format = workbook.add_format({
                    'bg_color': '#90EE90',
                    'border': 1
                })
                
                normal_format = workbook.add_format({'border': 1})
                
                # Sheet 1: Ranked Results
                self._write_ranked_results(
                    writer, output, header_format,
                    critical_format, high_format, medium_format, low_format, normal_format
                )
                
                # Sheet 2: Evidence Lines
                self._write_evidence_lines(writer, output, header_format, normal_format)
                
                # Sheet 3: Scoring Factors
                self._write_scoring_factors(writer, output, header_format, normal_format)
                
                # Sheet 4: Manual Review
                self._write_manual_review(writer, output, header_format, normal_format)
                
                # Sheet 5: Summary Statistics
                self._write_summary(writer, output, header_format, normal_format)
            
            logger.info(f"Results saved to {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            raise DataLoaderError(f"Failed to save results: {e}") from e

    @staticmethod
    def _write_ranked_results(writer, output, header_fmt, crit_fmt, high_fmt, med_fmt, low_fmt, norm_fmt):
        data = []
        for r in output.results:
            data.append({
                "Rank": r.rank,
                "Email ID": r.email_id,
                "Classifications": ", ".join(r.analysis.classifications),
                "Risk Score": round(r.risk_score, 2),
                "Level": r.criticality_level,
                "Confidence": round(r.analysis.confidence, 3),
                "Evidence Count": len(r.analysis.evidence_lines),
                "Manual Review": "YES" if r.analysis.manual_review_required else "NO"
            })
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name="Ranked Results", index=False)
        
        worksheet = writer.sheets["Ranked Results"]
        for col_num, col_name in enumerate(df.columns):
            worksheet.write(0, col_num, col_name, header_fmt)
        
        for row_num, r in enumerate(output.results, 1):
            level = r.criticality_level
            fmt = norm_fmt
            if level == "critical":
                fmt = crit_fmt
            elif level == "high":
                fmt = high_fmt
            elif level == "medium":
                fmt = med_fmt
            else:
                fmt = low_fmt
            
            worksheet.write(row_num, 4, level, fmt)

    @staticmethod
    def _write_evidence_lines(writer, output, header_fmt, norm_fmt):
        data = []
        for r in output.results:
            for line in r.analysis.evidence_lines:
                data.append({
                    "Email ID": r.email_id,
                    "Line Number": line.line_number,
                    "Risk Level": line.risk_level,
                    "Evidence Text": line.text[:500],
                    "Reason": line.reason,
                    "Confidence": round(line.confidence, 3)
                })
        
        if not data:
            data = [{"Email ID": "N/A", "Line Number": 0, "Risk Level": "N/A",
                     "Evidence Text": "No evidence", "Reason": "", "Confidence": 0}]
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name="Evidence Lines", index=False)
        
        worksheet = writer.sheets["Evidence Lines"]
        for col_num, col_name in enumerate(df.columns):
            worksheet.write(0, col_num, col_name, header_fmt)

    @staticmethod
    def _write_scoring_factors(writer, output, header_fmt, norm_fmt):
        data = []
        for r in output.results:
            f = r.scoring_factors
            data.append({
                "Email ID": r.email_id,
                "Confidence Score": round(f.confidence_score, 3),
                "Criticality Score": round(f.criticality_score, 3),
                "Evidence Contribution": round(f.evidence_contribution, 2),
                "Baseline Floor": round(f.baseline_floor, 3),
                "Final Risk Score": round(r.risk_score, 2)
            })
        
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name="Scoring Factors", index=False)
        
        worksheet = writer.sheets["Scoring Factors"]
        for col_num, col_name in enumerate(df.columns):
            worksheet.write(0, col_num, col_name, header_fmt)

    @staticmethod
    def _write_manual_review(writer, output, header_fmt, norm_fmt):
        if not output.manual_review_emails:
            df = pd.DataFrame([{"Message": "No emails require manual review"}])
        else:
            data = []
            for r in output.manual_review_emails:
                data.append({
                    "Rank": r.rank,
                    "Email ID": r.email_id,
                    "Risk Score": round(r.risk_score, 2),
                    "Level": r.criticality_level,
                    "Review Reason": r.analysis.manual_review_reason or "Requires review",
                    "Classifications": ", ".join(r.analysis.classifications)
                })
            df = pd.DataFrame(data)
        
        df.to_excel(writer, sheet_name="Manual Review", index=False)
        
        worksheet = writer.sheets["Manual Review"]
        for col_num, col_name in enumerate(df.columns):
            worksheet.write(0, col_num, col_name, header_fmt)

    @staticmethod
    def _write_summary(writer, output, header_fmt, norm_fmt):
        summary_data = {
            "Metric": [
                "Total Emails",
                "Critical Risk",
                "High Risk",
                "Medium Risk",
                "Low Risk",
                "Manual Review Required",
                "Processing Timestamp",
                "Total Processing Time (ms)"
            ],
            "Value": [
                output.summary.get("total", 0),
                output.summary.get("critical", 0),
                output.summary.get("high", 0),
                output.summary.get("medium", 0),
                output.summary.get("low", 0),
                output.summary.get("manual", 0),
                str(output.processing_timestamp) if output.processing_timestamp else "N/A",
                output.total_processing_time_ms
            ]
        }
        
        df = pd.DataFrame(summary_data)
        df.to_excel(writer, sheet_name="Summary", index=False)
        
        worksheet = writer.sheets["Summary"]
        for col_num, col_name in enumerate(df.columns):
            worksheet.write(0, col_num, col_name, header_fmt)


def get_data_loader_service() -> DataLoaderService:
    return DataLoaderService()


_service = None


def get_data_loader_service():
    global _service
    if _service is None:
        _service = DataLoaderService()
    return _service