import json
import logging
import time
import re
import random
from typing import Any, Dict, List, Tuple

from langchain_openai import AzureChatOpenAI
from config import settings
from utils.logger import get_logger

log = get_logger("llm")


class LLMError(Exception):
    pass


class LLMService:
    def __init__(self):
        try:
            self.client = AzureChatOpenAI(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_key=settings.AZURE_OPENAI_API_KEY,
                azure_deployment=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                temperature=0.2,
                timeout=30,
                max_retries=0,
            )
        except Exception as e:
            raise LLMError(f"Failed to init LLM: {e}") from e

    def call_json(self, prompt: str) -> Dict[str, Any]:
        messages = [("user", "Return ONLY valid JSON.\n\n" + prompt)]
        last_err = None

        for attempt in range(settings.MAX_RETRIES):
            try:
                response = self.client.invoke(
                    messages,
                    response_format={"type": "json_object"}
                )
                content = response.content.strip()
                if not content:
                    raise LLMError("Empty response")

                data = self._parse_json(content)
                return self._normalize(data)

            except Exception as e:
                last_err = e
                log.warning("Attempt %d failed: %s", attempt + 1, e)
                if attempt < settings.MAX_RETRIES - 1:
                    delay = min(settings.INITIAL_RETRY_DELAY * (2 ** attempt), settings.MAX_RETRY_DELAY)
                    delay += random.uniform(0, delay * 0.1)
                    time.sleep(delay)

        raise LLMError(f"All retries exhausted: {last_err}") from last_err

    @staticmethod
    def _parse_json(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        raise LLMError("Could not parse JSON from response")

    @staticmethod
    def _normalize(data: Any) -> Dict[str, Any]:
        if isinstance(data, dict):
            if "results" in data and isinstance(data["results"], list):
                return data
            for key in ("emails", "analyses", "analysis", "items"):
                if key in data and isinstance(data[key], list):
                    return {"results": data[key]}

        if isinstance(data, list):
            return {"results": data}

        raise LLMError("Response missing 'results' list")


_service: LLMService = None


def get_llm_service() -> LLMService:
    global _service
    if _service is None:
        _service = LLMService()
    return _service
