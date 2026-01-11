-- =======================================================================
-- Migration 001: Base check_ins table (stub for later alterations)
-- =======================================================================
-- Creates a minimal check_ins table so later migrations (e.g., 007) can
-- ALTER it to add spatial/location and contract integration columns.
-- =======================================================================

USE nilbx_db;

CREATE TABLE IF NOT EXISTS check_ins (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NULL,
    status ENUM('pending', 'validated', 'disputed', 'cancelled') DEFAULT 'pending',
    checked_in_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Base check-ins table; extended by later migrations';
