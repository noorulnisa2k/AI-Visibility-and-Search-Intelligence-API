import uuid
from datetime import datetime, timezone
from app import db


class BusinessProfile(db.Model):
    __tablename__ = "business_profiles"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    domain = db.Column(db.String(255), nullable=False, unique=True)
    industry = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    competitors = db.Column(db.JSON, nullable=False, default=list)
    status = db.Column(db.String(50), nullable=False, default="created")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pipeline_runs = db.relationship("PipelineRun", backref="profile", lazy=True, cascade="all, delete-orphan")
    queries = db.relationship("DiscoveredQuery", backref="profile", lazy=True, cascade="all, delete-orphan")
    recommendations = db.relationship("ContentRecommendation", backref="profile", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "profile_uuid": self.id,
            "name": self.name,
            "domain": self.domain,
            "industry": self.industry,
            "description": self.description,
            "competitors": self.competitors,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def summary_stats(self):
        total_queries = db.session.query(db.func.count(DiscoveredQuery.id)).filter_by(profile_uuid=self.id).scalar() or 0
        avg_score = db.session.query(db.func.avg(DiscoveredQuery.opportunity_score)).filter_by(profile_uuid=self.id).scalar() or 0
        total_recommendations = db.session.query(db.func.count(ContentRecommendation.id)).filter_by(profile_uuid=self.id).scalar() or 0
        return {
            "total_queries_discovered": total_queries,
            "avg_opportunity_score": round(float(avg_score), 4),
            "total_recommendations": total_recommendations,
        }


class PipelineRun(db.Model):
    __tablename__ = "pipeline_runs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_uuid = db.Column(db.String(36), db.ForeignKey("business_profiles.id"), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="pending")
    queries_discovered = db.Column(db.Integer, nullable=False, default=0)
    queries_scored = db.Column(db.Integer, nullable=False, default=0)
    tokens_used = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    queries = db.relationship("DiscoveredQuery", backref="pipeline_run", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "pipeline_uuid": self.id,
            "profile_uuid": self.profile_uuid,
            "status": self.status,
            "queries_discovered": self.queries_discovered,
            "queries_scored": self.queries_scored,
            "tokens_used": self.tokens_used,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
