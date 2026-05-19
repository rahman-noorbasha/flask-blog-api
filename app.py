from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")

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
        user_id INTEGER
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
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM posts WHERE user_id=?",
        (current_user.id,)
    )

    posts = cursor.fetchall()
    conn.close()

    return render_template("dashboard.html", posts=posts)


@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO posts (title, content, user_id) VALUES (?, ?, ?)",
            (title, content, current_user.id)
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

        cursor.execute(
            "UPDATE posts SET title=?, content=? WHERE id=? AND user_id=?",
            (title, content, post_id, current_user.id)
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


if __name__ == "__main__":
    app.run(debug=True)