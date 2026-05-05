import logging
from typing import Any, Optional

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Content Recommendation Agent specializing in identifying content gaps and generating actionable recommendations for improving AI visibility.

Your task: Given a list of high-value queries where the target domain does NOT appear in AI-generated answers, generate 3-5 specific, actionable content recommendations.

Guidelines:
- Each recommendation must directly address a specific query gap
- content_type must be one of: blog_post, landing_page, faq, comparison_guide, case_study, tutorial
- title should be a compelling, SEO-optimized content title
- rationale must explain WHY this content addresses the gap and how it improves AI visibility
- target_keywords should be 3-6 specific keywords/phrases the content should target
- priority: "high" for queries with opportunity_score > 0.6, "medium" for > 0.3, "low" otherwise
- Recommendations must be specific and actionable, not generic
- Return ONLY valid JSON — no markdown, no explanation

Output format (strictly this JSON schema):
{
  "recommendations": [
    {
      "target_query": "the exact query text this addresses",
      "content_type": "blog_post",
      "title": "Suggested content title",
      "rationale": "Why this content addresses the gap",
      "target_keywords": ["keyword1", "keyword2", "keyword3"],
      "priority": "high"
    }
  ]
}

The "recommendations" array must contain between 3 and 5 recommendation objects."""

USER_PROMPT_TEMPLATE = """Business: {name} ({domain})
Industry: {industry}

High-value queries where {domain} does NOT appear in AI-generated answers:

{queries_json}

Generate 3-5 actionable content recommendations to address these gaps."""


class ContentRecommendationAgent(BaseAgent):
    MODEL = "gpt-4o"
    TEMPERATURE = 0.5

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)

    def system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def run(
        self,
        profile: dict[str, Any],
        invisible_queries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        queries_text = ""
        for i, q in enumerate(invisible_queries, 1):
            queries_text += (
                f"{i}. \"{q['query_text']}\" "
                f"(volume: {q['estimated_search_volume']}, "
                f"difficulty: {q['competitive_difficulty']}, "
                f"opportunity_score: {q['opportunity_score']})\n"
            )

        user_prompt = USER_PROMPT_TEMPLATE.format(
            name=profile.get("name", ""),
            domain=profile.get("domain", ""),
            industry=profile.get("industry", ""),
            queries_json=queries_text,
        )

        raw = self._call_llm(self.system_prompt(), user_prompt)
        parsed = self._parse_json(raw)

        if not isinstance(parsed, dict) or "recommendations" not in parsed:
            raise ValueError(f"Unexpected response format from ContentRecommendationAgent: {parsed}")

        recommendations = parsed["recommendations"]
        if not isinstance(recommendations, list) or len(recommendations) < 1:
            raise ValueError(f"Expected at least 1 recommendation, got {len(recommendations) if isinstance(recommendations, list) else 0}")

        if len(recommendations) > 5:
            recommendations = recommendations[:5]

        valid_types = {"blog_post", "landing_page", "faq", "comparison_guide", "case_study", "tutorial"}
        for rec in recommendations:
            rec.setdefault("content_type", "blog_post")
            if rec["content_type"] not in valid_types:
                rec["content_type"] = "blog_post"
            rec.setdefault("priority", "medium")
            if rec["priority"] not in {"high", "medium", "low"}:
                rec["priority"] = "medium"
            if not isinstance(rec.get("target_keywords"), list):
                rec["target_keywords"] = []

        logger.info(f"ContentRecommendationAgent returned {len(recommendations)} recommendations")
        return recommendations
