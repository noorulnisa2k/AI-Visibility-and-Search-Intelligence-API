from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, Field, field_validator
from typing import Optional

from app import db
from app.models.profile import BusinessProfile, PipelineRun
from app.models.query import DiscoveredQuery
from app.models.recommendation import ContentRecommendation
from app.logging_config import get_active_logger

profiles_bp = Blueprint("profiles", __name__)


class ProfileCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    domain: str = Field(..., min_length=1, max_length=255)
    industry: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    competitors: list[str] = Field(default_factory=list)

    @field_validator("domain")
    @classmethod
    def strip_domain(cls, v):
        return v.lower().strip().removeprefix("http://").removeprefix("https://").removesuffix("/")


@profiles_bp.route("/profiles", methods=["POST"])
def create_profile():
    call_logger = get_active_logger("pipeline")
    body = request.get_json()
    if not body:
        call_logger.warning("CREATE PROFILE FAILED | empty body")
        return jsonify({"error": "Bad request", "message": "Request body must be valid JSON"}), 400

    try:
        data = ProfileCreateSchema(**body)
    except Exception as e:
        call_logger.warning(f"CREATE PROFILE VALIDATION FAILED | error={e}")
        return jsonify({"error": "Validation error", "message": str(e)}), 400

    existing = BusinessProfile.query.filter_by(domain=data.domain).first()
    if existing:
        call_logger.warning(f"CREATE PROFILE CONFLICT | domain={data.domain}")
        return jsonify({"error": "Conflict", "message": f"Profile with domain '{data.domain}' already exists"}), 409

    profile = BusinessProfile(
        name=data.name,
        domain=data.domain,
        industry=data.industry,
        description=data.description,
        competitors=data.competitors,
    )
    db.session.add(profile)
    db.session.commit()

    call_logger.info(
        f"DB SAVE | BusinessProfile created | uuid={profile.id} | "
        f"name={profile.name} domain={profile.domain} industry={profile.industry}"
    )

    return jsonify(profile.to_dict()), 201


@profiles_bp.route("/profiles/<profile_uuid>", methods=["GET"])
def get_profile(profile_uuid):
    call_logger = get_active_logger("pipeline")
    profile = BusinessProfile.query.get(profile_uuid)
    if not profile:
        call_logger.warning(f"GET PROFILE NOT FOUND | uuid={profile_uuid}")
        return jsonify({"error": "Not found", "message": f"Profile {profile_uuid} not found"}), 404

    stats = profile.summary_stats()
    call_logger.info(
        f"GET PROFILE | uuid={profile_uuid} | name={profile.name} | "
        f"queries={stats['total_queries_discovered']} avg_score={stats['avg_opportunity_score']}"
    )

    return jsonify({
        **profile.to_dict(),
        "stats": stats,
    }), 200
