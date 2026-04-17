# Email Analysis System

BFSI email analysis and risk scoring system using OpenAI LLM and embedding models.

## Installation

```Bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Setup

Create \.env\ file with API keys:
```
OPENAI_API_KEY=your_api_key
```

## Usage

```Bash
python main.py --input emails.xlsx --output results.xlsx
```

Load emails from Excel/CSV and get:
- Classification into 11 BFSI risk types
- Risk scores (0-100)
- Manual review flags
- Evidence and reasoning

## Classification Types

- **Tier 1**: money_laundering, fraud
- **Tier 2**: insider_trading
- **Tier 3**: bribery
- **Tier 4**: phishing
- **Tier 5**: malicious, scam
- **Tier 6**: quid_pro_quo
- **Tier 7**: market_manipulation
- **Tier 8**: secrecy_breach
- **Tier 9**: none

## Configuration

Edit \config.py\ to adjust:
- Model selection (MODEL_NAME)
- Risk thresholds (RISK_THRESHOLD)
- Criticality weights (CRITICALITY_WEIGHTS)
- Tone weights (TONE_WEIGHTS)

## Output

Results saved as Excel with sheets:
- Analysis Results: Classification, score, tone, confidence
- Manual Review: High-risk emails flagged for review
- Evidence Lines: Supporting evidence and reasons
- Scoring Factors: Score component breakdown

## Architecture

- **agents/**: Email analysis and scoring agents
- **services/**: LLM, embeddings, data loading, validation
- **schemas/**: Pydantic models for data validation
- **pipeline/**: LangGraph orchestration workflow
