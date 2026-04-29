import json

try:
    with open("scoring_matrix.json") as f:
        SCORING_MATRIX = json.load(f)
    CATEGORIES = ", ".join(SCORING_MATRIX.keys())
except:
    CATEGORIES = "phishing, fraud, data_leakage, policy_violation, normal"

ANALYSIS_PROMPT = f"""As a Compliance Auditor, detect risks in these emails.

Detection Categories:
- {CATEGORIES}

Severity Scale:
- CRITICAL: Immediate security threat or criminal activity.
- HIGH: Significant policy breach.
- MEDIUM: Suspicious activity.
- LOW: Minor anomaly.

JSON Output Template:
{{
  "results": [
    {{
      "email_id": "...",
      "classifications": ["fraud"], 
      "tags": ["urgent"],
      "confidence": 0.95,
      "reasoning": "...",
      "evidence_lines": [{{ "line_number": 1, "text": "...", "risk_level": "low|medium|high|critical", "reason": "..." }}],
      "manual_review_required": false
    }}
  ]
}}

Emails to Audit:
"""

FALLBACK_PROMPT = "Audit these communications for security risks and return JSON 'results'."
