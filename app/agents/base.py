import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

import openai
from flask import current_app

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    MODEL = "gpt-4o"
    MAX_RETRIES = 2
    TEMPERATURE = 0.2

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.total_tokens = 0

    @property
    def client(self) -> openai.OpenAI:
        key = self.api_key or current_app.config.get("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OpenAI API key is not configured")
        return openai.OpenAI(api_key=key)

    @abstractmethod
    def system_prompt(self) -> str:
        pass

    @abstractmethod
    def run(self, **kwargs) -> dict[str, Any]:
        pass

    def _call_llm(self, system_prompt: str, user_prompt: str, temperature: Optional[float] = None) -> str:
        temp = temperature if temperature is not None else self.TEMPERATURE
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temp,
                )
                usage = response.usage
                if usage:
                    self.total_tokens += usage.total_tokens
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty response from LLM")
                return content.strip()
            except Exception as e:
                logger.warning(f"LLM call attempt {attempt}/{self.MAX_RETRIES} failed: {e}")
                if attempt == self.MAX_RETRIES:
                    raise
        raise RuntimeError("LLM call exhausted retries")

    @staticmethod
    def _extract_json(text: str) -> Any:
        if text.startswith("```json"):
            text = text.removeprefix("```json").removesuffix("```").strip()
        elif text.startswith("```"):
            text = text.removeprefix("```").removesuffix("```").strip()
        return json.loads(text)

    def _parse_json(self, raw: str) -> Any:
        try:
            return self._extract_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"JSON parse failed, attempting recovery: {e}")
            first_brace = raw.find("{")
            last_brace = raw.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                try:
                    return self._extract_json(raw[first_brace : last_brace + 1])
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Could not extract valid JSON from LLM response: {raw[:200]}")
