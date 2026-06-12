import os
import hashlib
import csv
import io
from datetime import datetime, timedelta, date
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_file, g,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import bleach
import markdown

from db import get_connection, commit_and_close, rollback_and_close

app = Flask(__name__)
app.secret_key = "super_secret_key_for_library_app_2024"
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Для выполнения данного действия необходимо пройти процедуру аутентификации", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash("Для выполнения данного действия необходимо пройти процедуру аутентификации", "warning")
                return redirect(url_for("login"))
            if session.get("role_name") not in roles:
                flash("У вас недостаточно прав для выполнения данного действия", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.before_request
def load_user():
    g.user = None
    g.role_name = None
    g.user_fio = None
    if "user_id" in session:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT u.*, r.name as role_name FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = ?",
            (session["user_id"],),
        )
        user = cursor.fetchone()
        conn.close()
        if user:
            g.user = dict(user)
            g.role_name = user["role_name"]
            fio_parts = [user["last_name"], user["first_name"]]
            if user["patronymic"]:
                fio_parts.append(user["patronymic"])
            g.user_fio = " ".join(fio_parts)
            session["role_name"] = user["role_name"]


def get_session_id():
    if "sid" not in session:
        session["sid"] = hashlib.md5(os.urandom(32)).hexdigest()
    return session["sid"]


def track_visit(book_id):
    user_id = session.get("user_id")
    sid = get_session_id()
    today = date.today().isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    try:
        if user_id:
            cursor.execute(
                "SELECT COUNT(*) FROM book_visits WHERE book_id=? AND user_id=? AND visit_date=?",
                (book_id, user_id, today),
            )
            count = cursor.fetchone()[0]
            if count >= 10:
                conn.close()
                return
            cursor.execute(
                "INSERT INTO book_visits (book_id, user_id, session_id, visit_date) VALUES (?, ?, ?, ?)",
                (book_id, user_id, sid, today),
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM book_visits WHERE book_id=? AND user_id IS NULL AND session_id=? AND visit_date=?",
                (book_id, sid, today),
            )
            count = cursor.fetchone()[0]
            if count >= 10:
                conn.close()
                return
            cursor.execute(
                "INSERT INTO book_visits (book_id, user_id, session_id, visit_date) VALUES (?, NULL, ?, ?)",
                (book_id, sid, today),
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


@app.route("/")
def index():
    page = request.args.get("page", 1, type=int)
    per_page = 10

    conn = get_connection()
    cursor = conn.cursor()

    offset = (page - 1) * per_page
    cursor.execute(
        """SELECT b.*,
            GROUP_CONCAT(g.name, ', ') as genres,
            COALESCE(AVG(r.rating), 0) as avg_rating,
            COUNT(DISTINCT r.id) as review_count
        FROM books b
        LEFT JOIN book_genres bg ON b.id = bg.book_id
        LEFT JOIN genres g ON bg.genre_id = g.id
        LEFT JOIN reviews r ON b.id = r.book_id
        GROUP BY b.id
        ORDER BY b.year DESC, b.id DESC
        LIMIT ? OFFSET ?""",
        (per_page, offset),
    )
    books = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) as cnt FROM books")
    total = cursor.fetchone()[0]
    total_pages = max(1, (total + per_page - 1) // per_page)

    three_months_ago = (date.today() - timedelta(days=90)).isoformat()
    cursor.execute(
        """SELECT b.id, b.title, b.author, b.year, COUNT(bv.id) as visit_count
        FROM book_visits bv
        JOIN books b ON bv.book_id = b.id
        WHERE bv.visited_at >= ? AND bv.user_id IS NOT NULL
        GROUP BY b.id
        ORDER BY visit_count DESC
        LIMIT 5""",
        (three_months_ago,),
    )
    popular_books = [dict(row) for row in cursor.fetchall()]

    recently_viewed = []
    if "sid" in session or "user_id" in session:
        if "user_id" in session:
            cursor.execute(
                """SELECT DISTINCT b.id, b.title, b.author, b.year, bv.visited_at
                FROM book_visits bv
                JOIN books b ON bv.book_id = b.id
                WHERE bv.user_id = ?
                ORDER BY bv.visited_at DESC
                LIMIT 5""",
                (session["user_id"],),
            )
        else:
            cursor.execute(
                """SELECT DISTINCT b.id, b.title, b.author, b.year, bv.visited_at
                FROM book_visits bv
                JOIN books b ON bv.book_id = b.id
                WHERE bv.user_id IS NULL AND bv.session_id = ?
                ORDER BY bv.visited_at DESC
                LIMIT 5""",
                (get_session_id(),),
            )
        recently_viewed = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return render_template(
        "index.html",
        books=books,
        page=page,
        total_pages=total_pages,
        popular_books=popular_books,
        recently_viewed=recently_viewed,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_val = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT u.*, r.name as role_name FROM users u JOIN roles r ON u.role_id = r.id WHERE u.login = ?",
            (login_val,),
        )
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session.permanent = remember
            session["user_id"] = user["id"]
            session["role_name"] = user["role_name"]
            flash("Вы успешно вошли в систему", "success")
            return redirect(url_for("index"))
        else:
            flash("Невозможно аутентифицироваться с указанными логином и паролем", "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        login_val = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        last_name = request.form.get("last_name", "").strip()
        first_name = request.form.get("first_name", "").strip()
        patronymic = request.form.get("patronymic", "").strip() or None

        errors = []
        if not login_val:
            errors.append("Логин обязателен")
        if not password:
            errors.append("Пароль обязателен")
        if password != password_confirm:
            errors.append("Пароли не совпадают")
        if len(password) < 6:
            errors.append("Пароль должен содержать минимум 6 символов")
        if not last_name:
            errors.append("Фамилия обязательна")
        if not first_name:
            errors.append("Имя обязательно")

        if not errors:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE login = ?", (login_val,))
            if cursor.fetchone():
                errors.append("Пользователь с таким логином уже существует")

            if errors:
                conn.close()
            else:
                try:
                    pw_hash = generate_password_hash(password)
                    cursor.execute(
                        "INSERT INTO users (login, password_hash, last_name, first_name, patronymic, role_id) VALUES (?, ?, ?, ?, ?, ?)",
                        (login_val, pw_hash, last_name, first_name, patronymic, 3),
                    )
                    conn.commit()
                    flash("Регистрация успешна. Теперь вы можете войти.", "success")
                    return redirect(url_for("login"))
                except Exception:
                    conn.rollback()
                    errors.append("Ошибка при регистрации")
                finally:
                    conn.close()

        for e in errors:
            flash(e, "danger")

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы", "info")
    return redirect(url_for("index"))


@app.route("/books/add", methods=["GET", "POST"])
@role_required("Администратор")
def book_add():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM genres ORDER BY name")
    genres = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        year = request.form.get("year", "").strip()
        publisher = request.form.get("publisher", "").strip()
        author = request.form.get("author", "").strip()
        pages = request.form.get("pages", "").strip()
        genre_ids = request.form.getlist("genres")

        description = bleach.clean(
            description,
            tags=set(bleach.ALLOWED_TAGS) | {"p", "br", "ul", "ol", "li", "em", "strong", "a",
                                         "h1", "h2", "h3", "h4", "h5", "h6", "code", "pre", "blockquote"},
            attributes=bleach.ALLOWED_ATTRIBUTES,
        )

        errors = []
        if not title:
            errors.append("Название обязательно")
        if not description:
            errors.append("Описание обязательно")
        if not year:
            errors.append("Год обязателен")
        if not publisher:
            errors.append("Издательство обязательно")
        if not author:
            errors.append("Автор обязателен")
        if not pages:
            errors.append("Объём обязателен")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("book_form.html", genres=genres, form_data=request.form, edit_mode=False)

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO books (title, description, year, publisher, author, pages) VALUES (?, ?, ?, ?, ?, ?)",
                (title, description, int(year), publisher, author, int(pages)),
            )
            book_id = cursor.lastrowid

            for gid in genre_ids:
                cursor.execute(
                    "INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)",
                    (book_id, int(gid)),
                )

            cover = request.files.get("cover")
            if cover and cover.filename and allowed_file(cover.filename):
                cover_data = cover.read()
                md5_hash = hashlib.md5(cover_data).hexdigest()
                mime_type = cover.content_type

                cursor.execute(
                    "SELECT id, filename FROM covers WHERE md5_hash = ?",
                    (md5_hash,),
                )
                existing = cursor.fetchone()

                if existing:
                    cover_id = existing[0]
                else:
                    cursor.execute(
                        "INSERT INTO covers (filename, mime_type, md5_hash, book_id) VALUES (?, ?, ?, ?)",
                        (cover.filename, mime_type, md5_hash, book_id),
                    )
                    cover_id = cursor.lastrowid
                    ext = cover.filename.rsplit(".", 1)[1].lower()
                    save_filename = f"{cover_id}.{ext}"
                    cursor.execute(
                        "UPDATE covers SET filename = ? WHERE id = ?",
                        (save_filename, cover_id),
                    )
                    filepath = os.path.join(app.config["UPLOAD_FOLDER"], save_filename)
                    cover.seek(0)
                    cover.save(filepath)

            conn.commit()
            flash("Книга успешно добавлена", "success")
            return redirect(url_for("book_view", book_id=book_id))
        except Exception as e:
            conn.rollback()
            flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
            return render_template("book_form.html", genres=genres, form_data=request.form, edit_mode=False)
        finally:
            conn.close()

    return render_template("book_form.html", genres=genres, form_data={}, edit_mode=False)


@app.route("/books/<int:book_id>")
def book_view(book_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT b.*,
            GROUP_CONCAT(g.name, ', ') as genres,
            COALESCE(AVG(r.rating), 0) as avg_rating,
            COUNT(DISTINCT r.id) as review_count
        FROM books b
        LEFT JOIN book_genres bg ON b.id = bg.book_id
        LEFT JOIN genres g ON bg.genre_id = g.id
        LEFT JOIN reviews r ON b.id = r.book_id
        WHERE b.id = ?
        GROUP BY b.id""",
        (book_id,),
    )
    book = cursor.fetchone()

    if not book:
        flash("Книга не найдена", "danger")
        return redirect(url_for("index"))

    book = dict(book)

    cursor.execute("SELECT * FROM covers WHERE book_id = ? LIMIT 1", (book_id,))
    cover_row = cursor.fetchone()
    cover = dict(cover_row) if cover_row else None

    cursor.execute(
        """SELECT r.*, u.last_name, u.first_name, u.patronymic
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.book_id = ?
        ORDER BY r.created_at DESC""",
        (book_id,),
    )
    reviews = [dict(row) for row in cursor.fetchall()]

    user_review = None
    if g.user:
        cursor.execute(
            "SELECT * FROM reviews WHERE book_id = ? AND user_id = ?",
            (book_id, session["user_id"]),
        )
        ur = cursor.fetchone()
        if ur:
            user_review = dict(ur)

    conn.close()

    track_visit(book_id)

    description_html = markdown.markdown(
        book["description"],
        extensions=["extra", "codehilite", "toc"],
    )

    return render_template(
        "book_view.html",
        book=book,
        cover=cover,
        reviews=reviews,
        user_review=user_review,
        description_html=description_html,
    )


@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@role_required("Администратор", "Модератор")
def book_edit(book_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
    book_row = cursor.fetchone()
    if not book_row:
        conn.close()
        flash("Книга не найдена", "danger")
        return redirect(url_for("index"))
    book = dict(book_row)

    cursor.execute("SELECT * FROM genres ORDER BY name")
    genres = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT genre_id FROM book_genres WHERE book_id = ?", (book_id,))
    book_genre_ids = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM covers WHERE book_id = ? LIMIT 1", (book_id,))
    cover_row = cursor.fetchone()
    cover = dict(cover_row) if cover_row else None

    conn.close()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        year = request.form.get("year", "").strip()
        publisher = request.form.get("publisher", "").strip()
        author = request.form.get("author", "").strip()
        pages = request.form.get("pages", "").strip()
        genre_ids = request.form.getlist("genres")

        description = bleach.clean(
            description,
            tags=set(bleach.ALLOWED_TAGS) | {"p", "br", "ul", "ol", "li", "em", "strong", "a",
                                         "h1", "h2", "h3", "h4", "h5", "h6", "code", "pre", "blockquote"},
            attributes=bleach.ALLOWED_ATTRIBUTES,
        )

        errors = []
        if not title:
            errors.append("Название обязательно")
        if not description:
            errors.append("Описание обязательно")
        if not year:
            errors.append("Год обязателен")
        if not publisher:
            errors.append("Издательство обязательно")
        if not author:
            errors.append("Автор обязателен")
        if not pages:
            errors.append("Объём обязателен")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("book_form.html", genres=genres, book=book, book_genre_ids=book_genre_ids, cover=cover, form_data=request.form, edit_mode=True)

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE books SET title=?, description=?, year=?, publisher=?, author=?, pages=? WHERE id=?",
                (title, description, int(year), publisher, author, int(pages), book_id),
            )

            cursor.execute("DELETE FROM book_genres WHERE book_id = ?", (book_id,))
            for gid in genre_ids:
                cursor.execute(
                    "INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)",
                    (book_id, int(gid)),
                )

            conn.commit()
            flash("Книга успешно обновлена", "success")
            return redirect(url_for("book_view", book_id=book_id))
        except Exception:
            conn.rollback()
            flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
            return render_template("book_form.html", genres=genres, book=book, book_genre_ids=book_genre_ids, cover=cover, form_data=request.form, edit_mode=True)
        finally:
            conn.close()

    return render_template("book_form.html", genres=genres, book=book, book_genre_ids=book_genre_ids, cover=cover, form_data=book, edit_mode=True)


@app.route("/books/<int:book_id>/delete", methods=["POST"])
@role_required("Администратор")
def book_delete(book_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT c.filename FROM covers c WHERE c.book_id = ?", (book_id,))
    cover_row = cursor.fetchone()

    cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()

    if cover_row and cover_row[0]:
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], cover_row[0])
        if os.path.exists(filepath):
            os.remove(filepath)

    flash("Книга успешно удалена", "success")
    return redirect(url_for("index"))


@app.route("/books/<int:book_id>/reviews/add", methods=["GET", "POST"])
@login_required
def review_add(book_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
    book_row = cursor.fetchone()
    if not book_row:
        conn.close()
        flash("Книга не найдена", "danger")
        return redirect(url_for("index"))
    book = dict(book_row)

    cursor.execute(
        "SELECT * FROM reviews WHERE book_id = ? AND user_id = ?",
        (book_id, session["user_id"]),
    )
    existing = cursor.fetchone()
    conn.close()

    if existing:
        flash("Вы уже оставили рецензию на эту книгу", "warning")
        return redirect(url_for("book_view", book_id=book_id))

    if request.method == "POST":
        rating = request.form.get("rating", "5")
        text = request.form.get("text", "").strip()

        text = bleach.clean(
            text,
            tags=set(bleach.ALLOWED_TAGS) | {"p", "br", "ul", "ol", "li", "em", "strong", "a"},
            attributes=bleach.ALLOWED_ATTRIBUTES,
        )

        if not text:
            flash("Текст рецензии обязателен", "danger")
            return render_template("review_form.html", book=book, form_data=request.form)

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reviews (book_id, user_id, rating, text) VALUES (?, ?, ?, ?)",
                (book_id, session["user_id"], int(rating), text),
            )
            conn.commit()
            flash("Рецензия успешно добавлена", "success")
            return redirect(url_for("book_view", book_id=book_id))
        except Exception:
            conn.rollback()
            flash("При сохранении данных возникла ошибка", "danger")
            return render_template("review_form.html", book=book, form_data=request.form)
        finally:
            conn.close()

    return render_template("review_form.html", book=book, form_data={})


@app.route("/statistics")
@role_required("Администратор")
def statistics():
    tab = request.args.get("tab", "log")
    page_log = request.args.get("page_log", 1, type=int)
    page_stat = request.args.get("page_stat", 1, type=int)
    per_page = 10

    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    conn = get_connection()
    cursor = conn.cursor()

    log_offset = (page_log - 1) * per_page
    cursor.execute(
        """SELECT bv.id, bv.visited_at, b.title as book_title,
            CASE WHEN u.id IS NOT NULL THEN u.last_name || ' ' || u.first_name || ' ' || COALESCE(u.patronymic, '')
            ELSE 'Неаутентифицированный пользователь' END as user_fio
        FROM book_visits bv
        JOIN books b ON bv.book_id = b.id
        LEFT JOIN users u ON bv.user_id = u.id
        ORDER BY bv.visited_at DESC
        LIMIT ? OFFSET ?""",
        (per_page, log_offset),
    )
    log_entries = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) as cnt FROM book_visits")
    total_log = cursor.fetchone()[0]
    total_log_pages = max(1, (total_log + per_page - 1) // per_page)

    stat_offset = (page_stat - 1) * per_page
    stat_query = """
        SELECT b.id, b.title, COUNT(bv.id) as view_count
        FROM book_visits bv
        JOIN books b ON bv.book_id = b.id
        WHERE bv.user_id IS NOT NULL
    """
    stat_params = []

    if date_from:
        stat_query += " AND bv.visited_at >= ?"
        stat_params.append(date_from + " 00:00:00")
    if date_to:
        stat_query += " AND bv.visited_at <= ?"
        stat_params.append(date_to + " 23:59:59")

    stat_query += " GROUP BY b.id ORDER BY view_count DESC LIMIT ? OFFSET ?"
    stat_params.extend([per_page, stat_offset])

    cursor.execute(stat_query, stat_params)
    stat_entries = [dict(row) for row in cursor.fetchall()]

    count_query = """
        SELECT COUNT(*) as cnt FROM (
            SELECT b.id
            FROM book_visits bv
            JOIN books b ON bv.book_id = b.id
            WHERE bv.user_id IS NOT NULL
    """
    count_params = []
    if date_from:
        count_query += " AND bv.visited_at >= ?"
        count_params.append(date_from + " 00:00:00")
    if date_to:
        count_query += " AND bv.visited_at <= ?"
        count_params.append(date_to + " 23:59:59")
    count_query += " GROUP BY b.id) as sub"
    cursor.execute(count_query, count_params)
    total_stat = cursor.fetchone()[0]
    total_stat_pages = max(1, (total_stat + per_page - 1) // per_page)

    conn.close()

    return render_template(
        "statistics.html",
        tab=tab,
        log_entries=log_entries,
        stat_entries=stat_entries,
        page_log=page_log,
        page_stat=page_stat,
        total_log_pages=total_log_pages,
        total_stat_pages=total_stat_pages,
        date_from=date_from,
        date_to=date_to,
    )


@app.route("/statistics/export_log")
@role_required("Администратор")
def export_log():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT bv.visited_at, b.title as book_title,
            CASE WHEN u.id IS NOT NULL THEN u.last_name || ' ' || u.first_name || ' ' || COALESCE(u.patronymic, '')
            ELSE 'Неаутентифицированный пользователь' END as user_fio
        FROM book_visits bv
        JOIN books b ON bv.book_id = b.id
        LEFT JOIN users u ON bv.user_id = u.id
        ORDER BY bv.visited_at DESC"""
    )
    entries = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["№", "Пользователь", "Книга", "Дата и время просмотра"])
    for i, entry in enumerate(entries, 1):
        writer.writerow([i, entry["user_fio"], entry["book_title"], entry["visited_at"]])

    output.seek(0)
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"activity_log_{date_str}.csv"

    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8-sig"))
    mem.seek(0)

    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=filename)


@app.route("/statistics/export_stat")
@role_required("Администратор")
def export_stat():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    conn = get_connection()
    cursor = conn.cursor()

    stat_query = """
        SELECT b.title, COUNT(bv.id) as view_count
        FROM book_visits bv
        JOIN books b ON bv.book_id = b.id
        WHERE bv.user_id IS NOT NULL
    """
    stat_params = []

    if date_from:
        stat_query += " AND bv.visited_at >= ?"
        stat_params.append(date_from + " 00:00:00")
    if date_to:
        stat_query += " AND bv.visited_at <= ?"
        stat_params.append(date_to + " 23:59:59")

    stat_query += " GROUP BY b.id ORDER BY view_count DESC"
    cursor.execute(stat_query, stat_params)
    entries = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["№", "Книга", "Количество просмотров"])
    for i, entry in enumerate(entries, 1):
        writer.writerow([i, entry["title"], entry["view_count"]])

    output.seek(0)
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"book_statistics_{date_str}.csv"

    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8-sig"))
    mem.seek(0)

    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=filename)


@app.template_filter("markdown")
def markdown_filter(text):
    return markdown.markdown(text, extensions=["extra", "codehilite", "toc"])


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
