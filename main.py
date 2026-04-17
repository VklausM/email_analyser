#!/usr/bin/env python3
import argparse
import json
import logging
from pathlib import Path
from typing import Optional, Dict
import sys

from pipeline.email_analysis_pipeline import create_pipeline
from services.data_loader import get_data_loader_service
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("email_analysis.log")
    ]
)
logger = logging.getLogger(__name__)

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="BFSI Email Analysis System",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--file",
        "-f",
        type=str,
        required=True,
        help="Path to input email file (Excel or CSV)"
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="email_analysis_results.xlsx",
        help="Path to output Excel file (default: email_analysis_results.xlsx)"
    )

    parser.add_argument(
        "--custom-criticalities",
        "-c",
        type=str,
        default=None,
        help="JSON string with custom criticality weights for classifications"
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    return parser.parse_args()

def validate_input_file(file_path: str) -> Path:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    if not path.suffix.lower() in [".xlsx", ".xls", ".csv"]:
        raise ValueError(f"Unsupported file format: {path.suffix}. Use Excel or CSV.")

    return path

def parse_custom_criticalities(criticalities_json: Optional[str]) -> Optional[Dict[str, float]]:
    if not criticalities_json:
        return None

    try:
        criticalities = json.loads(criticalities_json)

        for key, value in criticalities.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f"Criticality value must be numeric: {key}={value}")
            if not 0 <= value <= 1:
                raise ValueError(f"Criticality value must be between 0 and 1: {key}={value}")

        return criticalities

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON for custom criticalities: {str(e)}")

def main():
    try:
        args = parse_arguments()

        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)

        logger.info("="*80)
        logger.info("BFSI Email Analysis System Started")
        logger.info(f"Configuration: {settings.MODEL_NAME}, Confidence Threshold: {settings.CONFIDENCE_THRESHOLD}")
        logger.info("="*80)

        input_file = validate_input_file(args.file)
        logger.info(f"Input file: {input_file}")

        custom_criticalities = None
        if args.custom_criticalities:
            custom_criticalities = parse_custom_criticalities(args.custom_criticalities)
            logger.info(f"Custom criticalities: {custom_criticalities}")

        logger.info("Creating analysis pipeline...")
        pipeline = create_pipeline()

        logger.info("Processing emails...")
        output = pipeline.process(
            file_path=str(input_file),
            custom_criticalities=custom_criticalities
        )

        logger.info(f"Saving results to {args.output}")
        data_loader = get_data_loader_service()
        data_loader.save_results_to_excel(
            output=output,
            file_path=args.output,
            include_evidence=True,
            include_factors=True
        )

        logger.info("="*80)
        logger.info("Analysis Complete - Summary")
        logger.info("="*80)
        logger.info(f"Total emails processed: {output.summary.get('total_emails', 0)}")
        logger.info(f"Critical risk emails: {output.summary.get('critical_count', 0)}")
        logger.info(f"High risk emails: {output.summary.get('high_count', 0)}")
        logger.info(f"Medium risk emails: {output.summary.get('medium_count', 0)}")
        logger.info(f"Low risk emails: {output.summary.get('low_count', 0)}")
        logger.info(f"Manual review required: {output.summary.get('manual_review_count', 0)}")
        logger.info(f"Average risk score: {output.summary.get('average_risk_score', 0):.2f}")
        logger.info("="*80)
        logger.info(f"Results saved to: {args.output}")
        logger.info("")

        return 0

    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        return 1

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        print(f"\nERROR: {str(e)}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
