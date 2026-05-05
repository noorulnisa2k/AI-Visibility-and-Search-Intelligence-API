import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()


def make_celery(app=None):
    celery_app = Celery(
        "ai_visibility",
        broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
    )

    if app:
        class ContextTask(celery_app.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery_app.Task = ContextTask

    return celery_app


celery = make_celery()


@celery.task(bind=True, name="app.tasks.run_pipeline")
def run_pipeline_task(self, profile_uuid):
    from app import create_app
    from app.services.pipeline import PipelineOrchestrator

    application = create_app()
    with application.app_context():
        orchestrator = PipelineOrchestrator()
        result = orchestrator.run(profile_uuid)
        return result
