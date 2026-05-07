import uuid
from datetime import datetime, timezone
from app import db


class DiscoveredQuery(db.Model):
    __tablename__ = "discovered_queries"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_uuid = db.Column(db.String(36), db.ForeignKey("business_profiles.id"), nullable=False)
    run_uuid = db.Column(db.String(36), db.ForeignKey("pipeline_runs.id"), nullable=False)
    query_text = db.Column(db.Text, nullable=False)
    estimated_search_volume = db.Column(db.Integer, nullable=False, default=0)
    competitive_difficulty = db.Column(db.Integer, nullable=False, default=0)
    opportunity_score = db.Column(db.Float, nullable=False, default=0.0)
    domain_visible = db.Column(db.Boolean, nullable=False, default=False)
    visibility_position = db.Column(db.Integer, nullable=True)
    discovered_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    recommendations = db.relationship("ContentRecommendation", backref="target_query", lazy=True, cascade="all, delete-orphan")

    @property
    def visibility_status(self):
        if self.domain_visible:
            return "visible"
        return "not_visible"

    def to_dict(self):
        return {
            "query_uuid": self.id,
            "query_text": self.query_text,
            "estimated_search_volume": self.estimated_search_volume,
            "competitive_difficulty": self.competitive_difficulty,
            "opportunity_score": round(self.opportunity_score, 4),
            "domain_visible": self.domain_visible,
            "visibility_position": self.visibility_position,
            "visibility_status": self.visibility_status,
            "discovered_at": self.discovered_at.isoformat(),
        }
