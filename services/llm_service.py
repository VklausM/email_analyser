import json
import time
import re
import random
from typing import Any, Dict
from langchain_openai import AzureChatOpenAI
from config import settings
from utils.logger import get_logger

log = get_logger("llm")

class LLMError(Exception): pass

class LLMService:
    def __init__(self):
        try: self.client = AzureChatOpenAI(azure_endpoint=settings.AZURE_OPENAI_ENDPOINT, api_key=settings.AZURE_OPENAI_API_KEY, azure_deployment=settings.AZURE_OPENAI_CHAT_DEPLOYMENT, api_version=settings.AZURE_OPENAI_API_VERSION, temperature=0.2, timeout=30, max_retries=0)
        except Exception as e: raise LLMError(f"Init failed: {e}")

    def call_json(self, prompt: str) -> Dict[str, Any]:
        msg, last = [("user", "Return ONLY valid JSON.\n\n" + prompt)], None
        for i in range(settings.MAX_RETRIES):
            try:
                log.debug("LLM Call (Attempt %d/%d)", i+1, settings.MAX_RETRIES)
                resp = self.client.invoke(msg, response_format={"type": "json_object"})
                if not resp.content.strip(): raise LLMError("Empty response")
                return self._normalize(self._parse(resp.content.strip()))
            except Exception as e:
                last = e
                log.warning("LLM Call Attempt %d failed: %s", i+1, e)
                if i < settings.MAX_RETRIES - 1:
                    d = min(settings.INITIAL_RETRY_DELAY * (2**i), settings.MAX_RETRY_DELAY)
                    time.sleep(d + random.uniform(0, d*0.1))
        raise LLMError(f"Retries exhausted: {last}")

    def _parse(self, text: str):
        try: return json.loads(text)
        except:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try: return json.loads(m.group())
                except: pass
        raise LLMError("JSON parse failed")

    def _normalize(self, data: Any):
        if isinstance(data, dict):
            if "results" in data and isinstance(data["results"], list): return data
            for k in ("emails", "analyses", "items"):
                if k in data and isinstance(data[k], list): return {"results": data[k]}
        if isinstance(data, list): return {"results": data}
        raise LLMError("Missing results list")

_svc = None
def get_llm_service():
    global _svc
    if _svc is None: _svc = LLMService()
    return _svc
