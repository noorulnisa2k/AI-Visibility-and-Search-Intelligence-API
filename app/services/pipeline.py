import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app import db
from app.agents.discovery import QueryDiscoveryAgent
from app.agents.scoring import VisibilityScoringAgent
from app.agents.recommendation import ContentRecommendationAgent
from app.models.profile import BusinessProfile, PipelineRun
from app.models.query import DiscoveredQuery
from app.models.recommendation import ContentRecommendation

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(self, api_key: Optional[str] = None, dataforseo_user: Optional[str] = None, dataforseo_pass: Optional[str] = None):
        self.api_key = api_key
        self.dataforseo_user = dataforseo_user
        self.dataforseo_pass = dataforseo_pass

    def run(self, profile_uuid: str) -> dict[str, Any]:
        profile = BusinessProfile.query.get(profile_uuid)
        if not profile:
            raise ValueError(f"Profile {profile_uuid} not found")

        run = PipelineRun(
            profile_uuid=profile_uuid,
            status="running",
        )
        db.session.add(run)
        db.session.commit()

        correlation_id = str(uuid.uuid4())[:8]
        logger.info(f"[{correlation_id}] Pipeline started for profile {profile_uuid}, run {run.id}")

        try:
            queries = self._run_agent_1(profile, run)
            scored_queries = self._run_agent_2(profile, run, queries)
            recommendations = self._run_agent_3(profile, run, scored_queries)

            run.status = "completed"
            run.queries_discovered = len(queries)
            run.queries_scored = len([q for q in scored_queries if "error" not in q])
            run.tokens_used = self._collect_tokens()
            run.completed_at = datetime.now(timezone.utc)
            db.session.commit()

            top_queries = sorted(
                [q for q in scored_queries if "error" not in q],
                key=lambda x: x["opportunity_score"],
                reverse=True,
            )[:3]

            logger.info(f"[{correlation_id}] Pipeline completed: {run.queries_discovered} queries, {run.queries_scored} scored, {len(recommendations)} recommendations")

            return {
                "pipeline_uuid": run.id,
                "status": "completed",
                "queries_discovered": run.queries_discovered,
                "queries_scored": run.queries_scored,
                "top_opportunity_queries": top_queries,
                "recommendations": recommendations,
                "tokens_used": run.tokens_used,
                "started_at": run.started_at.isoformat(),
                "completed_at": run.completed_at.isoformat(),
            }

        except Exception as e:
            logger.error(f"[{correlation_id}] Pipeline failed: {e}", exc_info=True)
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.now(timezone.utc)
            run.tokens_used = self._collect_tokens()
            db.session.commit()
            raise

    def recheck_query(self, query_uuid: str) -> dict[str, Any]:
        query = DiscoveredQuery.query.get(query_uuid)
        if not query:
            raise ValueError(f"Query {query_uuid} not found")

        agent = VisibilityScoringAgent(
            api_key=self.api_key,
            dataforseo_user=self.dataforseo_user,
            dataforseo_pass=self.dataforseo_pass,
        )
        profile = BusinessProfile.query.get(query.profile_uuid)
        results = agent.run(
            queries=[query.query_text],
            target_domain=profile.domain,
            competitors=profile.competitors,
        )
        self._merge_tokens(agent)

        result = results[0]
        query.estimated_search_volume = result["estimated_search_volume"]
        query.competitive_difficulty = result["competitive_difficulty"]
        query.opportunity_score = result["opportunity_score"]
        query.domain_visible = result["domain_visible"]
        query.visibility_position = result.get("visibility_position")
        db.session.commit()

        return {
            "query_uuid": query.id,
            "query_text": query.query_text,
            "estimated_search_volume": query.estimated_search_volume,
            "competitive_difficulty": query.competitive_difficulty,
            "opportunity_score": query.opportunity_score,
            "domain_visible": query.domain_visible,
            "visibility_position": query.visibility_position,
        }

    def _run_agent_1(self, profile: BusinessProfile, run: PipelineRun) -> list[str]:
        logger.info(f"Agent 1: Query Discovery for {profile.domain}")
        agent = QueryDiscoveryAgent(api_key=self.api_key)
        profile_data = {
            "name": profile.name,
            "domain": profile.domain,
            "industry": profile.industry,
            "description": profile.description,
            "competitors": profile.competitors,
        }
        queries = agent.run(profile=profile_data)
        self._merge_tokens(agent)

        for query_text in queries:
            dq = DiscoveredQuery(
                profile_uuid=profile.id,
                run_uuid=run.id,
                query_text=query_text,
            )
            db.session.add(dq)
        db.session.commit()
        return queries

    def _run_agent_2(self, profile: BusinessProfile, run: PipelineRun, queries: list[str]) -> list[dict[str, Any]]:
        logger.info(f"Agent 2: Visibility Scoring for {profile.domain} ({len(queries)} queries)")
        agent = VisibilityScoringAgent(
            api_key=self.api_key,
            dataforseo_user=self.dataforseo_user,
            dataforseo_pass=self.dataforseo_pass,
        )
        results = agent.run(
            queries=queries,
            target_domain=profile.domain,
            competitors=profile.competitors,
        )
        self._merge_tokens(agent)

        for result in results:
            dq = DiscoveredQuery.query.filter_by(run_uuid=run.id, query_text=result["query_text"]).first()
            if dq:
                dq.estimated_search_volume = result["estimated_search_volume"]
                dq.competitive_difficulty = result["competitive_difficulty"]
                dq.opportunity_score = result["opportunity_score"]
                dq.domain_visible = result["domain_visible"]
                dq.visibility_position = result.get("visibility_position")
        db.session.commit()

        return results

    def _run_agent_3(self, profile: BusinessProfile, run: PipelineRun, scored_queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        logger.info(f"Agent 3: Content Recommendations for {profile.domain}")
        invisible = [q for q in scored_queries if not q.get("domain_visible", False) and "error" not in q]
        invisible_sorted = sorted(invisible, key=lambda x: x["opportunity_score"], reverse=True)

        if not invisible_sorted:
            logger.info("No invisible queries found, skipping Agent 3")
            return []

        agent = ContentRecommendationAgent(api_key=self.api_key)
        profile_data = {
            "name": profile.name,
            "domain": profile.domain,
            "industry": profile.industry,
        }
        recommendations = agent.run(profile=profile_data, invisible_queries=invisible_sorted)
        self._merge_tokens(agent)

        for rec in recommendations:
            target_query = DiscoveredQuery.query.filter_by(
                profile_uuid=profile.id,
                query_text=rec.get("target_query", ""),
            ).first()

            cr = ContentRecommendation(
                profile_uuid=profile.id,
                query_uuid=target_query.id if target_query else run.id,
                content_type=rec["content_type"],
                title=rec["title"],
                rationale=rec["rationale"],
                target_keywords=rec.get("target_keywords", []),
                priority=rec["priority"],
            )
            db.session.add(cr)
        db.session.commit()

        return recommendations

    _total_tokens = 0

    def _merge_tokens(self, agent):
        self._total_tokens += agent.total_tokens

    def _collect_tokens(self) -> int:
        tokens = self._total_tokens
        self._total_tokens = 0
        return tokens
