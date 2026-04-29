from abc import ABC, abstractmethod
import json
import logging
import time
import re
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse
from config import settings
import random
from langchain_openai import AzureChatOpenAI
from langchain_core.exceptions import LangChainException

logger = logging.getLogger(__name__)


class LLMValidationError(Exception):
    """Raised when LLM response validation fails."""
    pass


class LLMServiceError(Exception):
    """Base exception for LLM service errors."""
    pass


class BaseLLMService(ABC):
    @abstractmethod
    def call_with_json(self, prompt: str, temperature: float = 0.2) -> Dict[str, Any]:
        pass


class OpenAIService(BaseLLMService):
    def __init__(self):        
        # Initialize client
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
            self.model = settings.AZURE_OPENAI_CHAT_DEPLOYMENT
            logger.info(f"LLM service initialized with model: {self.model}")
            
        except Exception as e:
            logger.error(f"Failed to initialize LLM service: {e}")
            raise LLMServiceError(f"LLM initialization failed: {e}") from e

    @staticmethod
    def _prepare_messages(
        prompt: str | List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        if isinstance(prompt, str):
            if not prompt or not isinstance(prompt, str):
                raise TypeError("Prompt must be a non-empty string")
            return [("user", prompt)]
        
        if isinstance(prompt, list):
            if not prompt:
                raise TypeError("Prompt list cannot be empty")
            
            validated = []
            for item in prompt:
                if not isinstance(item, tuple) or len(item) != 2:
                    raise TypeError(
                        "Each prompt item must be a (role, content) tuple"
                    )
                role, content = item
                if role not in ("user", "assistant", "system"):
                    raise TypeError(f"Invalid role: {role}")
                if not isinstance(content, str) or not content.strip():
                    raise TypeError(
                        f"Content for role '{role}' must be non-empty string"
                    )
                validated.append((role, content.strip()))
            
            return validated
        
        raise TypeError(
            "Prompt must be string or list of (role, content) tuples"
        )

    @staticmethod
    def _validate_json_response(data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise LLMValidationError(
                f"Response must be JSON object, got {type(data).__name__}"
            )
        
        # If already has 'results' key, validate it
        if "results" in data:
            results = data["results"]
            if not isinstance(results, list):
                raise LLMValidationError(
                    f"'results' must be list, got {type(results).__name__}"
                )
            if not results:
                raise LLMValidationError("'results' list is empty")
            return data
        
        # Try to find results in common alternative keys
        for key in ("emails", "analyses", "analysis", "items", "data"):
            if key in data and isinstance(data[key], list):
                if data[key]:  # Not empty
                    return {"results": data[key]}
        
        # If data is itself a list of results
        if isinstance(data, list) and data:
            return {"results": data}
        
        raise LLMValidationError(
            "Response does not contain valid 'results' structure"
        )

    @staticmethod
    def _extract_json_from_text(text: str) -> Dict[str, Any]:
        text = text.strip()
        
        # Try direct JSON parsing first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Look for JSON objects in text
        json_pattern = r'\{[\s\S]*\}(?=\s*$|\s*[`\n])'
        matches = re.finditer(json_pattern, text)
        
        for match in matches:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue
        
        # Look for JSON arrays
        json_array_pattern = r'\[[\s\S]*\](?=\s*$|\s*[`\n])'
        matches = re.finditer(json_array_pattern, text)
        
        for match in matches:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue
        
        raise LLMValidationError(
            "Could not extract valid JSON from response"
        )

    def _exponential_backoff(self, attempt: int) -> float:
        delay = settings.INITIAL_RETRY_DELAY * (2 ** attempt)
        delay = min(delay, settings.MAX_RETRY_DELAY)
        jitter = random.uniform(0, 0.1 * delay)
        return delay + jitter

    def call_with_json(
        self,
        prompt: str | List[Tuple[str, str]],
        temperature: float = 0.2
    ) -> Dict[str, Any]:
        
        # Prepare and validate messages
        try:
            messages = self._prepare_messages(prompt)
        except TypeError as e:
            logger.error(f"Invalid prompt format: {e}")
            raise LLMValidationError(f"Invalid prompt: {e}") from e
        
        # Add JSON instruction to first message
        if messages:
            role, content = messages[0]
            messages[0] = (
                role,
                "Return response ONLY as valid JSON object. "
                "No markdown, no extra text.\n\n" + content
            )
        
        last_error: Optional[Exception] = None
        
        # Retry loop with exponential backoff
        for attempt in range(settings.MAX_RETRIES):
            try:
                logger.info(
                    f"LLM call attempt {attempt + 1}/{settings.MAX_RETRIES}"
                )
                
                response = self.client.invoke(
                    messages,
                    temperature=min(max(temperature, 0.0), 2.0),
                    response_format={"type": "json_object"}
                )
                
                content = response.content.strip()
                
                if not content:
                    raise LLMValidationError("Empty response from LLM")
                
                # Parse JSON
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    logger.info("Attempting JSON extraction from response")
                    data = self._extract_json_from_text(content)
                
                # Validate structure
                validated_response = self._validate_json_response(data)
                
                logger.info(f"LLM call successful on attempt {attempt + 1}")
                return validated_response
                
            except LLMValidationError as e:
                last_error = e
                logger.warning(f"Validation error on attempt {attempt + 1}: {e}")

                if attempt < settings.MAX_RETRIES - 1:
                    delay = self._exponential_backoff(attempt)
                    logger.info(f"Retrying in {delay:.2f}s...")
                    time.sleep(delay)
                    
            except (LangChainException, Exception) as e:
                last_error = e
                logger.error(f"LLM call error on attempt {attempt + 1}: {e}")
                
                if attempt < settings.MAX_RETRIES - 1:
                    delay = self._exponential_backoff(attempt)
                    logger.info(f"Retrying in {delay:.2f}s...")
                    time.sleep(delay)
        
        # All retries exhausted
        error_msg = f"LLM call failed after {settings.MAX_RETRIES} attempts"
        if last_error:
            error_msg += f": {str(last_error)}"
        
        logger.error(error_msg)
        raise LLMServiceError(error_msg) from last_error


# Global LLM service instance (lazy initialization)
_llm_service: Optional[BaseLLMService] = None


def get_llm_service(service_type: str = "openai") -> BaseLLMService:
    global _llm_service
    
    if _llm_service is not None:
        return _llm_service
    
        
    if service_type == "openai":
        _llm_service = OpenAIService()
    else:
        raise ValueError(f"Unknown LLM service type: {service_type}")
        
    return _llm_service


def reset_llm_service() -> None:
    global _llm_service
    _llm_service = None


def set_llm_service(service: BaseLLMService) -> None:
    global _llm_service
    _llm_service = service


def call_llm(prompt: str) -> str:
    service = get_llm_service()
    return service.call(prompt, temperature=0.2)
