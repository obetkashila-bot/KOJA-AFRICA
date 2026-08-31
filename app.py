import os
import io
import re
import json
import uuid
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
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

load_dotenv()

# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
# Single-file Flask + Supabase REST/Storage application
#
# This version is intentionally built around the EXISTING
# database structure supplied for the project. It does not
# require psycopg/psycopg2 and does not assume a clean schema.
#
# Required Render environment variables:
#   SUPABASE_URL
#   SUPABASE_SERVICE_KEY
#
# Optional:
#   SECRET_KEY
#   SUPABASE_STORAGE_BUCKET (default: koja-files)
#   ADMIN_EMAIL
#   ADMIN_PASSWORD
#   MAX_UPLOAD_MB (default: 10)
# ============================================================

APP_NAME = "KOJA AFRICA"
TAGLINE = "Knowledge • Questions • Answers"
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "koja-files").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-koja-secret-key")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("koja")

if not SUPABASE_URL or not SUPABASE_KEY:
    log.warning("SUPABASE_URL or SUPABASE_SERVICE_KEY is not configured.")

SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

SB_STORAGE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "txt", "jpg", "jpeg", "png",
    "webp", "xls", "xlsx", "csv"
}

# Existing tables confirmed by the user.
TABLES = {
    "profiles", "assignments", "assignment_answers", "assignment_files",
    "assignment_requests", "assignment_responses", "answers",
    "questions", "question_files", "question_attachments", "question_messages",
    "cv_requests", "farmer_profiles", "farmer_registrations",
    "farmer_requests", "tpin_requests", "tpn_requests",
    "appointments", "doctor_profiles", "lawyer_profiles", "teacher_profiles",
    "driver_profiles", "deliveries", "service_requests", "service_providers",
    "provider_services", "service_categories", "service_comments",
    "service_documents", "koja_service_requests", "koja_services",
    "koja_users", "koja_clients", "koja_request_files",
    "koja_request_history", "notifications", "koja_notifications",
    "activity_logs", "logs", "payments", "products", "purchases",
    "resource_purchases", "resources", "documents", "document_library",
    "document_records", "document_access_logs", "document_statistics",
    "downloads", "download_history", "result_verifications",
    "universities", "university_programmes",
    "university_application_requirements", "university_applications",
    "university_requests", "education_material_requests", "requests",
    "request_files", "settings", "KOJA ZM"
}

# ------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def clean(value, max_len=5000):
    if value is None:
        return ""
    return str(value).strip()[:max_len]

def allowed_file(filename):
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def current_user():
    return session.get("user")

def is_admin():
    u = current_user() or {}
    return bool(u.get("is_admin")) or str(u.get("role", "")).lower() in {
        "admin", "administrator", "superadmin"
    }

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in first.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in first.", "warning")
            return redirect(url_for("login", next=request.path))
        if not is_admin():
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def json_error(resp):
    try:
        return resp.json()
    except Exception:
        return {"message": resp.text[:1000]}

def sb_url(table):
    return f"{SUPABASE_URL}/rest/v1/{quote(table, safe='')}"

def storage_url(path):
    return (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{quote(STORAGE_BUCKET, safe='')}/{quote(path, safe='/')}"
    )

def public_storage_url(path):
    return (
        f"{SUPABASE_URL}/storage/v1/object/public/"
        f"{quote(STORAGE_BUCKET, safe='')}/{quote(path, safe='/')}"
    )

def sb_request(method, table, *, params=None, data=None, headers=None, timeout=25):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase environment variables are missing.")
    h = dict(SB_HEADERS)
    if headers:
        h.update(headers)
    return requests.request(
        method,
        sb_url(table),
        headers=h,
        params=params,
        json=data,
        timeout=timeout
    )

def sb_select(table, params=None, timeout=25):
    try:
        r = sb_request("GET", table, params=params, timeout=timeout)
        if r.status_code >= 400:
            log.error("SELECT %s failed: %s", table, json_error(r))
            return []
        return r.json() if r.text else []
    except Exception:
        log.exception("SELECT exception on %s", table)
        return []

def sb_insert(table, row, *, returning="representation"):
    """
    Inserts against the existing table. If an older merged schema rejects
    an optional column, remove that exact offending field and retry.
    This is useful because the project contains legacy/merged tables.
    """
    payload = dict(row)
    for _ in range(12):
        try:
            headers = {"Prefer": f"return={returning}"}
            r = sb_request("POST", table, data=payload, headers=headers)
            if r.status_code < 400:
                if not r.text:
                    return True, None
                body = r.json()
                return True, body[0] if isinstance(body, list) and body else body
            msg = json_error(r)
            text = json.dumps(msg)
            # PostgREST normally identifies a missing column as:
            # "Could not find the 'foo' column of 'table'..."
            m = re.search(r"Could not find the '([^']+)' column", text)
            if not m:
                m = re.search(r"column ['\"]?([A-Za-z0-9_]+)['\"]? does not exist", text)
            if m and m.group(1) in payload:
                bad = m.group(1)
                payload.pop(bad, None)
                continue
            log.error("INSERT %s failed: %s", table, msg)
            return False, msg
        except Exception as exc:
            log.exception("INSERT exception on %s", table)
            return False, {"message": str(exc)}
    return False, {"message": "Could not insert after schema compatibility retries."}

def sb_update(table, filters, patch):
    try:
        params = dict(filters)
        r = sb_request(
            "PATCH", table, params=params,
            data=patch,
            headers={"Prefer": "return=representation"}
        )
        if r.status_code >= 400:
            return False, json_error(r)
        body = r.json() if r.text else []
        return True, body[0] if isinstance(body, list) and body else body
    except Exception as exc:
        log.exception("UPDATE exception on %s", table)
        return False, {"message": str(exc)}

def sb_count(table):
    try:
        r = sb_request(
            "GET", table,
            params={"select": "id", "limit": "1"},
            headers={"Prefer": "count=exact"}
        )
        if r.status_code >= 400:
            return 0
        cr = r.headers.get("Content-Range", "")
        m = re.search(r"/(\d+|\*)$", cr)
        if m and m.group(1).isdigit():
            return int(m.group(1))
        return len(r.json() or [])
    except Exception:
        return 0

def find_profile_by_email(email):
    email = clean(email, 320).lower()
    rows = sb_select("profiles", {
        "select": "*",
        "email": f"eq.{email}",
        "limit": "1"
    })
    return rows[0] if rows else None

def find_profile_by_id(user_id):
    rows = sb_select("profiles", {
        "select": "*",
        "id": f"eq.{user_id}",
        "limit": "1"
    })
    return rows[0] if rows else None

def log_activity(action, description="", user_id=None):
    uid = user_id or (current_user() or {}).get("id")
    row = {
        "user_id": uid,
        "action": clean(action, 100),
        "description": clean(description, 2000),
        "ip_address": request.headers.get("X-Forwarded-For", request.remote_addr),
        "user_agent": request.headers.get("User-Agent", "")[:500],
        "created_at": now_iso(),
    }
    ok, _ = sb_insert("activity_logs", row)
    if not ok:
        # Some old schemas may not have all optional columns.
        row.pop("ip_address", None)
        row.pop("user_agent", None)
        sb_insert("activity_logs", row)

def notify(user_id, title, message, link=""):
    row = {
        "user_id": user_id,
        "title": clean(title, 250),
        "message": clean(message, 4000),
        "link": clean(link, 1000),
        "is_read": False,
        "created_at": now_iso(),
    }
    ok, _ = sb_insert("notifications", row)
    if not ok:
        row.pop("link", None)
        sb_insert("notifications", row)

def admin_bootstrap():
    """
    If ADMIN_EMAIL and ADMIN_PASSWORD are set, make that profile admin.
    It never exposes the password in the UI.
    """
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return
    p = find_profile_by_email(ADMIN_EMAIL)
    if p:
        patch = {"is_admin": True, "role": "admin", "is_active": True}
        sb_update("profiles", {"id": f"eq.{p['id']}"}, patch)
        return
    ok, created = sb_insert("profiles", {
        "name": "KOJA Administrator",
        "full_name": "KOJA Administrator",
        "email": ADMIN_EMAIL,
        "role": "admin",
        "is_admin": True,
        "is_active": True,
        "password_hash": generate_password_hash(ADMIN_PASSWORD),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    if ok:
        log.info("Created configured KOJA admin account: %s", ADMIN_EMAIL)

# ------------------------------------------------------------
# HTML shell
# ------------------------------------------------------------

BASE_CSS = """
:root{--bg:#f5f7fb;--card:#fff;--text:#172033;--muted:#667085;--primary:#0b6bcb;--dark:#102a43;--danger:#c62828;--ok:#16833b;--border:#e5e7eb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,Helvetica,sans-serif}
a{text-decoration:none;color:var(--primary)}.nav{background:var(--dark);color:#fff;padding:13px 16px;position:sticky;top:0;z-index:10}
.navin{max-width:1180px;margin:auto;display:flex;gap:14px;align-items:center;flex-wrap:wrap}.brand{font-weight:800;font-size:19px;color:#fff;margin-right:auto}
.nav a{color:#eaf2f8}.wrap{max-width:1180px;margin:22px auto;padding:0 14px}
.hero{background:linear-gradient(135deg,#102a43,#0b6bcb);color:#fff;padding:34px 24px;border-radius:18px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;box-shadow:0 2px 9px #0000000a;margin-bottom:16px}
h1,h2,h3{margin-top:0}small,.muted{color:var(--muted)}.stat{font-size:30px;font-weight:800}
form{display:grid;gap:10px}input,textarea,select{width:100%;padding:11px;border:1px solid #ccd2da;border-radius:9px;font:inherit;background:#fff}
textarea{min-height:120px;resize:vertical}button,.btn{display:inline-block;border:0;border-radius:9px;background:var(--primary);color:#fff;padding:10px 14px;cursor:pointer;font-weight:700}
.btn.secondary{background:#475467}.btn.ok{background:var(--ok)}.btn.danger{background:var(--danger)}.actions{display:flex;gap:8px;flex-wrap:wrap}
.flash{padding:12px;border-radius:9px;background:#fff3cd;border:1px solid #ffe69c;margin-bottom:10px}.flash.error{background:#fce8e6;border-color:#f4c7c3}.flash.success{background:#e7f6ec;border-color:#b7e1c3}
table{width:100%;border-collapse:collapse;background:#fff}th,td{padding:10px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
.badge{display:inline-block;padding:4px 8px;border-radius:99px;background:#eef2f7;font-size:12px}.footer{padding:30px 15px;text-align:center;color:var(--muted)}
@media(max-width:650px){.navin{gap:9px}.hero{padding:24px 18px}.card{padding:14px}th,td{font-size:13px}}
"""

def render_page(title, body, **ctx):
    u = current_user()
    return render_template_string(
        """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{title}} — KOJA AFRICA</title><style>{{css|safe}}</style></head>
<body>
<div class="nav"><div class="navin">
<a class="brand" href="{{url_for('home')}}">KOJA AFRICA</a>
<a href="{{url_for('home')}}">Home</a>
<a href="{{url_for('services')}}">Services</a>
<a href="{{url_for('universities')}}">Universities</a>
<a href="{{url_for('documents')}}">Resources</a>
{% if user %}<a href="{{url_for('dashboard')}}">Dashboard</a>{% endif %}
{% if admin %}<a href="{{url_for('admin_dashboard')}}">Admin</a>{% endif %}
{% if user %}<a href="{{url_for('logout')}}">Logout</a>{% else %}<a href="{{url_for('login')}}">Login</a>{% endif %}
</div></div>
<div class="wrap">
{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}<div class="flash {{category}}">{{message}}</div>{% endfor %}
{% endwith %}
{{body|safe}}
</div>
<div class="footer">KOJA AFRICA — {{tagline}}<br><small>Use the platform responsibly and protect your personal information.</small></div>
</body></html>""",
        title=title, body=body, css=BASE_CSS,
        user=u, admin=is_admin(), tagline=TAGLINE, **ctx
    )

def card_link(title, text, endpoint, button="Open"):
    return f"""<div class="card"><h3>{title}</h3><p>{text}</p>
<a class="btn" href="{url_for(endpoint)}">{button}</a></div>"""

# ------------------------------------------------------------
# Health / home
# ------------------------------------------------------------

@app.route("/health")
def health():
    result = {
        "status": "ok",
        "app": APP_NAME,
        "time": now_iso(),
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "database": "unknown",
    }
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            r = sb_request("GET", "profiles", params={"select": "id", "limit": "1"})
            result["database"] = "ok" if r.status_code < 400 else "error"
        except Exception as exc:
            result["database"] = "error"
            result["error"] = str(exc)[:300]
    return result, 200 if result["database"] in ("ok", "unknown") else 503

@app.route("/")
def home():
    body = f"""
<div class="hero"><h1>KOJA AFRICA</h1>
<p>{TAGLINE}</p>
<p>Academic support, documents, applications, professional services and local requests in one mobile-friendly platform.</p>
<div class="actions">
<a class="btn" href="{url_for('register')}">Create account</a>
<a class="btn secondary" href="{url_for('login')}">Log in</a>
</div></div>
<div class="grid">
{card_link("Questions & Answers","Ask academic questions and receive answers.","question_new")}
{card_link("Assignments","Submit assignment requests and files.","assignment_new")}
{card_link("CV Builder","Create a professional CV as a PDF.","cv_new")}
{card_link("Farmer Registration","Submit a farmer registration/request.","farmer_new")}
{card_link("TPIN Assistance","Request tax/TIN assistance.","tpin_new")}
{card_link("Doctor Booking","Request a medical appointment with a listed doctor.","doctor_book")}
{card_link("Lawyer Services","Submit a legal-service request.","lawyer_request")}
{card_link("Teacher/Tutor","Request tutoring or teaching support.","teacher_request")}
{card_link("Deliveries","Create and track a delivery request.","delivery_new")}
{card_link("Universities","Browse universities, programmes and requirements.","universities")}
{card_link("Resources","Browse academic documents and resources.","documents")}
</div>"""
    return render_page("Home", body)

# ------------------------------------------------------------
# Authentication — deliberately uses the existing profiles table
# ------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = clean(request.form.get("name"), 200)
        email = clean(request.form.get("email"), 320).lower()
        phone = clean(request.form.get("phone"), 80)
        password = request.form.get("password", "")
        institution = clean(request.form.get("institution"), 250)
        student_number = clean(request.form.get("student_number"), 150)

        if not name or not email or not password:
            flash("Name, email and password are required.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif find_profile_by_email(email):
            flash("An account with this email already exists. Use Log in or reset the account from the admin panel.", "error")
        else:
            ok, row = sb_insert("profiles", {
                "name": name,
                "full_name": name,
                "email": email,
                "phone": phone or None,
                "role": "student",
                "institution": institution or None,
                "student_number": student_number or None,
                "password_hash": generate_password_hash(password),
                "is_active": True,
                "is_admin": False,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })
            if ok:
                flash("Registration successful. You can now log in.", "success")
                log_activity("register", "New account registered", row.get("id") if row else None)
                return redirect(url_for("login"))
            flash("Registration failed. Check the Render logs for the Supabase error.", "error")

    body = f"""<div class="card"><h2>Create KOJA account</h2>
<form method="post">
<input name="name" placeholder="Full name" required>
<input name="email" type="email" placeholder="Email address" required>
<input name="phone" placeholder="Phone number">
<input name="institution" placeholder="School / institution">
<input name="student_number" placeholder="Student number">
<input name="password" type="password" placeholder="Password (minimum 6 characters)" required>
<button>Create account</button>
</form><p>Already registered? <a href="{url_for('login')}">Log in</a></p></div>"""
    return render_page("Register", body)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = clean(request.form.get("email"), 320).lower()
        password = request.form.get("password", "")
        p = find_profile_by_email(email)

        # This is the key fix for the project's previous "Invalid login credentials"
        # problem: the app authenticates against the actual profiles.password_hash
        # column instead of expecting a Supabase Auth user that may not exist.
        if not p:
            flash("Invalid email or password.", "error")
        elif p.get("is_active") is False:
            flash("This account is inactive. Contact the administrator.", "error")
        elif not p.get("password_hash"):
            flash("This account has no application password. Ask the administrator to reset it.", "error")
        else:
            try:
                valid = check_password_hash(p["password_hash"], password)
            except Exception:
                valid = False
            if valid:
                session.clear()
                session["user"] = {
                    "id": p.get("id"),
                    "email": p.get("email"),
                    "name": p.get("full_name") or p.get("name") or "",
                    "role": p.get("role") or "student",
                    "is_admin": bool(p.get("is_admin")),
                    "phone": p.get("phone"),
                }
                log_activity("login", "Successful login")
                nxt = request.args.get("next") or request.form.get("next")
                return redirect(nxt if nxt and nxt.startswith("/") else url_for("dashboard"))
            flash("Invalid email or password.", "error")

    body = f"""<div class="card"><h2>KOJA login</h2>
<form method="post">
<input name="email" type="email" placeholder="Email address" required>
<input name="password" type="password" placeholder="Password" required>
<button>Log in</button>
</form><p>No account? <a href="{url_for('register')}">Create one</a></p>
<p class="muted">This application uses the password hash stored in the existing <b>profiles</b> table.</p>
</div>"""
    return render_page("Login", body)

@app.route("/logout")
def logout():
    if current_user():
        log_activity("logout", "User logged out")
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

@app.route("/account")
@login_required
def account():
    p = find_profile_by_id(current_user()["id"]) or current_user()
    body = f"""<div class="card"><h2>My account</h2>
<p><b>Name:</b> {clean(p.get('full_name') or p.get('name'))}</p>
<p><b>Email:</b> {clean(p.get('email'))}</p>
<p><b>Phone:</b> {clean(p.get('phone') or 'Not supplied')}</p>
<p><b>Role:</b> {clean(p.get('role'))}</p>
<p><b>Institution:</b> {clean(p.get('institution') or 'Not supplied')}</p>
<p><b>Student number:</b> {clean(p.get('student_number') or 'Not supplied')}</p>
</div>"""
    return render_page("Account", body)

# ------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    uid = current_user()["id"]
    questions = sb_count_for_user("questions", uid)
    assignments = sb_count_for_user("assignments", uid)
    requests_n = sb_count_for_user("service_requests", uid)
    body = f"""<div class="hero"><h2>Welcome, {clean(current_user().get('name') or 'User')}</h2>
<p>Your KOJA account is active.</p></div>
<div class="grid">
<div class="card"><div class="stat">{questions}</div><small>Questions</small></div>
<div class="card"><div class="stat">{assignments}</div><small>Assignments</small></div>
<div class="card"><div class="stat">{requests_n}</div><small>Service requests</small></div>
</div>
<div class="grid">
{card_link("Ask a question","Submit an academic question.","question_new")}
{card_link("Assignment","Create an assignment request.","assignment_new")}
{card_link("CV","Build and download a CV.","cv_new")}
{card_link("Farmer","Register or request farmer assistance.","farmer_new")}
{card_link("Doctor","Request an appointment.","doctor_book")}
{card_link("Delivery","Create a delivery request.","delivery_new")}
{card_link("My account","View your profile.","account")}
</div>"""
    return render_page("Dashboard", body)

def sb_count_for_user(table, uid):
    candidates = ["user_id", "student_id", "client_id", "profile_id", "created_by"]
    for col in candidates:
        rows = sb_select(table, {
            "select": "id",
            col: f"eq.{uid}",
            "limit": "1000"
        })
        if rows:
            return len(rows)
    return 0

# ------------------------------------------------------------
# Generic request creator
# ------------------------------------------------------------

def create_request_record(table, values, success_message):
    row = dict(values)
    row.setdefault("user_id", current_user()["id"])
    row.setdefault("created_at", now_iso())
    ok, created = sb_insert(table, row)
    if ok:
        flash(success_message, "success")
        log_activity("create", f"{table} request created")
        return created
    flash("The request could not be saved. Check the Render logs.", "error")
    return None

# ------------------------------------------------------------
# Questions and answers
# ------------------------------------------------------------

@app.route("/questions")
@login_required
def questions():
    rows = sb_select("questions", {
        "select": "*",
        "order": "created_at.desc",
        "limit": "50"
    })
    html = "<div class='actions'><a class='btn' href='/questions/new'>Ask question</a></div>"
    if not rows:
        html += "<div class='card'><p>No questions have been posted yet.</p></div>"
    for q in rows:
        html += f"""<div class="card"><h3>{clean(q.get('title') or q.get('question') or 'Question')}</h3>
<p>{clean(q.get('question') or q.get('description') or '')}</p>
<span class="badge">{clean(q.get('status') or 'pending')}</span>
</div>"""
    return render_page("Questions", html)

@app.route("/questions/new", methods=["GET", "POST"])
@login_required
def question_new():
    if request.method == "POST":
        title = clean(request.form.get("title"), 250)
        question = clean(request.form.get("question"), 8000)
        subject = clean(request.form.get("subject"), 250)
        ok, row = sb_insert("questions", {
            "user_id": current_user()["id"],
            "student_id": current_user()["id"],
            "title": title,
            "question": question,
            "description": question,
            "subject": subject,
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })
        if ok:
            flash("Question submitted.", "success")
            log_activity("question_created", title)
            return redirect(url_for("questions"))
        flash("Could not save the question.", "error")
    body = """<div class="card"><h2>Ask an academic question</h2>
<form method="post">
<input name="title" placeholder="Question title" required>
<input name="subject" placeholder="Subject">
<textarea name="question" placeholder="Write your question clearly..." required></textarea>
<button>Submit question</button>
</form></div>"""
    return render_page("Ask Question", body)

# ------------------------------------------------------------
# Assignments
# ------------------------------------------------------------

@app.route("/assignments")
@login_required
def assignments():
    rows = sb_select("assignments", {
        "select": "*",
        "order": "created_at.desc",
        "limit": "50"
    })
    html = "<div class='actions'><a class='btn' href='/assignments/new'>New assignment</a></div>"
    for a in rows:
        html += f"""<div class="card"><h3>{clean(a.get('title') or a.get('name') or 'Assignment')}</h3>
<p>{clean(a.get('description') or a.get('question') or '')}</p>
<span class="badge">{clean(a.get('status') or 'pending')}</span></div>"""
    if not rows:
        html += "<div class='card'>No assignments found.</div>"
    return render_page("Assignments", html)

@app.route("/assignments/new", methods=["GET", "POST"])
@login_required
def assignment_new():
    if request.method == "POST":
        title = clean(request.form.get("title"), 250)
        subject = clean(request.form.get("subject"), 200)
        description = clean(request.form.get("description"), 8000)
        due = clean(request.form.get("due_date"), 100)

        ok, row = sb_insert("assignments", {
            "user_id": current_user()["id"],
            "student_id": current_user()["id"],
            "title": title,
            "name": title,
            "subject": subject,
            "description": description,
            "question": description,
            "due_date": due or None,
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })
        if ok:
            aid = (row or {}).get("id")
            f = request.files.get("file")
            if f and f.filename and allowed_file(f.filename) and aid:
                upload_to_storage(f, f"assignments/{aid}")
                # File metadata is stored if the existing table accepts it.
            flash("Assignment submitted.", "success")
            log_activity("assignment_created", title)
            return redirect(url_for("assignments"))
        flash("Could not save assignment.", "error")
    body = """<div class="card"><h2>Submit assignment</h2>
<form method="post" enctype="multipart/form-data">
<input name="title" placeholder="Assignment title" required>
<input name="subject" placeholder="Subject">
<textarea name="description" placeholder="Assignment question/instructions" required></textarea>
<input name="due_date" placeholder="Due date (optional)">
<input type="file" name="file" accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png">
<button>Submit assignment</button>
</form></div>"""
    return render_page("New Assignment", body)

@app.route("/assignment-answers/new", methods=["GET", "POST"])
@login_required
def assignment_answer_new():
    if request.method == "POST":
        assignment_id = clean(request.form.get("assignment_id"), 100)
        answer = clean(request.form.get("answer"), 12000)
        ok, _ = sb_insert("assignment_answers", {
            "assignment_id": assignment_id,
            "user_id": current_user()["id"],
            "student_id": current_user()["id"],
            "answer": answer,
            "status": "submitted",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })
        flash("Assignment answer submitted." if ok else "Could not submit answer.",
              "success" if ok else "error")
        if ok:
            log_activity("assignment_answer", f"Assignment {assignment_id}")
            return redirect(url_for("assignments"))
    body = """<div class="card"><h2>Submit assignment answer</h2>
<form method="post">
<input name="assignment_id" placeholder="Assignment ID" required>
<textarea name="answer" placeholder="Your answer" required></textarea>
<button>Submit answer</button>
</form></div>"""
    return render_page("Assignment Answer", body)

# ------------------------------------------------------------
# File storage
# ------------------------------------------------------------

def upload_to_storage(file_obj, folder):
    if not file_obj or not file_obj.filename:
        return None
    filename = secure_filename(file_obj.filename)
    if not allowed_file(filename):
        return None
    ext = filename.rsplit(".", 1)[1].lower()
    object_path = f"{folder.strip('/')}/{uuid.uuid4().hex}.{ext}"
    data = file_obj.read()
    mime = file_obj.mimetype or "application/octet-stream"
    headers = dict(SB_STORAGE_HEADERS)
    headers["Content-Type"] = mime
    try:
        r = requests.post(storage_url(object_path), headers=headers, data=data, timeout=60)
        if r.status_code >= 400:
            log.error("Storage upload failed: %s", json_error(r))
            return None
        return {
            "path": object_path,
            "url": public_storage_url(object_path),
            "file_name": filename,
            "file_size": len(data),
            "mime_type": mime,
        }
    except Exception:
        log.exception("Storage upload exception")
        return None

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Choose a file.", "error")
        else:
            result = upload_to_storage(f, f"users/{current_user()['id']}")
            if result:
                flash(f"File uploaded: {result['file_name']}", "success")
                log_activity("file_upload", result["file_name"])
            else:
                flash("Upload failed. Confirm the Supabase Storage bucket exists and is named correctly.", "error")
    body = """<div class="card"><h2>Upload file</h2>
<p class="muted">Maximum size configured by MAX_UPLOAD_MB. Allowed: PDF, Word, Excel, CSV, text and common images.</p>
<form method="post" enctype="multipart/form-data"><input type="file" name="file" required><button>Upload</button></form></div>"""
    return render_page("Upload", body)

# ------------------------------------------------------------
# CV builder
# ------------------------------------------------------------

def make_cv_pdf(data):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=45, leftMargin=45, topMargin=45, bottomMargin=45)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(data["full_name"], styles["Title"]),
        Paragraph(f"{data['email']} | {data['phone']}", styles["Normal"]),
        Spacer(1, 14),
        Paragraph("PROFESSIONAL SUMMARY", styles["Heading2"]),
        Paragraph(data["summary"], styles["BodyText"]),
        Spacer(1, 10),
        Paragraph("EDUCATION", styles["Heading2"]),
        Paragraph(data["education"].replace("\n", "<br/>"), styles["BodyText"]),
        Spacer(1, 10),
        Paragraph("EXPERIENCE", styles["Heading2"]),
        Paragraph(data["experience"].replace("\n", "<br/>"), styles["BodyText"]),
        Spacer(1, 10),
        Paragraph("SKILLS", styles["Heading2"]),
        Paragraph(data["skills"].replace("\n", "<br/>"), styles["BodyText"]),
        Spacer(1, 10),
        Paragraph("REFERENCES", styles["Heading2"]),
        Paragraph(data["references"].replace("\n", "<br/>"), styles["BodyText"]),
    ]
    doc.build(story)
    buf.seek(0)
    return buf

@app.route("/cv", methods=["GET", "POST"])
@login_required
def cv_new():
    if request.method == "POST":
        data = {
            "full_name": clean(request.form.get("full_name"), 250),
            "email": clean(request.form.get("email"), 320),
            "phone": clean(request.form.get("phone"), 100),
            "summary": clean(request.form.get("summary"), 4000),
            "education": clean(request.form.get("education"), 6000),
            "experience": clean(request.form.get("experience"), 6000),
            "skills": clean(request.form.get("skills"), 4000),
            "references": clean(request.form.get("references"), 4000),
        }
        ok, row = sb_insert("cv_requests", {
            "user_id": current_user()["id"],
            "full_name": data["full_name"],
            "email": data["email"],
            "phone": data["phone"],
            "summary": data["summary"],
            "education": data["education"],
            "experience": data["experience"],
            "skills": data["skills"],
            "references": data["references"],
            "status": "completed",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })
        if ok:
            pdf = make_cv_pdf(data)
            log_activity("cv_created", "CV PDF generated")
            return send_file(pdf, as_attachment=True,
                             download_name=f"{secure_filename(data['full_name']) or 'KOJA'}_CV.pdf",
                             mimetype="application/pdf")
        flash("CV request could not be saved. Try again.", "error")
    body = """<div class="card"><h2>KOJA CV Builder</h2>
<form method="post">
<input name="full_name" placeholder="Full name" required>
<input name="email" type="email" placeholder="Email" required>
<input name="phone" placeholder="Phone">
<textarea name="summary" placeholder="Professional summary"></textarea>
<textarea name="education" placeholder="Education"></textarea>
<textarea name="experience" placeholder="Work experience"></textarea>
<textarea name="skills" placeholder="Skills"></textarea>
<textarea name="references" placeholder="References"></textarea>
<button>Generate CV PDF</button>
</form></div>"""
    return render_page("CV Builder", body)

# ------------------------------------------------------------
# Farmer / TPIN
# ------------------------------------------------------------

@app.route("/farmer", methods=["GET", "POST"])
@login_required
def farmer_new():
    if request.method == "POST":
        values = {
            "user_id": current_user()["id"],
            "full_name": clean(request.form.get("full_name"), 250),
            "phone": clean(request.form.get("phone"), 100),
            "nrc": clean(request.form.get("nrc"), 100),
            "province": clean(request.form.get("province"), 100),
            "district": clean(request.form.get("district"), 100),
            "farm_name": clean(request.form.get("farm_name"), 250),
            "crop_or_livestock": clean(request.form.get("crop_or_livestock"), 500),
            "farm_size": clean(request.form.get("farm_size"), 100),
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        row = create_request_record("farmer_registrations", values, "Farmer registration submitted.")
        if row:
            return redirect(url_for("dashboard"))
    body = """<div class="card"><h2>Farmer registration</h2>
<form method="post">
<input name="full_name" placeholder="Full name" required>
<input name="phone" placeholder="Phone" required>
<input name="nrc" placeholder="NRC number">
<input name="province" placeholder="Province">
<input name="district" placeholder="District">
<input name="farm_name" placeholder="Farm name">
<input name="crop_or_livestock" placeholder="Crop or livestock">
<input name="farm_size" placeholder="Farm size">
<button>Submit registration</button>
</form></div>"""
    return render_page("Farmer Registration", body)

@app.route("/tpin", methods=["GET", "POST"])
@login_required
def tpin_new():
    if request.method == "POST":
        values = {
            "user_id": current_user()["id"],
            "full_name": clean(request.form.get("full_name"), 250),
            "phone": clean(request.form.get("phone"), 100),
            "nrc": clean(request.form.get("nrc"), 100),
            "email": clean(request.form.get("email"), 320),
            "request_type": clean(request.form.get("request_type"), 250),
            "description": clean(request.form.get("description"), 5000),
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        row = create_request_record("tpin_requests", values, "TPIN assistance request submitted.")
        if row:
            return redirect(url_for("dashboard"))
    body = """<div class="card"><h2>TPIN assistance</h2>
<form method="post">
<input name="full_name" placeholder="Full name" required>
<input name="phone" placeholder="Phone">
<input name="email" type="email" placeholder="Email">
<input name="nrc" placeholder="NRC">
<select name="request_type"><option>New TPIN</option><option>TPIN support</option><option>Update details</option><option>Other</option></select>
<textarea name="description" placeholder="Describe the assistance you need"></textarea>
<button>Submit request</button>
</form></div>"""
    return render_page("TPIN Assistance", body)

# ------------------------------------------------------------
# Doctors / lawyers / teachers
# ------------------------------------------------------------

@app.route("/doctors")
@login_required
def doctors():
    rows = sb_select("doctor_profiles", {
        "select": "*", "limit": "100"
    })
    html = "<div class='card'><h2>Doctors</h2>"
    if not rows:
        html += "<p>No doctor profiles are currently listed.</p>"
    for d in rows:
        html += f"""<div class="card"><h3>{clean(d.get('full_name') or d.get('name') or 'Doctor')}</h3>
<p>{clean(d.get('specialization') or d.get('specialty') or '')}</p>
<p>{clean(d.get('location') or '')}</p></div>"""
    html += "</div>"
    return render_page("Doctors", html)

@app.route("/doctor-booking", methods=["GET", "POST"])
@login_required
def doctor_book():
    if request.method == "POST":
        values = {
            "user_id": current_user()["id"],
            "patient_id": current_user()["id"],
            "doctor_id": clean(request.form.get("doctor_id"), 100) or None,
            "doctor_name": clean(request.form.get("doctor_name"), 250),
            "patient_name": clean(request.form.get("patient_name"), 250),
            "phone": clean(request.form.get("phone"), 100),
            "appointment_date": clean(request.form.get("appointment_date"), 100),
            "appointment_time": clean(request.form.get("appointment_time"), 50),
            "reason": clean(request.form.get("reason"), 4000),
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        row = create_request_record("appointments", values, "Doctor booking request submitted.")
        if row:
            return redirect(url_for("dashboard"))
    body = """<div class="card"><h2>Doctor booking</h2>
<form method="post">
<input name="doctor_id" placeholder="Doctor ID (optional)">
<input name="doctor_name" placeholder="Doctor name (optional)">
<input name="patient_name" placeholder="Patient name" required>
<input name="phone" placeholder="Phone">
<input name="appointment_date" type="date" required>
<input name="appointment_time" type="time" required>
<textarea name="reason" placeholder="Reason for appointment"></textarea>
<button>Request appointment</button>
</form></div>"""
    return render_page("Doctor Booking", body)

@app.route("/lawyer", methods=["GET", "POST"])
@login_required
def lawyer_request():
    if request.method == "POST":
        row = create_request_record("service_requests", {
            "user_id": current_user()["id"],
            "service_type": "lawyer",
            "title": clean(request.form.get("title"), 250),
            "description": clean(request.form.get("description"), 7000),
            "phone": clean(request.form.get("phone"), 100),
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }, "Lawyer request submitted.")
        if row:
            return redirect(url_for("dashboard"))
    body = """<div class="card"><h2>Lawyer service request</h2>
<form method="post">
<input name="title" placeholder="Matter / service required" required>
<input name="phone" placeholder="Phone">
<textarea name="description" placeholder="Describe your legal-service request" required></textarea>
<button>Submit request</button>
</form></div>"""
    return render_page("Lawyer", body)

@app.route("/teacher", methods=["GET", "POST"])
@login_required
def teacher_request():
    if request.method == "POST":
        row = create_request_record("service_requests", {
            "user_id": current_user()["id"],
            "service_type": "teacher",
            "title": clean(request.form.get("title"), 250),
            "subject": clean(request.form.get("subject"), 250),
            "class_level": clean(request.form.get("class_level"), 100),
            "description": clean(request.form.get("description"), 6000),
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }, "Teacher/tutor request submitted.")
        if row:
            return redirect(url_for("dashboard"))
    body = """<div class="card"><h2>Teacher / tutor request</h2>
<form method="post">
<input name="title" placeholder="What help do you need?" required>
<input name="subject" placeholder="Subject">
<input name="class_level" placeholder="Grade / class">
<textarea name="description" placeholder="Explain what you need"></textarea>
<button>Submit request</button>
</form></div>"""
    return render_page("Teacher Services", body)

# ------------------------------------------------------------
# Deliveries
# ------------------------------------------------------------

@app.route("/deliveries")
@login_required
def deliveries():
    rows = sb_select("deliveries", {
        "select": "*", "order": "created_at.desc", "limit": "100"
    })
    html = f"<div class='actions'><a class='btn' href='{url_for('delivery_new')}'>New delivery</a></div>"
    for d in rows:
        code = d.get("tracking_code") or d.get("delivery_code") or d.get("id") or ""
        html += f"""<div class="card"><h3>Tracking: {clean(code)}</h3>
<p><b>From:</b> {clean(d.get('pickup_address') or d.get('pickup_location') or '')}</p>
<p><b>To:</b> {clean(d.get('delivery_address') or d.get('destination') or '')}</p>
<p><b>Status:</b> {clean(d.get('status') or 'pending')}</p></div>"""
    return render_page("Deliveries", html)

@app.route("/delivery/new", methods=["GET", "POST"])
@login_required
def delivery_new():
    if request.method == "POST":
        code = "KOJA-" + uuid.uuid4().hex[:10].upper()
        row = create_request_record("deliveries", {
            "user_id": current_user()["id"],
            "customer_id": current_user()["id"],
            "tracking_code": code,
            "delivery_code": code,
            "sender_name": clean(request.form.get("sender_name"), 250),
            "sender_phone": clean(request.form.get("sender_phone"), 100),
            "receiver_name": clean(request.form.get("receiver_name"), 250),
            "receiver_phone": clean(request.form.get("receiver_phone"), 100),
            "pickup_address": clean(request.form.get("pickup_address"), 1000),
            "pickup_location": clean(request.form.get("pickup_address"), 1000),
            "delivery_address": clean(request.form.get("delivery_address"), 1000),
            "destination": clean(request.form.get("delivery_address"), 1000),
            "description": clean(request.form.get("description"), 3000),
            "status": "requested",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }, f"Delivery request submitted. Tracking code: {code}")
        if row:
            return redirect(url_for("deliveries"))
    body = """<div class="card"><h2>Create delivery</h2>
<form method="post">
<input name="sender_name" placeholder="Sender name" required>
<input name="sender_phone" placeholder="Sender phone" required>
<input name="receiver_name" placeholder="Receiver name" required>
<input name="receiver_phone" placeholder="Receiver phone" required>
<input name="pickup_address" placeholder="Pickup address" required>
<input name="delivery_address" placeholder="Delivery address" required>
<textarea name="description" placeholder="Package description"></textarea>
<button>Create delivery</button>
</form></div>"""
    return render_page("New Delivery", body)

@app.route("/delivery/track", methods=["GET", "POST"])
def delivery_track():
    rows = []
    if request.method == "POST":
        code = clean(request.form.get("tracking_code"), 100)
        rows = sb_select("deliveries", {
            "select": "*",
            "or": f"(tracking_code.eq.{code},delivery_code.eq.{code})",
            "limit": "5"
        })
        if not rows:
            flash("Tracking code not found.", "error")
    html = """<div class="card"><h2>Track delivery</h2>
<form method="post"><input name="tracking_code" placeholder="KOJA-XXXXXXXXXX" required><button>Track</button></form></div>"""
    for d in rows:
        html += f"""<div class="card"><h3>{clean(d.get('tracking_code') or d.get('delivery_code'))}</h3>
<p>Status: <b>{clean(d.get('status') or 'unknown')}</b></p>
<p>{clean(d.get('pickup_address') or '')} → {clean(d.get('delivery_address') or d.get('destination') or '')}</p></div>"""
    return render_page("Track Delivery", html)

# ------------------------------------------------------------
# Services
# ------------------------------------------------------------

@app.route("/services")
def services():
    body = f"""<h2>KOJA Services</h2><div class="grid">
{card_link("Academic Questions","Questions and answers.","question_new")}
{card_link("Assignments","Assignment submission and answers.","assignment_new")}
{card_link("CV","Professional CV PDF.","cv_new")}
{card_link("Farmers","Farmer registration.","farmer_new")}
{card_link("TPIN","Tax/TIN assistance.","tpin_new")}
{card_link("Doctor","Appointment request.","doctor_book")}
{card_link("Lawyer","Legal-service request.","lawyer_request")}
{card_link("Teacher","Tutoring request.","teacher_request")}
{card_link("Delivery","Delivery and tracking.","delivery_new")}
</div>"""
    return render_page("Services", body)

# ------------------------------------------------------------
# Universities
# ------------------------------------------------------------

@app.route("/universities")
def universities():
    rows = sb_select("universities", {
        "select": "*",
        "order": "name.asc",
        "limit": "200"
    })
    html = "<div class='card'><h2>Universities</h2>"
    if not rows:
        html += "<p>No university records are currently stored.</p>"
    for u in rows:
        uid = u.get("id")
        name = u.get("name") or u.get("university_name") or "University"
        html += f"""<div class="card"><h3>{clean(name)}</h3>
<p>{clean(u.get('location') or u.get('province') or '')}</p>
<a class="btn" href="{url_for('university_detail', university_id=uid)}">Programmes & requirements</a>
</div>"""
    html += "</div>"
    return render_page("Universities", html)

@app.route("/universities/<university_id>")
def university_detail(university_id):
    u = sb_select("universities", {
        "select": "*", "id": f"eq.{university_id}", "limit": "1"
    })
    if not u:
        abort(404)
    uni = u[0]
    programmes = sb_select("university_programmes", {
        "select": "*",
        "university_id": f"eq.{university_id}",
        "limit": "200"
    })
    reqs = sb_select("university_application_requirements", {
        "select": "*",
        "university_id": f"eq.{university_id}",
        "limit": "200"
    })
    html = f"""<div class="card"><h2>{clean(uni.get('name') or uni.get('university_name'))}</h2>
<p>{clean(uni.get('description') or '')}</p></div><div class="card"><h2>Programmes</h2>"""
    if programmes:
        for p in programmes:
            html += f"<p><b>{clean(p.get('name') or p.get('programme_name') or p.get('title'))}</b> — {clean(p.get('description') or '')}</p>"
    else:
        html += "<p>No programme records found.</p>"
    html += "</div><div class='card'><h2>Application requirements</h2>"
    if reqs:
        for r in reqs:
            html += f"<p>{clean(r.get('requirement') or r.get('description') or r.get('name') or '')}</p>"
    else:
        html += "<p>No requirement records found.</p>"
    html += "</div>"
    return render_page("University", html)

@app.route("/university-application", methods=["GET", "POST"])
@login_required
def university_application():
    if request.method == "POST":
        row = create_request_record("university_applications", {
            "user_id": current_user()["id"],
            "university_id": clean(request.form.get("university_id"), 100) or None,
            "programme_id": clean(request.form.get("programme_id"), 100) or None,
            "full_name": clean(request.form.get("full_name"), 250),
            "email": clean(request.form.get("email"), 320),
            "phone": clean(request.form.get("phone"), 100),
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }, "University application request submitted.")
        if row:
            return redirect(url_for("dashboard"))
    body = """<div class="card"><h2>University application request</h2>
<form method="post">
<input name="university_id" placeholder="University ID">
<input name="programme_id" placeholder="Programme ID">
<input name="full_name" placeholder="Full name" required>
<input name="email" type="email" placeholder="Email" required>
<input name="phone" placeholder="Phone">
<button>Submit application request</button>
</form></div>"""
    return render_page("University Application", body)

# ------------------------------------------------------------
# Documents / resources
# ------------------------------------------------------------

@app.route("/documents")
def documents():
    rows = sb_select("documents", {
        "select": "*", "order": "created_at.desc", "limit": "100"
    })
    if not rows:
        rows = sb_select("document_library", {
            "select": "*", "order": "created_at.desc", "limit": "100"
        })
    html = "<div class='card'><h2>Academic resources</h2>"
    if not rows:
        html += "<p>No documents are currently available.</p>"
    for d in rows:
        title = d.get("title") or d.get("name") or d.get("file_name") or "Document"
        path = d.get("file_path") or d.get("file_url") or ""
        link = path if str(path).startswith("http") else ""
        html += f"""<div class="card"><h3>{clean(title)}</h3>
<p>{clean(d.get('description') or '')}</p>
<p><span class="badge">{clean(d.get('subject') or d.get('document_type') or 'resource')}</span></p>"""
        if link:
            html += f'<a class="btn" href="{clean(link,2000)}" target="_blank">Open</a>'
        elif d.get("id"):
            html += f'<a class="btn" href="{url_for("document_download", document_id=d["id"])}">Download</a>'
        html += "</div>"
    html += "</div>"
    return render_page("Resources", html)

@app.route("/documents/<document_id>/download")
@login_required
def document_download(document_id):
    rows = sb_select("documents", {
        "select": "*", "id": f"eq.{document_id}", "limit": "1"
    })
    table = "documents"
    if not rows:
        rows = sb_select("document_library", {
            "select": "*", "id": f"eq.{document_id}", "limit": "1"
        })
        table = "document_library"
    if not rows:
        abort(404)
    d = rows[0]
    path = d.get("file_path")
    url = d.get("file_url")
    if url:
        return redirect(url)
    if not path:
        abort(404)
    try:
        r = requests.get(storage_url(path), headers=SB_STORAGE_HEADERS, timeout=60)
        if r.status_code >= 400:
            abort(404)
        log_activity("document_download", str(d.get("title") or d.get("file_name") or document_id))
        return send_file(io.BytesIO(r.content), as_attachment=True,
                         download_name=secure_filename(d.get("file_name") or "document"),
                         mimetype=d.get("mime_type") or "application/octet-stream")
    except Exception:
        abort(404)

# ------------------------------------------------------------
# Payments — records are created, actual gateway can be added
# without changing the application architecture.
# ------------------------------------------------------------

@app.route("/payment", methods=["GET", "POST"])
@login_required
def payment():
    if request.method == "POST":
        amount = clean(request.form.get("amount"), 50)
        purpose = clean(request.form.get("purpose"), 250)
        ok, row = sb_insert("payments", {
            "user_id": current_user()["id"],
            "amount": amount,
            "currency": "ZMW",
            "purpose": purpose,
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })
        if ok:
            flash("Payment record created. An administrator can process/verify the payment.", "success")
            log_activity("payment_request", purpose)
            return redirect(url_for("dashboard"))
        flash("Payment request could not be saved.", "error")
    body = """<div class="card"><h2>Payment request</h2>
<p>This records a Zambian Kwacha payment request. A live gateway must be configured separately before accepting real money.</p>
<form method="post">
<input name="amount" type="number" min="0" step="0.01" placeholder="Amount ZMW" required>
<input name="purpose" placeholder="Purpose" required>
<button>Create payment request</button>
</form></div>"""
    return render_page("Payment", body)

# ------------------------------------------------------------
# Notifications
# ------------------------------------------------------------

@app.route("/notifications")
@login_required
def notifications():
    rows = sb_select("notifications", {
        "select": "*",
        "user_id": f"eq.{current_user()['id']}",
        "order": "created_at.desc",
        "limit": "100"
    })
    html = "<div class='card'><h2>Notifications</h2>"
    for n in rows:
        html += f"""<div class="card"><h3>{clean(n.get('title') or 'Notification')}</h3>
<p>{clean(n.get('message') or '')}</p><small>{clean(n.get('created_at') or '')}</small></div>"""
    if not rows:
        html += "<p>No notifications.</p>"
    html += "</div>"
    return render_page("Notifications", html)

# ------------------------------------------------------------
# Admin
# ------------------------------------------------------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    counts = {}
    for t in [
        "profiles", "questions", "assignments", "cv_requests",
        "farmer_registrations", "tpin_requests", "appointments",
        "service_requests", "deliveries", "payments",
        "university_applications", "documents"
    ]:
        counts[t] = sb_count(t)

    html = "<div class='hero'><h2>KOJA Administrator</h2><p>Manage the live application data.</p></div><div class='grid'>"
    for k, v in counts.items():
        html += f"<div class='card'><div class='stat'>{v}</div><small>{k}</small></div>"
    html += "</div><div class='grid'>"
    html += card_link("Users","View registered accounts.","admin_users")
    html += card_link("Questions","Review academic questions.","admin_questions")
    html += card_link("Assignments","Review assignments.","admin_assignments")
    html += card_link("Requests","Review service requests.","admin_requests")
    html += card_link("Deliveries","Review deliveries.","admin_deliveries")
    html += card_link("Payments","Review payment records.","admin_payments")
    html += "</div>"
    return render_page("Admin", html)

@app.route("/admin/users")
@admin_required
def admin_users():
    rows = sb_select("profiles", {
        "select": "*", "order": "created_at.desc", "limit": "300"
    })
    html = "<div class='card'><h2>Users</h2><table><tr><th>Name</th><th>Email</th><th>Role</th><th>Admin</th><th>Active</th></tr>"
    for p in rows:
        html += f"""<tr><td>{clean(p.get('full_name') or p.get('name'))}</td>
<td>{clean(p.get('email'))}</td><td>{clean(p.get('role'))}</td>
<td>{'Yes' if p.get('is_admin') else 'No'}</td>
<td>{'Yes' if p.get('is_active', True) else 'No'}</td></tr>"""
    html += "</table></div>"
    return render_page("Admin Users", html)

def admin_table_page(title, table, fields):
    rows = sb_select(table, {"select": "*", "order": "created_at.desc", "limit": "200"})
    html = f"<div class='card'><h2>{title}</h2>"
    if not rows:
        html += "<p>No records found.</p>"
    for row in rows:
        html += "<div class='card'>"
        for field in fields:
            if field in row and row.get(field) not in (None, ""):
                html += f"<p><b>{clean(field)}:</b> {clean(row.get(field),1500)}</p>"
        html += "</div>"
    html += "</div>"
    return render_page(title, html)

@app.route("/admin/questions")
@admin_required
def admin_questions():
    return admin_table_page("Academic Questions", "questions",
                            ["id","user_id","title","question","subject","status","created_at"])

@app.route("/admin/assignments")
@admin_required
def admin_assignments():
    return admin_table_page("Assignments", "assignments",
                            ["id","user_id","title","subject","description","status","created_at"])

@app.route("/admin/requests")
@admin_required
def admin_requests():
    return admin_table_page("Service Requests", "service_requests",
                            ["id","user_id","service_type","title","description","status","created_at"])

@app.route("/admin/deliveries")
@admin_required
def admin_deliveries():
    return admin_table_page("Deliveries", "deliveries",
                            ["id","user_id","tracking_code","delivery_code","sender_name","receiver_name","pickup_address","delivery_address","status","created_at"])

@app.route("/admin/payments")
@admin_required
def admin_payments():
    return admin_table_page("Payments", "payments",
                            ["id","user_id","amount","currency","purpose","status","created_at"])

@app.route("/admin/user/<user_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_user(user_id):
    p = find_profile_by_id(user_id)
    if not p:
        abort(404)
    new_value = not bool(p.get("is_active", True))
    ok, _ = sb_update("profiles", {"id": f"eq.{user_id}"}, {
        "is_active": new_value,
        "updated_at": now_iso()
    })
    flash("User status updated." if ok else "Could not update user.", "success" if ok else "error")
    return redirect(url_for("admin_users"))

@app.route("/admin/user/<user_id>/make-admin", methods=["POST"])
@admin_required
def admin_make_admin(user_id):
    ok, _ = sb_update("profiles", {"id": f"eq.{user_id}"}, {
        "is_admin": True, "role": "admin", "updated_at": now_iso()
    })
    flash("Administrator role granted." if ok else "Could not update user.",
          "success" if ok else "error")
    return redirect(url_for("admin_users"))

# ------------------------------------------------------------
# 404 / 413 / 500
# ------------------------------------------------------------

@app.errorhandler(404)
def not_found(_):
    return render_page("Not Found",
                       "<div class='card'><h2>Page not found</h2><p>The requested page does not exist.</p></div>"), 404

@app.errorhandler(403)
def forbidden(_):
    return render_page("Forbidden",
                       "<div class='card'><h2>Access denied</h2><p>You do not have administrator permission for this page.</p></div>"), 403

@app.errorhandler(413)
def too_large(_):
    return render_page("File too large",
                       f"<div class='card'><h2>File too large</h2><p>The maximum upload size is {MAX_UPLOAD_MB} MB.</p></div>"), 413

@app.errorhandler(500)
def server_error(err):
    log.exception("Unhandled Flask error: %s", err)
    return render_page("Server Error",
                       "<div class='card'><h2>KOJA AFRICA server error</h2><p>The error has been logged. Check Render logs for the exact traceback.</p></div>"), 500

# ------------------------------------------------------------
# Startup
# ------------------------------------------------------------

@app.before_request
def request_log():
    # Keep logs useful but avoid passwords/form contents.
    if request.path not in ("/health",):
        log.info("%s %s", request.method, request.path)

try:
    admin_bootstrap()
except Exception:
    log.exception("Admin bootstrap failed")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
