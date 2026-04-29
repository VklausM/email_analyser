import json

try:
    with open("scoring_matrix.json") as f:
        SCORING_MATRIX = json.load(f)
    CAT_MAP = {f"type_{i:02d}": name for i, name in enumerate(SCORING_MATRIX.keys())}
    REVERSE_CAT_MAP = {name: cat_id for cat_id, name in CAT_MAP.items()}
    CATEGORIES_DESC = "\n".join([f"- {cid}: {name}" for cid, name in CAT_MAP.items()])
except:
    CAT_MAP = {"type_01": "risk_detected", "type_02": "normal"}
    REVERSE_CAT_MAP = {"risk_detected": "type_01", "normal": "type_02"}
    CATEGORIES_DESC = "- type_01: risk_detected\n- type_02: normal"

ANALYSIS_PROMPT = f"""Audit text patterns carefully. 

STRICT RULE: Only set manual_review_required=true for clear, unambiguous L3 or L4 findings. For all L1/L2 findings or doubts, set manual_review_required=false.

Pattern Definitions:
{CATEGORIES_DESC}

Levels:
- L4: Highest priority finding.
- L3: Significant finding.
- L2: Minor anomaly.
- L1: Routine observation.

Output JSON:
{{
  "results": [
    {{
      "email_id": "...",
      "classifications": ["type_01"], 
      "tags": ["urgent"],
      "confidence": 0.9,
      "reasoning": "...",
      "evidence_lines": [{{ "line_number": 1, "text": "...", "risk_level": "L1|L2|L3|L4", "reason": "..." }}],
      "manual_review_required": false
    }}
  ]
}}

Text:
"""

FALLBACK_PROMPT = "Classify patterns in JSON 'results'."
