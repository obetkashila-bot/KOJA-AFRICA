import os
import io
import json
import uuid
import time
import secrets
import logging
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    flash,
    send_file,
    jsonify,
    abort,
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# Single-file Flask + Supabase REST + Supabase Storage
#
# IMPORTANT:
# - No psycopg / psycopg2
# - No reportlab dependency
# - No database connection at application startup
# - Existing Supabase schema is detected dynamically
# - Browser GPS tracking supported
# ============================================================

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja-africa")


# ============================================================
# CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
)

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Some older deployments may have used this name.
if not SUPABASE_SERVICE_KEY:
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_KEY", "")

STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "koja-files")

APP_NAME = "KOJA AFRICA"
APP_TAGLINE = "Knowledge • Questions • Answers"

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "jpg",
    "jpeg",
    "png",
    "webp",
}

MAX_UPLOAD_MB = 15


# ============================================================
# BASIC HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def supabase_configured():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def sb_headers(extra=None):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    if extra:
        headers.update(extra)

    return headers


def sb_rest_url(table):
    return f"{SUPABASE_URL}/rest/v1/{quote(table, safe='')}"


def sb_storage_url(path):
    return (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{quote(STORAGE_BUCKET, safe='')}/"
        f"{quote(path, safe='/')}"
    )


def json_or_empty(response):
    try:
        return response.json()
    except Exception:
        return {}


def db_select(
    table,
    filters=None,
    select="*",
    order=None,
    limit=None,
):
    """
    Safe Supabase REST SELECT.
    Returns [] on failure instead of crashing the entire application.
    """
    if not supabase_configured():
        logger.error("Supabase is not configured.")
        return []

    params = {
        "select": select
    }

    if filters:
        for key, value in filters.items():
            if value is None:
                params[key] = "is.null"
            else:
                params[key] = f"eq.{value}"

    if order:
        params["order"] = order

    if limit:
        params["limit"] = str(limit)

    try:
        r = requests.get(
            sb_rest_url(table),
            headers=sb_headers(),
            params=params,
            timeout=20,
        )

        if not r.ok:
            logger.error(
                "SELECT %s failed: %s %s",
                table,
                r.status_code,
                r.text[:1000],
            )
            return []

        data = json_or_empty(r)
        return data if isinstance(data, list) else []

    except Exception as exc:
        logger.exception("Database SELECT error: %s", exc)
        return []


def db_insert(table, payload, returning="representation"):
    if not supabase_configured():
        return None, "Supabase is not configured."

    headers = sb_headers({
        "Prefer": returning
    })

    try:
        r = requests.post(
            sb_rest_url(table),
            headers=headers,
            json=payload,
            timeout=20,
        )

        if not r.ok:
            logger.error(
                "INSERT %s failed: %s %s",
                table,
                r.status_code,
                r.text[:1500],
            )
            return None, r.text

        data = json_or_empty(r)

        if isinstance(data, list):
            return (data[0] if data else None), None

        return data, None

    except Exception as exc:
        logger.exception("Database INSERT error: %s", exc)
        return None, str(exc)


def db_update(table, filters, payload):
    if not supabase_configured():
        return None, "Supabase is not configured."

    params = {}

    for key, value in filters.items():
        params[key] = f"eq.{value}"

    try:
        r = requests.patch(
            sb_rest_url(table),
            headers=sb_headers({"Prefer": "return=representation"}),
            params=params,
            json=payload,
            timeout=20,
        )

        if not r.ok:
            logger.error(
                "UPDATE %s failed: %s %s",
                table,
                r.status_code,
                r.text[:1500],
            )
            return None, r.text

        data = json_or_empty(r)
        return data, None

    except Exception as exc:
        logger.exception("Database UPDATE error: %s", exc)
        return None, str(exc)


def db_delete(table, filters):
    if not supabase_configured():
        return False, "Supabase is not configured."

    params = {}

    for key, value in filters.items():
        params[key] = f"eq.{value}"

    try:
        r = requests.delete(
            sb_rest_url(table),
            headers=sb_headers(),
            params=params,
            timeout=20,
        )

        if not r.ok:
            return False, r.text

        return True, None

    except Exception as exc:
        logger.exception("Database DELETE error: %s", exc)
        return False, str(exc)


def table_exists(table):
    """
    REST existence test.
    """
    if not supabase_configured():
        return False

    try:
        r = requests.get(
            sb_rest_url(table),
            headers=sb_headers(),
            params={"select": "*", "limit": "1"},
            timeout=10,
        )

        return r.status_code < 400

    except Exception:
        return False


def first_row(table, filters):
    rows = db_select(table, filters=filters, limit=1)
    return rows[0] if rows else None


# ============================================================
# STORAGE
# ============================================================

def upload_storage(file_storage, folder="uploads"):
    """
    Uploads a file to Supabase Storage.
    Returns public URL/path information.
    """
    if not file_storage or not file_storage.filename:
        return None, "No file supplied."

    if not supabase_configured():
        return None, "Supabase is not configured."

    filename = secure_filename(file_storage.filename)

    if not filename:
        return None, "Invalid filename."

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ALLOWED_EXTENSIONS:
        return None, f"File type .{ext} is not allowed."

    data = file_storage.read()

    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        return None, f"Maximum file size is {MAX_UPLOAD_MB} MB."

    unique_name = f"{uuid.uuid4().hex}_{filename}"
    path = f"{folder.strip('/')}/{unique_name}"

    mime = file_storage.mimetype or "application/octet-stream"

    headers = sb_headers({
        "Content-Type": mime,
        "x-upsert": "true",
    })

    try:
        r = requests.post(
            sb_storage_url(path),
            headers=headers,
            data=data,
            timeout=60,
        )

        if not r.ok:
            logger.error(
                "Storage upload failed: %s %s",
                r.status_code,
                r.text[:1500],
            )
            return None, r.text

        public_url = (
            f"{SUPABASE_URL}/storage/v1/object/public/"
            f"{quote(STORAGE_BUCKET, safe='')}/"
            f"{quote(path, safe='/')}"
        )

        return {
            "path": path,
            "url": public_url,
            "file_name": filename,
            "file_size": len(data),
            "mime_type": mime,
        }, None

    except Exception as exc:
        logger.exception("Storage error: %s", exc)
        return None, str(exc)


def delete_storage(path):
    if not path or not supabase_configured():
        return False

    try:
        r = requests.delete(
            sb_storage_url(path),
            headers=sb_headers(),
            timeout=20,
        )
        return r.ok
    except Exception:
        return False


# ============================================================
# AUTHENTICATION
# ============================================================

def current_user():
    return session.get("user")


def login_user(user):
    session.clear()

    session["user"] = {
        "id": str(user.get("id")),
        "name": (
            user.get("full_name")
            or user.get("name")
            or user.get("email")
            or "KOJA User"
        ),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "role": user.get("role") or "student",
        "is_admin": bool(user.get("is_admin", False)),
        "institution": user.get("institution"),
        "student_number": user.get("student_number"),
    }

    session.permanent = True


def find_user_by_email(email):
    email = (email or "").strip().lower()

    if not email:
        return None

    # Confirmed modern/merged KOJA profile table.
    rows = db_select(
        "profiles",
        filters={"email": email},
        limit=1,
    )

    if rows:
        return rows[0]

    # Compatibility with older KOJA table.
    rows = db_select(
        "koja_users",
        filters={"email": email},
        limit=1,
    )

    if rows:
        return rows[0]

    return None


def password_matches(user, password):
    stored = user.get("password_hash")

    if not stored or not password:
        return False

    try:
        return check_password_hash(stored, password)
    except Exception:
        return False


def find_user_by_id(user_id):
    if not user_id:
        return None

    rows = db_select(
        "profiles",
        filters={"id": user_id},
        limit=1,
    )

    if rows:
        return rows[0]

    rows = db_select(
        "koja_users",
        filters={"id": user_id},
        limit=1,
    )

    return rows[0] if rows else None


# ============================================================
# DECORATORS
# ============================================================

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
        user = current_user()

        if not user:
            flash("Administrator login required.", "warning")
            return redirect(url_for("login"))

        if not user.get("is_admin"):
            flash("Administrator access required.", "danger")
            return redirect(url_for("dashboard"))

        return fn(*args, **kwargs)

    return wrapper


# ============================================================
# ACTIVITY LOGGING
# ============================================================

def log_activity(action, description="", user_id=None):
    """
    Uses activity_logs when available.
    Failure is deliberately non-fatal.
    """
    uid = user_id

    if not uid and current_user():
        uid = current_user().get("id")

    payload = {
        "action": action,
        "description": description,
    }

    if uid:
        payload["user_id"] = uid

    try:
        db_insert("activity_logs", payload)
    except Exception:
        pass


# ============================================================
# TEMPLATE
# ============================================================

BASE_HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1,
               maximum-scale=1">

<title>{{ title or "KOJA AFRICA" }}</title>

<link rel="stylesheet"
 href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">

<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family:
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
    background: #f5f7fb;
    color: #172033;
}

nav {
    background: #10233f;
    color: white;
    padding: 12px 15px;
    position: sticky;
    top: 0;
    z-index: 1000;
}

.nav-inner {
    max-width: 1200px;
    margin: auto;
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}

.brand {
    font-weight: 800;
    font-size: 19px;
    margin-right: auto;
}

nav a {
    color: white;
    text-decoration: none;
    padding: 8px 10px;
    border-radius: 7px;
}

nav a:hover {
    background: rgba(255,255,255,.12);
}

.container {
    width: min(1200px, calc(100% - 24px));
    margin: 20px auto 50px;
}

.card {
    background: white;
    border-radius: 13px;
    padding: 18px;
    margin-bottom: 16px;
    box-shadow: 0 3px 14px rgba(0,0,0,.06);
}

.hero {
    background: linear-gradient(135deg,#10233f,#176b87);
    color: white;
    padding: 28px 20px;
    border-radius: 15px;
    margin-bottom: 18px;
}

h1,h2,h3 {
    margin-top: 0;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(230px,1fr));
    gap: 15px;
}

input,
select,
textarea,
button {
    width: 100%;
    padding: 11px 12px;
    margin-top: 6px;
    margin-bottom: 12px;
    border-radius: 8px;
    border: 1px solid #ccd3df;
    font: inherit;
}

textarea {
    min-height: 120px;
}

button,
.btn {
    display: inline-block;
    background: #176b87;
    color: white;
    border: 0;
    text-decoration: none;
    cursor: pointer;
    padding: 10px 14px;
    border-radius: 8px;
}

.btn.secondary {
    background: #5f6b7a;
}

.btn.success {
    background: #177245;
}

.btn.danger {
    background: #a62d2d;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    border-bottom: 1px solid #e4e7ec;
    padding: 9px;
    text-align: left;
    vertical-align: top;
}

.alert {
    padding: 12px;
    border-radius: 8px;
    margin-bottom: 10px;
    background: #eaf2ff;
}

.stat {
    padding: 18px;
    background: white;
    border-radius: 12px;
    box-shadow: 0 2px 10px rgba(0,0,0,.05);
}

.big {
    font-size: 28px;
    font-weight: 800;
}

#map {
    height: 430px;
    border-radius: 12px;
    overflow: hidden;
}

.small {
    color: #667085;
    font-size: 13px;
}

.badge {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 20px;
    background: #e7eef5;
    font-size: 12px;
}

footer {
    text-align: center;
    color: #667085;
    padding: 30px;
}

@media(max-width:650px) {
    nav a {
        font-size: 13px;
    }

    table {
        display: block;
        overflow-x: auto;
    }

    #map {
        height: 350px;
    }
}
</style>
</head>

<body>

<nav>
<div class="nav-inner">
<div class="brand">KOJA AFRICA</div>

<a href="{{ url_for('home') }}">Home</a>

{% if user %}
<a href="{{ url_for('dashboard') }}">Dashboard</a>
<a href="{{ url_for('services') }}">Services</a>
<a href="{{ url_for('questions') }}">Questions</a>
<a href="{{ url_for('assignments') }}">Assignments</a>
<a href="{{ url_for('universities') }}">Universities</a>
<a href="{{ url_for('deliveries') }}">Deliveries</a>
<a href="{{ url_for('logout') }}">Logout</a>
{% else %}
<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Register</a>
{% endif %}

{% if user and user.is_admin %}
<a href="{{ url_for('admin') }}">Admin</a>
{% endif %}
</div>
</nav>

<div class="container">

{% with messages = get_flashed_messages(with_categories=true) %}
{% for category, message in messages %}
<div class="alert">{{ message }}</div>
{% endfor %}
{% endwith %}

{{ body|safe }}

</div>

<footer>
KOJA AFRICA — Knowledge • Questions • Answers<br>
Academic • Professional • Agricultural • Health • Transport Services
</footer>

<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>

</body>
</html>
"""


def render_page(title, body_template, **context):
    context["user"] = current_user()

    body = render_template_string(
        body_template,
        **context
    )

    return render_template_string(
        BASE_HTML,
        title=title,
        body=body,
        user=current_user(),
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    return render_page(
        "KOJA AFRICA",
        """
<div class="hero">
<h1>KOJA AFRICA</h1>
<p>Knowledge • Questions • Answers</p>
<p>
Academic services, university applications, CV creation,
farmer registration, professional bookings and delivery services.
</p>

{% if not user %}
<a class="btn" href="{{ url_for('register') }}">Create Account</a>
<a class="btn secondary" href="{{ url_for('login') }}">Login</a>
{% endif %}
</div>

<div class="grid">

<div class="card">
<h3>Academic</h3>
<p>Questions, assignments, learning resources and answered documents.</p>
<a class="btn" href="{{ url_for('questions') }}">Academic Questions</a>
</div>

<div class="card">
<h3>University Applications</h3>
<p>Choose a university, programme and academic year.</p>
<a class="btn" href="{{ url_for('universities') }}">Universities</a>
</div>

<div class="card">
<h3>CV</h3>
<p>Create and download a professional CV.</p>
<a class="btn" href="{{ url_for('cv') }}">Create CV</a>
</div>

<div class="card">
<h3>Farmer Registration</h3>
<p>Submit agricultural registration information.</p>
<a class="btn" href="{{ url_for('farmer') }}">Farmer Portal</a>
</div>

<div class="card">
<h3>Doctor Booking</h3>
<p>Find available doctors and request an appointment.</p>
<a class="btn" href="{{ url_for('doctors') }}">Find Doctors</a>
</div>

<div class="card">
<h3>Teacher Booking</h3>
<p>Find teachers/tutors by subject and grade.</p>
<a class="btn" href="{{ url_for('teachers') }}">Find Teachers</a>
</div>

<div class="card">
<h3>Deliveries</h3>
<p>Register a delivery and track its status.</p>
<a class="btn" href="{{ url_for('deliveries') }}">Delivery</a>
</div>

<div class="card">
<h3>Live GPS</h3>
<p>Drivers can share their phone location with customers.</p>
<a class="btn" href="{{ url_for('tracking') }}">Tracking</a>
</div>

</div>
""",
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "application": APP_NAME,
        "supabase_configured": supabase_configured(),
        "timestamp": utc_now(),
        "python": os.sys.version.split()[0],
    })


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not full_name or not email or not password:
            flash(
                "Full name, email and password are required.",
                "danger"
            )
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return redirect(url_for("register"))

        if find_user_by_email(email):
            flash("An account with this email already exists.", "warning")
            return redirect(url_for("login"))

        password_hash = generate_password_hash(password)

        payload = {
            "id": str(uuid.uuid4()),
            "name": full_name,
            "full_name": full_name,
            "email": email,
            "phone": phone or None,
            "password_hash": password_hash,
            "role": "student",
            "is_admin": False,
            "is_active": True,
        }

        # profiles is the confirmed current account table.
        row, error = db_insert("profiles", payload)

        if error:
            # Fallback for old table.
            old_payload = {
                "id": payload["id"],
                "full_name": full_name,
                "email": email,
                "phone": phone or None,
                "password_hash": password_hash,
            }

            row, error = db_insert("KOJA ZM", old_payload)

        if error:
            flash(
                "Registration failed. Check the Render logs for the "
                "Supabase database error.",
                "danger"
            )
            return redirect(url_for("register"))

        login_user(row or payload)
        log_activity(
            "registration",
            "New KOJA account registered."
        )

        flash("Account created successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_page(
        "Register",
        """
<div class="card">
<h2>Create KOJA Account</h2>

<form method="post">

<label>Full Name</label>
<input name="full_name" required>

<label>Email</label>
<input name="email" type="email" required>

<label>Phone</label>
<input name="phone">

<label>Password</label>
<input name="password" type="password" required minlength="6">

<button type="submit">Create Account</button>

</form>
</div>
"""
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = find_user_by_email(email)

        if not user:
            flash(
                "Invalid login credentials.",
                "danger"
            )
            return redirect(url_for("login"))

        if user.get("is_active") is False:
            flash("This account is inactive.", "danger")
            return redirect(url_for("login"))

        if not password_matches(user, password):
            flash(
                "Invalid login credentials.",
                "danger"
            )
            return redirect(url_for("login"))

        login_user(user)

        log_activity(
            "login",
            "User logged into KOJA."
        )

        next_url = request.args.get("next")

        if next_url and next_url.startswith("/"):
            return redirect(next_url)

        return redirect(url_for("dashboard"))

    return render_page(
        "Login",
        """
<div class="card" style="max-width:500px;margin:auto">

<h2>KOJA Login</h2>

<p class="small">
Use the email and password you used during KOJA registration.
</p>

<form method="post">

<label>Email</label>
<input name="email" type="email" autocomplete="email" required>

<label>Password</label>
<input name="password"
       type="password"
       autocomplete="current-password"
       required>

<button type="submit">Login</button>

</form>

<p>
No account?
<a href="{{ url_for('register') }}">Create one</a>
</p>

</div>
"""
    )


@app.route("/logout")
def logout():
    if current_user():
        log_activity("logout", "User logged out.")

    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()

    questions_count = len(
        db_select(
            "questions",
            filters={"user_id": user["id"]},
            limit=1000,
        )
    )

    deliveries_count = len(
        db_select(
            "deliveries",
            filters={"customer_id": user["id"]},
            limit=1000,
        )
    )

    appointments_count = len(
        db_select(
            "appointments",
            filters={"client_id": user["id"]},
            limit=1000,
        )
    )

    return render_page(
        "Dashboard",
        """
<div class="hero">
<h2>Welcome, {{ user.name }}</h2>
<p>{{ user.email }}</p>
</div>

<div class="grid">

<div class="stat">
<div class="big">{{ questions_count }}</div>
Academic Questions
</div>

<div class="stat">
<div class="big">{{ deliveries_count }}</div>
Deliveries
</div>

<div class="stat">
<div class="big">{{ appointments_count }}</div>
Appointments
</div>

<div class="stat">
<div class="big">
{% if user.is_admin %}ADMIN{% else %}USER{% endif %}
</div>
Account
</div>

</div>

<div class="card">
<h3>KOJA Services</h3>

<div class="grid">

<a class="btn" href="{{ url_for('cv') }}">Create CV</a>
<a class="btn" href="{{ url_for('universities') }}">University Application</a>
<a class="btn" href="{{ url_for('farmer') }}">Farmer Registration</a>
<a class="btn" href="{{ url_for('doctors') }}">Doctor Booking</a>
<a class="btn" href="{{ url_for('teachers') }}">Teacher Booking</a>
<a class="btn" href="{{ url_for('deliveries') }}">Delivery</a>
<a class="btn" href="{{ url_for('tracking') }}">GPS Tracking</a>

</div>
</div>
""",
        questions_count=questions_count,
        deliveries_count=deliveries_count,
        appointments_count=appointments_count,
    )


# ============================================================
# SERVICES
# ============================================================

@app.route("/services")
@login_required
def services():
    return render_page(
        "KOJA Services",
        """
<div class="hero">
<h2>KOJA Services</h2>
<p>Choose a service.</p>
</div>

<div class="grid">

<div class="card">
<h3>Academic Questions</h3>
<a class="btn" href="{{ url_for('questions') }}">Open</a>
</div>

<div class="card">
<h3>Assignments</h3>
<a class="btn" href="{{ url_for('assignments') }}">Open</a>
</div>

<div class="card">
<h3>CV</h3>
<a class="btn" href="{{ url_for('cv') }}">Open</a>
</div>

<div class="card">
<h3>University Applications</h3>
<a class="btn" href="{{ url_for('universities') }}">Open</a>
</div>

<div class="card">
<h3>Farmer Registration</h3>
<a class="btn" href="{{ url_for('farmer') }}">Open</a>
</div>

<div class="card">
<h3>Doctors</h3>
<a class="btn" href="{{ url_for('doctors') }}">Open</a>
</div>

<div class="card">
<h3>Teachers</h3>
<a class="btn" href="{{ url_for('teachers') }}">Open</a>
</div>

<div class="card">
<h3>Deliveries</h3>
<a class="btn" href="{{ url_for('deliveries') }}">Open</a>
</div>

</div>
"""
    )


# ============================================================
# QUESTIONS
# ============================================================

@app.route("/questions", methods=["GET", "POST"])
@login_required
def questions():
    user = current_user()

    if request.method == "POST":
        question_text = request.form.get("question", "").strip()
        subject = request.form.get("subject", "").strip()

        if not question_text:
            flash("Enter your question.", "danger")
            return redirect(url_for("questions"))

        payload = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "question": question_text,
            "subject": subject or None,
            "created_at": utc_now(),
        }

        row, error = db_insert("questions", payload)

        if error:
            # Try older schema without optional columns.
            payload = {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "question": question_text,
            }

            row, error = db_insert("questions", payload)

        if error:
            flash(
                "Question could not be submitted. "
                "The existing questions table may use different columns.",
                "danger"
            )
        else:
            log_activity(
                "question_created",
                "Student submitted an academic question."
            )
            flash("Question submitted.", "success")

        return redirect(url_for("questions"))

    rows = db_select(
        "questions",
        filters={"user_id": user["id"]},
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Questions",
        """
<div class="card">
<h2>Ask an Academic Question</h2>

<form method="post">

<label>Subject</label>
<input name="subject"
       placeholder="Mathematics, Biology, Chemistry...">

<label>Question</label>
<textarea name="question" required></textarea>

<button type="submit">Submit Question</button>

</form>
</div>

<div class="card">
<h2>My Questions</h2>

{% if rows %}
{% for q in rows %}
<div class="card">
<strong>{{ q.get("subject") or "Academic" }}</strong>
<p>{{ q.get("question") or q.get("question_text") }}</p>

{% if q.get("answer") %}
<hr>
<strong>Answer</strong>
<p>{{ q.get("answer") }}</p>
{% endif %}

<span class="badge">
{{ q.get("status") or "Submitted" }}
</span>

</div>
{% endfor %}
{% else %}
<p>No questions submitted yet.</p>
{% endif %}

</div>
""",
        rows=rows,
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments", methods=["GET", "POST"])
@login_required
def assignments():
    user = current_user()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        file = request.files.get("file")

        uploaded = None

        if file and file.filename:
            uploaded, error = upload_storage(
                file,
                folder="assignments"
            )

            if error:
                flash(f"Upload failed: {error}", "danger")
                return redirect(url_for("assignments"))

        payload = {
            "id": str(uuid.uuid4()),
            "student_id": user["id"],
            "user_id": user["id"],
            "title": title,
            "description": description,
            "created_at": utc_now(),
        }

        if uploaded:
            payload.update({
                "file_name": uploaded["file_name"],
                "file_path": uploaded["path"],
                "file_url": uploaded["url"],
                "file_size": uploaded["file_size"],
                "mime_type": uploaded["mime_type"],
            })

        row, error = db_insert("assignments", payload)

        if error:
            # Minimal fallback because the old assignments schema
            # may not contain all fields.
            minimal = {
                "id": str(uuid.uuid4()),
                "title": title,
                "description": description,
            }

            if uploaded:
                minimal["file_name"] = uploaded["file_name"]
                minimal["file_path"] = uploaded["path"]
                minimal["file_url"] = uploaded["url"]

            row, error = db_insert("assignments", minimal)

        if error:
            flash(
                "Assignment could not be saved. "
                "Check the assignments table columns.",
                "danger"
            )
        else:
            flash("Assignment uploaded successfully.", "success")

        return redirect(url_for("assignments"))

    rows = db_select(
        "assignments",
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Assignments",
        """
<div class="card">
<h2>Upload Assignment</h2>

<form method="post"
      enctype="multipart/form-data">

<label>Assignment Title</label>
<input name="title" required>

<label>Description / Question</label>
<textarea name="description"></textarea>

<label>Assignment File</label>
<input type="file"
       name="file"
       accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png">

<button type="submit">Upload Assignment</button>

</form>
</div>

<div class="card">
<h2>Assignments</h2>

{% if rows %}
<table>
<tr>
<th>Title</th>
<th>Description</th>
<th>File</th>
</tr>

{% for item in rows %}
<tr>
<td>{{ item.get("title") or "Assignment" }}</td>
<td>{{ item.get("description") or "" }}</td>
<td>
{% if item.get("file_url") %}
<a class="btn"
   href="{{ item.get("file_url") }}"
   target="_blank">
Download
</a>
{% else %}
No file
{% endif %}
</td>
</tr>
{% endfor %}
</table>
{% else %}
<p>No assignments found.</p>
{% endif %}

</div>
""",
        rows=rows,
    )


# ============================================================
# CV
# ============================================================

@app.route("/cv", methods=["GET", "POST"])
@login_required
def cv():
    user = current_user()

    if request.method == "POST":
        data = {
            "full_name": request.form.get("full_name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip(),
            "address": request.form.get("address", "").strip(),
            "profile": request.form.get("profile", "").strip(),
            "education": request.form.get("education", "").strip(),
            "experience": request.form.get("experience", "").strip(),
            "skills": request.form.get("skills", "").strip(),
            "references": request.form.get("references", "").strip(),
        }

        return render_page(
            "CV Preview",
            """
<div class="card">

<h1>{{ data.full_name }}</h1>

<p>
{{ data.phone }} |
{{ data.email }} |
{{ data.address }}
</p>

{% if data.profile %}
<h2>Professional Profile</h2>
<p>{{ data.profile }}</p>
{% endif %}

{% if data.education %}
<h2>Education</h2>
<p style="white-space:pre-wrap">{{ data.education }}</p>
{% endif %}

{% if data.experience %}
<h2>Work Experience</h2>
<p style="white-space:pre-wrap">{{ data.experience }}</p>
{% endif %}

{% if data.skills %}
<h2>Skills</h2>
<p style="white-space:pre-wrap">{{ data.skills }}</p>
{% endif %}

{% if data.references %}
<h2>References</h2>
<p style="white-space:pre-wrap">{{ data.references }}</p>
{% endif %}

<hr>

<button onclick="window.print()">Print / Save as PDF</button>

</div>
""",
            data=data,
        )

    return render_page(
        "CV Builder",
        """
<div class="card">
<h2>CV Builder</h2>

<form method="post">

<label>Full Name</label>
<input name="full_name"
       value="{{ user.name }}"
       required>

<label>Phone</label>
<input name="phone"
       value="{{ user.phone or '' }}">

<label>Email</label>
<input name="email"
       value="{{ user.email or '' }}"
       required>

<label>Address</label>
<input name="address">

<label>Professional Profile</label>
<textarea name="profile"></textarea>

<label>Education</label>
<textarea name="education"
placeholder="Institution, qualification, dates"></textarea>

<label>Work Experience</label>
<textarea name="experience"></textarea>

<label>Skills</label>
<textarea name="skills"></textarea>

<label>References</label>
<textarea name="references"></textarea>

<button type="submit">Generate CV</button>

</form>

<p class="small">
The generated CV can be printed or saved as PDF directly from
your Android browser.
</p>

</div>
"""
    )


# ============================================================
# FARMER REGISTRATION
# ============================================================

@app.route("/farmer", methods=["GET", "POST"])
@login_required
def farmer():
    user = current_user()

    if request.method == "POST":
        data = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "nrc": request.form.get("nrc", "").strip(),
            "date_of_birth": request.form.get("date_of_birth") or None,
            "first_name": request.form.get("first_name", "").strip(),
            "middle_names": request.form.get("middle_names", "").strip(),
            "last_name": request.form.get("last_name", "").strip(),
            "gender": request.form.get("gender", ""),
            "phone": request.form.get("phone", "").strip(),
            "location": request.form.get("location", "").strip(),
            "payment_method": request.form.get("payment_method", ""),
            "provider": request.form.get("provider", ""),
            "branch": request.form.get("branch", ""),
            "account_number": request.form.get("account_number", ""),
            "account_name": request.form.get("account_name", ""),
            "status": "submitted",
            "created_at": utc_now(),
        }

        nrc_file = request.files.get("nrc_document")

        if nrc_file and nrc_file.filename:
            uploaded, error = upload_storage(
                nrc_file,
                folder="farmer-nrc"
            )

            if error:
                flash(error, "danger")
                return redirect(url_for("farmer"))

            data["nrc_document_url"] = uploaded["url"]
            data["nrc_document_path"] = uploaded["path"]

        # Try the actual farmer_registrations table.
        row, error = db_insert(
            "farmer_registrations",
            data
        )

        if error:
            # Retry with common essential fields only.
            minimal = {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "nrc": data["nrc"],
                "first_name": data["first_name"],
                "middle_names": data["middle_names"],
                "last_name": data["last_name"],
                "gender": data["gender"],
                "phone": data["phone"],
                "location": data["location"],
            }

            row, error = db_insert(
                "farmer_registrations",
                minimal
            )

        if error:
            flash(
                "Farmer registration could not be submitted. "
                "Your existing farmer table uses additional/different "
                "columns. The application did not crash.",
                "danger"
            )
        else:
            log_activity(
                "farmer_registration",
                "Farmer registration submitted."
            )
            flash(
                "Farmer registration submitted successfully.",
                "success"
            )

        return redirect(url_for("farmer"))

    return render_page(
        "Farmer Registration",
        """
<div class="hero">
<h2>KOJA Farmer Registration</h2>
<p>Register your agricultural service request.</p>
</div>

<div class="card">

<form method="post"
      enctype="multipart/form-data">

<h3>Step 1 — Personal Details</h3>

<label>NRC</label>
<input name="nrc" required>

<label>Date of Birth</label>
<input name="date_of_birth" type="date">

<label>First Name</label>
<input name="first_name" required>

<label>Middle Names</label>
<input name="middle_names">

<label>Last Name</label>
<input name="last_name" required>

<label>Gender</label>
<select name="gender">
<option value="">Select</option>
<option>Male</option>
<option>Female</option>
</select>

<label>Phone</label>
<input name="phone" required>

<label>NRC Card</label>
<input type="file"
       name="nrc_document"
       accept=".jpg,.jpeg,.png,.pdf">

<h3>Step 2 — Farming Location</h3>

<label>Location</label>
<input name="location"
       placeholder="Province / District / Chiefdom / Camp">

<h3>Step 3 — Payment Details</h3>

<label>Payment Method</label>
<select name="payment_method">
<option>Bank Account</option>
<option>Mobile Money (MNO)</option>
<option>Wallet</option>
</select>

<label>Provider</label>
<select name="provider">
<option value="">Select provider</option>
<option>AB Bank</option>
<option>Absa Bank Zambia PLC</option>
<option>Access Bank</option>
<option>Bank of Zambia</option>
<option>Bayport Financial Services</option>
<option>Citibank Zambia</option>
<option>Ecobank</option>
<option>First Alliance Bank</option>
<option>First Capital Bank</option>
<option>First National Bank</option>
<option>Indo Zambia Bank</option>
<option>IZWE</option>
<option>NATSAVE</option>
<option>Stanbic Bank Zambia</option>
<option>Standard Chartered Bank</option>
<option>United Bank for Africa</option>
<option>Zambia Industrial Commercial Bank</option>
<option>Zambia National Building Society</option>
<option>Zambia National Commercial Bank</option>
</select>

<label>Branch</label>
<input name="branch">

<label>Account / Mobile Number</label>
<input name="account_number">

<label>Account Name</label>
<input name="account_name">

<button type="submit">
Submit Farmer Registration
</button>

</form>

</div>
"""
    )


# ============================================================
# DOCTORS
# ============================================================

@app.route("/doctors")
@login_required
def doctors():
    doctors = db_select(
        "doctor_profiles",
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Doctors",
        """
<div class="hero">
<h2>Find a Doctor</h2>
<p>Choose a specific doctor and request an appointment.</p>
</div>

<div class="grid">

{% for d in doctors %}

<div class="card">

<h3>
{{ d.get("full_name")
   or d.get("doctor_name")
   or "Doctor" }}
</h3>

<p>
<strong>Specialty:</strong>
{{ d.get("specialty") or "General" }}
</p>

<p>
<strong>Hospital/Clinic:</strong>
{{ d.get("hospital_clinic") or "Not specified" }}
</p>

<p>
<strong>Consultation:</strong>
{{ d.get("consultation_type") or "Appointment" }}
</p>

{% if d.get("consultation_fee") %}
<p>
<strong>Fee:</strong>
{{ d.get("currency") or "ZMW" }}
{{ d.get("consultation_fee") }}
</p>
{% endif %}

<a class="btn"
href="{{ url_for('book_doctor', provider_id=d.get('provider_id')) }}">
Book This Doctor
</a>

<a class="btn secondary"
href="{{ url_for('provider_map',
                  provider_id=d.get('provider_id'),
                  provider_type='doctor') }}">
View Location
</a>

</div>

{% else %}

<div class="card">
<p>No doctor profiles have been registered yet.</p>
</div>

{% endfor %}

</div>
""",
        doctors=doctors,
    )


@app.route("/doctor/book/<provider_id>", methods=["GET", "POST"])
@login_required
def book_doctor(provider_id):
    user = current_user()

    doctor = first_row(
        "doctor_profiles",
        {"provider_id": provider_id}
    )

    if not doctor:
        abort(404)

    if request.method == "POST":
        payload = {
            "id": str(uuid.uuid4()),
            "client_id": user["id"],
            "provider_id": provider_id,
            "appointment_type": "doctor",
            "appointment_date": request.form.get("appointment_date"),
            "start_time": request.form.get("start_time"),
            "end_time": request.form.get("end_time"),
            "location": request.form.get("location", ""),
            "status": "requested",
            "notes": request.form.get("notes", ""),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

        row, error = db_insert(
            "appointments",
            payload
        )

        if error:
            flash(
                "Appointment could not be created: "
                + str(error)[:500],
                "danger"
            )
        else:
            log_activity(
                "doctor_booking",
                "Doctor appointment requested."
            )
            flash(
                "Doctor booking request submitted.",
                "success"
            )

        return redirect(url_for("dashboard"))

    return render_page(
        "Book Doctor",
        """
<div class="card">

<h2>
Book
{{ doctor.get("full_name")
   or doctor.get("doctor_name")
   or "Doctor" }}
</h2>

<p>
<strong>Specialty:</strong>
{{ doctor.get("specialty") or "General" }}
</p>

<form method="post">

<label>Date</label>
<input type="date"
       name="appointment_date"
       required>

<label>Start Time</label>
<input type="time"
       name="start_time"
       required>

<label>End Time</label>
<input type="time"
       name="end_time">

<label>Location</label>
<input name="location"
       placeholder="Hospital, clinic or online">

<label>Notes</label>
<textarea name="notes"></textarea>

<button type="submit">Request Appointment</button>

</form>

</div>
""",
        doctor=doctor,
    )


# ============================================================
# TEACHERS
# ============================================================

@app.route("/teachers")
@login_required
def teachers():
    teachers = db_select(
        "teacher_profiles",
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Teachers",
        """
<div class="hero">
<h2>Find a Teacher / Tutor</h2>
<p>Choose a specific teacher for tutoring.</p>
</div>

<div class="grid">

{% for t in teachers %}

<div class="card">

<h3>
{{ t.get("full_name")
   or t.get("teacher_name")
   or "Teacher" }}
</h3>

<p>
<strong>Subjects:</strong>
{{ t.get("subjects") or "Not specified" }}
</p>

<p>
<strong>Grades:</strong>
{{ t.get("grade_levels") or "Not specified" }}
</p>

<p>
<strong>Qualification:</strong>
{{ t.get("qualification") or "Not specified" }}
</p>

<p>
<strong>Experience:</strong>
{{ t.get("teaching_experience") or "Not specified" }}
</p>

{% if t.get("hourly_rate") %}
<p>
<strong>Rate:</strong>
{{ t.get("currency") or "ZMW" }}
{{ t.get("hourly_rate") }}/hour
</p>
{% endif %}

<a class="btn"
href="{{ url_for('book_teacher',
                  provider_id=t.get('provider_id')) }}">
Book Teacher
</a>

<a class="btn secondary"
href="{{ url_for('provider_map',
                  provider_id=t.get('provider_id'),
                  provider_type='teacher') }}">
View Location
</a>

</div>

{% else %}

<div class="card">
<p>No teacher profiles have been registered yet.</p>
</div>

{% endfor %}

</div>
""",
        teachers=teachers,
    )


@app.route("/teacher/book/<provider_id>", methods=["GET", "POST"])
@login_required
def book_teacher(provider_id):
    user = current_user()

    teacher = first_row(
        "teacher_profiles",
        {"provider_id": provider_id}
    )

    if not teacher:
        abort(404)

    if request.method == "POST":
        payload = {
            "id": str(uuid.uuid4()),
            "client_id": user["id"],
            "provider_id": provider_id,
            "appointment_type": "teacher",
            "appointment_date": request.form.get("appointment_date"),
            "start_time": request.form.get("start_time"),
            "end_time": request.form.get("end_time"),
            "location": request.form.get("location", ""),
            "status": "requested",
            "notes": request.form.get("notes", ""),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

        row, error = db_insert(
            "appointments",
            payload
        )

        if error:
            flash(
                "Teacher booking failed: "
                + str(error)[:500],
                "danger"
            )
        else:
            flash(
                "Teacher booking request submitted.",
                "success"
            )

        return redirect(url_for("dashboard"))

    return render_page(
        "Book Teacher",
        """
<div class="card">

<h2>
Book
{{ teacher.get("full_name")
   or teacher.get("teacher_name")
   or "Teacher" }}
</h2>

<p>
{{ teacher.get("subjects") or "" }}
</p>

<form method="post">

<label>Date</label>
<input type="date"
       name="appointment_date"
       required>

<label>Start Time</label>
<input type="time"
       name="start_time"
       required>

<label>End Time</label>
<input type="time"
       name="end_time">

<label>Location / Online</label>
<input name="location">

<label>Notes</label>
<textarea name="notes"></textarea>

<button type="submit">Book Teacher</button>

</form>

</div>
""",
        teacher=teacher,
    )


# ============================================================
# DELIVERIES
# ============================================================

@app.route("/deliveries", methods=["GET", "POST"])
@login_required
def deliveries():
    user = current_user()

    if request.method == "POST":
        tracking_code = (
            "KOJA-"
            + datetime.now().strftime("%Y%m%d")
            + "-"
            + secrets.token_hex(3).upper()
        )

        payload = {
            "id": str(uuid.uuid4()),
            "customer_id": user["id"],
            "pickup_location": request.form.get(
                "pickup_location", ""
            ).strip(),
            "destination": request.form.get(
                "destination", ""
            ).strip(),
            "recipient_name": request.form.get(
                "recipient_name", ""
            ).strip(),
            "recipient_phone": request.form.get(
                "recipient_phone", ""
            ).strip(),
            "package_description": request.form.get(
                "package_description", ""
            ).strip(),
            "package_weight": request.form.get(
                "package_weight"
            ) or None,
            "delivery_fee": request.form.get(
                "delivery_fee"
            ) or 0,
            "currency": "ZMW",
            "requested_date": request.form.get(
                "requested_date"
            ) or None,
            "requested_time": request.form.get(
                "requested_time"
            ) or None,
            "status": "requested",
            "tracking_code": tracking_code,
            "notes": request.form.get("notes", ""),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

        row, error = db_insert(
            "deliveries",
            payload
        )

        if error:
            flash(
                "Delivery could not be registered: "
                + str(error)[:600],
                "danger"
            )
        else:
            flash(
                f"Delivery registered. Tracking code: {tracking_code}",
                "success"
            )

        return redirect(url_for("deliveries"))

    rows = db_select(
        "deliveries",
        filters={"customer_id": user["id"]},
        order="created_at.desc",
        limit=100,
    )

    return render_page(
        "Deliveries",
        """
<div class="card">

<h2>Register Delivery</h2>

<form method="post">

<label>Pickup Location</label>
<input name="pickup_location"
       placeholder="Type pickup address/place"
       required>

<label>Destination</label>
<input name="destination"
       placeholder="Type destination"
       required>

<label>Recipient Name</label>
<input name="recipient_name" required>

<label>Recipient Phone</label>
<input name="recipient_phone" required>

<label>Package Description</label>
<textarea name="package_description"></textarea>

<label>Package Weight (kg)</label>
<input type="number"
       step="0.01"
       name="package_weight">

<label>Delivery Fee (ZMW)</label>
<input type="number"
       step="0.01"
       name="delivery_fee">

<label>Requested Date</label>
<input type="date"
       name="requested_date">

<label>Requested Time</label>
<input type="time"
       name="requested_time">

<label>Notes</label>
<textarea name="notes"></textarea>

<button type="submit">
Register Delivery
</button>

</form>

</div>

<div class="card">

<h2>My Deliveries</h2>

{% for d in rows %}

<div class="card">

<strong>
{{ d.get("tracking_code") }}
</strong>

<p>
{{ d.get("pickup_location") }}
→
{{ d.get("destination") }}
</p>

<p>
Status:
<span class="badge">
{{ d.get("status") or "requested" }}
</span>
</p>

<a class="btn"
href="{{ url_for('track_delivery',
                  tracking_code=d.get('tracking_code')) }}">
Track Driver
</a>

</div>

{% else %}

<p>No deliveries registered.</p>

{% endfor %}

</div>
""",
        rows=rows,
    )


# ============================================================
# DELIVERY TRACKING
# ============================================================

@app.route("/track/<tracking_code>")
@login_required
def track_delivery(tracking_code):
    delivery = first_row(
        "deliveries",
        {"tracking_code": tracking_code}
    )

    if not delivery:
        abort(404)

    return render_page(
        "Track Delivery",
        """
<div class="hero">
<h2>Delivery Tracking</h2>
<p>
Tracking code:
<strong>{{ delivery.get("tracking_code") }}</strong>
</p>
</div>

<div class="card">

<p>
<strong>Pickup:</strong>
{{ delivery.get("pickup_location") }}
</p>

<p>
<strong>Destination:</strong>
{{ delivery.get("destination") }}
</p>

<p>
<strong>Status:</strong>
{{ delivery.get("status") }}
</p>

<div id="map"></div>

<p id="tracking-status"
   class="small">
Waiting for driver's location...
</p>

</div>

<script>

const trackingCode =
    {{ delivery.get("tracking_code")|tojson }};

let map = L.map("map").setView(
    [-13.9626, 28.3228],
    6
);

L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
    }
).addTo(map);

let marker = null;

async function loadDriverLocation() {

    try {

        const response =
            await fetch(
                "/api/delivery/"
                + encodeURIComponent(trackingCode)
                + "/location"
            );

        const data =
            await response.json();

        if (!data.ok) {
            document.getElementById(
                "tracking-status"
            ).textContent =
                data.message || "No GPS location available.";

            return;
        }

        const lat = data.latitude;
        const lon = data.longitude;

        if (!marker) {

            marker = L.marker([lat, lon])
                .addTo(map)
                .bindPopup("Driver location");

            map.setView([lat, lon], 15);

        } else {

            marker.setLatLng([lat, lon]);

        }

        document.getElementById(
            "tracking-status"
        ).textContent =
            "Driver location updated: "
            + (data.updated_at || "recently");

    } catch (error) {

        document.getElementById(
            "tracking-status"
        ).textContent =
            "Unable to obtain driver location.";

    }
}

loadDriverLocation();

setInterval(
    loadDriverLocation,
    10000
);

</script>
""",
        delivery=delivery,
    )


@app.route("/api/delivery/<tracking_code>/location")
@login_required
def delivery_location(tracking_code):

    delivery = first_row(
        "deliveries",
        {"tracking_code": tracking_code}
    )

    if not delivery:
        return jsonify({
            "ok": False,
            "message": "Delivery not found."
        }), 404

    delivery_id = delivery.get("id")
    driver_id = delivery.get("driver_id")

    locations = []

    if delivery_id:
        locations = db_select(
            "koja_location_updates",
            filters={"delivery_id": delivery_id},
            order="created_at.desc",
            limit=1,
        )

    if not locations and driver_id:
        locations = db_select(
            "koja_location_updates",
            filters={"user_id": driver_id},
            order="created_at.desc",
            limit=1,
        )

    if not locations:
        return jsonify({
            "ok": False,
            "message": "Driver has not shared a GPS location yet."
        })

    loc = locations[0]

    return jsonify({
        "ok": True,
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "accuracy": loc.get("accuracy"),
        "speed": loc.get("speed"),
        "heading": loc.get("heading"),
        "updated_at": loc.get("created_at"),
    })


# ============================================================
# DRIVER GPS TRACKING
# ============================================================

@app.route("/tracking")
@login_required
def tracking():
    return render_page(
        "Live GPS Tracking",
        """
<div class="hero">
<h2>Live GPS Tracking</h2>
<p>
Use your phone's GPS to share your current position.
</p>
</div>

<div class="card">

<h3>Driver GPS</h3>

<label>Delivery ID (optional)</label>
<input id="delivery_id"
       placeholder="Paste delivery UUID">

<button onclick="startTracking()">
Start GPS Sharing
</button>

<button class="btn danger"
        onclick="stopTracking()">
Stop GPS Sharing
</button>

<p id="gps-status">
GPS not started.
</p>

<div id="map"></div>

</div>

<script>

let watchId = null;
let marker = null;

const map = L.map("map").setView(
    [-13.9626, 28.3228],
    6
);

L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
    }
).addTo(map);

function setStatus(text) {
    document.getElementById(
        "gps-status"
    ).textContent = text;
}

function startTracking() {

    if (!navigator.geolocation) {

        setStatus(
            "This phone/browser does not support GPS."
        );

        return;
    }

    setStatus(
        "Requesting GPS permission..."
    );

    watchId =
        navigator.geolocation.watchPosition(
            sendPosition,
            gpsError,
            {
                enableHighAccuracy: true,
                maximumAge: 5000,
                timeout: 15000
            }
        );
}

async function sendPosition(position) {

    const coords = position.coords;

    const lat = coords.latitude;
    const lon = coords.longitude;

    if (!marker) {

        marker = L.marker([lat, lon])
            .addTo(map)
            .bindPopup("Your current location");

    } else {

        marker.setLatLng([lat, lon]);

    }

    map.setView(
        [lat, lon],
        16
    );

    const deliveryId =
        document.getElementById(
            "delivery_id"
        ).value.trim();

    try {

        const response =
            await fetch(
                "/api/gps/update",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        latitude: lat,
                        longitude: lon,
                        accuracy: coords.accuracy,
                        speed: coords.speed,
                        heading: coords.heading,
                        altitude: coords.altitude,
                        delivery_id:
                            deliveryId || null
                    })
                }
            );

        const data =
            await response.json();

        if (data.ok) {

            setStatus(
                "GPS sharing active. "
                + new Date().toLocaleTimeString()
            );

        } else {

            setStatus(
                data.message ||
                "GPS position could not be saved."
            );

        }

    } catch (error) {

        setStatus(
            "Network error while sending GPS position."
        );

    }
}

function gpsError(error) {

    if (error.code === 1) {

        setStatus(
            "GPS permission was denied. "
            + "Allow location permission in your browser."
        );

    } else if (error.code === 2) {

        setStatus(
            "Your device could not determine its location."
        );

    } else if (error.code === 3) {

        setStatus(
            "GPS request timed out."
        );

    } else {

        setStatus(
            "GPS error."
        );
    }
}

function stopTracking() {

    if (watchId !== null) {

        navigator.geolocation.clearWatch(
            watchId
        );

        watchId = null;

        setStatus(
            "GPS sharing stopped."
        );
    }
}

</script>
"""
    )


@app.route("/api/gps/update", methods=["POST"])
@login_required
def gps_update():

    if not table_exists("koja_location_updates"):
        return jsonify({
            "ok": False,
            "message":
                "GPS table is not installed. "
                "Create public.koja_location_updates "
                "in Supabase first."
        }), 503

    body = request.get_json(
        silent=True
    ) or {}

    try:
        latitude = float(
            body.get("latitude")
        )

        longitude = float(
            body.get("longitude")
        )

    except Exception:

        return jsonify({
            "ok": False,
            "message": "Invalid latitude or longitude."
        }), 400

    if not (-90 <= latitude <= 90):
        return jsonify({
            "ok": False,
            "message": "Invalid latitude."
        }), 400

    if not (-180 <= longitude <= 180):
        return jsonify({
            "ok": False,
            "message": "Invalid longitude."
        }), 400

    user = current_user()

    payload = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "delivery_id": body.get("delivery_id") or None,
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": body.get("accuracy"),
        "speed": body.get("speed"),
        "heading": body.get("heading"),
        "altitude": body.get("altitude"),
        "is_online": True,
        "created_at": utc_now(),
    }

    row, error = db_insert(
        "koja_location_updates",
        payload
    )

    if error:
        return jsonify({
            "ok": False,
            "message": "GPS location could not be saved."
        }), 500

    # If this GPS update belongs to a delivery,
    # associate the driver with that delivery.
    delivery_id = body.get("delivery_id")

    if delivery_id:

        db_update(
            "deliveries",
            {"id": delivery_id},
            {
                "driver_id": user["id"],
                "updated_at": utc_now(),
            }
        )

    return jsonify({
        "ok": True,
        "latitude": latitude,
        "longitude": longitude,
        "created_at": utc_now(),
    })


# ============================================================
# PROVIDER MAP
# ============================================================

@app.route("/provider-map/<provider_id>")
@login_required
def provider_map(provider_id):

    provider_type = request.args.get(
        "provider_type",
        "provider"
    )

    return render_page(
        "Provider Location",
        """
<div class="hero">
<h2>{{ provider_type|title }} Location</h2>
<p>
The map displays the latest GPS position shared by
this service provider.
</p>
</div>

<div class="card">

<div id="map"></div>

<p id="status">
Loading provider location...
</p>

</div>

<script>

const providerId =
    {{ provider_id|tojson }};

const providerType =
    {{ provider_type|tojson }};

const map =
    L.map("map").setView(
        [-13.9626, 28.3228],
        6
    );

L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 19,
        attribution:
            "&copy; OpenStreetMap contributors"
    }
).addTo(map);

let marker = null;

async function updateMap() {

    try {

        const r =
            await fetch(
                "/api/provider/"
                + encodeURIComponent(providerId)
                + "/location"
            );

        const data =
            await r.json();

        if (!data.ok) {

            document.getElementById(
                "status"
            ).textContent =
                data.message ||
                "No location available.";

            return;
        }

        const point = [
            data.latitude,
            data.longitude
        ];

        if (!marker) {

            marker =
                L.marker(point)
                .addTo(map)
                .bindPopup(
                    providerType
                    + " location"
                );

            map.setView(point, 15);

        } else {

            marker.setLatLng(point);

        }

        document.getElementById(
            "status"
        ).textContent =
            "Last update: "
            + data.updated_at;

    } catch (e) {

        document.getElementById(
            "status"
        ).textContent =
            "Unable to load GPS position.";

    }
}

updateMap();

setInterval(
    updateMap,
    10000
);

</script>
""",
        provider_id=provider_id,
        provider_type=provider_type,
    )


@app.route("/api/provider/<provider_id>/location")
@login_required
def provider_location(provider_id):

    rows = db_select(
        "koja_location_updates",
        filters={"user_id": provider_id},
        order="created_at.desc",
        limit=1,
    )

    if not rows:
        return jsonify({
            "ok": False,
            "message":
                "This provider has not shared a GPS location."
        })

    loc = rows[0]

    return jsonify({
        "ok": True,
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "accuracy": loc.get("accuracy"),
        "speed": loc.get("speed"),
        "heading": loc.get("heading"),
        "updated_at": loc.get("created_at"),
    })


# ============================================================
# UNIVERSITY APPLICATIONS
# ============================================================

@app.route("/universities")
@login_required
def universities():

    universities = db_select(
        "universities",
        order="name.asc",
        limit=200,
    )

    return render_page(
        "Universities",
        """
<div class="hero">
<h2>University Applications</h2>
<p>
Select the university first, then select a programme.
</p>
</div>

<div class="card">

{% if universities %}

<div class="grid">

{% for university in universities %}

<div class="card">

<h3>
{{ university.get("name")
   or university.get("university_name")
   or "University" }}
</h3>

<p>
{{ university.get("location")
   or university.get("description")
   or "" }}
</p>

<a class="btn"
href="{{ url_for(
    'university_apply',
    university_id=university.get('id')
) }}">
Apply
</a>

</div>

{% endfor %}

</div>

{% else %}

<p>
No universities are currently loaded into the universities table.
</p>

{% endif %}

</div>
""",
        universities=universities,
    )


@app.route("/university/apply/<university_id>", methods=["GET", "POST"])
@login_required
def university_apply(university_id):

    user = current_user()

    university = first_row(
        "universities",
        {"id": university_id}
    )

    if not university:
        abort(404)

    programmes = db_select(
        "university_programmes",
        filters={"university_id": university_id},
        order="name.asc",
        limit=500,
    )

    requirements = db_select(
        "university_application_requirements",
        filters={"university_id": university_id},
        limit=500,
    )

    if request.method == "POST":

        programme_id = request.form.get(
            "programme_id"
        )

        year = request.form.get(
            "academic_year"
        )

        payload = {
            "id": str(uuid.uuid4()),
            "user_id": user["id"],
            "university_id": university_id,
            "programme_id": programme_id,
            "academic_year": year,
            "full_name": user["name"],
            "email": user["email"],
            "phone": user.get("phone"),
            "status": "draft",
            "created_at": utc_now(),
        }

        row, error = db_insert(
            "university_applications",
            payload
        )

        if error:

            minimal = {
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "university_id": university_id,
                "programme_id": programme_id,
                "academic_year": year,
            }

            row, error = db_insert(
                "university_applications",
                minimal
            )

        if error:

            flash(
                "Application could not be created: "
                + str(error)[:600],
                "danger"
            )

        else:

            flash(
                "University application started.",
                "success"
            )

        return redirect(
            url_for(
                "universities"
            )
        )

    return render_page(
        "University Application",
        """
<div class="card">

<h2>
{{ university.get("name")
   or university.get("university_name") }}
</h2>

<h3>Select Programme</h3>

<form method="post">

<label>Programme</label>

<select name="programme_id" required>

<option value="">
Select programme
</option>

{% for p in programmes %}

<option value="{{ p.get('id') }}">

{{ p.get("name")
   or p.get("programme_name")
   or p.get("title") }}

</option>

{% endfor %}

</select>

<label>Academic Year</label>

<select name="academic_year" required>

<option value="2026/2027">
2026/2027
</option>

<option value="2027/2028">
2027/2028
</option>

</select>

<button type="submit">
Start Application
</button>

</form>

</div>

<div class="card">

<h3>University Requirements</h3>

{% if requirements %}

{% for requirement in requirements %}

<div class="card">

<strong>
{{ requirement.get("title")
   or requirement.get("requirement")
   or "Requirement" }}
</strong>

<p>
{{ requirement.get("description")
   or requirement.get("details")
   or "" }}
</p>

</div>

{% endfor %}

{% else %}

<p>
No specific requirements have been entered into the
university requirements table yet.
</p>

{% endif %}

</div>
""",
        university=university,
        programmes=programmes,
        requirements=requirements,
    )


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    tables = [
        "profiles",
        "questions",
        "assignments",
        "farmer_registrations",
        "doctor_profiles",
        "teacher_profiles",
        "driver_profiles",
        "deliveries",
        "appointments",
        "universities",
        "university_applications",
        "activity_logs",
    ]

    counts = {}

    for table in tables:

        rows = db_select(
            table,
            select="*",
            limit=1000,
        )

        counts[table] = len(rows)

    return render_page(
        "Admin Dashboard",
        """
<div class="hero">
<h2>KOJA Administrator</h2>
<p>
System management dashboard.
</p>
</div>

<div class="grid">

{% for name, count in counts.items() %}

<div class="stat">

<div class="big">
{{ count }}
</div>

{{ name }}

</div>

{% endfor %}

</div>

<div class="card">

<h3>Management</h3>

<p>
Use Supabase for detailed record management.
The application only exposes operations that match
the existing schema.
</p>

<a class="btn"
href="{{ url_for('admin_deliveries') }}">
Manage Deliveries
</a>

<a class="btn"
href="{{ url_for('admin_appointments') }}">
Manage Appointments
</a>

<a class="btn"
href="{{ url_for('admin_users') }}">
Manage Users
</a>

</div>
""",
        counts=counts,
    )


@app.route("/admin/users")
@admin_required
def admin_users():

    rows = db_select(
        "profiles",
        order="created_at.desc",
        limit=200,
    )

    return render_page(
        "Admin Users",
        """
<div class="card">

<h2>Users</h2>

<table>

<tr>
<th>Name</th>
<th>Email</th>
<th>Phone</th>
<th>Role</th>
<th>Admin</th>
</tr>

{% for u in rows %}

<tr>

<td>
{{ u.get("full_name") or u.get("name") }}
</td>

<td>
{{ u.get("email") }}
</td>

<td>
{{ u.get("phone") or "" }}
</td>

<td>
{{ u.get("role") or "" }}
</td>

<td>
{{ "Yes" if u.get("is_admin") else "No" }}
</td>

</tr>

{% endfor %}

</table>

</div>
""",
        rows=rows,
    )


@app.route("/admin/deliveries")
@admin_required
def admin_deliveries():

    rows = db_select(
        "deliveries",
        order="created_at.desc",
        limit=300,
    )

    return render_page(
        "Admin Deliveries",
        """
<div class="card">

<h2>Deliveries</h2>

<table>

<tr>
<th>Tracking</th>
<th>Customer</th>
<th>Pickup</th>
<th>Destination</th>
<th>Driver</th>
<th>Status</th>
</tr>

{% for d in rows %}

<tr>

<td>
{{ d.get("tracking_code") }}
</td>

<td>
{{ d.get("customer_id") }}
</td>

<td>
{{ d.get("pickup_location") }}
</td>

<td>
{{ d.get("destination") }}
</td>

<td>
{{ d.get("driver_id") or "Unassigned" }}
</td>

<td>
{{ d.get("status") }}
</td>

</tr>

{% endfor %}

</table>

</div>
""",
        rows=rows,
    )


@app.route("/admin/appointments")
@admin_required
def admin_appointments():

    rows = db_select(
        "appointments",
        order="created_at.desc",
        limit=300,
    )

    return render_page(
        "Admin Appointments",
        """
<div class="card">

<h2>Appointments</h2>

<table>

<tr>
<th>Date</th>
<th>Client</th>
<th>Provider</th>
<th>Type</th>
<th>Status</th>
</tr>

{% for a in rows %}

<tr>

<td>
{{ a.get("appointment_date") }}
</td>

<td>
{{ a.get("client_id") }}
</td>

<td>
{{ a.get("provider_id") }}
</td>

<td>
{{ a.get("appointment_type") }}
</td>

<td>
{{ a.get("status") }}
</td>

</tr>

{% endfor %}

</table>

</div>
""",
        rows=rows,
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return render_page(
        "Not Found",
        """
<div class="card">
<h2>Page Not Found</h2>
<p>The requested page does not exist.</p>
<a class="btn" href="{{ url_for('home') }}">
Return Home
</a>
</div>
"""
    ), 404


@app.errorhandler(413)
def too_large(error):
    return render_page(
        "File Too Large",
        """
<div class="card">
<h2>File Too Large</h2>
<p>
The maximum upload size is {{ max_mb }} MB.
</p>
</div>
""",
        max_mb=MAX_UPLOAD_MB,
    ), 413


@app.errorhandler(500)
def internal_error(error):
    logger.exception(
        "Unhandled application error"
    )

    return render_page(
        "Server Error",
        """
<div class="card">

<h2>KOJA AFRICA Server Error</h2>

<p>
The server encountered an unexpected error.
The error has been logged on the server.
</p>

<a class="btn"
href="{{ url_for('home') }}">
Return Home
</a>

</div>
"""
    ), 500


# ============================================================
# STARTUP
# ============================================================

@app.before_request
def before_request():
    """
    Deliberately does NOT connect to PostgreSQL or Supabase here.
    This prevents the entire Render service from crashing merely
    because the database is temporarily unavailable.
    """
    pass


@app.context_processor
def inject_globals():
    return {
        "APP_NAME": APP_NAME,
        "APP_TAGLINE": APP_TAGLINE,
    }


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv("PORT", "5000")
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
