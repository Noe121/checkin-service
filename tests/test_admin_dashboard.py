"""
Admin Dashboard Service - Comprehensive Test Suite
Tests for admin dashboard features: audit logging, alerts, reports, metrics
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from src.models import (
        Base, AdminAuditLog, SystemAlert, ReportSchedule, 
        DashboardMetric, SeverityEnum
    )
    from src.admin_service import AdminService
except ImportError:
    # Fallback for type checking
    from ..src.models import (  # type: ignore[import-not-found]
        Base, AdminAuditLog, SystemAlert, ReportSchedule, 
        DashboardMetric, SeverityEnum
    )
    from ..src.admin_service import AdminService  # type: ignore[import-not-found]


# Type ignore for SQLAlchemy ORM assertions
# Pylance struggles with SQLAlchemy Column types in assert statements
# These are safe to ignore as they are testing ORM objects


# ===== Database Setup =====

@pytest.fixture(scope="session")
def db_engine():
    """Create in-memory SQLite database for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Get database session"""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


# ===== Audit Log Tests =====

class TestAuditLogs:
    """Test audit logging functionality"""

    def test_log_user_action(self, db_session: Session):
        """Test logging a user action"""
        service = AdminService(db_session)
        
        log = service.log_action(
            admin_id=1,
            action="SUSPEND_DEAL",
            entity_type="deal",
            entity_id=100,
            changes={"status": {"old": "ACTIVE", "new": "SUSPENDED"}},
            reason="Suspicious activity detected"
        )

        assert log.id is not None
        assert getattr(log, "admin_id", None) == 1
        assert getattr(log, "action", None) == "SUSPEND_DEAL"
        assert getattr(log, "entity_type", None) == "deal"
        assert getattr(log, "entity_id", None) == 100
        assert getattr(log, "reason", None) == "Suspicious activity detected"
        assert getattr(log, "is_deleted", False) is False  # type: ignore[reportGeneralTypeIssues]

    def test_get_audit_logs(self, db_session: Session):
        """Test retrieving audit logs"""
        service = AdminService(db_session)
        
        # Create multiple logs
        service.log_action(1, "CREATE_DEAL", "deal", 1)
        service.log_action(1, "SUSPEND_DEAL", "deal", 1)
        service.log_action(2, "UPDATE_USER", "user", 10)

        logs = service.get_audit_logs(skip=0, limit=100)
        assert len(logs) == 3

    def test_get_audit_logs_with_filters(self, db_session: Session):
        """Test filtering audit logs"""
        service = AdminService(db_session)
        
        service.log_action(1, "CREATE_DEAL", "deal", 1)
        service.log_action(1, "SUSPEND_DEAL", "deal", 2)
        service.log_action(2, "UPDATE_USER", "user", 10)

        # Filter by admin_id
        logs = service.get_audit_logs(filters={"admin_id": 1})
        assert len(logs) == 2

        # Filter by action
        logs = service.get_audit_logs(filters={"action": "CREATE_DEAL"})
        assert len(logs) == 1

        # Filter by entity_type
        logs = service.get_audit_logs(filters={"entity_type": "user"})
        assert len(logs) == 1

    def test_get_audit_log_count(self, db_session: Session):
        """Test counting audit logs"""
        service = AdminService(db_session)
        
        service.log_action(1, "CREATE_DEAL", "deal", 1)
        service.log_action(1, "SUSPEND_DEAL", "deal", 2)
        service.log_action(2, "UPDATE_USER", "user", 10)

        total = service.get_audit_log_count()
        assert total == 3

        # Count with filter
        count = service.get_audit_log_count(filters={"admin_id": 1})
        assert count == 2

    def test_audit_log_pagination(self, db_session: Session):
        """Test pagination of audit logs"""
        service = AdminService(db_session)
        
        for i in range(10):
            service.log_action(1, "ACTION", "deal", i)

        # Get first page
        logs = service.get_audit_logs(skip=0, limit=5)
        assert len(logs) == 5

        # Get second page
        logs = service.get_audit_logs(skip=5, limit=5)
        assert len(logs) == 5


# ===== System Alert Tests =====

class TestSystemAlerts:
    """Test system alert functionality"""

    def test_create_alert(self, db_session: Session):
        """Test creating a system alert"""
        service = AdminService(db_session)
        
        alert = service.create_alert(
            alert_type="error",
            message="Database connection failed",
            severity=SeverityEnum.CRITICAL,
            source="payment-service",
            details={"error_code": "DB_CONNECTION_FAILED"}
        )

        assert alert.id is not None
        assert getattr(alert, "alert_type", None) == "error"
        assert getattr(alert, "message", None) == "Database connection failed"
        assert getattr(alert, "severity", None) == SeverityEnum.CRITICAL
        assert getattr(alert, "is_resolved", False) is False  # type: ignore[reportGeneralTypeIssues]

    def test_get_active_alerts(self, db_session: Session):
        """Test getting active/unresolved alerts"""
        service = AdminService(db_session)
        
        # Create resolved alert
        alert1 = service.create_alert("info", "Test message 1", SeverityEnum.LOW)
        service.resolve_alert(alert1.id, admin_id=1)  # type: ignore[reportArgumentType]

        # Create unresolved alerts
        alert2 = service.create_alert("error", "Test message 2", SeverityEnum.HIGH)
        alert3 = service.create_alert("warning", "Test message 3", SeverityEnum.MEDIUM)

        active_alerts = service.get_active_alerts()
        assert len(active_alerts) == 2

    def test_get_alerts_with_filter(self, db_session: Session):
        """Test filtering alerts"""
        service = AdminService(db_session)
        
        service.create_alert("error", "Error 1", SeverityEnum.CRITICAL)
        service.create_alert("warning", "Warning 1", SeverityEnum.MEDIUM)
        service.create_alert("info", "Info 1", SeverityEnum.LOW)

        # Get only unresolved
        alerts = service.get_alerts(only_unresolved=True)
        assert len(alerts) == 3

    def test_resolve_alert(self, db_session: Session):
        """Test resolving an alert"""
        service = AdminService(db_session)
        
        alert = service.create_alert("error", "Test error", SeverityEnum.HIGH)
        assert alert.is_resolved is False  # type: ignore[reportGeneralTypeIssues]

        resolved = service.resolve_alert(
            alert.id,  # type: ignore[reportArgumentType]
            admin_id=5,
            resolution_notes="Fixed the issue"
        )

    assert resolved is not None  # type: ignore[reportGeneralTypeIssues]
    assert getattr(resolved, "is_resolved", False) is True  # type: ignore[reportGeneralTypeIssues]
    assert getattr(resolved, "resolved_by", None) == 5  # type: ignore[reportOptionalMemberAccess]
    assert getattr(resolved, "resolution_notes", None) == "Fixed the issue"  # type: ignore[reportOptionalMemberAccess,reportGeneralTypeIssues]

    def test_alert_count_by_type(self, db_session: Session):
        """Test counting alerts"""
        service = AdminService(db_session)
        
        service.create_alert("error", "Error 1", SeverityEnum.CRITICAL)
        service.create_alert("warning", "Warning 1", SeverityEnum.MEDIUM)
        service.create_alert("info", "Info 1", SeverityEnum.LOW)

        total = service.get_alert_count()
        assert total == 3

        unresolved = service.get_alert_count(only_unresolved=True)
        assert unresolved == 3


# ===== Report Schedule Tests =====

class TestReportSchedules:
    """Test report schedule functionality"""

    def test_create_report_schedule(self, db_session: Session):
        """Test creating a report schedule"""
        service = AdminService(db_session)
        
        schedule = service.create_report_schedule(
            admin_id=1,
            report_type="financial",
            frequency="daily",
            email_recipients=["admin@example.com", "finance@example.com"],
            parameters={"include_details": True}
        )

        assert schedule.id is not None
        assert schedule.admin_id == 1  # type: ignore
        assert schedule.report_type == "financial"  # type: ignore
        assert schedule.frequency == "daily"  # type: ignore
    assert getattr(schedule, "is_active", False) is True  # type: ignore

    def test_get_active_schedules(self, db_session: Session):
        """Test getting active schedules"""
        service = AdminService(db_session)
        
        # Create active schedules
        schedule1 = service.create_report_schedule(1, "financial", "daily")
        schedule2 = service.create_report_schedule(1, "compliance", "weekly")

        # Create inactive schedule
        schedule3 = service.create_report_schedule(1, "performance", "monthly")
        service.update_report_schedule(schedule3.id, is_active=False)  # type: ignore

        active = service.get_active_schedules()
        assert len(active) == 2

    def test_update_report_schedule(self, db_session: Session):
        """Test updating a report schedule"""
        service = AdminService(db_session)
        
        schedule = service.create_report_schedule(
            1, "financial", "daily",
            email_recipients=["admin@example.com"]
        )

        updated = service.update_report_schedule(
            schedule.id,  # type: ignore
            frequency="weekly",
            email_recipients=["admin@example.com", "finance@example.com"]
        )

        assert updated is not None  # type: ignore
        assert updated.frequency == "weekly"  # type: ignore
        assert len(updated.email_recipients or []) == 2  # type: ignore

    def test_deactivate_schedule(self, db_session: Session):
        """Test deactivating a report schedule"""
        service = AdminService(db_session)
        
        schedule = service.create_report_schedule(1, "financial", "daily")
        assert schedule.is_active is True  # type: ignore

        updated = service.update_report_schedule(schedule.id, is_active=False)  # type: ignore
        assert updated is not None  # type: ignore
    assert getattr(updated, "is_active", True) is False  # type: ignore


# ===== Dashboard Metrics Tests =====

class TestDashboardMetrics:
    """Test dashboard metrics functionality"""

    def test_create_metric(self, db_session: Session):
        """Test creating a metric"""
        service = AdminService(db_session)
        
        start = datetime.utcnow() - timedelta(days=1)
        end = datetime.utcnow()

        metric = service.create_metric(
            metric_type="users",
            current_value=Decimal("1500"),
            period_start=start,
            period_end=end,
            previous_value=Decimal("1400"),
            description="Active users"
        )

        assert metric.id is not None
    assert getattr(metric, "metric_type", None) == "users"  # type: ignore
    assert getattr(metric, "current_value", None) == Decimal("1500")  # type: ignore
    assert getattr(metric, "change_percent", None) == Decimal("7.14")  # type: ignore  # (1500-1400)/1400*100

    def test_get_metrics_by_type(self, db_session: Session):
        """Test retrieving metrics by type"""
        service = AdminService(db_session)
        
        start = datetime.utcnow()
        end = start + timedelta(hours=1)

        # Create multiple metrics
        service.create_metric("users", Decimal("1000"), start, end)
        service.create_metric("users", Decimal("1100"), start, end)
        service.create_metric("deals", Decimal("500"), start, end)

        users_metrics = service.get_metrics_by_type("users", limit=10)
        assert len(users_metrics) == 2
        
        deals_metrics = service.get_metrics_by_type("deals")
        assert len(deals_metrics) == 1

    def test_get_latest_metric(self, db_session: Session):
        """Test getting the latest metric of a type"""
        service = AdminService(db_session)
        
        start = datetime.utcnow()
        end = start + timedelta(hours=1)

        metric1 = service.create_metric("revenue", Decimal("5000"), start, end)
        metric2 = service.create_metric("revenue", Decimal("5500"), start, end)

        latest = service.get_latest_metric("revenue")
        assert latest is not None  # type: ignore
        assert getattr(latest, "id", None) == getattr(metric2, "id", None)  # type: ignore
        assert getattr(latest, "current_value", None) == Decimal("5500")  # type: ignore

    def test_invalidate_metrics(self, db_session: Session):
        """Test invalidating metrics cache"""
        service = AdminService(db_session)
        
        start = datetime.utcnow()
        end = start + timedelta(hours=1)

        service.create_metric("users", Decimal("1000"), start, end)
        service.create_metric("deals", Decimal("500"), start, end)

        # Invalidate all metrics
        count = service.invalidate_metrics()
        assert count == 2

        # Invalidate specific type
        count = service.invalidate_metrics("users")
        assert count >= 1


# ===== Dashboard Summary Tests =====

class TestDashboardSummary:
    """Test dashboard summary functionality"""

    def test_get_dashboard_summary(self, db_session: Session):
        """Test getting dashboard summary"""
        service = AdminService(db_session)
        
        # Create some data
        service.log_action(1, "CREATE_DEAL", "deal", 1)
        service.create_alert("error", "Test error", SeverityEnum.HIGH)
        service.create_report_schedule(1, "financial", "daily")

        summary = service.get_dashboard_summary()
        assert "active_alerts" in summary
        assert "total_audit_logs" in summary
        assert "active_report_schedules" in summary
        assert "timestamp" in summary
        assert summary["active_alerts"] > 0
        assert summary["total_audit_logs"] > 0
        assert summary["active_report_schedules"] > 0


# ===== Integration Tests =====

class TestIntegration:
    """Integration tests for admin dashboard"""

    def test_full_admin_workflow(self, db_session: Session):
        """Test complete admin workflow"""
        service = AdminService(db_session)
        
        # 1. Create audit log for deal suspension
        log = service.log_action(
            admin_id=1,
            action="SUSPEND_DEAL",
            entity_type="deal",
            entity_id=100,
            reason="Suspicious activity"
        )
        assert log.id is not None

        # 2. Create alert for the event
        alert = service.create_alert(
            alert_type="warning",
            message=f"Deal {100} suspended by admin",
            severity=SeverityEnum.HIGH,
            source="admin-dashboard"
        )
        assert getattr(alert, "is_resolved", False) is False

        # 3. Resolve the alert
        resolved = service.resolve_alert(alert.id, admin_id=1, resolution_notes="Approved")  # type: ignore
        assert resolved is not None  # type: ignore
        assert getattr(resolved, "is_resolved", False) is True  # type: ignore

        # 4. Create report schedule
        schedule = service.create_report_schedule(
            admin_id=1,
            report_type="compliance",
            frequency="weekly"
        )
        assert getattr(schedule, "is_active", False) is True

        # 5. Verify dashboard summary
        summary = service.get_dashboard_summary()
        assert summary["total_audit_logs"] == 1
        assert summary["active_report_schedules"] == 1

    def test_soft_delete_pattern(self, db_session: Session):
        """Test soft delete pattern with audit logs"""
        service = AdminService(db_session)
        
        log = service.log_action(1, "TEST_ACTION", "deal", 1)
        log_id = log.id

        # Manually soft delete
        log.is_deleted = True  # type: ignore
        log.deleted_at = datetime.utcnow()  # type: ignore
        db_session.commit()

        # Query should exclude deleted
        logs = service.get_audit_logs()
        assert len(logs) == 0

        # Query with all_including_deleted should find it
        all_logs = db_session.query(AdminAuditLog).all()
        assert len(all_logs) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
