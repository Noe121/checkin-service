-- Admin Dashboard Service - Database Schema
-- Tables for admin dashboard, audit logging, alerts, reports, and metrics

-- Admin Audit Log Table
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    admin_id INT NOT NULL,
    action VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INT NULL,
    changes JSON NULL,
    ip_address VARCHAR(45) NULL,
    reason TEXT NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_admin_id (admin_id),
    INDEX idx_action (action),
    INDEX idx_entity_type (entity_type),
    INDEX idx_created_at (created_at),
    INDEX idx_is_deleted (is_deleted)
);

-- System Alert Table
CREATE TABLE IF NOT EXISTS system_alert (
    id INT PRIMARY KEY AUTO_INCREMENT,
    alert_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    severity ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL') DEFAULT 'MEDIUM',
    source VARCHAR(100) NULL,
    details JSON NULL,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP NULL,
    resolved_by INT NULL,
    resolution_notes TEXT NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_is_resolved (is_resolved),
    INDEX idx_severity (severity),
    INDEX idx_created_at (created_at),
    INDEX idx_is_deleted (is_deleted)
);

-- Report Schedule Table
CREATE TABLE IF NOT EXISTS report_schedule (
    id INT PRIMARY KEY AUTO_INCREMENT,
    admin_id INT NOT NULL,
    report_type VARCHAR(50) NOT NULL,
    frequency VARCHAR(20) NOT NULL,
    email_recipients JSON NULL,
    include_details BOOLEAN DEFAULT TRUE,
    last_generated_at TIMESTAMP NULL,
    next_scheduled_at TIMESTAMP NULL,
    is_active BOOLEAN DEFAULT TRUE,
    parameters JSON NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_admin_id (admin_id),
    INDEX idx_report_type (report_type),
    INDEX idx_is_active (is_active),
    INDEX idx_is_deleted (is_deleted)
);

-- Dashboard Metric Table
CREATE TABLE IF NOT EXISTS dashboard_metric (
    id INT PRIMARY KEY AUTO_INCREMENT,
    metric_type VARCHAR(50) NOT NULL,
    current_value DECIMAL(15, 2) NOT NULL,
    previous_value DECIMAL(15, 2) NULL,
    change_percent DECIMAL(10, 2) NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    description TEXT NULL,
    is_cache_valid BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_metric_type (metric_type),
    INDEX idx_period_start (period_start),
    INDEX idx_created_at (created_at)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_audit_log_admin_action ON admin_audit_log (admin_id, action);
CREATE INDEX IF NOT EXISTS idx_alert_severity_resolved ON system_alert (severity, is_resolved);
CREATE INDEX IF NOT EXISTS idx_report_schedule_active ON report_schedule (is_active, frequency);
CREATE INDEX IF NOT EXISTS idx_metric_type_period ON dashboard_metric (metric_type, period_start);
