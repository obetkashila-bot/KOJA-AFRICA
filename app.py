import os
import io
import uuid
import json
import secrets
import logging
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote

import requests

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    flash,
    send_file,
    abort,
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ReportLab is used for CV generation
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ============================================================
# KOJA AFRICA
# Multi-Service Client Assistance Platform
#
# SUPABASE REST VERSION
#
# IMPORTANT:
# This application does NOT use psycopg / psycopg2.
#
# Required Render environment variables:
#
# SUPABASE_URL
# SUPABASE_ANON_KEY
# SUPABASE_SERVICE_KEY
# SECRET_KEY
# ADMIN_EMAIL
# ADMIN_PASSWORD
#
# Optional:
# KOJA_PAYMENT_AMOUNT
# FLW_SECRET_KEY
# FLW_SECRET_HASH
# FLW_BASE_URL
#
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    secrets.token_hex(32)
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja")

# ============================================================
# CONFIGURATION
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

ADMIN_EMAIL = os.getenv(
    "ADMIN_EMAIL",
    "admin@kojaafrica.com"
)

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD",
    "ChangeThisPassword123!"
)

PAYMENT_AMOUNT = os.getenv(
    "KOJA_PAYMENT_AMOUNT",
    "10.00"
)

FLW_SECRET_KEY = os.getenv("FLW_SECRET_KEY", "")
FLW_SECRET_HASH = os.getenv("FLW_SECRET_HASH", "")

FLW_BASE_URL = os.getenv(
    "FLW_BASE_URL",
    "https://api.flutterwave.com/v3"
)

STORAGE_BUCKET = "koja-files"

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

# ============================================================
# BASIC VALIDATION
# ============================================================

if not SUPABASE_URL:
    logger.warning("SUPABASE_URL is not configured.")

if not SUPABASE_ANON_KEY:
    logger.warning("SUPABASE_ANON_KEY is not configured.")

if not SUPABASE_SERVICE_KEY:
    logger.warning("SUPABASE_SERVICE_KEY is not configured.")


# ============================================================
# SUPABASE HELPERS
# ============================================================

def rest_headers(service=True, return_data=False):
    """
    Headers for Supabase PostgREST.
    """

    key = (
        SUPABASE_SERVICE_KEY
        if service
        else SUPABASE_ANON_KEY
    )

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    if return_data:
        headers["Prefer"] = "return=representation"

    return headers


def table_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"


def supabase_select(
    table,
    params=None,
    service=True,
):
    """
    GET records from a Supabase table.
    """

    try:
        response = requests.get(
            table_url(table),
            headers=rest_headers(service=service),
            params=params or {},
            timeout=30,
        )

        if not response.ok:
            logger.error(
                "Supabase SELECT %s: %s",
                table,
                response.text
            )
            return []

        data = response.json()

        if isinstance(data, list):
            return data

        return []

    except Exception as exc:
        logger.exception(
            "Supabase SELECT error: %s",
            exc
        )
        return []


def supabase_insert(
    table,
    payload,
    service=True,
):
    """
    Insert one record.
    """

    try:
        response = requests.post(
            table_url(table),
            headers=rest_headers(
                service=service,
                return_data=True,
            ),
            json=payload,
            timeout=30,
        )

        if not response.ok:
            logger.error(
                "Supabase INSERT %s: %s",
                table,
                response.text
            )
            return None

        data = response.json()

        if isinstance(data, list) and data:
            return data[0]

        return data

    except Exception as exc:
        logger.exception(
            "Supabase INSERT error: %s",
            exc
        )
        return None


def supabase_update(
    table,
    filters,
    payload,
    service=True,
):
    """
    Update records using PostgREST filters.
    """

    try:
        response = requests.patch(
            table_url(table),
            headers=rest_headers(
                service=service,
                return_data=True,
            ),
            params=filters,
            json=payload,
            timeout=30,
        )

        if not response.ok:
            logger.error(
                "Supabase UPDATE %s: %s",
                table,
                response.text
            )
            return None

        data = response.json()

        if isinstance(data, list):
            return data

        return data

    except Exception as exc:
        logger.exception(
            "Supabase UPDATE error: %s",
            exc
        )
        return None


def supabase_delete(
    table,
    filters,
    service=True,
):
    """
    Delete records.
    """

    try:
        response = requests.delete(
            table_url(table),
            headers=rest_headers(service=service),
            params=filters,
            timeout=30,
        )

        if not response.ok:
            logger.error(
                "Supabase DELETE %s: %s",
                table,
                response.text
            )
            return False

        return True

    except Exception as exc:
        logger.exception(
            "Supabase DELETE error: %s",
            exc
        )
        return False


def get_one(
    table,
    record_id,
    service=True,
):
    rows = supabase_select(
        table,
        {
            "id": f"eq.{record_id}",
            "limit": "1",
        },
        service=service,
    )

    return rows[0] if rows else None


def get_by_user(
    table,
    user_id,
    service=True,
    order="created_at.desc",
):
    return supabase_select(
        table,
        {
            "user_id": f"eq.{user_id}",
            "order": order,
        },
        service=service,
    )


# ============================================================
# AUTHENTICATION
# ============================================================

def current_user():
    return session.get("user")


def current_user_id():
    user = current_user()

    if not user:
        return None

    return user.get("id")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):

        if not current_user():
            flash(
                "Please log in to continue.",
                "warning"
            )
            return redirect(
                url_for("login")
            )

        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):

        if not session.get("admin"):
            flash(
                "Administrator access required.",
                "danger"
            )
            return redirect(
                url_for("admin_login")
            )

        return view(*args, **kwargs)

    return wrapper


def provider_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):

        if not current_user():
            return redirect(url_for("login"))

        providers = supabase_select(
            "service_providers",
            {
                "user_id": f"eq.{current_user_id()}",
                "limit": "1",
            }
        )

        if not providers:
            flash(
                "You are not registered as a service provider.",
                "warning"
            )
            return redirect(
                url_for("dashboard")
            )

        return view(*args, **kwargs)

    return wrapper


# ============================================================
# SUPABASE AUTH
# ============================================================

def auth_signup(email, password):
    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "password": password,
            },
            timeout=30,
        )

        if not response.ok:
            logger.error(
                "Signup failed: %s",
                response.text
            )
            return None, response.text

        return response.json(), None

    except Exception as exc:
        return None, str(exc)


def auth_login(email, password):
    try:
        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "password": password,
            },
            timeout=30,
        )

        if not response.ok:
            logger.error(
                "Login failed: %s",
                response.text
            )
            return None, response.text

        return response.json(), None

    except Exception as exc:
        return None, str(exc)


# ============================================================
# STORAGE
# ============================================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def upload_to_storage(
    file_storage,
    folder="uploads",
):
    """
    Upload a Flask uploaded file to:
    koja-files/folder/uuid-filename
    """

    if not file_storage:
        return None

    filename = secure_filename(
        file_storage.filename or ""
    )

    if not filename:
        return None

    if not allowed_file(filename):
        return None

    extension = filename.rsplit(".", 1)[1].lower()

    storage_name = (
        f"{folder}/"
        f"{uuid.uuid4().hex}."
        f"{extension}"
    )

    content = file_storage.read()

    content_type = (
        file_storage.content_type
        or "application/octet-stream"
    )

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{storage_name}"
    )

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": content_type,
        "x-upsert": "false",
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            data=content,
            timeout=60,
        )

        if not response.ok:
            logger.error(
                "Storage upload failed: %s",
                response.text
            )
            return None

        return {
            "path": storage_name,
            "url": None,
            "file_name": filename,
            "file_size": len(content),
            "mime_type": content_type,
        }

    except Exception as exc:
        logger.exception(
            "Storage error: %s",
            exc
        )
        return None


def create_signed_url(path, expires=3600):
    if not path:
        return None

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"sign/{STORAGE_BUCKET}/"
        f"{quote(path, safe='/')}"
    )

    try:
        response = requests.post(
            url,
            headers=rest_headers(service=True),
            json={
                "expiresIn": expires
            },
            timeout=30,
        )

        if not response.ok:
            return None

        data = response.json()

        if isinstance(data, dict):
            signed = data.get("signedURL")

            if signed:
                if signed.startswith("http"):
                    return signed

                return (
                    f"{SUPABASE_URL}"
                    f"{signed}"
                )

        return None

    except Exception:
        return None


def delete_storage_file(path):
    if not path:
        return False

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}"
    )

    try:
        response = requests.delete(
            url,
            headers=rest_headers(service=True),
            json=[path],
            timeout=30,
        )

        return response.ok

    except Exception:
        return False


# ============================================================
# COMMON DATABASE FUNCTIONS
# ============================================================

def categories():
    return supabase_select(
        "service_categories",
        {
            "is_active": "eq.true",
            "order": "name.asc",
        }
    )


def create_notification(
    user_id,
    title,
    message,
    service_request_id=None,
    notification_type="general",
):
    payload = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "notification_type": notification_type,
        "is_read": False,
    }

    if service_request_id:
        payload["service_request_id"] = (
            service_request_id
        )

    return supabase_insert(
        "notifications",
        payload,
    )


def create_activity(
    user_id,
    service_request_id,
    action,
    description=None,
    old_status=None,
    new_status=None,
):
    return supabase_insert(
        "activity_logs",
        {
            "user_id": user_id,
            "service_request_id": service_request_id,
            "action": action,
            "description": description,
            "old_status": old_status,
            "new_status": new_status,
            "ip_address": request.remote_addr,
        }
    )


def create_comment(
    service_request_id,
    message,
    sender_type,
    user_id=None,
):
    return supabase_insert(
        "service_comments",
        {
            "service_request_id": service_request_id,
            "user_id": user_id,
            "sender_type": sender_type,
            "message": message,
        }
    )


# ============================================================
# HTML LAYOUT
# ============================================================

BASE_HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width,initial-scale=1">

<title>{{ title or "KOJA AFRICA" }}</title>

<style>
:root {
    --primary:#0b6b4f;
    --primary2:#064e3b;
    --bg:#f4f7f6;
    --card:#ffffff;
    --text:#17201d;
    --muted:#68756f;
    --danger:#b42318;
    --warning:#a15c00;
    --border:#dfe7e3;
}

* {
    box-sizing:border-box;
}

body {
    margin:0;
    background:var(--bg);
    color:var(--text);
    font-family:
        Arial,
        Helvetica,
        sans-serif;
}

nav {
    background:
        linear-gradient(
            135deg,
            var(--primary2),
            var(--primary)
        );
    color:white;
    padding:14px 18px;
}

.nav-inner {
    max-width:1200px;
    margin:auto;
    display:flex;
    gap:14px;
    align-items:center;
    justify-content:space-between;
    flex-wrap:wrap;
}

.brand {
    color:white;
    text-decoration:none;
    font-weight:800;
    font-size:21px;
}

.nav-links {
    display:flex;
    gap:7px;
    flex-wrap:wrap;
}

.nav-links a {
    color:white;
    text-decoration:none;
    padding:8px 10px;
    border-radius:8px;
}

.nav-links a:hover {
    background:rgba(255,255,255,.15);
}

.container {
    max-width:1200px;
    margin:22px auto;
    padding:0 14px;
}

.hero {
    background:
        linear-gradient(
            135deg,
            #064e3b,
            #0b6b4f
        );
    color:white;
    border-radius:18px;
    padding:28px;
    margin-bottom:20px;
}

.hero h1 {
    margin:0 0 8px;
}

.hero p {
    margin:0;
    opacity:.9;
}

.grid {
    display:grid;
    grid-template-columns:
        repeat(auto-fit,minmax(220px,1fr));
    gap:16px;
}

.card {
    background:var(--card);
    border:1px solid var(--border);
    border-radius:15px;
    padding:18px;
    box-shadow:
        0 3px 12px
        rgba(0,0,0,.04);
}

.card h3 {
    margin-top:0;
}

.service-card {
    transition:.15s;
}

.service-card:hover {
    transform:translateY(-2px);
    box-shadow:
        0 8px 25px
        rgba(0,0,0,.08);
}

.btn {
    display:inline-block;
    background:var(--primary);
    color:white;
    border:0;
    padding:10px 14px;
    border-radius:9px;
    text-decoration:none;
    cursor:pointer;
    font-weight:600;
}

.btn:hover {
    background:var(--primary2);
}

.btn-secondary {
    background:#e8efec;
    color:#12352b;
}

.btn-danger {
    background:var(--danger);
}

.btn-warning {
    background:var(--warning);
}

input,
select,
textarea {
    width:100%;
    padding:11px;
    margin:6px 0 14px;
    border:1px solid #cfdad5;
    border-radius:9px;
    font:inherit;
    background:white;
}

textarea {
    min-height:120px;
    resize:vertical;
}

label {
    font-weight:600;
    display:block;
}

table {
    width:100%;
    border-collapse:collapse;
    background:white;
}

th,
td {
    padding:10px;
    border-bottom:1px solid var(--border);
    text-align:left;
    vertical-align:top;
}

th {
    background:#eef4f1;
}

.table-wrap {
    overflow-x:auto;
}

.flash {
    padding:12px 14px;
    margin-bottom:12px;
    border-radius:9px;
    background:#e9f5ef;
    border:1px solid #cbe7d8;
}

.flash.danger {
    background:#fff0ef;
    border-color:#f0c4c0;
}

.flash.warning {
    background:#fff7e8;
    border-color:#efd49b;
}

.badge {
    display:inline-block;
    padding:5px 8px;
    border-radius:999px;
    background:#e9f5ef;
    font-size:12px;
}

.muted {
    color:var(--muted);
}

.stat {
    font-size:30px;
    font-weight:800;
}

form.inline {
    display:inline;
}

footer {
    text-align:center;
    padding:35px 15px;
    color:var(--muted);
}

@media(max-width:600px) {
    .hero {
        padding:21px;
    }

    th,
    td {
        font-size:13px;
    }
}
</style>
</head>

<body>

<nav>
<div class="nav-inner">

<a class="brand"
   href="{{ url_for('home') }}">
KOJA AFRICA
</a>

<div class="nav-links">

<a href="{{ url_for('home') }}">
Home
</a>

<a href="{{ url_for('services') }}">
Services
</a>

<a href="{{ url_for('universities') }}">
Universities
</a>

{% if session.get('user') %}
<a href="{{ url_for('dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('notifications') }}">
Notifications
</a>

<a href="{{ url_for('logout') }}">
Logout
</a>
{% else %}
<a href="{{ url_for('login') }}">
Login
</a>

<a href="{{ url_for('register') }}">
Register
</a>
{% endif %}

{% if session.get('admin') %}
<a href="{{ url_for('admin_dashboard') }}">
Admin
</a>
{% endif %}

</div>
</div>
</nav>

<div class="container">

{% with messages = get_flashed_messages(
with_categories=true) %}

{% for category, message in messages %}

<div class="flash {{ category }}">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</div>

<footer>
KOJA AFRICA —
Knowledge • Questions • Answers
<br>
Academic Assistance • Business Services •
Farmer Services • Professional Services
</footer>

</body>
</html>
"""


def page(content, title="KOJA AFRICA"):
    return render_template_string(
        BASE_HTML,
        content=content,
        title=title,
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    cats = categories()

    html = """
<div class="hero">
<h1>KOJA AFRICA</h1>
<p>
Knowledge • Questions • Answers
</p>
<p style="margin-top:10px">
Academic assistance, assignments, CV services,
farmer registration, TPIN assistance, doctor booking,
lawyer booking, teachers, drivers, delivery and
other professional services.
</p>
</div>

<h2>KOJA Services</h2>

<div class="grid">

{% for c in cats %}

<div class="card service-card">

<div style="font-size:32px">
{{ c.icon or "🛠️" }}
</div>

<h3>
{{ c.name }}
</h3>

<p class="muted">
{{ c.description or "" }}
</p>

<a class="btn"
href="{{ url_for('service_request',
category=c.slug) }}">
Request Service
</a>

</div>

{% endfor %}

</div>

<div class="grid" style="margin-top:20px">

<div class="card">
<h3>🎓 Students</h3>
<p>
Assignments, academic questions,
documents and university information.
</p>
<a class="btn"
href="{{ url_for('service_request',
category='assignments') }}">
Get Academic Help
</a>
</div>

<div class="card">
<h3>🌾 Farmers</h3>
<p>
Get assistance with farmer registration
and agricultural-related services.
</p>
<a class="btn"
href="{{ url_for('service_request',
category='farmer-registration') }}">
Farmer Registration
</a>
</div>

<div class="card">
<h3>💼 Professionals</h3>
<p>
Doctors, lawyers, teachers, tutors and
drivers can register as service providers.
</p>
<a class="btn"
href="{{ url_for('provider_register') }}">
Become a Provider
</a>
</div>

</div>
"""

    return page(
        render_template_string(
            html,
            cats=cats,
        )
    )


# ============================================================
# SERVICES
# ============================================================

@app.route("/services")
def services():

    cats = categories()

    html = """
<h1>KOJA Services</h1>

<div class="grid">

{% for c in cats %}

<div class="card">

<h2>
{{ c.icon or "🛠️" }}
</h2>

<h3>
{{ c.name }}
</h3>

<p>
{{ c.description or "" }}
</p>

<a class="btn"
href="{{ url_for(
'service_request',
category=c.slug
) }}">
Request
</a>

</div>

{% endfor %}

</div>
"""

    return page(
        render_template_string(
            html,
            cats=cats,
        ),
        "Services",
    )


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not email or not password:
            flash(
                "Email and password are required.",
                "danger"
            )
            return redirect(
                url_for("register")
            )

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "danger"
            )
            return redirect(
                url_for("register")
            )

        data, error = auth_signup(
            email,
            password,
        )

        if error:
            flash(
                "Registration failed. "
                "Check the email and password and try again.",
                "danger"
            )
            return redirect(
                url_for("register")
            )

        flash(
            "Account created. If Supabase email confirmation "
            "is enabled, confirm your email before logging in.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    html = """
<div class="card">

<h1>Create KOJA Account</h1>

<form method="post">

<label>Email</label>
<input
    type="email"
    name="email"
    required
>

<label>Password</label>
<input
    type="password"
    name="password"
    minlength="6"
    required
>

<button class="btn">
Create Account
</button>

</form>

<p>
Already have an account?
<a href="{{ url_for('login') }}">
Login
</a>
</p>

</div>
"""

    return page(
        render_template_string(html),
        "Register",
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        data, error = auth_login(
            email,
            password,
        )

        if error or not data:
            flash(
                "Login failed. Check your credentials "
                "or confirm your email.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        user = data.get("user") or {}

        if not user.get("id"):
            flash(
                "Unable to identify the account.",
                "danger"
            )
            return redirect(
                url_for("login")
            )

        session["user"] = {
            "id": user.get("id"),
            "email": user.get("email"),
            "access_token": data.get(
                "access_token"
            ),
        }

        flash(
            "Welcome to KOJA AFRICA.",
            "success"
        )

        return redirect(
            url_for("dashboard")
        )

    html = """
<div class="card">

<h1>Login</h1>

<form method="post">

<label>Email</label>
<input
    type="email"
    name="email"
    required
>

<label>Password</label>
<input
    type="password"
    name="password"
    required
>

<button class="btn">
Login
</button>

</form>

<p>
No account?
<a href="{{ url_for('register') }}">
Create one
</a>
</p>

</div>
"""

    return page(
        render_template_string(html),
        "Login",
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    uid = current_user_id()

    requests_list = get_by_user(
        "service_requests",
        uid,
    )

    notifications_list = supabase_select(
        "notifications",
        {
            "user_id": f"eq.{uid}",
            "is_read": "eq.false",
            "order": "created_at.desc",
            "limit": "10",
        }
    )

    html = """
<div class="hero">
<h1>My KOJA Dashboard</h1>
<p>
{{ session.user.email }}
</p>
</div>

<div class="grid">

<div class="card">
<h3>My Requests</h3>
<div class="stat">
{{ requests_list|length }}
</div>
</div>

<div class="card">
<h3>Unread Notifications</h3>
<div class="stat">
{{ notifications_list|length }}
</div>
</div>

</div>

<div class="card" style="margin-top:20px">

<h2>My Service Requests</h2>

{% if requests_list %}

<div class="table-wrap">

<table>

<tr>
<th>Title</th>
<th>Status</th>
<th>Amount</th>
<th>Created</th>
<th></th>
</tr>

{% for r in requests_list %}

<tr>

<td>
{{ r.title or "Service Request" }}
</td>

<td>
<span class="badge">
{{ r.status }}
</span>
</td>

<td>
{{ r.currency or "ZMW" }}
{{ r.amount or 0 }}
</td>

<td>
{{ r.created_at }}
</td>

<td>
<a class="btn"
href="{{ url_for(
'request_detail',
request_id=r.id
) }}">
View
</a>
</td>

</tr>

{% endfor %}

</table>

</div>

{% else %}

<p class="muted">
You have not submitted a service request yet.
</p>

<a class="btn"
href="{{ url_for('services') }}">
Browse Services
</a>

{% endif %}

</div>
"""

    return page(
        render_template_string(
            html,
            requests_list=requests_list,
            notifications_list=notifications_list,
        ),
        "Dashboard",
    )


# ============================================================
# GENERIC SERVICE REQUEST
# ============================================================

@app.route(
    "/service/<category>",
    methods=["GET", "POST"]
)
@login_required
def service_request(category):

    cats = supabase_select(
        "service_categories",
        {
            "slug": f"eq.{category}",
            "limit": "1",
        }
    )

    if not cats:
        abort(404)

    cat = cats[0]

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        if not title:
            title = cat["name"]

        request_row = supabase_insert(
            "service_requests",
            {
                "user_id": current_user_id(),
                "service_category_id": cat["id"],
                "title": title,
                "description": description,
                "status": "submitted",
                "priority": request.form.get(
                    "priority",
                    "normal"
                ),
                "amount": 0,
                "currency": "ZMW",
                "payment_status": "unpaid",
                "client_notes": request.form.get(
                    "client_notes",
                    ""
                ),
            }
        )

        if not request_row:
            flash(
                "Unable to create your request.",
                "danger"
            )
            return redirect(
                url_for(
                    "service_request",
                    category=category,
                )
            )

        request_id = request_row["id"]

        # ----------------------------------------------------
        # FARMER REGISTRATION
        # ----------------------------------------------------

        if category == "farmer-registration":

            supabase_insert(
                "farmer_profiles",
                {
                    "user_id": current_user_id(),
                    "service_request_id": request_id,
                    "full_name": request.form.get(
                        "full_name"
                    ),
                    "phone": request.form.get(
                        "phone"
                    ),
                    "email": request.form.get(
                        "email"
                    ),
                    "nrc_number": request.form.get(
                        "nrc_number"
                    ),
                    "province": request.form.get(
                        "province"
                    ),
                    "district": request.form.get(
                        "district"
                    ),
                    "chiefdom": request.form.get(
                        "chiefdom"
                    ),
                    "village": request.form.get(
                        "village"
                    ),
                    "farm_name": request.form.get(
                        "farm_name"
                    ),
                    "farm_location": request.form.get(
                        "farm_location"
                    ),
                    "farm_size": request.form.get(
                        "farm_size"
                    ) or None,
                    "farm_size_unit": request.form.get(
                        "farm_size_unit",
                        "hectares"
                    ),
                    "farming_type": request.form.get(
                        "farming_type"
                    ),
                    "crops": request.form.get(
                        "crops"
                    ),
                    "livestock": request.form.get(
                        "livestock"
                    ),
                    "cooperative_name": request.form.get(
                        "cooperative_name"
                    ),
                    "registration_status": "submitted",
                }
            )

        # ----------------------------------------------------
        # TPIN
        # ----------------------------------------------------

        elif category == "tpin":

            supabase_insert(
                "tpin_requests",
                {
                    "user_id": current_user_id(),
                    "service_request_id": request_id,
                    "full_name": request.form.get(
                        "full_name"
                    ),
                    "phone": request.form.get(
                        "phone"
                    ),
                    "email": request.form.get(
                        "email"
                    ),
                    "nrc_number": request.form.get(
                        "nrc_number"
                    ),
                    "business_name": request.form.get(
                        "business_name"
                    ),
                    "business_type": request.form.get(
                        "business_type"
                    ),
                    "province": request.form.get(
                        "province"
                    ),
                    "district": request.form.get(
                        "district"
                    ),
                    "address": request.form.get(
                        "address"
                    ),
                    "request_type": request.form.get(
                        "request_type",
                        "individual"
                    ),
                    "status": "submitted",
                }
            )

        # ----------------------------------------------------
        # CV
        # ----------------------------------------------------

        elif category == "cv-career":

            education = request.form.get(
                "education",
                ""
            )

            experience = request.form.get(
                "experience",
                ""
            )

            skills = request.form.get(
                "skills",
                ""
            )

            certificates = request.form.get(
                "certificates",
                ""
            )

            references_data = request.form.get(
                "references_data",
                ""
            )

            supabase_insert(
                "cv_requests",
                {
                    "user_id": current_user_id(),
                    "service_request_id": request_id,
                    "full_name": request.form.get(
                        "full_name"
                    ),
                    "phone": request.form.get(
                        "phone"
                    ),
                    "email": request.form.get(
                        "email"
                    ),
                    "professional_title":
                        request.form.get(
                            "professional_title"
                        ),
                    "professional_summary":
                        request.form.get(
                            "professional_summary"
                        ),
                    "education": [
                        x.strip()
                        for x in education.split("\n")
                        if x.strip()
                    ],
                    "experience": [
                        x.strip()
                        for x in experience.split("\n")
                        if x.strip()
                    ],
                    "skills": [
                        x.strip()
                        for x in skills.split(",")
                        if x.strip()
                    ],
                    "certificates": [
                        x.strip()
                        for x in certificates.split("\n")
                        if x.strip()
                    ],

                    # IMPORTANT:
                    # Existing KOJA column is
                    # references_data
                    "references_data": [
                        x.strip()
                        for x in references_data.split("\n")
                        if x.strip()
                    ],

                    "target_job": request.form.get(
                        "target_job"
                    ),
                    "template": request.form.get(
                        "template",
                        "professional"
                    ),
                    "status": "submitted",
                }
            )

        # ----------------------------------------------------
        # ASSIGNMENT
        # ----------------------------------------------------

        elif category == "assignments":

            assignment = supabase_insert(
                "assignment_requests",
                {
                    "user_id": current_user_id(),
                    "service_request_id": request_id,
                    "institution": request.form.get(
                        "institution"
                    ),
                    "programme": request.form.get(
                        "programme"
                    ),
                    "course": request.form.get(
                        "course"
                    ),
                    "subject": request.form.get(
                        "subject"
                    ),
                    "class_level": request.form.get(
                        "class_level"
                    ),
                    "assignment_title":
                        request.form.get(
                            "assignment_title"
                        ),
                    "deadline": request.form.get(
                        "deadline"
                    ) or None,

                    # Existing database has BOTH
                    # question_text and question.
                    "question_text": request.form.get(
                        "question_text"
                    ),
                    "question": request.form.get(
                        "question_text"
                    ),

                    "additional_information":
                        request.form.get(
                            "additional_information"
                        ),

                    "lecturer_requirements":
                        request.form.get(
                            "lecturer_requirements"
                        ),

                    "status": "submitted",
                }
            )

            uploaded = request.files.get(
                "assignment_file"
            )

            if assignment and uploaded:
                uploaded_info = upload_to_storage(
                    uploaded,
                    "assignments"
                )

                if uploaded_info:
                    supabase_insert(
                        "service_documents",
                        {
                            "service_request_id":
                                request_id,
                            "user_id":
                                current_user_id(),
                            "file_name":
                                uploaded_info[
                                    "file_name"
                                ],
                            "file_path":
                                uploaded_info[
                                    "path"
                                ],
                            "file_size":
                                uploaded_info[
                                    "file_size"
                                ],
                            "mime_type":
                                uploaded_info[
                                    "mime_type"
                                ],
                            "document_type":
                                "assignment",
                            "uploaded_by":
                                "client",
                        }
                    )

        # ----------------------------------------------------
        # GENERAL UPLOAD
        # ----------------------------------------------------

        uploaded = request.files.get(
            "document"
        )

        if uploaded and uploaded.filename:

            uploaded_info = upload_to_storage(
                uploaded,
                "service-documents"
            )

            if uploaded_info:

                supabase_insert(
                    "service_documents",
                    {
                        "service_request_id":
                            request_id,
                        "user_id":
                            current_user_id(),
                        "file_name":
                            uploaded_info[
                                "file_name"
                            ],
                        "file_path":
                            uploaded_info[
                                "path"
                            ],
                        "file_size":
                            uploaded_info[
                                "file_size"
                            ],
                        "mime_type":
                            uploaded_info[
                                "mime_type"
                            ],
                        "document_type":
                            category,
                        "uploaded_by":
                            "client",
                    }
                )

        create_activity(
            current_user_id(),
            request_id,
            "request_created",
            f"{cat['name']} request submitted.",
            new_status="submitted",
        )

        create_notification(
            current_user_id(),
            "Request Submitted",
            f"Your {cat['name']} request has been received.",
            request_id,
            "service_request",
        )

        flash(
            "Your KOJA service request has been submitted.",
            "success"
        )

        return redirect(
            url_for(
                "request_detail",
                request_id=request_id,
            )
        )

    # --------------------------------------------------------
    # FORM FIELDS
    # --------------------------------------------------------

    if category == "farmer-registration":

        extra = """
<h3>Farmer Information</h3>

<label>Full Name</label>
<input name="full_name" required>

<label>Phone</label>
<input name="phone">

<label>Email</label>
<input type="email" name="email">

<label>NRC Number</label>
<input name="nrc_number">

<label>Province</label>
<input name="province">

<label>District</label>
<input name="district">

<label>Chiefdom</label>
<input name="chiefdom">

<label>Village</label>
<input name="village">

<label>Farm Name</label>
<input name="farm_name">

<label>Farm Location</label>
<input name="farm_location">

<label>Farm Size</label>
<input type="number"
       step="0.01"
       name="farm_size">

<label>Farm Size Unit</label>
<select name="farm_size_unit">
<option value="hectares">Hectares</option>
<option value="acres">Acres</option>
</select>

<label>Farming Type</label>
<input name="farming_type"
       placeholder="Crop farming, livestock, mixed...">

<label>Crops</label>
<textarea name="crops"></textarea>

<label>Livestock</label>
<textarea name="livestock"></textarea>

<label>Cooperative Name</label>
<input name="cooperative_name">
"""

    elif category == "tpin":

        extra = """
<h3>TPIN Information</h3>

<label>Full Name</label>
<input name="full_name" required>

<label>Phone</label>
<input name="phone">

<label>Email</label>
<input type="email" name="email">

<label>NRC Number</label>
<input name="nrc_number">

<label>Request Type</label>
<select name="request_type">
<option value="individual">Individual</option>
<option value="business">Business</option>
<option value="farmer">Farmer</option>
<option value="other">Other</option>
</select>

<label>Business Name</label>
<input name="business_name">

<label>Business Type</label>
<input name="business_type">

<label>Province</label>
<input name="province">

<label>District</label>
<input name="district">

<label>Address</label>
<textarea name="address"></textarea>
"""

    elif category == "cv-career":

        extra = """
<h3>CV Information</h3>

<label>Full Name</label>
<input name="full_name" required>

<label>Phone</label>
<input name="phone">

<label>Email</label>
<input type="email" name="email">

<label>Professional Title</label>
<input name="professional_title"
       placeholder="Teacher, Accountant, Student...">

<label>Professional Summary</label>
<textarea name="professional_summary"></textarea>

<label>Education</label>
<textarea name="education"
placeholder="One qualification per line"></textarea>

<label>Work Experience</label>
<textarea name="experience"
placeholder="One experience per line"></textarea>

<label>Skills</label>
<textarea name="skills"
placeholder="Separate skills with commas"></textarea>

<label>Certificates</label>
<textarea name="certificates"></textarea>

<label>References</label>
<textarea name="references_data"></textarea>

<label>Target Job</label>
<input name="target_job">

<label>CV Template</label>
<select name="template">
<option value="professional">
Professional
</option>
<option value="modern">
Modern
</option>
<option value="simple">
Simple
</option>
</select>
"""

    elif category == "assignments":

        extra = """
<h3>Assignment Information</h3>

<label>Institution</label>
<input name="institution">

<label>Programme</label>
<input name="programme">

<label>Course</label>
<input name="course">

<label>Subject</label>
<input name="subject">

<label>Class Level</label>
<input name="class_level">

<label>Assignment Title</label>
<input name="assignment_title"
       required>

<label>Deadline</label>
<input type="date"
       name="deadline">

<label>Question</label>
<textarea name="question_text"
required></textarea>

<label>Lecturer Requirements</label>
<textarea name="lecturer_requirements"></textarea>

<label>Additional Information</label>
<textarea name="additional_information"></textarea>

<label>Assignment File</label>
<input type="file"
       name="assignment_file">

<p class="muted">
Maximum file size: 10 MB.
</p>
"""

    else:

        extra = """
<label>Document</label>
<input type="file"
       name="document">

<p class="muted">
You may attach a supporting document.
Maximum file size: 10 MB.
</p>
"""

    html = """
<div class="card">

<h1>
{{ cat.icon or "🛠️" }}
{{ cat.name }}
</h1>

<p class="muted">
{{ cat.description or "" }}
</p>

<form method="post"
      enctype="multipart/form-data">

<label>Request Title</label>

<input name="title"
       value="{{ cat.name }}"
       required>

<label>Description</label>

<textarea name="description"
placeholder="Explain what you need KOJA to help you with."
></textarea>

<label>Priority</label>

<select name="priority">

<option value="normal">
Normal
</option>

<option value="low">
Low
</option>

<option value="high">
High
</option>

<option value="urgent">
Urgent
</option>

</select>

{{ extra|safe }}

<label>Additional Client Notes</label>

<textarea name="client_notes"></textarea>

<button class="btn">
Submit Request
</button>

</form>

</div>
"""

    return page(
        render_template_string(
            html,
            cat=cat,
            extra=extra,
        ),
        cat["name"],
    )


# ============================================================
# REQUEST DETAIL
# ============================================================

@app.route(
    "/request/<request_id>",
    methods=["GET", "POST"]
)
@login_required
def request_detail(request_id):

    row = get_one(
        "service_requests",
        request_id,
    )

    if not row:
        abort(404)

    if (
        row.get("user_id")
        != current_user_id()
    ):
        abort(403)

    if request.method == "POST":

        message = request.form.get(
            "message",
            ""
        ).strip()

        if message:

            create_comment(
                request_id,
                message,
                "client",
                current_user_id(),
            )

            create_activity(
                current_user_id(),
                request_id,
                "comment_added",
                "Client added a comment.",
            )

            flash(
                "Message sent.",
                "success"
            )

        return redirect(
            url_for(
                "request_detail",
                request_id=request_id,
            )
        )

    comments = supabase_select(
        "service_comments",
        {
            "service_request_id":
                f"eq.{request_id}",
            "order":
                "created_at.asc",
        }
    )

    documents = supabase_select(
        "service_documents",
        {
            "service_request_id":
                f"eq.{request_id}",
            "order":
                "created_at.desc",
        }
    )

    html = """
<div class="card">

<h1>
{{ row.title }}
</h1>

<p>
Status:
<span class="badge">
{{ row.status }}
</span>
</p>

<p>
Priority:
<strong>
{{ row.priority }}
</strong>
</p>

<p>
Amount:
<strong>
{{ row.currency or "ZMW" }}
{{ row.amount or 0 }}
</strong>
</p>

<p>
Payment:
<span class="badge">
{{ row.payment_status }}
</span>
</p>

<h3>Description</h3>

<p>
{{ row.description or "No description." }}
</p>

{% if row.admin_notes %}

<h3>Administrator Notes</h3>

<p>
{{ row.admin_notes }}
</p>

{% endif %}

</div>


<div class="card"
style="margin-top:18px">

<h2>Documents</h2>

{% if documents %}

<ul>

{% for d in documents %}

<li>
{{ d.file_name }}

{% if d.file_path %}

<a class="btn"
href="{{ url_for(
'download_service_document',
document_id=d.id
) }}">
Open
</a>

{% endif %}

</li>

{% endfor %}

</ul>

{% else %}

<p class="muted">
No documents attached.
</p>

{% endif %}

</div>


<div class="card"
style="margin-top:18px">

<h2>Communication</h2>

{% for c in comments %}

<div style="
padding:10px;
border-bottom:1px solid #ddd;
">

<strong>
{{ c.sender_type|capitalize }}
</strong>

<span class="muted">
{{ c.created_at }}
</span>

<p>
{{ c.message }}
</p>

</div>

{% endfor %}

<form method="post">

<label>Send Message</label>

<textarea name="message"
required></textarea>

<button class="btn">
Send
</button>

</form>

</div>
"""

    return page(
        render_template_string(
            html,
            row=row,
            comments=comments,
            documents=documents,
        ),
        "Service Request",
    )


# ============================================================
# DOCUMENT DOWNLOAD
# ============================================================

@app.route(
    "/document/<document_id>/download"
)
@login_required
def download_service_document(document_id):

    document = get_one(
        "service_documents",
        document_id,
    )

    if not document:
        abort(404)

    request_row = get_one(
        "service_requests",
        document.get("service_request_id"),
    )

    if not request_row:
        abort(404)

    if (
        request_row.get("user_id")
        != current_user_id()
        and not session.get("admin")
    ):
        abort(403)

    signed = create_signed_url(
        document.get("file_path"),
        3600,
    )

    if not signed:
        flash(
            "Unable to create document link.",
            "danger"
        )
        return redirect(
            request.referrer
            or url_for("dashboard")
        )

    return redirect(signed)


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@login_required
def notifications():

    rows = supabase_select(
        "notifications",
        {
            "user_id":
                f"eq.{current_user_id()}",
            "order":
                "created_at.desc",
        }
    )

    for row in rows:
        if not row.get("is_read"):
            supabase_update(
                "notifications",
                {
                    "id":
                        f"eq.{row['id']}"
                },
                {
                    "is_read": True
                }
            )

    html = """
<div class="card">

<h1>Notifications</h1>

{% if rows %}

{% for n in rows %}

<div style="
padding:14px;
border-bottom:1px solid #ddd;
">

<h3>
{{ n.title }}
</h3>

<p>
{{ n.message }}
</p>

<span class="muted">
{{ n.created_at }}
</span>

</div>

{% endfor %}

{% else %}

<p class="muted">
No notifications.
</p>

{% endif %}

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
        ),
        "Notifications",
    )


# ============================================================
# PROVIDER REGISTRATION
# ============================================================

@app.route(
    "/provider/register",
    methods=["GET", "POST"]
)
@login_required
def provider_register():

    existing = supabase_select(
        "service_providers",
        {
            "user_id":
                f"eq.{current_user_id()}",
            "limit":
                "1",
        }
    )

    if existing:
        flash(
            "You already have a provider profile.",
            "warning"
        )
        return redirect(
            url_for("provider_dashboard")
        )

    if request.method == "POST":

        provider_type = request.form.get(
            "provider_type"
        )

        provider = supabase_insert(
            "service_providers",
            {
                "user_id":
                    current_user_id(),

                "provider_type":
                    provider_type,

                "full_name":
                    request.form.get(
                        "full_name"
                    ),

                "phone":
                    request.form.get(
                        "phone"
                    ),

                "email":
                    request.form.get(
                        "email"
                    ),

                "province":
                    request.form.get(
                        "province"
                    ),

                "district":
                    request.form.get(
                        "district"
                    ),

                "address":
                    request.form.get(
                        "address"
                    ),

                "qualification":
                    request.form.get(
                        "qualification"
                    ),

                "experience":
                    request.form.get(
                        "experience"
                    ),

                "license_number":
                    request.form.get(
                        "license_number"
                    ),

                "bio":
                    request.form.get(
                        "bio"
                    ),

                "verification_status":
                    "pending",

                "is_available":
                    True,

                "is_active":
                    True,
            }
        )

        if not provider:
            flash(
                "Unable to register provider.",
                "danger"
            )
            return redirect(
                url_for(
                    "provider_register"
                )
            )

        # Provider-specific profile
        if provider_type == "doctor":

            supabase_insert(
                "doctor_profiles",
                {
                    "provider_id":
                        provider["id"],

                    "specialty":
                        request.form.get(
                            "specialty"
                        ),

                    "hospital_clinic":
                        request.form.get(
                            "hospital_clinic"
                        ),

                    "registration_number":
                        request.form.get(
                            "registration_number"
                        ),

                    "consultation_fee":
                        request.form.get(
                            "consultation_fee"
                        ) or 0,

                    "consultation_type":
                        request.form.get(
                            "consultation_type",
                            "in_person"
                        ),
                }
            )

        elif provider_type == "lawyer":

            supabase_insert(
                "lawyer_profiles",
                {
                    "provider_id":
                        provider["id"],

                    "practice_area":
                        request.form.get(
                            "practice_area"
                        ),

                    "law_firm":
                        request.form.get(
                            "law_firm"
                        ),

                    "license_number":
                        request.form.get(
                            "license_number"
                        ),

                    "consultation_fee":
                        request.form.get(
                            "consultation_fee"
                        ) or 0,

                    "consultation_type":
                        request.form.get(
                            "consultation_type",
                            "in_person"
                        ),
                }
            )

        elif provider_type == "teacher":

            supabase_insert(
                "teacher_profiles",
                {
                    "provider_id":
                        provider["id"],

                    "subjects":
                        request.form.get(
                            "subjects"
                        ),

                    "grade_levels":
                        request.form.get(
                            "grade_levels"
                        ),

                    "qualification":
                        request.form.get(
                            "qualification"
                        ),

                    "teaching_experience":
                        request.form.get(
                            "teaching_experience"
                        ),

                    "hourly_rate":
                        request.form.get(
                            "hourly_rate"
                        ) or 0,

                    "teaching_mode":
                        request.form.get(
                            "teaching_mode",
                            "both"
                        ),
                }
            )

        elif provider_type == "driver":

            supabase_insert(
                "driver_profiles",
                {
                    "provider_id":
                        provider["id"],

                    "vehicle_type":
                        request.form.get(
                            "vehicle_type"
                        ),

                    "vehicle_make":
                        request.form.get(
                            "vehicle_make"
                        ),

                    "vehicle_model":
                        request.form.get(
                            "vehicle_model"
                        ),

                    "vehicle_registration":
                        request.form.get(
                            "vehicle_registration"
                        ),

                    "driving_license_number":
                        request.form.get(
                            "driving_license_number"
                        ),

                    "service_area":
                        request.form.get(
                            "service_area"
                        ),

                    "verification_status":
                        "pending",
                }
            )

        flash(
            "Provider application submitted. "
            "An administrator must verify your account.",
            "success"
        )

        return redirect(
            url_for("provider_dashboard")
        )

    html = """
<div class="card">

<h1>Become a KOJA Service Provider</h1>

<form method="post">

<label>Provider Type</label>

<select name="provider_type"
id="provider_type"
required
onchange="showTypeFields()">

<option value="doctor">
Doctor
</option>

<option value="lawyer">
Lawyer
</option>

<option value="teacher">
Teacher / Tutor
</option>

<option value="driver">
Driver / Delivery
</option>

<option value="academic">
Academic Provider
</option>

<option value="other">
Other
</option>

</select>

<label>Full Name</label>
<input name="full_name" required>

<label>Phone</label>
<input name="phone">

<label>Email</label>
<input type="email" name="email">

<label>Province</label>
<input name="province">

<label>District</label>
<input name="district">

<label>Address</label>
<textarea name="address"></textarea>

<label>Qualification</label>
<input name="qualification">

<label>Experience</label>
<textarea name="experience"></textarea>

<label>License / Registration Number</label>
<input name="license_number">

<label>Professional Bio</label>
<textarea name="bio"></textarea>

<div id="doctorFields">

<h3>Doctor Details</h3>

<label>Specialty</label>
<input name="specialty">

<label>Hospital / Clinic</label>
<input name="hospital_clinic">

<label>Medical Registration Number</label>
<input name="registration_number">

<label>Consultation Fee (ZMW)</label>
<input type="number"
step="0.01"
name="consultation_fee">

<label>Consultation Type</label>
<select name="consultation_type">
<option value="in_person">
In person
</option>
<option value="online">
Online
</option>
<option value="both">
Both
</option>
</select>

</div>

<div id="lawyerFields">

<h3>Lawyer Details</h3>

<label>Practice Area</label>
<input name="practice_area">

<label>Law Firm</label>
<input name="law_firm">

</div>

<div id="teacherFields">

<h3>Teacher / Tutor Details</h3>

<label>Subjects</label>
<input name="subjects">

<label>Grade Levels</label>
<input name="grade_levels">

<label>Teaching Qualification</label>
<input name="teaching_qualification">

<label>Teaching Experience</label>
<input name="teaching_experience">

<label>Hourly Rate (ZMW)</label>
<input type="number"
step="0.01"
name="hourly_rate">

<label>Teaching Mode</label>
<select name="teaching_mode">
<option value="online">Online</option>
<option value="physical">Physical</option>
<option value="both">Both</option>
</select>

</div>

<div id="driverFields">

<h3>Driver Details</h3>

<label>Vehicle Type</label>
<input name="vehicle_type">

<label>Vehicle Make</label>
<input name="vehicle_make">

<label>Vehicle Model</label>
<input name="vehicle_model">

<label>Vehicle Registration</label>
<input name="vehicle_registration">

<label>Driving License Number</label>
<input name="driving_license_number">

<label>Service Area</label>
<input name="service_area">

</div>

<button class="btn">
Submit Provider Application
</button>

</form>

</div>

<script>

function showTypeFields() {

    const type =
        document.getElementById(
            "provider_type"
        ).value;

    document.getElementById(
        "doctorFields"
    ).style.display =
        type === "doctor"
        ? "block"
        : "none";

    document.getElementById(
        "lawyerFields"
    ).style.display =
        type === "lawyer"
        ? "block"
        : "none";

    document.getElementById(
        "teacherFields"
    ).style.display =
        type === "teacher"
        ? "block"
        : "none";

    document.getElementById(
        "driverFields"
    ).style.display =
        type === "driver"
        ? "block"
        : "none";
}

showTypeFields();

</script>
"""

    return page(
        render_template_string(html),
        "Provider Registration",
    )


# ============================================================
# PROVIDER DASHBOARD
# ============================================================

@app.route("/provider")
@provider_required
def provider_dashboard():

    providers = supabase_select(
        "service_providers",
        {
            "user_id":
                f"eq.{current_user_id()}",
            "limit":
                "1",
        }
    )

    provider = providers[0]

    assigned = supabase_select(
        "service_requests",
        {
            "assigned_provider_id":
                f"eq.{provider['id']}",
            "order":
                "created_at.desc",
        }
    )

    html = """
<div class="hero">
<h1>Provider Dashboard</h1>

<p>
{{ provider.full_name }}
—
{{ provider.provider_type }}
</p>

<p>
Verification:
<strong>
{{ provider.verification_status }}
</strong>
</p>

</div>

<div class="card">

<h2>Assigned Requests</h2>

{% if assigned %}

<div class="table-wrap">

<table>

<tr>
<th>Request</th>
<th>Status</th>
<th>Action</th>
</tr>

{% for r in assigned %}

<tr>

<td>
{{ r.title }}
</td>

<td>
{{ r.status }}
</td>

<td>
<a class="btn"
href="{{ url_for(
'provider_request',
request_id=r.id
) }}">
Open
</a>
</td>

</tr>

{% endfor %}

</table>

</div>

{% else %}

<p class="muted">
No requests have been assigned to you.
</p>

{% endif %}

</div>
"""

    return page(
        render_template_string(
            html,
            provider=provider,
            assigned=assigned,
        ),
        "Provider Dashboard",
    )


# ============================================================
# PROVIDER REQUEST
# ============================================================

@app.route(
    "/provider/request/<request_id>",
    methods=["GET", "POST"]
)
@provider_required
def provider_request(request_id):

    providers = supabase_select(
        "service_providers",
        {
            "user_id":
                f"eq.{current_user_id()}",
            "limit":
                "1",
        }
    )

    provider = providers[0]

    row = get_one(
        "service_requests",
        request_id,
    )

    if not row:
        abort(404)

    if (
        row.get("assigned_provider_id")
        != provider["id"]
    ):
        abort(403)

    if request.method == "POST":

        status = request.form.get(
            "status"
        )

        allowed = {
            "accepted",
            "in_progress",
            "scheduled",
            "completed",
            "cancelled",
        }

        if status not in allowed:
            flash(
                "Invalid status.",
                "danger"
            )
            return redirect(
                request.url
            )

        old_status = row.get("status")

        payload = {
            "status": status
        }

        if status == "completed":
            payload["completed_at"] = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

        supabase_update(
            "service_requests",
            {
                "id":
                    f"eq.{request_id}"
            },
            payload,
        )

        create_activity(
            current_user_id(),
            request_id,
            "provider_status_update",
            "Provider updated service request.",
            old_status,
            status,
        )

        if row.get("user_id"):

            create_notification(
                row["user_id"],
                "Service Request Updated",
                f"Your request is now: {status}.",
                request_id,
                "service_request",
            )

        flash(
            "Request updated.",
            "success"
        )

        return redirect(
            request.url
        )

    html = """
<div class="card">

<h1>
{{ row.title }}
</h1>

<p>
{{ row.description }}
</p>

<p>
Current status:
<strong>
{{ row.status }}
</strong>
</p>

<form method="post">

<label>Update Status</label>

<select name="status">

<option value="accepted">
Accepted
</option>

<option value="in_progress">
In Progress
</option>

<option value="scheduled">
Scheduled
</option>

<option value="completed">
Completed
</option>

<option value="cancelled">
Cancelled
</option>

</select>

<button class="btn">
Update
</button>

</form>

</div>
"""

    return page(
        render_template_string(
            html,
            row=row,
        ),
        "Provider Request",
    )


# ============================================================
# DOCTOR / LAWYER / TEACHER / DRIVER DIRECTORY
# ============================================================

@app.route("/providers/<provider_type>")
def provider_directory(provider_type):

    allowed = {
        "doctor",
        "lawyer",
        "teacher",
        "driver",
        "academic",
        "other",
    }

    if provider_type not in allowed:
        abort(404)

    providers = supabase_select(
        "service_providers",
        {
            "provider_type":
                f"eq.{provider_type}",
            "verification_status":
                "eq.verified",
            "is_active":
                "eq.true",
            "is_available":
                "eq.true",
            "order":
                "full_name.asc",
        }
    )

    html = """
<div class="hero">
<h1>
{{ provider_type|capitalize }} Services
</h1>

<p>
Verified KOJA service providers
</p>
</div>

<div class="grid">

{% for p in providers %}

<div class="card">

<h2>
{{ p.full_name }}
</h2>

<p>
<strong>
{{ p.provider_type|capitalize }}
</strong>
</p>

<p>
{{ p.qualification or "" }}
</p>

<p>
{{ p.experience or "" }}
</p>

<p>
{{ p.province or "" }}
{{ p.district or "" }}
</p>

<a class="btn"
href="{{ url_for(
'provider_profile',
provider_id=p.id
) }}">
View Profile
</a>

</div>

{% else %}

<div class="card">

<p>
No verified providers are currently available.
</p>

</div>

{% endfor %}

</div>
"""

    return page(
        render_template_string(
            html,
            providers=providers,
            provider_type=provider_type,
        ),
        "Providers",
    )


# ============================================================
# PROVIDER PROFILE
# ============================================================

@app.route(
    "/provider/profile/<provider_id>"
)
def provider_profile(provider_id):

    provider = get_one(
        "service_providers",
        provider_id,
    )

    if not provider:
        abort(404)

    if provider.get(
        "verification_status"
    ) != "verified":
        abort(404)

    doctor = []
    lawyer = []
    teacher = []
    driver = []

    if provider["provider_type"] == "doctor":

        doctor = supabase_select(
            "doctor_profiles",
            {
                "provider_id":
                    f"eq.{provider_id}",
                "limit":
                    "1",
            }
        )

    elif provider["provider_type"] == "lawyer":

        lawyer = supabase_select(
            "lawyer_profiles",
            {
                "provider_id":
                    f"eq.{provider_id}",
                "limit":
                    "1",
            }
        )

    elif provider["provider_type"] == "teacher":

        teacher = supabase_select(
            "teacher_profiles",
            {
                "provider_id":
                    f"eq.{provider_id}",
                "limit":
                    "1",
            }
        )

    elif provider["provider_type"] == "driver":

        driver = supabase_select(
            "driver_profiles",
            {
                "provider_id":
                    f"eq.{provider_id}",
                "limit":
                    "1",
            }
        )

    html = """
<div class="card">

<h1>
{{ provider.full_name }}
</h1>

<p>
{{ provider.bio or "" }}
</p>

<p>
<strong>Type:</strong>
{{ provider.provider_type }}
</p>

<p>
<strong>Qualification:</strong>
{{ provider.qualification or "Not provided" }}
</p>

<p>
<strong>Experience:</strong>
{{ provider.experience or "Not provided" }}
</p>

<p>
<strong>Location:</strong>
{{ provider.province or "" }},
{{ provider.district or "" }}
</p>

{% if doctor %}

<h3>Doctor Details</h3>

<p>
Specialty:
{{ doctor[0].specialty }}
</p>

<p>
Hospital / Clinic:
{{ doctor[0].hospital_clinic }}
</p>

<p>
Consultation Fee:
ZMW {{ doctor[0].consultation_fee }}
</p>

{% endif %}

{% if lawyer %}

<h3>Lawyer Details</h3>

<p>
Practice Area:
{{ lawyer[0].practice_area }}
</p>

<p>
Law Firm:
{{ lawyer[0].law_firm }}
</p>

<p>
Consultation Fee:
ZMW {{ lawyer[0].consultation_fee }}
</p>

{% endif %}

{% if teacher %}

<h3>Teacher / Tutor Details</h3>

<p>
Subjects:
{{ teacher[0].subjects }}
</p>

<p>
Grade Levels:
{{ teacher[0].grade_levels }}
</p>

<p>
Hourly Rate:
ZMW {{ teacher[0].hourly_rate }}
</p>

{% endif %}

{% if driver %}

<h3>Driver Details</h3>

<p>
Vehicle:
{{ driver[0].vehicle_type }}
{{ driver[0].vehicle_make }}
{{ driver[0].vehicle_model }}
</p>

<p>
Service Area:
{{ driver[0].service_area }}
</p>

{% endif %}

{% if session.get('user') %}

<a class="btn"
href="{{ url_for(
'service_request',
category=(
'doctor-booking'
if provider.provider_type == 'doctor'
else
'lawyer-booking'
if provider.provider_type == 'lawyer'
else
'teacher-tutor'
if provider.provider_type == 'teacher'
else
'driver-delivery'
)
) }}">
Request Service
</a>

{% else %}

<a class="btn"
href="{{ url_for('login') }}">
Login to Request
</a>

{% endif %}

</div>
"""

    return page(
        render_template_string(
            html,
            provider=provider,
            doctor=doctor,
            lawyer=lawyer,
            teacher=teacher,
            driver=driver,
        ),
        provider["full_name"],
    )


# ============================================================
# APPOINTMENT BOOKING
# ============================================================

@app.route(
    "/appointment/<provider_id>",
    methods=["GET", "POST"]
)
@login_required
def appointment_booking(provider_id):

    provider = get_one(
        "service_providers",
        provider_id,
    )

    if not provider:
        abort(404)

    if request.method == "POST":

        category_slug = (
            "doctor-booking"
            if provider["provider_type"]
            == "doctor"
            else "lawyer-booking"
        )

        cats = supabase_select(
            "service_categories",
            {
                "slug":
                    f"eq.{category_slug}",
                "limit":
                    "1",
            }
        )

        if not cats:
            flash(
                "Service category is not configured.",
                "danger"
            )
            return redirect(
                request.url
            )

        service_request = supabase_insert(
            "service_requests",
            {
                "user_id":
                    current_user_id(),
                "service_category_id":
                    cats[0]["id"],
                "title":
                    f"Appointment with "
                    f"{provider['full_name']}",
                "description":
                    request.form.get(
                        "notes"
                    ),
                "status":
                    "scheduled",
                "priority":
                    "normal",
                "amount":
                    request.form.get(
                        "amount"
                    ) or 0,
                "currency":
                    "ZMW",
                "payment_status":
                    "unpaid",
            }
        )

        if not service_request:
            flash(
                "Unable to create appointment request.",
                "danger"
            )
            return redirect(
                request.url
            )

        appointment = supabase_insert(
            "appointments",
            {
                "service_request_id":
                    service_request["id"],
                "client_id":
                    current_user_id(),
                "provider_id":
                    provider_id,
                "appointment_type":
                    request.form.get(
                        "appointment_type"
                    ),
                "appointment_date":
                    request.form.get(
                        "appointment_date"
                    ),
                "start_time":
                    request.form.get(
                        "start_time"
                    ),
                "end_time":
                    request.form.get(
                        "end_time"
                    ),
                "location":
                    request.form.get(
                        "location"
                    ),
                "meeting_link":
                    request.form.get(
                        "meeting_link"
                    ),
                "status":
                    "pending",
                "notes":
                    request.form.get(
                        "notes"
                    ),
            }
        )

        if appointment:

            supabase_update(
                "service_requests",
                {
                    "id":
                        f"eq.{service_request['id']}"
                },
                {
                    "assigned_provider_id":
                        provider_id
                }
            )

            create_notification(
                current_user_id(),
                "Appointment Requested",
                f"Your appointment request "
                f"with {provider['full_name']} "
                f"has been submitted.",
                service_request["id"],
                "appointment",
            )

            flash(
                "Appointment request submitted.",
                "success"
            )

            return redirect(
                url_for(
                    "request_detail",
                    request_id=
                        service_request["id"]
                )
            )

    html = """
<div class="card">

<h1>
Book Appointment
</h1>

<h2>
{{ provider.full_name }}
</h2>

<p>
{{ provider.provider_type }}
</p>

<form method="post">

<label>Appointment Type</label>
<select name="appointment_type">
<option value="in_person">
In Person
</option>
<option value="online">
Online
</option>
<option value="consultation">
Consultation
</option>
</select>

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
<input name="location">

<label>Meeting Link</label>
<input name="meeting_link">

<label>Amount (ZMW)</label>
<input type="number"
step="0.01"
name="amount"
value="0">

<label>Notes</label>
<textarea name="notes"></textarea>

<button class="btn">
Request Appointment
</button>

</form>

</div>
"""

    return page(
        render_template_string(
            html,
            provider=provider,
        ),
        "Book Appointment",
    )


# ============================================================
# DELIVERY
# ============================================================

@app.route(
    "/delivery",
    methods=["GET", "POST"]
)
@login_required
def delivery_request():

    if request.method == "POST":

        cats = supabase_select(
            "service_categories",
            {
                "slug":
                    "eq.driver-delivery",
                "limit":
                    "1",
            }
        )

        if not cats:
            flash(
                "Delivery service is not configured.",
                "danger"
            )
            return redirect(
                request.url
            )

        service_request = supabase_insert(
            "service_requests",
            {
                "user_id":
                    current_user_id(),

                "service_category_id":
                    cats[0]["id"],

                "title":
                    "Delivery Request",

                "description":
                    request.form.get(
                        "package_description"
                    ),

                "status":
                    "submitted",

                "priority":
                    request.form.get(
                        "priority",
                        "normal"
                    ),

                "amount":
                    request.form.get(
                        "delivery_fee"
                    ) or 0,

                "currency":
                    "ZMW",

                "payment_status":
                    "unpaid",
            }
        )

        if not service_request:
            flash(
                "Unable to create delivery request.",
                "danger"
            )
            return redirect(
                request.url
            )

        delivery = supabase_insert(
            "deliveries",
            {
                "service_request_id":
                    service_request["id"],

                "customer_id":
                    current_user_id(),

                "pickup_location":
                    request.form.get(
                        "pickup_location"
                    ),

                "destination":
                    request.form.get(
                        "destination"
                    ),

                "recipient_name":
                    request.form.get(
                        "recipient_name"
                    ),

                "recipient_phone":
                    request.form.get(
                        "recipient_phone"
                    ),

                "package_description":
                    request.form.get(
                        "package_description"
                    ),

                "package_weight":
                    request.form.get(
                        "package_weight"
                    ) or None,

                "delivery_fee":
                    request.form.get(
                        "delivery_fee"
                    ) or 0,

                "currency":
                    "ZMW",

                "requested_date":
                    request.form.get(
                        "requested_date"
                    ),

                "requested_time":
                    request.form.get(
                        "requested_time"
                    ),

                "status":
                    "requested",
            }
        )

        if delivery:

            flash(
                "Delivery request submitted.",
                "success"
            )

            return redirect(
                url_for(
                    "delivery_tracking",
                    tracking_code=
                        delivery.get(
                            "tracking_code"
                        ),
                )
            )

    html = """
<div class="card">

<h1>🚚 Request Delivery</h1>

<form method="post">

<label>Pickup Location</label>
<input name="pickup_location"
required>

<label>Destination</label>
<input name="destination"
required>

<label>Recipient Name</label>
<input name="recipient_name">

<label>Recipient Phone</label>
<input name="recipient_phone">

<label>Package Description</label>
<textarea name="package_description"></textarea>

<label>Package Weight</label>
<input type="number"
step="0.01"
name="package_weight">

<label>Delivery Fee (ZMW)</label>
<input type="number"
step="0.01"
name="delivery_fee"
value="0">

<label>Requested Date</label>
<input type="date"
name="requested_date">

<label>Requested Time</label>
<input type="time"
name="requested_time">

<label>Priority</label>
<select name="priority">
<option value="normal">
Normal
</option>
<option value="high">
High
</option>
<option value="urgent">
Urgent
</option>
</select>

<button class="btn">
Request Delivery
</button>

</form>

</div>
"""

    return page(
        render_template_string(html),
        "Delivery",
    )


# ============================================================
# DELIVERY TRACKING
# ============================================================

@app.route(
    "/delivery/track/<tracking_code>"
)
def delivery_tracking(tracking_code):

    rows = supabase_select(
        "deliveries",
        {
            "tracking_code":
                f"eq.{tracking_code}",
            "limit":
                "1",
        }
    )

    if not rows:
        abort(404)

    delivery = rows[0]

    html = """
<div class="card">

<h1>Delivery Tracking</h1>

<h2>
{{ delivery.tracking_code }}
</h2>

<p>
Status:
<span class="badge">
{{ delivery.status }}
</span>
</p>

<p>
From:
<strong>
{{ delivery.pickup_location }}
</strong>
</p>

<p>
To:
<strong>
{{ delivery.destination }}
</strong>
</p>

<p>
Recipient:
{{ delivery.recipient_name or "" }}
</p>

<p>
Requested:
{{ delivery.requested_date or "" }}
{{ delivery.requested_time or "" }}
</p>

{% if delivery.delivered_at %}

<p>
Delivered:
{{ delivery.delivered_at }}
</p>

{% endif %}

</div>
"""

    return page(
        render_template_string(
            html,
            delivery=delivery,
        ),
        "Delivery Tracking",
    )


# ============================================================
# CV PDF GENERATION
# ============================================================

def generate_cv_pdf(cv):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CVTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=20,
        spaceAfter=10,
    )

    heading = ParagraphStyle(
        "CVHeading",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=12,
        spaceAfter=7,
    )

    normal = styles["BodyText"]

    story = []

    story.append(
        Paragraph(
            cv.get("full_name")
            or "KOJA Applicant",
            title_style,
        )
    )

    contact = []

    if cv.get("phone"):
        contact.append(
            cv["phone"]
        )

    if cv.get("email"):
        contact.append(
            cv["email"]
        )

    if contact:
        story.append(
            Paragraph(
                " | ".join(contact),
                normal,
            )
        )

    story.append(
        Spacer(1, 12)
    )

    if cv.get("professional_title"):
        story.append(
            Paragraph(
                cv["professional_title"],
                heading,
            )
        )

    if cv.get("professional_summary"):
        story.append(
            Paragraph(
                cv["professional_summary"],
                normal,
            )
        )

    def json_items(value):
        if not value:
            return []

        if isinstance(value, list):
            return value

        if isinstance(value, str):

            try:
                decoded = json.loads(value)

                if isinstance(decoded, list):
                    return decoded

            except Exception:
                pass

            return [
                x.strip()
                for x in value.split("\n")
                if x.strip()
            ]

        return []

    sections = [
        (
            "Education",
            cv.get("education")
        ),
        (
            "Professional Experience",
            cv.get("experience")
        ),
        (
            "Skills",
            cv.get("skills")
        ),
        (
            "Certificates",
            cv.get("certificates")
        ),
        (
            "References",
            cv.get("references_data")
        ),
    ]

    for heading_text, value in sections:

        items = json_items(value)

        if not items:
            continue

        story.append(
            Paragraph(
                heading_text,
                heading,
            )
        )

        for item in items:

            if isinstance(item, dict):
                item = " — ".join(
                    f"{k}: {v}"
                    for k, v in item.items()
                )

            story.append(
                Paragraph(
                    "• " + str(item),
                    normal,
                )
            )

            story.append(
                Spacer(1, 3)
            )

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            "Prepared by KOJA AFRICA",
            normal,
        )
    )

    doc.build(story)

    buffer.seek(0)

    return buffer


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if (
            email == ADMIN_EMAIL.lower()
            and check_password_hash(
                generate_password_hash(
                    ADMIN_PASSWORD
                ),
                password,
            )
        ):
            session["admin"] = True
            session["admin_email"] = email

            flash(
                "Administrator login successful.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        # Also allow direct comparison
        # for simple Render environment setup.
        if (
            email == ADMIN_EMAIL.lower()
            and secrets.compare_digest(
                password,
                ADMIN_PASSWORD,
            )
        ):

            session["admin"] = True
            session["admin_email"] = email

            flash(
                "Administrator login successful.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        flash(
            "Invalid administrator credentials.",
            "danger"
        )

    html = """
<div class="card">

<h1>KOJA Administrator</h1>

<form method="post">

<label>Admin Email</label>
<input type="email"
name="email"
required>

<label>Admin Password</label>
<input type="password"
name="password"
required>

<button class="btn">
Login
</button>

</form>

</div>
"""

    return page(
        render_template_string(html),
        "Admin Login",
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop("admin", None)
    session.pop("admin_email", None)

    flash(
        "Administrator logged out.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    requests_list = supabase_select(
        "service_requests",
        {
            "order":
                "created_at.desc",
            "limit":
                "100",
        }
    )

    providers = supabase_select(
        "service_providers",
        {
            "order":
                "created_at.desc",
            "limit":
                "100",
        }
    )

    farmers = supabase_select(
        "farmer_profiles",
        {
            "order":
                "created_at.desc",
            "limit":
                "100",
        }
    )

    tpin = supabase_select(
        "tpin_requests",
        {
            "order":
                "created_at.desc",
            "limit":
                "100",
        }
    )

    cvs = supabase_select(
        "cv_requests",
        {
            "order":
                "created_at.desc",
            "limit":
                "100",
        }
    )

    assignments = supabase_select(
        "assignment_requests",
        {
            "order":
                "created_at.desc",
            "limit":
                "100",
        }
    )

    appointments = supabase_select(
        "appointments",
        {
            "order":
                "created_at.desc",
            "limit":
                "100",
        }
    )

    deliveries = supabase_select(
        "deliveries",
        {
            "order":
                "created_at.desc",
            "limit":
                "100",
        }
    )

    html = """
<div class="hero">

<h1>KOJA AFRICA ADMIN</h1>

<p>
Manage clients, services, providers,
assignments, CVs, farmers, TPIN requests,
appointments and deliveries.
</p>

<a class="btn"
href="{{ url_for('admin_logout') }}">
Admin Logout
</a>

</div>


<div class="grid">

<div class="card">
<h3>Service Requests</h3>
<div class="stat">
{{ requests_list|length }}
</div>
</div>

<div class="card">
<h3>Providers</h3>
<div class="stat">
{{ providers|length }}
</div>
</div>

<div class="card">
<h3>Farmers</h3>
<div class="stat">
{{ farmers|length }}
</div>
</div>

<div class="card">
<h3>TPIN</h3>
<div class="stat">
{{ tpin|length }}
</div>
</div>

<div class="card">
<h3>CV Requests</h3>
<div class="stat">
{{ cvs|length }}
</div>
</div>

<div class="card">
<h3>Assignments</h3>
<div class="stat">
{{ assignments|length }}
</div>
</div>

<div class="card">
<h3>Appointments</h3>
<div class="stat">
{{ appointments|length }}
</div>
</div>

<div class="card">
<h3>Deliveries</h3>
<div class="stat">
{{ deliveries|length }}
</div>
</div>

</div>


<div class="grid"
style="margin-top:20px">

<div class="card">

<h3>Manage Requests</h3>

<a class="btn"
href="{{ url_for(
'admin_requests'
) }}">
Open
</a>

</div>

<div class="card">

<h3>Providers</h3>

<a class="btn"
href="{{ url_for(
'admin_providers'
) }}">
Open
</a>

</div>

<div class="card">

<h3>Farmers</h3>

<a class="btn"
href="{{ url_for(
'admin_farmers'
) }}">
Open
</a>

</div>

<div class="card">

<h3>TPIN</h3>

<a class="btn"
href="{{ url_for(
'admin_tpin'
) }}">
Open
</a>

</div>

<div class="card">

<h3>CV Requests</h3>

<a class="btn"
href="{{ url_for(
'admin_cvs'
) }}">
Open
</a>

</div>

<div class="card">

<h3>Assignments</h3>

<a class="btn"
href="{{ url_for(
'admin_assignments'
) }}">
Open
</a>

</div>

<div class="card">

<h3>Appointments</h3>

<a class="btn"
href="{{ url_for(
'admin_appointments'
) }}">
Open
</a>

</div>

<div class="card">

<h3>Deliveries</h3>

<a class="btn"
href="{{ url_for(
'admin_deliveries'
) }}">
Open
</a>

</div>

<div class="card">

<h3>Universities</h3>

<a class="btn"
href="{{ url_for(
'admin_universities'
) }}">
Open
</a>

</div>

</div>
"""

    return page(
        render_template_string(
            html,
            requests_list=requests_list,
            providers=providers,
            farmers=farmers,
            tpin=tpin,
            cvs=cvs,
            assignments=assignments,
            appointments=appointments,
            deliveries=deliveries,
        ),
        "KOJA Admin",
    )


# ============================================================
# ADMIN REQUESTS
# ============================================================

@app.route(
    "/admin/requests",
    methods=["GET", "POST"]
)
@admin_required
def admin_requests():

    if request.method == "POST":

        request_id = request.form.get(
            "request_id"
        )

        new_status = request.form.get(
            "status"
        )

        admin_notes = request.form.get(
            "admin_notes"
        )

        row = get_one(
            "service_requests",
            request_id,
        )

        if row:

            supabase_update(
                "service_requests",
                {
                    "id":
                        f"eq.{request_id}"
                },
                {
                    "status":
                        new_status,

                    "admin_notes":
                        admin_notes,
                }
            )

            create_activity(
                None,
                request_id,
                "admin_status_update",
                "Administrator updated request.",
                row.get("status"),
                new_status,
            )

            if row.get("user_id"):

                create_notification(
                    row["user_id"],
                    "KOJA Request Updated",
                    f"Your request status is now "
                    f"{new_status}.",
                    request_id,
                    "service_request",
                )

            flash(
                "Request updated.",
                "success"
            )

        return redirect(
            url_for("admin_requests")
        )

    rows = supabase_select(
        "service_requests",
        {
            "order":
                "created_at.desc",
            "limit":
                "200",
        }
    )

    html = """
<div class="card">

<h1>Service Requests</h1>

<div class="table-wrap">

<table>

<tr>
<th>Title</th>
<th>User</th>
<th>Status</th>
<th>Amount</th>
<th>Action</th>
</tr>

{% for r in rows %}

<tr>

<td>
{{ r.title }}
</td>

<td>
{{ r.user_id }}
</td>

<td>
{{ r.status }}
</td>

<td>
{{ r.currency }} {{ r.amount }}
</td>

<td>

<form method="post">

<input type="hidden"
name="request_id"
value="{{ r.id }}">

<select name="status">

<option value="submitted">
Submitted
</option>

<option value="under_review">
Under Review
</option>

<option value="information_required">
Information Required
</option>

<option value="assigned">
Assigned
</option>

<option value="accepted">
Accepted
</option>

<option value="in_progress">
In Progress
</option>

<option value="scheduled">
Scheduled
</option>

<option value="completed">
Completed
</option>

<option value="cancelled">
Cancelled
</option>

<option value="rejected">
Rejected
</option>

</select>

<textarea
name="admin_notes"
placeholder="Admin notes"
></textarea>

<button class="btn">
Update
</button>

</form>

</td>

</tr>

{% endfor %}

</table>

</div>

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
        ),
        "Admin Requests",
    )


# ============================================================
# ADMIN PROVIDERS
# ============================================================

@app.route(
    "/admin/providers",
    methods=["GET", "POST"]
)
@admin_required
def admin_providers():

    if request.method == "POST":

        provider_id = request.form.get(
            "provider_id"
        )

        status = request.form.get(
            "verification_status"
        )

        is_active = (
            request.form.get(
                "is_active"
            )
            == "true"
        )

        supabase_update(
            "service_providers",
            {
                "id":
                    f"eq.{provider_id}"
            },
            {
                "verification_status":
                    status,

                "is_active":
                    is_active,
            }
        )

        flash(
            "Provider updated.",
            "success"
        )

        return redirect(
            url_for(
                "admin_providers"
            )
        )

    rows = supabase_select(
        "service_providers",
        {
            "order":
                "created_at.desc",
            "limit":
                "200",
        }
    )

    html = """
<div class="card">

<h1>Service Providers</h1>

<div class="table-wrap">

<table>

<tr>
<th>Name</th>
<th>Type</th>
<th>Location</th>
<th>Verification</th>
<th>Action</th>
</tr>

{% for p in rows %}

<tr>

<td>
{{ p.full_name }}
</td>

<td>
{{ p.provider_type }}
</td>

<td>
{{ p.province }}
{{ p.district }}
</td>

<td>
{{ p.verification_status }}
</td>

<td>

<form method="post">

<input type="hidden"
name="provider_id"
value="{{ p.id }}">

<select name="verification_status">

<option value="pending">
Pending
</option>

<option value="verified">
Verified
</option>

<option value="rejected">
Rejected
</option>

<option value="suspended">
Suspended
</option>

</select>

<select name="is_active">

<option value="true">
Active
</option>

<option value="false">
Inactive
</option>

</select>

<button class="btn">
Save
</button>

</form>

</td>

</tr>

{% endfor %}

</table>

</div>

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
        ),
        "Admin Providers",
    )


# ============================================================
# ADMIN FARMERS
# ============================================================

@app.route(
    "/admin/farmers",
    methods=["GET", "POST"]
)
@admin_required
def admin_farmers():

    if request.method == "POST":

        farmer_id = request.form.get(
            "farmer_id"
        )

        status = request.form.get(
            "registration_status"
        )

        notes = request.form.get(
            "admin_notes"
        )

        supabase_update(
            "farmer_profiles",
            {
                "id":
                    f"eq.{farmer_id}"
            },
            {
                "registration_status":
                    status,

                "admin_notes":
                    notes,
            }
        )

        flash(
            "Farmer registration updated.",
            "success"
        )

        return redirect(
            url_for(
                "admin_farmers"
            )
        )

    rows = supabase_select(
        "farmer_profiles",
        {
            "order":
                "created_at.desc",
            "limit":
                "200",
        }
    )

    html = """
<div class="card">

<h1>Farmer Registrations</h1>

<div class="table-wrap">

<table>

<tr>
<th>Farmer</th>
<th>Phone</th>
<th>Province</th>
<th>District</th>
<th>Status</th>
<th>Action</th>
</tr>

{% for f in rows %}

<tr>

<td>
{{ f.full_name }}
</td>

<td>
{{ f.phone }}
</td>

<td>
{{ f.province }}
</td>

<td>
{{ f.district }}
</td>

<td>
{{ f.registration_status }}
</td>

<td>

<form method="post">

<input type="hidden"
name="farmer_id"
value="{{ f.id }}">

<select
name="registration_status">

<option value="submitted">
Submitted
</option>

<option value="under_review">
Under Review
</option>

<option value="information_required">
Information Required
</option>

<option value="processing">
Processing
</option>

<option value="completed">
Completed
</option>

<option value="rejected">
Rejected
</option>

</select>

<textarea
name="admin_notes"
placeholder="Notes"
></textarea>

<button class="btn">
Save
</button>

</form>

</td>

</tr>

{% endfor %}

</table>

</div>

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
        ),
        "Farmers",
    )


# ============================================================
# ADMIN TPIN
# ============================================================

@app.route(
    "/admin/tpin",
    methods=["GET", "POST"]
)
@admin_required
def admin_tpin():

    if request.method == "POST":

        row_id = request.form.get(
            "id"
        )

        status = request.form.get(
            "status"
        )

        notes = request.form.get(
            "admin_notes"
        )

        tpin_number = request.form.get(
            "tpin_number"
        )

        row = get_one(
            "tpin_requests",
            row_id,
        )

        supabase_update(
            "tpin_requests",
            {
                "id":
                    f"eq.{row_id}"
            },
            {
                "status":
                    status,

                "admin_notes":
                    notes,

                "tpin_number":
                    tpin_number,
            }
        )

        if row and row.get("user_id"):

            create_notification(
                row["user_id"],
                "TPIN Request Updated",
                f"Your TPIN request is now "
                f"{status}.",
                row.get(
                    "service_request_id"
                ),
                "tpin",
            )

        flash(
            "TPIN request updated.",
            "success"
        )

        return redirect(
            url_for("admin_tpin")
        )

    rows = supabase_select(
        "tpin_requests",
        {
            "order":
                "created_at.desc",
            "limit":
                "200",
        }
    )

    html = """
<div class="card">

<h1>TPIN Requests</h1>

<div class="table-wrap">

<table>

<tr>
<th>Name</th>
<th>NRC</th>
<th>Business</th>
<th>Status</th>
<th>Action</th>
</tr>

{% for r in rows %}

<tr>

<td>
{{ r.full_name }}
</td>

<td>
{{ r.nrc_number }}
</td>

<td>
{{ r.business_name }}
</td>

<td>
{{ r.status }}
</td>

<td>

<form method="post">

<input type="hidden"
name="id"
value="{{ r.id }}">

<select name="status">

<option value="submitted">
Submitted
</option>

<option value="under_review">
Under Review
</option>

<option value="information_required">
Information Required
</option>

<option value="processing">
Processing
</option>

<option value="completed">
Completed
</option>

<option value="rejected">
Rejected
</option>

</select>

<label>TPIN Number</label>

<input name="tpin_number"
value="{{ r.tpin_number or '' }}">

<textarea
name="admin_notes"
placeholder="Admin notes"
></textarea>

<button class="btn">
Save
</button>

</form>

</td>

</tr>

{% endfor %}

</table>

</div>

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
        ),
        "TPIN",
    )


# ============================================================
# ADMIN CV REQUESTS
# ============================================================

@app.route(
    "/admin/cvs",
    methods=["GET", "POST"]
)
@admin_required
def admin_cvs():

    if request.method == "POST":

        cv_id = request.form.get(
            "cv_id"
        )

        status = request.form.get(
            "status"
        )

        notes = request.form.get(
            "admin_notes"
        )

        supabase_update(
            "cv_requests",
            {
                "id":
                    f"eq.{cv_id}"
            },
            {
                "status":
                    status,

                "admin_notes":
                    notes,
            }
        )

        flash(
            "CV request updated.",
            "success"
        )

        return redirect(
            url_for("admin_cvs")
        )

    rows = supabase_select(
        "cv_requests",
        {
            "order":
                "created_at.desc",
            "limit":
                "200",
        }
    )

    html = """
<div class="card">

<h1>CV Requests</h1>

<div class="table-wrap">

<table>

<tr>
<th>Name</th>
<th>Target Job</th>
<th>Status</th>
<th>Action</th>
</tr>

{% for c in rows %}

<tr>

<td>
{{ c.full_name }}
</td>

<td>
{{ c.target_job }}
</td>

<td>
{{ c.status }}
</td>

<td>

<a class="btn"
href="{{ url_for(
'admin_generate_cv',
cv_id=c.id
) }}">
Generate CV
</a>

<form method="post"
style="margin-top:8px">

<input type="hidden"
name="cv_id"
value="{{ c.id }}">

<select name="status">

<option value="submitted">
Submitted
</option>

<option value="under_review">
Under Review
</option>

<option value="processing">
Processing
</option>

<option value="ready">
Ready
</option>

<option value="completed">
Completed
</option>

<option value="cancelled">
Cancelled
</option>

</select>

<textarea
name="admin_notes"
placeholder="Notes"
></textarea>

<button class="btn">
Save
</button>

</form>

</td>

</tr>

{% endfor %}

</table>

</div>

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
        ),
        "CV Requests",
    )


# ============================================================
# ADMIN GENERATE CV
# ============================================================

@app.route(
    "/admin/cv/<cv_id>/generate"
)
@admin_required
def admin_generate_cv(cv_id):

    cv = get_one(
        "cv_requests",
        cv_id,
    )

    if not cv:
        abort(404)

    pdf = generate_cv_pdf(cv)

    filename = (
        "cv-"
        + secure_filename(
            cv.get("full_name")
            or "applicant"
        ).replace(" ", "-")
        + "-"
        + uuid.uuid4().hex[:8]
        + ".pdf"
    )

    path = (
        "generated-cvs/"
        + filename
    )

    content = pdf.getvalue()

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{path}"
    )

    try:

        response = requests.post(
            url,
            headers={
                "Authorization":
                    f"Bearer {SUPABASE_SERVICE_KEY}",

                "apikey":
                    SUPABASE_SERVICE_KEY,

                "Content-Type":
                    "application/pdf",

                "x-upsert":
                    "true",
            },
            data=content,
            timeout=60,
        )

        if not response.ok:
            flash(
                "CV PDF upload failed.",
                "danger"
            )
            return redirect(
                url_for("admin_cvs")
            )

    except Exception as exc:

        logger.exception(exc)

        flash(
            "Unable to generate CV.",
            "danger"
        )

        return redirect(
            url_for("admin_cvs")
        )

    supabase_update(
        "cv_requests",
        {
            "id":
                f"eq.{cv_id}"
        },
        {
            "generated_file_path":
                path,

            "status":
                "ready",
        }
    )

    if cv.get("user_id"):

        create_notification(
            cv["user_id"],
            "Your CV is Ready",
            "Your KOJA CV has been generated.",
            cv.get(
                "service_request_id"
            ),
            "cv",
        )

    flash(
        "CV generated successfully.",
        "success"
    )

    return redirect(
        url_for(
            "admin_cvs"
        )
    )


# ============================================================
# CLIENT CV DOWNLOAD
# ============================================================

@app.route(
    "/cv/<cv_id>/download"
)
@login_required
def cv_download(cv_id):

    cv = get_one(
        "cv_requests",
        cv_id,
    )

    if not cv:
        abort(404)

    if (
        cv.get("user_id")
        != current_user_id()
        and not session.get("admin")
    ):
        abort(403)

    signed = create_signed_url(
        cv.get(
            "generated_file_path"
        ),
        3600,
    )

    if not signed:
        flash(
            "CV is not currently available.",
            "warning"
        )

        return redirect(
            url_for("dashboard")
        )

    return redirect(signed)


# ============================================================
# ADMIN ASSIGNMENTS
# ============================================================

@app.route(
    "/admin/assignments",
    methods=["GET", "POST"]
)
@admin_required
def admin_assignments():

    if request.method == "POST":

        assignment_id = request.form.get(
            "assignment_id"
        )

        status = request.form.get(
            "status"
        )

        notes = request.form.get(
            "admin_notes"
        )

        row = get_one(
            "assignment_requests",
            assignment_id,
        )

        supabase_update(
            "assignment_requests",
            {
                "id":
                    f"eq.{assignment_id}"
            },
            {
                "status":
                    status,

                "admin_notes":
                    notes,
            }
        )

        if row and row.get("user_id"):

            create_notification(
                row["user_id"],
                "Assignment Updated",
                f"Your assignment request "
                f"is now {status}.",
                row.get(
                    "service_request_id"
                ),
                "assignment",
            )

        flash(
            "Assignment updated.",
            "success"
        )

        return redirect(
            url_for(
                "admin_assignments"
            )
        )

    rows = supabase_select(
        "assignment_requests",
        {
            "order":
                "created_at.desc",
            "limit":
                "200",
        }
    )

    html = """
<div class="card">

<h1>Assignment Requests</h1>

<div class="table-wrap">

<table>

<tr>
<th>Title</th>
<th>Institution</th>
<th>Course</th>
<th>Deadline</th>
<th>Status</th>
<th>Action</th>
</tr>

{% for a in rows %}

<tr>

<td>
{{ a.assignment_title }}
</td>

<td>
{{ a.institution }}
</td>

<td>
{{ a.course }}
</td>

<td>
{{ a.deadline }}
</td>

<td>
{{ a.status }}
</td>

<td>

<form method="post">

<input type="hidden"
name="assignment_id"
value="{{ a.id }}">

<select name="status">

<option value="submitted">
Submitted
</option>

<option value="assigned">
Assigned
</option>

<option value="under_review">
Under Review
</option>

<option value="in_progress">
In Progress
</option>

<option value="answer_ready">
Answer Ready
</option>

<option value="completed">
Completed
</option>

<option value="cancelled">
Cancelled
</option>

</select>

<textarea
name="admin_notes"
placeholder="Notes"
></textarea>

<button class="btn">
Update
</button>

</form>

</td>

</tr>

{% endfor %}

</table>

</div>

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
        ),
        "Assignments",
    )


# ============================================================
# ADMIN APPOINTMENTS
# ============================================================

@app.route(
    "/admin/appointments",
    methods=["GET", "POST"]
)
@admin_required
def admin_appointments():

    if request.method == "POST":

        appointment_id = request.form.get(
            "appointment_id"
        )

        status = request.form.get(
            "status"
        )

        supabase_update(
            "appointments",
            {
                "id":
                    f"eq.{appointment_id}"
            },
            {
                "status":
                    status
            }
        )

        flash(
            "Appointment updated.",
            "success"
        )

        return redirect(
            url_for(
                "admin_appointments"
            )
        )

    rows = supabase_select(
        "appointments",
        {
            "order":
                "appointment_date.asc",
            "limit":
                "200",
        }
    )

    html = """
<div class="card">

<h1>Appointments</h1>

<div class="table-wrap">

<table>

<tr>
<th>Date</th>
<th>Time</th>
<th>Client</th>
<th>Provider</th>
<th>Status</th>
<th>Action</th>
</tr>

{% for a in rows %}

<tr>

<td>
{{ a.appointment_date }}
</td>

<td>
{{ a.start_time }}
-
{{ a.end_time }}
</td>

<td>
{{ a.client_id }}
</td>

<td>
{{ a.provider_id }}
</td>

<td>
{{ a.status }}
</td>

<td>

<form method="post">

<input type="hidden"
name="appointment_id"
value="{{ a.id }}">

<select name="status">

<option value="pending">
Pending
</option>

<option value="confirmed">
Confirmed
</option>

<option value="rescheduled">
Rescheduled
</option>

<option value="completed">
Completed
</option>

<option value="cancelled">
Cancelled
</option>

<option value="no_show">
No Show
</option>

</select>

<button class="btn">
Save
</button>

</form>

</td>

</tr>

{% endfor %}

</table>

</div>

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
        ),
        "Appointments",
    )


# ============================================================
# ADMIN DELIVERIES
# ============================================================

@app.route(
    "/admin/deliveries",
    methods=["GET", "POST"]
)
@admin_required
def admin_deliveries():

    if request.method == "POST":

        delivery_id = request.form.get(
            "delivery_id"
        )

        status = request.form.get(
            "status"
        )

        driver_id = request.form.get(
            "driver_id"
        )

        payload = {
            "status":
                status
        }

        if driver_id:
            payload["driver_id"] = driver_id

        if status == "delivered":

            payload["delivered_at"] = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

        supabase_update(
            "deliveries",
            {
                "id":
                    f"eq.{delivery_id}"
            },
            payload
        )

        delivery = get_one(
            "deliveries",
            delivery_id,
        )

        if delivery and delivery.get(
            "customer_id"
        ):

            create_notification(
                delivery["customer_id"],
                "Delivery Updated",
                f"Delivery "
                f"{delivery.get('tracking_code')} "
                f"is now {status}.",
                delivery.get(
                    "service_request_id"
                ),
                "delivery",
            )

        flash(
            "Delivery updated.",
            "success"
        )

        return redirect(
            url_for(
                "admin_deliveries"
            )
        )

    rows = supabase_select(
        "deliveries",
        {
            "order":
                "created_at.desc",
            "limit":
                "200",
        }
    )

    drivers = supabase_select(
        "service_providers",
        {
            "provider_type":
                "eq.driver",
            "verification_status":
                "eq.verified",
            "is_active":
                "eq.true",
            "order":
                "full_name.asc",
        }
    )

    html = """
<div class="card">

<h1>Deliveries</h1>

<div class="table-wrap">

<table>

<tr>
<th>Tracking</th>
<th>Pickup</th>
<th>Destination</th>
<th>Driver</th>
<th>Status</th>
<th>Action</th>
</tr>

{% for d in rows %}

<tr>

<td>
{{ d.tracking_code }}
</td>

<td>
{{ d.pickup_location }}
</td>

<td>
{{ d.destination }}
</td>

<td>
{{ d.driver_id or "Not assigned" }}
</td>

<td>
{{ d.status }}
</td>

<td>

<form method="post">

<input type="hidden"
name="delivery_id"
value="{{ d.id }}">

<label>Driver</label>

<select name="driver_id">

<option value="">
-- Select Driver --
</option>

{% for driver in drivers %}

<option value="{{ driver.id }}"
{% if d.driver_id == driver.id %}
selected
{% endif %}>

{{ driver.full_name }}

</option>

{% endfor %}

</select>

<select name="status">

<option value="requested">
Requested
</option>

<option value="assigned">
Assigned
</option>

<option value="accepted">
Accepted
</option>

<option value="picked_up">
Picked Up
</option>

<option value="in_transit">
In Transit
</option>

<option value="delivered">
Delivered
</option>

<option value="cancelled">
Cancelled
</option>

<option value="failed">
Failed
</option>

</select>

<button class="btn">
Save
</button>

</form>

</td>

</tr>

{% endfor %}

</table>

</div>

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
            drivers=drivers,
        ),
        "Deliveries",
    )


# ============================================================
# UNIVERSITIES
# ============================================================

@app.route("/universities")
def universities():

    rows = supabase_select(
        "universities",
        {
            "is_active":
                "eq.true",
            "order":
                "name.asc",
        }
    )

    html = """
<h1>Zambia Universities</h1>

<div class="grid">

{% for u in rows %}

<div class="card">

<h2>
{{ u.name }}
</h2>

<p>
{{ u.location or "" }}
</p>

<p>
{{ u.province or "" }}
</p>

{% if u.description %}
<p>
{{ u.description }}
</p>
{% endif %}

<a class="btn"
href="{{ url_for(
'university_detail',
university_id=u.id
) }}">
View Programmes
</a>

{% if u.website %}
<a class="btn btn-secondary"
href="{{ u.website }}"
target="_blank">
Website
</a>
{% endif %}

</div>

{% endfor %}

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
        ),
        "Universities",
    )


# ============================================================
# UNIVERSITY DETAIL
# ============================================================

@app.route(
    "/university/<university_id>"
)
def university_detail(university_id):

    university = get_one(
        "universities",
        university_id,
    )

    if not university:
        abort(404)

    programmes = supabase_select(
        "university_programmes",
        {
            "university_id":
                f"eq.{university_id}",
            "is_active":
                "eq.true",
            "order":
                "programme_name.asc",
        }
    )

    html = """
<div class="hero">

<h1>
{{ university.name }}
</h1>

<p>
{{ university.location or "" }}
</p>

</div>

<h2>Programmes</h2>

<div class="grid">

{% for p in programmes %}

<div class="card">

<h3>
{{ p.programme_name }}
</h3>

<p>
<strong>Faculty:</strong>
{{ p.faculty or "Not specified" }}
</p>

<p>
<strong>Qualification:</strong>
{{ p.qualification or "" }}
</p>

<p>
<strong>Duration:</strong>
{{ p.duration or "" }}
</p>

<h4>
Entry Requirements
</h4>

<p>
{{ p.entry_requirements or "" }}
</p>

<h4>
Application Requirements
</h4>

<p>
{{ p.application_requirements or "" }}
</p>

{% if p.application_fee %}

<p>
Application Fee:
<strong>
ZMW {{ p.application_fee }}
</strong>
</p>

{% endif %}

{% if p.application_url %}

<a class="btn"
href="{{ p.application_url }}"
target="_blank">
Apply
</a>

{% endif %}

</div>

{% else %}

<div class="card">
<p>
No programmes have been added yet.
</p>
</div>

{% endfor %}

</div>
"""

    return page(
        render_template_string(
            html,
            university=university,
            programmes=programmes,
        ),
        university["name"],
    )


# ============================================================
# ADMIN UNIVERSITIES
# ============================================================

@app.route(
    "/admin/universities",
    methods=["GET", "POST"]
)
@admin_required
def admin_universities():

    if request.method == "POST":

        action = request.form.get(
            "action"
        )

        if action == "university":

            supabase_insert(
                "universities",
                {
                    "name":
                        request.form.get(
                            "name"
                        ),

                    "province":
                        request.form.get(
                            "province"
                        ),

                    "location":
                        request.form.get(
                            "location"
                        ),

                    "website":
                        request.form.get(
                            "website"
                        ),

                    "admissions_url":
                        request.form.get(
                            "admissions_url"
                        ),

                    "description":
                        request.form.get(
                            "description"
                        ),

                    "is_active":
                        True,
                }
            )

            flash(
                "University added.",
                "success"
            )

        elif action == "programme":

            university_id = request.form.get(
                "university_id"
            )

            supabase_insert(
                "university_programmes",
                {
                    "university_id":
                        university_id,

                    "programme_name":
                        request.form.get(
                            "programme_name"
                        ),

                    "faculty":
                        request.form.get(
                            "faculty"
                        ),

                    "qualification":
                        request.form.get(
                            "qualification"
                        ),

                    "duration":
                        request.form.get(
                            "duration"
                        ),

                    "entry_requirements":
                        request.form.get(
                            "entry_requirements"
                        ),

                    "application_requirements":
                        request.form.get(
                            "application_requirements"
                        ),

                    "application_fee":
                        request.form.get(
                            "application_fee"
                        ) or None,

                    "currency":
                        "ZMW",

                    "application_url":
                        request.form.get(
                            "application_url"
                        ),

                    "is_active":
                        True,
                }
            )

            flash(
                "Programme added.",
                "success"
            )

        return redirect(
            url_for(
                "admin_universities"
            )
        )

    rows = supabase_select(
        "universities",
        {
            "order":
                "name.asc",
        }
    )

    html = """
<div class="grid">

<div class="card">

<h1>Add University</h1>

<form method="post">

<input type="hidden"
name="action"
value="university">

<label>Name</label>
<input name="name"
required>

<label>Province</label>
<input name="province">

<label>Location</label>
<input name="location">

<label>Website</label>
<input name="website">

<label>Admissions URL</label>
<input name="admissions_url">

<label>Description</label>
<textarea name="description"></textarea>

<button class="btn">
Add University
</button>

</form>

</div>


<div class="card">

<h1>Add Programme</h1>

<form method="post">

<input type="hidden"
name="action"
value="programme">

<label>University</label>

<select name="university_id"
required>

{% for u in rows %}

<option value="{{ u.id }}">
{{ u.name }}
</option>

{% endfor %}

</select>

<label>Programme Name</label>
<input name="programme_name"
required>

<label>Faculty</label>
<input name="faculty">

<label>Qualification</label>
<input name="qualification">

<label>Duration</label>
<input name="duration">

<label>Entry Requirements</label>
<textarea
name="entry_requirements"
></textarea>

<label>Application Requirements</label>
<textarea
name="application_requirements"
></textarea>

<label>Application Fee</label>
<input type="number"
step="0.01"
name="application_fee">

<label>Application URL</label>
<input name="application_url">

<button class="btn">
Add Programme
</button>

</form>

</div>

</div>


<div class="card"
style="margin-top:20px">

<h2>Universities</h2>

{% for u in rows %}

<p>
<strong>
{{ u.name }}
</strong>
—
{{ u.province or "" }}
</p>

{% endfor %}

</div>
"""

    return page(
        render_template_string(
            html,
            rows=rows,
        ),
        "Admin Universities",
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    configured = bool(
        SUPABASE_URL
        and SUPABASE_ANON_KEY
        and SUPABASE_SERVICE_KEY
    )

    return {
        "status": "ok",
        "app": "KOJA AFRICA",
        "supabase_configured":
            configured,
        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return page(
        """
<div class="card">

<h1>404</h1>

<p>
The page you requested could not be found.
</p>

<a class="btn"
href="/">
Return Home
</a>

</div>
""",
        "Not Found",
    ), 404


@app.errorhandler(403)
def forbidden(error):

    return page(
        """
<div class="card">

<h1>403</h1>

<p>
You do not have permission to access this page.
</p>

<a class="btn"
href="/">
Return Home
</a>

</div>
""",
        "Forbidden",
    ), 403


@app.errorhandler(413)
def too_large(error):

    return page(
        """
<div class="card">

<h1>File Too Large</h1>

<p>
The maximum upload size is 10 MB.
</p>

<a class="btn"
href="/">
Return Home
</a>

</div>
""",
        "File Too Large",
    ), 413


@app.errorhandler(500)
def server_error(error):

    logger.exception(error)

    return page(
        """
<div class="card">

<h1>Server Error</h1>

<p>
KOJA AFRICA encountered an unexpected error.
Please try again.
</p>

<a class="btn"
href="/">
Return Home
</a>

</div>
""",
        "Server Error",
    ), 500


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
