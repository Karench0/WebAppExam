import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library.db")


def setup():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON")

    cursor.executescript("""
    CREATE TABLE roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(50) NOT NULL,
        description TEXT NOT NULL
    );

    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login VARCHAR(100) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        last_name VARCHAR(100) NOT NULL,
        first_name VARCHAR(100) NOT NULL,
        patronymic VARCHAR(100) DEFAULT NULL,
        role_id INTEGER NOT NULL,
        FOREIGN KEY (role_id) REFERENCES roles(id)
    );

    CREATE TABLE genres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(100) NOT NULL UNIQUE
    );

    CREATE TABLE books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title VARCHAR(255) NOT NULL,
        description TEXT NOT NULL,
        year INTEGER NOT NULL,
        publisher VARCHAR(255) NOT NULL,
        author VARCHAR(255) NOT NULL,
        pages INTEGER NOT NULL
    );

    CREATE TABLE book_genres (
        book_id INTEGER NOT NULL,
        genre_id INTEGER NOT NULL,
        PRIMARY KEY (book_id, genre_id),
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
        FOREIGN KEY (genre_id) REFERENCES genres(id) ON DELETE CASCADE
    );

    CREATE TABLE covers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename VARCHAR(255) NOT NULL,
        mime_type VARCHAR(100) NOT NULL,
        md5_hash VARCHAR(32) NOT NULL,
        book_id INTEGER NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
    );

    CREATE TABLE reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        rating INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE book_visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        user_id INTEGER DEFAULT NULL,
        session_id VARCHAR(255) DEFAULT NULL,
        visited_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        visit_date DATE NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE INDEX idx_book_visits_date ON book_visits(visit_date);
    CREATE INDEX idx_book_visits_book_user_date ON book_visits(book_id, user_id, visit_date);
    CREATE INDEX idx_book_visits_visited_at ON book_visits(visited_at);
    """)

    cursor.executemany(
        "INSERT INTO roles (name, description) VALUES (?, ?)",
        [
            ("Администратор", "Суперпользователь, имеет полный доступ к системе"),
            ("Модератор", "Может редактировать данные книг и производить модерацию рецензий"),
            ("Пользователь", "Может оставлять рецензии"),
        ],
    )

    cursor.executemany(
        "INSERT INTO genres (name) VALUES (?)",
        [
            ("Художественная литература",),
            ("Научная фантастика",),
            ("Детектив",),
            ("Фантастика",),
            ("Классика",),
            ("Поэзия",),
            ("Научно-популярная",),
            ("Исторический роман",),
            ("Приключения",),
            ("Философия",),
        ],
    )

    users = [
        ("admin", "admin123", "Админ", "Карен", "Админович", 1),
        ("moderator", "mod123", "Модератор", "Карен", "Модераторович", 2),
        ("user", "user123", "Пользователь", "Карен", "Пользователевич", 3),
    ]
    for login, password, last, first, patron, role_id in users:
        pw_hash = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (login, password_hash, last_name, first_name, patronymic, role_id) VALUES (?, ?, ?, ?, ?, ?)",
            (login, pw_hash, last, first, patron, role_id),
        )

    sample_books = [
        ("Мастер и Маргарита", "Роман Михаила Булгакова, написанный в 1928–1940 годах. Одно из наиболее известных произведений русской литературы XX века.", 1967, "АСТ", "Михаил Булгаков", 480, [5, 1]),
        ("Дюна", "Научно-фантастический роман Фрэнка Герберта. Эпическая сага о планете Арракис.", 1965, "АСТ", "Фрэнк Герберт", 736, [2, 9]),
        ("Преступление и наказание", "Социально-психологический и социально-философский роман Фёдора Достоевского.", 1866, "Эксмо", "Фёдор Достоевский", 576, [5, 10]),
        ("1984", "Антиутопический роман Джорджа Оруэлла, изданный в 1949 году.", 1949, "АСТ", "Джордж Оруэлл", 320, [1, 4]),
        ("Гарри Поттер и философский камень", "Первый роман серии «Гарри Поттер» британской писательницы Дж. К. Роулинг.", 1997, "Махаон", "Дж. К. Роулинг", 432, [1, 9]),
    ]

    for title, desc, year, publisher, author, pages, genre_ids in sample_books:
        cursor.execute(
            "INSERT INTO books (title, description, year, publisher, author, pages) VALUES (?, ?, ?, ?, ?, ?)",
            (title, desc, year, publisher, author, pages),
        )
        book_id = cursor.lastrowid
        for gid in genre_ids:
            cursor.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, gid))

    conn.commit()
    conn.close()

    print("Database setup complete!")
    print("Users: admin/admin123, moderator/mod123, user/user123")


if __name__ == "__main__":
    setup()
