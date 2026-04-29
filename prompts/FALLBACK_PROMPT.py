FALLBACK_PROMPT = """YOU ARE A RISK ANALYSIS SYSTEM.

RETURN ONLY VALID JSON. NO EXTRA TEXT.

TASK:
Assess emails for potential financial/compliance risk signals.

Do NOT make definitive accusations of crimes.
Instead, identify:
- unusual requests
- suspicious financial language
- confidentiality concerns
- social engineering patterns

CLASSIFICATIONS (use best fit):
- suspicious_activity
- sensitive_information
- unusual_request
- phishing_like
- none

OUTPUT FORMAT:
{
  "results": [
    {
      "email_id": "string",
      "classifications": ["string"],
      "confidence": 0.0,
      "evidence_lines": [
        {
          "line_number": 1,
          "text": "string",
          "risk_level": "low" | "medium" | "high",
          "reason": "string"
        }
      ],
      "reasoning": "string",
      "manual_review_required": true,
      "manual_review_reason": "string or null"
    }
  ]
}
"""