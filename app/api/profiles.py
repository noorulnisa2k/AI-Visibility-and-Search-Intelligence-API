from flask import Blueprint, request, jsonify
from pydantic import BaseModel, Field, field_validator
from typing import Optional

from app import db
from app.models.profile import BusinessProfile, PipelineRun
from app.models.query import DiscoveredQuery
from app.models.recommendation import ContentRecommendation

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
    body = request.get_json()
    if not body:
        return jsonify({"error": "Bad request", "message": "Request body must be valid JSON"}), 400

    try:
        data = ProfileCreateSchema(**body)
    except Exception as e:
        return jsonify({"error": "Validation error", "message": str(e)}), 400

    existing = BusinessProfile.query.filter_by(domain=data.domain).first()
    if existing:
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

    return jsonify(profile.to_dict()), 201


@profiles_bp.route("/profiles/<profile_uuid>", methods=["GET"])
def get_profile(profile_uuid):
    profile = BusinessProfile.query.get(profile_uuid)
    if not profile:
        return jsonify({"error": "Not found", "message": f"Profile {profile_uuid} not found"}), 404

    stats = profile.summary_stats()

    return jsonify({
        **profile.to_dict(),
        "stats": stats,
    }), 200
