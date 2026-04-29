ANALYSIS_PROMPT = """Analyze these emails for BFSI compliance risks.
Rules:
1. Classify: phishing, scam, data_leakage, fraudulent_request, unauthorized_disclosure, policy_violation, suspicious_attachment, suspicious_link, urgency_tactic, pressure_tactic, or normal_email.
2. Tag: urgent, financial_amount, sensitive_data, external_sender, internal_policy.
3. Extract specific evidence lines with line numbers.
4. If risk is low, use normal_email.

Output JSON:
{
  "results": [
    {
      "email_id": "...",
      "classifications": ["..."],
      "tags": ["..."],
      "confidence": 0.0-1.0,
      "reasoning": "...",
      "evidence_lines": [{"line_number": 1, "text": "...", "risk_level": "low|medium|high|critical", "reason": "...", "confidence": 0.5}],
      "manual_review_required": true|false,
      "manual_review_reason": "..."
    }
  ]
}

Emails:
"""

FALLBACK_PROMPT = """Extract risk classifications from these emails. Return JSON list 'results'."""
