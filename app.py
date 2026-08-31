import os
import io
import json
import uuid
import secrets
import logging
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, flash, send_file, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

# ============================================================
# KOJA AFRICA / KOJA ZM
# Knowledge • Questions • Answers
# Flask + Supabase REST API
# ============================================================

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "koja-files")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_NAME = os.getenv("ADMIN_NAME", "KOJA Administrator")

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "txt", "jpg", "jpeg", "png", "webp"
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("koja")

# ------------------------------------------------------------
# Basic configuration validation
# ------------------------------------------------------------

def configured():
    return bool(SUPABASE_URL and SUPABASE_KEY)

def require_config():
    if not configured():
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY are required. "
            "Set them in Render Environment Variables."
        )

def headers(extra=None):
    require_config()
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h

# ------------------------------------------------------------
# Supabase REST helpers
# ------------------------------------------------------------

def sb_get(table, params=None, single=False):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers({"Accept": "application/json"}),
        params=params or {},
        timeout=30,
    )
    if r.status_code >= 400:
        log.error("GET %s %s: %s", table, r.status_code, r.text)
        raise RuntimeError(f"Supabase GET {table} failed: {r.text}")
    data = r.json()
    if single:
        return data[0] if data else None
    return data

def sb_insert(table, data, select="*"):
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers({
            "Prefer": "return=representation",
            "Accept": "application/json",
        }),
        params={"select": select},
        json=data,
        timeout=30,
    )
    if r.status_code >= 400:
        log.error("INSERT %s %s: %s", table, r.status_code, r.text)
        raise RuntimeError(f"Supabase INSERT {table} failed: {r.text}")
    data = r.json()
    return data[0] if isinstance(data, list) and data else data

def sb_update(table, filters, data, select="*"):
    params = dict(filters or {})
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers({
            "Prefer": "return=representation",
            "Accept": "application/json",
        }),
        params={**params, "select": select},
        json=data,
        timeout=30,
    )
    if r.status_code >= 400:
        log.error("UPDATE %s %s: %s", table, r.status_code, r.text)
        raise RuntimeError(f"Supabase UPDATE {table} failed: {r.text}")
    body = r.json()
    return body[0] if isinstance(body, list) and body else body

def sb_delete(table, filters):
    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers({"Prefer": "return=minimal"}),
        params=filters or {},
        timeout=30,
    )
    if r.status_code >= 400:
        log.error("DELETE %s %s: %s", table, r.status_code, r.text)
        raise RuntimeError(f"Supabase DELETE {table} failed: {r.text}")
    return True

def count_rows(table, params=None):
    p = dict(params or {})
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers({
            "Prefer": "count=exact",
            "Range": "0-0",
            "Accept": "application/json",
        }),
        params=p,
        timeout=30,
    )
    if r.status_code >= 400:
        return 0
    cr = r.headers.get("Content-Range", "")
    try:
        return int(cr.split("/")[-1])
    except Exception:
        try:
            return len(r.json())
        except Exception:
            return 0

# ------------------------------------------------------------
# Storage helpers
# ------------------------------------------------------------

def storage_upload(file_storage, folder="uploads"):
    require_config()
    original = secure_filename(file_storage.filename or "file")
    if not original:
        raise ValueError("Invalid filename.")
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("File type is not allowed.")

    path = f"{folder}/{datetime.now(timezone.utc).strftime('%Y/%m')}/{uuid.uuid4()}-{original}"
    data = file_storage.read()
    content_type = file_storage.mimetype or "application/octet-stream"

    r = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_BUCKET, safe='')}/{quote(path, safe='/')}",
        headers=headers({"Content-Type": content_type, "x-upsert": "false"}),
        data=data,
        timeout=60,
    )
    if r.status_code >= 400:
        log.error("Storage upload failed: %s %s", r.status_code, r.text)
        raise RuntimeError(f"Storage upload failed: {r.text}")

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{quote(SUPABASE_BUCKET, safe='')}/{quote(path, safe='/')}"
    return path, public_url, original, len(data), content_type

def storage_download(path):
    require_config()
    r = requests.get(
        f"{SUPABASE_URL}/storage/v1/object/{quote(SUPABASE_BUCKET, safe='')}/{quote(path, safe='/')}",
        headers=headers(),
        timeout=60,
    )
    if r.status_code >= 400:
        abort(404)
    return r.content, r.headers.get("Content-Type", "application/octet-stream")

# ------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def current_user():
    return session.get("user")

def is_admin():
    u = current_user()
    return bool(u and u.get("is_admin"))

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please log in first.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Administrator login required.", "warning")
            return redirect(url_for("login", next=request.path))
        if not is_admin():
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def clean(v):
    return (v or "").strip()

def pgr(params, column, value):
    if value:
        params[column] = f"eq.{value}"

def safe_json(value, fallback=None):
    if fallback is None:
        fallback = {}
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback

def log_activity(action, description="", user_id=None, email=None):
    try:
        sb_insert("activity_logs", {
            "user_id": user_id,
            "action": action,
            "description": description,
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get("User-Agent", ""),
            "email": email,
        })
    except Exception as e:
        log.warning("Activity log skipped: %s", e)

def notify(email, title, message, request_id=None):
    try:
        sb_insert("koja_notifications", {
            "client_email": email,
            "request_id": request_id,
            "title": title,
            "message": message,
        })
    except Exception as e:
        log.warning("Notification skipped: %s", e)

# ------------------------------------------------------------
# User authentication
# Supports both profiles and koja_users tables.
# ------------------------------------------------------------

def find_user(email):
    email = clean(email).lower()
    if not email:
        return None

    try:
        rows = sb_get("profiles", {
            "select": "id,name,full_name,email,role,password_hash,phone,institution,student_number,is_active,is_admin",
            "email": f"eq.{email}",
            "limit": "1",
        })
        if rows:
            u = rows[0]
            return {
                "id": u.get("id"),
                "name": u.get("full_name") or u.get("name") or email,
                "email": u.get("email") or email,
                "role": u.get("role") or ("admin" if u.get("is_admin") else "student"),
                "password_hash": u.get("password_hash"),
                "phone": u.get("phone"),
                "institution": u.get("institution"),
                "student_number": u.get("student_number"),
                "is_active": u.get("is_active", True),
                "is_admin": bool(u.get("is_admin")) or u.get("role") == "admin",
                "table": "profiles",
            }
    except Exception as e:
        log.warning("profiles lookup failed: %s", e)

    try:
        rows = sb_get("koja_users", {
            "select": "id,full_name,email,phone,password_hash",
            "email": f"eq.{email}",
            "limit": "1",
        })
        if rows:
            u = rows[0]
            return {
                "id": u.get("id"),
                "name": u.get("full_name") or email,
                "email": u.get("email") or email,
                "role": "student",
                "password_hash": u.get("password_hash"),
                "phone": u.get("phone"),
                "institution": "",
                "student_number": "",
                "is_active": True,
                "is_admin": False,
                "table": "koja_users",
            }
    except Exception as e:
        log.warning("koja_users lookup failed: %s", e)

    return None

def ensure_env_admin():
    """
    Creates/updates the configured admin in profiles when ADMIN_EMAIL
    and ADMIN_PASSWORD are supplied. This fixes the common situation
    where an admin can see the database but cannot log into the Flask app.
    """
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return

    try:
        existing = find_user(ADMIN_EMAIL)
        ph = generate_password_hash(ADMIN_PASSWORD)

        if existing and existing.get("table") == "profiles":
            sb_update("profiles", {"id": f"eq.{existing['id']}"}, {
                "full_name": ADMIN_NAME,
                "email": ADMIN_EMAIL,
                "password_hash": ph,
                "role": "admin",
                "is_admin": True,
                "is_active": True,
            })
            return

        if existing:
            # Existing koja_users record cannot be made admin because
            # its table has no admin columns. Create a profiles admin.
            pass

        sb_insert("profiles", {
            "full_name": ADMIN_NAME,
            "email": ADMIN_EMAIL,
            "role": "admin",
            "password_hash": ph,
            "is_admin": True,
            "is_active": True,
        })
        log.info("Configured administrator created.")
    except Exception as e:
        log.warning("Admin bootstrap failed: %s", e)

# ------------------------------------------------------------
# Base template
# ------------------------------------------------------------

BASE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title or "KOJA Africa" }}</title>
<style>
:root{--p:#0b5ed7;--dark:#102033;--bg:#f5f7fb;--card:#fff;--muted:#667085;--ok:#198754;--danger:#dc3545;--border:#e5e7eb}
*{box-sizing:border-box} body{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:#182230}
a{color:var(--p);text-decoration:none} a:hover{text-decoration:underline}
nav{background:var(--dark);color:#fff;padding:12px 4%;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
nav a{color:#fff;font-weight:600} .brand{font-size:20px;margin-right:auto}
.container{width:min(1200px,94%);margin:24px auto}.hero{background:linear-gradient(135deg,#0b5ed7,#17365d);color:#fff;border-radius:18px;padding:30px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;box-shadow:0 2px 8px #00000008}
h1,h2,h3{margin-top:0}.muted{color:var(--muted)}.small{font-size:13px}
.btn,button{display:inline-block;border:0;border-radius:9px;background:var(--p);color:#fff;padding:10px 15px;cursor:pointer;font-weight:600}
.btn.secondary{background:#475467}.btn.success{background:var(--ok)}.btn.danger{background:var(--danger)}
input,select,textarea{width:100%;padding:11px;border:1px solid #cfd5dd;border-radius:8px;margin:5px 0 14px;background:#fff}
textarea{min-height:120px;resize:vertical}label{font-weight:600;font-size:14px}
table{width:100%;border-collapse:collapse;background:#fff}th,td{padding:10px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
.badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#eef2ff;font-size:12px}
.alert{padding:12px 14px;border-radius:9px;margin:10px 0;background:#fff3cd}.alert.success{background:#d1e7dd}.alert.danger{background:#f8d7da}
.stat{font-size:30px;font-weight:800}.actions{display:flex;gap:8px;flex-wrap:wrap}
footer{padding:30px 4%;color:var(--muted);text-align:center}
@media(max-width:650px){table{display:block;overflow:auto}.hero{padding:22px}.container{width:96%}}
</style>
</head>
<body>
<nav>
<a class="brand" href="{{ url_for('home') }}">KOJA AFRICA</a>
<a href="{{ url_for('universities') }}">Universities</a>
<a href="{{ url_for('programmes') }}">Programmes</a>
<a href="{{ url_for('documents') }}">Resources</a>
<a href="{{ url_for('questions') }}">Questions</a>
{% if user %}
<a href="{{ url_for('dashboard') }}">Dashboard</a>
{% if user.is_admin %}<a href="{{ url_for('admin') }}">Admin</a>{% endif %}
<a href="{{ url_for('logout') }}">Logout</a>
{% else %}
<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Register</a>
{% endif %}
</nav>
<div class="container">
{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}
<div class="alert {{ category }}">{{ message }}</div>
{% endfor %}
{% endwith %}
{{ body|safe }}
</div>
<footer>KOJA AFRICA — Knowledge • Questions • Answers</footer>
</body>
</html>
"""

def page(title, template, **ctx):
    body = render_template_string(template, **ctx)
    return render_template_string(BASE, title=title, body=body, user=current_user())

# ------------------------------------------------------------
# Home
# ------------------------------------------------------------

@app.route("/")
def home():
    stats = {}
    for table in ["universities", "university_programmes", "university_applications", "documents", "questions"]:
        stats[table] = count_rows(table)

    return page("KOJA Africa", r"""
<div class="hero">
<h1>KOJA AFRICA</h1>
<p>Knowledge • Questions • Answers</p>
<p>University admissions, academic programmes, requirements, assignments and learning resources.</p>
<div class="actions">
<a class="btn" href="{{ url_for('universities') }}">Explore Universities</a>
<a class="btn secondary" href="{{ url_for('programmes') }}">Find a Programme</a>
</div>
</div>
<br>
<div class="grid">
<div class="card"><div class="stat">{{ stats.universities }}</div><div class="muted">Universities</div></div>
<div class="card"><div class="stat">{{ stats.university_programmes }}</div><div class="muted">Programmes</div></div>
<div class="card"><div class="stat">{{ stats.university_applications }}</div><div class="muted">Applications</div></div>
<div class="card"><div class="stat">{{ stats.documents }}</div><div class="muted">Learning resources</div></div>
</div>
<br>
<div class="card">
<h2>University Admissions</h2>
<p>Compare institutions, search programmes, check entry requirements and start an application.</p>
</div>
""", stats=stats)

# ------------------------------------------------------------
# Authentication
# ------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = clean(request.form.get("full_name"))
        email = clean(request.form.get("email")).lower()
        phone = clean(request.form.get("phone"))
        institution = clean(request.form.get("institution"))
        student_number = clean(request.form.get("student_number"))
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Name, email and password are required.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return redirect(url_for("register"))

        try:
            if find_user(email):
                flash("An account with that email already exists.", "danger")
                return redirect(url_for("login"))

            user = sb_insert("profiles", {
                "full_name": name,
                "name": name,
                "email": email,
                "phone": phone,
                "institution": institution,
                "student_number": student_number,
                "password_hash": generate_password_hash(password),
                "role": "student",
                "is_admin": False,
                "is_active": True,
            })
            session["user"] = {
                "id": user.get("id"),
                "name": name,
                "email": email,
                "role": "student",
                "phone": phone,
                "institution": institution,
                "student_number": student_number,
                "is_admin": False,
            }
            log_activity("register", "New student registration", user.get("id"), email)
            flash("Account created successfully.", "success")
            return redirect(url_for("dashboard"))
        except Exception as e:
            flash(f"Registration failed: {e}", "danger")

    return page("Register", r"""
<div class="card">
<h1>Create KOJA account</h1>
<form method="post">
<label>Full name</label><input name="full_name" required>
<label>Email</label><input type="email" name="email" required>
<label>Phone</label><input name="phone">
<label>Institution</label><input name="institution">
<label>Student number</label><input name="student_number">
<label>Password</label><input type="password" name="password" minlength="6" required>
<button>Create account</button>
</form>
</div>
""")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = clean(request.form.get("email")).lower()
        password = request.form.get("password", "")
        next_url = request.form.get("next") or url_for("dashboard")

        # Allow the configured environment admin to work immediately.
        if ADMIN_EMAIL and ADMIN_PASSWORD and email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            ensure_env_admin()

        try:
            user = find_user(email)
        except Exception as e:
            flash(f"Login service error: {e}", "danger")
            return redirect(url_for("login"))

        if not user or not user.get("password_hash"):
            flash("Invalid login credentials.", "danger")
            return redirect(url_for("login"))

        if user.get("is_active") is False:
            flash("This account is inactive. Contact the administrator.", "danger")
            return redirect(url_for("login"))

        try:
            valid = check_password_hash(user["password_hash"], password)
        except Exception:
            valid = False

        if not valid:
            flash("Invalid login credentials.", "danger")
            return redirect(url_for("login"))

        session["user"] = {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "phone": user.get("phone"),
            "institution": user.get("institution"),
            "student_number": user.get("student_number"),
            "is_admin": user.get("is_admin", False),
        }
        log_activity("login", "User login", user["id"], user["email"])
        return redirect(next_url)

    return page("Login", r"""
<div class="card">
<h1>Login</h1>
<p class="muted">Use the email and password registered in KOJA.</p>
<form method="post">
<input type="hidden" name="next" value="{{ request.args.get('next','') }}">
<label>Email</label><input type="email" name="email" required>
<label>Password</label><input type="password" name="password" required>
<button>Login</button>
</form>
<p>New student? <a href="{{ url_for('register') }}">Create an account</a></p>
</div>
""")

@app.route("/logout")
def logout():
    u = current_user()
    if u:
        log_activity("logout", "User logout", u.get("id"), u.get("email"))
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

# ------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    u = current_user()
    email = u["email"]
    applications = []
    questions_ = []
    requests_ = []
    notifications_ = []

    try:
        applications = sb_get("university_applications", {
            "select": "*",
            "user_id": f"eq.{u['id']}",
            "order": "created_at.desc",
        })
    except Exception:
        pass

    try:
        questions_ = sb_get("questions", {
            "select": "*",
            "student_id": f"eq.{u['id']}",
            "order": "created_at.desc",
        })
    except Exception:
        pass

    try:
        requests_ = sb_get("koja_service_requests", {
            "select": "*",
            "client_email": f"eq.{email}",
            "order": "created_at.desc",
        })
    except Exception:
        pass

    try:
        notifications_ = sb_get("koja_notifications", {
            "select": "*",
            "client_email": f"eq.{email}",
            "order": "created_at.desc",
            "limit": "20",
        })
    except Exception:
        pass

    return page("Dashboard", r"""
<h1>Student Dashboard</h1>
<div class="card">
<h2>Welcome, {{ user.name }}</h2>
<p>{{ user.email }}</p>
</div>
<br>
<div class="grid">
<div class="card"><h3>University applications</h3><div class="stat">{{ applications|length }}</div><a href="{{ url_for('my_applications') }}">View applications</a></div>
<div class="card"><h3>Questions</h3><div class="stat">{{ questions|length }}</div><a href="{{ url_for('questions') }}">Ask a question</a></div>
<div class="card"><h3>Service requests</h3><div class="stat">{{ requests|length }}</div></div>
<div class="card"><h3>Notifications</h3><div class="stat">{{ notifications|length }}</div></div>
</div>
<br>
<div class="card">
<h2>Quick actions</h2>
<div class="actions">
<a class="btn" href="{{ url_for('universities') }}">Find university</a>
<a class="btn" href="{{ url_for('programmes') }}">Find programme</a>
<a class="btn" href="{{ url_for('new_application') }}">Start application</a>
<a class="btn secondary" href="{{ url_for('new_question') }}">Ask academic question</a>
</div>
</div>
""", applications=applications, questions=questions_, requests=requests_, notifications=notifications_)

# ------------------------------------------------------------
# Universities
# ------------------------------------------------------------

@app.route("/universities")
def universities():
    q = clean(request.args.get("q"))
    params = {
        "select": "*",
        "is_active": "eq.true",
        "order": "name.asc",
    }
    if q:
        params["name"] = f"ilike.*{q}*"

    try:
        rows = sb_get("universities", params)
    except Exception as e:
        rows = []
        flash(str(e), "danger")

    # Programme counts are calculated from the actual relationship.
    counts = {}
    try:
        all_programmes = sb_get("university_programmes", {
            "select": "university_id",
            "is_active": "eq.true",
        })
        for p in all_programmes:
            uid = p.get("university_id")
            counts[uid] = counts.get(uid, 0) + 1
    except Exception:
        pass

    return page("Universities", r"""
<div class="card">
<h1>Zambian Universities & Institutions</h1>
<form method="get">
<input name="q" value="{{ q }}" placeholder="Search university">
<button>Search</button>
</form>
</div><br>
<div class="grid">
{% for u in rows %}
<div class="card">
<h2>{{ u.name }}</h2>
<p class="muted">{{ u.abbreviation or "" }} {{ ("• " ~ u.province) if u.province else "" }}</p>
<p>{{ u.description or "University information and admissions." }}</p>
<p><span class="badge">{{ counts.get(u.id, 0) }} programmes</span></p>
<div class="actions">
<a class="btn" href="{{ url_for('university_detail', university_id=u.id) }}">View university</a>
{% if u.application_url %}<a class="btn secondary" target="_blank" href="{{ u.application_url }}">Official application</a>{% endif %}
</div>
</div>
{% else %}
<div class="card"><p>No universities found.</p></div>
{% endfor %}
</div>
""", rows=rows, q=q, counts=counts)

@app.route("/universities/<uuid:university_id>")
def university_detail(university_id):
    try:
        u = sb_get("universities", {
            "select": "*",
            "id": f"eq.{university_id}",
            "limit": "1",
        }, single=True)
        if not u:
            abort(404)

        programmes = sb_get("university_programmes", {
            "select": "*",
            "university_id": f"eq.{university_id}",
            "is_active": "eq.true",
            "order": "programme_name.asc",
        })
    except Exception as e:
        flash(str(e), "danger")
        return redirect(url_for("universities"))

    return page(u["name"], r"""
<div class="hero">
<h1>{{ u.name }}</h1>
<p>{{ u.description or "University admissions and programme information." }}</p>
<div class="actions">
{% if u.application_url %}<a class="btn" target="_blank" href="{{ u.application_url }}">Apply on official website</a>{% endif %}
{% if u.admissions_url %}<a class="btn secondary" target="_blank" href="{{ u.admissions_url }}">Admissions information</a>{% endif %}
</div>
</div><br>
<div class="card">
<h2>University information</h2>
<table>
<tr><th>Institution type</th><td>{{ u.institution_type or "-" }}</td></tr>
<tr><th>Ownership</th><td>{{ u.ownership or "-" }}</td></tr>
<tr><th>Province</th><td>{{ u.province or "-" }}</td></tr>
<tr><th>District</th><td>{{ u.district or "-" }}</td></tr>
<tr><th>Campus</th><td>{{ u.campus or "-" }}</td></tr>
<tr><th>Application status</th><td>{{ u.application_status or "Unknown" }}</td></tr>
<tr><th>Deadline</th><td>{{ u.deadline or "-" }}</td></tr>
<tr><th>Fee</th><td>{{ u.application_fee_zmw or "-" }} ZMW</td></tr>
</table>
</div><br>
<div class="card">
<h2>Programmes ({{ programmes|length }})</h2>
<div class="grid">
{% for p in programmes %}
<div class="card">
<h3>{{ p.programme_name }}</h3>
<p class="muted">{{ p.qualification or p.qualification_level or "" }}</p>
<p><b>Duration:</b> {{ p.duration or p.study_duration or "-" }}</p>
<p><b>Required subjects:</b> {{ p.required_subjects or "Not specified" }}</p>
<p><b>Minimum grade:</b> {{ p.minimum_grade or p.minimum_points or "Not specified" }}</p>
<p><b>Status:</b> {{ p.application_status or "Unknown" }}</p>
<a class="btn" href="{{ url_for('programme_detail', programme_id=p.id) }}">View requirements</a>
</div>
{% endfor %}
</div>
</div>
""", u=u, programmes=programmes)

# ------------------------------------------------------------
# Programmes
# ------------------------------------------------------------

@app.route("/programmes")
def programmes():
    q = clean(request.args.get("q"))
    university_id = clean(request.args.get("university_id"))

    universities_ = []
    try:
        universities_ = sb_get("universities", {
            "select": "id,name",
            "is_active": "eq.true",
            "order": "name.asc",
        })
    except Exception:
        pass

    params = {
        "select": "*,universities(name)",
        "is_active": "eq.true",
        "order": "programme_name.asc",
        "limit": "500",
    }
    if q:
        params["programme_name"] = f"ilike.*{q}*"
    if university_id:
        params["university_id"] = f"eq.{university_id}"

    try:
        rows = sb_get("university_programmes", params)
    except Exception as e:
        # Some Supabase schemas may not expose the relation in REST.
        # Fall back to programme data and resolve university names locally.
        try:
            params["select"] = "*"
            rows = sb_get("university_programmes", params)
            lookup = {x["id"]: x["name"] for x in universities_}
            for x in rows:
                x["universities"] = {"name": lookup.get(x.get("university_id"), "Unknown")}
        except Exception:
            rows = []
            flash(str(e), "danger")

    return page("Programmes", r"""
<div class="card">
<h1>Find a University Programme</h1>
<form method="get">
<label>Programme</label>
<input name="q" value="{{ q }}" placeholder="e.g. Computer Science">
<label>University</label>
<select name="university_id">
<option value="">All universities</option>
{% for u in universities %}
<option value="{{ u.id }}" {% if university_id == u.id|string %}selected{% endif %}>{{ u.name }}</option>
{% endfor %}
</select>
<button>Search</button>
</form>
</div><br>
<div class="card">
<p><b>{{ rows|length }}</b> programme(s) found.</p>
</div><br>
<div class="grid">
{% for p in rows %}
<div class="card">
<h3>{{ p.programme_name }}</h3>
<p><b>{{ (p.universities.name if p.universities else "") }}</b></p>
<p class="muted">{{ p.qualification or p.qualification_level or p.programme_type or "" }}</p>
<p><b>Subjects:</b> {{ p.required_subjects or "Not specified" }}</p>
<p><b>Minimum:</b> {{ p.minimum_grade or p.minimum_points or "Not specified" }}</p>
<p><b>Fee:</b> {{ p.application_fee if p.application_fee is not none else "Not specified" }} {{ p.currency or "ZMW" }}</p>
<a class="btn" href="{{ url_for('programme_detail', programme_id=p.id) }}">Details</a>
</div>
{% else %}
<div class="card"><p>No programmes found.</p></div>
{% endfor %}
</div>
""", rows=rows, q=q, university_id=university_id, universities=universities_)

@app.route("/programmes/<uuid:programme_id>")
def programme_detail(programme_id):
    try:
        p = sb_get("university_programmes", {
            "select": "*",
            "id": f"eq.{programme_id}",
            "limit": "1",
        }, single=True)
        if not p:
            abort(404)

        u = sb_get("universities", {
            "select": "*",
            "id": f"eq.{p['university_id']}",
            "limit": "1",
        }, single=True)

        requirements = sb_get("university_application_requirements", {
            "select": "*",
            "programme_id": f"eq.{programme_id}",
            "order": "created_at.asc",
        })
    except Exception as e:
        flash(str(e), "danger")
        return redirect(url_for("programmes"))

    return page(p["programme_name"], r"""
<div class="hero">
<h1>{{ p.programme_name }}</h1>
<p>{{ u.name if u else "University" }}</p>
<div class="actions">
<a class="btn" href="{{ url_for('new_application', programme_id=p.id) }}">Start application</a>
{% if p.application_url %}<a class="btn secondary" target="_blank" href="{{ p.application_url }}">Official application</a>{% endif %}
</div>
</div><br>
<div class="card">
<h2>Programme details</h2>
<table>
<tr><th>Qualification</th><td>{{ p.qualification or p.qualification_level or "-" }}</td></tr>
<tr><th>Faculty</th><td>{{ p.faculty or "-" }}</td></tr>
<tr><th>School</th><td>{{ p.school or "-" }}</td></tr>
<tr><th>Duration</th><td>{{ p.duration or p.study_duration or "-" }}</td></tr>
<tr><th>Study mode</th><td>{{ p.study_mode or "-" }}</td></tr>
<tr><th>Entry level</th><td>{{ p.entry_level or "-" }}</td></tr>
<tr><th>Required subjects</th><td>{{ p.required_subjects or "-" }}</td></tr>
<tr><th>Minimum grade</th><td>{{ p.minimum_grade or "-" }}</td></tr>
<tr><th>Minimum points</th><td>{{ p.minimum_points or "-" }}</td></tr>
<tr><th>Entry requirements</th><td>{{ p.entry_requirements or p.requirements or "-" }}</td></tr>
<tr><th>Application requirements</th><td>{{ p.application_requirements or "-" }}</td></tr>
<tr><th>Application fee</th><td>{{ p.application_fee if p.application_fee is not none else "-" }} {{ p.currency or "ZMW" }}</td></tr>
<tr><th>Deadline</th><td>{{ p.deadline or "-" }}</td></tr>
<tr><th>Status</th><td>{{ p.application_status or "Unknown" }}</td></tr>
</table>
</div><br>
<div class="card">
<h2>Specific application requirements</h2>
{% for r in requirements %}
<div class="card">
<h3>{{ r.requirement_title }}</h3>
<p>{{ r.requirement_description or "" }}</p>
{% if r.document_type %}<p><b>Document:</b> {{ r.document_type }}</p>{% endif %}
{% if r.applicant_type %}<p><b>Applicant:</b> {{ r.applicant_type }}</p>{% endif %}
<p><b>Required:</b> {{ "Yes" if r.required else "No" }}</p>
{% if r.source_url %}<a target="_blank" href="{{ r.source_url }}">Source / verify</a>{% endif %}
</div>
{% else %}
<p>No programme-specific requirements have been entered yet. Use the university's official admissions page to verify current requirements.</p>
{% endfor %}
</div>
""", p=p, u=u, requirements=requirements)

# ------------------------------------------------------------
# University applications
# ------------------------------------------------------------

@app.route("/applications")
@login_required
def my_applications():
    u = current_user()
    try:
        rows = sb_get("university_applications", {
            "select": "*",
            "user_id": f"eq.{u['id']}",
            "order": "created_at.desc",
        })
    except Exception as e:
        rows = []
        flash(str(e), "danger")

    return page("My University Applications", r"""
<div class="actions">
<h1 style="margin-right:auto">My Applications</h1>
<a class="btn" href="{{ url_for('new_application') }}">New application</a>
</div>
<br>
<div class="card">
<table>
<tr><th>Application</th><th>University</th><th>Programme</th><th>Status</th><th>Payment</th><th>Date</th></tr>
{% for a in rows %}
<tr>
<td><a href="{{ url_for('application_detail', application_id=a.id) }}">{{ a.application_number or a.id }}</a></td>
<td>{{ a.university }}</td><td>{{ a.programme }}</td>
<td><span class="badge">{{ a.application_status or a.status }}</span></td>
<td>{{ a.payment_status }}</td><td>{{ a.created_at }}</td>
</tr>
{% else %}
<tr><td colspan="6">No applications yet.</td></tr>
{% endfor %}
</table>
</div>
""", rows=rows)

@app.route("/applications/new", methods=["GET", "POST"])
@login_required
def new_application():
    u = current_user()
    programme_id = request.args.get("programme_id") or request.form.get("programme_id")
    p = None
    university = None

    if programme_id:
        try:
            p = sb_get("university_programmes", {
                "select": "*",
                "id": f"eq.{programme_id}",
                "limit": "1",
            }, single=True)
            if p:
                university = sb_get("universities", {
                    "select": "*",
                    "id": f"eq.{p['university_id']}",
                    "limit": "1",
                }, single=True)
        except Exception:
            p = None

    if request.method == "POST":
        university_id = clean(request.form.get("university_id"))
        programme_id = clean(request.form.get("programme_id"))
        if not university_id or not programme_id:
            flash("Select a university and programme.", "danger")
            return redirect(url_for("new_application"))

        try:
            university = sb_get("universities", {
                "select": "*", "id": f"eq.{university_id}", "limit": "1"
            }, single=True)
            p = sb_get("university_programmes", {
                "select": "*", "id": f"eq.{programme_id}", "limit": "1"
            }, single=True)
            if not university or not p:
                raise ValueError("Selected university or programme was not found.")

            first = clean(request.form.get("first_name"))
            middle = clean(request.form.get("middle_names"))
            last = clean(request.form.get("last_name"))
            full = " ".join(x for x in [first, middle, last] if x)

            application = sb_insert("university_applications", {
                "user_id": u["id"],
                "university_id": university_id,
                "programme_id": programme_id,
                "university": university.get("name"),
                "programme": p.get("programme_name"),
                "intake": clean(request.form.get("intake")),
                "applicant_first_name": first,
                "applicant_middle_names": middle,
                "applicant_last_name": last,
                "full_name": full,
                "date_of_birth": request.form.get("date_of_birth") or None,
                "gender": clean(request.form.get("gender")),
                "nrc_number": clean(request.form.get("nrc_number")),
                "phone": clean(request.form.get("phone")),
                "email": clean(request.form.get("email")).lower(),
                "address": clean(request.form.get("address")),
                "province": clean(request.form.get("province")),
                "district": clean(request.form.get("district")),
                "previous_school": clean(request.form.get("previous_school")),
                "qualification": clean(request.form.get("qualification")),
                "application_information": clean(request.form.get("application_information")),
                "applicant_notes": clean(request.form.get("applicant_notes")),
                "status": "submitted",
                "application_status": "submitted",
                "payment_status": "unpaid",
                "application_fee": p.get("application_fee") or university.get("application_fee_zmw") or 0,
                "currency": p.get("currency") or "ZMW",
                "submitted_at": now_iso(),
            })
            notify(
                u["email"],
                "University application submitted",
                f"Your application for {p['programme_name']} at {university['name']} has been submitted."
            )
            log_activity("university_application", f"Application {application.get('id')}", u["id"], u["email"])
            flash("University application submitted successfully.", "success")
            return redirect(url_for("application_detail", application_id=application["id"]))
        except Exception as e:
            flash(f"Application failed: {e}", "danger")

    # University list for the form
    try:
        us = sb_get("universities", {
            "select": "id,name",
            "is_active": "eq.true",
            "order": "name.asc",
        })
    except Exception:
        us = []

    return page("University Application", r"""
<div class="card">
<h1>University Application</h1>
<form method="post">
<label>University</label>
<select name="university_id" required onchange="location.href='{{ url_for('new_application') }}?programme_id='+encodeURIComponent(this.value)">
<option value="">Select university</option>
{% for x in us %}
<option value="{{ x.id }}" {% if university and university.id == x.id %}selected{% endif %}>{{ x.name }}</option>
{% endfor %}
</select>

{% if university %}
<label>Programme</label>
<select name="programme_id" required>
<option value="">Select programme</option>
{% for x in programmes %}
<option value="{{ x.id }}" {% if p and p.id == x.id %}selected{% endif %}>{{ x.programme_name }}</option>
{% endfor %}
</select>
{% else %}
<p class="muted">Select a university above, then choose a programme.</p>
{% endif %}

<h3>Applicant details</h3>
<label>First name</label><input name="first_name" required>
<label>Middle names</label><input name="middle_names">
<label>Last name</label><input name="last_name" required>
<label>Date of birth</label><input type="date" name="date_of_birth">
<label>Gender</label><select name="gender"><option value="">Select</option><option>Male</option><option>Female</option><option>Other</option></select>
<label>NRC number</label><input name="nrc_number">
<label>Phone</label><input name="phone" value="{{ user.phone or '' }}">
<label>Email</label><input type="email" name="email" value="{{ user.email }}" required>
<label>Address</label><textarea name="address"></textarea>
<label>Province</label><input name="province">
<label>District</label><input name="district">
<label>Previous school</label><input name="previous_school">
<label>Previous qualification</label><input name="qualification">
<label>Intake</label><input name="intake" placeholder="e.g. 2027">
<label>Additional application information</label><textarea name="application_information"></textarea>
<label>Applicant notes</label><textarea name="applicant_notes"></textarea>
<button>Submit application</button>
</form>
</div>
""", us=us, university=university, p=p, programmes=(
        sb_get("university_programmes", {
            "select": "*",
            "university_id": f"eq.{university['id']}",
            "is_active": "eq.true",
            "order": "programme_name.asc",
        }) if university else []
    ))

@app.route("/applications/<uuid:application_id>")
@login_required
def application_detail(application_id):
    u = current_user()
    try:
        a = sb_get("university_applications", {
            "select": "*",
            "id": f"eq.{application_id}",
            "limit": "1",
        }, single=True)
    except Exception:
        a = None
    if not a:
        abort(404)
    if not u["is_admin"] and a.get("user_id") != u["id"]:
        abort(403)

    return page("Application", r"""
<div class="card">
<h1>University Application</h1>
<p><b>Application number:</b> {{ a.application_number or a.id }}</p>
<table>
<tr><th>University</th><td>{{ a.university }}</td></tr>
<tr><th>Programme</th><td>{{ a.programme }}</td></tr>
<tr><th>Applicant</th><td>{{ a.full_name }}</td></tr>
<tr><th>Email</th><td>{{ a.email }}</td></tr>
<tr><th>Phone</th><td>{{ a.phone }}</td></tr>
<tr><th>Status</th><td><span class="badge">{{ a.application_status or a.status }}</span></td></tr>
<tr><th>Payment</th><td>{{ a.payment_status }} — {{ a.application_fee }} {{ a.currency }}</td></tr>
<tr><th>Admin notes</th><td>{{ a.admin_notes or "-" }}</td></tr>
<tr><th>Rejection reason</th><td>{{ a.rejection_reason or "-" }}</td></tr>
<tr><th>Submitted</th><td>{{ a.submitted_at or a.created_at }}</td></tr>
</table>
</div>
""", a=a)

# ------------------------------------------------------------
# Questions
# ------------------------------------------------------------

@app.route("/questions")
@login_required
def questions():
    u = current_user()
    try:
        if u["is_admin"]:
            rows = sb_get("questions", {"select": "*", "order": "created_at.desc"})
        else:
            rows = sb_get("questions", {
                "select": "*",
                "student_id": f"eq.{u['id']}",
                "order": "created_at.desc",
            })
    except Exception as e:
        rows = []
        flash(str(e), "danger")

    return page("Questions", r"""
<div class="actions"><h1 style="margin-right:auto">Academic Questions</h1><a class="btn" href="{{ url_for('new_question') }}">Ask question</a></div>
<br>
<div class="grid">
{% for q in rows %}
<div class="card">
<h3>{{ q.subject or "Academic question" }}</h3>
<p>{{ q.question }}</p>
<p><span class="badge">{{ q.status }}</span></p>
{% if q.answer %}<hr><h3>Answer</h3><p>{{ q.answer }}</p>{% endif %}
</div>
{% else %}<div class="card"><p>No questions found.</p></div>{% endfor %}
</div>
""", rows=rows)

@app.route("/questions/new", methods=["GET", "POST"])
@login_required
def new_question():
    u = current_user()
    if request.method == "POST":
        try:
            q = sb_insert("questions", {
                "student_id": u["id"],
                "student_name": u["name"],
                "question": clean(request.form.get("question")),
                "subject": clean(request.form.get("subject")),
                "course": clean(request.form.get("course")),
                "class_level": clean(request.form.get("class_level")),
                "status": "pending",
            })
            log_activity("question", "Academic question submitted", u["id"], u["email"])
            flash("Question submitted.", "success")
            return redirect(url_for("questions"))
        except Exception as e:
            flash(f"Could not submit question: {e}", "danger")

    return page("Ask Question", r"""
<div class="card">
<h1>Ask an Academic Question</h1>
<form method="post">
<label>Subject</label><input name="subject">
<label>Course</label><input name="course">
<label>Class / Level</label><input name="class_level">
<label>Question</label><textarea name="question" required></textarea>
<button>Submit question</button>
</form>
</div>
""")

# ------------------------------------------------------------
# Documents / learning resources
# ------------------------------------------------------------

@app.route("/documents")
def documents():
    q = clean(request.args.get("q"))
    source_table = "documents"
    params = {
        "select": "*",
        "is_active": "eq.true",
        "order": "created_at.desc",
        "limit": "200",
    }
    if q:
        params["title"] = f"ilike.*{q}*"

    try:
        rows = sb_get(source_table, params)
    except Exception:
        try:
            source_table = "document_library"
            params.pop("is_active", None)
            rows = sb_get(source_table, params)
        except Exception as e:
            rows = []
            flash(str(e), "danger")

    return page("Learning Resources", r"""
<div class="card">
<h1>Learning Resources</h1>
<form method="get"><input name="q" value="{{ q }}" placeholder="Search documents"><button>Search</button></form>
</div><br>
<div class="grid">
{% for d in rows %}
<div class="card">
<h3>{{ d.title }}</h3>
<p>{{ d.description or "" }}</p>
<p class="muted">{{ d.subject or "" }} {{ d.course or "" }} {{ d.class_level or "" }}</p>
{% if d.file_url %}<a class="btn" target="_blank" href="{{ d.file_url }}">Open</a>{% elif d.file_path %}<a class="btn" href="{{ url_for('download_storage', path=d.file_path) }}">Download</a>{% endif %}
</div>
{% else %}<div class="card"><p>No documents available.</p></div>{% endfor %}
</div>
""", rows=rows, q=q)

@app.route("/storage/<path:path>")
@login_required
def download_storage(path):
    data, content_type = storage_download(path)
    u = current_user()
    log_activity("download", path, u["id"], u["email"])
    return send_file(io.BytesIO(data), mimetype=content_type, download_name=os.path.basename(path))

# ------------------------------------------------------------
# Admin
# ------------------------------------------------------------

@app.route("/admin")
@admin_required
def admin():
    stats = {
        "universities": count_rows("universities"),
        "programmes": count_rows("university_programmes"),
        "applications": count_rows("university_applications"),
        "questions": count_rows("questions"),
        "documents": count_rows("documents"),
        "requests": count_rows("koja_service_requests"),
        "users": count_rows("profiles"),
    }
    try:
        apps = sb_get("university_applications", {
            "select": "*",
            "order": "created_at.desc",
            "limit": "20",
        })
    except Exception:
        apps = []

    return page("Admin Dashboard", r"""
<div class="hero">
<h1>KOJA Administrator</h1>
<p>Manage universities, programmes, applications, questions and resources.</p>
</div><br>
<div class="grid">
{% for k,v in stats.items() %}
<div class="card"><div class="stat">{{ v }}</div><div class="muted">{{ k|capitalize }}</div></div>
{% endfor %}
</div><br>
<div class="grid">
<div class="card"><h2>University data</h2>
<a class="btn" href="{{ url_for('admin_universities') }}">Manage universities</a>
<a class="btn" href="{{ url_for('admin_programmes') }}">Manage programmes</a>
</div>
<div class="card"><h2>Admissions</h2>
<a class="btn" href="{{ url_for('admin_applications') }}">Manage applications</a>
</div>
<div class="card"><h2>Academic</h2>
<a class="btn" href="{{ url_for('admin_questions') }}">Manage questions</a>
</div>
<div class="card"><h2>System</h2>
<a class="btn secondary" href="{{ url_for('health') }}">System health</a>
</div>
</div><br>
<div class="card"><h2>Recent applications</h2>
<table><tr><th>Number</th><th>Student</th><th>University</th><th>Programme</th><th>Status</th></tr>
{% for a in apps %}
<tr><td><a href="{{ url_for('admin_application', application_id=a.id) }}">{{ a.application_number or a.id }}</a></td><td>{{ a.full_name }}</td><td>{{ a.university }}</td><td>{{ a.programme }}</td><td>{{ a.application_status or a.status }}</td></tr>
{% endfor %}
</table></div>
""", stats=stats, apps=apps)

@app.route("/admin/universities")
@admin_required
def admin_universities():
    rows = sb_get("universities", {"select":"*", "order":"name.asc"})
    return page("Manage Universities", r"""
<div class="actions"><h1 style="margin-right:auto">Universities</h1><a class="btn" href="{{ url_for('admin_university_new') }}">Add university</a></div>
<div class="card"><table><tr><th>Name</th><th>Province</th><th>Programmes</th><th>Status</th><th></th></tr>
{% for u in rows %}
<tr><td>{{ u.name }}</td><td>{{ u.province or "-" }}</td><td><a href="{{ url_for('admin_programmes') }}?university_id={{ u.id }}">View</a></td><td>{{ u.is_active }}</td><td><a class="btn" href="{{ url_for('admin_university_edit', university_id=u.id) }}">Edit</a></td></tr>
{% endfor %}</table></div>
""", rows=rows)

@app.route("/admin/universities/new", methods=["GET","POST"])
@admin_required
def admin_university_new():
    if request.method == "POST":
        try:
            u = sb_insert("universities", university_form_data())
            flash("University added.", "success")
            return redirect(url_for("admin_universities"))
        except Exception as e:
            flash(f"Could not add university: {e}", "danger")
    return university_form_page("Add University", None)

@app.route("/admin/universities/<uuid:university_id>/edit", methods=["GET","POST"])
@admin_required
def admin_university_edit(university_id):
    u = sb_get("universities", {"select":"*", "id":f"eq.{university_id}", "limit":"1"}, single=True)
    if not u: abort(404)
    if request.method == "POST":
        try:
            sb_update("universities", {"id":f"eq.{university_id}"}, university_form_data())
            flash("University updated.", "success")
            return redirect(url_for("admin_universities"))
        except Exception as e:
            flash(f"Could not update university: {e}", "danger")
    return university_form_page("Edit University", u)

def university_form_data():
    return {
        "name": clean(request.form.get("name")),
        "abbreviation": clean(request.form.get("abbreviation")),
        "institution_type": clean(request.form.get("institution_type")),
        "ownership": clean(request.form.get("ownership")),
        "province": clean(request.form.get("province")),
        "district": clean(request.form.get("district")),
        "campus": clean(request.form.get("campus")),
        "location": clean(request.form.get("location")),
        "description": clean(request.form.get("description")),
        "website": clean(request.form.get("website")),
        "application_url": clean(request.form.get("application_url")),
        "admissions_url": clean(request.form.get("admissions_url")),
        "admissions_email": clean(request.form.get("admissions_email")),
        "admissions_phone": clean(request.form.get("admissions_phone")),
        "application_fee_zmw": request.form.get("application_fee_zmw") or None,
        "intake": clean(request.form.get("intake")),
        "application_status": clean(request.form.get("application_status")) or "unknown",
        "deadline": request.form.get("deadline") or None,
        "accreditation_status": clean(request.form.get("accreditation_status")),
        "general_requirements": clean(request.form.get("general_requirements")),
        "required_documents": clean(request.form.get("required_documents")),
        "application_instructions": clean(request.form.get("application_instructions")),
        "undergraduate_admissions_url": clean(request.form.get("undergraduate_admissions_url")),
        "postgraduate_admissions_url": clean(request.form.get("postgraduate_admissions_url")),
        "contact_person": clean(request.form.get("contact_person")),
        "is_active": request.form.get("is_active") == "on",
        "last_verified_at": now_iso(),
        "last_admissions_check": now_iso(),
    }

def university_form_page(title, u):
    return page(title, r"""
<div class="card"><h1>{{ title }}</h1>
<form method="post">
{% for field,label in [
("name","University name"),("abbreviation","Abbreviation"),("institution_type","Institution type"),
("ownership","Ownership"),("province","Province"),("district","District"),("campus","Campus"),
("location","Location"),("website","Website"),("application_url","Application URL"),
("admissions_url","Admissions URL"),("admissions_email","Admissions email"),
("admissions_phone","Admissions phone"),("application_fee_zmw","Application fee ZMW"),
("intake","Intake"),("deadline","Deadline"),("accreditation_status","Accreditation status"),
("undergraduate_admissions_url","Undergraduate admissions URL"),
("postgraduate_admissions_url","Postgraduate admissions URL"),("contact_person","Contact person")
] %}
<label>{{ label }}</label><input name="{{ field }}" value="{{ u.get(field,'') if u else '' }}">
{% endfor %}
<label>Description</label><textarea name="description">{{ u.get('description','') if u else '' }}</textarea>
<label>General requirements</label><textarea name="general_requirements">{{ u.get('general_requirements','') if u else '' }}</textarea>
<label>Required documents</label><textarea name="required_documents">{{ u.get('required_documents','') if u else '' }}</textarea>
<label>Application instructions</label><textarea name="application_instructions">{{ u.get('application_instructions','') if u else '' }}</textarea>
<label>Application status</label><select name="application_status">
{% for x in ['unknown','open','closed','active','not_open'] %}<option {% if u and u.application_status==x %}selected{% endif %}>{{ x }}</option>{% endfor %}
</select>
<label><input type="checkbox" name="is_active" {% if not u or u.is_active %}checked{% endif %}> Active</label>
<br><button>Save</button>
</form></div>
""", title=title, u=u)

@app.route("/admin/programmes")
@admin_required
def admin_programmes():
    university_id = clean(request.args.get("university_id"))
    try:
        us = sb_get("universities", {"select":"id,name", "order":"name.asc"})
        params = {"select":"*", "order":"programme_name.asc", "limit":"1000"}
        if university_id:
            params["university_id"] = f"eq.{university_id}"
        ps = sb_get("university_programmes", params)
        names = {u["id"]:u["name"] for u in us}
        for p in ps:
            p["_university_name"] = names.get(p.get("university_id"), "Unknown")
    except Exception as e:
        us,ps=[],[]
        flash(str(e),"danger")
    return page("Manage Programmes", r"""
<div class="actions"><h1 style="margin-right:auto">Programmes</h1><a class="btn" href="{{ url_for('admin_programme_new') }}">Add programme</a></div>
<div class="card"><form method="get"><select name="university_id"><option value="">All universities</option>{% for u in us %}<option value="{{u.id}}" {% if university_id==u.id|string %}selected{% endif %}>{{u.name}}</option>{% endfor %}</select><button>Filter</button></form></div><br>
<div class="card"><table><tr><th>Programme</th><th>University</th><th>Subjects</th><th>Minimum</th><th>Status</th><th></th></tr>
{% for p in ps %}<tr><td>{{p.programme_name}}</td><td>{{p._university_name}}</td><td>{{p.required_subjects or '-'}}</td><td>{{p.minimum_grade or p.minimum_points or '-'}}</td><td>{{p.application_status}}</td><td><a class="btn" href="{{url_for('admin_programme_edit',programme_id=p.id)}}">Edit</a></td></tr>{% endfor %}
</table></div>
""", us=us, ps=ps, university_id=university_id)

@app.route("/admin/programmes/new", methods=["GET","POST"])
@admin_required
def admin_programme_new():
    if request.method == "POST":
        try:
            p = sb_insert("university_programmes", programme_form_data())
            flash("Programme added.", "success")
            return redirect(url_for("admin_programmes"))
        except Exception as e:
            flash(f"Could not add programme: {e}", "danger")
    return programme_form_page("Add Programme", None)

@app.route("/admin/programmes/<uuid:programme_id>/edit", methods=["GET","POST"])
@admin_required
def admin_programme_edit(programme_id):
    p = sb_get("university_programmes", {"select":"*", "id":f"eq.{programme_id}", "limit":"1"}, single=True)
    if not p: abort(404)
    if request.method == "POST":
        try:
            sb_update("university_programmes", {"id":f"eq.{programme_id}"}, programme_form_data())
            flash("Programme updated.", "success")
            return redirect(url_for("admin_programmes"))
        except Exception as e:
            flash(f"Could not update programme: {e}", "danger")
    return programme_form_page("Edit Programme", p)

def programme_form_data():
    return {
        "university_id": request.form.get("university_id") or None,
        "programme_name": clean(request.form.get("programme_name")),
        "programme_code": clean(request.form.get("programme_code")),
        "qualification_level": clean(request.form.get("qualification_level")),
        "qualification": clean(request.form.get("qualification")),
        "faculty": clean(request.form.get("faculty")),
        "school": clean(request.form.get("school")),
        "duration": clean(request.form.get("duration")),
        "study_mode": clean(request.form.get("study_mode")),
        "entry_level": clean(request.form.get("entry_level")),
        "requirements": clean(request.form.get("requirements")),
        "entry_requirements": clean(request.form.get("entry_requirements")),
        "application_requirements": clean(request.form.get("application_requirements")),
        "required_subjects": clean(request.form.get("required_subjects")),
        "minimum_grade": clean(request.form.get("minimum_grade")),
        "application_url": clean(request.form.get("application_url")),
        "application_status": clean(request.form.get("application_status")) or "unknown",
        "deadline": request.form.get("deadline") or None,
        "application_fee": request.form.get("application_fee") or None,
        "currency": clean(request.form.get("currency")) or "ZMW",
        "description": clean(request.form.get("description")),
        "programme_type": clean(request.form.get("programme_type")),
        "campus": clean(request.form.get("campus")),
        "study_duration": clean(request.form.get("study_duration")),
        "minimum_points": request.form.get("minimum_points") or None,
        "admissions_url": clean(request.form.get("admissions_url")),
        "last_verified_at": now_iso(),
        "is_active": request.form.get("is_active") == "on",
    }

def programme_form_page(title, p):
    try:
        us = sb_get("universities", {"select":"id,name", "order":"name.asc"})
    except Exception:
        us=[]
    return page(title, r"""
<div class="card"><h1>{{title}}</h1><form method="post">
<label>University</label><select name="university_id" required><option value="">Select</option>
{% for u in us %}<option value="{{u.id}}" {% if p and p.university_id==u.id %}selected{% endif %}>{{u.name}}</option>{% endfor %}</select>
{% for field,label in [
("programme_name","Programme name"),("programme_code","Programme code"),("qualification_level","Qualification level"),
("qualification","Qualification"),("faculty","Faculty"),("school","School"),("duration","Duration"),
("study_mode","Study mode"),("entry_level","Entry level"),("required_subjects","Required subjects"),
("minimum_grade","Minimum grade"),("application_url","Application URL"),("deadline","Deadline"),
("application_fee","Application fee"),("currency","Currency"),("programme_type","Programme type"),
("campus","Campus"),("study_duration","Study duration"),("minimum_points","Minimum points"),
("admissions_url","Admissions URL")
] %}<label>{{label}}</label><input name="{{field}}" value="{{p.get(field,'') if p else ''}}">{% endfor %}
<label>Requirements</label><textarea name="requirements">{{p.get('requirements','') if p else ''}}</textarea>
<label>Entry requirements</label><textarea name="entry_requirements">{{p.get('entry_requirements','') if p else ''}}</textarea>
<label>Application requirements</label><textarea name="application_requirements">{{p.get('application_requirements','') if p else ''}}</textarea>
<label>Description</label><textarea name="description">{{p.get('description','') if p else ''}}</textarea>
<label>Application status</label><select name="application_status">{% for x in ['unknown','active','open','closed'] %}<option {% if p and p.application_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select>
<label><input type="checkbox" name="is_active" {% if not p or p.is_active %}checked{% endif %}> Active</label><br>
<button>Save programme</button></form></div>
""", title=title, p=p, us=us)

# ------------------------------------------------------------
# Admin applications/questions
# ------------------------------------------------------------

@app.route("/admin/applications")
@admin_required
def admin_applications():
    rows = sb_get("university_applications", {"select":"*", "order":"created_at.desc", "limit":"500"})
    return page("Manage Applications", r"""
<div class="card"><h1>University Applications</h1><table>
<tr><th>Number</th><th>Applicant</th><th>University</th><th>Programme</th><th>Status</th><th>Payment</th><th></th></tr>
{% for a in rows %}<tr><td>{{a.application_number or a.id}}</td><td>{{a.full_name}}<br>{{a.email}}</td><td>{{a.university}}</td><td>{{a.programme}}</td><td>{{a.application_status or a.status}}</td><td>{{a.payment_status}}</td><td><a class="btn" href="{{url_for('admin_application',application_id=a.id)}}">Open</a></td></tr>{% endfor %}
</table></div>
""", rows=rows)

@app.route("/admin/applications/<uuid:application_id>", methods=["GET","POST"])
@admin_required
def admin_application(application_id):
    a = sb_get("university_applications", {"select":"*", "id":f"eq.{application_id}", "limit":"1"}, single=True)
    if not a: abort(404)

    if request.method == "POST":
        try:
            status = clean(request.form.get("application_status")) or "submitted"
            payment_status = clean(request.form.get("payment_status")) or a.get("payment_status","unpaid")
            sb_update("university_applications", {"id":f"eq.{application_id}"}, {
                "application_status": status,
                "status": status,
                "payment_status": payment_status,
                "admin_notes": clean(request.form.get("admin_notes")),
                "rejection_reason": clean(request.form.get("rejection_reason")),
                "reviewed_at": now_iso(),
                "reviewed_by": current_user()["id"],
            })
            notify(a.get("email"), "Application status updated",
                   f"Your application status is now: {status}.")
            flash("Application updated.", "success")
            return redirect(url_for("admin_application", application_id=application_id))
        except Exception as e:
            flash(f"Update failed: {e}", "danger")

    return page("Review Application", r"""
<div class="card"><h1>Review Application</h1>
<table>
{% for k,v in [('Application number',a.application_number or a.id),('Applicant',a.full_name),('Email',a.email),('Phone',a.phone),('University',a.university),('Programme',a.programme),('DOB',a.date_of_birth),('Gender',a.gender),('NRC',a.nrc_number),('Previous school',a.previous_school),('Qualification',a.qualification),('Address',a.address),('Province',a.province),('District',a.district),('Information',a.application_information)] %}
<tr><th>{{k}}</th><td>{{v or '-'}}</td></tr>{% endfor %}
</table></div><br>
<div class="card"><form method="post">
<label>Application status</label><select name="application_status">{% for x in ['draft','submitted','under_review','approved','rejected','completed','cancelled'] %}<option {% if a.application_status==x or a.status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select>
<label>Payment status</label><select name="payment_status">{% for x in ['unpaid','pending','paid','failed','refunded'] %}<option {% if a.payment_status==x %}selected{% endif %}>{{x}}</option>{% endfor %}</select>
<label>Admin notes</label><textarea name="admin_notes">{{a.admin_notes or ''}}</textarea>
<label>Rejection reason</label><textarea name="rejection_reason">{{a.rejection_reason or ''}}</textarea>
<button>Save review</button></form></div>
""", a=a)

@app.route("/admin/questions")
@admin_required
def admin_questions():
    rows = sb_get("questions", {"select":"*", "order":"created_at.desc", "limit":"500"})
    return page("Manage Questions", r"""
<div class="card"><h1>Academic Questions</h1><table>
<tr><th>Student</th><th>Question</th><th>Status</th><th></th></tr>
{% for q in rows %}<tr><td>{{q.student_name}}</td><td>{{q.question}}</td><td>{{q.status}}</td><td><a class="btn" href="{{url_for('admin_question',question_id=q.id)}}">Answer</a></td></tr>{% endfor %}
</table></div>
""", rows=rows)

@app.route("/admin/questions/<uuid:question_id>", methods=["GET","POST"])
@admin_required
def admin_question(question_id):
    q = sb_get("questions", {"select":"*", "id":f"eq.{question_id}", "limit":"1"}, single=True)
    if not q: abort(404)
    if request.method == "POST":
        try:
            sb_update("questions", {"id":f"eq.{question_id}"}, {
                "answer": clean(request.form.get("answer")),
                "answer_by": current_user()["name"],
                "answered_by": current_user()["id"],
                "answered_at": now_iso(),
                "status": clean(request.form.get("status")) or "answered",
                "updated_at": now_iso(),
            })
            flash("Answer saved.", "success")
            return redirect(url_for("admin_question", question_id=question_id))
        except Exception as e:
            flash(f"Could not save answer: {e}", "danger")
    return page("Answer Question", r"""
<div class="card"><h1>Answer Question</h1><p><b>{{q.student_name}}</b></p><p>{{q.question}}</p>
<form method="post"><label>Answer</label><textarea name="answer" required>{{q.answer or ''}}</textarea>
<label>Status</label><select name="status"><option>answered</option><option>pending</option><option>closed</option></select>
<button>Save answer</button></form></div>
""", q=q)

# ------------------------------------------------------------
# Admin: requirements for a programme
# ------------------------------------------------------------

@app.route("/admin/programmes/<uuid:programme_id>/requirements", methods=["GET","POST"])
@admin_required
def admin_requirements(programme_id):
    p = sb_get("university_programmes", {"select":"*", "id":f"eq.{programme_id}", "limit":"1"}, single=True)
    if not p: abort(404)

    if request.method == "POST":
        try:
            sb_insert("university_application_requirements", {
                "university_id": p["university_id"],
                "programme_id": programme_id,
                "applicant_type": clean(request.form.get("applicant_type")),
                "requirement_title": clean(request.form.get("requirement_title")),
                "requirement_description": clean(request.form.get("requirement_description")),
                "required": request.form.get("required") == "on",
                "source_url": clean(request.form.get("source_url")),
                "category": clean(request.form.get("category")),
                "document_type": clean(request.form.get("document_type")),
                "applicant_instruction": clean(request.form.get("applicant_instruction")),
                "last_verified_at": now_iso(),
            })
            flash("Requirement added.", "success")
        except Exception as e:
            flash(f"Could not add requirement: {e}", "danger")

    rows = sb_get("university_application_requirements", {
        "select":"*", "programme_id":f"eq.{programme_id}", "order":"created_at.asc"
    })
    return page("Programme Requirements", r"""
<div class="card"><h1>{{p.programme_name}}</h1><p>Add the documents/conditions applicants must meet.</p></div><br>
<div class="card"><h2>Add requirement</h2><form method="post">
<label>Title</label><input name="requirement_title" required>
<label>Description</label><textarea name="requirement_description"></textarea>
<label>Applicant type</label><input name="applicant_type" placeholder="e.g. School leaver">
<label>Category</label><input name="category" placeholder="e.g. Academic">
<label>Document type</label><input name="document_type" placeholder="e.g. Grade 12 certificate">
<label>Applicant instruction</label><textarea name="applicant_instruction"></textarea>
<label>Source URL</label><input name="source_url">
<label><input type="checkbox" name="required" checked> Required</label><br>
<button>Add requirement</button></form></div><br>
<div class="grid">{% for r in rows %}<div class="card"><h3>{{r.requirement_title}}</h3><p>{{r.requirement_description}}</p><p><b>Required:</b> {{r.required}}</p></div>{% endfor %}</div>
""", p=p, rows=rows)

# ------------------------------------------------------------
# Health / error handlers
# ------------------------------------------------------------

@app.route("/health")
def health():
    result = {"app": "ok", "supabase_configured": configured(), "time": now_iso()}
    if configured():
        try:
            result["universities"] = count_rows("universities")
            result["programmes"] = count_rows("university_programmes")
            result["database"] = "ok"
        except Exception as e:
            result["database"] = "error"
            result["error"] = str(e)
    return result

@app.errorhandler(403)
def forbidden(e):
    return page("Forbidden", "<div class='card'><h1>403</h1><p>You do not have permission to access this page.</p></div>"), 403

@app.errorhandler(404)
def not_found(e):
    return page("Not Found", "<div class='card'><h1>404</h1><p>The requested page was not found.</p></div>"), 404

@app.errorhandler(413)
def too_large(e):
    return page("File too large", "<div class='card'><h1>File too large</h1><p>The upload exceeds the configured limit.</p></div>"), 413

@app.errorhandler(500)
def server_error(e):
    log.exception("Server error")
    return page("Server Error", "<div class='card'><h1>Server error</h1><p>Please check the Render logs.</p></div>"), 500

# ------------------------------------------------------------
# Startup
# ------------------------------------------------------------

if __name__ == "__main__":
    # Do not fail import on Render when configuration is temporarily missing.
    if configured():
        try:
            ensure_env_admin()
        except Exception as e:
            log.warning("Startup admin check failed: %s", e)

    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
