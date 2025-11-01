-- ============================================
-- 💡 THERMOTRACK DATABASE - ENHANCED SAMPLE SCHEMA
-- ============================================

DROP DATABASE IF EXISTS thermotrack;
CREATE DATABASE thermotrack CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE thermotrack;

-- ============================================
-- USERS TABLE
-- ============================================
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- ROOMS TABLE
-- ============================================
CREATE TABLE rooms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    location VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- DEVICES TABLE
-- ============================================
CREATE TABLE devices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    device_uid VARCHAR(100) UNIQUE,
    type VARCHAR(50),
    status ENUM('active','inactive') DEFAULT 'active',
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP NULL,
    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
);

-- ============================================
-- READINGS TABLE
-- ============================================
CREATE TABLE readings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    temperature FLOAT,
    humidity FLOAT,
    motion_detected BOOLEAN DEFAULT 0,
    pressure FLOAT,
    light_level FLOAT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
);

CREATE INDEX idx_readings_device_time ON readings (device_id, recorded_at DESC);

-- ============================================
-- ALERTS TABLE
-- ============================================
CREATE TABLE alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id INT NOT NULL,
    room_id INT NULL,
    reading_id INT NULL,
    message VARCHAR(255) NOT NULL,
    severity ENUM('info','warning','critical') DEFAULT 'info',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE SET NULL,
    FOREIGN KEY (reading_id) REFERENCES readings(id) ON DELETE SET NULL
);

CREATE INDEX idx_alerts_device_time ON alerts (device_id, created_at DESC);

-- ============================================
-- AUDIT LOG TABLE
-- ============================================
CREATE TABLE audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    action VARCHAR(100) NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- ============================================
-- SAMPLE DATA
-- ============================================

-- Rooms
INSERT INTO rooms (name, location) VALUES
('Server Room', 'Building A'),
('Office Lab', 'Building B'),
('Warehouse', 'Building C');

-- Devices
INSERT INTO devices (room_id, name, device_uid, type, status) VALUES
(1, 'Raspberry Pi #1', 'pi-001', 'Temperature', 'active'),
(1, 'DHT22 Node', 'dht-001', 'Humidity', 'active'),
(2, 'ESP32 Sensor', 'esp-002', 'Temperature', 'active'),
(2, 'PIR Motion #1', 'pir-002', 'Motion', 'active'),
(3, 'Warehouse Temp', 'wh-temp-003', 'Temperature', 'active'),
(3, 'Warehouse Motion', 'wh-motion-004', 'Motion', 'active');

-- Readings
INSERT INTO readings (device_id, temperature, humidity, motion_detected, pressure, light_level, recorded_at) VALUES
-- Server Room readings
(1, 24.5, 45.1, 0, 1012.5, 120.0, '2025-11-01 14:00:00'),
(1, 25.2, 44.9, 0, 1012.2, 130.5, '2025-11-01 15:00:00'),
(2, 24.8, 46.2, 0, 1011.9, 125.0, '2025-11-01 14:10:00'),

-- Office Lab readings
(3, 28.9, 61.3, 1, 1009.8, 80.0, '2025-11-01 14:19:11'),
(3, 29.2, 60.9, 0, 1009.6, 85.3, '2025-11-01 15:19:11'),
(4, NULL, NULL, 1, NULL, 0, '2025-11-01 15:19:11'),

-- Warehouse readings
(5, 22.5, 49.7, 0, 1013.1, 95.0, '2025-11-01 13:59:00'),
(5, 22.8, 50.2, 0, 1012.9, 100.0, '2025-11-01 14:59:00'),
(6, NULL, NULL, 1, NULL, 0, '2025-11-01 14:59:00');

-- Alerts
INSERT INTO alerts (device_id, room_id, message, severity, created_at) VALUES
(1, 1, 'Temperature slightly above safe range', 'warning', '2025-11-01 15:00:00'),
(2, 1, 'Humidity spike detected', 'info', '2025-11-01 15:10:00'),
(3, 2, 'Temperature exceeded comfort level', 'critical', '2025-11-01 15:19:00'),
(5, 3, 'Warehouse cooling unit stable', 'info', '2025-11-01 14:59:00');

-- Users
INSERT INTO users (username, email, password) VALUES
('admin', 'admin@example.com', 'admin123');

-- ============================================
-- ✅ DATABASE READY WITH DEMO DATA
-- ============================================
