from abc import ABC, abstractmethod
import re
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urlunparse
from config import settings
import json
from langchain_openai import AzureChatOpenAI

class BaseLLMService(ABC):
    @abstractmethod
    def call(self, prompt: str, temperature: float = 0.2) -> str:
        pass
    
    @abstractmethod
    def call_with_json(self, prompt: str, temperature: float = 0.2) -> Dict[str, Any]:
        pass


class OpenAIService(BaseLLMService):
    def __init__(self):
       
        self.client = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_deployment=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            temperature=0,
        )
        self.model = settings.AZURE_OPENAI_CHAT_DEPLOYMENT
    

    def _prepare_messages(self, prompt: str | list[tuple[str, str]]) -> list[tuple[str, str]]:
        if isinstance(prompt, str):
            return [("user", prompt)]
        if isinstance(prompt, list):
            return prompt
        raise TypeError("Unsupported prompt type for LLM invocation")

    def call(self, prompt: str | list[tuple[str, str]], temperature: float = 0.2) -> str:
        try:
            messages = self._prepare_messages(prompt)
            response = self.client.invoke(messages, temperature=temperature)
            return response.content.strip()
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {str(e)}")

    def call_with_json(self, prompt: str | list[tuple[str, str]], temperature: float = 0.2) -> Dict[str, Any]:
        try:
            messages = self._prepare_messages(prompt)
            response = self.client.invoke(messages, temperature=temperature)
            content = response.content.strip()
            json_string = re.sub(r"```json\s*", "", content, flags=re.IGNORECASE).rstrip("```").strip()
            data = json.loads(json_string)

            if isinstance(data, list):
                return {"results": data}
            if isinstance(data, dict):
                if "results" in data and isinstance(data["results"], list):
                    return {"results": data["results"]}
                # allow common alternate keys
                for key in ("emails", "analyses", "analysis", "items"):
                    if key in data and isinstance(data[key], list):
                        return {"results": data[key]}
                if all(isinstance(v, dict) for v in data.values()):
                    return {"results": [data]}
            raise RuntimeError("LLM response JSON is not a supported analysis format")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse JSON response: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {str(e)}")


_llm_service: Optional[BaseLLMService] = None


def get_llm_service(service_type: str = "openai") -> BaseLLMService:
    global _llm_service
    if _llm_service is None:
        if service_type == "openai":
            _llm_service = OpenAIService()
        else:
            raise ValueError(f"Unknown LLM service type: {service_type}")
    return _llm_service


def set_llm_service(service: BaseLLMService) -> None:
    global _llm_service
    _llm_service = service


def call_llm(prompt: str) -> str:
    service = get_llm_service()
    return service.call(prompt, temperature=0.2)
