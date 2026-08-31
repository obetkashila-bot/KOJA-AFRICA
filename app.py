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
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    flash,
    send_file,
    abort,
    jsonify,
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# Flask + Supabase REST API
#
# Modules:
#   - Authentication
#   - Student dashboard
#   - Universities
#   - Programmes
#   - Admission requirements
#   - University applications
#   - Academic questions
#   - Learning resources
#   - CV builder
#   - Assignments
#   - Farmer registration
#   - Doctor booking
#   - Delivery requests
#   - Notifications
#   - Activity logs
#   - Administrator dashboard
# ============================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    secrets.token_hex(32)
)

app.config["MAX_CONTENT_LENGTH"] = (
    int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")

SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_KEY", "")
).strip()

SUPABASE_BUCKET = os.getenv(
    "SUPABASE_BUCKET",
    "koja-files"
).strip()

ADMIN_EMAIL = os.getenv(
    "ADMIN_EMAIL",
    ""
).strip().lower()

ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD",
    ""
)

ADMIN_NAME = os.getenv(
    "ADMIN_NAME",
    "KOJA Administrator"
).strip()

PORT = int(os.getenv("PORT", "5000"))

MAX_UPLOAD_MB = int(
    os.getenv("MAX_UPLOAD_MB", "20")
)

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "txt",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "csv",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

log = logging.getLogger("koja")


# ============================================================
# CONFIGURATION
# ============================================================

def configured():
    return bool(
        SUPABASE_URL
        and SUPABASE_KEY
    )


def require_config():
    if not configured():
        raise RuntimeError(
            "Supabase is not configured. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY "
            "in Render Environment Variables."
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


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    return str(value).strip()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def current_user():
    return session.get("user")


def is_admin():
    user = current_user()

    return bool(
        user
        and user.get("is_admin") is True
    )


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


def json_text(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False
        )
    except Exception:
        return "{}"


def uuid_string():
    return str(uuid.uuid4())


def valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


# ============================================================
# SUPABASE REST API
# ============================================================

def sb_get(
    table,
    params=None,
    single=False
):
    require_config()

    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers({
            "Accept": "application/json"
        }),
        params=params or {},
        timeout=30,
    )

    if r.status_code >= 400:
        log.error(
            "GET %s %s: %s",
            table,
            r.status_code,
            r.text
        )

        raise RuntimeError(
            f"Supabase GET {table} failed: {r.text}"
        )

    try:
        data = r.json()
    except Exception:
        data = []

    if single:
        return data[0] if data else None

    return data


def sb_insert(
    table,
    data,
    select="*"
):
    require_config()

    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers({
            "Prefer": "return=representation",
            "Accept": "application/json",
        }),
        params={
            "select": select
        },
        json=data,
        timeout=30,
    )

    if r.status_code >= 400:
        log.error(
            "INSERT %s %s: %s",
            table,
            r.status_code,
            r.text
        )

        raise RuntimeError(
            f"Supabase INSERT {table} failed: {r.text}"
        )

    try:
        body = r.json()
    except Exception:
        return data

    if isinstance(body, list):
        return body[0] if body else data

    return body


def sb_update(
    table,
    filters,
    data,
    select="*"
):
    require_config()

    params = dict(filters or {})

    params["select"] = select

    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers({
            "Prefer": "return=representation",
            "Accept": "application/json",
        }),
        params=params,
        json=data,
        timeout=30,
    )

    if r.status_code >= 400:
        log.error(
            "UPDATE %s %s: %s",
            table,
            r.status_code,
            r.text
        )

        raise RuntimeError(
            f"Supabase UPDATE {table} failed: {r.text}"
        )

    try:
        body = r.json()
    except Exception:
        return data

    if isinstance(body, list):
        return body[0] if body else data

    return body


def sb_delete(
    table,
    filters
):
    require_config()

    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers({
            "Prefer": "return=minimal"
        }),
        params=filters or {},
        timeout=30,
    )

    if r.status_code >= 400:
        log.error(
            "DELETE %s %s: %s",
            table,
            r.status_code,
            r.text
        )

        raise RuntimeError(
            f"Supabase DELETE {table} failed: {r.text}"
        )

    return True


def count_rows(
    table,
    params=None
):
    if not configured():
        return 0

    p = dict(params or {})

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers({
                "Prefer": "count=exact",
                "Range": "0-0",
                "Accept": "application/json",
            }),
            params=p,
            timeout=20,
        )

        if r.status_code >= 400:
            return 0

        content_range = r.headers.get(
            "Content-Range",
            ""
        )

        if "/" in content_range:
            value = content_range.split("/")[-1]

            if value != "*":
                return int(value)

        try:
            return len(r.json())
        except Exception:
            return 0

    except Exception:
        return 0


# ============================================================
# OPTIONAL TABLE HELPERS
# ============================================================

def table_available(table):
    if not configured():
        return False

    try:
        requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers({
                "Accept": "application/json",
                "Range": "0-0",
            }),
            timeout=10,
        )

        # A 401/403 means the table may exist but the key has
        # a policy problem. It is still considered unavailable
        # to the application.
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers({
                "Accept": "application/json",
                "Range": "0-0",
            }),
            timeout=10,
        )

        return r.status_code < 400

    except Exception:
        return False


def optional_get(
    table,
    params=None
):
    try:
        return sb_get(
            table,
            params or {}
        )
    except Exception as e:
        log.warning(
            "Optional table %s unavailable: %s",
            table,
            e
        )

        return []


def optional_insert(
    table,
    data
):
    try:
        return sb_insert(
            table,
            data
        )
    except Exception as e:
        log.warning(
            "Optional insert %s failed: %s",
            table,
            e
        )

        return None


# ============================================================
# STORAGE
# ============================================================

def storage_upload(
    file_storage,
    folder="uploads"
):
    require_config()

    original = secure_filename(
        file_storage.filename or ""
    )

    if not original:
        raise ValueError(
            "Invalid filename."
        )

    if "." not in original:
        raise ValueError(
            "File extension is required."
        )

    ext = original.rsplit(
        ".",
        1
    )[-1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "This file type is not allowed."
        )

    data = file_storage.read()

    if not data:
        raise ValueError(
            "The uploaded file is empty."
        )

    if len(data) > (
        MAX_UPLOAD_MB * 1024 * 1024
    ):
        raise ValueError(
            f"File exceeds {MAX_UPLOAD_MB} MB."
        )

    month_path = datetime.now(
        timezone.utc
    ).strftime("%Y/%m")

    path = (
        f"{folder}/"
        f"{month_path}/"
        f"{uuid.uuid4()}-{original}"
    )

    content_type = (
        file_storage.mimetype
        or "application/octet-stream"
    )

    url_path = quote(
        path,
        safe="/"
    )

    bucket = quote(
        SUPABASE_BUCKET,
        safe=""
    )

    r = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{bucket}/{url_path}",
        headers=headers({
            "Content-Type": content_type,
            "x-upsert": "false",
        }),
        data=data,
        timeout=90,
    )

    if r.status_code >= 400:
        log.error(
            "Storage upload failed: %s %s",
            r.status_code,
            r.text
        )

        raise RuntimeError(
            f"Storage upload failed: {r.text}"
        )

    public_url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/public/"
        f"{bucket}/{url_path}"
    )

    return (
        path,
        public_url,
        original,
        len(data),
        content_type
    )


def storage_download(path):
    require_config()

    bucket = quote(
        SUPABASE_BUCKET,
        safe=""
    )

    safe_path = quote(
        path,
        safe="/"
    )

    r = requests.get(
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{bucket}/{safe_path}",
        headers=headers(),
        timeout=90,
    )

    if r.status_code >= 400:
        abort(404)

    return (
        r.content,
        r.headers.get(
            "Content-Type",
            "application/octet-stream"
        )
    )


# ============================================================
# ACTIVITY / NOTIFICATIONS
# ============================================================

def log_activity(
    action,
    description="",
    user_id=None,
    email=None
):
    try:
        data = {
            "user_id": user_id,
            "action": action,
            "description": description,
            "ip_address": request.remote_addr,
            "user_agent": request.headers.get(
                "User-Agent",
                ""
            ),
        }

        # Some installations have an email column and
        # some don't. First try the richer record.
        if email:
            data["email"] = email

        try:
            sb_insert(
                "activity_logs",
                data
            )
        except Exception:
            data.pop(
                "email",
                None
            )

            sb_insert(
                "activity_logs",
                data
            )

    except Exception as e:
        log.warning(
            "Activity log skipped: %s",
            e
        )


def notify(
    email,
    title,
    message,
    request_id=None
):
    if not email:
        return

    try:
        data = {
            "client_email": email,
            "title": title,
            "message": message,
        }

        if request_id:
            data["request_id"] = request_id

        try:
            sb_insert(
                "koja_notifications",
                data
            )
        except Exception:
            data.pop(
                "request_id",
                None
            )

            sb_insert(
                "koja_notifications",
                data
            )

    except Exception as e:
        log.warning(
            "Notification skipped: %s",
            e
        )


# ============================================================
# AUTHENTICATION
# ============================================================

def find_profile_user(email):
    email = clean(email).lower()

    if not email:
        return None

    try:
        rows = sb_get(
            "profiles",
            {
                "select": "*",
                "email": f"eq.{email}",
                "limit": "1",
            }
        )

        if not rows:
            return None

        u = rows[0]

        return {
            "id": u.get("id"),
            "name": (
                u.get("full_name")
                or u.get("name")
                or email
            ),
            "email": (
                u.get("email")
                or email
            ),
            "phone": u.get("phone"),
            "institution": u.get(
                "institution",
                ""
            ),
            "student_number": u.get(
                "student_number",
                ""
            ),
            "password_hash": u.get(
                "password_hash"
            ),
            "role": (
                u.get("role")
                or (
                    "admin"
                    if u.get("is_admin")
                    else "student"
                )
            ),
            "is_admin": bool(
                u.get("is_admin")
            ) or u.get("role") == "admin",
            "is_active": (
                u.get("is_active", True)
            ),
            "table": "profiles",
        }

    except Exception as e:
        log.warning(
            "profiles authentication lookup failed: %s",
            e
        )

        return None


def find_koja_user(email):
    email = clean(email).lower()

    if not email:
        return None

    try:
        rows = sb_get(
            "koja_users",
            {
                "select": "*",
                "email": f"eq.{email}",
                "limit": "1",
            }
        )

        if not rows:
            return None

        u = rows[0]

        return {
            "id": u.get("id"),
            "name": (
                u.get("full_name")
                or u.get("name")
                or email
            ),
            "email": (
                u.get("email")
                or email
            ),
            "phone": u.get("phone"),
            "institution": u.get(
                "institution",
                ""
            ),
            "student_number": u.get(
                "student_number",
                ""
            ),
            "password_hash": u.get(
                "password_hash"
            ),
            "role": "student",
            "is_admin": False,
            "is_active": True,
            "table": "koja_users",
        }

    except Exception as e:
        log.warning(
            "koja_users authentication lookup failed: %s",
            e
        )

        return None


def find_user(email):
    email = clean(email).lower()

    if not email:
        return None

    user = find_profile_user(
        email
    )

    if user:
        return user

    return find_koja_user(
        email
    )


def ensure_env_admin():
    """
    The environment administrator is deliberately supported
    without depending on the exact columns in profiles.

    This is important because an inconsistent profiles schema
    must not prevent ADMIN_EMAIL / ADMIN_PASSWORD from working.
    """

    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return

    try:
        existing = find_profile_user(
            ADMIN_EMAIL
        )

        password_hash = (
            generate_password_hash(
                ADMIN_PASSWORD
            )
        )

        if existing:
            try:
                sb_update(
                    "profiles",
                    {
                        "id": (
                            f"eq.{existing['id']}"
                        )
                    },
                    {
                        "full_name": ADMIN_NAME,
                        "password_hash": password_hash,
                        "role": "admin",
                        "is_admin": True,
                        "is_active": True,
                    }
                )

                return

            except Exception as e:
                log.warning(
                    "Could not update existing "
                    "profile admin: %s",
                    e
                )

        # If profiles is unavailable, do not stop the app.
        try:
            sb_insert(
                "profiles",
                {
                    "full_name": ADMIN_NAME,
                    "name": ADMIN_NAME,
                    "email": ADMIN_EMAIL,
                    "password_hash": password_hash,
                    "role": "admin",
                    "is_admin": True,
                    "is_active": True,
                }
            )

            log.info(
                "Environment administrator created."
            )

        except Exception as e:
            log.warning(
                "Could not create database admin: %s",
                e
            )

    except Exception as e:
        log.warning(
            "Admin bootstrap failed: %s",
            e
        )


def login_environment_admin(
    email,
    password
):
    return bool(
        ADMIN_EMAIL
        and ADMIN_PASSWORD
        and email == ADMIN_EMAIL
        and secrets.compare_digest(
            password,
            ADMIN_PASSWORD
        )
    )


# ============================================================
# DECORATORS
# ============================================================

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):

        if not current_user():
            flash(
                "Please log in first.",
                "warning"
            )

            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )

        return fn(
            *args,
            **kwargs
        )

    return wrapped


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):

        if not current_user():
            flash(
                "Administrator login required.",
                "warning"
            )

            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )

        if not is_admin():
            abort(403)

        return fn(
            *args,
            **kwargs
        )

    return wrapped


# ============================================================
# BASE HTML
# ============================================================

BASE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">

<meta
 name="viewport"
 content="width=device-width,initial-scale=1"
>

<meta
 name="theme-color"
 content="#0b5ed7"
>

<title>{{ title or "KOJA Africa" }}</title>

<style>

:root{
 --primary:#0b5ed7;
 --primary-dark:#084298;
 --dark:#102033;
 --bg:#f5f7fb;
 --card:#ffffff;
 --text:#182230;
 --muted:#667085;
 --border:#e4e7ec;
 --success:#198754;
 --danger:#dc3545;
 --warning:#ffc107;
 --info:#0dcaf0;
}

*{
 box-sizing:border-box;
}

body{
 margin:0;
 background:var(--bg);
 color:var(--text);
 font-family:
 Arial,
 Helvetica,
 sans-serif;
 line-height:1.5;
}

a{
 color:var(--primary);
 text-decoration:none;
}

a:hover{
 text-decoration:underline;
}

nav{
 background:var(--dark);
 color:#fff;
 padding:13px 4%;
 display:flex;
 align-items:center;
 gap:12px;
 flex-wrap:wrap;
}

nav a{
 color:#fff;
 font-weight:600;
}

.brand{
 font-size:21px;
 margin-right:auto;
}

.container{
 width:min(1200px,94%);
 margin:24px auto;
}

.hero{
 background:
 linear-gradient(
 135deg,
 #0b5ed7,
 #17365d
 );
 color:#fff;
 border-radius:18px;
 padding:30px;
}

.hero a{
 color:#fff;
}

.grid{
 display:grid;
 grid-template-columns:
 repeat(
 auto-fit,
 minmax(260px,1fr)
 );
 gap:16px;
}

.card{
 background:var(--card);
 border:1px solid var(--border);
 border-radius:14px;
 padding:18px;
 box-shadow:
 0 2px 8px
 rgba(0,0,0,.04);
 margin-bottom:16px;
}

.card .card{
 box-shadow:none;
}

h1,
h2,
h3{
 margin-top:0;
}

.muted{
 color:var(--muted);
}

.small{
 font-size:13px;
}

.stat{
 font-size:30px;
 font-weight:800;
}

.actions{
 display:flex;
 gap:8px;
 flex-wrap:wrap;
 align-items:center;
}

.btn,
button{
 display:inline-block;
 border:0;
 border-radius:9px;
 background:var(--primary);
 color:#fff;
 padding:10px 15px;
 cursor:pointer;
 font-weight:700;
}

.btn:hover{
 text-decoration:none;
 background:var(--primary-dark);
}

.btn.secondary{
 background:#475467;
}

.btn.success{
 background:var(--success);
}

.btn.danger{
 background:var(--danger);
}

.btn.warning{
 background:#b58100;
}

input,
select,
textarea{
 width:100%;
 padding:11px;
 border:
 1px solid #cfd5dd;
 border-radius:8px;
 margin:5px 0 14px;
 background:#fff;
 font:inherit;
}

textarea{
 min-height:120px;
 resize:vertical;
}

label{
 font-weight:600;
 font-size:14px;
}

table{
 width:100%;
 border-collapse:collapse;
 background:#fff;
}

th,
td{
 padding:10px;
 border-bottom:
 1px solid var(--border);
 text-align:left;
 vertical-align:top;
}

.badge{
 display:inline-block;
 padding:4px 9px;
 border-radius:999px;
 background:#eef2ff;
 font-size:12px;
 font-weight:700;
}

.alert{
 padding:12px 14px;
 border-radius:9px;
 margin:10px 0;
 background:#fff3cd;
}

.alert.success{
 background:#d1e7dd;
}

.alert.danger{
 background:#f8d7da;
}

.alert.warning{
 background:#fff3cd;
}

.alert.info{
 background:#cff4fc;
}

hr{
 border:0;
 border-top:
 1px solid var(--border);
 margin:20px 0;
}

.stat-card{
 min-height:120px;
}

.feature-icon{
 font-size:30px;
 margin-bottom:8px;
}

.form-grid{
 display:grid;
 grid-template-columns:
 repeat(
 auto-fit,
 minmax(230px,1fr)
 );
 gap:12px;
}

.form-grid > div{
 min-width:0;
}

footer{
 padding:30px 4%;
 color:var(--muted);
 text-align:center;
}

@media(max-width:650px){

 nav{
  padding:12px 3%;
 }

 .brand{
  width:100%;
  margin-bottom:5px;
 }

 .container{
  width:96%;
  margin:15px auto;
 }

 .hero{
  padding:22px;
 }

 table{
  display:block;
  overflow-x:auto;
  white-space:nowrap;
 }

}

</style>
</head>

<body>

<nav>

<a
 class="brand"
 href="{{ url_for('home') }}"
>
KOJA AFRICA
</a>

<a href="{{ url_for('universities') }}">
Universities
</a>

<a href="{{ url_for('programmes') }}">
Programmes
</a>

<a href="{{ url_for('documents') }}">
Resources
</a>

{% if user %}
<a href="{{ url_for('questions') }}">
Questions
</a>

<a href="{{ url_for('cv_builder') }}">
CV
</a>

<a href="{{ url_for('assignments') }}">
Assignments
</a>

<a href="{{ url_for('services') }}">
Services
</a>

<a href="{{ url_for('dashboard') }}">
Dashboard
</a>

{% if user.is_admin %}
<a href="{{ url_for('admin') }}">
Admin
</a>
{% endif %}

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

</nav>

<div class="container">

{% with messages =
 get_flashed_messages(
  with_categories=true
 )
%}

{% for category,message in messages %}

<div class="alert {{ category }}">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ body|safe }}

</div>

<footer>
KOJA AFRICA —
Knowledge • Questions • Answers
</footer>

</body>
</html>
"""


def page(
    title,
    template,
    **ctx
):
    body = render_template_string(
        template,
        **ctx
    )

    return render_template_string(
        BASE,
        title=title,
        body=body,
        user=current_user()
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    stats = {}

    tables = [
        "universities",
        "university_programmes",
        "university_applications",
        "documents",
        "questions",
        "profiles",
    ]

    for table in tables:
        stats[table] = count_rows(
            table
        )

    return page(
        "KOJA Africa",
        r"""

<div class="hero">

<h1>
KOJA AFRICA
</h1>

<p>
Knowledge • Questions • Answers
</p>

<p>
A Zambian digital platform for
education, admissions, academic
services, agriculture, healthcare,
documents, assignments and deliveries.
</p>

<div class="actions">

<a
 class="btn"
 href="{{ url_for('universities') }}"
>
Explore Universities
</a>

<a
 class="btn secondary"
 href="{{ url_for('programmes') }}"
>
Find a Programme
</a>

{% if not user %}

<a
 class="btn success"
 href="{{ url_for('register') }}"
>
Create Account
</a>

{% endif %}

</div>

</div>

<br>

<div class="grid">

<div class="card stat-card">
<div class="stat">
{{ stats.universities }}
</div>
<div class="muted">
Universities
</div>
</div>

<div class="card stat-card">
<div class="stat">
{{ stats.university_programmes }}
</div>
<div class="muted">
Programmes
</div>
</div>

<div class="card stat-card">
<div class="stat">
{{ stats.university_applications }}
</div>
<div class="muted">
Applications
</div>
</div>

<div class="card stat-card">
<div class="stat">
{{ stats.documents }}
</div>
<div class="muted">
Learning resources
</div>
</div>

</div>

<br>

<div class="grid">

<div class="card">

<div class="feature-icon">
🎓
</div>

<h2>
University Admissions
</h2>

<p>
Search Zambian universities,
programmes, entry requirements
and application information.
</p>

<a
 class="btn"
 href="{{ url_for('universities') }}"
>
Explore
</a>

</div>

<div class="card">

<div class="feature-icon">
📚
</div>

<h2>
Academic Support
</h2>

<p>
Ask questions, submit assignments
and access learning resources.
</p>

<a
 class="btn"
 href="{{ url_for('questions') if user else url_for('login') }}"
>
Academic Support
</a>

</div>

<div class="card">

<div class="feature-icon">
📄
</div>

<h2>
CV Builder
</h2>

<p>
Create your professional CV and
download it as a PDF.
</p>

<a
 class="btn"
 href="{{ url_for('cv_builder') if user else url_for('login') }}"
>
Build CV
</a>

</div>

<div class="card">

<div class="feature-icon">
🚚
</div>

<h2>
KOJA Services
</h2>

<p>
Farmer registration, doctor booking
and delivery requests.
</p>

<a
 class="btn"
 href="{{ url_for('services') if user else url_for('login') }}"
>
Services
</a>

</div>

</div>

"""
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = clean(
            request.form.get(
                "full_name"
            )
        )

        email = clean(
            request.form.get(
                "email"
            )
        ).lower()

        phone = clean(
            request.form.get(
                "phone"
            )
        )

        institution = clean(
            request.form.get(
                "institution"
            )
        )

        student_number = clean(
            request.form.get(
                "student_number"
            )
        )

        password = request.form.get(
            "password",
            ""
        )

        confirm = request.form.get(
            "confirm_password",
            ""
        )

        if not name or not email or not password:
            flash(
                "Name, email and password are required.",
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

        if password != confirm:
            flash(
                "Passwords do not match.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        if login_environment_admin(
            email,
            password
        ):
            flash(
                "That email is reserved for the administrator.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        try:

            if find_user(email):

                flash(
                    "An account with that email already exists.",
                    "danger"
                )

                return redirect(
                    url_for("login")
                )

            password_hash = (
                generate_password_hash(
                    password
                )
            )

            # Primary registration table.
            try:

                user = sb_insert(
                    "koja_users",
                    {
                        "full_name": name,
                        "email": email,
                        "phone": phone,
                        "password_hash": password_hash,
                    }
                )

                user_id = user.get(
                    "id"
                )

                table_used = "koja_users"

            except Exception as e:

                log.warning(
                    "koja_users registration failed: %s",
                    e
                )

                user = sb_insert(
                    "profiles",
                    {
                        "full_name": name,
                        "name": name,
                        "email": email,
                        "phone": phone,
                        "institution": institution,
                        "student_number": student_number,
                        "password_hash": password_hash,
                        "role": "student",
                        "is_admin": False,
                        "is_active": True,
                    }
                )

                user_id = user.get(
                    "id"
                )

                table_used = "profiles"

            session["user"] = {
                "id": user_id,
                "name": name,
                "email": email,
                "phone": phone,
                "institution": institution,
                "student_number": student_number,
                "role": "student",
                "is_admin": False,
            }

            log_activity(
                "register",
                "New student registration",
                user_id,
                email
            )

            flash(
                "Account created successfully.",
                "success"
            )

            return redirect(
                url_for("dashboard")
            )

        except Exception as e:

            log.exception(
                "Registration error"
            )

            flash(
                f"Registration failed: {e}",
                "danger"
            )

    return page(
        "Register",
        r"""

<div class="card">

<h1>
Create KOJA Account
</h1>

<form method="post">

<label>
Full name
</label>

<input
 name="full_name"
 required
 autocomplete="name"
>

<label>
Email
</label>

<input
 type="email"
 name="email"
 required
 autocomplete="email"
>

<label>
Phone
</label>

<input
 name="phone"
>

<label>
Institution
</label>

<input
 name="institution"
>

<label>
Student number
</label>

<input
 name="student_number"
>

<label>
Password
</label>

<input
 type="password"
 name="password"
 minlength="6"
 required
 autocomplete="new-password"
>

<label>
Confirm password
</label>

<input
 type="password"
 name="confirm_password"
 minlength="6"
 required
 autocomplete="new-password"
>

<button>
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
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = clean(
            request.form.get(
                "email"
            )
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

        next_url = (
            request.form.get(
                "next"
            )
            or url_for("dashboard")
        )

        if not email or not password:

            flash(
                "Email and password are required.",
                "danger"
            )

            return redirect(
                url_for(
                    "login",
                    next=next_url
                )
            )

        # ====================================================
        # IMPORTANT:
        # Environment administrator is authenticated directly.
        #
        # This prevents "Invalid login credentials" when the
        # profiles table has a different schema.
        # ====================================================

        if login_environment_admin(
            email,
            password
        ):

            session["user"] = {
                "id": "environment-admin",
                "name": ADMIN_NAME,
                "email": ADMIN_EMAIL,
                "phone": "",
                "institution": "KOJA AFRICA",
                "student_number": "",
                "role": "admin",
                "is_admin": True,
            }

            try:
                ensure_env_admin()
            except Exception:
                pass

            log_activity(
                "admin_login",
                "Environment administrator login",
                None,
                ADMIN_EMAIL
            )

            return redirect(
                next_url
            )

        try:

            user = find_user(
                email
            )

        except Exception as e:

            log.exception(
                "Login lookup error"
            )

            flash(
                f"Login service error: {e}",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        if not user:

            flash(
                "Invalid login credentials.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        password_hash = user.get(
            "password_hash"
        )

        if not password_hash:

            flash(
                "This account does not have a valid password. "
                "Please register again or contact the administrator.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        if user.get(
            "is_active",
            True
        ) is False:

            flash(
                "This account is inactive. Contact the administrator.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        try:

            valid = check_password_hash(
                password_hash,
                password
            )

        except Exception:

            valid = False

        if not valid:

            flash(
                "Invalid login credentials.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        session["user"] = {
            "id": user.get("id"),
            "name": user.get("name"),
            "email": user.get("email"),
            "phone": user.get("phone"),
            "institution": user.get("institution"),
            "student_number": user.get("student_number"),
            "role": user.get("role"),
            "is_admin": bool(
                user.get("is_admin")
            ),
        }

        log_activity(
            "login",
            "User login",
            user.get("id"),
            user.get("email")
        )

        return redirect(
            next_url
        )

    return page(
        "Login",
        r"""

<div class="card">

<h1>
Login
</h1>

<p class="muted">
Students use their registered email and password.
</p>

<form method="post">

<input
 type="hidden"
 name="next"
 value="{{ request.args.get('next','') }}"
>

<label>
Email
</label>

<input
 type="email"
 name="email"
 required
 autocomplete="email"
>

<label>
Password
</label>

<input
 type="password"
 name="password"
 required
 autocomplete="current-password"
>

<button>
Login
</button>

</form>

<hr>

<p>
New student?
<a href="{{ url_for('register') }}">
Create an account
</a>
</p>

</div>

"""
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    user = current_user()

    if user:

        log_activity(
            "logout",
            "User logout",
            user.get("id"),
            user.get("email")
        )

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

    user = current_user()

    applications = []
    questions_ = []
    notifications_ = []

    assignments_ = []
    services_ = []

    try:

        applications = sb_get(
            "university_applications",
            {
                "select": "*",
                "user_id": (
                    f"eq.{user['id']}"
                ),
                "order": "created_at.desc",
            }
        )

    except Exception:
        pass

    try:

        questions_ = sb_get(
            "questions",
            {
                "select": "*",
                "student_id": (
                    f"eq.{user['id']}"
                ),
                "order": "created_at.desc",
            }
        )

    except Exception:
        pass

    try:

        notifications_ = sb_get(
            "koja_notifications",
            {
                "select": "*",
                "client_email": (
                    f"eq.{user['email']}"
                ),
                "order": "created_at.desc",
                "limit": "20",
            }
        )

    except Exception:
        pass

    assignments_ = optional_get(
        "koja_assignments",
        {
            "select": "*",
            "student_id": (
                f"eq.{user['id']}"
            ),
            "order": "created_at.desc",
        }
    )

    services_ = optional_get(
        "koja_service_requests",
        {
            "select": "*",
            "client_email": (
                f"eq.{user['email']}"
            ),
            "order": "created_at.desc",
        }
    )

    return page(
        "Dashboard",
        r"""

<h1>
Student Dashboard
</h1>

<div class="card">

<h2>
Welcome, {{ user.name }}
</h2>

<p>
{{ user.email }}
</p>

{% if user.institution %}
<p>
<b>Institution:</b>
{{ user.institution }}
</p>
{% endif %}

</div>

<div class="grid">

<div class="card">

<h3>
University Applications
</h3>

<div class="stat">
{{ applications|length }}
</div>

<a href="{{ url_for('my_applications') }}">
View applications
</a>

</div>

<div class="card">

<h3>
Academic Questions
</h3>

<div class="stat">
{{ questions|length }}
</div>

<a href="{{ url_for('questions') }}">
View questions
</a>

</div>

<div class="card">

<h3>
Assignments
</h3>

<div class="stat">
{{ assignments|length }}
</div>

<a href="{{ url_for('assignments') }}">
My assignments
</a>

</div>

<div class="card">

<h3>
Service Requests
</h3>

<div class="stat">
{{ services|length }}
</div>

<a href="{{ url_for('services') }}">
My services
</a>

</div>

<div class="card">

<h3>
Notifications
</h3>

<div class="stat">
{{ notifications|length }}
</div>

</div>

</div>

<br>

<div class="card">

<h2>
Quick Actions
</h2>

<div class="actions">

<a
 class="btn"
 href="{{ url_for('universities') }}"
>
Find University
</a>

<a
 class="btn"
 href="{{ url_for('programmes') }}"
>
Find Programme
</a>

<a
 class="btn"
 href="{{ url_for('new_application') }}"
>
University Application
</a>

<a
 class="btn"
 href="{{ url_for('new_question') }}"
>
Ask Question
</a>

<a
 class="btn"
 href="{{ url_for('cv_builder') }}"
>
Create CV
</a>

<a
 class="btn"
 href="{{ url_for('new_assignment') }}"
>
Submit Assignment
</a>

<a
 class="btn"
 href="{{ url_for('farmer_registration') }}"
>
Farmer Registration
</a>

<a
 class="btn"
 href="{{ url_for('doctor_booking') }}"
>
Book Doctor
</a>

<a
 class="btn"
 href="{{ url_for('delivery_request') }}"
>
Request Delivery
</a>

</div>

</div>

<br>

<div class="card">

<h2>
Recent Notifications
</h2>

{% for n in notifications %}

<div class="card">

<h3>
{{ n.title }}
</h3>

<p>
{{ n.message }}
</p>

<p class="muted small">
{{ n.created_at }}
</p>

</div>

{% else %}

<p>
No notifications yet.
</p>

{% endfor %}

</div>

""",
        applications=applications,
        questions=questions_,
        notifications=notifications_,
        assignments=assignments_,
        services=services_,
    )


# ============================================================
# UNIVERSITIES
# ============================================================

@app.route("/universities")
def universities():

    q = clean(
        request.args.get("q")
    )

    params = {
        "select": "*",
        "order": "name.asc",
        "limit": "500",
    }

    if q:
        params["name"] = (
            f"ilike.*{q}*"
        )

    try:

        rows = sb_get(
            "universities",
            params
        )

    except Exception as e:

        rows = []

        flash(
            f"Could not load universities: {e}",
            "danger"
        )

    counts = {}

    try:

        programmes = sb_get(
            "university_programmes",
            {
                "select": "university_id",
                "is_active": "eq.true",
                "limit": "5000",
            }
        )

        for p in programmes:

            uid = p.get(
                "university_id"
            )

            counts[uid] = (
                counts.get(uid, 0) + 1
            )

    except Exception:
        pass

    return page(
        "Universities",
        r"""

<div class="card">

<h1>
Zambian Universities & Institutions
</h1>

<form method="get">

<input
 name="q"
 value="{{ q }}"
 placeholder="Search university"
>

<button>
Search
</button>

</form>

</div>

<div class="grid">

{% for u in rows %}

<div class="card">

<h2>
{{ u.name }}
</h2>

<p class="muted">

{{ u.abbreviation or "" }}

{% if u.province %}
•
{{ u.province }}
{% endif %}

</p>

<p>
{{ u.description or
"University information and admissions." }}
</p>

<p>

<span class="badge">
{{ counts.get(u.id,0) }}
programmes
</span>

</p>

<div class="actions">

<a
 class="btn"
 href="{{ url_for(
 'university_detail',
 university_id=u.id
 ) }}"
>
View university
</a>

{% if u.application_url %}

<a
 class="btn secondary"
 target="_blank"
 href="{{ u.application_url }}"
>
Official application
</a>

{% endif %}

</div>

</div>

{% else %}

<div class="card">

<p>
No universities found.
</p>

</div>

{% endfor %}

</div>

""",
        rows=rows,
        q=q,
        counts=counts
    )


# ============================================================
# UNIVERSITY DETAIL
# ============================================================

@app.route(
    "/universities/<uuid:university_id>"
)
def university_detail(
    university_id
):

    try:

        university = sb_get(
            "universities",
            {
                "select": "*",
                "id": (
                    f"eq.{university_id}"
                ),
                "limit": "1",
            },
            single=True
        )

        if not university:
            abort(404)

        programmes_ = sb_get(
            "university_programmes",
            {
                "select": "*",
                "university_id": (
                    f"eq.{university_id}"
                ),
                "is_active": "eq.true",
                "order": "programme_name.asc",
                "limit": "1000",
            }
        )

    except Exception as e:

        flash(
            str(e),
            "danger"
        )

        return redirect(
            url_for("universities")
        )

    return page(
        university["name"],
        r"""

<div class="hero">

<h1>
{{ u.name }}
</h1>

<p>
{{ u.description or
"University admissions and programme information." }}
</p>

<div class="actions">

{% if u.application_url %}

<a
 class="btn"
 target="_blank"
 href="{{ u.application_url }}"
>
Apply on official website
</a>

{% endif %}

{% if u.admissions_url %}

<a
 class="btn secondary"
 target="_blank"
 href="{{ u.admissions_url }}"
>
Admissions Information
</a>

{% endif %}

</div>

</div>

<br>

<div class="card">

<h2>
University Information
</h2>

<table>

<tr>
<th>Institution type</th>
<td>{{ u.institution_type or "-" }}</td>
</tr>

<tr>
<th>Ownership</th>
<td>{{ u.ownership or "-" }}</td>
</tr>

<tr>
<th>Province</th>
<td>{{ u.province or "-" }}</td>
</tr>

<tr>
<th>District</th>
<td>{{ u.district or "-" }}</td>
</tr>

<tr>
<th>Campus</th>
<td>{{ u.campus or "-" }}</td>
</tr>

<tr>
<th>Location</th>
<td>{{ u.location or "-" }}</td>
</tr>

<tr>
<th>Application status</th>
<td>{{ u.application_status or "Unknown" }}</td>
</tr>

<tr>
<th>Deadline</th>
<td>{{ u.deadline or "-" }}</td>
</tr>

<tr>
<th>Application fee</th>
<td>
{{ u.application_fee_zmw or "-" }}
ZMW
</td>
</tr>

<tr>
<th>Accreditation</th>
<td>
{{ u.accreditation_status or "-" }}
</td>
</tr>

</table>

</div>

<br>

<div class="card">

<h2>
Programmes
({{ programmes|length }})
</h2>

<div class="grid">

{% for p in programmes %}

<div class="card">

<h3>
{{ p.programme_name }}
</h3>

<p class="muted">
{{ p.qualification
or p.qualification_level
or "" }}
</p>

<p>
<b>Duration:</b>
{{ p.duration
or p.study_duration
or "-" }}
</p>

<p>
<b>Required subjects:</b>
{{ p.required_subjects
or "Not specified" }}
</p>

<p>
<b>Minimum grade:</b>
{{ p.minimum_grade
or p.minimum_points
or "Not specified" }}
</p>

<p>
<b>Status:</b>
{{ p.application_status
or "Unknown" }}
</p>

<a
 class="btn"
 href="{{ url_for(
 'programme_detail',
 programme_id=p.id
 ) }}"
>
View Requirements
</a>

</div>

{% else %}

<p>
No programmes have been entered.
</p>

{% endfor %}

</div>

</div>

""",
        u=university,
        programmes=programmes_
    )


# ============================================================
# PROGRAMMES
# ============================================================

@app.route("/programmes")
def programmes():

    q = clean(
        request.args.get("q")
    )

    university_id = clean(
        request.args.get(
            "university_id"
        )
    )

    universities_ = optional_get(
        "universities",
        {
            "select": "id,name",
            "order": "name.asc",
            "limit": "500",
        }
    )

    params = {
        "select": "*",
        "order": "programme_name.asc",
        "limit": "1000",
    }

    if q:
        params["programme_name"] = (
            f"ilike.*{q}*"
        )

    if university_id:
        params["university_id"] = (
            f"eq.{university_id}"
        )

    try:

        rows = sb_get(
            "university_programmes",
            params
        )

    except Exception as e:

        rows = []

        flash(
            f"Could not load programmes: {e}",
            "danger"
        )

    names = {
        str(x.get("id")):
        x.get("name")
        for x in universities_
    }

    for row in rows:

        row["_university_name"] = names.get(
            str(row.get("university_id")),
            "Unknown"
        )

    return page(
        "Programmes",
        r"""

<div class="card">

<h1>
Find a University Programme
</h1>

<form method="get">

<label>
Programme
</label>

<input
 name="q"
 value="{{ q }}"
 placeholder="e.g. Computer Science"
>

<label>
University
</label>

<select name="university_id">

<option value="">
All universities
</option>

{% for u in universities %}

<option
 value="{{ u.id }}"
 {% if university_id ==
 u.id|string %}
 selected
 {% endif %}
>

{{ u.name }}

</option>

{% endfor %}

</select>

<button>
Search
</button>

</form>

</div>

<div class="card">

<b>
{{ rows|length }}
</b>
programme(s) found.

</div>

<div class="grid">

{% for p in rows %}

<div class="card">

<h3>
{{ p.programme_name }}
</h3>

<p>
<b>
{{ p._university_name }}
</b>
</p>

<p class="muted">
{{ p.qualification
or p.qualification_level
or p.programme_type
or "" }}
</p>

<p>
<b>Subjects:</b>
{{ p.required_subjects
or "Not specified" }}
</p>

<p>
<b>Minimum:</b>
{{ p.minimum_grade
or p.minimum_points
or "Not specified" }}
</p>

<p>
<b>Fee:</b>
{{ p.application_fee
if p.application_fee is not none
else "Not specified" }}
{{ p.currency or "ZMW" }}
</p>

<a
 class="btn"
 href="{{ url_for(
 'programme_detail',
 programme_id=p.id
 ) }}"
>
Details
</a>

</div>

{% else %}

<div class="card">
No programmes found.
</div>

{% endfor %}

</div>

""",
        rows=rows,
        q=q,
        university_id=university_id,
        universities=universities_
    )


# ============================================================
# PROGRAMME DETAIL
# ============================================================

@app.route(
    "/programmes/<uuid:programme_id>"
)
def programme_detail(
    programme_id
):

    try:

        p = sb_get(
            "university_programmes",
            {
                "select": "*",
                "id": (
                    f"eq.{programme_id}"
                ),
                "limit": "1",
            },
            single=True
        )

        if not p:
            abort(404)

        u = sb_get(
            "universities",
            {
                "select": "*",
                "id": (
                    f"eq.{p['university_id']}"
                ),
                "limit": "1",
            },
            single=True
        )

        requirements = optional_get(
            "university_application_requirements",
            {
                "select": "*",
                "programme_id": (
                    f"eq.{programme_id}"
                ),
                "order": "created_at.asc",
            }
        )

    except Exception as e:

        flash(
            str(e),
            "danger"
        )

        return redirect(
            url_for("programmes")
        )

    return page(
        p["programme_name"],
        r"""

<div class="hero">

<h1>
{{ p.programme_name }}
</h1>

<p>
{{ u.name if u else "University" }}
</p>

<div class="actions">

{% if user %}

<a
 class="btn"
 href="{{ url_for(
 'new_application',
 programme_id=p.id
 ) }}"
>
Start Application
</a>

{% else %}

<a
 class="btn"
 href="{{ url_for(
 'login',
 next=url_for(
 'new_application',
 programme_id=p.id
 )
 ) }}"
>
Login to Apply
</a>

{% endif %}

{% if p.application_url %}

<a
 class="btn secondary"
 target="_blank"
 href="{{ p.application_url }}"
>
Official Application
</a>

{% endif %}

</div>

</div>

<br>

<div class="card">

<h2>
Programme Details
</h2>

<table>

<tr>
<th>Qualification</th>
<td>
{{ p.qualification
or p.qualification_level
or "-" }}
</td>
</tr>

<tr>
<th>Faculty</th>
<td>{{ p.faculty or "-" }}</td>
</tr>

<tr>
<th>School</th>
<td>{{ p.school or "-" }}</td>
</tr>

<tr>
<th>Duration</th>
<td>
{{ p.duration
or p.study_duration
or "-" }}
</td>
</tr>

<tr>
<th>Study mode</th>
<td>{{ p.study_mode or "-" }}</td>
</tr>

<tr>
<th>Entry level</th>
<td>{{ p.entry_level or "-" }}</td>
</tr>

<tr>
<th>Required subjects</th>
<td>
{{ p.required_subjects or "-" }}
</td>
</tr>

<tr>
<th>Minimum grade</th>
<td>
{{ p.minimum_grade or "-" }}
</td>
</tr>

<tr>
<th>Minimum points</th>
<td>
{{ p.minimum_points or "-" }}
</td>
</tr>

<tr>
<th>Entry requirements</th>
<td>
{{ p.entry_requirements
or p.requirements
or "-" }}
</td>
</tr>

<tr>
<th>Application requirements</th>
<td>
{{ p.application_requirements or "-" }}
</td>
</tr>

<tr>
<th>Application fee</th>
<td>
{{ p.application_fee
if p.application_fee is not none
else "-" }}
{{ p.currency or "ZMW" }}
</td>
</tr>

<tr>
<th>Deadline</th>
<td>
{{ p.deadline or "-" }}
</td>
</tr>

<tr>
<th>Status</th>
<td>
{{ p.application_status or "Unknown" }}
</td>
</tr>

</table>

</div>

<br>

<div class="card">

<h2>
Specific Application Requirements
</h2>

{% for r in requirements %}

<div class="card">

<h3>
{{ r.requirement_title }}
</h3>

<p>
{{ r.requirement_description or "" }}
</p>

{% if r.document_type %}

<p>
<b>Document:</b>
{{ r.document_type }}
</p>

{% endif %}

{% if r.applicant_type %}

<p>
<b>Applicant:</b>
{{ r.applicant_type }}
</p>

{% endif %}

<p>
<b>Required:</b>
{{ "Yes" if r.required else "No" }}
</p>

{% if r.source_url %}

<a
 target="_blank"
 href="{{ r.source_url }}"
>
Source / Verify
</a>

{% endif %}

</div>

{% else %}

<p>
No programme-specific requirements have
been entered yet. Applicants should verify
current requirements with the institution.
</p>

{% endfor %}

</div>

""",
        p=p,
        u=u,
        requirements=requirements
    )


# ============================================================
# UNIVERSITY APPLICATIONS
# ============================================================

@app.route("/applications")
@login_required
def my_applications():

    user = current_user()

    try:

        rows = sb_get(
            "university_applications",
            {
                "select": "*",
                "user_id": (
                    f"eq.{user['id']}"
                ),
                "order": "created_at.desc",
            }
        )

    except Exception as e:

        rows = []

        flash(
            str(e),
            "danger"
        )

    return page(
        "My Applications",
        r"""

<div class="actions">

<h1 style="margin-right:auto">
My Applications
</h1>

<a
 class="btn"
 href="{{ url_for('new_application') }}"
>
New Application
</a>

</div>

<div class="card">

<table>

<tr>
<th>Application</th>
<th>University</th>
<th>Programme</th>
<th>Status</th>
<th>Payment</th>
<th>Date</th>
</tr>

{% for a in rows %}

<tr>

<td>

<a
 href="{{ url_for(
 'application_detail',
 application_id=a.id
 ) }}"
>

{{ a.application_number
or a.id }}

</a>

</td>

<td>
{{ a.university }}
</td>

<td>
{{ a.programme }}
</td>

<td>

<span class="badge">
{{ a.application_status
or a.status }}
</span>

</td>

<td>
{{ a.payment_status or "unpaid" }}
</td>

<td>
{{ a.created_at }}
</td>

</tr>

{% else %}

<tr>

<td colspan="6">
No applications yet.
</td>

</tr>

{% endfor %}

</table>

</div>

""",
        rows=rows
    )


# ============================================================
# NEW UNIVERSITY APPLICATION
# ============================================================

@app.route(
    "/applications/new",
    methods=["GET", "POST"]
)
@login_required
def new_application():

    user = current_user()

    selected_programme_id = (
        clean(
            request.args.get(
                "programme_id"
            )
        )
        or clean(
            request.form.get(
                "programme_id"
            )
        )
    )

    selected_university_id = clean(
        request.form.get(
            "university_id"
        )
    )

    programme = None
    university = None

    universities_ = optional_get(
        "universities",
        {
            "select": "id,name",
            "order": "name.asc",
            "limit": "500",
        }
    )

    # --------------------------------------------------------
    # GET programme correctly.
    # --------------------------------------------------------

    if selected_programme_id:

        try:

            programme = sb_get(
                "university_programmes",
                {
                    "select": "*",
                    "id": (
                        f"eq.{selected_programme_id}"
                    ),
                    "limit": "1",
                },
                single=True
            )

            if programme:

                selected_university_id = str(
                    programme.get(
                        "university_id"
                    )
                )

        except Exception:
            programme = None

    if selected_university_id:

        try:

            university = sb_get(
                "universities",
                {
                    "select": "*",
                    "id": (
                        f"eq.{selected_university_id}"
                    ),
                    "limit": "1",
                },
                single=True
            )

        except Exception:
            university = None

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    if request.method == "POST":

        university_id = clean(
            request.form.get(
                "university_id"
            )
        )

        programme_id = clean(
            request.form.get(
                "programme_id"
            )
        )

        if not university_id or not programme_id:

            flash(
                "Select both a university and a programme.",
                "danger"
            )

            return redirect(
                url_for(
                    "new_application"
                )
            )

        try:

            university = sb_get(
                "universities",
                {
                    "select": "*",
                    "id": (
                        f"eq.{university_id}"
                    ),
                    "limit": "1",
                },
                single=True
            )

            programme = sb_get(
                "university_programmes",
                {
                    "select": "*",
                    "id": (
                        f"eq.{programme_id}"
                    ),
                    "limit": "1",
                },
                single=True
            )

            if not university:
                raise ValueError(
                    "Selected university was not found."
                )

            if not programme:
                raise ValueError(
                    "Selected programme was not found."
                )

            if str(
                programme.get(
                    "university_id"
                )
            ) != str(university_id):

                raise ValueError(
                    "The selected programme does not belong "
                    "to the selected university."
                )

            first = clean(
                request.form.get(
                    "first_name"
                )
            )

            middle = clean(
                request.form.get(
                    "middle_names"
                )
            )

            last = clean(
                request.form.get(
                    "last_name"
                )
            )

            full_name = " ".join(
                x for x in [
                    first,
                    middle,
                    last
                ]
                if x
            )

            applicant_email = clean(
                request.form.get(
                    "email"
                )
            ).lower()

            application = sb_insert(
                "university_applications",
                {
                    "user_id": user["id"],
                    "university_id": university_id,
                    "programme_id": programme_id,

                    "university":
                        university.get("name"),

                    "programme":
                        programme.get(
                            "programme_name"
                        ),

                    "intake":
                        clean(
                            request.form.get(
                                "intake"
                            )
                        ),

                    "applicant_first_name":
                        first,

                    "applicant_middle_names":
                        middle,

                    "applicant_last_name":
                        last,

                    "full_name":
                        full_name,

                    "date_of_birth":
                        request.form.get(
                            "date_of_birth"
                        )
                        or None,

                    "gender":
                        clean(
                            request.form.get(
                                "gender"
                            )
                        ),

                    "nrc_number":
                        clean(
                            request.form.get(
                                "nrc_number"
                            )
                        ),

                    "phone":
                        clean(
                            request.form.get(
                                "phone"
                            )
                        ),

                    "email":
                        applicant_email,

                    "address":
                        clean(
                            request.form.get(
                                "address"
                            )
                        ),

                    "province":
                        clean(
                            request.form.get(
                                "province"
                            )
                        ),

                    "district":
                        clean(
                            request.form.get(
                                "district"
                            )
                        ),

                    "previous_school":
                        clean(
                            request.form.get(
                                "previous_school"
                            )
                        ),

                    "qualification":
                        clean(
                            request.form.get(
                                "qualification"
                            )
                        ),

                    "application_information":
                        clean(
                            request.form.get(
                                "application_information"
                            )
                        ),

                    "applicant_notes":
                        clean(
                            request.form.get(
                                "applicant_notes"
                            )
                        ),

                    "status":
                        "submitted",

                    "application_status":
                        "submitted",

                    "payment_status":
                        "unpaid",

                    "application_fee":
                        programme.get(
                            "application_fee"
                        )
                        or university.get(
                            "application_fee_zmw"
                        )
                        or 0,

                    "currency":
                        programme.get(
                            "currency"
                        )
                        or "ZMW",

                    "submitted_at":
                        now_iso(),
                }
            )

            notify(
                applicant_email,
                "University application submitted",
                (
                    "Your application for "
                    f"{programme['programme_name']} "
                    f"at {university['name']} "
                    "has been submitted."
                )
            )

            log_activity(
                "university_application",
                f"Application {application.get('id')}",
                user["id"],
                user["email"]
            )

            flash(
                "University application submitted successfully.",
                "success"
            )

            return redirect(
                url_for(
                    "application_detail",
                    application_id=application["id"]
                )
            )

        except Exception as e:

            log.exception(
                "Application error"
            )

            flash(
                f"Application failed: {e}",
                "danger"
            )

    programmes_ = []

    if university:

        programmes_ = optional_get(
            "university_programmes",
            {
                "select": "*",
                "university_id": (
                    f"eq.{university['id']}"
                ),
                "is_active": "eq.true",
                "order": "programme_name.asc",
                "limit": "1000",
            }
        )

    return page(
        "University Application",
        r"""

<div class="card">

<h1>
University Application
</h1>

<form method="post">

<label>
University
</label>

<select
 name="university_id"
 onchange="this.form.submit()"
 required
>

<option value="">
Select university
</option>

{% for x in universities %}

<option
 value="{{ x.id }}"
 {% if university
 and university.id|string ==
 x.id|string %}
 selected
 {% endif %}
>

{{ x.name }}

</option>

{% endfor %}

</select>

<noscript>
<button>
Load University
</button>
</noscript>

<label>
Programme
</label>

<select
 name="programme_id"
 required
>

<option value="">
Select programme
</option>

{% for x in programmes %}

<option
 value="{{ x.id }}"
 {% if programme
 and programme.id|string ==
 x.id|string %}
 selected
 {% endif %}
>

{{ x.programme_name }}

</option>

{% endfor %}

</select>

{% if not programmes %}

<p class="muted">
Select a university to load its programmes.
</p>

{% endif %}

<hr>

<h3>
Applicant Details
</h3>

<div class="form-grid">

<div>

<label>
First name
</label>

<input
 name="first_name"
 required
>

</div>

<div>

<label>
Middle names
</label>

<input
 name="middle_names"
>

</div>

<div>

<label>
Last name
</label>

<input
 name="last_name"
 required
>

</div>

<div>

<label>
Date of birth
</label>

<input
 type="date"
 name="date_of_birth"
>

</div>

<div>

<label>
Gender
</label>

<select name="gender">

<option value="">
Select
</option>

<option>
Male
</option>

<option>
Female
</option>

<option>
Other
</option>

</select>

</div>

<div>

<label>
NRC number
</label>

<input
 name="nrc_number"
>

</div>

<div>

<label>
Phone
</label>

<input
 name="phone"
 value="{{ user.phone or '' }}"
>

</div>

<div>

<label>
Email
</label>

<input
 type="email"
 name="email"
 value="{{ user.email }}"
 required
>

</div>

<div>

<label>
Province
</label>

<input
 name="province"
>

</div>

<div>

<label>
District
</label>

<input
 name="district"
>

</div>

</div>

<label>
Address
</label>

<textarea
 name="address"
></textarea>

<label>
Previous school
</label>

<input
 name="previous_school"
>

<label>
Previous qualification
</label>

<input
 name="qualification"
>

<label>
Intake
</label>

<input
 name="intake"
 placeholder="e.g. 2027"
>

<label>
Additional application information
</label>

<textarea
 name="application_information"
></textarea>

<label>
Applicant notes
</label>

<textarea
 name="applicant_notes"
></textarea>

<button>
Submit Application
</button>

</form>

</div>

""",
        universities=universities_,
        university=university,
        programme=programme,
        programmes=programmes_
    )


# ============================================================
# APPLICATION DETAIL
# ============================================================

@app.route(
    "/applications/<uuid:application_id>"
)
@login_required
def application_detail(
    application_id
):

    user = current_user()

    try:

        a = sb_get(
            "university_applications",
            {
                "select": "*",
                "id": (
                    f"eq.{application_id}"
                ),
                "limit": "1",
            },
            single=True
        )

    except Exception:
        a = None

    if not a:
        abort(404)

    if (
        not user["is_admin"]
        and str(a.get("user_id"))
        != str(user["id"])
    ):
        abort(403)

    return page(
        "Application",
        r"""

<div class="card">

<h1>
University Application
</h1>

<table>

<tr>
<th>Application number</th>
<td>
{{ a.application_number
or a.id }}
</td>
</tr>

<tr>
<th>University</th>
<td>
{{ a.university }}
</td>
</tr>

<tr>
<th>Programme</th>
<td>
{{ a.programme }}
</td>
</tr>

<tr>
<th>Applicant</th>
<td>
{{ a.full_name }}
</td>
</tr>

<tr>
<th>Email</th>
<td>
{{ a.email }}
</td>
</tr>

<tr>
<th>Phone</th>
<td>
{{ a.phone }}
</td>
</tr>

<tr>
<th>Status</th>
<td>
<span class="badge">
{{ a.application_status
or a.status }}
</span>
</td>
</tr>

<tr>
<th>Payment</th>
<td>
{{ a.payment_status }}
—
{{ a.application_fee }}
{{ a.currency }}
</td>
</tr>

<tr>
<th>Admin notes</th>
<td>
{{ a.admin_notes or "-" }}
</td>
</tr>

<tr>
<th>Rejection reason</th>
<td>
{{ a.rejection_reason or "-" }}
</td>
</tr>

<tr>
<th>Submitted</th>
<td>
{{ a.submitted_at
or a.created_at }}
</td>
</tr>

</table>

</div>

"""
        ,
        a=a
    )


# ============================================================
# QUESTIONS
# ============================================================

@app.route("/questions")
@login_required
def questions():

    user = current_user()

    try:

        if user["is_admin"]:

            rows = sb_get(
                "questions",
                {
                    "select": "*",
                    "order": "created_at.desc",
                    "limit": "500",
                }
            )

        else:

            rows = sb_get(
                "questions",
                {
                    "select": "*",
                    "student_id": (
                        f"eq.{user['id']}"
                    ),
                    "order": "created_at.desc",
                    "limit": "500",
                }
            )

    except Exception as e:

        rows = []

        flash(
            str(e),
            "danger"
        )

    return page(
        "Questions",
        r"""

<div class="actions">

<h1 style="margin-right:auto">
Academic Questions
</h1>

<a
 class="btn"
 href="{{ url_for('new_question') }}"
>
Ask Question
</a>

</div>

<div class="grid">

{% for q in rows %}

<div class="card">

<h3>
{{ q.subject or
"Academic question" }}
</h3>

<p>
{{ q.question }}
</p>

<p>

<span class="badge">
{{ q.status or "pending" }}
</span>

</p>

{% if q.answer %}

<hr>

<h3>
Answer
</h3>

<p>
{{ q.answer }}
</p>

{% endif %}

</div>

{% else %}

<div class="card">
No questions found.
</div>

{% endfor %}

</div>

""",
        rows=rows
    )


@app.route(
    "/questions/new",
    methods=["GET", "POST"]
)
@login_required
def new_question():

    user = current_user()

    if request.method == "POST":

        question = clean(
            request.form.get(
                "question"
            )
        )

        if not question:

            flash(
                "Question is required.",
                "danger"
            )

            return redirect(
                url_for("new_question")
            )

        try:

            q = sb_insert(
                "questions",
                {
                    "student_id":
                        user["id"],

                    "student_name":
                        user["name"],

                    "question":
                        question,

                    "subject":
                        clean(
                            request.form.get(
                                "subject"
                            )
                        ),

                    "course":
                        clean(
                            request.form.get(
                                "course"
                            )
                        ),

                    "class_level":
                        clean(
                            request.form.get(
                                "class_level"
                            )
                        ),

                    "status":
                        "pending",
                }
            )

            log_activity(
                "question",
                "Academic question submitted",
                user["id"],
                user["email"]
            )

            flash(
                "Question submitted.",
                "success"
            )

            return redirect(
                url_for("questions")
            )

        except Exception as e:

            flash(
                f"Could not submit question: {e}",
                "danger"
            )

    return page(
        "Ask Question",
        r"""

<div class="card">

<h1>
Ask an Academic Question
</h1>

<form method="post">

<label>
Subject
</label>

<input name="subject">

<label>
Course
</label>

<input name="course">

<label>
Class / Level
</label>

<input name="class_level">

<label>
Question
</label>

<textarea
 name="question"
 required
></textarea>

<button>
Submit Question
</button>

</form>

</div>

"""
    )


# ============================================================
# DOCUMENTS
# ============================================================

@app.route("/documents")
def documents():

    q = clean(
        request.args.get("q")
    )

    params = {
        "select": "*",
        "order": "created_at.desc",
        "limit": "300",
    }

    if q:
        params["title"] = (
            f"ilike.*{q}*"
        )

    source_table = "documents"

    try:

        rows = sb_get(
            "documents",
            params
        )

    except Exception:

        source_table = "document_library"

        try:

            rows = sb_get(
                "document_library",
                {
                    "select": "*",
                    "order": "created_at.desc",
                    "limit": "300",
                }
            )

        except Exception as e:

            rows = []

            flash(
                f"Could not load documents: {e}",
                "danger"
            )

    return page(
        "Learning Resources",
        r"""

<div class="card">

<h1>
Learning Resources
</h1>

<form method="get">

<input
 name="q"
 value="{{ q }}"
 placeholder="Search documents"
>

<button>
Search
</button>

</form>

</div>

<div class="grid">

{% for d in rows %}

<div class="card">

<h3>
{{ d.title }}
</h3>

<p>
{{ d.description or "" }}
</p>

<p class="muted">

{{ d.subject or "" }}

{{ d.course or "" }}

{{ d.class_level or "" }}

</p>

{% if d.file_url %}

<a
 class="btn"
 target="_blank"
 href="{{ d.file_url }}"
>
Open
</a>

{% elif d.file_path %}

<a
 class="btn"
 href="{{ url_for(
 'download_storage',
 path=d.file_path
 ) }}"
>
Download
</a>

{% endif %}

</div>

{% else %}

<div class="card">
No documents available.
</div>

{% endfor %}

</div>

""",
        rows=rows,
        q=q,
        source_table=source_table
    )


@app.route(
    "/storage/<path:path>"
)
@login_required
def download_storage(path):

    data, content_type = (
        storage_download(path)
    )

    user = current_user()

    log_activity(
        "download",
        path,
        user["id"],
        user["email"]
    )

    return send_file(
        io.BytesIO(data),
        mimetype=content_type,
        download_name=os.path.basename(
            path
        )
    )


# ============================================================
# CV BUILDER
# ============================================================

@app.route(
    "/cv",
    methods=["GET", "POST"]
)
@login_required
def cv_builder():

    user = current_user()

    existing = None

    try:

        rows = sb_get(
            "koja_cvs",
            {
                "select": "*",
                "user_id": (
                    f"eq.{user['id']}"
                ),
                "order": "created_at.desc",
                "limit": "1",
            }
        )

        if rows:
            existing = rows[0]

    except Exception:
        pass

    if request.method == "POST":

        data = {
            "user_id":
                user["id"],

            "full_name":
                clean(
                    request.form.get(
                        "full_name"
                    )
                ),

            "professional_title":
                clean(
                    request.form.get(
                        "professional_title"
                    )
                ),

            "email":
                clean(
                    request.form.get(
                        "email"
                    )
                ).lower(),

            "phone":
                clean(
                    request.form.get(
                        "phone"
                    )
                ),

            "address":
                clean(
                    request.form.get(
                        "address"
                    )
                ),

            "profile":
                clean(
                    request.form.get(
                        "profile"
                    )
                ),

            "education":
                clean(
                    request.form.get(
                        "education"
                    )
                ),

            "experience":
                clean(
                    request.form.get(
                        "experience"
                    )
                ),

            "skills":
                clean(
                    request.form.get(
                        "skills"
                    )
                ),

            "certifications":
                clean(
                    request.form.get(
                        "certifications"
                    )
                ),

            "languages":
                clean(
                    request.form.get(
                        "languages"
                    )
                ),

            "references":
                clean(
                    request.form.get(
                        "references"
                    )
                ),

            "updated_at":
                now_iso(),
        }

        try:

            if existing:

                cv = sb_update(
                    "koja_cvs",
                    {
                        "id": (
                            f"eq.{existing['id']}"
                        )
                    },
                    data
                )

            else:

                data["created_at"] = (
                    now_iso()
                )

                cv = sb_insert(
                    "koja_cvs",
                    data
                )

            existing = cv

            flash(
                "CV saved successfully.",
                "success"
            )

        except Exception as e:

            flash(
                "CV could not be saved. "
                "Make sure the koja_cvs table exists. "
                f"Details: {e}",
                "danger"
            )

    return page(
        "CV Builder",
        r"""

<div class="card">

<h1>
Professional CV Builder
</h1>

<p class="muted">
Complete the information below.
Your CV can be saved for later use.
</p>

<form method="post">

<div class="form-grid">

<div>

<label>
Full name
</label>

<input
 name="full_name"
 value="{{ existing.full_name if existing else user.name }}"
 required
>

</div>

<div>

<label>
Professional title
</label>

<input
 name="professional_title"
 value="{{ existing.professional_title if existing else '' }}"
 placeholder="e.g. Teacher, Accountant, Student"
>

</div>

<div>

<label>
Email
</label>

<input
 type="email"
 name="email"
 value="{{ existing.email if existing else user.email }}"
>

</div>

<div>

<label>
Phone
</label>

<input
 name="phone"
 value="{{ existing.phone if existing else user.phone or '' }}"
>

</div>

</div>

<label>
Address
</label>

<input
 name="address"
 value="{{ existing.address if existing else '' }}"
>

<label>
Professional Profile
</label>

<textarea
 name="profile"
 placeholder="Short professional summary"
>{{ existing.profile if existing else '' }}</textarea>

<label>
Education
</label>

<textarea
 name="education"
 placeholder="One qualification per line"
>{{ existing.education if existing else '' }}</textarea>

<label>
Work Experience
</label>

<textarea
 name="experience"
 placeholder="Position, organisation, dates and responsibilities"
>{{ existing.experience if existing else '' }}</textarea>

<label>
Skills
</label>

<textarea
 name="skills"
 placeholder="List your skills"
>{{ existing.skills if existing else '' }}</textarea>

<label>
Certifications
</label>

<textarea
 name="certifications"
>{{ existing.certifications if existing else '' }}</textarea>

<label>
Languages
</label>

<textarea
 name="languages"
>{{ existing.languages if existing else '' }}</textarea>

<label>
References
</label>

<textarea
 name="references"
>{{ existing.references if existing else '' }}</textarea>

<button>
Save CV
</button>

{% if existing %}

<a
 class="btn success"
 href="{{ url_for(
 'cv_pdf',
 cv_id=existing.id
 ) }}"
>
Download CV PDF
</a>

{% endif %}

</form>

</div>

"""
        ,
        existing=existing
    )


# ============================================================
# CV PDF
# ============================================================

@app.route(
    "/cv/<uuid:cv_id>/pdf"
)
@login_required
def cv_pdf(cv_id):

    user = current_user()

    try:

        cv = sb_get(
            "koja_cvs",
            {
                "select": "*",
                "id": (
                    f"eq.{cv_id}"
                ),
                "limit": "1",
            },
            single=True
        )

    except Exception as e:

        flash(
            f"Could not load CV: {e}",
            "danger"
        )

        return redirect(
            url_for("cv_builder")
        )

    if not cv:
        abort(404)

    if (
        not user["is_admin"]
        and str(cv.get("user_id"))
        != str(user["id"])
    ):
        abort(403)

    try:

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import (
            getSampleStyleSheet,
            ParagraphStyle
        )
        from reportlab.lib.enums import TA_CENTER
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            HRFlowable,
        )
        from reportlab.lib.units import cm

    except Exception:

        flash(
            "ReportLab is not installed. "
            "Add reportlab to requirements.txt.",
            "danger"
        )

        return redirect(
            url_for("cv_builder")
        )

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.7 * cm,
        leftMargin=1.7 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="KOJA Africa CV"
    )

    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "CVName",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=20,
        leading=24,
        spaceAfter=5,
    )

    title_style = ParagraphStyle(
        "CVTitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=11,
        leading=14,
        spaceAfter=10,
    )

    section_style = ParagraphStyle(
        "CVSection",
        parent=styles["Heading2"],
        fontSize=12,
        leading=15,
        spaceBefore=10,
        spaceAfter=5,
    )

    body_style = ParagraphStyle(
        "CVBody",
        parent=styles["BodyText"],
        fontSize=9.5,
        leading=13,
        spaceAfter=5,
    )

    story = []

    full_name = (
        cv.get("full_name")
        or "Curriculum Vitae"
    )

    story.append(
        Paragraph(
            full_name,
            name_style
        )
    )

    if cv.get(
        "professional_title"
    ):

        story.append(
            Paragraph(
                cv["professional_title"],
                title_style
            )
        )

    contact = " | ".join(
        x
        for x in [
            cv.get("email"),
            cv.get("phone"),
            cv.get("address"),
        ]
        if x
    )

    if contact:

        story.append(
            Paragraph(
                contact,
                title_style
            )
        )

    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            spaceAfter=8
        )
    )

    sections = [
        (
            "PROFESSIONAL PROFILE",
            cv.get("profile")
        ),
        (
            "EDUCATION",
            cv.get("education")
        ),
        (
            "WORK EXPERIENCE",
            cv.get("experience")
        ),
        (
            "SKILLS",
            cv.get("skills")
        ),
        (
            "CERTIFICATIONS",
            cv.get("certifications")
        ),
        (
            "LANGUAGES",
            cv.get("languages")
        ),
        (
            "REFERENCES",
            cv.get("references")
        ),
    ]

    for heading, value in sections:

        if not value:
            continue

        story.append(
            Paragraph(
                heading,
                section_style
            )
        )

        paragraphs = str(
            value
        ).splitlines()

        for paragraph in paragraphs:

            paragraph = clean(
                paragraph
            )

            if not paragraph:
                continue

            paragraph = (
                paragraph
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

            story.append(
                Paragraph(
                    paragraph,
                    body_style
                )
            )

    story.append(
        Spacer(
            1,
            15
        )
    )

    story.append(
        Paragraph(
            "Generated by KOJA AFRICA",
            body_style
        )
    )

    doc.build(story)

    buffer.seek(0)

    log_activity(
        "cv_pdf",
        f"Generated CV {cv_id}",
        user["id"],
        user["email"]
    )

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=(
            secure_filename(
                full_name
            )
            or "KOJA_CV"
        )
        + ".pdf"
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments")
@login_required
def assignments():

    user = current_user()

    rows = optional_get(
        "koja_assignments",
        {
            "select": "*",
            "student_id": (
                f"eq.{user['id']}"
            ),
            "order": "created_at.desc",
            "limit": "500",
        }
    )

    return page(
        "Assignments",
        r"""

<div class="actions">

<h1 style="margin-right:auto">
My Assignments
</h1>

<a
 class="btn"
 href="{{ url_for('new_assignment') }}"
>
Submit Assignment
</a>

</div>

<div class="grid">

{% for a in rows %}

<div class="card">

<h3>
{{ a.title }}
</h3>

<p>
<b>Subject:</b>
{{ a.subject or "-" }}
</p>

<p>
<b>Course:</b>
{{ a.course or "-" }}
</p>

<p>
<b>Status:</b>

<span class="badge">
{{ a.status or "submitted" }}
</span>

</p>

{% if a.description %}

<p>
{{ a.description }}
</p>

{% endif %}

{% if a.answer or a.admin_response %}

<hr>

<h3>
Administrator Response
</h3>

<p>
{{ a.answer
or a.admin_response }}
</p>

{% endif %}

{% if a.file_url %}

<a
 class="btn"
 target="_blank"
 href="{{ a.file_url }}"
>
Open Assignment
</a>

{% elif a.file_path %}

<a
 class="btn"
 href="{{ url_for(
 'download_storage',
 path=a.file_path
 ) }}"
>
Download Assignment
</a>

{% endif %}

</div>

{% else %}

<div class="card">

<p>
No assignments submitted yet.
</p>

<a
 class="btn"
 href="{{ url_for('new_assignment') }}"
>
Submit Assignment
</a>

</div>

{% endfor %}

</div>

""",
        rows=rows
    )


@app.route(
    "/assignments/new",
    methods=["GET", "POST"]
)
@login_required
def new_assignment():

    user = current_user()

    if request.method == "POST":

        title = clean(
            request.form.get(
                "title"
            )
        )

        if not title:

            flash(
                "Assignment title is required.",
                "danger"
            )

            return redirect(
                url_for("new_assignment")
            )

        file = request.files.get(
            "file"
        )

        file_path = None
        file_url = None
        file_name = None
        file_size = 0
        mime_type = None

        try:

            if file and file.filename:

                (
                    file_path,
                    file_url,
                    file_name,
                    file_size,
                    mime_type
                ) = storage_upload(
                    file,
                    "assignments"
                )

            data = {
                "student_id":
                    user["id"],

                "student_name":
                    user["name"],

                "student_email":
                    user["email"],

                "title":
                    title,

                "subject":
                    clean(
                        request.form.get(
                            "subject"
                        )
                    ),

                "course":
                    clean(
                        request.form.get(
                            "course"
                        )
                    ),

                "class_level":
                    clean(
                        request.form.get(
                            "class_level"
                        )
                    ),

                "description":
                    clean(
                        request.form.get(
                            "description"
                        )
                    ),

                "status":
                    "submitted",

                "file_path":
                    file_path,

                "file_url":
                    file_url,

                "file_name":
                    file_name,

                "file_size":
                    file_size,

                "mime_type":
                    mime_type,

                "created_at":
                    now_iso(),
            }

            assignment = sb_insert(
                "koja_assignments",
                data
            )

            log_activity(
                "assignment",
                (
                    "Assignment submitted: "
                    f"{title}"
                ),
                user["id"],
                user["email"]
            )

            notify(
                ADMIN_EMAIL,
                "New assignment submitted",
                (
                    f"{user['name']} submitted "
                    f"an assignment: {title}."
                )
            )

            flash(
                "Assignment submitted successfully.",
                "success"
            )

            return redirect(
                url_for("assignments")
            )

        except Exception as e:

            log.exception(
                "Assignment submission failed"
            )

            flash(
                "Assignment submission failed. "
                "Make sure the koja_assignments table "
                "exists and the storage bucket is configured. "
                f"Details: {e}",
                "danger"
            )

    return page(
        "Submit Assignment",
        r"""

<div class="card">

<h1>
Submit Assignment
</h1>

<form
 method="post"
 enctype="multipart/form-data"
>

<label>
Assignment title
</label>

<input
 name="title"
 required
>

<label>
Subject
</label>

<input
 name="subject"
>

<label>
Course
</label>

<input
 name="course"
>

<label>
Class / Level
</label>

<input
 name="class_level"
>

<label>
Description / instructions
</label>

<textarea
 name="description"
></textarea>

<label>
Assignment file
</label>

<input
 type="file"
 name="file"
 accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.jpg,.jpeg,.png"
>

<p class="muted small">
Maximum configured file size:
{{ max_upload_mb }} MB.
</p>

<button>
Submit Assignment
</button>

</form>

</div>

""",
        max_upload_mb=MAX_UPLOAD_MB
    )


# ============================================================
# SERVICES HOME
# ============================================================

@app.route("/services")
@login_required
def services():

    user = current_user()

    rows = optional_get(
        "koja_service_requests",
        {
            "select": "*",
            "client_email": (
                f"eq.{user['email']}"
            ),
            "order": "created_at.desc",
            "limit": "500",
        }
    )

    return page(
        "KOJA Services",
        r"""

<div class="hero">

<h1>
KOJA Services
</h1>

<p>
Access additional services through
your KOJA account.
</p>

<div class="actions">

<a
 class="btn"
 href="{{ url_for('farmer_registration') }}"
>
Farmer Registration
</a>

<a
 class="btn"
 href="{{ url_for('doctor_booking') }}"
>
Doctor Booking
</a>

<a
 class="btn"
 href="{{ url_for('delivery_request') }}"
>
Delivery Request
</a>

</div>

</div>

<br>

<div class="card">

<h2>
My Service Requests
</h2>

<table>

<tr>
<th>Type</th>
<th>Title</th>
<th>Status</th>
<th>Date</th>
</tr>

{% for r in rows %}

<tr>

<td>
{{ r.request_type
or r.type
or "-" }}
</td>

<td>
{{ r.title or "-" }}
</td>

<td>

<span class="badge">
{{ r.status or "submitted" }}
</span>

</td>

<td>
{{ r.created_at or "-" }}
</td>

</tr>

{% else %}

<tr>
<td colspan="4">
No service requests.
</td>
</tr>

{% endfor %}

</table>

</div>

"""
        ,
        rows=rows
    )


# ============================================================
# GENERIC SERVICE INSERT
# ============================================================

def create_service_request(
    request_type,
    title,
    description,
    user,
    metadata=None
):
    """
    Uses koja_service_requests as the common service queue.

    The richer metadata field is attempted first. If the
    installation does not have metadata, the core request is
    inserted without it.
    """

    base = {
        "client_email":
            user["email"],

        "title":
            title,

        "description":
            description,

        "status":
            "submitted",

        "created_at":
            now_iso(),
    }

    # request_type is expected in the newer schema.
    # If it does not exist, retry without it.
    if request_type:
        base["request_type"] = (
            request_type
        )

    if metadata is not None:
        base["metadata"] = (
            json_text(metadata)
        )

    try:

        return sb_insert(
            "koja_service_requests",
            base
        )

    except Exception as first_error:

        retry = dict(base)

        retry.pop(
            "metadata",
            None
        )

        try:

            return sb_insert(
                "koja_service_requests",
                retry
            )

        except Exception:

            retry.pop(
                "request_type",
                None
            )

            return sb_insert(
                "koja_service_requests",
                retry
            )


# ============================================================
# FARMER REGISTRATION
# ============================================================

@app.route(
    "/farmer-registration",
    methods=["GET", "POST"]
)
@login_required
def farmer_registration():

    user = current_user()

    if request.method == "POST":

        farmer_name = clean(
            request.form.get(
                "farmer_name"
            )
        )

        if not farmer_name:

            flash(
                "Farmer name is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "farmer_registration"
                )
            )

        metadata = {
            "farmer_name":
                farmer_name,

            "phone":
                clean(
                    request.form.get(
                        "phone"
                    )
                ),

            "nrc":
                clean(
                    request.form.get(
                        "nrc"
                    )
                ),

            "province":
                clean(
                    request.form.get(
                        "province"
                    )
                ),

            "district":
                clean(
                    request.form.get(
                        "district"
                    )
                ),

            "chiefdom":
                clean(
                    request.form.get(
                        "chiefdom"
                    )
                ),

            "camp":
                clean(
                    request.form.get(
                        "camp"
                    )
                ),

            "farm_location":
                clean(
                    request.form.get(
                        "farm_location"
                    )
                ),

            "farm_size":
                clean(
                    request.form.get(
                        "farm_size"
                    )
                ),

            "crops":
                clean(
                    request.form.get(
                        "crops"
                    )
                ),

            "livestock":
                clean(
                    request.form.get(
                        "livestock"
                    )
                ),

            "farmer_type":
                clean(
                    request.form.get(
                        "farmer_type"
                    )
                ),

            "additional_information":
                clean(
                    request.form.get(
                        "additional_information"
                    )
                ),
        }

        try:

            result = create_service_request(
                "farmer_registration",
                "Farmer Registration",
                (
                    f"Farmer registration for "
                    f"{farmer_name}"
                ),
                user,
                metadata
            )

            log_activity(
                "farmer_registration",
                farmer_name,
                user["id"],
                user["email"]
            )

            notify(
                ADMIN_EMAIL,
                "New farmer registration",
                (
                    f"{farmer_name} submitted "
                    "a farmer registration."
                )
            )

            flash(
                "Farmer registration submitted successfully.",
                "success"
            )

            return redirect(
                url_for("services")
            )

        except Exception as e:

            flash(
                f"Farmer registration failed: {e}",
                "danger"
            )

    return page(
        "Farmer Registration",
        r"""

<div class="card">

<h1>
Farmer Registration
</h1>

<p>
Register your farming details with KOJA.
</p>

<form method="post">

<label>
Farmer full name
</label>

<input
 name="farmer_name"
 value="{{ user.name }}"
 required
>

<label>
Phone
</label>

<input
 name="phone"
 value="{{ user.phone or '' }}"
>

<label>
NRC
</label>

<input
 name="nrc"
>

<div class="form-grid">

<div>

<label>
Province
</label>

<input
 name="province"
>

</div>

<div>

<label>
District
</label>

<input
 name="district"
>

</div>

<div>

<label>
Chiefdom
</label>

<input
 name="chiefdom"
>

</div>

<div>

<label>
Agricultural camp
</label>

<input
 name="camp"
>

</div>

</div>

<label>
Farm location
</label>

<input
 name="farm_location"
>

<div class="form-grid">

<div>

<label>
Farm size
</label>

<input
 name="farm_size"
 placeholder="e.g. 5 hectares"
>

</div>

<div>

<label>
Farmer type
</label>

<select name="farmer_type">

<option>
Small-scale
</option>

<option>
Commercial
</option>

<option>
Emerging
</option>

<option>
Cooperative
</option>

</select>

</div>

</div>

<label>
Crops
</label>

<textarea
 name="crops"
 placeholder="e.g. maize, soya beans, groundnuts"
></textarea>

<label>
Livestock
</label>

<textarea
 name="livestock"
 placeholder="e.g. cattle, goats, chickens"
></textarea>

<label>
Additional information
</label>

<textarea
 name="additional_information"
></textarea>

<button>
Register Farmer
</button>

</form>

</div>

"""
    )


# ============================================================
# DOCTOR BOOKING
# ============================================================

@app.route(
    "/doctor-booking",
    methods=["GET", "POST"]
)
@login_required
def doctor_booking():

    user = current_user()

    if request.method == "POST":

        doctor_name = clean(
            request.form.get(
                "doctor_name"
            )
        )

        booking_date = clean(
            request.form.get(
                "booking_date"
            )
        )

        booking_time = clean(
            request.form.get(
                "booking_time"
            )
        )

        if not booking_date:

            flash(
                "Booking date is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "doctor_booking"
                )
            )

        metadata = {
            "patient_name":
                clean(
                    request.form.get(
                        "patient_name"
                    )
                ) or user["name"],

            "patient_phone":
                clean(
                    request.form.get(
                        "patient_phone"
                    )
                ) or user.get(
                    "phone",
                    ""
                ),

            "doctor_name":
                doctor_name,

            "facility":
                clean(
                    request.form.get(
                        "facility"
                    )
                ),

            "booking_date":
                booking_date,

            "booking_time":
                booking_time,

            "service":
                clean(
                    request.form.get(
                        "service"
                    )
                ),

            "reason":
                clean(
                    request.form.get(
                        "reason"
                    )
                ),

            "additional_information":
                clean(
                    request.form.get(
                        "additional_information"
                    )
                ),
        }

        try:

            create_service_request(
                "doctor_booking",
                "Doctor Booking",
                (
                    f"Doctor booking for "
                    f"{metadata['patient_name']} "
                    f"on {booking_date} "
                    f"{booking_time}"
                ),
                user,
                metadata
            )

            log_activity(
                "doctor_booking",
                "Doctor appointment request",
                user["id"],
                user["email"]
            )

            notify(
                ADMIN_EMAIL,
                "New doctor booking",
                (
                    f"{metadata['patient_name']} "
                    "submitted a doctor booking."
                )
            )

            flash(
                "Doctor booking request submitted.",
                "success"
            )

            return redirect(
                url_for("services")
            )

        except Exception as e:

            flash(
                f"Doctor booking failed: {e}",
                "danger"
            )

    return page(
        "Doctor Booking",
        r"""

<div class="card">

<h1>
Book a Doctor
</h1>

<p>
Submit a healthcare appointment request.
The administrator can review and confirm it.
</p>

<form method="post">

<label>
Patient name
</label>

<input
 name="patient_name"
 value="{{ user.name }}"
 required
>

<label>
Patient phone
</label>

<input
 name="patient_phone"
 value="{{ user.phone or '' }}"
>

<label>
Doctor name
</label>

<input
 name="doctor_name"
 placeholder="Preferred doctor, if known"
>

<label>
Clinic / Hospital
</label>

<input
 name="facility"
>

<div class="form-grid">

<div>

<label>
Appointment date
</label>

<input
 type="date"
 name="booking_date"
 required
>

</div>

<div>

<label>
Preferred time
</label>

<input
 type="time"
 name="booking_time"
>

</div>

</div>

<label>
Service
</label>

<select name="service">

<option>
General consultation
</option>

<option>
Follow-up
</option>

<option>
Dental
</option>

<option>
Eye clinic
</option>

<option>
Maternal health
</option>

<option>
Child health
</option>

<option>
Other
</option>

</select>

<label>
Reason for appointment
</label>

<textarea
 name="reason"
></textarea>

<label>
Additional information
</label>

<textarea
 name="additional_information"
></textarea>

<button>
Submit Booking
</button>

</form>

</div>

"""
    )


# ============================================================
# DELIVERY REQUEST
# ============================================================

@app.route(
    "/delivery",
    methods=["GET", "POST"]
)
@login_required
def delivery_request():

    user = current_user()

    if request.method == "POST":

        sender = clean(
            request.form.get(
                "sender_name"
            )
        ) or user["name"]

        receiver = clean(
            request.form.get(
                "receiver_name"
            )
        )

        pickup = clean(
            request.form.get(
                "pickup_location"
            )
        )

        destination = clean(
            request.form.get(
                "delivery_location"
            )
        )

        if not receiver:
            flash(
                "Receiver name is required.",
                "danger"
            )

            return redirect(
                url_for(
                    "delivery_request"
                )
            )

        if not pickup or not destination:

            flash(
                "Pickup and delivery locations are required.",
                "danger"
            )

            return redirect(
                url_for(
                    "delivery_request"
                )
            )

        metadata = {

            "sender_name":
                sender,

            "sender_phone":
                clean(
                    request.form.get(
                        "sender_phone"
                    )
                ) or user.get(
                    "phone",
                    ""
                ),

            "receiver_name":
                receiver,

            "receiver_phone":
                clean(
                    request.form.get(
                        "receiver_phone"
                    )
                ),

            "pickup_location":
                pickup,

            "delivery_location":
                destination,

            "package_description":
                clean(
                    request.form.get(
                        "package_description"
                    )
                ),

            "package_size":
                clean(
                    request.form.get(
                        "package_size"
                    )
                ),

            "preferred_date":
                clean(
                    request.form.get(
                        "preferred_date"
                    )
                ),

            "preferred_time":
                clean(
                    request.form.get(
                        "preferred_time"
                    )
                ),

            "delivery_notes":
                clean(
                    request.form.get(
                        "delivery_notes"
                    )
                ),
        }

        try:

            create_service_request(
                "delivery",
                "Delivery Request",
                (
                    f"Delivery from "
                    f"{pickup} to "
                    f"{destination}"
                ),
                user,
                metadata
            )

            log_activity(
                "delivery_request",
                (
                    f"{pickup} -> "
                    f"{destination}"
                ),
                user["id"],
                user["email"]
            )

            notify(
                ADMIN_EMAIL,
                "New delivery request",
                (
                    f"New delivery request from "
                    f"{sender}."
                )
            )

            flash(
                "Delivery request submitted successfully.",
                "success"
            )

            return redirect(
                url_for("services")
            )

        except Exception as e:

            flash(
                f"Delivery request failed: {e}",
                "danger"
            )

    return page(
        "Delivery Request",
        r"""

<div class="card">

<h1>
Request a Delivery
</h1>

<form method="post">

<label>
Sender name
</label>

<input
 name="sender_name"
 value="{{ user.name }}"
>

<label>
Sender phone
</label>

<input
 name="sender_phone"
 value="{{ user.phone or '' }}"
>

<label>
Receiver name
</label>

<input
 name="receiver_name"
 required
>

<label>
Receiver phone
</label>

<input
 name="receiver_phone"
>

<label>
Pickup location
</label>

<textarea
 name="pickup_location"
 required
></textarea>

<label>
Delivery location
</label>

<textarea
 name="delivery_location"
 required
></textarea>

<label>
Package description
</label>

<textarea
 name="package_description"
 placeholder="What is being delivered?"
></textarea>

<label>
Package size
</label>

<select name="package_size">

<option>
Small
</option>

<option>
Medium
</option>

<option>
Large
</option>

<option>
Very large
</option>

</select>

<div class="form-grid">

<div>

<label>
Preferred date
</label>

<input
 type="date"
 name="preferred_date"
>

</div>

<div>

<label>
Preferred time
</label>

<input
 type="time"
 name="preferred_time"
>

</div>

</div>

<label>
Delivery notes
</label>

<textarea
 name="delivery_notes"
></textarea>

<button>
Request Delivery
</button>

</form>

</div>

"""
    )


# ============================================================
# ALIASES
# ============================================================

@app.route(
    "/farmer"
)
@login_required
def farmer_alias():

    return redirect(
        url_for(
            "farmer_registration"
        )
    )


@app.route(
    "/doctor"
)
@login_required
def doctor_alias():

    return redirect(
        url_for(
            "doctor_booking"
        )
    )


@app.route(
    "/deliveries"
)
@login_required
def deliveries_alias():

    return redirect(
        url_for(
            "delivery_request"
        )
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    stats = {

        "Universities":
            count_rows(
                "universities"
            ),

        "Programmes":
            count_rows(
                "university_programmes"
            ),

        "Applications":
            count_rows(
                "university_applications"
            ),

        "Questions":
            count_rows(
                "questions"
            ),

        "Documents":
            count_rows(
                "documents"
            ),

        "Users":
            count_rows(
                "profiles"
            ),

        "CVs":
            count_rows(
                "koja_cvs"
            ),

        "Assignments":
            count_rows(
                "koja_assignments"
            ),

        "Service requests":
            count_rows(
                "koja_service_requests"
            ),
    }

    applications = optional_get(
        "university_applications",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "20",
        }
    )

    services_ = optional_get(
        "koja_service_requests",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "20",
        }
    )

    assignments_ = optional_get(
        "koja_assignments",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "20",
        }
    )

    return page(
        "Admin Dashboard",
        r"""

<div class="hero">

<h1>
KOJA Administrator
</h1>

<p>
Manage KOJA Africa.
</p>

<div class="actions">

<a
 class="btn"
 href="{{ url_for(
 'admin_universities'
 ) }}"
>
Universities
</a>

<a
 class="btn"
 href="{{ url_for(
 'admin_programmes'
 ) }}"
>
Programmes
</a>

<a
 class="btn"
 href="{{ url_for(
 'admin_applications'
 ) }}"
>
Applications
</a>

<a
 class="btn"
 href="{{ url_for(
 'admin_questions'
 ) }}"
>
Questions
</a>

<a
 class="btn"
 href="{{ url_for(
 'admin_services'
 ) }}"
>
Services
</a>

<a
 class="btn"
 href="{{ url_for(
 'admin_assignments'
 ) }}"
>
Assignments
</a>

</div>

</div>

<br>

<div class="grid">

{% for name,value in stats.items() %}

<div class="card">

<div class="stat">
{{ value }}
</div>

<div class="muted">
{{ name }}
</div>

</div>

{% endfor %}

</div>

<br>

<div class="grid">

<div class="card">

<h2>
Admissions
</h2>

<a
 class="btn"
 href="{{ url_for(
 'admin_applications'
 ) }}"
>
Manage Applications
</a>

</div>

<div class="card">

<h2>
Academic
</h2>

<a
 class="btn"
 href="{{ url_for(
 'admin_questions'
 ) }}"
>
Manage Questions
</a>

<a
 class="btn secondary"
 href="{{ url_for(
 'admin_assignments'
 ) }}"
>
Assignments
</a>

</div>

<div class="card">

<h2>
Services
</h2>

<a
 class="btn"
 href="{{ url_for(
 'admin_services'
 ) }}"
>
Manage Service Requests
</a>

</div>

<div class="card">

<h2>
System
</h2>

<a
 class="btn secondary"
 href="{{ url_for('health') }}"
>
System Health
</a>

</div>

</div>

<br>

<div class="card">

<h2>
Recent Applications
</h2>

<table>

<tr>

<th>
Applicant
</th>

<th>
University
</th>

<th>
Programme
</th>

<th>
Status
</th>

</tr>

{% for a in applications %}

<tr>

<td>
{{ a.full_name }}
</td>

<td>
{{ a.university }}
</td>

<td>
{{ a.programme }}
</td>

<td>
{{ a.application_status
or a.status }}
</td>

</tr>

{% else %}

<tr>
<td colspan="4">
No applications.
</td>
</tr>

{% endfor %}

</table>

</div>

<br>

<div class="card">

<h2>
Recent Service Requests
</h2>

<table>

<tr>

<th>
Type
</th>

<th>
Title
</th>

<th>
Email
</th>

<th>
Status
</th>

</tr>

{% for r in services %}

<tr>

<td>
{{ r.request_type
or r.type
or "-" }}
</td>

<td>
{{ r.title }}
</td>

<td>
{{ r.client_email }}
</td>

<td>
{{ r.status
or "submitted" }}
</td>

</tr>

{% else %}

<tr>
<td colspan="4">
No service requests.
</td>
</tr>

{% endfor %}

</table>

</div>

"""
        ,
        stats=stats,
        applications=applications,
        services=services_,
        assignments=assignments_
    )


# ============================================================
# ADMIN UNIVERSITIES
# ============================================================

@app.route("/admin/universities")
@admin_required
def admin_universities():

    rows = optional_get(
        "universities",
        {
            "select": "*",
            "order": "name.asc",
            "limit": "1000",
        }
    )

    return page(
        "Manage Universities",
        r"""

<div class="actions">

<h1 style="margin-right:auto">
Universities
</h1>

<a
 class="btn"
 href="{{ url_for(
 'admin_university_new'
 ) }}"
>
Add University
</a>

</div>

<div class="card">

<table>

<tr>

<th>
Name
</th>

<th>
Province
</th>

<th>
Status
</th>

<th>
Actions
</th>

</tr>

{% for u in rows %}

<tr>

<td>
{{ u.name }}
</td>

<td>
{{ u.province or "-" }}
</td>

<td>
{{ "Active" if u.is_active else "Inactive" }}
</td>

<td>

<a
 class="btn"
 href="{{ url_for(
 'admin_university_edit',
 university_id=u.id
 ) }}"
>
Edit
</a>

</td>

</tr>

{% endfor %}

</table>

</div>

"""
        ,
        rows=rows
    )


def university_form_data():

    return {

        "name":
            clean(
                request.form.get(
                    "name"
                )
            ),

        "abbreviation":
            clean(
                request.form.get(
                    "abbreviation"
                )
            ),

        "institution_type":
            clean(
                request.form.get(
                    "institution_type"
                )
            ),

        "ownership":
            clean(
                request.form.get(
                    "ownership"
                )
            ),

        "province":
            clean(
                request.form.get(
                    "province"
                )
            ),

        "district":
            clean(
                request.form.get(
                    "district"
                )
            ),

        "campus":
            clean(
                request.form.get(
                    "campus"
                )
            ),

        "location":
            clean(
                request.form.get(
                    "location"
                )
            ),

        "description":
            clean(
                request.form.get(
                    "description"
                )
            ),

        "website":
            clean(
                request.form.get(
                    "website"
                )
            ),

        "application_url":
            clean(
                request.form.get(
                    "application_url"
                )
            ),

        "admissions_url":
            clean(
                request.form.get(
                    "admissions_url"
                )
            ),

        "admissions_email":
            clean(
                request.form.get(
                    "admissions_email"
                )
            ),

        "admissions_phone":
            clean(
                request.form.get(
                    "admissions_phone"
                )
            ),

        "application_fee_zmw":
            request.form.get(
                "application_fee_zmw"
            )
            or None,

        "intake":
            clean(
                request.form.get(
                    "intake"
                )
            ),

        "application_status":
            clean(
                request.form.get(
                    "application_status"
                )
            )
            or "unknown",

        "deadline":
            request.form.get(
                "deadline"
            )
            or None,

        "accreditation_status":
            clean(
                request.form.get(
                    "accreditation_status"
                )
            ),

        "general_requirements":
            clean(
                request.form.get(
                    "general_requirements"
                )
            ),

        "required_documents":
            clean(
                request.form.get(
                    "required_documents"
                )
            ),

        "application_instructions":
            clean(
                request.form.get(
                    "application_instructions"
                )
            ),

        "undergraduate_admissions_url":
            clean(
                request.form.get(
                    "undergraduate_admissions_url"
                )
            ),

        "postgraduate_admissions_url":
            clean(
                request.form.get(
                    "postgraduate_admissions_url"
                )
            ),

        "contact_person":
            clean(
                request.form.get(
                    "contact_person"
                )
            ),

        "is_active":
            request.form.get(
                "is_active"
            ) == "on",

        "last_verified_at":
            now_iso(),

        "last_admissions_check":
            now_iso(),
    }


def university_form_page(
    title,
    university=None
):

    return page(
        title,
        r"""

<div class="card">

<h1>
{{ title }}
</h1>

<form method="post">

<div class="form-grid">

{% for field,label in [

("name","University name"),

("abbreviation","Abbreviation"),

("institution_type","Institution type"),

("ownership","Ownership"),

("province","Province"),

("district","District"),

("campus","Campus"),

("location","Location"),

("website","Website"),

("application_url","Application URL"),

("admissions_url","Admissions URL"),

("admissions_email","Admissions email"),

("admissions_phone","Admissions phone"),

("application_fee_zmw","Application fee ZMW"),

("intake","Intake"),

("deadline","Deadline"),

("accreditation_status","Accreditation status"),

("undergraduate_admissions_url",
"Undergraduate admissions URL"),

("postgraduate_admissions_url",
"Postgraduate admissions URL"),

("contact_person","Contact person")

] %}

<div>

<label>
{{ label }}
</label>

<input
 name="{{ field }}"
 value="{{ university.get(field,'') if university else '' }}"
>

</div>

{% endfor %}

</div>

<label>
Description
</label>

<textarea
 name="description"
>{{ university.get('description','') if university else '' }}</textarea>

<label>
General requirements
</label>

<textarea
 name="general_requirements"
>{{ university.get('general_requirements','') if university else '' }}</textarea>

<label>
Required documents
</label>

<textarea
 name="required_documents"
>{{ university.get('required_documents','') if university else '' }}</textarea>

<label>
Application instructions
</label>

<textarea
 name="application_instructions"
>{{ university.get('application_instructions','') if university else '' }}</textarea>

<label>
Application status
</label>

<select name="application_status">

{% for x in [
'unknown',
'open',
'closed',
'active',
'not_open'
] %}

<option
 value="{{ x }}"
 {% if university
 and university.application_status ==
 x %}
 selected
 {% endif %}
>

{{ x }}

</option>

{% endfor %}

</select>

<label>

<input
 type="checkbox"
 name="is_active"
 {% if not university
 or university.is_active %}
 checked
 {% endif %}
>

Active

</label>

<br>

<button>
Save University
</button>

</form>

</div>

"""
        ,
        title=title,
        university=university
    )


@app.route(
    "/admin/universities/new",
    methods=["GET", "POST"]
)
@admin_required
def admin_university_new():

    if request.method == "POST":

        try:

            sb_insert(
                "universities",
                university_form_data()
            )

            flash(
                "University added.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_universities"
                )
            )

        except Exception as e:

            flash(
                f"Could not add university: {e}",
                "danger"
            )

    return university_form_page(
        "Add University"
    )


@app.route(
    "/admin/universities/<uuid:university_id>/edit",
    methods=["GET", "POST"]
)
@admin_required
def admin_university_edit(
    university_id
):

    university = sb_get(
        "universities",
        {
            "select": "*",
            "id": (
                f"eq.{university_id}"
            ),
            "limit": "1",
        },
        single=True
    )

    if not university:
        abort(404)

    if request.method == "POST":

        try:

            sb_update(
                "universities",
                {
                    "id": (
                        f"eq.{university_id}"
                    )
                },
                university_form_data()
            )

            flash(
                "University updated.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_universities"
                )
            )

        except Exception as e:

            flash(
                f"Could not update university: {e}",
                "danger"
            )

    return university_form_page(
        "Edit University",
        university
    )


# ============================================================
# ADMIN PROGRAMMES
# ============================================================

@app.route("/admin/programmes")
@admin_required
def admin_programmes():

    university_id = clean(
        request.args.get(
            "university_id"
        )
    )

    us = optional_get(
        "universities",
        {
            "select": "id,name",
            "order": "name.asc",
            "limit": "1000",
        }
    )

    params = {
        "select": "*",
        "order": "programme_name.asc",
        "limit": "2000",
    }

    if university_id:

        params["university_id"] = (
            f"eq.{university_id}"
        )

    ps = optional_get(
        "university_programmes",
        params
    )

    names = {
        str(u.get("id")):
        u.get("name")
        for u in us
    }

    for p in ps:

        p["_university_name"] = names.get(
            str(
                p.get(
                    "university_id"
                )
            ),
            "Unknown"
        )

    return page(
        "Manage Programmes",
        r"""

<div class="actions">

<h1 style="margin-right:auto">
Programmes
</h1>

<a
 class="btn"
 href="{{ url_for(
 'admin_programme_new'
 ) }}"
>
Add Programme
</a>

</div>

<div class="card">

<form method="get">

<select
 name="university_id"
>

<option value="">
All universities
</option>

{% for u in us %}

<option
 value="{{ u.id }}"
 {% if university_id ==
 u.id|string %}
 selected
 {% endif %}
>

{{ u.name }}

</option>

{% endfor %}

</select>

<button>
Filter
</button>

</form>

</div>

<div class="card">

<table>

<tr>

<th>
Programme
</th>

<th>
University
</th>

<th>
Subjects
</th>

<th>
Minimum
</th>

<th>
Status
</th>

<th>
Actions
</th>

</tr>

{% for p in ps %}

<tr>

<td>
{{ p.programme_name }}
</td>

<td>
{{ p._university_name }}
</td>

<td>
{{ p.required_subjects or "-" }}
</td>

<td>
{{ p.minimum_grade
or p.minimum_points
or "-" }}
</td>

<td>
{{ p.application_status
or "-" }}
</td>

<td>

<a
 class="btn"
 href="{{ url_for(
 'admin_programme_edit',
 programme_id=p.id
 ) }}"
>
Edit
</a>

<a
 class="btn secondary"
 href="{{ url_for(
 'admin_requirements',
 programme_id=p.id
 ) }}"
>
Requirements
</a>

</td>

</tr>

{% endfor %}

</table>

</div>

"""
        ,
        us=us,
        ps=ps,
        university_id=university_id
    )


def programme_form_data():

    return {

        "university_id":
            request.form.get(
                "university_id"
            )
            or None,

        "programme_name":
            clean(
                request.form.get(
                    "programme_name"
                )
            ),

        "programme_code":
            clean(
                request.form.get(
                    "programme_code"
                )
            ),

        "qualification_level":
            clean(
                request.form.get(
                    "qualification_level"
                )
            ),

        "qualification":
            clean(
                request.form.get(
                    "qualification"
                )
            ),

        "faculty":
            clean(
                request.form.get(
                    "faculty"
                )
            ),

        "school":
            clean(
                request.form.get(
                    "school"
                )
            ),

        "duration":
            clean(
                request.form.get(
                    "duration"
                )
            ),

        "study_mode":
            clean(
                request.form.get(
                    "study_mode"
                )
            ),

        "entry_level":
            clean(
                request.form.get(
                    "entry_level"
                )
            ),

        "requirements":
            clean(
                request.form.get(
                    "requirements"
                )
            ),

        "entry_requirements":
            clean(
                request.form.get(
                    "entry_requirements"
                )
            ),

        "application_requirements":
            clean(
                request.form.get(
                    "application_requirements"
                )
            ),

        "required_subjects":
            clean(
                request.form.get(
                    "required_subjects"
                )
            ),

        "minimum_grade":
            clean(
                request.form.get(
                    "minimum_grade"
                )
            ),

        "application_url":
            clean(
                request.form.get(
                    "application_url"
                )
            ),

        "application_status":
            clean(
                request.form.get(
                    "application_status"
                )
            )
            or "unknown",

        "deadline":
            request.form.get(
                "deadline"
            )
            or None,

        "application_fee":
            request.form.get(
                "application_fee"
            )
            or None,

        "currency":
            clean(
                request.form.get(
                    "currency"
                )
            )
            or "ZMW",

        "description":
            clean(
                request.form.get(
                    "description"
                )
            ),

        "programme_type":
            clean(
                request.form.get(
                    "programme_type"
                )
            ),

        "campus":
            clean(
                request.form.get(
                    "campus"
                )
            ),

        "study_duration":
            clean(
                request.form.get(
                    "study_duration"
                )
            ),

        "minimum_points":
            request.form.get(
                "minimum_points"
            )
            or None,

        "admissions_url":
            clean(
                request.form.get(
                    "admissions_url"
                )
            ),

        "last_verified_at":
            now_iso(),

        "is_active":
            request.form.get(
                "is_active"
            ) == "on",
    }


def programme_form_page(
    title,
    programme=None
):

    us = optional_get(
        "universities",
        {
            "select": "id,name",
            "order": "name.asc",
            "limit": "1000",
        }
    )

    return page(
        title,
        r"""

<div class="card">

<h1>
{{ title }}
</h1>

<form method="post">

<label>
University
</label>

<select
 name="university_id"
 required
>

<option value="">
Select university
</option>

{% for u in us %}

<option
 value="{{ u.id }}"
 {% if programme
 and programme.university_id|string ==
 u.id|string %}
 selected
 {% endif %}
>

{{ u.name }}

</option>

{% endfor %}

</select>

<div class="form-grid">

{% for field,label in [

("programme_name","Programme name"),

("programme_code","Programme code"),

("qualification_level","Qualification level"),

("qualification","Qualification"),

("faculty","Faculty"),

("school","School"),

("duration","Duration"),

("study_mode","Study mode"),

("entry_level","Entry level"),

("required_subjects","Required subjects"),

("minimum_grade","Minimum grade"),

("application_url","Application URL"),

("deadline","Deadline"),

("application_fee","Application fee"),

("currency","Currency"),

("programme_type","Programme type"),

("campus","Campus"),

("study_duration","Study duration"),

("minimum_points","Minimum points"),

("admissions_url","Admissions URL")

] %}

<div>

<label>
{{ label }}
</label>

<input
 name="{{ field }}"
 value="{{ programme.get(field,'') if programme else '' }}"
>

</div>

{% endfor %}

</div>

<label>
Requirements
</label>

<textarea
 name="requirements"
>{{ programme.get('requirements','') if programme else '' }}</textarea>

<label>
Entry requirements
</label>

<textarea
 name="entry_requirements"
>{{ programme.get('entry_requirements','') if programme else '' }}</textarea>

<label>
Application requirements
</label>

<textarea
 name="application_requirements"
>{{ programme.get('application_requirements','') if programme else '' }}</textarea>

<label>
Description
</label>

<textarea
 name="description"
>{{ programme.get('description','') if programme else '' }}</textarea>

<label>
Application status
</label>

<select name="application_status">

{% for x in [
'unknown',
'active',
'open',
'closed'
] %}

<option
 value="{{ x }}"
 {% if programme
 and programme.application_status ==
 x %}
 selected
 {% endif %}
>

{{ x }}

</option>

{% endfor %}

</select>

<label>

<input
 type="checkbox"
 name="is_active"
 {% if not programme
 or programme.is_active %}
 checked
 {% endif %}
>

Active

</label>

<br>

<button>
Save Programme
</button>

</form>

</div>

"""
        ,
        title=title,
        programme=programme,
        us=us
    )


@app.route(
    "/admin/programmes/new",
    methods=["GET", "POST"]
)
@admin_required
def admin_programme_new():

    if request.method == "POST":

        try:

            sb_insert(
                "university_programmes",
                programme_form_data()
            )

            flash(
                "Programme added.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_programmes"
                )
            )

        except Exception as e:

            flash(
                f"Could not add programme: {e}",
                "danger"
            )

    return programme_form_page(
        "Add Programme"
    )


@app.route(
    "/admin/programmes/<uuid:programme_id>/edit",
    methods=["GET", "POST"]
)
@admin_required
def admin_programme_edit(
    programme_id
):

    programme = sb_get(
        "university_programmes",
        {
            "select": "*",
            "id": (
                f"eq.{programme_id}"
            ),
            "limit": "1",
        },
        single=True
    )

    if not programme:
        abort(404)

    if request.method == "POST":

        try:

            sb_update(
                "university_programmes",
                {
                    "id": (
                        f"eq.{programme_id}"
                    )
                },
                programme_form_data()
            )

            flash(
                "Programme updated.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_programmes"
                )
            )

        except Exception as e:

            flash(
                f"Could not update programme: {e}",
                "danger"
            )

    return programme_form_page(
        "Edit Programme",
        programme
    )


# ============================================================
# ADMIN REQUIREMENTS
# ============================================================

@app.route(
    "/admin/programmes/<uuid:programme_id>/requirements",
    methods=["GET", "POST"]
)
@admin_required
def admin_requirements(
    programme_id
):

    p = sb_get(
        "university_programmes",
        {
            "select": "*",
            "id": (
                f"eq.{programme_id}"
            ),
            "limit": "1",
        },
        single=True
    )

    if not p:
        abort(404)

    if request.method == "POST":

        try:

            sb_insert(
                "university_application_requirements",
                {
                    "university_id":
                        p["university_id"],

                    "programme_id":
                        programme_id,

                    "applicant_type":
                        clean(
                            request.form.get(
                                "applicant_type"
                            )
                        ),

                    "requirement_title":
                        clean(
                            request.form.get(
                                "requirement_title"
                            )
                        ),

                    "requirement_description":
                        clean(
                            request.form.get(
                                "requirement_description"
                            )
                        ),

                    "required":
                        request.form.get(
                            "required"
                        ) == "on",

                    "source_url":
                        clean(
                            request.form.get(
                                "source_url"
                            )
                        ),

                    "category":
                        clean(
                            request.form.get(
                                "category"
                            )
                        ),

                    "document_type":
                        clean(
                            request.form.get(
                                "document_type"
                            )
                        ),

                    "applicant_instruction":
                        clean(
                            request.form.get(
                                "applicant_instruction"
                            )
                        ),

                    "last_verified_at":
                        now_iso(),
                }
            )

            flash(
                "Requirement added.",
                "success"
            )

        except Exception as e:

            flash(
                f"Could not add requirement: {e}",
                "danger"
            )

    rows = optional_get(
        "university_application_requirements",
        {
            "select": "*",
            "programme_id": (
                f"eq.{programme_id}"
            ),
            "order": "created_at.asc",
        }
    )

    return page(
        "Programme Requirements",
        r"""

<div class="card">

<h1>
{{ p.programme_name }}
</h1>

<p>
Add the documents and conditions
applicants must meet.
</p>

</div>

<div class="card">

<h2>
Add Requirement
</h2>

<form method="post">

<label>
Requirement title
</label>

<input
 name="requirement_title"
 required
>

<label>
Description
</label>

<textarea
 name="requirement_description"
></textarea>

<label>
Applicant type
</label>

<input
 name="applicant_type"
 placeholder="e.g. School leaver"
>

<label>
Category
</label>

<input
 name="category"
 placeholder="e.g. Academic"
>

<label>
Document type
</label>

<input
 name="document_type"
 placeholder="e.g. Grade 12 certificate"
>

<label>
Applicant instruction
</label>

<textarea
 name="applicant_instruction"
></textarea>

<label>
Source URL
</label>

<input
 name="source_url"
>

<label>

<input
 type="checkbox"
 name="required"
 checked
>

Required

</label>

<br>

<button>
Add Requirement
</button>

</form>

</div>

<div class="grid">

{% for r in rows %}

<div class="card">

<h3>
{{ r.requirement_title }}
</h3>

<p>
{{ r.requirement_description }}
</p>

<p>
<b>Required:</b>
{{ r.required }}
</p>

</div>

{% else %}

<div class="card">
No requirements added.
</div>

{% endfor %}

</div>

"""
        ,
        p=p,
        rows=rows
    )


# ============================================================
# ADMIN APPLICATIONS
# ============================================================

@app.route("/admin/applications")
@admin_required
def admin_applications():

    rows = optional_get(
        "university_applications",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "1000",
        }
    )

    return page(
        "Manage Applications",
        r"""

<div class="card">

<h1>
University Applications
</h1>

<table>

<tr>

<th>
Number
</th>

<th>
Applicant
</th>

<th>
University
</th>

<th>
Programme
</th>

<th>
Status
</th>

<th>
Payment
</th>

<th>
Action
</th>

</tr>

{% for a in rows %}

<tr>

<td>
{{ a.application_number
or a.id }}
</td>

<td>
{{ a.full_name }}
<br>
{{ a.email }}
</td>

<td>
{{ a.university }}
</td>

<td>
{{ a.programme }}
</td>

<td>
{{ a.application_status
or a.status }}
</td>

<td>
{{ a.payment_status }}
</td>

<td>

<a
 class="btn"
 href="{{ url_for(
 'admin_application',
 application_id=a.id
 ) }}"
>
Open
</a>

</td>

</tr>

{% endfor %}

</table>

</div>

"""
        ,
        rows=rows
    )


@app.route(
    "/admin/applications/<uuid:application_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_application(
    application_id
):

    a = sb_get(
        "university_applications",
        {
            "select": "*",
            "id": (
                f"eq.{application_id}"
            ),
            "limit": "1",
        },
        single=True
    )

    if not a:
        abort(404)

    if request.method == "POST":

        try:

            status = clean(
                request.form.get(
                    "application_status"
                )
            ) or "submitted"

            payment_status = clean(
                request.form.get(
                    "payment_status"
                )
            ) or (
                a.get(
                    "payment_status"
                )
                or "unpaid"
            )

            sb_update(
                "university_applications",
                {
                    "id": (
                        f"eq.{application_id}"
                    )
                },
                {
                    "application_status":
                        status,

                    "status":
                        status,

                    "payment_status":
                        payment_status,

                    "admin_notes":
                        clean(
                            request.form.get(
                                "admin_notes"
                            )
                        ),

                    "rejection_reason":
                        clean(
                            request.form.get(
                                "rejection_reason"
                            )
                        ),

                    "reviewed_at":
                        now_iso(),

                    "reviewed_by":
                        current_user()["id"],
                }
            )

            notify(
                a.get("email"),
                "Application status updated",
                (
                    "Your university application "
                    f"status is now: {status}."
                )
            )

            flash(
                "Application updated.",
                "success"
            )

        except Exception as e:

            flash(
                f"Update failed: {e}",
                "danger"
            )

    return page(
        "Review Application",
        r"""

<div class="card">

<h1>
Review Application
</h1>

<table>

{% for k,v in [

("Application number",
a.application_number or a.id),

("Applicant",
a.full_name),

("Email",
a.email),

("Phone",
a.phone),

("University",
a.university),

("Programme",
a.programme),

("DOB",
a.date_of_birth),

("Gender",
a.gender),

("NRC",
a.nrc_number),

("Previous school",
a.previous_school),

("Qualification",
a.qualification),

("Address",
a.address),

("Province",
a.province),

("District",
a.district),

("Information",
a.application_information)

] %}

<tr>

<th>
{{ k }}
</th>

<td>
{{ v or "-" }}
</td>

</tr>

{% endfor %}

</table>

</div>

<div class="card">

<form method="post">

<label>
Application status
</label>

<select
 name="application_status"
>

{% for x in [
'draft',
'submitted',
'under_review',
'approved',
'rejected',
'completed',
'cancelled'
] %}

<option
 value="{{ x }}"
 {% if a.application_status == x
 or a.status == x %}
 selected
 {% endif %}
>

{{ x }}

</option>

{% endfor %}

</select>

<label>
Payment status
</label>

<select
 name="payment_status"
>

{% for x in [
'unpaid',
'pending',
'paid',
'failed',
'refunded'
] %}

<option
 value="{{ x }}"
 {% if a.payment_status == x %}
 selected
 {% endif %}
>

{{ x }}

</option>

{% endfor %}

</select>

<label>
Admin notes
</label>

<textarea
 name="admin_notes"
>{{ a.admin_notes or '' }}</textarea>

<label>
Rejection reason
</label>

<textarea
 name="rejection_reason"
>{{ a.rejection_reason or '' }}</textarea>

<button>
Save Review
</button>

</form>

</div>

"""
        ,
        a=a
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    rows = optional_get(
        "questions",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "1000",
        }
    )

    return page(
        "Manage Questions",
        r"""

<div class="card">

<h1>
Academic Questions
</h1>

<table>

<tr>

<th>
Student
</th>

<th>
Question
</th>

<th>
Status
</th>

<th>
Action
</th>

</tr>

{% for q in rows %}

<tr>

<td>
{{ q.student_name }}
</td>

<td>
{{ q.question }}
</td>

<td>
{{ q.status }}
</td>

<td>

<a
 class="btn"
 href="{{ url_for(
 'admin_question',
 question_id=q.id
 ) }}"
>
Answer
</a>

</td>

</tr>

{% endfor %}

</table>

</div>

"""
        ,
        rows=rows
    )


@app.route(
    "/admin/questions/<uuid:question_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_question(
    question_id
):

    q = sb_get(
        "questions",
        {
            "select": "*",
            "id": (
                f"eq.{question_id}"
            ),
            "limit": "1",
        },
        single=True
    )

    if not q:
        abort(404)

    if request.method == "POST":

        answer = clean(
            request.form.get(
                "answer"
            )
        )

        status = clean(
            request.form.get(
                "status"
            )
        ) or "answered"

        try:

            sb_update(
                "questions",
                {
                    "id": (
                        f"eq.{question_id}"
                    )
                },
                {
                    "answer":
                        answer,

                    "answer_by":
                        current_user()["name"],

                    "answered_by":
                        current_user()["id"],

                    "answered_at":
                        now_iso(),

                    "status":
                        status,

                    "updated_at":
                        now_iso(),
                }
            )

            flash(
                "Answer saved.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_question",
                    question_id=question_id
                )
            )

        except Exception as e:

            flash(
                f"Could not save answer: {e}",
                "danger"
            )

    return page(
        "Answer Question",
        r"""

<div class="card">

<h1>
Answer Question
</h1>

<p>
<b>
{{ q.student_name }}
</b>
</p>

<div class="card">

{{ q.question }}

</div>

<form method="post">

<label>
Answer
</label>

<textarea
 name="answer"
 required
>{{ q.answer or '' }}</textarea>

<label>
Status
</label>

<select name="status">

<option>
answered
</option>

<option>
pending
</option>

<option>
closed
</option>

</select>

<button>
Save Answer
</button>

</form>

</div>

"""
        ,
        q=q
    )


# ============================================================
# ADMIN ASSIGNMENTS
# ============================================================

@app.route("/admin/assignments")
@admin_required
def admin_assignments():

    rows = optional_get(
        "koja_assignments",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "1000",
        }
    )

    return page(
        "Manage Assignments",
        r"""

<div class="card">

<h1>
Assignments
</h1>

<table>

<tr>

<th>
Student
</th>

<th>
Title
</th>

<th>
Subject
</th>

<th>
Status
</th>

<th>
Date
</th>

</tr>

{% for a in rows %}

<tr>

<td>
{{ a.student_name or a.student_email }}
</td>

<td>
{{ a.title }}
</td>

<td>
{{ a.subject or "-" }}
</td>

<td>
{{ a.status or "submitted" }}
</td>

<td>
{{ a.created_at or "-" }}
</td>

</tr>

{% else %}

<tr>

<td colspan="5">
No assignments found.
</td>

</tr>

{% endfor %}

</table>

</div>

"""
        ,
        rows=rows
    )


# ============================================================
# ADMIN SERVICES
# ============================================================

@app.route("/admin/services")
@admin_required
def admin_services():

    rows = optional_get(
        "koja_service_requests",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "1000",
        }
    )

    return page(
        "Manage Services",
        r"""

<div class="card">

<h1>
Service Requests
</h1>

<table>

<tr>

<th>
Type
</th>

<th>
Client
</th>

<th>
Title
</th>

<th>
Description
</th>

<th>
Status
</th>

<th>
Date
</th>

</tr>

{% for r in rows %}

<tr>

<td>
{{ r.request_type
or r.type
or "-" }}
</td>

<td>
{{ r.client_email or "-" }}
</td>

<td>
{{ r.title or "-" }}
</td>

<td>
{{ r.description or "-" }}
</td>

<td>
{{ r.status or "submitted" }}
</td>

<td>
{{ r.created_at or "-" }}
</td>

</tr>

{% else %}

<tr>

<td colspan="6">
No service requests.
</td>

</tr>

{% endfor %}

</table>

</div>

"""
        ,
        rows=rows
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    result = {
        "app": "ok",
        "supabase_configured":
            configured(),
        "time":
            now_iso(),
    }

    if not configured():

        result["database"] = (
            "not_configured"
        )

        return jsonify(
            result
        )

    try:

        result["universities"] = (
            count_rows(
                "universities"
            )
        )

        result["programmes"] = (
            count_rows(
                "university_programmes"
            )
        )

        result["database"] = "ok"

    except Exception as e:

        result["database"] = "error"

        result["error"] = str(e)

    return jsonify(
        result
    )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    return page(
        "Forbidden",
        r"""

<div class="card">

<h1>
403
</h1>

<p>
You do not have permission to access this page.
</p>

<a
 class="btn"
 href="{{ url_for('home') }}"
>
Return Home
</a>

</div>

"""
    ), 403


@app.errorhandler(404)
def not_found(error):

    return page(
        "Not Found",
        r"""

<div class="card">

<h1>
404
</h1>

<p>
The requested page was not found.
</p>

<a
 class="btn"
 href="{{ url_for('home') }}"
>
Return Home
</a>

</div>

"""
    ), 404


@app.errorhandler(413)
def too_large(error):

    return page(
        "File Too Large",
        r"""

<div class="card">

<h1>
File Too Large
</h1>

<p>
The uploaded file exceeds the configured
maximum of {{ max_upload_mb }} MB.
</p>

</div>

""",
        max_upload_mb=MAX_UPLOAD_MB
    ), 413


@app.errorhandler(500)
def server_error(error):

    log.exception(
        "Unhandled server error"
    )

    return page(
        "Server Error",
        r"""

<div class="card">

<h1>
Server Error
</h1>

<p>
The server encountered an unexpected error.
Please check the Render logs.
</p>

</div>

"""
    ), 500


# ============================================================
# STARTUP
# ============================================================

def startup():

    log.info(
        "Starting KOJA AFRICA"
    )

    log.info(
        "Supabase configured: %s",
        configured()
    )

    if configured():

        try:

            ensure_env_admin()

        except Exception as e:

            log.warning(
                "Admin startup check failed: %s",
                e
            )

    else:

        log.warning(
            "SUPABASE_URL or SUPABASE_SERVICE_KEY "
            "is missing."
        )


startup()


# ============================================================
# RENDER ENTRY POINT
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
