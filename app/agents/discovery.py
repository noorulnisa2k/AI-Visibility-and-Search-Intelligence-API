import json
import logging
from typing import Any, Optional

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Query Discovery Agent specializing in identifying commercially relevant questions that users ask AI assistants (ChatGPT, Claude, Perplexity, etc.) when searching for products or services.

Your task: Given a business profile, generate 10-20 natural-language questions that real users would ask AI tools when evaluating solutions in this space.

Guidelines:
- Questions must be commercially relevant (related to buying, comparing, or evaluating tools/services)
- Include a mix of: comparison queries ("X vs Y"), best-of queries ("best tool for X"), problem-solution queries ("how do I do X"), and informational queries with commercial intent
- Questions should be specific and realistic — not generic
- Include the target domain and competitors naturally across different questions
- Each question should be a complete, well-formed sentence
- Return ONLY valid JSON — no markdown, no explanation, no preamble

Output format (strictly this JSON schema):
{
  "queries": [
    "What is the best tool for [specific task]?",
    "How does [domain] compare to [competitor]?",
    ...
  ]
}

The "queries" array must contain between 10 and 20 question strings. Each string must be a question ending with a question mark. Do not include duplicates."""

USER_PROMPT_TEMPLATE = """Business Profile:
- Company: {name}
- Domain: {domain}
- Industry: {industry}
- Description: {description}
- Competitors: {competitors}

Generate queries that users would ask AI assistants when looking for solutions in the {industry} space, specifically related to {name} and its competitors."""


class QueryDiscoveryAgent(BaseAgent):
    MODEL = "gpt-4o"
    TEMPERATURE = 0.7

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def run(self, profile: dict[str, Any]) -> list[str]:
        competitors_str = ", ".join(profile.get("competitors", []))
        user_prompt = USER_PROMPT_TEMPLATE.format(
            name=profile.get("name", ""),
            domain=profile.get("domain", ""),
            industry=profile.get("industry", ""),
            description=profile.get("description", ""),
            competitors=competitors_str,
        )

        raw = self._call_llm(self.system_prompt(), user_prompt)
        parsed = self._parse_json(raw)

        if not isinstance(parsed, dict) or "queries" not in parsed:
            raise ValueError(f"Unexpected response format from QueryDiscoveryAgent: {parsed}")

        queries = parsed["queries"]
        if not isinstance(queries, list) or len(queries) < 10:
            raise ValueError(f"Expected at least 10 queries, got {len(queries) if isinstance(queries, list) else 0}")

        queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]

        if len(queries) > 20:
            queries = queries[:20]

        logger.info(f"QueryDiscoveryAgent returned {len(queries)} queries")
        return queries
