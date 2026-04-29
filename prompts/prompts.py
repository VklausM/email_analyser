ANALYSIS_PROMPT = """Analyze these emails for BFSI compliance and security risks.

Focus Areas:
- Phishing: Attempts to steal credentials or sensitive bank info.
- Social Engineering: Urgency, authority, or fear used to bypass procedures.
- Data Protection: Unauthorized sharing of customer PII or internal secrets.
- Fraud: Unusual payment requests or account changes.

Rules:
1. Only flag 'manual_review_required' if the email is genuinely ambiguous or contains a high-stakes request that MUST be seen by a human (e.g., large transfer request). Do not over-flag.
2. If it's a routine business email, classify as 'normal_email' with high confidence.
3. Use specific categories: phishing, social_engineering, data_leakage, fraudulent_request, policy_violation, normal_email.

Output JSON:
{
  "results": [
    {
      "email_id": "...",
      "classifications": ["..."],
      "tags": ["..."],
      "confidence": 0.85,
      "reasoning": "...",
      "evidence_lines": [{"line_number": 1, "text": "...", "risk_level": "low|medium|high|critical", "reason": "..."}],
      "manual_review_required": false,
      "manual_review_reason": "..."
    }
  ]
}

Emails:
"""

FALLBACK_PROMPT = "Extract security risks from these emails. Use JSON list 'results'."
