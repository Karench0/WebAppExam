CREATE DATABASE IF NOT EXISTS library_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE library_db;

CREATE TABLE IF NOT EXISTS roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    login VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    patronymic VARCHAR(100) DEFAULT NULL,
    role_id INT NOT NULL,
    FOREIGN KEY (role_id) REFERENCES roles(id)
);

CREATE TABLE IF NOT EXISTS genres (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS books (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    year YEAR NOT NULL,
    publisher VARCHAR(255) NOT NULL,
    author VARCHAR(255) NOT NULL,
    pages INT NOT NULL
);

CREATE TABLE IF NOT EXISTS book_genres (
    book_id INT NOT NULL,
    genre_id INT NOT NULL,
    PRIMARY KEY (book_id, genre_id),
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (genre_id) REFERENCES genres(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS covers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    md5_hash VARCHAR(32) NOT NULL,
    book_id INT NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    book_id INT NOT NULL,
    user_id INT NOT NULL,
    rating INT NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS book_visits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    book_id INT NOT NULL,
    user_id INT DEFAULT NULL,
    session_id VARCHAR(255) DEFAULT NULL,
    visited_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    visit_date DATE NOT NULL,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_book_visits_date ON book_visits(visit_date);
CREATE INDEX idx_book_visits_book_user_date ON book_visits(book_id, user_id, visit_date);
CREATE INDEX idx_book_visits_visited_at ON book_visits(visited_at);

INSERT INTO roles (name, description) VALUES
('Администратор', 'Суперпользователь, имеет полный доступ к системе'),
('Модератор', 'Может редактировать данные книг и производить модерацию рецензий'),
('Пользователь', 'Может оставлять рецензии');

INSERT INTO genres (name) VALUES
('Художественная литература'),
('Научная фантастика'),
('Детектив'),
('Фантастика'),
('Классика'),
('Поэзия'),
('Научно-популярная'),
('Исторический роман'),
('Приключения'),
('Философия');

INSERT INTO users (login, password_hash, last_name, first_name, patronymic, role_id) VALUES
('admin', 'pbkdf2:sha256:600000$placeholder$placeholder', 'Иванов', 'Админ', 'Админович', 1),
('moderator', 'pbkdf2:sha256:600000$placeholder$placeholder', 'Петров', 'Модератор', 'Петрович', 2),
('user', 'pbkdf2:sha256:600000$placeholder$placeholder', 'Сидоров', 'Пользователь', 'Сидорович', 3);
