ANALYSIS_PROMPT = """Analyze the following emails for BFSI (Banking, Financial Services, and Insurance) compliance and security risks.
Your goal is to detect threats including fraud, data leakage, social engineering, and regulatory non-compliance.

RISK CATEGORIES:
1.  Phishing/Scam: Attempts to steal credentials or sensitive info.
2.  Financial Fraud: Unauthorized payment requests, bank account changes, or fraudulent invoices.
3.  Data Leakage (DLP): Sharing PII (Personally Identifiable Information), SPII, account numbers, or internal credentials.
4.  Social Engineering: Urgency, authority, or fear tactics used to manipulate employees.
5.  Policy Violation: Breach of internal BFSI protocols or regulatory requirements (e.g., SEBI, RBI, GDPR, PCI-DSS).

OUTPUT REQUIREMENTS:
- Classify with at least one: phishing, financial_fraud, data_leakage, social_engineering, policy_violation, or normal_email.
- Add tags: urgent, pii_detected, payment_request, external_sender, internal_sensitive.
- Extract evidence lines with line numbers and a clear reason for the risk level.
- Confidence must be 0.0-1.0.
- manual_review_required: true if there is any ambiguity or high-risk detection.

Return ONLY a JSON object with a "results" key containing a list of objects.

Emails to analyze:
"""

FALLBACK_PROMPT = """Analyze these emails for BFSI risks (Fraud, Phishing, DLP). Return JSON list 'results'."""
