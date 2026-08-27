
import os
import io
import uuid
import secrets
import logging
from functools import wraps
from datetime import datetime, timezone

import requests
from flask import (
    Flask, request, redirect, url_for, session, render_template_string,
    flash, send_file, abort, jsonify
)
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import mm


# ============================================================
# KOJA AFRICA - FLASK + SUPABASE
# Aligned with the tables supplied by the user.
# AI has been removed.
# ============================================================

app = Flask(__name__)
app.secret_key = os.environ.get("KOJA_SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
STORAGE_BUCKET = os.environ.get("KOJA_STORAGE_BUCKET", "koja-files")

ADMIN_EMAIL = os.environ.get("KOJA_ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.environ.get("KOJA_ADMIN_PASSWORD", "")

APP_NAME = "KOJA AFRICA"
APP_TAGLINE = "Knowledge • Questions • Answers"

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "txt", "csv", "ppt", "pptx"
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja")


# ============================================================
# HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_text(value, limit=50000):
    if value is None:
        return ""
    return str(value).strip()[:limit]


def allowed_file(filename):
    return bool(
        filename and "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def current_user():
    return session.get("user")


def is_admin():
    u = current_user()
    return bool(u and u.get("role") == "admin")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in first.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_admin():
            flash("Administrator access required.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def student_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user() or is_admin():
            flash("Student access required.")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper


# ============================================================
# CSRF
# ============================================================

def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def csrf_check():
    token = request.form.get("csrf_token", "")
    return secrets.compare_digest(token, session.get("csrf_token", ""))


@app.context_processor
def inject_globals():
    return {
        "csrf_token": csrf_token(),
        "koja_user": current_user(),
        "is_admin": is_admin(),
    }


# ============================================================
# SUPABASE REST
# ============================================================

def sb_headers(extra=None):
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def sb_request(method, table, params=None, data=None, prefer=None, timeout=30):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase environment variables are missing.")

    headers = sb_headers()
    if prefer:
        headers["Prefer"] = prefer

    r = requests.request(
        method,
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=params,
        json=data,
        timeout=timeout,
    )
    if not r.ok:
        logger.error("Supabase %s %s: %s", method, table, r.text)
    return r


def db_select(table, params=None):
    r = sb_request("GET", table, params=params)
    if not r.ok:
        raise RuntimeError(r.text)
    return r.json() if r.text else []


def db_insert(table, data, select="*"):
    r = sb_request(
        "POST", table,
        params={"select": select},
        data=data,
        prefer="return=representation",
    )
    if not r.ok:
        raise RuntimeError(r.text)
    return r.json() if r.text else []


def db_update(table, filters, data, select="*"):
    params = dict(filters)
    params["select"] = select
    r = sb_request(
        "PATCH", table,
        params=params,
        data=data,
        prefer="return=representation",
    )
    if not r.ok:
        raise RuntimeError(r.text)
    return r.json() if r.text else []


def db_delete(table, filters):
    r = sb_request(
        "DELETE", table,
        params=filters,
        prefer="return=minimal",
    )
    if not r.ok:
        raise RuntimeError(r.text)
    return True


# ============================================================
# SUPABASE AUTH
# Uses Supabase Auth rather than inventing a users table.
# ============================================================

def auth_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }


def auth_signup(email, password, name):
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/signup",
        headers=auth_headers(),
        json={
            "email": email,
            "password": password,
            "data": {"name": name},
        },
        timeout=30,
    )
    return r


def auth_login(email, password):
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers=auth_headers(),
        json={"email": email, "password": password},
        timeout=30,
    )
    return r


def auth_recover(email):
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/recover",
        headers=auth_headers(),
        json={"email": email},
        timeout=30,
    )
    return r


def auth_users():
    r = requests.get(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=sb_headers(),
        params={"page": 1, "per_page": 1000},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(r.text)
    data = r.json()
    return data.get("users", [])


# ============================================================
# STORAGE
# ============================================================

def storage_upload(data, path, content_type):
    path = path.lstrip("/")
    r = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{path}",
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "true",
        },
        data=data,
        timeout=90,
    )
    if not r.ok:
        raise RuntimeError(f"Storage upload failed: {r.text}")
    return path


def storage_download(path):
    if not path:
        raise RuntimeError("Missing storage path.")
    path = path.lstrip("/")
    r = requests.get(
        f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{path}",
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
        },
        timeout=90,
    )
    if not r.ok:
        raise RuntimeError(f"Storage download failed: {r.text}")
    return r.content


# ============================================================
# DATA HELPERS
# ============================================================

def get_assignment(aid):
    rows = db_select("assignments", {
        "id": f"eq.{aid}",
        "select": "*",
        "limit": "1",
    })
    return rows[0] if rows else None


def get_answer(aid):
    rows = db_select("assignment_answers", {
        "assignment_id": f"eq.{aid}",
        "select": "*",
        "order": "created_at.desc",
        "limit": "1",
    })
    return rows[0] if rows else None


def get_document(did):
    rows = db_select("document_library", {
        "id": f"eq.{did}",
        "select": "*",
        "limit": "1",
    })
    return rows[0] if rows else None


def log_record(document_id, user_id, action):
    try:
        db_insert("document_records", {
            "id": str(uuid.uuid4()),
            "document_id": document_id,
            "user_id": user_id,
            "action": action,
            "ip_address": request.headers.get("X-Forwarded-For", request.remote_addr),
            "user_agent": request.headers.get("User-Agent", "")[:1000],
            "created_at": now_iso(),
        })
    except Exception:
        logger.exception("Could not write document record.")


# ============================================================
# SCREEN-ONLY KOJA BRAIN SYMBOL
# Never placed inside generated PDFs.
# ============================================================

BRAIN_LOGO = """
<div class="koja-mark" aria-label="KOJA AFRICA">
<svg viewBox="0 0 120 90" role="img">
  <path d="M48 15c-14-8-31 2-31 18 0 4 1 8 3 11-9 8-5 24 7 28
  5 2 10 2 15 0 5 7 15 9 23 5 4 8 13 11 21 7 9-4 12-14 8-23
  7-4 9-13 5-20 5-8-1-15-7-18-14-2-5-6-9-12-12z"
  fill="none" stroke="currentColor" stroke-width="4"
  stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M48 18v53M35 27c6 2 10 7 10 14M24 45c8 0 14 4 17 10
  M72 22c-5 3-8 8-8 14M82 38c-8 1-13 6-15 13M73 61c-5-1-10 1-13 5"
  fill="none" stroke="currentColor" stroke-width="3"
  stroke-linecap="round"/>
</svg>
<span>KOJA</span>
</div>
"""


# ============================================================
# PDF GENERATOR
# No KOJA logo/watermark is inserted.
# ============================================================

def build_pdf(title, subject, student_name, question, answer):
    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "T", parent=styles["Title"], alignment=TA_CENTER,
        fontSize=18, leading=22, spaceAfter=10
    )
    body = ParagraphStyle(
        "B", parent=styles["BodyText"],
        fontSize=10.5, leading=15, spaceAfter=8
    )
    heading = ParagraphStyle(
        "H", parent=styles["Heading2"],
        fontSize=12, leading=16, spaceBefore=8, spaceAfter=6
    )

    def html(x):
        return safe_text(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")

    story = [
        Paragraph("ANSWERED ASSIGNMENT", title_style),
        Paragraph(f"<b>Assignment:</b> {html(title)}", body),
        Paragraph(f"<b>Subject:</b> {html(subject)}", body),
        Paragraph(f"<b>Student:</b> {html(student_name)}", body),
        Paragraph("QUESTION", heading),
        Paragraph(html(question), body),
        Paragraph("ANSWER", heading),
        Paragraph(html(answer), body),
        Spacer(1, 15),
        Paragraph(
            "Generated academic document",
            ParagraphStyle("F", parent=body, alignment=TA_CENTER, fontSize=8)
        ),
    ]
    doc.build(story)
    return out.getvalue()


# ============================================================
# TEMPLATE
# ============================================================

BASE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} - KOJA AFRICA</title>
<style>
:root{
 --bg:#f3f6fa;--card:#fff;--text:#172033;--muted:#667085;
 --nav:#0d2b4d;--accent:#1261a0;--border:#dce3ec;
}
body.dark{--bg:#101722;--card:#182331;--text:#f1f5f9;--muted:#aab6c5;--border:#2d3b4d}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,sans-serif;transition:.2s}
nav{background:var(--nav);color:#fff;position:sticky;top:0;z-index:20}
.navinner{max-width:1180px;margin:auto;padding:10px 15px;display:flex;align-items:center;gap:13px;flex-wrap:wrap}
.brand{font-weight:800;font-size:20px;margin-right:auto}
nav a{color:#fff;text-decoration:none;font-size:14px}
.container{max-width:1180px;margin:24px auto;padding:0 15px}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:20px;margin-bottom:18px;box-shadow:0 4px 16px rgba(0,0,0,.05)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:15px}
input,textarea,select{width:100%;padding:11px;margin:6px 0 13px;border:1px solid var(--border);border-radius:9px;background:var(--card);color:var(--text);font-size:15px}
textarea{min-height:150px}
button,.btn{display:inline-block;padding:10px 15px;border:0;border-radius:9px;background:var(--accent);color:#fff;text-decoration:none;cursor:pointer}
.btn-danger{background:#b42318}.btn-success{background:#218c5a}.btn-dark{background:#172033}
.flash{background:#fff3cd;color:#5b4700;padding:12px;border-radius:9px;margin-bottom:15px}
body.dark .flash{background:#4b3d14;color:#fff0ad}
table{width:100%;border-collapse:collapse;overflow:hidden}
th,td{padding:10px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
.answer{white-space:pre-wrap;line-height:1.65}
.small{font-size:13px;color:var(--muted)}
.hero{text-align:center;padding:45px 10px}
.koja-mark{display:inline-flex;align-items:center;gap:9px;color:#1261a0;font-weight:900;font-size:22px;letter-spacing:2px}
.koja-mark svg{width:58px;height:48px}
.screen-mark{position:fixed;right:14px;bottom:14px;opacity:.18;z-index:1;pointer-events:none}
.stat{font-size:30px;font-weight:800}
.badge{display:inline-block;padding:5px 8px;border-radius:999px;background:#e7eef7;font-size:12px}
body.dark .badge{background:#29384a}
.actions{display:flex;gap:8px;flex-wrap:wrap}
@media(max-width:700px){table{font-size:12px}.container{margin-top:15px}}
</style>
</head>
<body>
<nav>
<div class="navinner">
<span class="brand">KOJA AFRICA</span>
{% if koja_user %}
<a href="{{ url_for('dashboard') }}">Dashboard</a>
<a href="{{ url_for('documents') }}">Library</a>
{% if is_admin %}<a href="{{ url_for('admin_assignments') }}">Assignments</a>{% endif %}
<a href="{{ url_for('settings') }}">Settings</a>
<a href="{{ url_for('logout') }}">Logout</a>
{% else %}
<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Create account</a>
{% endif %}
</div>
</nav>
{{ brain|safe }}
<div class="container">
{% with msgs=get_flashed_messages() %}
{% for m in msgs %}<div class="flash">{{ m }}</div>{% endfor %}
{% endwith %}
{{ content|safe }}
</div>
<script>
(function(){
  const dark = localStorage.getItem("koja_dark")==="1";
  if(dark) document.body.classList.add("dark");
})();
function toggleDark(){
  document.body.classList.toggle("dark");
  localStorage.setItem("koja_dark",document.body.classList.contains("dark")?"1":"0");
}
</script>
</body>
</html>
"""


def page(content, title="KOJA AFRICA"):
    return render_template_string(
        BASE,
        content=content,
        title=title,
        brain=f'<div class="screen-mark">{BRAIN_LOGO}</div>'
    )


# ============================================================
# FIRST OPEN LOG
# One web-open record per login session.
# Logs are visible only to admins.
# ============================================================

@app.before_request
def first_open_log():
    if request.endpoint and request.endpoint in {
        "static", "health", "login", "register", "forgot_password"
    }:
        return
    if current_user() and not session.get("web_open_logged"):
        session["web_open_logged"] = True
        log_record(
            None,
            current_user().get("id"),
            "web_open"
        )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    return page("""
<div class="hero">
%s
<h1>KOJA AFRICA</h1>
<p>Knowledge • Questions • Answers</p>
<p class="small">Assignments, academic resources, past papers, notes and books.</p>
<div class="actions" style="justify-content:center;margin-top:20px">
<a class="btn" href="/login">Login</a>
<a class="btn btn-dark" href="/register">Create Account</a>
</div>
</div>
<div class="grid">
<div class="card"><h3>Assignments</h3><p>Students and administrators can upload academic work.</p></div>
<div class="card"><h3>Resources</h3><p>Past papers, notes, books and other learning materials.</p></div>
<div class="card"><h3>Comments & Status</h3><p>Track assignment status and administrator comments.</p></div>
<div class="card"><h3>Secure Downloads</h3><p>Files are served through KOJA rather than exposing private storage paths.</p></div>
</div>
""" % BRAIN_LOGO)


# ============================================================
# AUTH
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if not csrf_check():
            abort(400)

        name = safe_text(request.form.get("name"), 255)
        email = safe_text(request.form.get("email"), 255).lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 6:
            flash("Name, valid email and a password of at least 6 characters are required.")
            return redirect(url_for("register"))

        try:
            r = auth_signup(email, password, name)
            if not r.ok:
                flash("Registration failed: " + safe_text(r.text, 1000))
                return redirect(url_for("register"))

            # Depending on Supabase email-confirmation settings, a session
            # may or may not be returned immediately.
            data = r.json()
            if data.get("access_token"):
                session["user"] = {
                    "id": data["user"]["id"],
                    "email": data["user"]["email"],
                    "student_name": name,
                    "role": "student",
                    "access_token": data["access_token"],
                }
                flash("Account created successfully.")
                return redirect(url_for("dashboard"))

            flash("Account created. Check your email if confirmation is enabled, then log in.")
            return redirect(url_for("login"))

        except Exception as e:
            logger.exception(e)
            flash("Registration error: " + safe_text(str(e), 1000))

    return page("""
<div class="card" style="max-width:600px;margin:auto">
<h2>Create Student Account</h2>
<form method="post">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label>Name</label><input name="name" required>
<label>Email</label><input type="email" name="email" required>
<label>Password</label><input type="password" name="password" minlength="6" required>
<button>Create Account</button>
</form>
</div>
""", "Register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not csrf_check():
            abort(400)

        email = safe_text(request.form.get("email"), 255).lower()
        password = request.form.get("password", "")

        # Admin credentials are kept only in Render environment variables.
        if ADMIN_EMAIL and email == ADMIN_EMAIL and secrets.compare_digest(password, ADMIN_PASSWORD):
            session.clear()
            session["user"] = {
                "id": "admin",
                "email": ADMIN_EMAIL,
                "student_name": "Administrator",
                "role": "admin",
            }
            session["web_open_logged"] = False
            flash("Administrator login successful.")
            return redirect(url_for("admin_dashboard"))

        try:
            r = auth_login(email, password)
            if not r.ok:
                flash("Login failed. Check your email and password.")
                return redirect(url_for("login"))

            data = r.json()
            u = data.get("user", {})
            metadata = u.get("user_metadata") or {}

            session.clear()
            session["user"] = {
                "id": u.get("id"),
                "email": u.get("email", email),
                "student_name": metadata.get("name") or email.split("@")[0],
                "role": "student",
                "access_token": data.get("access_token"),
            }
            session["web_open_logged"] = False
            return redirect(url_for("dashboard"))

        except Exception as e:
            logger.exception(e)
            flash("Login error: " + safe_text(str(e), 1000))

    return page("""
<div class="card" style="max-width:600px;margin:auto">
<h2>Login</h2>
<form method="post">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label>Email</label><input type="email" name="email" required>
<label>Password</label><input type="password" name="password" required>
<button>Login</button>
</form>
<p><a href="/forgot-password">Forgot password?</a></p>
</div>
""", "Login")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        if not csrf_check():
            abort(400)
        email = safe_text(request.form.get("email"), 255).lower()
        try:
            r = auth_recover(email)
            # Do not reveal whether an account exists.
            if not r.ok:
                logger.warning("Password recovery response: %s", r.text)
            flash("If the account exists, Supabase will send password recovery instructions.")
            return redirect(url_for("login"))
        except Exception as e:
            logger.exception(e)
            flash("Password recovery request could not be completed.")

    return page("""
<div class="card" style="max-width:600px;margin:auto">
<h2>Forgot Password</h2>
<p class="small">Enter your account email. Supabase will handle the recovery email.</p>
<form method="post">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<input type="email" name="email" required>
<button>Send Reset Instructions</button>
</form>
</div>
""", "Forgot Password")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ============================================================
# SETTINGS
# ============================================================

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        if not csrf_check():
            abort(400)
        name = safe_text(request.form.get("name"), 255)
        if name and not is_admin():
            # Supabase Auth user metadata update.
            token = current_user().get("access_token")
            if token:
                try:
                    r = requests.put(
                        f"{SUPABASE_URL}/auth/v1/user",
                        headers={
                            "apikey": SUPABASE_SERVICE_KEY,
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        json={"data": {"name": name}},
                        timeout=30,
                    )
                    if r.ok:
                        session["user"]["student_name"] = name
                        flash("Profile updated.")
                    else:
                        flash("Could not update profile.")
                except Exception:
                    flash("Could not update profile.")

    u = current_user()
    return page(f"""
<div class="card" style="max-width:700px;margin:auto">
<h2>Settings</h2>
<p><b>Name:</b> {safe_text(u.get("student_name"))}</p>
<p><b>Email:</b> {safe_text(u.get("email"))}</p>
<form method="post">
<input type="hidden" name="csrf_token" value="{{{{ csrf_token }}}}">
<label>Display name</label>
<input name="name" value="{safe_text(u.get("student_name"))}">
<button>Save Profile</button>
</form>
<hr>
<h3>Appearance</h3>
<button type="button" onclick="toggleDark()">Toggle Dark Mode</button>
</div>
""", "Settings")


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():
    if is_admin():
        return redirect(url_for("admin_dashboard"))

    uid = current_user().get("id")
    email = current_user().get("email")

    try:
        assignments = db_select("assignments", {
            "or": f"student_id.eq.{uid},email.eq.{email}",
            "select": "*",
            "order": "created_at.desc",
        })
    except Exception:
        assignments = []

    rows = ""
    for a in assignments:
        answer = get_answer(a["id"])
        answer_btn = ""
        if answer and answer.get("answer_file_path"):
            answer_btn = f'<a class="btn btn-success" href="/assignment/{a["id"]}/answer/download">Answer PDF</a>'

        rows += f"""
<tr>
<td>{safe_text(a.get("title"))}</td>
<td>{safe_text(a.get("subject"))}</td>
<td><span class="badge">{safe_text(a.get("status"))}</span></td>
<td>{safe_text(a.get("admin_comment")) or "—"}</td>
<td><div class="actions">{answer_btn}<a class="btn" href="/assignment/{a["id"]}">View</a></div></td>
</tr>
"""

    return page(f"""
<div class="card">
<h2>Student Dashboard</h2>
<p>Welcome, <b>{safe_text(current_user().get("student_name"))}</b></p>
<div class="actions">
<a class="btn" href="/assignment/upload">Upload Assignment</a>
<a class="btn btn-dark" href="/documents">Learning Library</a>
<a class="btn" href="/settings">Settings</a>
</div>
</div>
<div class="card">
<h3>My Assignments</h3>
<table>
<tr><th>Title</th><th>Subject</th><th>Status</th><th>Comment</th><th>View</th></tr>
{rows or "<tr><td colspan='5'>No assignments yet.</td></tr>"}
</table>
</div>
""", "Student Dashboard")


# ============================================================
# STUDENT UPLOAD
# ============================================================

@app.route("/assignment/upload", methods=["GET", "POST"])
@student_required
def upload_assignment():
    if request.method == "POST":
        if not csrf_check():
            abort(400)

        title = safe_text(request.form.get("title"), 255)
        description = safe_text(request.form.get("description"), 5000)
        subject = safe_text(request.form.get("subject"), 255)
        course = safe_text(request.form.get("course"), 255)
        level = safe_text(request.form.get("class_level"), 255)
        question = safe_text(request.form.get("question"), 15000)
        f = request.files.get("file")

        if not title or not f or not f.filename or not allowed_file(f.filename):
            flash("Title and a supported file are required.")
            return redirect(url_for("upload_assignment"))

        try:
            content = f.read()
            aid = str(uuid.uuid4())
            filename = secure_filename(f.filename)
            path = f"assignments/{aid}/{filename}"
            mime = f.content_type or "application/octet-stream"

            storage_upload(content, path, mime)

            u = current_user()
            db_insert("assignments", {
                "id": aid,
                "student_id": u.get("id"),
                "title": title,
                "description": description,
                "subject": subject,
                "course": course,
                "class_level": level,
                "file_name": filename,
                "file_path": path,
                "file_size": len(content),
                "mime_type": mime,
                "status": "submitted",
                "email": u.get("email"),
                "question": question,
                "student_name": u.get("student_name"),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })
            flash("Assignment uploaded successfully.")
            return redirect(url_for("dashboard"))
        except Exception as e:
            logger.exception(e)
            flash("Upload failed: " + safe_text(str(e), 1000))

    return page("""
<div class="card">
<h2>Upload Assignment</h2>
<form method="post" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label>Title</label><input name="title" required>
<label>Subject</label><input name="subject">
<label>Course</label><input name="course">
<label>Class level</label><input name="class_level">
<label>Description</label><textarea name="description"></textarea>
<label>Question</label><textarea name="question"></textarea>
<label>PDF / Word / other supported file</label><input type="file" name="file" required>
<button>Upload</button>
</form>
</div>
""", "Upload Assignment")


# ============================================================
# VIEW ASSIGNMENT
# ============================================================

@app.route("/assignment/<aid>")
@login_required
def view_assignment(aid):
    a = get_assignment(aid)
    if not a:
        abort(404)

    u = current_user()
    if not is_admin() and a.get("email") != u.get("email") and a.get("student_id") != u.get("id"):
        abort(403)

    answer = get_answer(aid)
    comments = []

    try:
        comments = db_select("assignment_responses", {
            "assignment_id": f"eq.{aid}",
            "select": "*",
            "order": "created_at.desc",
        })
    except Exception:
        pass

    comment_html = "".join(
        f'<div class="card"><b>Response</b><p class="answer">{safe_text(c.get("response_text"))}</p><span class="small">{safe_text(c.get("created_at"))}</span></div>'
        for c in comments
    )

    answer_html = ""
    if answer:
        answer_html = f"""
<div class="card">
<h3>Answer</h3>
<p class="answer">{safe_text(answer.get("answer_text"))}</p>
{"<a class='btn btn-success' href='/assignment/"+aid+"/answer/download'>Download Answer PDF</a>" if answer.get("answer_file_path") else ""}
</div>
"""

    return page(f"""
<div class="card">
<h2>{safe_text(a.get("title"))}</h2>
<p><b>Status:</b> <span class="badge">{safe_text(a.get("status"))}</span></p>
<p><b>Subject:</b> {safe_text(a.get("subject"))}</p>
<p><b>Course:</b> {safe_text(a.get("course"))}</p>
<p><b>Class:</b> {safe_text(a.get("class_level"))}</p>
<p><b>Admin comment:</b> {safe_text(a.get("admin_comment")) or "No comment yet."}</p>
<h3>Question</h3>
<div class="answer">{safe_text(a.get("question") or a.get("description"))}</div>
<br>
<a class="btn" href="/assignment/{aid}/download">Download Assignment</a>
</div>
{answer_html}
<div class="card"><h3>Responses / Comments</h3>{comment_html or "<p>No responses yet.</p>"}</div>
""", "Assignment")


# ============================================================
# ASSIGNMENT DOWNLOAD
# ============================================================

@app.route("/assignment/<aid>/download")
@login_required
def download_assignment(aid):
    a = get_assignment(aid)
    if not a:
        abort(404)

    u = current_user()
    if not is_admin() and a.get("email") != u.get("email") and a.get("student_id") != u.get("id"):
        abort(403)

    try:
        data = storage_download(a.get("file_path"))
        log_record(aid, u.get("id"), "assignment_download")
        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=a.get("file_name") or "assignment",
            mimetype=a.get("mime_type") or "application/octet-stream",
        )
    except Exception:
        abort(404)


# ============================================================
# ANSWER DOWNLOAD
# ============================================================

@app.route("/assignment/<aid>/answer/download")
@login_required
def download_answer(aid):
    a = get_assignment(aid)
    if not a:
        abort(404)

    u = current_user()
    if not is_admin() and a.get("email") != u.get("email") and a.get("student_id") != u.get("id"):
        abort(403)

    ans = get_answer(aid)
    if not ans or not ans.get("answer_file_path"):
        abort(404)

    try:
        data = storage_download(ans["answer_file_path"])
        log_record(aid, u.get("id"), "answer_download")
        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=ans.get("answer_file_name") or "answer.pdf",
            mimetype="application/pdf",
        )
    except Exception:
        abort(404)


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():
    try:
        assignments = db_select("assignments", {
            "select": "*",
            "order": "created_at.desc",
        })
    except Exception:
        assignments = []

    try:
        docs = db_select("document_library", {
            "select": "*",
            "order": "created_at.desc",
        })
    except Exception:
        docs = []

    return page(f"""
<div class="grid">
<div class="card"><h3>Assignments</h3><div class="stat">{len(assignments)}</div></div>
<div class="card"><h3>Library Documents</h3><div class="stat">{len(docs)}</div></div>
</div>
<div class="card">
<h2>Administrator Dashboard</h2>
<div class="actions">
<a class="btn" href="/admin/assignments">Manage Assignments</a>
<a class="btn btn-success" href="/admin/assignment/new">Send Assignment to Student</a>
<a class="btn" href="/admin/document/upload">Upload Past Paper / Note / Book</a>
<a class="btn btn-dark" href="/admin/logs">View Logs</a>
<a class="btn" href="/settings">Settings</a>
</div>
</div>
""", "Admin Dashboard")


# ============================================================
# ADMIN ASSIGNMENTS
# ============================================================

@app.route("/admin/assignments")
@admin_required
def admin_assignments():
    try:
        assignments = db_select("assignments", {
            "select": "*",
            "order": "created_at.desc",
        })
    except Exception:
        assignments = []

    rows = ""
    for a in assignments:
        ans = get_answer(a["id"])
        rows += f"""
<tr>
<td>{safe_text(a.get("title"))}</td>
<td>{safe_text(a.get("student_name"))}</td>
<td>{safe_text(a.get("email"))}</td>
<td>{safe_text(a.get("status"))}</td>
<td>{safe_text(a.get("admin_comment")) or "—"}</td>
<td><a class="btn" href="/admin/assignment/{a["id"]}">Open</a></td>
</tr>
"""

    return page(f"""
<div class="card">
<h2>Assignment Management</h2>
<a class="btn btn-success" href="/admin/assignment/new">Send Assignment to Student</a>
</div>
<div class="card">
<table>
<tr><th>Title</th><th>Student</th><th>Email</th><th>Status</th><th>Comment</th><th>Open</th></tr>
{rows or "<tr><td colspan='6'>No assignments.</td></tr>"}
</table>
</div>
""", "Assignments")


# ============================================================
# ADMIN SEND ASSIGNMENT DIRECTLY TO STUDENT
# Uses Supabase Auth admin users + assignments table.
# ============================================================

@app.route("/admin/assignment/new", methods=["GET", "POST"])
@admin_required
def admin_new_assignment():
    try:
        users = auth_users()
        students = [
            u for u in users
            if (u.get("email") or "").lower() != ADMIN_EMAIL
        ]
    except Exception as e:
        logger.exception(e)
        students = []
        flash("Could not load registered students.")

    if request.method == "POST":
        if not csrf_check():
            abort(400)

        student_id = safe_text(request.form.get("student_id"), 100)
        title = safe_text(request.form.get("title"), 255)
        question = safe_text(request.form.get("question"), 15000)
        subject = safe_text(request.form.get("subject"), 255)
        course = safe_text(request.form.get("course"), 255)
        level = safe_text(request.form.get("class_level"), 255)
        comment = safe_text(request.form.get("admin_comment"), 5000)
        f = request.files.get("file")

        target = next((x for x in students if x.get("id") == student_id), None)
        if not target:
            flash("Select a valid student.")
            return redirect(url_for("admin_new_assignment"))

        if not title:
            flash("Assignment title is required.")
            return redirect(url_for("admin_new_assignment"))

        try:
            aid = str(uuid.uuid4())
            filename = None
            path = None
            size = 0
            mime = "application/octet-stream"

            if f and f.filename:
                if not allowed_file(f.filename):
                    flash("Unsupported assignment file.")
                    return redirect(url_for("admin_new_assignment"))
                data = f.read()
                filename = secure_filename(f.filename)
                path = f"assignments/{aid}/{filename}"
                mime = f.content_type or "application/octet-stream"
                size = len(data)
                storage_upload(data, path, mime)

            db_insert("assignments", {
                "id": aid,
                "student_id": student_id,
                "title": title,
                "description": comment,
                "subject": subject,
                "course": course,
                "class_level": level,
                "file_name": filename,
                "file_path": path,
                "file_size": size,
                "mime_type": mime,
                "status": "assigned",
                "admin_comment": comment,
                "email": target.get("email"),
                "question": question,
                "student_name": (target.get("user_metadata") or {}).get("name") or target.get("email"),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })
            flash("Assignment sent directly to the student.")
            return redirect(url_for("admin_assignments"))

        except Exception as e:
            logger.exception(e)
            flash("Could not create assignment: " + safe_text(str(e), 1000))

    options = "".join(
        f'<option value="{safe_text(u.get("id"))}">{safe_text((u.get("user_metadata") or {}).get("name") or u.get("email"))} — {safe_text(u.get("email"))}</option>'
        for u in students
    )

    return page(f"""
<div class="card">
<h2>Send Assignment Directly to Student</h2>
<form method="post" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{{{ csrf_token }}}}">
<label>Student</label><select name="student_id" required><option value="">Select student</option>{options}</select>
<label>Title</label><input name="title" required>
<label>Subject</label><input name="subject">
<label>Course</label><input name="course">
<label>Class level</label><input name="class_level">
<label>Question / instructions</label><textarea name="question"></textarea>
<label>Admin comment</label><textarea name="admin_comment"></textarea>
<label>PDF / Word file (optional)</label><input type="file" name="file">
<button>Send Assignment</button>
</form>
</div>
""", "Send Assignment")


# ============================================================
# ADMIN OPEN ASSIGNMENT
# ============================================================

@app.route("/admin/assignment/<aid>")
@admin_required
def admin_assignment(aid):
    a = get_assignment(aid)
    if not a:
        abort(404)
    ans = get_answer(aid)
    existing = safe_text(ans.get("answer_text")) if ans else ""

    return page(f"""
<div class="card">
<h2>{safe_text(a.get("title"))}</h2>
<p><b>Student:</b> {safe_text(a.get("student_name"))} ({safe_text(a.get("email"))})</p>
<p><b>Status:</b> <span class="badge">{safe_text(a.get("status"))}</span></p>
<p><b>Subject:</b> {safe_text(a.get("subject"))}</p>
<p><a class="btn" href="/assignment/{aid}/download">Download Student Assignment</a></p>
<h3>Question</h3><div class="answer">{safe_text(a.get("question") or a.get("description"))}</div>
</div>

<div class="card">
<h3>Update Status / Comment</h3>
<form method="post" action="/admin/assignment/{aid}/update">
<input type="hidden" name="csrf_token" value="{{{{ csrf_token }}}}">
<label>Status</label>
<select name="status">
{''.join(f'<option {"selected" if s==a.get("status") else ""}>{s}</option>' for s in ["assigned","submitted","received","reviewing","answered","completed","rejected"])}
</select>
<label>Comment</label>
<textarea name="admin_comment">{safe_text(a.get("admin_comment"))}</textarea>
<button>Save Status & Comment</button>
</form>
</div>

<div class="card">
<h3>Write Answer</h3>
<form method="post" action="/admin/assignment/{aid}/answer">
<input type="hidden" name="csrf_token" value="{{{{ csrf_token }}}}">
<textarea name="answer" style="min-height:350px" required>{existing}</textarea>
<button>Save Answer and Generate PDF</button>
</form>
</div>
""", "Manage Assignment")


@app.route("/admin/assignment/<aid>/update", methods=["POST"])
@admin_required
def update_assignment(aid):
    if not csrf_check():
        abort(400)
    if not get_assignment(aid):
        abort(404)

    status = safe_text(request.form.get("status"), 50)
    comment = safe_text(request.form.get("admin_comment"), 5000)

    try:
        db_update("assignments", {"id": f"eq.{aid}"}, {
            "status": status,
            "admin_comment": comment,
            "reviewed_by": None,
            "updated_at": now_iso(),
        })
        flash("Assignment status and comment updated.")
    except Exception as e:
        flash("Update failed: " + safe_text(str(e), 1000))

    return redirect(url_for("admin_assignment", aid=aid))


@app.route("/admin/assignment/<aid>/answer", methods=["POST"])
@admin_required
def save_answer(aid):
    if not csrf_check():
        abort(400)

    a = get_assignment(aid)
    if not a:
        abort(404)

    answer_text = safe_text(request.form.get("answer"), 50000)
    if not answer_text:
        flash("Answer cannot be empty.")
        return redirect(url_for("admin_assignment", aid=aid))

    try:
        pdf = build_pdf(
            a.get("title") or "Assignment",
            a.get("subject") or "",
            a.get("student_name") or "",
            a.get("question") or a.get("description") or "",
            answer_text,
        )

        pdf_name = secure_filename(a.get("title") or "answer") + "_answered.pdf"
        path = f"answer-pdfs/{aid}/{uuid.uuid4()}_{pdf_name}"
        storage_upload(pdf, path, "application/pdf")

        old = get_answer(aid)
        data = {
            "assignment_id": aid,
            "student_id": a.get("student_id"),
            "answer_text": answer_text,
            "answer_file_name": pdf_name,
            "answer_file_path": path,
            "generated_by": "Administrator",
            "status": "published",
            "updated_at": now_iso(),
        }

        if old:
            db_update("assignment_answers", {"id": f"eq.{old["id"]}"}, data)
        else:
            data["id"] = str(uuid.uuid4())
            db_insert("assignment_answers", data)

        db_update("assignments", {"id": f"eq.{aid}"}, {
            "answer_file_name": pdf_name,
            "answer_file_path": path,
            "answered_at": now_iso(),
            "answered_by": None if current_user().get("id") == "admin" else current_user().get("id"),
            "status": "answered",
            "updated_at": now_iso(),
        })

        flash("Answer saved. PDF generated without the screen watermark/logo.")
    except Exception as e:
        logger.exception(e)
        flash("Answer failed: " + safe_text(str(e), 1000))

    return redirect(url_for("admin_assignment", aid=aid))


# ============================================================
# DOCUMENT LIBRARY
# Past papers, notes, books, etc.
# ============================================================

@app.route("/documents")
@login_required
def documents():
    q = safe_text(request.args.get("q"), 255)
    dtype = safe_text(request.args.get("type"), 100)

    try:
        params = {
            "select": "*",
            "order": "created_at.desc",
        }
        if q:
            q2 = q.replace(",", " ").replace("(", " ").replace(")", " ")
            params["or"] = (
                f"title.ilike.*{q2}*,"
                f"description.ilike.*{q2}*,"
                f"subject.ilike.*{q2}*,"
                f"course.ilike.*{q2}*"
            )
        if dtype:
            params["document_type"] = f"eq.{dtype}"

        docs = db_select("document_library", params)
    except Exception:
        docs = []

    rows = "".join(
        f"""
<tr>
<td>{safe_text(d.get("title"))}</td>
<td>{safe_text(d.get("document_type"))}</td>
<td>{safe_text(d.get("subject"))}</td>
<td>{safe_text(d.get("course"))}</td>
<td>{safe_text(d.get("file_name"))}</td>
<td><a class="btn" href="/document/{d.get("id")}/download">View / Download</a></td>
</tr>
"""
        for d in docs if d.get("is_active") is not False
    )

    return page(f"""
<div class="card">
<h2>KOJA Learning Library</h2>
<p class="small">Past papers • Notes • Books • Academic documents • Study materials</p>
<form method="get">
<input name="q" value="{safe_text(q)}" placeholder="Search title, subject, course...">
<select name="type">
<option value="">All types</option>
<option {"selected" if dtype=="past_paper" else ""}>past_paper</option>
<option {"selected" if dtype=="notes" else ""}>notes</option>
<option {"selected" if dtype=="book" else ""}>book</option>
<option {"selected" if dtype=="academic" else ""}>academic</option>
</select>
<button>Search</button>
</form>
</div>
<div class="card">
<table>
<tr><th>Title</th><th>Type</th><th>Subject</th><th>Course</th><th>File</th><th>Action</th></tr>
{rows or "<tr><td colspan='6'>No documents found.</td></tr>"}
</table>
</div>
""", "Library")


@app.route("/admin/document/upload", methods=["GET", "POST"])
@admin_required
def admin_document_upload():
    if request.method == "POST":
        if not csrf_check():
            abort(400)

        title = safe_text(request.form.get("title"), 255)
        desc = safe_text(request.form.get("description"), 5000)
        dtype = safe_text(request.form.get("document_type"), 100) or "academic"
        subject = safe_text(request.form.get("subject"), 255)
        course = safe_text(request.form.get("course"), 255)
        level = safe_text(request.form.get("class_level"), 255)
        public = request.form.get("is_public") == "on"
        f = request.files.get("file")

        if not title or not f or not f.filename or not allowed_file(f.filename):
            flash("Title and supported file are required.")
            return redirect(url_for("admin_document_upload"))

        try:
            did = str(uuid.uuid4())
            filename = secure_filename(f.filename)
            data = f.read()
            mime = f.content_type or "application/octet-stream"
            path = f"library/{did}/{filename}"
            storage_upload(data, path, mime)

            u = current_user()
            db_insert("document_library", {
                "id": did,
                "title": title,
                "description": desc,
                "document_type": dtype,
                "subject": subject,
                "course": course,
                "class_level": level,
                "file_name": filename,
                "file_path": path,
                "file_url": None,
                "file_size": len(data),
                "mime_type": mime,
                "uploaded_by": None,
                "uploader_name": u.get("student_name"),
                "uploader_email": u.get("email"),
                "uploader_role": "admin",
                "is_public": public,
                "is_active": True,
                "download_count": 0,
                "view_count": 0,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })
            flash("Library document uploaded.")
            return redirect(url_for("documents"))
        except Exception as e:
            logger.exception(e)
            flash("Document upload failed: " + safe_text(str(e), 1000))

    return page("""
<div class="card">
<h2>Upload Learning Resource</h2>
<p class="small">Use this for past papers, notes, books and other resources.</p>
<form method="post" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label>Title</label><input name="title" required>
<label>Description</label><textarea name="description"></textarea>
<label>Type</label>
<select name="document_type">
<option value="past_paper">Past Paper</option>
<option value="notes">Notes</option>
<option value="book">Book</option>
<option value="academic">Academic</option>
</select>
<label>Subject</label><input name="subject">
<label>Course</label><input name="course">
<label>Class level</label><input name="class_level">
<label>File</label><input type="file" name="file" required>
<label><input type="checkbox" name="is_public"> Mark as public resource</label>
<br><br>
<button>Upload Resource</button>
</form>
</div>
""", "Upload Resource")


@app.route("/document/<did>/download")
@login_required
def document_download(did):
    d = get_document(did)
    if not d or d.get("is_active") is False:
        abort(404)

    try:
        data = storage_download(d.get("file_path"))

        count = int(d.get("download_count") or 0) + 1
        views = int(d.get("view_count") or 0) + 1
        db_update("document_library", {"id": f"eq.{did}"}, {
            "download_count": count,
            "view_count": views,
            "updated_at": now_iso(),
        })

        log_record(did, current_user().get("id"), "download")
        log_record(did, current_user().get("id"), "view")

        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=d.get("file_name") or "document",
            mimetype=d.get("mime_type") or "application/octet-stream",
        )
    except Exception:
        abort(404)


# ============================================================
# ADMIN LOGS - ADMIN ONLY
# ============================================================

@app.route("/admin/logs")
@admin_required
def admin_logs():
    try:
        logs = db_select("document_records", {
            "select": "*",
            "order": "created_at.desc",
            "limit": "300",
        })
    except Exception:
        logs = []

    rows = "".join(
        f"""
<tr>
<td>{safe_text(x.get("action"))}</td>
<td>{safe_text(x.get("user_id"))}</td>
<td>{safe_text(x.get("ip_address"))}</td>
<td>{safe_text(x.get("created_at"))}</td>
</tr>
"""
        for x in logs
    )

    return page(f"""
<div class="card">
<h2>KOJA Activity Logs</h2>
<p class="small">Visible to administrators only. Web opening is recorded once per login session.</p>
<table>
<tr><th>Action</th><th>User</th><th>IP</th><th>Time</th></tr>
{rows or "<tr><td colspan='4'>No logs.</td></tr>"}
</table>
</div>
""", "Admin Logs")


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_KEY:
        missing.append("SUPABASE_SERVICE_KEY")
    if not ADMIN_EMAIL:
        missing.append("KOJA_ADMIN_EMAIL")
    if not ADMIN_PASSWORD:
        missing.append("KOJA_ADMIN_PASSWORD")

    if missing:
        return jsonify({
            "status": "error",
            "missing": missing,
        }), 500

    try:
        r = sb_request("GET", "assignments", {
            "select": "id",
            "limit": "1",
        }, timeout=10)

        if not r.ok:
            return jsonify({"status": "error", "supabase": r.text}), 500

        return jsonify({
            "status": "ok",
            "app": APP_NAME,
            "supabase": "connected",
            "ai": False,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
# ERRORS / START
# ============================================================

@app.errorhandler(413)
def too_large(e):
    return page("<div class='card'><h2>File too large</h2><p>Maximum upload size is 20 MB.</p></div>", "File Too Large"), 413


@app.errorhandler(404)
def not_found(e):
    return page("<div class='card'><h2>Page not found</h2><a class='btn' href='/'>Home</a></div>", "Not Found"), 404


@app.errorhandler(403)
def forbidden(e):
    return page("<div class='card'><h2>Access denied</h2></div>", "Access Denied"), 403


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
