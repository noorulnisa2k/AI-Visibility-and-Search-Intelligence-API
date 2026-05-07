import logging
import os
import base64
import requests
from typing import Any, Optional

from app.agents.base import BaseAgent
from app.utils.scoring import calculate_opportunity_score
from app.logging_config import get_active_logger

logger = logging.getLogger("app.agents.scoring")

SYSTEM_PROMPT = """You are a Visibility Scoring Agent specializing in analyzing search queries for AI visibility opportunities.

Your task: For each query, provide realistic estimates of search volume, competitive difficulty, and whether the target domain would appear in AI-generated answers.

Scoring guidelines:
- estimated_search_volume: Monthly search volume (integer). Be realistic based on query specificity. Broad queries: 1000-5000. Niche queries: 100-800. Long-tail: 50-300.
- competitive_difficulty: Integer 0-100. Higher means harder to rank/appear. Consider: number of established players, query maturity, content saturation.
- domain_visible: Boolean. Would the target domain likely appear in top AI-generated answers for this query? Be conservative — most domains are NOT visible for most queries. Only mark true if the domain is a well-known market leader with strong brand authority directly relevant to the query. For niche, competitor-focused, or comparison queries (e.g. "best X", "X vs Y"), the target domain is usually NOT visible.
- visibility_position: Integer 1-10 if domain_visible is true, null if false. Estimated position in AI answer (1=first mentioned).

Output format (strictly this JSON schema):
{
  "estimated_search_volume": 1200,
  "competitive_difficulty": 62,
  "domain_visible": false,
  "visibility_position": null
}

Return ONLY the JSON object. No markdown, no explanation."""


class VisibilityScoringAgent(BaseAgent):
    MODEL = "gpt-4o"
    TEMPERATURE = 0.1

    def __init__(self, api_key: Optional[str] = None, dataforseo_user: Optional[str] = None, dataforseo_pass: Optional[str] = None):
        super().__init__(api_key)
        self.dataforseo_user = dataforseo_user or os.getenv("DATAFORSEO_USER", "")
        self.dataforseo_pass = dataforseo_pass or os.getenv("DATAFORSEO_PASS", "")

    def _fetch_dataforseo_volume(self, query: str) -> Optional[int]:
        if not self.dataforseo_user or not self.dataforseo_pass:
            return None
        try:
            auth = base64.b64encode(f"{self.dataforseo_user}:{self.dataforseo_pass}".encode()).decode()
            headers = {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
            }
            payload = [
                {
                    "language_code": "en",
                    "location_code": 2840,
                    "keyword": query,
                }
            ]
            resp = requests.post(
                "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live",
                json=payload,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("tasks") and data["tasks"][0].get("result"):
                result = data["tasks"][0]["result"][0]
                return result.get("search_volume")
        except Exception as e:
            logger.warning(f"DataForSEO API call failed for '{query}': {e}")
        return None

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def _score_query(self, query: str, target_domain: str, competitors: list[str]) -> dict[str, Any]:
        user_prompt = f"""Query: "{query}"
Target domain: {target_domain}
Competitors: {', '.join(competitors)}

Analyze this query and return the scoring JSON."""

        raw = self._call_llm(SYSTEM_PROMPT, user_prompt)
        parsed = self._parse_json(raw)
        return parsed

    def run(self, queries: list[str], target_domain: str, competitors: list[str]) -> list[dict[str, Any]]:
        call_logger = get_active_logger("scoring")
        call_logger.info(f"AGENT 2 START | Scoring | queries={len(queries)} | domain={target_domain}")

        results = []
        for i, query_text in enumerate(queries, 1):
            try:
                call_logger.debug(f"AGENT 2 SCORING {i}/{len(queries)} | {query_text}")

                volume = self._fetch_dataforseo_volume(query_text)
                if volume:
                    call_logger.debug(f"AGENT 2 DATAFORSEO | query={query_text} | volume={volume}")

                ai_result = self._score_query(query_text, target_domain, competitors)
                call_logger.debug(f"AGENT 2 LLM RAW | {ai_result}")

                estimated_volume = volume or ai_result.get("estimated_search_volume", 0)
                difficulty = ai_result.get("competitive_difficulty", 50)
                domain_visible = ai_result.get("domain_visible", False)
                visibility_position = ai_result.get("visibility_position")

                if not isinstance(estimated_volume, int) or estimated_volume < 0:
                    estimated_volume = 0
                if not isinstance(difficulty, int) or difficulty < 0:
                    difficulty = 0
                difficulty = min(difficulty, 100)
                if not isinstance(domain_visible, bool):
                    domain_visible = False

                opp_score = calculate_opportunity_score(
                    estimated_search_volume=estimated_volume,
                    competitive_difficulty=difficulty,
                    domain_visible=domain_visible,
                    query_text=query_text,
                )

                score_entry = {
                    "query_text": query_text,
                    "estimated_search_volume": estimated_volume,
                    "competitive_difficulty": difficulty,
                    "opportunity_score": opp_score,
                    "domain_visible": domain_visible,
                    "visibility_position": visibility_position,
                }
                results.append(score_entry)

                call_logger.info(
                    f"AGENT 2 SCORED {i}/{len(queries)} | {query_text} | "
                    f"vol={estimated_volume} diff={difficulty} visible={domain_visible} score={opp_score:.4f}"
                )

            except Exception as e:
                logger.error(f"Failed to score query '{query_text}': {e}")
                call_logger.error(f"AGENT 2 ERROR | query={query_text} | error={e}")
                results.append({
                    "query_text": query_text,
                    "estimated_search_volume": 0,
                    "competitive_difficulty": 50,
                    "opportunity_score": 0.0,
                    "domain_visible": False,
                    "visibility_position": None,
                    "error": str(e),
                })

        call_logger.info(
            f"AGENT 2 COMPLETE | scored={len(results)}/{len(queries)} | tokens_used={self.total_tokens}"
        )
        return results
