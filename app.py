from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import sqlite3
import os

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.secret_key = os.environ.get("SECRET_KEY","local-dev-secret-key")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        content TEXT,
        user_id INTEGER,
        created_at TIMESTAMP,
        attachment TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    post_id INTEGER
)
""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT,
    user_id INTEGER,
    post_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

    conn.commit()
    conn.close()


init_db()


# ---------------- USER CLASS ----------------
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return User(user[0], user[1])
    return None


# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )
            conn.commit()
            flash("Registration successful!", "success")
            return redirect(url_for("login"))
        except:
            flash("Username already exists", "error")

        conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        )

        user = cursor.fetchone()
        conn.close()

        if user:
            login_user(User(user[0], user[1]))
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials", "error")

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    search = request.args.get('search', '')
    page = request.args.get("page", 1, type=int)
    per_page = 5

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    if search:
        cursor.execute(
            "SELECT COUNT(*) FROM posts WHERE user_id=? AND (title LIKE ? OR content LIKE ?)",
            (
                current_user.id,
                f'%{search}%',
                f'%{search}%'
            )
        )
        total_posts = cursor.fetchone()[0]
        total_pages = max(1, (total_posts + per_page - 1) // per_page)

        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * per_page
        cursor.execute(
            "SELECT * FROM posts WHERE user_id = ? AND (title LIKE ? OR content LIKE ?) ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (
                current_user.id,
                f'%{search}%',
                f'%{search}%',
                per_page,
                offset
            )
        )
    else:
        cursor.execute(
            "SELECT COUNT(*) FROM posts WHERE user_id=?",
            (current_user.id,)
        )
        total_posts = cursor.fetchone()[0]
        total_pages = max(1, (total_posts + per_page - 1) // per_page)

        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * per_page
        cursor.execute(
            "SELECT * FROM posts WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (current_user.id, per_page, offset)
        )

    posts = cursor.fetchall()
    post_data = []

    for post in posts:
        cursor.execute(
        "SELECT COUNT(*) FROM likes WHERE post_id=?",
        (post[0],)
         )
        like_count = cursor.fetchone()[0]
        cursor.execute(
    "SELECT COUNT(*) FROM comments WHERE post_id=?",
    (post[0],)
)
        comment_count = cursor.fetchone()[0]
        post_data.append((post, like_count, comment_count))

    conn.close()

    return render_template(
        "dashboard.html",
        posts= post_data,
        search=search,
        total_pages=total_pages,
        page=page
    )


@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        file = request.files["attachment"]
        filename = None

        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        cursor.execute(
    """
    INSERT INTO posts (title, content, user_id, created_at, attachment)
    VALUES (?, ?, ?, datetime('now'), ?)
    """,
    (title, content, current_user.id, filename)
)

        conn.commit()
        conn.close()

        flash("Post created successfully.", "success")
        return redirect(url_for("dashboard"), code=303)

    return render_template(
        "create_post.html",
        action_url=url_for("create"),
        page_title="Create Post",
        header_title="Create New Post",
        header_desc="Write a story, article, or update for your blog.",
        btn_text="Publish Post",
        title_value="",
        content_value="",
        form_method="POST"
    )


@app.route("/edit/<int:post_id>", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM posts WHERE id=? AND user_id=?",
        (post_id, current_user.id)
    )
    post = cursor.fetchone()

    if not post:
        conn.close()
        flash("Post not found or access denied.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        file = request.files["attachment"]
        filename = post[5]
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        
        cursor.execute(
            "UPDATE posts SET title=?, content=?, attachment=? WHERE id=? AND user_id=?",
            (title, content, filename, post_id, current_user.id,)
        )
        conn.commit()
        conn.close()

        flash("Post updated successfully.", "success")
        return redirect(url_for("dashboard"), code=303)

    conn.close()
    return render_template(
        "create_post.html",
        action_url=url_for("edit_post", post_id=post_id),
        page_title="Edit Post",
        header_title="Edit Post",
        header_desc="Update your blog post content.",
        btn_text="Save Changes",
        title_value=post[1],
        content_value=post[2],
        form_method="POST"
    )


@app.route("/delete/<int:post_id>", methods=["POST"])
@login_required
def delete_post(post_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM posts WHERE id=? AND user_id=?",
        (post_id, current_user.id)
    )
    conn.commit()
    conn.close()

    flash("Post deleted successfully.", "success")
    return redirect(url_for("dashboard"), code=303)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))
@app.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    # Delete user's posts
    cursor.execute(
        "DELETE FROM posts WHERE user_id=?",
        (current_user.id,)
    )

    # Delete user account
    cursor.execute(
        "DELETE FROM users WHERE id=?",
        (current_user.id,)
    )

    conn.commit()
    conn.close()

    logout_user()
    flash("Your account has been deleted successfully.", "success")

    return redirect(url_for("login"))
@app.route("/like/<int:post_id>", methods=["POST"])
@login_required
def like_post(post_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM likes WHERE user_id=? AND post_id=?",
        (current_user.id, post_id)
    )

    existing_like = cursor.fetchone()

    if existing_like:
        cursor.execute(
            "DELETE FROM likes WHERE user_id=? AND post_id=?",
            (current_user.id, post_id)
        )
    else:
        cursor.execute(
            "INSERT INTO likes (user_id, post_id) VALUES (?, ?)",
            (current_user.id, post_id)
        )

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))
@app.route("/comment/<int:post_id>", methods=["POST"])
@login_required
def comment_post(post_id):
    content = request.form["comment"]

    if content.strip():
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO comments (content, user_id, post_id)
            VALUES (?, ?, ?)
            """,
            (content, current_user.id, post_id)
        )

        conn.commit()
        conn.close()

    return redirect(url_for("dashboard"))
@app.route("/post/<int:post_id>")
def view_post(post_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM posts WHERE id=?", (post_id,))
    post = cursor.fetchone()

    conn.close()

    if not post:
        flash("Post not found", "error")
        return redirect(url_for("dashboard"))

    return render_template("view_post.html", post=post)


if __name__ == "__main__":
    app.run(debug=True)