from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.secret_key = os.environ.get("SECRET_KEY","local-dev-secret-key")

# ensure upload folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    edited_at TIMESTAMP DEFAULT NULL
)
""")

    cursor.execute("PRAGMA table_info(comments)")
    comment_columns = [column[1] for column in cursor.fetchall()]
    if "edited_at" not in comment_columns:
        cursor.execute("ALTER TABLE comments ADD COLUMN edited_at TIMESTAMP DEFAULT NULL")

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
    try:
        uid = int(user_id)
    except Exception:
        conn.close()
        return None

    cursor.execute("SELECT * FROM users WHERE id=?", (uid,))
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
        password = generate_password_hash(request.form["password"])

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
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        )

        user = cursor.fetchone()

        if user:
            stored_password = user[2]

            if stored_password.startswith("scrypt:") or stored_password.startswith("pbkdf2:"):
                valid_password = check_password_hash(stored_password, password)
            else:
                valid_password = stored_password == password

                if valid_password:
                    new_hash = generate_password_hash(password)

                    cursor.execute(
                        "UPDATE users SET password=? WHERE id=?",
                        (new_hash, user[0])
                    )

                    conn.commit()

            if valid_password:
                conn.close()
                login_user(User(user[0], user[1]))
                return redirect(url_for("dashboard"))

        conn.close()
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
        cursor.execute(
            "SELECT COUNT(*) FROM likes WHERE post_id IN (SELECT id FROM posts WHERE user_id=? AND (title LIKE ? OR content LIKE ?))",
            (
                current_user.id,
                f'%{search}%',
                f'%{search}%'
            )
        )
        total_likes = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM comments WHERE post_id IN (SELECT id FROM posts WHERE user_id=? AND (title LIKE ? OR content LIKE ?))",
            (
                current_user.id,
                f'%{search}%',
                f'%{search}%'
            )
        )
        total_comments = cursor.fetchone()[0]
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
        cursor.execute(
            "SELECT COUNT(*) FROM likes WHERE post_id IN (SELECT id FROM posts WHERE user_id=?)",
            (current_user.id,)
        )
        total_likes = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM comments WHERE post_id IN (SELECT id FROM posts WHERE user_id=?)",
            (current_user.id,)
        )
        total_comments = cursor.fetchone()[0]
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
        cursor.execute(
            """
            SELECT comments.content, users.username
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.post_id=?
            ORDER BY comments.created_at DESC
            """,
            (post[0],)
        )
        cursor.execute(
            """
            SELECT comments.id, comments.content, comments.user_id, users.username, comments.edited_at
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.post_id=?
            ORDER BY comments.created_at DESC
            """,
            (post[0],)
        )
        raw_comments = cursor.fetchall()

        # convert post tuple and comments to dicts for easier template use
        post_dict = {
            "id": post[0],
            "title": post[1],
            "content": post[2],
            "user_id": post[3],
            "created_at": post[4],
            "attachment": post[5]
        }

        comments = []
        for c in raw_comments:
            comments.append({
                "id": c[0],
                "content": c[1],
                "user_id": c[2],
                "username": c[3],
                "edited_at": c[4]
            })

        post_data.append((post_dict, like_count, comment_count, comments))
    conn.close()

    return render_template(
        "dashboard.html",
        posts=post_data,
        search=search,
        total_posts=total_posts,
        total_likes=total_likes,
        total_comments=total_comments,
        total_pages=total_pages,
        page=page
    )


@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        title = request.form.get("title", "")
        content = request.form.get("content", "")
        file = request.files.get("attachment")
        filename = None

        if file and getattr(file, 'filename', None):
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
        title = request.form.get("title", "")
        content = request.form.get("content", "")
        file = request.files.get("attachment")
        filename = post[5]
        if file and getattr(file, 'filename', None):
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
    cursor.execute(
        "SELECT COUNT(*) FROM likes WHERE post_id=?",
        (post_id,)
    )
    like_count = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        "success": True,
        "likes": like_count
    })
@app.route("/comment/<int:post_id>", methods=["POST"])
@login_required
def comment_post(post_id):
    content = request.form.get("comment", "")

    if content and content.strip():
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO comments (content, user_id, post_id)
            VALUES (?, ?, ?)
            """,
            (content, current_user.id, post_id)
        )
        comment_id = cursor.lastrowid

        conn.commit()
        cursor.execute(
            "SELECT COUNT(*) FROM comments WHERE post_id=?",
            (post_id,)
        )
        comment_count = cursor.fetchone()[0]

        conn.close()

        return jsonify({
            "success": True,
            "comment_id": comment_id,
            "username": current_user.username,
            "comment_count": comment_count,
            "comment": content
        })

    return jsonify({"success": False})

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
@app.route("/feed")
@login_required
def feed():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT posts.id, posts.title, posts.content, posts.user_id, posts.created_at, posts.attachment, users.username
        FROM posts
        JOIN users ON posts.user_id = users.id
        ORDER BY posts.created_at DESC
    """)

    raw_posts = cursor.fetchall()
    posts = []
    for p in raw_posts:
        post_id = p[0]
        cursor.execute("SELECT COUNT(*) FROM likes WHERE post_id=?", (post_id,))
        like_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM comments WHERE post_id=?", (post_id,))
        comment_count = cursor.fetchone()[0]

        # load recent comments for the post
        cursor.execute(
            """
            SELECT comments.id, comments.content, comments.user_id, users.username, comments.edited_at
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.post_id=?
            ORDER BY comments.created_at DESC
            """,
            (post_id,)
        )
        raw_comments = cursor.fetchall()
        comments = []
        for c in raw_comments:
            comments.append({
                "id": c[0],
                "content": c[1],
                "user_id": c[2],
                "username": c[3],
                "edited_at": c[4]
            })

        posts.append({
            "id": p[0],
            "title": p[1],
            "content": p[2],
            "user_id": p[3],
            "created_at": p[4],
            "attachment": p[5],
            "username": p[6],
            "like_count": like_count,
            "comment_count": comment_count,
            "comments": comments
        })

    conn.close()

    return render_template("feed.html", posts=posts)
@app.route("/user/<username>")
@login_required
def user_profile(username):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE username=?", (username,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        flash("User not found", "error")
        return redirect(url_for("feed"))

    cursor.execute(
        "SELECT COUNT(*) FROM posts WHERE user_id=?",
        (user[0],)
    )
    total_posts = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM likes
        WHERE post_id IN (
            SELECT id FROM posts WHERE user_id=?
        )
    """, (user[0],))
    total_likes = cursor.fetchone()[0]

    cursor.execute("""
        SELECT * FROM posts
        WHERE user_id=?
        ORDER BY created_at DESC
    """, (user[0],))
    posts = cursor.fetchall()

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        total_posts=total_posts,
        total_likes=total_likes,
        posts=posts
    )
@app.route("/comment/edit/<int:comment_id>", methods=["POST"])
@login_required
def edit_comment(comment_id):
    new_content = request.form.get("comment", "").strip()

    if not new_content:
        return jsonify({"success": False, "message": "Comment cannot be empty"})

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM comments WHERE id=?", (comment_id,))
    comment = cursor.fetchone()

    if not comment:
        conn.close()
        return jsonify({"success": False, "message": "Comment not found"})

    if comment[0] != current_user.id:
        conn.close()
        return jsonify({"success": False, "message": "Not allowed"})

    cursor.execute(
        "UPDATE comments SET content=?, edited_at=datetime('now') WHERE id=?",
        (new_content, comment_id)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "comment": new_content,
        "edited": True
    })
@app.route("/delete-comment/<int:comment_id>", methods=["POST"])
@login_required
def delete_comment(comment_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT comments.user_id, posts.user_id, comments.post_id
        FROM comments
        JOIN posts ON comments.post_id = posts.id
        WHERE comments.id=?
        """,
        (comment_id,)
    )

    comment = cursor.fetchone()

    if not comment:
        conn.close()
        return jsonify({"success": False})

    comment_owner_id = comment[0]
    post_owner_id = comment[1]
    post_id = comment[2]

    if current_user.id == comment_owner_id or current_user.id == post_owner_id:
        cursor.execute(
            "DELETE FROM comments WHERE id=?",
            (comment_id,)
        )
        conn.commit()
        cursor.execute(
            "SELECT COUNT(*) FROM comments WHERE post_id=?",
            (post_id,)
        )
        comment_count = cursor.fetchone()[0]

        conn.close()
        return jsonify({"success": True, "comment_count": comment_count})

    conn.close()
    return jsonify({"success": False})

if __name__ == "__main__":
    app.run(debug=True)
