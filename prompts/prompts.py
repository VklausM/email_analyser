ANALYSIS_PROMPT = """You are a BFSI compliance analyst. Analyze each email for financial crime, regulatory risk, and compliance issues.

Return ONLY valid JSON — no markdown, no explanation, nothing else.

Required format:
{
  "results": [
    {
      "email_id": "string",
      "classifications": ["string"],
      "tags": ["string"],
      "confidence": 0.0,
      "evidence_lines": [
        {
          "line_number": 1,
          "text": "exact text from email",
          "risk_level": "low|medium|high|critical",
          "reason": "why this is risky",
          "confidence": 0.0
        }
      ],
      "reasoning": "string",
      "manual_review_required": false,
      "manual_review_reason": null
    }
  ]
}

Classification values (pick all that apply):
  malicious, fraud, money_laundering, market_manipulation, bribery,
  insider_trading, secrecy_breach, phishing, scam, quid_pro_quo,
  compliance, financial_risk, normal_email

Rules:
- If no risk detected → classifications: ["normal_email"], evidence_lines: []
- If risk detected → confidence >= 0.6, include 1-3 evidence_lines with exact quoted text
- If intent is ambiguous → manual_review_required: true
- Do NOT use "none" or "unknown" as a classification

Tags (pick all that apply from this list):
  urgent, confidential, financial_amount_mentioned, external_sender,
  attachment_hinted, third_party_mentioned, regulatory_term, vague_language

Analyze the following emails:
"""

FALLBACK_PROMPT = """Analyze these emails for compliance risk. Return JSON only.

Format: {"results": [{"email_id": "...", "classifications": ["..."], "tags": [], "confidence": 0.0,
"evidence_lines": [], "reasoning": "...", "manual_review_required": false, "manual_review_reason": null}]}

Use "normal_email" for no-risk emails. Never use "none" or "unknown".

Emails:
"""
