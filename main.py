import argparse
import logging
import sys
from pathlib import Path
from pipeline.email_analysis_pipeline import create_pipeline
from services.data_loader import get_data_loader_service
from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", "-f", required=True)
    parser.add_argument("--output", "-o", default="email_analysis_results.xlsx")
    args = parser.parse_args()

    try:
        logger.info(f"Starting BFSI Analysis: {args.file}")
        
        pipeline = create_pipeline()
        output = pipeline.process(args.file)

        logger.info(f"Saving to {args.output}")
        get_data_loader_service().save_results_to_excel(output, args.output)

        print("\n" + "="*30)
        print(f"Total Emails: {output.summary.get('total')}")
        print(f"Critical Risks: {output.summary.get('critical')}")
        print(f"Manual Reviews: {output.summary.get('manual')}")
        print("="*30)
        
    except Exception as e:
        logger.error(f"Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
