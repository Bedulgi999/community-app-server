
import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request, session, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, Post, Comment, PostLike, Follow, Notification
from forms import RegisterForm, LoginForm, PostForm, CommentForm, ProfileForm

ALLOWED_EXTENSIONS = {"png","jpg","jpeg","gif","webp"}

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    @app.context_processor
    def inject_now():
        return {"now": datetime.utcnow()}

    def current_user():
        uid = session.get("uid")
        return User.query.get(uid) if uid else None

    def allowed_file(filename):
        return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS

    def save_file(file):
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            final = f"{int(datetime.utcnow().timestamp())}_{name}{ext}"
            path = os.path.join(app.config["UPLOAD_FOLDER"], final)
            file.save(path)
            return final
        return None

    def notify(user_id, type_, actor_id, message, post_id=None, comment_id=None):
        if user_id == actor_id:
            return
        n = Notification(user_id=user_id, type=type_, actor_id=actor_id, message=message,
                         post_id=post_id, comment_id=comment_id)
        db.session.add(n)
        db.session.commit()

    @app.route("/")
    def index():
        mode = request.args.get("mode", "all")
        user = current_user()
        if mode == "following" and user:
            subq = db.session.query(Follow.followed_id).filter(Follow.follower_id == user.id).subquery()
            posts = Post.query.filter(Post.user_id.in_(subq)).order_by(Post.created_at.desc()).limit(50).all()
        else:
            posts = Post.query.order_by(Post.created_at.desc()).limit(50).all()
        return render_template("index.html", user=user, posts=posts, mode=mode)

    @app.route("/register", methods=["GET","POST"])
    def register():
        if current_user():
            return redirect(url_for("index"))
        form = RegisterForm()
        if form.validate_on_submit():
            if User.query.filter((User.username == form.username.data) | (User.email == form.email.data)).first():
                flash("Username or email already exists.", "danger")
                return render_template("register.html", form=form, user=current_user())
            u = User(username=form.username.data.strip(), email=form.email.data.strip(),
                     password_hash=generate_password_hash(form.password.data))
            db.session.add(u); db.session.commit()
            flash("Registration complete. Please log in.", "success")
            return redirect(url_for("login"))
        return render_template("register.html", form=form, user=current_user())

    @app.route("/login", methods=["GET","POST"])
    def login():
        if current_user():
            return redirect(url_for("index"))
        form = LoginForm()
        if form.validate_on_submit():
            u = User.query.filter_by(username=form.username.data).first()
            if not u or not check_password_hash(u.password_hash, form.password.data):
                flash("Invalid credentials.", "danger")
            else:
                session["uid"] = u.id
                flash(f"Welcome, {u.username}!", "success")
                return redirect(request.args.get("next") or url_for("index"))
        return render_template("login.html", form=form, user=current_user())

    @app.route("/logout")
    def logout():
        session.pop("uid", None)
        flash("Logged out.", "info")
        return redirect(url_for("index"))

    @app.route("/u/<username>", methods=["GET","POST"])
    def profile(username):
        profile_user = User.query.filter_by(username=username).first_or_404()
        form = ProfileForm()
        user = current_user()
        if user and user.id == profile_user.id and form.validate_on_submit():
            profile_user.bio = form.bio.data or ""
            if "avatar" in request.files:
                fn = save_file(request.files["avatar"])
                if fn: profile_user.avatar = fn
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("profile", username=username))
        if user and user.id == profile_user.id:
            form.bio.data = profile_user.bio
        posts = Post.query.filter_by(user_id=profile_user.id).order_by(Post.created_at.desc()).all()
        is_following = False
        if user:
            is_following = db.session.query(Follow).filter_by(follower_id=user.id, followed_id=profile_user.id).first() is not None
        return render_template("profile.html", user=user, profile_user=profile_user, posts=posts, form=form, is_following=is_following)

    @app.route("/follow/<username>")
    def follow(username):
        user = current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        target = User.query.filter_by(username=username).first_or_404()
        if target.id == user.id:
            flash("You cannot follow yourself.", "warning")
            return redirect(url_for("profile", username=username))
        exists = db.session.query(Follow).filter_by(follower_id=user.id, followed_id=target.id).first()
        if not exists:
            db.session.add(Follow(follower_id=user.id, followed_id=target.id)); db.session.commit()
            notify(target.id, "follow", user.id, f"{user.username} started following you.")
            flash(f"You are now following {target.username}.", "success")
        return redirect(url_for("profile", username=username))

    @app.route("/unfollow/<username>")
    def unfollow(username):
        user = current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        target = User.query.filter_by(username=username).first_or_404()
        db.session.query(Follow).filter_by(follower_id=user.id, followed_id=target.id).delete()
        db.session.commit()
        flash(f"Unfollowed {target.username}.", "info")
        return redirect(url_for("profile", username=username))

    @app.route("/post/new", methods=["GET","POST"])
    def post_new():
        user = current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        form = PostForm()
        if form.validate_on_submit():
            image_fn = save_file(request.files.get("image"))
            p = Post(user_id=user.id, title=form.title.data, body=form.body.data, image=image_fn)
            db.session.add(p); db.session.commit()
            flash("Post published.", "success")
            return redirect(url_for("index"))
        return render_template("post_edit.html", form=form, user=user, mode="new")

    @app.route("/post/<int:pid>")
    def post_detail(pid):
        p = Post.query.get_or_404(pid)
        form = CommentForm()
        user = current_user()
        liked = False
        if user:
            liked = db.session.query(PostLike).filter_by(user_id=user.id, post_id=p.id).first() is not None
        return render_template("post_detail.html", post=p, form=form, user=user, liked=liked)

    @app.route("/post/<int:pid>/edit", methods=["GET","POST"])
    def post_edit(pid):
        user = current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        p = Post.query.get_or_404(pid)
        if p.user_id != user.id and not user.is_admin:
            abort(403)
        form = PostForm()
        if request.method == "GET":
            form.title.data = p.title
            form.body.data = p.body
        if form.validate_on_submit():
            p.title = form.title.data
            p.body = form.body.data
            if request.files.get("image") and request.files["image"].filename:
                image_fn = save_file(request.files["image"])
                if image_fn: p.image = image_fn
            db.session.commit()
            flash("Post updated.", "success")
            return redirect(url_for("post_detail", pid=pid))
        return render_template("post_edit.html", form=form, user=user, mode="edit")

    @app.route("/post/<int:pid>/delete")
    def post_delete(pid):
        user = current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        p = Post.query.get_or_404(pid)
        if p.user_id != user.id and not user.is_admin:
            abort(403)
        db.session.delete(p); db.session.commit()
        flash("Post deleted.", "info")
        return redirect(url_for("index"))

    @app.route("/post/<int:pid>/comment", methods=["POST"])
    def comment_add(pid):
        user = current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        p = Post.query.get_or_404(pid)
        form = CommentForm()
        if form.validate_on_submit():
            c = Comment(post_id=p.id, user_id=user.id, body=form.body.data)
            db.session.add(c); db.session.commit()
            notify(p.user_id, "comment", user.id, f"{user.username} commented on your post.", post_id=p.id, comment_id=c.id)
            flash("Comment added.", "success")
        else:
            flash("Failed to add comment.", "danger")
        return redirect(url_for("post_detail", pid=pid))

    @app.route("/post/<int:pid>/like")
    def post_like(pid):
        user = current_user()
        if not user: return redirect(url_for("login", next=request.path))
        p = Post.query.get_or_404(pid)
        existing = db.session.query(PostLike).filter_by(user_id=user.id, post_id=p.id).first()
        if not existing:
            db.session.add(PostLike(user_id=user.id, post_id=p.id)); db.session.commit()
            notify(p.user_id, "like", user.id, f"{user.username} liked your post.", post_id=p.id)
        return redirect(url_for("post_detail", pid=pid))

    @app.route("/post/<int:pid>/unlike")
    def post_unlike(pid):
        user = current_user()
        if not user: return redirect(url_for("login", next=request.path))
        db.session.query(PostLike).filter_by(user_id=user.id, post_id=pid).delete()
        db.session.commit()
        return redirect(url_for("post_detail", pid=pid))

    @app.route("/notifications")
    def notifications():
        user = current_user()
        if not user: return redirect(url_for("login", next=request.path))
        items = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(100).all()
        return render_template("notifications.html", user=user, items=items)

    @app.route("/notifications/read_all")
    def notifications_read_all():
        user = current_user()
        if not user: return redirect(url_for("login", next=request.path))
        Notification.query.filter_by(user_id=user.id, is_read=False).update({"is_read": True})
        db.session.commit()
        flash("All notifications marked as read.", "success")
        return redirect(url_for("notifications"))

    @app.route("/dashboard")
    def dashboard():
        user = current_user()
        if not user: return redirect(url_for("login", next=request.path))
        if not user.is_admin: abort(403)
        users_count = User.query.count()
        posts_count = Post.query.count()
        comments_count = Comment.query.count()
        top_posts = (
            db.session.query(Post, db.func.count(PostLike.id).label("like_count"))
            .outerjoin(PostLike, PostLike.post_id == Post.id)
            .group_by(Post.id)
            .order_by(db.text("like_count DESC")).limit(10).all()
        )
        recent = Post.query.order_by(Post.created_at.desc()).limit(10).all()
        return render_template("dashboard.html", user=user, users_count=users_count, posts_count=posts_count,
                               comments_count=comments_count, top_posts=top_posts, recent=recent)

    @app.route("/uploads/<path:filename>")
    def uploads(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.route("/search")
    def search():
        q = request.args.get("q", "").strip()
        posts = []
        if q:
            like = f"%%{q}%%"
            posts = Post.query.filter((Post.title.ilike(like)) | (Post.body.ilike(like))).order_by(Post.created_at.desc()).limit(100).all()
        return render_template("index.html", user=current_user(), posts=posts, mode="search", q=q)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, message="Forbidden"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="Not found"), 404

    @app.errorhandler(413)
    def too_large(e):
        flash("File too large (max 10MB).", "danger")
        return redirect(request.referrer or url_for("index"))

    return app

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        from models import db
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
