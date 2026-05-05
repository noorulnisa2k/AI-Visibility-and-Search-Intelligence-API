from flask import Blueprint, request, jsonify

from app import db
from app.models.profile import BusinessProfile
from app.models.query import DiscoveredQuery
from app.models.recommendation import ContentRecommendation
from app.services.pipeline import PipelineOrchestrator

queries_bp = Blueprint("queries", __name__)


@queries_bp.route("/profiles/<profile_uuid>/run", methods=["POST"])
def run_pipeline(profile_uuid):
    profile = BusinessProfile.query.get(profile_uuid)
    if not profile:
        return jsonify({"error": "Not found", "message": f"Profile {profile_uuid} not found"}), 404

    orchestrator = PipelineOrchestrator()
    try:
        result = orchestrator.run(profile_uuid)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": "Pipeline failed", "message": str(e)}), 500


@queries_bp.route("/profiles/<profile_uuid>/queries", methods=["GET"])
def get_queries(profile_uuid):
    profile = BusinessProfile.query.get(profile_uuid)
    if not profile:
        return jsonify({"error": "Not found", "message": f"Profile {profile_uuid} not found"}), 404

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    min_score = request.args.get("min_score", type=float)
    status_filter = request.args.get("status")

    query_obj = DiscoveredQuery.query.filter_by(profile_uuid=profile_uuid)

    if min_score is not None:
        query_obj = query_obj.filter(DiscoveredQuery.opportunity_score >= min_score)

    if status_filter == "visible":
        query_obj = query_obj.filter_by(domain_visible=True)
    elif status_filter == "not_visible":
        query_obj = query_obj.filter_by(domain_visible=False)
    elif status_filter == "unknown":
        query_obj = query_obj.filter(DiscoveredQuery.domain_visible.is_(None))

    query_obj = query_obj.order_by(DiscoveredQuery.opportunity_score.desc())

    pagination = query_obj.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "queries": [q.to_dict() for q in pagination.items],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        },
    }), 200


@queries_bp.route("/profiles/<profile_uuid>/recommendations", methods=["GET"])
def get_recommendations(profile_uuid):
    profile = BusinessProfile.query.get(profile_uuid)
    if not profile:
        return jsonify({"error": "Not found", "message": f"Profile {profile_uuid} not found"}), 404

    recommendations = db.session.query(ContentRecommendation).filter_by(profile_uuid=profile_uuid).all()

    return jsonify({
        "recommendations": [r.to_dict() for r in recommendations],
        "total": len(recommendations),
    }), 200


@queries_bp.route("/queries/<query_uuid>/recheck", methods=["POST"])
def recheck_query(query_uuid):
    orchestrator = PipelineOrchestrator()
    try:
        result = orchestrator.recheck_query(query_uuid)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": "Not found", "message": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "Recheck failed", "message": str(e)}), 500
