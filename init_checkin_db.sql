-- Check-in Service Database Initialization
-- Add these tables to your main NILbx database

-- 6. Check-ins (Geo-fence + Social Proof)
CREATE TABLE IF NOT EXISTS checkins (
    id INT PRIMARY KEY AUTO_INCREMENT,
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

    FOREIGN KEY (deal_id) REFERENCES deals(id) ON DELETE CASCADE,
    FOREIGN KEY (athlete_id) REFERENCES influencers(id) ON DELETE CASCADE,

    INDEX idx_deal_id (deal_id),
    INDEX idx_athlete_id (athlete_id),
    INDEX idx_status (status),
    INDEX idx_checkin_time (checkin_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Geo-fences (Hotspot boundaries)
CREATE TABLE IF NOT EXISTS geo_fences (
    id INT PRIMARY KEY AUTO_INCREMENT,
    hotspot_name VARCHAR(255) NOT NULL,
    deal_id INT,
    lat_center DECIMAL(10, 8) NOT NULL,
    lng_center DECIMAL(11, 8) NOT NULL,
    radius_meters INT NOT NULL DEFAULT 100,  -- 100m radius
    address VARCHAR(255),
    active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (deal_id) REFERENCES deals(id) ON DELETE SET NULL,

    INDEX idx_hotspot_name (hotspot_name),
    INDEX idx_active (active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sample geo-fence data
INSERT INTO geo_fences (hotspot_name, lat_center, lng_center, radius_meters, address) VALUES
('Starbucks Downtown', 40.712776, -74.005974, 50, '123 Main St, New York, NY'),
('Chipotle Campus', 37.441883, -122.143019, 75, '456 University Ave, Palo Alto, CA'),
('Nike Store Mall', 47.606209, -122.332071, 100, '789 Mall Way, Seattle, WA');