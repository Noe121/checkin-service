-- Check-in Service: initial schema (service-owned, no cross-service FKs)
-- Database target: checkin_db

CREATE TABLE IF NOT EXISTS checkins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    deal_id INT NOT NULL,
    athlete_id INT NOT NULL,
    location_lat DECIMAL(10, 8),
    location_lng DECIMAL(11, 8),
    geo_verified BOOLEAN DEFAULT FALSE,
    social_post_url VARCHAR(500),
    social_verified BOOLEAN DEFAULT FALSE,
    photo_url VARCHAR(500),
    status ENUM('pending', 'verified', 'rejected') DEFAULT 'pending',
    checkin_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_deal_id (deal_id),
    INDEX idx_athlete_id (athlete_id),
    INDEX idx_status (status),
    INDEX idx_checkin_time (checkin_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS geo_fences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hotspot_name VARCHAR(255) NOT NULL,
    deal_id INT,
    lat_center DECIMAL(10, 8) NOT NULL,
    lng_center DECIMAL(11, 8) NOT NULL,
    radius_meters INT NOT NULL DEFAULT 100,
    address VARCHAR(255),
    active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_hotspot_name (hotspot_name),
    INDEX idx_active (active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
