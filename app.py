import os
import json
import uuid
import hashlib
import secrets
import threading
from datetime import datetime, timezone
from functools import wraps

import requests
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, send_from_directory,
    abort, Response
)

# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# CONNECTED FLASK PORTAL
# - Supabase PostgreSQL REST API
# - Supabase Storage
# - Local fallback
# - Student portal
# - Admin portal
# - System activity/security logs
# - Google Search Console
# ============================================================

app = Flask(__name__)
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_SECRET_IN_RENDER"
)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

SITE_URL = os.environ.get(
    "SITE_URL",
    "https://koja-africa.onrender.com"
).rstrip("/")

SITE_NAME = "KOJA AFRICA"
SITE_DESCRIPTION = (
    "KOJA AFRICA provides academic questions, assignment support, "
    "research assistance, learning resources and academic answers."
)

GOOGLE_VERIFICATION = "u4nfIf5MfXm0iVvECSQeYAov4Tz4601ayY5kYzNc4ko"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "koja_data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
STUDENT_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "student")
ADMIN_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "admin")

for d in (DATA_DIR, UPLOAD_DIR, STUDENT_UPLOAD_DIR, ADMIN_UPLOAD_DIR):
    os.makedirs(d, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.json")

LOCK = threading.Lock()

ADMIN_EMAIL = os.environ.get(
    "KOJA_ADMIN_EMAIL",
    "admin@koja.africa"
).strip().lower()

ADMIN_PASSWORD = os.environ.get(
    "KOJA_ADMIN_PASSWORD",
    "ChangeMe123!"
)

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    ""
).strip().rstrip("/")

SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    ""
).strip()

STORAGE_BUCKET = os.environ.get(
    "KOJA_STORAGE_BUCKET",
    "koja-files"
).strip()

ALLOWED_EXTENSIONS = {
    "pdf", "png", "jpg", "jpeg", "webp", "gif",
    "doc", "docx", "txt", "ppt", "pptx",
    "xls", "xlsx", "csv"
}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


# ============================================================
# GENERAL HELPERS
# ============================================================

def now():
    return datetime.now(timezone.utc).isoformat()


def esc(value):
    from markupsafe import escape
    return str(escape("" if value is None else value))


def ensure_file(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2, ensure_ascii=False)


ensure_file(USERS_FILE, [])
ensure_file(QUESTIONS_FILE, [])
ensure_file(LOGS_FILE, [])


def read_json(path):
    try:
        with LOCK:
            with open(path, "r", encoding="utf-8") as f:
                value = json.load(f)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def write_json(path, data):
    with LOCK:
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp, path)


# ============================================================
# SUPABASE
# ============================================================

def supabase_configured():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def supabase_headers(content_type=True):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": "Bearer " + SUPABASE_SERVICE_KEY
    }
    if content_type:
        headers["Content-Type"] = "application/json"
    return headers


def supabase_request(method, endpoint, data=None, timeout=10):
    if not supabase_configured():
        return None

    try:
        r = requests.request(
            method,
            SUPABASE_URL + endpoint,
            headers=supabase_headers(),
            json=data,
            timeout=timeout
        )
        if r.status_code >= 400:
            return None
        if not r.text:
            return {}
        return r.json()
    except Exception:
        return None


def supabase_insert(table, row):
    return supabase_request(
        "POST",
        "/rest/v1/" + table,
        row
    )


def supabase_update(table, key, value, row):
    return supabase_request(
        "PATCH",
        f"/rest/v1/{table}?id=eq.{value}",
        row
    )


def supabase_test():
    if not supabase_configured():
        return False
    try:
        r = requests.get(
            SUPABASE_URL + "/rest/v1/",
            headers=supabase_headers(False),
            timeout=5
        )
        return r.status_code < 400
    except Exception:
        return False


# ============================================================
# SYSTEM LOGGING
# ============================================================
#
# Every important KOJA event is written locally and, when
# Supabase is configured, also inserted into koja_logs.
#
# Suggested Supabase table:
#
# create table public.koja_logs (
#   id uuid primary key,
#   created_at timestamptz not null default now(),
#   level text not null,
#   category text not null,
#   user_id text,
#   user_email text,
#   action text not null,
#   details text,
#   ip_address text,
#   user_agent text
# );
#
# ============================================================

def client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def log_event(
    action,
    category="System",
    level="INFO",
    details="",
    user_id=None,
    user_email=None
):
    try:
        uid = user_id or session.get("user_id") or "system"
        email = user_email or session.get("email") or "system"

        entry = {
            "id": str(uuid.uuid4()),
            "created_at": now(),
            "level": level.upper(),
            "category": category,
            "user_id": str(uid),
            "user_email": str(email),
            "action": action,
            "details": str(details)[:2000],
            "ip_address": client_ip(),
            "user_agent": request.headers.get(
                "User-Agent", ""
            )[:1000]
        }

        logs = read_json(LOGS_FILE)
        logs.append(entry)

        # Keep the local fallback bounded.
        if len(logs) > 5000:
            logs = logs[-5000:]

        write_json(LOGS_FILE, logs)

        if supabase_configured():
            supabase_insert("koja_logs", entry)

    except Exception:
        # Logging must never crash the main application.
        pass


def logs():
    return read_json(LOGS_FILE)


# ============================================================
# PASSWORDS / USERS
# ============================================================

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        200000
    )
    return salt + "$" + digest.hex()


def verify_password(password, stored):
    try:
        salt, digest = stored.split("$", 1)
        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt.encode(),
            200000
        ).hex()
        return secrets.compare_digest(check, digest)
    except Exception:
        return False


def users():
    return read_json(USERS_FILE)


def find_user(email):
    email = (email or "").strip().lower()
    for user in users():
        if user.get("email", "").strip().lower() == email:
            return user
    return None


def create_admin():
    data = users()

    for user in data:
        if user.get("email", "").strip().lower() == ADMIN_EMAIL:
            user["role"] = "admin"
            user["name"] = "KOJA Administrator"
            if not user.get("password"):
                user["password"] = hash_password(ADMIN_PASSWORD)
            write_json(USERS_FILE, data)
            return

    data.append({
        "id": "ADMIN",
        "name": "KOJA Administrator",
        "email": ADMIN_EMAIL,
        "password": hash_password(ADMIN_PASSWORD),
        "role": "admin",
        "created_at": now()
    })
    write_json(USERS_FILE, data)


create_admin()


# ============================================================
# QUESTIONS
# ============================================================

def questions():
    return read_json(QUESTIONS_FILE)


def find_question(question_id):
    for q in questions():
        if str(q.get("id")) == str(question_id):
            return q
    return None


def save_questions(data):
    write_json(QUESTIONS_FILE, data)


def sync_question(question):
    if not supabase_configured():
        return

    row = {
        "id": question["id"],
        "student_id": question["student_id"],
        "student_name": question["student_name"],
        "student_email": question["student_email"],
        "subject": question["subject"],
        "question": question["question"],
        "status": question["status"],
        "answer": question.get("answer", ""),
        "created_at": question["created_at"],
        "answered_at": question.get("answered_at")
    }
    supabase_insert("koja_questions", row)


# ============================================================
# AUTH
# ============================================================

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def is_admin_session():
    return (
        session.get("role") == "admin"
        and session.get("email", "").strip().lower() == ADMIN_EMAIL
    )


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        if not is_admin_session():
            log_event(
                "Unauthorized Admin Access",
                "Security",
                "WARNING",
                request.path
            )
            flash("Administrator access required.", "error")
            return redirect(url_for("student_dashboard"))
        return fn(*args, **kwargs)
    return wrapper


# ============================================================
# FILES
# ============================================================

def extension_of(filename):
    filename = (filename or "").strip()
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def allowed_file(filename):
    return extension_of(filename) in ALLOWED_EXTENSIONS


def upload_to_supabase(local_path, storage_path, content_type):
    if not supabase_configured():
        return False

    try:
        with open(local_path, "rb") as f:
            r = requests.post(
                f"{SUPABASE_URL}/storage/v1/object/"
                f"{STORAGE_BUCKET}/{storage_path}",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": "Bearer " + SUPABASE_SERVICE_KEY,
                    "Content-Type": content_type,
                    "x-upsert": "false"
                },
                data=f,
                timeout=30
            )
        return r.status_code in (200, 201)
    except Exception:
        return False


def save_upload(file, category, question_id=None):
    if not file or not file.filename:
        return None

    original = file.filename.strip()

    if not allowed_file(original):
        log_event(
            "Upload Failed",
            "Storage",
            "ERROR",
            f"Invalid file type: {original}"
        )
        return None

    extension = extension_of(original)
    stored = str(uuid.uuid4()) + "." + extension

    if category == "student":
        directory = STUDENT_UPLOAD_DIR
    elif category == "admin":
        directory = ADMIN_UPLOAD_DIR
    else:
        return None

    destination = os.path.join(directory, stored)

    try:
        file.save(destination)
    except Exception as exc:
        log_event(
            "Upload Failed",
            "Storage",
            "ERROR",
            str(exc)
        )
        return None

    storage_path = (
        f"{category}/{question_id or 'general'}/{stored}"
    )

    # Best-effort Supabase Storage connection.
    supabase_uploaded = upload_to_supabase(
        destination,
        storage_path,
        file.mimetype or "application/octet-stream"
    )

    if supabase_uploaded:
        log_event(
            "File Uploaded",
            "Storage",
            "SUCCESS",
            f"{original} -> Supabase Storage"
        )
    else:
        log_event(
            "File Saved Locally",
            "Storage",
            "INFO",
            f"{original}; Supabase Storage unavailable"
        )

    return {
        "id": str(uuid.uuid4()),
        "original_name": original,
        "stored_name": stored,
        "category": category,
        "extension": extension,
        "is_image": extension in IMAGE_EXTENSIONS,
        "storage_path": storage_path,
        "supabase_uploaded": supabase_uploaded
    }


def save_multiple_uploads(files, category, question_id=None):
    result = []
    for file in files:
        saved = save_upload(
            file,
            category,
            question_id
        )
        if saved:
            result.append(saved)
    return result


def attachment_html(attachments, viewer, question_id=None):
    if not attachments:
        return '<div class="muted">No attachments.</div>'

    output = ""

    for a in attachments:
        stored = a.get("stored_name", "")
        if not stored:
            continue

        name = esc(a.get("original_name", "Attachment"))

        if viewer == "admin":
            route = f"/admin/file/{a.get('category')}/{stored}"
        else:
            route = (
                f"/student/file/{question_id}/"
                f"{a.get('category')}/{stored}"
            )

        preview = ""
        if a.get("is_image"):
            preview = (
                f'<img class="attachment-image" '
                f'src="{route}" alt="Uploaded file">'
            )

        output += f"""
        <div class="attachment">
            <strong>📎 {name}</strong>
            {preview}
            <br>
            <a class="btn small" href="{route}" target="_blank">
                Open File
            </a>
        </div>
        """

    return output


# ============================================================
# HTML
# ============================================================

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#101828">
<meta name="google-site-verification"
content="u4nfIf5MfXm0iVvECSQeYAov4Tz4601ayY5kYzNc4ko">
<meta name="description" content="{{ site_description }}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{{ canonical_url }}">
<title>{{ title }} - KOJA AFRICA</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f4f7fb;color:#172033;font-family:Arial,sans-serif}
nav{background:#101828;color:white;padding:14px 18px;display:flex;
justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
.logo{font-size:23px;font-weight:900}
.k{color:#2196f3}.o{color:#22c55e}.j{color:#ef4444}.a{color:#2563eb}
.navlinks{display:flex;gap:6px;flex-wrap:wrap}
nav a{color:white;text-decoration:none;padding:8px 11px;border-radius:7px}
nav a:hover{background:#26354d}
.container{width:94%;max-width:1200px;margin:25px auto}
.card{background:white;padding:22px;margin-bottom:20px;border-radius:14px;
box-shadow:0 5px 20px rgba(0,0,0,.06)}
.hero{background:linear-gradient(135deg,#101828,#2563eb);color:white;
padding:40px 28px;border-radius:18px;margin-bottom:20px}
.hero h1{font-size:40px;margin-top:0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:15px}
.stat{background:#eef4ff;padding:20px;border-radius:12px}
.stat h2{margin-top:0;font-size:30px}
input,textarea,select{width:100%;padding:12px;margin-top:7px;margin-bottom:15px;
border:1px solid #d0d5dd;border-radius:8px;font-size:15px}
textarea{min-height:190px;resize:vertical}
button,.btn{display:inline-block;background:#2563eb;color:white;border:0;
padding:11px 17px;border-radius:8px;text-decoration:none;cursor:pointer}
.green{background:#16a34a!important}.purple{background:#7c3aed!important}
.red{background:#dc2626!important}.small{padding:7px 10px;font-size:13px}
.auth{max-width:500px;margin:45px auto}
.alert{background:#dcfce7;color:#166534;padding:12px;border-radius:8px;margin-bottom:15px}
.alert.error{background:#fee2e2;color:#991b1b}
.muted{color:#667085}
.question{white-space:pre-wrap;line-height:1.7;background:#f8fafc;padding:16px;border-radius:9px}
.answer{white-space:pre-wrap;background:#f0fdf4;border-left:4px solid #16a34a;
padding:16px;border-radius:8px;line-height:1.7}
.badge{display:inline-block;padding:5px 10px;border-radius:20px;background:#e5e7eb;font-size:12px}
.pending{background:#ffedd5;color:#9a3412}.answered{background:#dcfce7;color:#166534}
.warning{background:#fef3c7;color:#92400e}.error-badge{background:#fee2e2;color:#991b1b}
.notice{padding:13px;border-radius:8px;background:#eff6ff;color:#1e40af;margin-bottom:15px}
.attachment{border:1px solid #e4e7ec;border-radius:10px;padding:13px;margin-top:10px}
.attachment-image{max-width:100%;max-height:450px;display:block;border-radius:8px;margin:10px 0}
table{width:100%;border-collapse:collapse}
th,td{padding:11px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}
th{background:#f8fafc}
.log-info{color:#2563eb}.log-success{color:#16a34a}
.log-warning{color:#d97706}.log-error{color:#dc2626}
.live{color:#16a34a;font-weight:bold}
.log-details{max-width:360px;white-space:pre-wrap;word-break:break-word}
@media(max-width:650px){.container{width:96%}.hero h1{font-size:31px}
table{display:block;overflow-x:auto}}
</style>
</head>
<body>
<nav>
<div class="logo">
<span class="k">k</span><span class="o">o</span><span class="j">j</span><span class="a">a</span> AFRICA
</div>
<div class="navlinks">
{% if session.get("user_id") %}
{% if session.get("role") == "admin" %}
<a href="/admin">Dashboard</a>
<a href="/admin/questions">Questions</a>
<a href="/admin/answers">Answers</a>
<a href="/admin/logs">Logs</a>
<a href="/admin/config">Configuration</a>
{% else %}
<a href="/student">Dashboard</a>
<a href="/student/ask">Ask Question</a>
{% endif %}
<a href="/logout">Logout</a>
{% else %}
<a href="/">Home</a><a href="/login">Login</a><a href="/register">Register</a>
{% endif %}
</div>
</nav>
<div class="container">
{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}
<div class="alert {{ category }}">{{ message }}</div>
{% endfor %}
{% endwith %}
{{ content|safe }}
</div>
</body>
</html>
"""


def render_page(title, content, canonical=None):
    return render_template_string(
        HTML,
        title=title,
        content=content,
        canonical_url=canonical or SITE_URL,
        site_description=SITE_DESCRIPTION
    )


# ============================================================
# PUBLIC
# ============================================================

@app.route("/")
def home():
    content = """
    <div class="hero">
        <h1>KOJA AFRICA</h1>
        <p>Knowledge • Questions • Answers</p>
        <p>Academic questions, assignment support, research assistance
        and learning resources.</p>
        <a class="btn" href="/register">Create Student Account</a>
        <a class="btn" href="/login">Login</a>
    </div>
    <div class="grid">
        <div class="card"><h2>Ask Questions</h2>
        <p>Submit academic questions through KOJA.</p></div>
        <div class="card"><h2>Upload Work</h2>
        <p>Attach documents and photographs.</p></div>
        <div class="card"><h2>Receive Answers</h2>
        <p>View answers and administrator files.</p></div>
    </div>
    """
    return render_page("Knowledge, Questions & Answers", content, SITE_URL + "/")


# ============================================================
# GOOGLE / SEO
# ============================================================

@app.route("/robots.txt")
def robots():
    text = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /student
Disallow: /login
Disallow: /register
Disallow: /logout

Sitemap: {SITE_URL}/sitemap.xml
"""
    return Response(text, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{SITE_URL}/</loc></url>
</urlset>"""
    return Response(xml, mimetype="application/xml")


@app.route("/google4d3d8178b7b4659e.html")
def google_verification():
    return "google-site-verification: google4d3d8178b7b4659e.html"


# ============================================================
# LOGIN / REGISTER
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if email == ADMIN_EMAIL and secrets.compare_digest(
            password, ADMIN_PASSWORD
        ):
            session.clear()
            session["user_id"] = "ADMIN"
            session["email"] = ADMIN_EMAIL
            session["name"] = "KOJA Administrator"
            session["role"] = "admin"
            log_event("Admin Login", "Auth", "SUCCESS", "Administrator logged in")
            return redirect(url_for("admin_dashboard"))

        user = find_user(email)

        if not user or not verify_password(
            password, user.get("password", "")
        ):
            log_event(
                "Failed Login",
                "Auth",
                "WARNING",
                f"Invalid credentials for {email}",
                user_email=email
            )
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        session.clear()
        session["user_id"] = user["id"]
        session["email"] = user["email"]
        session["name"] = user["name"]
        session["role"] = "student"

        log_event("User Login", "Auth", "SUCCESS", "Student logged in")
        return redirect(url_for("student_dashboard"))

    content = """
    <div class="auth card">
    <h1>KOJA AFRICA</h1>
    <p class="muted">Knowledge • Questions • Answers</p>
    <form method="post">
    <label>Email</label><input type="email" name="email" required>
    <label>Password</label><input type="password" name="password" required>
    <button type="submit">Login</button>
    </form>
    <p>New student? <a href="/register">Create Student Account</a></p>
    </div>
    """
    return render_page("Login", content, SITE_URL + "/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if len(name) < 2:
            flash("Enter your full name.", "error")
            return redirect(url_for("register"))

        if email == ADMIN_EMAIL:
            flash("That email is reserved.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "error")
            return redirect(url_for("register"))

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        if find_user(email):
            flash("An account with this email already exists.", "error")
            return redirect(url_for("register"))

        user = {
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password": hash_password(password),
            "role": "student",
            "created_at": now()
        }

        data = users()
        data.append(user)
        write_json(USERS_FILE, data)

        if supabase_configured():
            supabase_insert("koja_users", {
                "id": user["id"],
                "name": name,
                "email": email,
                "role": "student",
                "created_at": user["created_at"]
            })

        log_event(
            "User Registered",
            "Auth",
            "SUCCESS",
            "New student account created",
            user_id=user["id"],
            user_email=email
        )

        flash("Account created successfully.", "success")
        return redirect(url_for("login"))

    content = """
    <div class="auth card">
    <h1>Student Registration</h1>
    <form method="post">
    <label>Full Name</label><input name="name" required>
    <label>Email</label><input type="email" name="email" required>
    <label>Password</label><input type="password" name="password" minlength="6" required>
    <label>Confirm Password</label><input type="password" name="confirm" minlength="6" required>
    <button type="submit">Create Account</button>
    </form>
    <p><a href="/login">Already have an account?</a></p>
    </div>
    """
    return render_page("Register", content, SITE_URL + "/register")


@app.route("/logout")
def logout():
    if session.get("user_id"):
        log_event("User Logout", "Auth", "INFO", "Session ended")
    session.clear()
    return redirect(url_for("home"))


# ============================================================
# STUDENT
# ============================================================

@app.route("/student")
@login_required
def student_dashboard():
    if is_admin_session():
        return redirect(url_for("admin_dashboard"))

    data = [
        q for q in questions()
        if q.get("student_id") == session.get("user_id")
    ]
    data.sort(key=lambda q: q.get("created_at", ""), reverse=True)

    total = len(data)
    answered = sum(q.get("status") == "Answered" for q in data)
    pending = total - answered

    cards = ""
    for q in data:
        status = q.get("status", "Pending")
        badge = "answered" if status == "Answered" else "pending"
        answer = q.get("answer", "")

        answer_html = (
            f'<div class="answer">{esc(answer)}</div>'
            if answer else
            '<p class="muted">Waiting for an answer.</p>'
        )

        cards += f"""
        <div class="card">
        <h2>{esc(q.get("subject"))}</h2>
        <span class="badge {badge}">{esc(status)}</span>
        <p class="muted">{esc(q.get("created_at"))}</p>
        <h3>Your Question</h3>
        <div class="question">{esc(q.get("question"))}</div>
        <h3>Your Attachments</h3>
        {attachment_html(q.get("attachments", []), "student", q.get("id"))}
        <h3>Administrator Answer</h3>
        {answer_html}
        <h3>Administrator Files</h3>
        {attachment_html(q.get("answer_attachments", []), "student", q.get("id"))}
        </div>
        """

    if not cards:
        cards = """
        <div class="card">
        <h2>No questions yet.</h2>
        <a class="btn" href="/student/ask">Ask Question</a>
        </div>
        """

    content = f"""
    <div class="hero">
    <h1>Welcome, {esc(session.get("name"))}</h1>
    <p>Submit questions and receive answers through KOJA AFRICA.</p>
    <a class="btn" href="/student/ask">Ask Question</a>
    </div>
    <div class="grid">
    <div class="stat"><h2>{total}</h2><p>Total Questions</p></div>
    <div class="stat"><h2>{answered}</h2><p>Answered</p></div>
    <div class="stat"><h2>{pending}</h2><p>Pending</p></div>
    </div>
    <h2>My Questions</h2>
    {cards}
    """
    return render_page("Student Dashboard", content)


@app.route("/student/ask", methods=["GET", "POST"])
@login_required
def ask_question():
    if is_admin_session():
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        question_text = request.form.get("question", "").strip()

        if len(subject) < 2 or len(question_text) < 3:
            flash("Enter a valid subject and question.", "error")
            return redirect(url_for("ask_question"))

        question_id = str(uuid.uuid4())
        attachments = save_multiple_uploads(
            request.files.getlist("attachments"),
            "student",
            question_id
        )

        item = {
            "id": question_id,
            "student_id": session.get("user_id"),
            "student_name": session.get("name"),
            "student_email": session.get("email"),
            "subject": subject,
            "question": question_text,
            "attachments": attachments,
            "status": "Pending",
            "answer": "",
            "answer_attachments": [],
            "answered_at": None,
            "answered_by": None,
            "created_at": now()
        }

        data = questions()
        data.append(item)
        save_questions(data)
        sync_question(item)

        log_event(
            "Question Submitted",
            "Question",
            "INFO",
            f"{subject} | {question_id}"
        )

        flash("Question submitted successfully.", "success")
        return redirect(url_for("student_dashboard"))

    content = """
    <div class="card">
    <h1>Ask a Question</h1>
    <form method="post" enctype="multipart/form-data">
    <label>Subject</label>
    <input name="subject" placeholder="e.g. Chemistry" required>
    <label>Question</label>
    <textarea name="question" placeholder="Write your academic question..." required></textarea>
    <label>Attachments</label>
    <input type="file" name="attachments" multiple
    accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.webp,.gif">
    <button type="submit">Submit Question</button>
    </form>
    </div>
    """
    return render_page("Ask Question", content)


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():
    data = questions()
    total = len(data)
    pending = sum(q.get("status") != "Answered" for q in data)
    answered = total - pending
    total_logs = len(logs())

    content = f"""
    <div class="hero">
    <h1>KOJA Administrator</h1>
    <p>Manage questions, answers, files and system activity.</p>
    </div>
    <div class="grid">
    <div class="stat"><h2>{total}</h2><p>Total Questions</p></div>
    <div class="stat"><h2>{pending}</h2><p>Pending</p></div>
    <div class="stat"><h2>{answered}</h2><p>Answered</p></div>
    <div class="stat"><h2>{total_logs}</h2><p>System Logs</p></div>
    </div>
    <div class="card">
    <a class="btn" href="/admin/questions">Questions</a>
    <a class="btn green" href="/admin/answers">Answers</a>
    <a class="btn purple" href="/admin/logs">System Logs</a>
    <a class="btn" href="/admin/config">Configuration</a>
    </div>
    """
    return render_page("Admin Dashboard", content)


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():
    data = [
        q for q in questions()
        if q.get("status") != "Answered"
    ]
    data.sort(key=lambda q: q.get("created_at", ""), reverse=True)

    rows = ""
    for q in data:
        text = q.get("question", "")
        if len(text) > 200:
            text = text[:200] + "..."

        rows += f"""
        <tr>
        <td>{esc(q.get("student_name"))}<br>
        <small>{esc(q.get("student_email"))}</small></td>
        <td>{esc(q.get("subject"))}</td>
        <td>{esc(text)}</td>
        <td><span class="badge pending">Pending</span></td>
        <td>
        <a class="btn small" href="/admin/question/{q.get('id')}">Open</a>
        <a class="btn purple small"
        href="/admin/question/{q.get('id')}/upload">Answer + Files</a>
        </td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="5">No pending questions.</td></tr>'

    content = f"""
    <div class="card"><h1>Student Questions</h1>
    <p>Open a question and provide an academic answer.</p></div>
    <div class="card"><div style="overflow-x:auto">
    <table><thead><tr>
    <th>Student</th><th>Subject</th><th>Question</th><th>Status</th><th>Actions</th>
    </tr></thead><tbody>{rows}</tbody></table>
    </div></div>
    """
    return render_page("Questions", content)


@app.route("/admin/question/<question_id>", methods=["GET", "POST"])
@admin_required
def admin_question(question_id):
    question = find_question(question_id)
    if not question:
        flash("Question not found.", "error")
        return redirect(url_for("admin_questions"))

    if request.method == "POST":
        answer = request.form.get("answer", "").strip()
        if len(answer) < 2:
            flash("Write an answer first.", "error")
            return redirect(url_for("admin_question", question_id=question_id))

        answered_at = now()
        data = questions()

        for item in data:
            if str(item.get("id")) == str(question_id):
                item["answer"] = answer
                item["status"] = "Answered"
                item["answered_at"] = answered_at
                item["answered_by"] = session.get("email")
                break

        save_questions(data)

        supabase_update(
            "koja_questions",
            "id",
            question_id,
            {
                "answer": answer,
                "status": "Answered",
                "answered_at": answered_at
            }
        )

        log_event(
            "Answer Posted",
            "Answer",
            "SUCCESS",
            f"Answer posted to question {question_id}"
        )

        flash("Answer saved.", "success")
        return redirect(
            url_for("admin_upload_answer", question_id=question_id)
        )

    content = f"""
    <div class="card">
    <a href="/admin/questions">← Questions</a>
    <h1>{esc(question.get("subject"))}</h1>
    <p><strong>Student:</strong> {esc(question.get("student_name"))}<br>
    <strong>Email:</strong> {esc(question.get("student_email"))}</p>
    </div>
    <div class="card">
    <h2>Student Question</h2>
    <div class="question">{esc(question.get("question"))}</div>
    <h2>Student Attachments</h2>
    {attachment_html(question.get("attachments", []), "admin")}
    </div>
    <div class="card">
    <h2>Academic Answer</h2>
    <form method="post">
    <textarea name="answer" required>{esc(question.get("answer", ""))}</textarea>
    <button class="green" type="submit">Save Answer</button>
    </form>
    <br>
    <a class="btn purple" href="/admin/question/{question_id}/upload">
    Upload With Answer</a>
    </div>
    """
    return render_page("Open Question", content)


@app.route("/admin/question/<question_id>/upload", methods=["GET", "POST"])
@admin_required
def admin_upload_answer(question_id):
    question = find_question(question_id)
    if not question:
        flash("Question not found.", "error")
        return redirect(url_for("admin_questions"))

    if request.method == "POST":
        answer = request.form.get("answer", "").strip()
        if not answer:
            answer = question.get("answer", "").strip()

        if len(answer) < 2:
            flash("Write an answer before sending.", "error")
            return redirect(url_for(
                "admin_upload_answer",
                question_id=question_id
            ))

        attachments = save_multiple_uploads(
            request.files.getlist("answer_attachments"),
            "admin",
            question_id
        )

        answered_at = now()
        data = questions()

        for item in data:
            if str(item.get("id")) == str(question_id):
                item["answer"] = answer
                item["status"] = "Answered"
                item["answered_at"] = answered_at
                item["answered_by"] = session.get("email")

                existing = item.get("answer_attachments", [])
                if not isinstance(existing, list):
                    existing = []
                existing.extend(attachments)
                item["answer_attachments"] = existing
                break

        save_questions(data)

        supabase_update(
            "koja_questions",
            "id",
            question_id,
            {
                "answer": answer,
                "status": "Answered",
                "answered_at": answered_at
            }
        )

        log_event(
            "Answer Sent",
            "Answer",
            "SUCCESS",
            f"Answer and {len(attachments)} attachment(s) sent to {question_id}"
        )

        flash("Answer sent successfully.", "success")
        return redirect(url_for("admin_answers"))

    content = f"""
    <div class="card">
    <a href="/admin/questions">← Questions</a>
    <h1>Upload With Answer</h1>
    <p>Student: <strong>{esc(question.get("student_name"))}</strong></p>
    <div class="question">{esc(question.get("question"))}</div>
    </div>
    <div class="card">
    <form method="post" enctype="multipart/form-data">
    <label>Academic Answer</label>
    <textarea name="answer" required>{esc(question.get("answer", ""))}</textarea>
    <label>Answer Files</label>
    <input type="file" name="answer_attachments" multiple
    accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.webp,.gif">
    <button class="green" type="submit">Send Answer + Files</button>
    </form>
    </div>
    <div class="card">
    <h2>Previously Sent Files</h2>
    {attachment_html(question.get("answer_attachments", []), "admin")}
    </div>
    """
    return render_page("Upload With Answer", content)


@app.route("/admin/answers")
@admin_required
def admin_answers():
    data = [q for q in questions() if q.get("status") == "Answered"]
    data.sort(key=lambda q: q.get("answered_at", ""), reverse=True)

    cards = ""
    for q in data:
        cards += f"""
        <div class="card">
        <h2>{esc(q.get("subject"))}</h2>
        <span class="badge answered">Answered</span>
        <p><strong>Student:</strong> {esc(q.get("student_name"))}</p>
        <div class="question">{esc(q.get("question"))}</div>
        <h3>Answer</h3>
        <div class="answer">{esc(q.get("answer"))}</div>
        <a class="btn" href="/admin/question/{q.get('id')}">Open</a>
        </div>
        """

    return render_page(
        "Previous Answers",
        cards or '<div class="card"><h2>No previous answers.</h2></div>'
    )


# ============================================================
# ADMIN SYSTEM LOGS
# ============================================================

@app.route("/admin/logs")
@admin_required
def admin_logs():
    all_logs = logs()
    all_logs.sort(
        key=lambda x: x.get("created_at", ""),
        reverse=True
    )

    level_filter = request.args.get("level", "").upper().strip()
    category_filter = request.args.get("category", "").strip().lower()
    user_filter = request.args.get("user", "").strip().lower()

    filtered = []
    for item in all_logs:
        if level_filter and item.get("level") != level_filter:
            continue
        if category_filter and category_filter not in item.get(
            "category", ""
        ).lower():
            continue
        if user_filter and user_filter not in (
            item.get("user_email", "") or ""
        ).lower():
            continue
        filtered.append(item)

    today = datetime.now(timezone.utc).date().isoformat()
    today_count = sum(
        str(x.get("created_at", "")).startswith(today)
        for x in all_logs
    )
    errors = sum(
        x.get("level") == "ERROR"
        for x in all_logs
    )

    rows = ""
    for item in filtered[:500]:
        level = item.get("level", "INFO")
        css = {
            "SUCCESS": "log-success",
            "WARNING": "log-warning",
            "ERROR": "log-error",
            "INFO": "log-info"
        }.get(level, "log-info")

        rows += f"""
        <tr>
        <td>{esc(item.get("created_at"))}</td>
        <td class="{css}"><strong>{esc(level)}</strong></td>
        <td>{esc(item.get("category"))}</td>
        <td>{esc(item.get("user_email"))}</td>
        <td>{esc(item.get("action"))}</td>
        <td class="log-details">{esc(item.get("details"))}</td>
        <td>{esc(item.get("ip_address"))}</td>
        </tr>
        """

    if not rows:
        rows = '<tr><td colspan="7">No matching logs.</td></tr>'

    categories = sorted({
        str(x.get("category", ""))
        for x in all_logs
        if x.get("category")
    })

    options = "".join(
        f'<option value="{esc(c)}">{esc(c)}</option>'
        for c in categories
    )

    content = f"""
    <div class="hero">
    <h1>KOJA System Logs</h1>
    <p>Monitor user activity, questions, answers, storage and security events.</p>
    <span class="live">● Logging active</span>
    </div>

    <div class="grid">
    <div class="stat"><h2>{len(all_logs)}</h2><p>Total Logs</p></div>
    <div class="stat"><h2>{today_count}</h2><p>Today</p></div>
    <div class="stat"><h2>{errors}</h2><p>Errors</p></div>
    <div class="stat"><h2>{len(users())}</h2><p>Registered Users</p></div>
    </div>

    <div class="card">
    <h2>Filter Logs</h2>
    <form method="get">
    <label>Level</label>
    <select name="level">
    <option value="">All Levels</option>
    <option>INFO</option><option>SUCCESS</option>
    <option>WARNING</option><option>ERROR</option>
    </select>
    <label>Category</label>
    <select name="category">
    <option value="">All Categories</option>
    {options}
    </select>
    <label>User</label>
    <input name="user" value="{esc(user_filter)}"
    placeholder="Search email">
    <button type="submit">Filter</button>
    <a class="btn" href="/admin/logs">Clear</a>
    </form>
    </div>

    <div class="card">
    <div style="overflow-x:auto">
    <table>
    <thead><tr>
    <th>Time</th><th>Level</th><th>Category</th>
    <th>User</th><th>Action</th><th>Details</th><th>IP</th>
    </tr></thead>
    <tbody>{rows}</tbody>
    </table>
    </div>
    </div>
    """
    return render_page("System Logs", content)


# ============================================================
# FILE ACCESS
# ============================================================

@app.route("/admin/file/<category>/<filename>")
@admin_required
def admin_file(category, filename):
    if category == "student":
        directory = STUDENT_UPLOAD_DIR
    elif category == "admin":
        directory = ADMIN_UPLOAD_DIR
    else:
        abort(404)

    log_event(
        "File Viewed",
        "Storage",
        "INFO",
        f"{category}/{filename}"
    )

    return send_from_directory(directory, filename)


@app.route("/student/file/<question_id>/<category>/<filename>")
@login_required
def student_file(question_id, category, filename):
    if is_admin_session():
        return redirect(url_for("admin_dashboard"))

    question = find_question(question_id)
    if not question:
        return "File not found", 404

    if question.get("student_id") != session.get("user_id"):
        log_event(
            "Unauthorized File Access",
            "Security",
            "WARNING",
            f"Question {question_id}"
        )
        return "Access denied", 403

    if category == "student":
        attachments = question.get("attachments", [])
        directory = STUDENT_UPLOAD_DIR
    elif category == "admin":
        attachments = question.get("answer_attachments", [])
        directory = ADMIN_UPLOAD_DIR
    else:
        return "Invalid category", 404

    for a in attachments:
        if a.get("stored_name") == filename:
            log_event(
                "File Viewed",
                "Storage",
                "INFO",
                f"{category}/{filename}"
            )
            return send_from_directory(directory, filename)

    return "File not found", 404


# ============================================================
# CONFIG / HEALTH
# ============================================================

@app.route("/admin/config")
@admin_required
def admin_config():
    configured = supabase_configured()
    connected = supabase_test() if configured else False

    content = f"""
    <div class="card">
    <h1>Configuration</h1>
    <h2>Supabase</h2>
    <p>Configured:
    <span class="badge {'answered' if configured else 'pending'}">
    {"YES" if configured else "NO"}</span></p>
    <p>Connection:
    <span class="badge {'answered' if connected else 'pending'}">
    {"WORKING" if connected else "UNAVAILABLE"}</span></p>
    <p>Storage bucket: <strong>{esc(STORAGE_BUCKET)}</strong></p>
    <p>System logs:
    <span class="badge answered">ACTIVE</span></p>
    </div>
    """
    return render_page("Configuration", content)


@app.route("/health")
def health():
    return {
        "status": "ok",
        "application": SITE_NAME,
        "supabase_configured": supabase_configured(),
        "supabase_connected": supabase_test(),
        "logging": True,
        "local_fallback": True
    }


# ============================================================
# ERRORS
# ============================================================

@app.errorhandler(413)
def too_large(error):
    log_event(
        "Upload Failed",
        "Storage",
        "ERROR",
        "Request exceeded 10 MB"
    )
    flash("Maximum upload size is 10 MB.", "error")
    if session.get("user_id"):
        return redirect(
            url_for(
                "admin_dashboard"
                if is_admin_session()
                else "ask_question"
            )
        )
    return redirect(url_for("login"))


@app.errorhandler(404)
def not_found(error):
    return render_page(
        "Not Found",
        '<div class="card"><h1>Page Not Found</h1>'
        '<a class="btn" href="/">Go Home</a></div>'
    ), 404


@app.errorhandler(500)
def server_error(error):
    log_event(
        "Internal Server Error",
        "System",
        "ERROR",
        str(error)
    )
    return render_page(
        "KOJA Error",
        '<div class="card"><h1>KOJA AFRICA</h1>'
        '<p>An unexpected error occurred.</p>'
        '<a class="btn" href="/">Go Home</a></div>'
    ), 500


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9999"))

    print("=" * 60)
    print("KOJA AFRICA")
    print("Knowledge • Questions • Answers")
    print("System logging: ENABLED")
    print("Supabase:", supabase_configured())
    print("Port:", port)
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
