"""
Admin Dashboard Service Logic
Business logic for admin dashboard operations
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func

from models import AdminAuditLog, SystemAlert, ReportSchedule, DashboardMetric, SeverityEnum
from soft_delete import soft_delete_filter


class AdminService:
    """Service for admin dashboard operations"""

    def __init__(self, db: Session):
        """Initialize admin service"""
        self.db = db

    # ===== Audit Log Methods =====

    def log_action(
        self,
        admin_id: int,
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        changes: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> AdminAuditLog:
        """Log an admin action to audit trail"""
        audit_log = AdminAuditLog(
            admin_id=admin_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            ip_address=ip_address,
            reason=reason,
        )
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)
        return audit_log

    def get_audit_logs(
        self, skip: int = 0, limit: int = 100, filters: Optional[Dict[str, Any]] = None
    ) -> List[AdminAuditLog]:
        """Get audit logs with optional filters"""
        query = self.db.query(AdminAuditLog).filter(soft_delete_filter(AdminAuditLog))

        if filters:
            if "admin_id" in filters:
                query = query.filter(AdminAuditLog.admin_id == filters["admin_id"])
            if "action" in filters:
                query = query.filter(AdminAuditLog.action == filters["action"])
            if "entity_type" in filters:
                query = query.filter(AdminAuditLog.entity_type == filters["entity_type"])
            if "date_from" in filters:
                query = query.filter(AdminAuditLog.created_at >= filters["date_from"])
            if "date_to" in filters:
                query = query.filter(AdminAuditLog.created_at <= filters["date_to"])

        return query.order_by(AdminAuditLog.created_at.desc()).offset(skip).limit(limit).all()  # type: ignore

    def get_audit_log_count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Get total count of audit logs"""
        query = self.db.query(func.count(AdminAuditLog.id)).filter(
            soft_delete_filter(AdminAuditLog)
        )

        if filters:
            if "admin_id" in filters:
                query = query.filter(AdminAuditLog.admin_id == filters["admin_id"])
            if "action" in filters:
                query = query.filter(AdminAuditLog.action == filters["action"])

        return query.scalar() or 0  # type: ignore

    # ===== System Alert Methods =====

    def create_alert(
        self,
        alert_type: str,
        message: str,
        severity: SeverityEnum = SeverityEnum.MEDIUM,
        source: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> SystemAlert:
        """Create a new system alert"""
        alert = SystemAlert(
            alert_type=alert_type,
            message=message,
            severity=severity,
            source=source,
            details=details,
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def get_active_alerts(self, limit: int = 50) -> List[SystemAlert]:
        """Get all unresolved alerts"""
        return (
            self.db.query(SystemAlert)
            .filter(soft_delete_filter(SystemAlert))
            .filter(SystemAlert.is_resolved == False)  # type: ignore
            .order_by(SystemAlert.severity, SystemAlert.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_alerts(
        self, skip: int = 0, limit: int = 100, only_unresolved: bool = False
    ) -> List[SystemAlert]:
        """Get system alerts with pagination"""
        query = self.db.query(SystemAlert).filter(soft_delete_filter(SystemAlert))

        if only_unresolved:
            query = query.filter(SystemAlert.is_resolved == False)  # type: ignore

        return (
            query.order_by(SystemAlert.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def resolve_alert(
        self,
        alert_id: int,
        admin_id: int,
        resolution_notes: Optional[str] = None,
    ) -> Optional[SystemAlert]:
        """Resolve a system alert"""
        alert = self.db.query(SystemAlert).filter(SystemAlert.id == alert_id).first()
        if not alert:
            return None

        alert.is_resolved = True  # type: ignore
        alert.resolved_at = datetime.utcnow()  # type: ignore
        alert.resolved_by = admin_id  # type: ignore
        alert.resolution_notes = resolution_notes  # type: ignore

        self.db.commit()
        self.db.refresh(alert)
        return alert

    def get_alert_count(self, only_unresolved: bool = False) -> int:
        """Get total alert count"""
        query = self.db.query(func.count(SystemAlert.id)).filter(
            soft_delete_filter(SystemAlert)
        )

        if only_unresolved:
            query = query.filter(SystemAlert.is_resolved == False)  # type: ignore

        return query.scalar() or 0  # type: ignore

    # ===== Report Schedule Methods =====

    def create_report_schedule(
        self,
        admin_id: int,
        report_type: str,
        frequency: str,
        email_recipients: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> ReportSchedule:
        """Create a scheduled report"""
        schedule = ReportSchedule(
            admin_id=admin_id,
            report_type=report_type,
            frequency=frequency,
            email_recipients=email_recipients,
            parameters=parameters,
        )
        self.db.add(schedule)
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def get_active_schedules(self) -> List[ReportSchedule]:
        """Get all active report schedules"""
        return (
            self.db.query(ReportSchedule)
            .filter(soft_delete_filter(ReportSchedule))
            .filter(ReportSchedule.is_active == True)  # type: ignore
            .all()
        )

    def update_report_schedule(
        self, schedule_id: int, **kwargs: Any
    ) -> Optional[ReportSchedule]:
        """Update a report schedule"""
        schedule = self.db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()
        if not schedule:
            return None

        for key, value in kwargs.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)

        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    # ===== Dashboard Metrics Methods =====

    def create_metric(
        self,
        metric_type: str,
        current_value: Decimal,
        period_start: datetime,
        period_end: datetime,
        previous_value: Optional[Decimal] = None,
        description: Optional[str] = None,
    ) -> DashboardMetric:
        """Create a dashboard metric"""
        change_percent = None
        if previous_value and previous_value != 0:
            change_percent = Decimal(
                ((current_value - previous_value) / previous_value) * 100
            )

        metric = DashboardMetric(
            metric_type=metric_type,
            current_value=current_value,
            previous_value=previous_value,
            change_percent=change_percent,
            period_start=period_start,
            period_end=period_end,
            description=description,
        )
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def get_metrics_by_type(self, metric_type: str, limit: int = 1) -> List[DashboardMetric]:
        """Get recent metrics of a specific type"""
        return (
            self.db.query(DashboardMetric)
            .filter(DashboardMetric.metric_type == metric_type)
            .order_by(DashboardMetric.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_latest_metric(self, metric_type: str) -> Optional[DashboardMetric]:
        """Get the latest metric of a specific type"""
        return (
            self.db.query(DashboardMetric)
            .filter(DashboardMetric.metric_type == metric_type)
            .order_by(DashboardMetric.created_at.desc())
            .first()
        )

    def invalidate_metrics(self, metric_type: Optional[str] = None) -> int:
        """Invalidate metrics cache"""
        query = self.db.query(DashboardMetric)

        if metric_type:
            query = query.filter(DashboardMetric.metric_type == metric_type)

        count = query.update({"is_cache_valid": False})  # type: ignore
        self.db.commit()
        return count

    # ===== Dashboard Summary =====

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get overall dashboard summary"""
        return {
            "active_alerts": self.get_alert_count(only_unresolved=True),
            "total_audit_logs": self.get_audit_log_count(),
            "active_report_schedules": len(self.get_active_schedules()),
            "timestamp": datetime.utcnow().isoformat(),
        }
