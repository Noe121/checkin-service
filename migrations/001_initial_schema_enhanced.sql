-- NILBX Admin Dashboard Service Database Schema
-- Database: admin_db (Port 3322) - LOCAL DEVELOPMENT ONLY
-- Cloud/Production: Uses nilbx_db (shared database)
-- Purpose: Admin dashboard, audit logging, alerts, reports, and metrics

-- Enable foreign key checks
SET FOREIGN_KEY_CHECKS = 1;

-- Create the database if it doesn't exist
CREATE DATABASE IF NOT EXISTS admin_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE admin_db;

-- Create user with access from any host (for Docker containers)
CREATE USER IF NOT EXISTS 'adminuser'@'%' IDENTIFIED BY 'adminpass';
GRANT ALL PRIVILEGES ON admin_db.* TO 'adminuser'@'%';
FLUSH PRIVILEGES;

-- ====================================
-- Admin Audit Log Table
-- Comprehensive audit trail for all admin actions
-- ====================================
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    admin_id INT NOT NULL,
    admin_email VARCHAR(255),
    action VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id INT NULL,
    changes JSON NULL,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(500),
    reason TEXT NULL,
    status VARCHAR(20) DEFAULT 'success',
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_admin_id (admin_id),
    INDEX idx_action (action),
    INDEX idx_entity_type (entity_type),
    INDEX idx_entity (entity_type, entity_id),
    INDEX idx_created_at (created_at),
    INDEX idx_status (status),
    INDEX idx_is_deleted (is_deleted),
    INDEX idx_admin_action (admin_id, action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Admin audit trail - 7-year retention required';

-- ====================================
-- System Alert Table
-- Critical system alerts and monitoring
-- ====================================
CREATE TABLE IF NOT EXISTS system_alert (
    id INT PRIMARY KEY AUTO_INCREMENT,
    alert_type VARCHAR(50) NOT NULL,
    alert_category ENUM('security', 'performance', 'compliance', 'system', 'business') DEFAULT 'system',
    message TEXT NOT NULL,
    severity ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL') DEFAULT 'MEDIUM',
    source VARCHAR(100) NULL,
    details JSON NULL,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at DATETIME NULL,
    resolved_by INT NULL,
    resolution_notes TEXT NULL,
    notification_sent BOOLEAN DEFAULT FALSE,
    notification_sent_at DATETIME NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_is_resolved (is_resolved),
    INDEX idx_severity (severity),
    INDEX idx_alert_category (alert_category),
    INDEX idx_created_at (created_at),
    INDEX idx_is_deleted (is_deleted),
    INDEX idx_severity_resolved (severity, is_resolved)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='System alerts and monitoring';

-- ====================================
-- Report Schedule Table
-- Automated report generation and distribution
-- ====================================
CREATE TABLE IF NOT EXISTS report_schedule (
    id INT PRIMARY KEY AUTO_INCREMENT,
    admin_id INT NOT NULL,
    report_type VARCHAR(50) NOT NULL,
    report_name VARCHAR(255),
    frequency VARCHAR(20) NOT NULL,
    email_recipients JSON NULL,
    include_details BOOLEAN DEFAULT TRUE,
    last_generated_at DATETIME NULL,
    next_scheduled_at DATETIME NULL,
    is_active BOOLEAN DEFAULT TRUE,
    parameters JSON NULL,
    export_format ENUM('pdf', 'csv', 'xlsx', 'json') DEFAULT 'pdf',
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_admin_id (admin_id),
    INDEX idx_report_type (report_type),
    INDEX idx_is_active (is_active),
    INDEX idx_is_deleted (is_deleted),
    INDEX idx_next_scheduled (next_scheduled_at),
    INDEX idx_active_schedule (is_active, frequency)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Automated report scheduling';

-- ====================================
-- Dashboard Metric Table
-- Real-time dashboard metrics and KPIs
-- ====================================
CREATE TABLE IF NOT EXISTS dashboard_metric (
    id INT PRIMARY KEY AUTO_INCREMENT,
    metric_type VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    current_value DECIMAL(15, 2) NOT NULL,
    previous_value DECIMAL(15, 2) NULL,
    change_percent DECIMAL(10, 2) NULL,
    change_direction ENUM('up', 'down', 'stable') NULL,
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,
    description TEXT NULL,
    is_cache_valid BOOLEAN DEFAULT TRUE,
    cache_expires_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_metric_type (metric_type),
    INDEX idx_metric_name (metric_name),
    INDEX idx_period_start (period_start),
    INDEX idx_created_at (created_at),
    INDEX idx_cache_valid (is_cache_valid),
    INDEX idx_metric_type_period (metric_type, period_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Dashboard metrics and KPIs';

-- ====================================
-- Admin User Sessions
-- Track active admin sessions
-- ====================================
CREATE TABLE IF NOT EXISTS admin_sessions (
    id VARCHAR(255) PRIMARY KEY,
    admin_id INT NOT NULL,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    device_type ENUM('mobile', 'desktop', 'tablet'),
    location_country VARCHAR(2),
    is_active BOOLEAN DEFAULT TRUE,
    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_admin_id (admin_id),
    INDEX idx_expires_at (expires_at),
    INDEX idx_token_hash (token_hash),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Admin session management';

-- ====================================
-- Admin Permissions & Roles
-- Role-based access control for admin users
-- ====================================
CREATE TABLE IF NOT EXISTS admin_roles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    role_name VARCHAR(50) NOT NULL UNIQUE,
    role_description TEXT,
    permissions JSON NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_role_name (role_name),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Admin role definitions';

CREATE TABLE IF NOT EXISTS admin_user_roles (
    id INT PRIMARY KEY AUTO_INCREMENT,
    admin_id INT NOT NULL,
    role_id INT NOT NULL,
    assigned_by INT,
    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NULL,
    is_active BOOLEAN DEFAULT TRUE,

    FOREIGN KEY (role_id) REFERENCES admin_roles(id) ON DELETE CASCADE,

    INDEX idx_admin_id (admin_id),
    INDEX idx_role_id (role_id),
    INDEX idx_is_active (is_active),
    UNIQUE KEY unique_admin_role (admin_id, role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Admin user role assignments';

-- ====================================
-- System Configuration
-- Dynamic system configuration settings
-- ====================================
CREATE TABLE IF NOT EXISTS system_configuration (
    id INT PRIMARY KEY AUTO_INCREMENT,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    config_type ENUM('string', 'number', 'boolean', 'json') DEFAULT 'string',
    description TEXT,
    is_sensitive BOOLEAN DEFAULT FALSE,
    is_editable BOOLEAN DEFAULT TRUE,
    modified_by INT,
    modified_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_config_key (config_key),
    INDEX idx_is_sensitive (is_sensitive)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='System configuration settings';

-- ====================================
-- Sample Data
-- ====================================

-- Default admin roles
INSERT INTO admin_roles (role_name, role_description, permissions) VALUES
('super_admin', 'Full system access', '["*"]'),
('admin', 'Standard admin access', '["users.read", "users.update", "reports.read", "reports.create", "analytics.read"]'),
('support', 'Customer support access', '["users.read", "tickets.read", "tickets.update", "analytics.read"]'),
('analyst', 'Read-only analytics access', '["analytics.read", "reports.read"]');

-- Sample system configuration
INSERT INTO system_configuration (config_key, config_value, config_type, description, is_editable) VALUES
('maintenance_mode', 'false', 'boolean', 'Enable maintenance mode', TRUE),
('max_upload_size_mb', '50', 'number', 'Maximum file upload size in MB', TRUE),
('session_timeout_minutes', '60', 'number', 'Admin session timeout in minutes', TRUE),
('enable_2fa', 'true', 'boolean', 'Enable two-factor authentication', TRUE),
('alert_email_recipients', '["admin@nilbx.com"]', 'json', 'Email recipients for system alerts', TRUE);

-- Sample dashboard metrics
INSERT INTO dashboard_metric (metric_type, metric_name, current_value, previous_value, change_percent, period_start, period_end, description) VALUES
('revenue', 'Total Revenue', 125000.00, 110000.00, 13.64, DATE_SUB(NOW(), INTERVAL 30 DAY), NOW(), 'Total revenue for the period'),
('users', 'Active Users', 5420.00, 4800.00, 12.92, DATE_SUB(NOW(), INTERVAL 30 DAY), NOW(), 'Number of active users'),
('deals', 'Active Deals', 234.00, 198.00, 18.18, DATE_SUB(NOW(), INTERVAL 30 DAY), NOW(), 'Number of active NIL deals'),
('payments', 'Successful Payments', 1543.00, 1402.00, 10.06, DATE_SUB(NOW(), INTERVAL 30 DAY), NOW(), 'Number of successful payments');

-- ====================================
-- Database Verification
-- ====================================
SHOW TABLES;
SELECT 'Admin Dashboard Service Database Created - ENHANCED Schema Compatible' as status;
