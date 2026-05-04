import os
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_override=None):
    load_dotenv()

    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///dev.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    app.config["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")

    if config_override:
        app.config.update(config_override)

    db.init_app(app)
    migrate.init_app(app, db)

    from app.api.profiles import profiles_bp
    from app.api.queries import queries_bp

    app.register_blueprint(profiles_bp, url_prefix="/api/v1")
    app.register_blueprint(queries_bp, url_prefix="/api/v1")

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad request", "message": str(e.description)}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found", "message": str(e.description)}), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"error": "Internal server error", "message": "An unexpected error occurred"}), 500

    return app
