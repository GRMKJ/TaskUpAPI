-- TaskUp MariaDB schema v1
-- Run this script with a privileged user (e.g. root) to bootstrap the database.

DROP DATABASE IF EXISTS taskup;
CREATE DATABASE taskup CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE taskup;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

START TRANSACTION;

CREATE TABLE users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(190) NOT NULL UNIQUE,
    password_hash CHAR(60) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    status ENUM('active','inactive','blocked') NOT NULL DEFAULT 'active',
    last_login_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE devices (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    device_uuid CHAR(36) NOT NULL,
    device_name VARCHAR(150) NULL,
    platform ENUM('android','ios','web','desktop') NOT NULL,
    app_version VARCHAR(50) NULL,
    last_seen_at DATETIME NULL,
    fcm_token VARCHAR(512) NULL,
    fcm_token_updated_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_device_user_uuid (user_id, device_uuid),
    CONSTRAINT fk_devices_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE user_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    device_id BIGINT UNSIGNED NULL,
    refresh_token CHAR(64) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at DATETIME NULL,
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_sessions_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE tasks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NULL,
    priority ENUM('low','medium','high') NOT NULL DEFAULT 'medium',
    due_at DATETIME NULL,
    remind_at DATETIME NULL,
    remind_local_at DATETIME NULL,
    remind_timezone_offset_minutes INT NULL,
    completed TINYINT(1) NOT NULL DEFAULT 0,
    completed_at DATETIME NULL,
    archived TINYINT(1) NOT NULL DEFAULT 0,
    deleted_at DATETIME NULL,
    reminder_sent_at DATETIME NULL,
    version BIGINT UNSIGNED NOT NULL DEFAULT 1,
    checksum CHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_tasks_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_tasks_user (user_id),
    INDEX idx_tasks_user_version (user_id, version),
    INDEX idx_tasks_user_completed (user_id, completed, archived),
    INDEX idx_tasks_user_remind (user_id, remind_at)
) ENGINE=InnoDB;

CREATE TABLE task_change_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    task_id BIGINT UNSIGNED NOT NULL,
    device_id BIGINT UNSIGNED NULL,
    operation ENUM('create','update','complete','reopen','delete','restore') NOT NULL,
    change_payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_change_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_change_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_change_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE SET NULL,
    INDEX idx_change_user_created (user_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE device_sync_cursors (
    device_id BIGINT UNSIGNED PRIMARY KEY,
    last_change_id BIGINT UNSIGNED NOT NULL DEFAULT 0,
    last_synced_at TIMESTAMP NULL,
    CONSTRAINT fk_cursor_device FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE task_labels (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(60) NOT NULL,
    color CHAR(7) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_label_user_name (user_id, name),
    CONSTRAINT fk_labels_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE task_label_map (
    task_id BIGINT UNSIGNED NOT NULL,
    label_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (task_id, label_id),
    CONSTRAINT fk_map_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_map_label FOREIGN KEY (label_id) REFERENCES task_labels(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE task_comments (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_id BIGINT UNSIGNED NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_comments_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    CONSTRAINT fk_comments_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_comments_task_created (task_id, created_at)
) ENGINE=InnoDB;

CREATE TABLE recurring_tasks (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NULL,
    priority ENUM('low','medium','high') NOT NULL DEFAULT 'medium',
    recurrence_rule VARCHAR(255) NOT NULL,
    next_run_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_recurring_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;

COMMIT;
