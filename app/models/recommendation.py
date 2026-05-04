import uuid
from datetime import datetime, timezone
from app import db


class ContentRecommendation(db.Model):
    __tablename__ = "content_recommendations"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_uuid = db.Column(db.String(36), db.ForeignKey("business_profiles.id"), nullable=False)
    query_uuid = db.Column(db.String(36), db.ForeignKey("discovered_queries.id"), nullable=False)
    content_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    rationale = db.Column(db.Text, nullable=False)
    target_keywords = db.Column(db.JSON, nullable=False, default=list)
    priority = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "recommendation_uuid": self.id,
            "target_query_uuid": self.query_uuid,
            "content_type": self.content_type,
            "title": self.title,
            "rationale": self.rationale,
            "target_keywords": self.target_keywords,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
        }
