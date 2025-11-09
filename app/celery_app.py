"""
Celery application configuration for async task processing

Note: Full Celery setup and worker configuration is part of Phase 5.
This file provides the structure for KYC and role processing tasks.
"""

from celery import Celery
from decouple import config

# Redis URL for Celery broker and result backend
redis_url = config("REDIS_URL", default="redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "real_estate_app",
    broker=redis_url,
    backend=redis_url,
    include=["app.tasks.kyc_tasks", "app.tasks.role_tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

