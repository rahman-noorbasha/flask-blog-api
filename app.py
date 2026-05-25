from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
from flask_mail import Mail, Message
import os
import secrets

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_USERNAME")

mail = Mail(app)
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

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_USERNAME")

mail = Mail(app)

@app.context_processor
def inject_notification_count():
    if current_user.is_authenticated:
        unread_notifications = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=0
        ).count()

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
class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    type = db.Column(db.Text)
    post_id = db.Column(db.Integer, nullable=True)
    message = db.Column(db.Text)
    is_read = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
with app.app_context():
    db.create_all()

def send_email(to, subject, body):
    msg = Message(
        subject,
        recipients=[to]
    )

    msg.body = body

    mail.send(msg)
    


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

        send_email(
    email,
    "Verify Your Email",
    f"Click the link to verify your account:\n\n{verification_link}"
)

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
    user_id = current_user.id

    user_posts = Post.query.filter_by(user_id=user_id).all()
    post_ids = [post.id for post in user_posts]

    if post_ids:
        Like.query.filter(Like.post_id.in_(post_ids)).delete(synchronize_session=False)
        Comment.query.filter(Comment.post_id.in_(post_ids)).delete(synchronize_session=False)
        Bookmark.query.filter(Bookmark.post_id.in_(post_ids)).delete(synchronize_session=False)
        Notification.query.filter(Notification.post_id.in_(post_ids)).delete(synchronize_session=False)

    Like.query.filter_by(user_id=user_id).delete()
    Comment.query.filter_by(user_id=user_id).delete()
    Bookmark.query.filter_by(user_id=user_id).delete()

    Follower.query.filter(
        (Follower.follower_id == user_id) |
        (Follower.following_id == user_id)
    ).delete(synchronize_session=False)

    Notification.query.filter(
        (Notification.user_id == user_id) |
        (Notification.actor_id == user_id)
    ).delete(synchronize_session=False)

    Post.query.filter_by(user_id=user_id).delete()

    user = db.session.get(User, user_id)

    logout_user()

    if user:
        db.session.delete(user)

    db.session.commit()

    flash("Your account has been deleted successfully.", "success")
    return redirect(url_for("login"))

@app.route("/like/<int:post_id>", methods=["POST"])
@login_required
def like_post(post_id):
    post = db.session.get(Post, post_id)

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

        if post.user_id != current_user.id:
            new_notification = Notification(
                user_id=post.user_id,
                actor_id=current_user.id,
                type="like",
                post_id=post_id,
                message=f"{current_user.username} liked your post"
            )
            db.session.add(new_notification)

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
    if post.user_id != current_user.id:
        new_notification = Notification(
            user_id=post.user_id,
            actor_id=current_user.id,
            type="comment",
            post_id=post_id,
            message=f"{current_user.username} commented on your post"
    )

        db.session.add(new_notification)
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
    post = db.session.get(Post, post_id)

    if not post:
        flash("Post not found", "error")
        return redirect(url_for("dashboard"))

    return render_template("view_post.html", post=post)

@app.route("/feed")
@login_required
def feed():

    followed_users = [
        f.following_id
        for f in Follower.query.filter_by(
            follower_id=current_user.id
        ).all()
    ]

    posts_query = Post.query.order_by(
        Post.created_at.desc()
    ).all()

    posts = []

    for post in posts_query:

        post_user = db.session.get(User, post.user_id)

        priority = 1 if post.user_id in followed_users else 0

        like_count = Like.query.filter_by(
            post_id=post.id
        ).count()

        comment_count = Comment.query.filter_by(
            post_id=post.id
        ).count()

        raw_comments = Comment.query.filter_by(
            post_id=post.id
        ).order_by(Comment.created_at.desc()).all()

        comments = []

        for c in raw_comments:

            comment_user = db.session.get(User, c.user_id)

            comments.append({
                "id": c.id,
                "content": c.content,
                "user_id": c.user_id,
                "username": comment_user.username if comment_user else "Unknown",
                "edited_at": c.edited_at
            })

        is_bookmarked = Bookmark.query.filter_by(
            user_id=current_user.id,
            post_id=post.id
        ).first() is not None

        posts.append({
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "user_id": post.user_id,
            "created_at": post.created_at,
            "attachment": post.attachment,
            "is_image_attachment": bool(post.attachment)
            and post.attachment.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            ),
            "username": post_user.username if post_user else "Unknown",
            "priority": priority,
            "like_count": like_count,
            "comment_count": comment_count,
            "comments": comments,
            "is_bookmarked": is_bookmarked
        })

    posts.sort(
        key=lambda p: (p["priority"], p["created_at"]),
        reverse=True
    )

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

    bookmarks = Bookmark.query.filter_by(
        user_id=current_user.id
    ).order_by(Bookmark.id.desc()).all()

    posts = []

    for bookmark in bookmarks:

        post = db.session.get(Post, bookmark.post_id)

        if not post:
            continue

        post_user = db.session.get(User, post.user_id)

        like_count = Like.query.filter_by(
            post_id=post.id
        ).count()

        comment_count = Comment.query.filter_by(
            post_id=post.id
        ).count()

        raw_comments = Comment.query.filter_by(
            post_id=post.id
        ).order_by(Comment.created_at.desc()).all()

        comments = []

        for c in raw_comments:
            comment_user = db.session.get(User, c.user_id)

            comments.append({
                "id": c.id,
                "content": c.content,
                "user_id": c.user_id,
                "username": comment_user.username if comment_user else "Unknown",
                "edited_at": c.edited_at
            })

        posts.append({
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "user_id": post.user_id,
            "created_at": post.created_at,
            "attachment": post.attachment,
            "is_image_attachment": bool(post.attachment)
            and post.attachment.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            ),
            "username": post_user.username if post_user else "Unknown",
            "like_count": like_count,
            "comment_count": comment_count,
            "comments": comments,
            "is_bookmarked": True
        })

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

    user = User.query.filter_by(username=username).first()

    if not user:
        flash("User not found", "error")
        return redirect(url_for("feed"))

    total_posts = Post.query.filter_by(user_id=user.id).count()

    user_posts = Post.query.filter_by(
        user_id=user.id
    ).order_by(Post.created_at.desc()).all()

    total_likes = 0
    posts = []

    followers_count = Follower.query.filter_by(
        following_id=user.id
    ).count()

    following_count = Follower.query.filter_by(
        follower_id=user.id
    ).count()

    is_following = Follower.query.filter_by(
        follower_id=current_user.id,
        following_id=user.id
    ).first() is not None

    for post in user_posts:

        like_count = Like.query.filter_by(post_id=post.id).count()
        comment_count = Comment.query.filter_by(post_id=post.id).count()

        total_likes += like_count

        raw_comments = Comment.query.filter_by(
            post_id=post.id
        ).order_by(Comment.created_at.desc()).all()

        comments = []

        for comment in raw_comments:
            comment_user = db.session.get(User, comment.user_id)

            comments.append({
                "id": comment.id,
                "content": comment.content,
                "user_id": comment.user_id,
                "username": comment_user.username if comment_user else "Unknown",
                "edited_at": comment.edited_at
            })

        is_bookmarked = Bookmark.query.filter_by(
            user_id=current_user.id,
            post_id=post.id
        ).first() is not None

        posts.append({
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "user_id": post.user_id,
            "created_at": post.created_at,
            "attachment": post.attachment,
            "is_image_attachment": bool(post.attachment)
            and post.attachment.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp")
            ),
            "like_count": like_count,
            "comment_count": comment_count,
            "comments": comments,
            "is_bookmarked": is_bookmarked
        })

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

    user_to_follow = db.session.get(User, user_id)

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

        new_notification = Notification(
            user_id=user_id,
            actor_id=current_user.id,
            type="follow",
            post_id=None,
            message=f"{current_user.username} started following you"
        )

        db.session.add(new_notification)

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

    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()

    for notification in notifications:
        notification.is_read = 1

    db.session.commit()

    notification_data = []

    for n in notifications:
        actor = db.session.get(User, n.actor_id)

        notification_data.append({
            "id": n.id,
            "message": n.message,
            "created_at": n.created_at,
            "actor_username": actor.username if actor else "Unknown"
        })

    return render_template(
        "notifications.html",
        notifications=notification_data
    )


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

            send_email(
    email,
    "Reset Your Password",
    f"Click the link below to reset your password:\n\n{reset_link}"
)

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
