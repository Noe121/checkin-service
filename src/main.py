"""
Admin Dashboard Service - Main FastAPI Application
Centralized administration interface for platform management
"""
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Header, Query, Depends, Body
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from models import Base, AdminAuditLog, SystemAlert, ReportSchedule, DashboardMetric, SeverityEnum
from admin_service import AdminService
from soft_delete import soft_delete_filter

# ===== FastAPI Setup =====

app = FastAPI(
    title="Admin Dashboard Service",
    description="Centralized administration interface for platform management",
    version="1.0.0"
)

# ===== Database Configuration =====

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/nilbx_admin"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# Create tables
Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===== Health Check =====

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "admin-dashboard-service",
        "timestamp": datetime.utcnow().isoformat(),
        "feature_flags": {
            "audit_logging": True,
            "alert_management": True,
            "report_scheduling": True,
            "metrics_tracking": True,
        }
    }


# ===== Dashboard Endpoints =====

@app.get("/admin/dashboard")
def get_dashboard_overview(
    admin_id: int = Header(...),
    db: Session = Depends(get_db)
):
    """Get dashboard overview with key metrics"""
    service = AdminService(db)
    summary = service.get_dashboard_summary()

    # Get latest metrics
    metrics = {}
    for metric_type in ["users", "deals", "revenue", "disputes"]:
        latest = service.get_latest_metric(metric_type)
        if latest:
            metrics[metric_type] = latest.to_dict()

    return {
        "summary": summary,
        "metrics": metrics,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ===== Audit Log Endpoints =====

@app.get("/admin/audit-logs")
def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    admin_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get audit logs with filtering"""
    service = AdminService(db)
    
    filters = {}
    if admin_id:
        filters["admin_id"] = admin_id
    if action:
        filters["action"] = action
    if entity_type:
        filters["entity_type"] = entity_type

    logs = service.get_audit_logs(skip=skip, limit=limit, filters=filters)
    total = service.get_audit_log_count(filters=filters)

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [log.to_dict() for log in logs],
    }


@app.post("/admin/audit-logs")
def create_audit_log(
    admin_id: int = Header(...),
    action: str = Body(...),
    entity_type: str = Body(...),
    entity_id: Optional[int] = Body(None),
    changes: Optional[Dict[str, Any]] = Body(None),
    reason: Optional[str] = Body(None),
    db: Session = Depends(get_db)
):
    """Create new audit log entry"""
    service = AdminService(db)
    
    log = service.log_action(
        admin_id=admin_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        reason=reason,
    )

    return {
        "id": log.id,
        "message": "Audit log created successfully",
        "audit_log": log.to_dict(),
    }


# ===== System Alert Endpoints =====

@app.get("/admin/alerts")
def get_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    only_unresolved: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Get system alerts"""
    service = AdminService(db)
    
    alerts = service.get_alerts(skip=skip, limit=limit, only_unresolved=only_unresolved)
    total = service.get_alert_count(only_unresolved=only_unresolved)

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [alert.to_dict() for alert in alerts],
    }


@app.get("/admin/alerts/active")
def get_active_alerts(db: Session = Depends(get_db)):
    """Get active/unresolved alerts"""
    service = AdminService(db)
    alerts = service.get_active_alerts(limit=50)
    
    return {
        "total": len(alerts),
        "items": [alert.to_dict() for alert in alerts],
    }


@app.post("/admin/alerts")
def create_alert(
    alert_type: str = Body(...),
    message: str = Body(...),
    severity: str = Body("MEDIUM"),
    source: Optional[str] = Body(None),
    details: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db)
):
    """Create a new system alert"""
    service = AdminService(db)
    
    try:
        severity_enum = SeverityEnum(severity)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

    alert = service.create_alert(
        alert_type=alert_type,
        message=message,
        severity=severity_enum,
        source=source,
        details=details,
    )

    return {
        "id": alert.id,
        "message": "Alert created successfully",
        "alert": alert.to_dict(),
    }


@app.put("/admin/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    admin_id: int = Header(...),
    resolution_notes: Optional[str] = Body(None),
    db: Session = Depends(get_db)
):
    """Resolve a system alert"""
    service = AdminService(db)
    
    alert = service.resolve_alert(
        alert_id=alert_id,
        admin_id=admin_id,
        resolution_notes=resolution_notes,
    )

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        "id": alert.id,
        "message": "Alert resolved successfully",
        "alert": alert.to_dict(),
    }


# ===== Report Schedule Endpoints =====

@app.get("/admin/reports/schedules")
def get_report_schedules(db: Session = Depends(get_db)):
    """Get all active report schedules"""
    service = AdminService(db)
    schedules = service.get_active_schedules()

    return {
        "total": len(schedules),
        "items": [schedule.to_dict() for schedule in schedules],
    }


@app.post("/admin/reports/schedules")
def create_report_schedule(
    admin_id: int = Header(...),
    report_type: str = Body(...),
    frequency: str = Body(...),
    email_recipients: Optional[List[str]] = Body(None),
    parameters: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db)
):
    """Create a new report schedule"""
    service = AdminService(db)
    
    schedule = service.create_report_schedule(
        admin_id=admin_id,
        report_type=report_type,
        frequency=frequency,
        email_recipients=email_recipients,
        parameters=parameters,
    )

    return {
        "id": schedule.id,
        "message": "Report schedule created successfully",
        "schedule": schedule.to_dict(),
    }


@app.put("/admin/reports/schedules/{schedule_id}")
def update_report_schedule(
    schedule_id: int,
    is_active: Optional[bool] = Body(None),
    frequency: Optional[str] = Body(None),
    email_recipients: Optional[List[str]] = Body(None),
    db: Session = Depends(get_db)
):
    """Update a report schedule"""
    service = AdminService(db)
    
    updates = {}
    if is_active is not None:
        updates["is_active"] = is_active
    if frequency is not None:
        updates["frequency"] = frequency
    if email_recipients is not None:
        updates["email_recipients"] = email_recipients

    schedule = service.update_report_schedule(schedule_id, **updates)

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return {
        "id": schedule.id,
        "message": "Schedule updated successfully",
        "schedule": schedule.to_dict(),
    }


# ===== Dashboard Metrics Endpoints =====

@app.get("/admin/metrics/{metric_type}")
def get_metric(
    metric_type: str,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get metrics of a specific type"""
    service = AdminService(db)
    metrics = service.get_metrics_by_type(metric_type, limit=limit)

    return {
        "metric_type": metric_type,
        "total": len(metrics),
        "items": [metric.to_dict() for metric in metrics],
    }


@app.post("/admin/metrics")
def create_metric(
    metric_type: str = Body(...),
    current_value: float = Body(...),
    period_start: str = Body(...),
    period_end: str = Body(...),
    previous_value: Optional[float] = Body(None),
    description: Optional[str] = Body(None),
    db: Session = Depends(get_db)
):
    """Create a dashboard metric"""
    service = AdminService(db)
    
    try:
        period_start_dt = datetime.fromisoformat(period_start)
        period_end_dt = datetime.fromisoformat(period_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")

    metric = service.create_metric(
        metric_type=metric_type,
        current_value=Decimal(str(current_value)),
        period_start=period_start_dt,
        period_end=period_end_dt,
        previous_value=Decimal(str(previous_value)) if previous_value else None,
        description=description,
    )

    return {
        "id": metric.id,
        "message": "Metric created successfully",
        "metric": metric.to_dict(),
    }


@app.post("/admin/metrics/invalidate")
def invalidate_metrics(
    metric_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Invalidate metrics cache"""
    service = AdminService(db)
    count = service.invalidate_metrics(metric_type)

    return {
        "message": "Metrics invalidated successfully",
        "count": count,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)