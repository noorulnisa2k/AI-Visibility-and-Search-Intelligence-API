import os
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_override=None):
    load_dotenv()

    application = Flask(__name__)

    application.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///dev.db")
    application.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    application.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    application.config["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")

    if config_override:
        application.config.update(config_override)

    db.init_app(application)
    migrate.init_app(application, db)

    import app.models  # noqa: F401 - register models with SQLAlchemy

    from app.api.profiles import profiles_bp
    from app.api.queries import queries_bp

    application.register_blueprint(profiles_bp, url_prefix="/api/v1")
    application.register_blueprint(queries_bp, url_prefix="/api/v1")

    @application.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad request", "message": str(e.description)}), 400

    @application.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found", "message": str(e.description)}), 404

    @application.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "Internal server error", "message": "An unexpected error occurred"}), 500

    return application
