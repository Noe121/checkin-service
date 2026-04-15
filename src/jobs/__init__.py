"""Scheduled / housekeeping jobs for checkin-service.

These functions are meant to be invoked by an external scheduler (cron,
celery-beat, ECS scheduled task, etc.). The module itself does NOT wire
a runner — deployment is the environment's concern.
"""
