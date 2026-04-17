from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from openai import OpenAI
from config import settings
import json


class BaseLLMService(ABC):
    @abstractmethod
    def call(self, prompt: str, temperature: float = 0.2) -> str:
        pass
    
    @abstractmethod
    def call_with_json(self, prompt: str, temperature: float = 0.2) -> Dict[str, Any]:
        pass


class OpenAIService(BaseLLMService):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or settings.OPENAI_API_KEY)
        self.model = model or settings.MODEL_NAME
    
    def call(self, prompt: str, temperature: float = 0.2) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {str(e)}")
    
    def call_with_json(self, prompt: str, temperature: float = 0.2) -> Dict[str, Any]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return json.loads(content)
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
