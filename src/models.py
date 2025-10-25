"""
Admin Dashboard Service Models
SQLAlchemy models for admin dashboard with soft delete pattern
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, Text, Enum, DECIMAL, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from decimal import Decimal
import enum

Base = declarative_base()


class AdminAuditLog(Base):
    """Admin audit log for tracking administrative actions"""
    __tablename__ = "admin_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, nullable=False, index=True)
    action = Column(String(255), nullable=False)
    entity_type = Column(String(50), nullable=False)  # 'deal', 'user', 'payment', etc.
    entity_id = Column(Integer, nullable=True)
    changes = Column(JSON, nullable=True)  # JSON of before/after values
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    reason = Column(Text, nullable=True)  # Why the action was taken
    
    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """Convert to dictionary"""
        created_at_value = self.created_at  # type: ignore
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "changes": self.changes,
            "ip_address": self.ip_address,
            "reason": self.reason,
            "created_at": created_at_value.isoformat() if created_at_value is not None else None,
            "is_deleted": self.is_deleted,
        }


class SeverityEnum(str, enum.Enum):
    """Alert severity levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SystemAlert(Base):
    """System alerts for monitoring platform health"""
    __tablename__ = "system_alert"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String(50), nullable=False)  # 'error', 'warning', 'info', 'critical'
    message = Column(Text, nullable=False)
    severity = Column(Enum(SeverityEnum), default=SeverityEnum.MEDIUM, nullable=False)
    
    # Details
    source = Column(String(100), nullable=True)  # Which service raised alert
    details = Column(JSON, nullable=True)  # Additional context
    
    # Resolution tracking
    is_resolved = Column(Boolean, default=False, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, nullable=True)  # admin_id
    resolution_notes = Column(Text, nullable=True)
    
    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """Convert to dictionary"""
        resolved_at_value = self.resolved_at  # type: ignore
        created_at_value = self.created_at  # type: ignore
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "message": self.message,
            "severity": self.severity.value,
            "source": self.source,
            "details": self.details,
            "is_resolved": self.is_resolved,
            "resolved_at": resolved_at_value.isoformat() if resolved_at_value is not None else None,
            "created_at": created_at_value.isoformat() if created_at_value is not None else None,
        }


class ReportSchedule(Base):
    """Scheduled reports for automated generation"""
    __tablename__ = "report_schedule"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, nullable=False, index=True)
    report_type = Column(String(50), nullable=False)  # 'financial', 'compliance', 'performance', etc.
    frequency = Column(String(20), nullable=False)  # 'daily', 'weekly', 'monthly'
    
    # Delivery
    email_recipients = Column(JSON, nullable=True)  # List of email addresses
    include_details = Column(Boolean, default=True)  # Include detailed breakdown
    
    # Schedule tracking
    last_generated_at = Column(DateTime, nullable=True)
    next_scheduled_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Configuration
    parameters = Column(JSON, nullable=True)  # Report-specific parameters
    
    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """Convert to dictionary"""
        last_generated_value = self.last_generated_at  # type: ignore
        next_scheduled_value = self.next_scheduled_at  # type: ignore
        created_at_value = self.created_at  # type: ignore
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "report_type": self.report_type,
            "frequency": self.frequency,
            "email_recipients": self.email_recipients,
            "is_active": self.is_active,
            "last_generated_at": last_generated_value.isoformat() if last_generated_value is not None else None,
            "next_scheduled_at": next_scheduled_value.isoformat() if next_scheduled_value is not None else None,
            "created_at": created_at_value.isoformat() if created_at_value is not None else None,
        }


class DashboardMetric(Base):
    """Cached dashboard metrics for performance"""
    __tablename__ = "dashboard_metric"

    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(String(50), nullable=False, index=True)  # 'users', 'deals', 'revenue', etc.
    
    # Values
    current_value = Column(DECIMAL(15, 2), nullable=False)
    previous_value = Column(DECIMAL(15, 2), nullable=True)
    change_percent = Column(DECIMAL(10, 2), nullable=True)
    
    # Time period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    
    # Metadata
    description = Column(Text, nullable=True)
    is_cache_valid = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """Convert to dictionary"""
        current_val = self.current_value  # type: ignore
        previous_val = self.previous_value  # type: ignore
        change_val = self.change_percent  # type: ignore
        period_start_value = self.period_start  # type: ignore
        period_end_value = self.period_end  # type: ignore
        return {
            "id": self.id,
            "metric_type": self.metric_type,
            "current_value": float(current_val) if current_val is not None else 0,
            "previous_value": float(previous_val) if previous_val is not None else 0,
            "change_percent": float(change_val) if change_val is not None else 0,
            "period_start": period_start_value.isoformat() if period_start_value is not None else None,
            "period_end": period_end_value.isoformat() if period_end_value is not None else None,
            "is_valid": self.is_valid,
        }
