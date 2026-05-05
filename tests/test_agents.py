import json
import uuid
from unittest.mock import patch, MagicMock

import pytest

from app import create_app, db
from app.models.profile import BusinessProfile, PipelineRun
from app.models.query import DiscoveredQuery
from app.models.recommendation import ContentRecommendation
from app.agents.discovery import QueryDiscoveryAgent
from app.agents.scoring import VisibilityScoringAgent
from app.agents.recommendation import ContentRecommendationAgent
from app.utils.scoring import calculate_opportunity_score
from app.services.pipeline import PipelineOrchestrator


PROFILE_DATA = {
    "name": "Test SEO Tool",
    "domain": "testseo.com",
    "industry": "SEO Software",
    "description": "AI-powered SEO tool",
    "competitors": ["competitor1.com", "competitor2.com"],
}

QUERY_RESULT = {
    "queries": [
        "What is the best SEO tool for content teams?",
        "How does Test SEO compare to competitor1.com?",
        "Which tool is best for keyword research?",
        "How to optimize content for AI search?",
        "What are the top SEO tools in 2025?",
        "Is Test SEO worth the price?",
        "How do I do competitor keyword analysis?",
        "Best AI tool for content briefs?",
        "Test SEO vs competitor2.com review",
        "How to improve domain authority quickly?",
        "What is the best alternative to competitor1.com?",
        "How to measure SEO ROI?",
    ]
}

SCORE_RESULT = {
    "estimated_search_volume": 1200,
    "competitive_difficulty": 62,
    "domain_visible": False,
    "visibility_position": None,
}

RECOMMENDATION_RESULT = {
    "recommendations": [
        {
            "target_query": "What is the best SEO tool for content teams?",
            "content_type": "blog_post",
            "title": "Best SEO Tools for Content Teams in 2025",
            "rationale": "This query shows high commercial intent and your domain is not appearing",
            "target_keywords": ["seo tools", "content teams", "best seo software"],
            "priority": "high",
        },
        {
            "target_query": "How does Test SEO compare to competitor1.com?",
            "content_type": "comparison_guide",
            "title": "Test SEO vs Competitor1: Complete Comparison",
            "rationale": "Direct comparison query where competitor is being mentioned instead",
            "target_keywords": ["test seo review", "competitor1 alternative", "seo tool comparison"],
            "priority": "high",
        },
        {
            "target_query": "Best AI tool for content briefs?",
            "content_type": "landing_page",
            "title": "AI Content Brief Tool - Test SEO",
            "rationale": "Feature-specific landing page to capture this intent",
            "target_keywords": ["ai content briefs", "content brief generator", "automated briefs"],
            "priority": "medium",
        },
    ]
}


@pytest.fixture
def app():
    application = create_app(config_override={
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
    })
    with application.app_context():
        db.create_all()
        import app.models  # noqa
    yield application
    with application.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def profile_id(app):
    with app.app_context():
        p = BusinessProfile(**PROFILE_DATA)
        db.session.add(p)
        db.session.commit()
        pid = p.id
    return pid


@pytest.fixture
def orchestrator(app):
    return PipelineOrchestrator()


class TestOpportunityScore:
    def test_high_opportunity_query(self):
        score = calculate_opportunity_score(5000, 20, False, "best SEO tool vs competitor review")
        assert score > 0.5

    def test_low_opportunity_query(self):
        score = calculate_opportunity_score(50, 95, True, "what is seo")
        assert score < 0.3

    def test_visible_domain_reduces_score(self):
        score_visible = calculate_opportunity_score(1000, 50, True, "best tool")
        score_invisible = calculate_opportunity_score(1000, 50, False, "best tool")
        assert score_invisible > score_visible

    def test_commercial_intent_increases_score(self):
        score_commercial = calculate_opportunity_score(1000, 50, False, "best tool vs competitor review")
        score_info = calculate_opportunity_score(1000, 50, False, "what is the definition")
        assert score_commercial > score_info

    def test_score_bounded_0_to_1(self):
        assert 0.0 <= calculate_opportunity_score(0, 0, True, "test") <= 1.0
        assert 0.0 <= calculate_opportunity_score(99999, 0, False, "best vs review") <= 1.0


class TestQueryDiscoveryAgent:
    @patch.object(QueryDiscoveryAgent, "_call_llm")
    def test_returns_query_list(self, mock_call):
        expected = QUERY_RESULT["queries"]
        mock_call.return_value = json.dumps({"queries": expected})
        agent = QueryDiscoveryAgent(api_key="sk-test")
        result = agent.run(profile=PROFILE_DATA)
        assert isinstance(result, list)
        assert len(result) == len(expected)
        assert result == expected

    @patch.object(QueryDiscoveryAgent, "_call_llm")
    def test_handles_markdown_fences(self, mock_call):
        mock_call.return_value = f"```json\n{json.dumps(QUERY_RESULT)}\n```"
        agent = QueryDiscoveryAgent(api_key="sk-test")
        result = agent.run(profile=PROFILE_DATA)
        assert len(result) == 12

    @patch.object(QueryDiscoveryAgent, "_call_llm")
    def test_raises_on_invalid_format(self, mock_call):
        mock_call.return_value = json.dumps({"wrong_key": []})
        agent = QueryDiscoveryAgent(api_key="sk-test")
        with pytest.raises(ValueError, match="Unexpected response format"):
            agent.run(profile=PROFILE_DATA)

    @patch.object(QueryDiscoveryAgent, "_call_llm")
    def test_raises_on_too_few_queries(self, mock_call):
        mock_call.return_value = json.dumps({"queries": ["one", "two"]})
        agent = QueryDiscoveryAgent(api_key="sk-test")
        with pytest.raises(ValueError, match="Expected at least 10 queries"):
            agent.run(profile=PROFILE_DATA)

    @patch.object(QueryDiscoveryAgent, "_call_llm")
    def test_truncates_to_20_queries(self, mock_call):
        many_queries = {"queries": [f"Question {i}?" for i in range(30)]}
        mock_call.return_value = json.dumps(many_queries)
        agent = QueryDiscoveryAgent(api_key="sk-test")
        result = agent.run(profile=PROFILE_DATA)
        assert len(result) == 20

    def test_missing_api_key_no_call(self, app):
        with patch.object(QueryDiscoveryAgent, "_call_llm") as mock_call:
            mock_call.side_effect = RuntimeError("should not be called")
            agent = QueryDiscoveryAgent(api_key="")
            with app.app_context():
                with app.test_request_context():
                    app.config["OPENAI_API_KEY"] = ""
                    with pytest.raises((ValueError, RuntimeError)):
                        agent.run(profile=PROFILE_DATA)


class TestVisibilityScoringAgent:
    @patch.object(VisibilityScoringAgent, "_call_llm")
    def test_scores_single_query(self, mock_call):
        mock_call.return_value = json.dumps(SCORE_RESULT)
        agent = VisibilityScoringAgent(api_key="sk-test")
        results = agent.run(
            queries=["What is the best SEO tool?"],
            target_domain="testseo.com",
            competitors=["comp.com"],
        )
        assert len(results) == 1
        r = results[0]
        assert r["estimated_search_volume"] == 1200
        assert r["competitive_difficulty"] == 62
        assert r["domain_visible"] is False
        assert r["visibility_position"] is None
        assert 0.0 <= r["opportunity_score"] <= 1.0

    @patch.object(VisibilityScoringAgent, "_call_llm")
    def test_scores_multiple_queries(self, mock_call):
        mock_call.return_value = json.dumps(SCORE_RESULT)
        agent = VisibilityScoringAgent(api_key="sk-test")
        results = agent.run(
            queries=["Q1?", "Q2?", "Q3?"],
            target_domain="testseo.com",
            competitors=["comp.com"],
        )
        assert len(results) == 3

    @patch.object(VisibilityScoringAgent, "_call_llm")
    def test_continues_on_single_query_failure(self, mock_call):
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("LLM error")
            return json.dumps(SCORE_RESULT)

        mock_call.side_effect = side_effect
        agent = VisibilityScoringAgent(api_key="sk-test")
        results = agent.run(
            queries=["good query?", "fail query?", "another good?"],
            target_domain="testseo.com",
            competitors=["comp.com"],
        )
        assert len(results) == 3
        assert results[0]["estimated_search_volume"] == 1200
        assert "error" in results[1]
        assert results[2]["estimated_search_volume"] == 1200

    @patch.object(VisibilityScoringAgent, "_call_llm")
    def test_handles_invalid_json_from_llm(self, mock_call):
        mock_call.return_value = "this is not json at all"
        agent = VisibilityScoringAgent(api_key="sk-test")
        results = agent.run(
            queries=["test query?"],
            target_domain="testseo.com",
            competitors=["comp.com"],
        )
        assert "error" in results[0]


class TestContentRecommendationAgent:
    @patch.object(ContentRecommendationAgent, "_call_llm")
    def test_returns_recommendations(self, mock_call):
        mock_call.return_value = json.dumps(RECOMMENDATION_RESULT)
        agent = ContentRecommendationAgent(api_key="sk-test")
        invisible_queries = [
            {"query_text": "What is the best SEO tool for content teams?", "estimated_search_volume": 1200, "competitive_difficulty": 62, "opportunity_score": 0.7},
            {"query_text": "How does Test SEO compare to competitor1.com?", "estimated_search_volume": 800, "competitive_difficulty": 55, "opportunity_score": 0.65},
        ]
        results = agent.run(profile=PROFILE_DATA, invisible_queries=invisible_queries)
        assert len(results) == 3
        assert results[0]["content_type"] == "blog_post"
        assert results[0]["priority"] == "high"
        assert isinstance(results[0]["target_keywords"], list)

    @patch.object(ContentRecommendationAgent, "_call_llm")
    def test_validates_content_type(self, mock_call):
        bad_result = {"recommendations": [{"target_query": "q?", "content_type": "invalid_type", "title": "T", "rationale": "R", "target_keywords": [], "priority": "high"}]}
        mock_call.return_value = json.dumps(bad_result)
        agent = ContentRecommendationAgent(api_key="sk-test")
        results = agent.run(profile=PROFILE_DATA, invisible_queries=[{"query_text": "q?", "estimated_search_volume": 100, "competitive_difficulty": 50, "opportunity_score": 0.5}])
        assert results[0]["content_type"] == "blog_post"

    @patch.object(ContentRecommendationAgent, "_call_llm")
    def test_truncates_to_5_recommendations(self, mock_call):
        many_recs = {"recommendations": [
            {"target_query": f"Q{i}?", "content_type": "blog_post", "title": f"T{i}", "rationale": f"R{i}", "target_keywords": [], "priority": "high"}
            for i in range(8)
        ]}
        mock_call.return_value = json.dumps(many_recs)
        agent = ContentRecommendationAgent(api_key="sk-test")
        results = agent.run(profile=PROFILE_DATA, invisible_queries=[{"query_text": f"Q{i}?", "estimated_search_volume": 100, "competitive_difficulty": 50, "opportunity_score": 0.5} for i in range(8)])
        assert len(results) == 5


class TestPipelineOrchestrator:
    @patch.object(QueryDiscoveryAgent, "run")
    @patch.object(VisibilityScoringAgent, "run")
    @patch.object(ContentRecommendationAgent, "run")
    def test_full_pipeline_success(self, mock_rec, mock_score, mock_discover, app, profile_id, orchestrator):
        mock_discover.return_value = QUERY_RESULT["queries"]
        mock_score.return_value = [
            {**SCORE_RESULT, "query_text": q, "opportunity_score": calculate_opportunity_score(1200, 62, False, q)}
            for q in QUERY_RESULT["queries"]
        ]
        mock_rec.return_value = RECOMMENDATION_RESULT["recommendations"]

        with app.app_context():
            result = orchestrator.run(profile_id)

        assert result["status"] == "completed"
        assert result["queries_discovered"] == 12
        assert result["queries_scored"] == 12
        assert len(result["top_opportunity_queries"]) == 3
        assert len(result["recommendations"]) == 3

    @patch.object(QueryDiscoveryAgent, "run")
    @patch.object(VisibilityScoringAgent, "run")
    @patch.object(ContentRecommendationAgent, "run")
    def test_pipeline_persists_to_db(self, mock_rec, mock_score, mock_discover, app, profile_id, orchestrator):
        mock_discover.return_value = QUERY_RESULT["queries"][:3]
        mock_score.return_value = [
            {**SCORE_RESULT, "query_text": q, "opportunity_score": calculate_opportunity_score(1200, 62, False, q)}
            for q in QUERY_RESULT["queries"][:3]
        ]
        mock_rec.return_value = RECOMMENDATION_RESULT["recommendations"][:1]

        with app.app_context():
            orchestrator.run(profile_id)

            queries = db.session.query(DiscoveredQuery).filter_by(profile_uuid=profile_id).all()
            assert len(queries) == 3
            assert all(q.opportunity_score > 0 for q in queries)

            recommendations = db.session.query(ContentRecommendation).filter_by(profile_uuid=profile_id).all()
            assert len(recommendations) == 1

            runs = db.session.query(PipelineRun).filter_by(profile_uuid=profile_id).all()
            assert len(runs) == 1
            assert runs[0].status == "completed"

    @patch.object(QueryDiscoveryAgent, "run")
    @patch.object(VisibilityScoringAgent, "run")
    def test_pipeline_skips_agent_3_when_no_invisible_queries(self, mock_score, mock_discover, app, profile_id, orchestrator):
        mock_discover.return_value = QUERY_RESULT["queries"][:2]
        mock_score.return_value = [
            {**SCORE_RESULT, "domain_visible": True, "query_text": q, "opportunity_score": calculate_opportunity_score(1200, 62, True, q)}
            for q in QUERY_RESULT["queries"][:2]
        ]

        with app.app_context():
            result = orchestrator.run(profile_id)

        assert result["status"] == "completed"
        assert len(result["recommendations"]) == 0

    def test_recheck_query(self, app, profile_id, orchestrator):
        with app.app_context():
            dq = DiscoveredQuery(
                profile_uuid=profile_id,
                run_uuid=str(uuid.uuid4()),
                query_text="test query?",
            )
            db.session.add(dq)
            db.session.commit()
            dq_id = dq.id

        with app.app_context():
            with patch.object(VisibilityScoringAgent, "run") as mock_score:
                mock_score.return_value = [{
                    **SCORE_RESULT,
                    "query_text": "test query?",
                    "opportunity_score": calculate_opportunity_score(1200, 62, False, "test query?"),
                }]

                result = orchestrator.recheck_query(dq_id)

                assert result["estimated_search_volume"] == 1200
                assert result["competitive_difficulty"] == 62
                assert result["domain_visible"] is False

    def test_recheck_nonexistent_query(self, app, orchestrator):
        with app.app_context():
            with pytest.raises(ValueError, match="not found"):
                orchestrator.recheck_query("nonexistent-uuid")


class TestAPIEndpoints:
    def test_create_profile(self, client):
        resp = client.post("/api/v1/profiles", json=PROFILE_DATA)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == PROFILE_DATA["name"]
        assert data["domain"] == PROFILE_DATA["domain"]
        assert data["status"] == "created"
        assert "profile_uuid" in data

    def test_create_profile_strips_domain(self, client):
        resp = client.post("/api/v1/profiles", json={
            **PROFILE_DATA,
            "domain": "https://TestSEO.com/",
        })
        assert resp.status_code == 201
        assert resp.get_json()["domain"] == "testseo.com"

    def test_create_duplicate_profile(self, client):
        client.post("/api/v1/profiles", json=PROFILE_DATA)
        resp = client.post("/api/v1/profiles", json=PROFILE_DATA)
        assert resp.status_code == 409

    def test_create_profile_validation(self, client):
        resp = client.post("/api/v1/profiles", json={"name": ""})
        assert resp.status_code == 400

    def test_get_profile(self, client):
        create_resp = client.post("/api/v1/profiles", json=PROFILE_DATA)
        uuid = create_resp.get_json()["profile_uuid"]
        resp = client.get(f"/api/v1/profiles/{uuid}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "stats" in data
        assert "total_queries_discovered" in data["stats"]

    def test_get_profile_not_found(self, client):
        resp = client.get("/api/v1/profiles/nonexistent")
        assert resp.status_code == 404

    def test_get_queries_empty(self, client):
        create_resp = client.post("/api/v1/profiles", json=PROFILE_DATA)
        uuid = create_resp.get_json()["profile_uuid"]
        resp = client.get(f"/api/v1/profiles/{uuid}/queries")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["queries"] == []
        assert "pagination" in data

    def test_get_queries_with_filters(self, client):
        create_resp = client.post("/api/v1/profiles", json=PROFILE_DATA)
        uuid = create_resp.get_json()["profile_uuid"]
        resp = client.get(f"/api/v1/profiles/{uuid}/queries?min_score=0.5&status=not_visible&page=1&per_page=10")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "queries" in data
        assert "pagination" in data

    def test_get_recommendations_empty(self, client):
        create_resp = client.post("/api/v1/profiles", json=PROFILE_DATA)
        uuid = create_resp.get_json()["profile_uuid"]
        resp = client.get(f"/api/v1/profiles/{uuid}/recommendations")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["recommendations"] == []

    def test_recheck_query_not_found(self, client):
        resp = client.post("/api/v1/queries/nonexistent/recheck")
        assert resp.status_code == 404
