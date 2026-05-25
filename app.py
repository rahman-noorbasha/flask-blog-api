from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
import sqlite3
import os
import secrets

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.secret_key = os.environ.get("SECRET_KEY","local-dev-secret-key")

# ensure upload folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

database_url = os.environ.get("DATABASE_URL")

if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "users.db")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    profile_pic TEXT,
    bio TEXT,
    github TEXT,
    linkedin TEXT,
    location TEXT,
    email TEXT UNIQUE,
    is_verified INTEGER DEFAULT 0,
    verification_token TEXT,
    reset_token TEXT
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
    cursor.execute("""
CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    post_id INTEGER
)
""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS followers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    follower_id INTEGER,
    following_id INTEGER
)
""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    actor_id INTEGER,
    type TEXT,
    post_id INTEGER,
    message TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

    cursor.execute("PRAGMA table_info(comments)")
    comment_columns = [column[1] for column in cursor.fetchall()]
    if "edited_at" not in comment_columns:
        cursor.execute("ALTER TABLE comments ADD COLUMN edited_at TIMESTAMP DEFAULT NULL")

    cursor.execute("PRAGMA table_info(users)")
    user_columns = [column[1] for column in cursor.fetchall()]
    if "profile_pic" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT")
    if "bio" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN bio TEXT")
    if "github" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN github TEXT")
    if "linkedin" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN linkedin TEXT")
    if "location" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN location TEXT")
    if "email" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")

    if "is_verified" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")

    if "verification_token" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
    if "reset_token" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
    conn.commit()
    conn.close()


#init_db()
def create_notification(user_id, actor_id, notification_type, post_id, message):
    if user_id == actor_id:
        return

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO notifications (user_id, actor_id, type, post_id, message)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, actor_id, notification_type, post_id, message)
    )

    conn.commit()
    conn.close()

@app.context_processor
def inject_notification_count():
    if current_user.is_authenticated:
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (current_user.id,)
        )

        unread_notifications = cursor.fetchone()[0]

        conn.close()

        return dict(unread_notifications=unread_notifications)

    return dict(unread_notifications=0)

# ---------------- USER CLASS ----------------
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.Text, nullable=False)
    profile_pic = db.Column(db.Text)
    bio = db.Column(db.Text)
    github = db.Column(db.Text)
    linkedin = db.Column(db.Text)
    location = db.Column(db.Text)
    email = db.Column(db.String(255), unique=True)
    is_verified = db.Column(db.Integer, default=0)
    verification_token = db.Column(db.Text)
    reset_token = db.Column(db.Text)
    
with app.app_context():
    db.create_all()

class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text)
    content = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    attachment = db.Column(db.Text)
class Like(db.Model):
    __tablename__ = "likes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"))


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)


class Bookmark(db.Model):
    __tablename__ = "bookmarks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"))

class Follower(db.Model):
    __tablename__ = "followers"

    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    following_id = db.Column(db.Integer, db.ForeignKey("users.id"))
with app.app_context():
    db.create_all()
    


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = generate_password_hash(request.form["password"])
        verification_token = secrets.token_hex(16)

        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash("Email already registered. Please login or use another email.", "error")
            return redirect(url_for("register"))

        existing_username = User.query.filter_by(username=username).first()
        if existing_username:
            flash("Username already exists", "error")
            return redirect(url_for("register"))

        new_user = User(
            username=username,
            email=email,
            password=password,
            verification_token=verification_token,
            is_verified=0
        )

        db.session.add(new_user)
        db.session.commit()

        verification_link = url_for(
            "verify_email",
            token=verification_token,
            _external=True
        )

        print("Verification link:", verification_link)

        flash("Registration successful! Please verify your email.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user:
            stored_password = user.password
            valid_password = False

            if stored_password.startswith("scrypt:") or stored_password.startswith("pbkdf2:"):
                valid_password = check_password_hash(stored_password, password)
            else:
                valid_password = stored_password == password

                if valid_password:
                    user.password = generate_password_hash(password)
                    db.session.commit()

            if valid_password:
                if user.email and user.is_verified == 0:
                    flash("Please verify your email before logging in.", "error")
                    return redirect(url_for("login"))

                login_user(user)
                return redirect(url_for("dashboard"))

        flash("Invalid credentials", "error")

    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    search = request.args.get("search", "")
    page = request.args.get("page", 1, type=int)
    per_page = 5

    query = Post.query.filter_by(user_id=current_user.id)

    if search:
        query = query.filter(
            (Post.title.like(f"%{search}%")) |
            (Post.content.like(f"%{search}%"))
        )

    total_posts = query.count()

    total_likes = 0
    total_comments = 0

    total_pages = max(1, (total_posts + per_page - 1) // per_page)

    if page < 1:
        page = 1

    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page

    posts = query.order_by(Post.created_at.desc()) \
                 .offset(offset) \
                 .limit(per_page) \
                 .all()

    post_data = []

    for post in posts:
        like_count = Like.query.filter_by(post_id=post.id).count()
        comment_count = Comment.query.filter_by(post_id=post.id).count()

        raw_comments = Comment.query.filter_by(post_id=post.id) \
                                    .order_by(Comment.created_at.desc()) \
                                    .all()

        comments = []

        for c in raw_comments:
            comment_user = User.query.get(c.user_id)

            comments.append({
                "id": c.id,
                "content": c.content,
                "user_id": c.user_id,
                "username": comment_user.username if comment_user else "Unknown",
                "edited_at": c.edited_at
            })

        post_dict = {
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "user_id": post.user_id,
            "created_at": post.created_at,
            "attachment": post.attachment,
            "is_image_attachment": bool(post.attachment) and post.attachment.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            )
        }

        is_bookmarked = Bookmark.query.filter_by(
            user_id=current_user.id,
            post_id=post.id
        ).first() is not None

        post_data.append(
            (
                post_dict,
                like_count,
                comment_count,
                comments,
                is_bookmarked
            )
        )

        total_likes += like_count
        total_comments += comment_count

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
        
        

        new_post = Post(
        title=title,
        content=content,
        user_id=current_user.id,
        attachment=filename
        )

        db.session.add(new_post)
        db.session.commit()

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
    post = Post.query.filter_by(
        id=post_id,
        user_id=current_user.id
    ).first()

    if not post:
        flash("Post not found or access denied.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        title = request.form.get("title", "")
        content = request.form.get("content", "")
        file = request.files.get("attachment")

        filename = post.attachment

        if file and getattr(file, "filename", None):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        post.title = title
        post.content = content
        post.attachment = filename

        db.session.commit()

        flash("Post updated successfully.", "success")
        return redirect(url_for("dashboard"), code=303)

    return render_template(
        "create_post.html",
        action_url=url_for("edit_post", post_id=post_id),
        page_title="Edit Post",
        header_title="Edit Post",
        header_desc="Update your blog post content.",
        btn_text="Save Changes",
        title_value=post.title,
        content_value=post.content,
        form_method="POST"
    )

@app.route("/delete/<int:post_id>", methods=["POST"])
@login_required
def delete_post(post_id):

    post = Post.query.filter_by(
        id=post_id,
        user_id=current_user.id
    ).first()

    if not post:
        flash("Post not found or access denied.", "error")
        return redirect(url_for("dashboard"), code=303)

    db.session.delete(post)
    db.session.commit()

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

    cursor.execute(
        "SELECT id FROM posts WHERE user_id=?",
        (current_user.id,)
    )
    post_ids = [row[0] for row in cursor.fetchall()]

    if post_ids:
        placeholders = ",".join("?" for _ in post_ids)
        cursor.execute(f"DELETE FROM likes WHERE post_id IN ({placeholders})", post_ids)
        cursor.execute(f"DELETE FROM comments WHERE post_id IN ({placeholders})", post_ids)
        cursor.execute(f"DELETE FROM bookmarks WHERE post_id IN ({placeholders})", post_ids)
        cursor.execute(f"DELETE FROM notifications WHERE post_id IN ({placeholders})", post_ids)

    cursor.execute(
        "DELETE FROM likes WHERE user_id=?",
        (current_user.id,)
    )
    cursor.execute(
        "DELETE FROM comments WHERE user_id=?",
        (current_user.id,)
    )
    cursor.execute(
        "DELETE FROM bookmarks WHERE user_id=?",
        (current_user.id,)
    )
    cursor.execute(
        "DELETE FROM followers WHERE follower_id=? OR following_id=?",
        (current_user.id, current_user.id)
    )
    cursor.execute(
        "DELETE FROM notifications WHERE user_id=? OR actor_id=?",
        (current_user.id, current_user.id)
    )

    cursor.execute(
        "DELETE FROM posts WHERE user_id=?",
        (current_user.id,)
    )

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

    post = Post.query.get(post_id)

    if not post:
        return jsonify({
            "success": False,
            "message": "Post not found"
        }), 404

    existing_like = Like.query.filter_by(
        user_id=current_user.id,
        post_id=post_id
    ).first()

    if existing_like:
        db.session.delete(existing_like)

    else:
        new_like = Like(
            user_id=current_user.id,
            post_id=post_id
        )

        db.session.add(new_like)

    db.session.commit()

    like_count = Like.query.filter_by(post_id=post_id).count()

    return jsonify({
        "success": True,
        "likes": like_count
    })

@app.route("/comment/<int:post_id>", methods=["POST"])
@login_required
def comment_post(post_id):
    content = request.form.get("comment", "").strip()

    if not content:
        return jsonify({"success": False})

    post = Post.query.get(post_id)

    if not post:
        return jsonify({
            "success": False,
            "message": "Post not found"
        }), 404

    new_comment = Comment(
        content=content,
        user_id=current_user.id,
        post_id=post_id
    )

    db.session.add(new_comment)
    db.session.commit()

    comment_count = Comment.query.filter_by(post_id=post_id).count()

    return jsonify({
        "success": True,
        "comment_id": new_comment.id,
        "username": current_user.username,
        "comment_count": comment_count,
        "comment": content
    })

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
    SELECT posts.id,
           posts.title,
           posts.content,
           posts.user_id,
           posts.created_at,
           posts.attachment,
           users.username,

           CASE
               WHEN posts.user_id IN (
                   SELECT following_id
                   FROM followers
                   WHERE follower_id=?
               )
               THEN 1
               ELSE 0
           END AS priority

    FROM posts
    JOIN users ON posts.user_id = users.id

    ORDER BY priority DESC, posts.created_at DESC
""", (current_user.id,))
    
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
        cursor.execute(
        "SELECT * FROM bookmarks WHERE user_id=? AND post_id=?",
        (current_user.id, post_id,)
)
        is_bookmarked = cursor.fetchone() is not None

        posts.append({
            "id": p[0],
            "title": p[1],
            "content": p[2],
            "user_id": p[3],
            "created_at": p[4],
            "attachment": p[5],
            "is_image_attachment": bool(p[5]) and p[5].lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")),
            "username": p[6],
            "priority": p[7],
            "like_count": like_count,
            "comment_count": comment_count,
            "comments": comments,
            "is_bookmarked": is_bookmarked
        })

    conn.close()

    return render_template(
        "feed.html",
        posts=posts,
        page_title="Public Feed",
        subtitle="Browse the latest public posts in a clean, friendly feed designed for easy reading.",
        empty_message="No public posts are available yet. Create a new post from your dashboard and check back soon.",
        show_saved_link=True
    )

@app.route("/saved")
@login_required
def saved_posts():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT posts.id, posts.title, posts.content, posts.user_id, posts.created_at, posts.attachment, users.username
        FROM bookmarks
        JOIN posts ON bookmarks.post_id = posts.id
        JOIN users ON posts.user_id = users.id
        WHERE bookmarks.user_id = ?
        ORDER BY bookmarks.id DESC
    """, (current_user.id,))

    raw_posts = cursor.fetchall()
    posts = []
    for p in raw_posts:
        post_id = p[0]
        cursor.execute("SELECT COUNT(*) FROM likes WHERE post_id=?", (post_id,))
        like_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM comments WHERE post_id=?", (post_id,))
        comment_count = cursor.fetchone()[0]

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
            "is_image_attachment": bool(p[5]) and p[5].lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")),
            "username": p[6],
            "like_count": like_count,
            "comment_count": comment_count,
            "comments": comments,
            "is_bookmarked": True
        })

    conn.close()

    return render_template(
        "feed.html",
        posts=posts,
        page_title="Saved Posts",
        subtitle="All the posts you saved are collected here for quick reading.",
        empty_message="You have not saved any posts yet. Browse the public feed and tap Save on posts you want to keep.",
        show_saved_link=False
    )
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
    cursor.execute(
    "SELECT COUNT(*) FROM followers WHERE following_id=?",
    (user[0],)
)
    followers_count = cursor.fetchone()[0]

    cursor.execute(
    "SELECT COUNT(*) FROM followers WHERE follower_id=?",
    (user[0],)
)
    following_count = cursor.fetchone()[0]

    cursor.execute(
    "SELECT * FROM followers WHERE follower_id=? AND following_id=?",
    (current_user.id, user[0])
)
    is_following = cursor.fetchone() is not None

    cursor.execute("""
        SELECT * FROM posts
        WHERE user_id=?
        ORDER BY created_at DESC
    """, (user[0],))
    raw_posts = cursor.fetchall()
    posts = []

    for post in raw_posts:
        post_id = post[0]
        cursor.execute("SELECT COUNT(*) FROM likes WHERE post_id=?", (post_id,))
        like_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM comments WHERE post_id=?", (post_id,))
        comment_count = cursor.fetchone()[0]
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
        for comment in raw_comments:
            comments.append({
                "id": comment[0],
                "content": comment[1],
                "user_id": comment[2],
                "username": comment[3],
                "edited_at": comment[4]
            })

        cursor.execute(
            "SELECT * FROM bookmarks WHERE user_id=? AND post_id=?",
            (current_user.id, post_id)
        )

        posts.append({
            "id": post[0],
            "title": post[1],
            "content": post[2],
            "user_id": post[3],
            "created_at": post[4],
            "attachment": post[5],
            "is_image_attachment": bool(post[5]) and post[5].lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")),
            "like_count": like_count,
            "comment_count": comment_count,
            "comments": comments,
            "is_bookmarked": cursor.fetchone() is not None
        })
    conn.close()

    return render_template(
        "profile.html",
        user=user,
        total_posts=total_posts,
        total_likes=total_likes,
        posts=posts,
        followers_count=followers_count,
        following_count=following_count,
        is_following=is_following
    )
@app.route("/comment/edit/<int:comment_id>", methods=["POST"])
@login_required
def edit_comment(comment_id):
    new_content = request.form.get("comment", "").strip()

    if not new_content:
        return jsonify({
            "success": False,
            "message": "Comment cannot be empty"
        })

    comment = Comment.query.get(comment_id)

    if not comment:
        return jsonify({
            "success": False,
            "message": "Comment not found"
        })

    if comment.user_id != current_user.id:
        return jsonify({
            "success": False,
            "message": "Not allowed"
        })

    comment.content = new_content
    comment.edited_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        "success": True,
        "comment": new_content,
        "edited": True
    })

@app.route("/delete-comment/<int:comment_id>", methods=["POST"])
@login_required
def delete_comment(comment_id):

    comment = Comment.query.get(comment_id)

    if not comment:
        return jsonify({"success": False})

    post = Post.query.get(comment.post_id)

    if not post:
        return jsonify({"success": False})

    if current_user.id == comment.user_id or current_user.id == post.user_id:
        post_id = comment.post_id

        db.session.delete(comment)
        db.session.commit()

        comment_count = Comment.query.filter_by(post_id=post_id).count()

        return jsonify({
            "success": True,
            "comment_count": comment_count
        })

    return jsonify({"success": False})

@app.route("/bookmark/<int:post_id>", methods=["POST"])
@login_required
def bookmark_post(post_id):

    post = Post.query.get(post_id)

    if not post:
        return {
            "success": False,
            "message": "Post not found"
        }, 404

    existing_bookmark = Bookmark.query.filter_by(
        user_id=current_user.id,
        post_id=post_id
    ).first()

    if existing_bookmark:
        db.session.delete(existing_bookmark)
        bookmarked = False

    else:
        new_bookmark = Bookmark(
            user_id=current_user.id,
            post_id=post_id
        )

        db.session.add(new_bookmark)
        bookmarked = True

    db.session.commit()

    return {
        "success": True,
        "bookmarked": bookmarked
    }

@app.route("/upload-profile-pic", methods=["POST"])
@login_required
def upload_profile_pic():
    file = request.files.get("profile_pic")

    if file and file.filename:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        current_user.profile_pic = filename
        db.session.commit()

        flash("Profile picture updated successfully.", "success")

    return redirect(url_for("user_profile", username=current_user.username))

@app.route("/follow/<int:user_id>", methods=["POST"])
@login_required
def follow_user(user_id):
    if user_id == current_user.id:
        return {"success": False, "message": "You cannot follow yourself"}

    user_to_follow = User.query.get(user_id)

    if not user_to_follow:
        return {"success": False, "message": "User not found"}, 404

    existing_follow = Follower.query.filter_by(
        follower_id=current_user.id,
        following_id=user_id
    ).first()

    if existing_follow:
        db.session.delete(existing_follow)
        following = False

    else:
        new_follow = Follower(
            follower_id=current_user.id,
            following_id=user_id
        )

        db.session.add(new_follow)
        following = True

    db.session.commit()

    followers_count = Follower.query.filter_by(
        following_id=user_id
    ).count()

    return {
        "success": True,
        "following": following,
        "followers_count": followers_count
    }

@app.route("/notifications")
@login_required
def notifications():
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            notifications.id,
            notifications.message,
            notifications.created_at,
            users.username AS actor_username
        FROM notifications
        JOIN users ON notifications.actor_id = users.id
        WHERE notifications.user_id=?
        ORDER BY notifications.created_at DESC
        """,
        (current_user.id,)
    )

    notifications = cursor.fetchall()

    cursor.execute(
    "UPDATE notifications SET is_read=1 WHERE user_id=?",
    (current_user.id,)
)
    conn.commit()
    conn.close()

    return render_template("notifications.html", notifications=notifications)

@app.route("/delete-notification/<int:notification_id>", methods=["POST"])
@login_required
def delete_notification(notification_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM notifications WHERE id=? AND user_id=?",
        (notification_id, current_user.id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("notifications"))

@app.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():

    if request.method == "POST":
        current_user.bio = request.form.get("bio")
        current_user.github = request.form.get("github")
        current_user.linkedin = request.form.get("linkedin")
        current_user.location = request.form.get("location")

        db.session.commit()

        flash("Profile updated successfully", "success")

        return redirect(
            url_for(
                "user_profile",
                username=current_user.username
            )
        )

    return render_template(
        "edit_profile.html",
        user=current_user
    )

@app.route("/verify-email/<token>")
def verify_email(token):
    print("TOKEN FROM URL:", token)

    user = User.query.filter_by(verification_token=token).first()

    print("USER FOUND:", user)

    if user:
        user.is_verified = 1
        user.verification_token = None

        db.session.commit()

        flash("Email verified successfully. You can now login.", "success")
        return redirect(url_for("login"))

    flash("Invalid or expired verification link.", "error")
    return redirect(url_for("login"))


@app.route("/resend-verification", methods=["POST"])
def resend_verification():
    email = request.form.get("email", "")

    user = User.query.filter_by(email=email).first()

    if not user:
        flash("No account found with this email.", "error")
        return redirect(url_for("login"))

    if user.is_verified == 1:
        flash("This email is already verified. Please login.", "success")
        return redirect(url_for("login"))

    new_token = secrets.token_hex(16)

    user.verification_token = new_token

    db.session.commit()

    verification_link = url_for(
        "verify_email",
        token=new_token,
        _external=True
    )

    print("New verification link:", verification_link)

    flash("New verification link generated. Check terminal for now.", "success")
    return redirect(url_for("login"))

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "")

        print("EMAIL ENTERED:", email)

        user = User.query.filter_by(email=email).first()

        print("USER FOUND:", user)

        if user:
            reset_token = secrets.token_hex(16)

            user.reset_token = reset_token

            db.session.commit()

            reset_link = url_for(
                "reset_password",
                token=reset_token,
                _external=True
            )

            print("Password reset link:", reset_link)

        flash(
            "If this email exists, a password reset link has been generated.",
            "success"
        )

        return redirect(url_for("login"))

    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):

    user = User.query.filter_by(reset_token=token).first()

    if not user:
        flash("Invalid or expired reset link.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        new_password = request.form.get("password")

        user.password = generate_password_hash(new_password)
        user.reset_token = None

        db.session.commit()

        flash("Password reset successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")

if __name__ == "__main__":
    app.run(debug=True)
