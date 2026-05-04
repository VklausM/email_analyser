import json

def load_scoring_matrix(path="scoring_matrix.json"):
    try:
        with open(path) as f:
            data = json.load(f)

        if not isinstance(data, dict) or not data:
            raise ValueError("Invalid scoring matrix format")

        return data

    except Exception as e:
        print(f"[WARN] Failed to load scoring matrix: {e}")
        # Consistent fallback
        return {
            "risk_detected": 0.8,
            "normal": 0.0
        }


SCORING_MATRIX = load_scoring_matrix()

def normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_")


SCORING_MATRIX = {
    normalize_key(k): v for k, v in SCORING_MATRIX.items()
}

sorted_keys = sorted(SCORING_MATRIX.keys())

CAT_MAP = {
    f"type_{i:02d}": name
    for i, name in enumerate(sorted_keys)
}

REVERSE_CAT_MAP = {
    name: cat_id
    for cat_id, name in CAT_MAP.items()
}

CATEGORY_SCORES = SCORING_MATRIX

CATEGORIES_DESC = "\n".join(
    [f"- {cid}: {name}" for cid, name in CAT_MAP.items()]
)


ANALYSIS_PROMPT = f"""Audit text patterns carefully. 

STRICT RULE: Only set manual_review_required=true for clear, unambiguous L3 or L4 findings. For all L1/L2 findings or doubts, set manual_review_required=false.

Pattern Definitions:
{CATEGORIES_DESC}

Levels:
- L4: Highest priority finding.
- L3: Significant finding.
- L2: Minor anomaly.
- L1: Routine observation.

Output JSON (MUST contain a "results" key with the list of findings) (example):
{{
  "results": [
    {{
      "email_id": "...",
      "classifications": ["type_01"], 
      "tags": ["urgent"],
      "confidence": 0.75,
      "reasoning": "...",
      "evidence_lines": [{{ "line_number": 1, "text": "...", "risk_level": "L1|L2|L3|L4", "reason": "..." }}],
      "manual_review_required": false|true
    }}
  ]
}}

Text:
"""

FALLBACK_PROMPT = "Classify patterns in JSON 'results'."

SCORING_PROMPT = """You are a Data Assessment Specialist. Given the following audit findings, calculate a numeric priority score from 0 to 100.

Guidelines:
- 0-25: Level 1 (Routine)
- 26-50: Level 2 (Low priority)
- 51-75: Level 3 (Significant finding)
- 76-100: Level 4 (High priority)

Input:
Pattern Codes: {classifications}
Findings: {reasoning}
Evidence count: {evidence_count}
Confidence: {confidence}

Return ONLY a JSON object (example):
{{
  "score": 90,
  "notes": "Short summary"
}}
"""