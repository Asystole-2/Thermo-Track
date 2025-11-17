-- ============================================
-- 💡 THERMOTRACK DATABASE — MULTI-TENANT & SAFER
-- ============================================

DROP DATABASE IF EXISTS thermotrack;
CREATE DATABASE thermotrack CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE thermotrack;

-- Ensure InnoDB (FKs) is default
SET default_storage_engine=INNODB;

-- ============================================
-- USERS
-- ============================================
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role ENUM('admin', 'user', 'technician', 'viewer') NOT NULL DEFAULT 'user',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ============================================
-- ROOMS  (scoped to a user)
-- ============================================
CREATE TABLE rooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    location VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_rooms_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_rooms_user (user_id),
    UNIQUE KEY uq_user_room_name (user_id, name)
) ENGINE=InnoDB;

-- ============================================
-- DEVICES
-- ============================================
CREATE TABLE devices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    device_uid VARCHAR(100) UNIQUE,
    type VARCHAR(50),
    status ENUM('active','inactive') DEFAULT 'active',
    installed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP NULL DEFAULT NULL,
    CONSTRAINT fk_devices_room FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
    INDEX idx_devices_room (room_id),
    INDEX idx_devices_type (type)
) ENGINE=InnoDB;

-- ============================================
-- READINGS
-- ============================================
CREATE TABLE readings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    temperature DECIMAL(5,2) NULL,
    humidity DECIMAL(5,2) NULL,
    motion_detected BOOLEAN DEFAULT 0,
    pressure DECIMAL(7,2) NULL,
    light_level DECIMAL(10,2) NULL,
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_readings_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    INDEX idx_readings_device_time (device_id, recorded_at),
    INDEX idx_readings_time (recorded_at)
) ENGINE=InnoDB;

-- ============================================
-- ALERTS
-- ============================================
CREATE TABLE alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    room_id INT NULL,
    reading_id INT NULL,
    message VARCHAR(255) NOT NULL,
    severity ENUM('info','warning','critical') DEFAULT 'info',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_alerts_device  FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    CONSTRAINT fk_alerts_room    FOREIGN KEY (room_id)   REFERENCES rooms(id)   ON DELETE SET NULL,
    CONSTRAINT fk_alerts_reading FOREIGN KEY (reading_id) REFERENCES readings(id) ON DELETE SET NULL,
    INDEX idx_alerts_device_time (device_id, created_at),
    INDEX idx_alerts_room_time (room_id, created_at)
) ENGINE=InnoDB;

-- ============================================
-- AUDIT LOG
-- ============================================
CREATE TABLE audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(100) NOT NULL,
    details TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    INDEX idx_audit_user_time (user_id, created_at)
) ENGINE=InnoDB;

-- ============================================
-- VIEW: latest reading per device
-- ============================================
CREATE OR REPLACE VIEW v_latest_device_reading AS
SELECT r.*
FROM readings r
JOIN (
  SELECT device_id, MAX(recorded_at) AS max_time
  FROM readings
  GROUP BY device_id
) m ON m.device_id = r.device_id AND m.max_time = r.recorded_at;

-- ============================================
-- SAMPLE DATA
-- ============================================

-- Rooms (scoped to user_id)
-- admin's rooms: ids will be 1..3
INSERT INTO rooms (user_id, name, location) VALUES
(1, 'Server Room', 'Building A'),
(1, 'Office Lab',  'Building B'),
(1, 'Warehouse',   'Building C');

-- alice's rooms
INSERT INTO rooms (user_id, name, location) VALUES
(2, 'Studio',      'Level 4'),
(2, 'Greenhouse',  'Annex');

-- Devices (admin’s rooms)
INSERT INTO devices (room_id, name, device_uid, type, status) VALUES
(1, 'Raspberry Pi #1',   'pi-001',        'Temperature', 'active'),
(1, 'DHT22 Node',        'dht-001',       'Humidity',    'active'),
(2, 'ESP32 Sensor',      'esp-002',       'Temperature', 'active'),
(2, 'PIR Motion #1',     'pir-002',       'Motion',      'active'),
(3, 'Warehouse Temp',    'wh-temp-003',   'Temperature', 'active'),
(3, 'Warehouse Motion',  'wh-motion-004', 'Motion',      'active');

-- Devices (alice’s rooms)
INSERT INTO devices (room_id, name, device_uid, type, status) VALUES
(4, 'Studio Temp',       'stu-temp-005',  'Temperature', 'active'),
(5, 'Greenhouse Humid',  'gr-hum-006',    'Humidity',    'active');

-- Readings (admin’s devices)
INSERT INTO readings (device_id, temperature, humidity, motion_detected, pressure, light_level, recorded_at) VALUES
(1, 24.50, 45.10, 0, 1012.50, 120.00, '2025-11-01 14:00:00'),
(1, 25.20, 44.90, 0, 1012.20, 130.50, '2025-11-01 15:00:00'),
(2, NULL,  46.20, 0, 1011.90, 125.00, '2025-11-01 14:10:00'),
(3, 28.90, 61.30, 1, 1009.80, 80.00,  '2025-11-01 14:19:11'),
(3, 29.20, 60.90, 0, 1009.60, 85.30,  '2025-11-01 15:19:11'),
(4, NULL,  NULL,  1, NULL,    0.00,   '2025-11-01 15:19:11'),
(5, 22.50, 49.70, 0, 1013.10, 95.00,  '2025-11-01 13:59:00'),
(5, 22.80, 50.20, 0, 1012.90, 100.00, '2025-11-01 14:59:00'),
(6, NULL,  NULL,  1, NULL,    0.00,   '2025-11-01 14:59:00');

-- Readings (alice’s devices)
INSERT INTO readings (device_id, temperature, humidity, motion_detected, pressure, light_level, recorded_at) VALUES
(7, 23.40, 40.50, 0, 1010.40, 110.00, '2025-11-01 14:30:00'),
(8, 24.10, 62.80, 0, 1008.90,  90.00, '2025-11-01 14:35:00');

-- Alerts
INSERT INTO alerts (device_id, room_id, message, severity, created_at) VALUES
(1, 1, 'Temperature slightly above safe range', 'warning',  '2025-11-01 15:00:00'),
(2, 1, 'Humidity spike detected',               'info',     '2025-11-01 15:10:00'),
(3, 2, 'Temperature exceeded comfort level',    'critical', '2025-11-01 15:19:00'),
(5, 3, 'Warehouse cooling unit stable',         'info',     '2025-11-01 14:59:00'),
(7, 4, 'Studio temperature normal',             'info',     '2025-11-01 14:40:00');

ALTER TABLE rooms ADD COLUMN temperature_unit ENUM('celsius', 'fahrenheit', 'kelvin') DEFAULT 'celsius';

-- Add tables for room condition requests and notifications
CREATE TABLE IF NOT EXISTS room_condition_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_id INT NOT NULL,
    user_id INT NOT NULL,
    request_type ENUM('temperature_change', 'fan_adjustment', 'air_quality') NOT NULL,
    current_temperature DECIMAL(5,2),
    target_temperature DECIMAL(5,2),
    fan_level_request ENUM('more_air', 'less_air'),
    user_notes TEXT,
    status ENUM('pending', 'viewed', 'approved', 'denied', 'completed') DEFAULT 'pending',
    estimated_completion_time TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_requests_room FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
    CONSTRAINT fk_requests_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_requests_status (status),
    INDEX idx_requests_room (room_id),
    INDEX idx_requests_user (user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    request_id INT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type ENUM('info', 'success', 'warning', 'error') DEFAULT 'info',
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_notifications_request FOREIGN KEY (request_id) REFERENCES room_condition_requests(id) ON DELETE SET NULL,
    INDEX idx_notifications_user (user_id),
    INDEX idx_notifications_read (is_read)
) ENGINE=InnoDB;

-- update for room allocation for users
-- Add a new table for user-room relationships (many-to-many)
CREATE TABLE IF NOT EXISTS user_rooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    room_id INT NOT NULL,
    added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_rooms_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_rooms_room FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
    UNIQUE KEY uq_user_room (user_id, room_id),
    INDEX idx_user_rooms_user (user_id),
    INDEX idx_user_rooms_room (room_id)
) ENGINE=InnoDB;

-- Migrate existing rooms to user_rooms table
INSERT IGNORE INTO user_rooms (user_id, room_id)
SELECT user_id, id FROM rooms;

-- Add a sample room that doesn't belong to the current user for testing
INSERT IGNORE INTO rooms (user_id, name, location) VALUES
(1, 'Shared Lab', 'Building D'),
(1, 'Conference Room', 'Main Building');

-- Add devices to these shared rooms
INSERT IGNORE INTO devices (room_id, name, device_uid, type, status) VALUES
(8, 'Shared Temp Sensor', 'shared-temp-001', 'Temperature', 'active'),
(9, 'Conference Motion', 'conf-motion-001', 'Motion', 'active');

