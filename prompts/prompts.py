import json

try:
    with open("scoring_matrix.json") as f:
        SCORING_MATRIX = json.load(f)
    CATEGORIES = ", ".join(SCORING_MATRIX.keys())
except:
    CATEGORIES = "malicious, money_laundering, insider_trading, secrecy_breach, bribery, fraud, phishing, scam, market_manipulation, quid_pro_quo, compliance, financial risk, none"

ANALYSIS_PROMPT = f"""Analyze these emails for BFSI compliance risks.

Categories (Use ONLY these):
- {CATEGORIES}

Scoring Guidelines:
- CRITICAL: Direct evidence of crime or severe data breach.
- HIGH: Strong indicators of the selected category.
- MEDIUM: Suspicious behavior needing verification.
- LOW: Minor anomaly or context-dependent risk.

Output Example JSON:
{{
  "results": [
    {{
      "email_id": "...",
      "classifications": ["fraud", "phishing"], 
      "tags": ["urgent", "PII", "financial"],
      "confidence": 0.95,
      "reasoning": "...",
      "evidence_lines": [{{ "line_number": 1, "text": "...", "risk_level": "low|medium|high|critical", "reason": "..." }}],
      "manual_review_required": false
    }}
  ]
}}

Emails:
"""

FALLBACK_PROMPT = "Categorize BFSI risks using JSON 'results'."
