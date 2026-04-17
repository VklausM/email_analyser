import json

def parse_output(response):
    try:
        data = json.loads(response)
        return data
    except:
        return {
            "classification": ["unknown"],
            "confidence": 0.3,
            "tone": "neutral",
            "evidence_lines": [],
            "reasoning": "Parsing failed"
        }