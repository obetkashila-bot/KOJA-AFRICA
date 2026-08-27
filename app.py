import os
import io
import re
import uuid
import secrets
import logging
import mimetypes
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
    jsonify,
)

from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
)
from reportlab.lib import colors
from reportlab.lib.units import mm


# ============================================================
# KOJA AFRICA
# Single-file Flask application
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_IN_RENDER_TO_A_LONG_RANDOM_SECRET"
)

app.config["MAX_CONTENT_LENGTH"] = int(
    os.environ.get("MAX_UPLOAD_MB", "25")
) * 1024 * 1024

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
)

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja_africa")


# ============================================================
# ENVIRONMENT
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")

# New Supabase secret key is preferred.
# Legacy service_role remains supported.
SUPABASE_SECRET_KEY = (
    os.environ.get("SUPABASE_SECRET_KEY")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or ""
)

SUPABASE_ANON_KEY = (
    os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or ""
)

STORAGE_BUCKET = os.environ.get(
    "SUPABASE_STORAGE_BUCKET",
    "koja-assignments"
)

APP_NAME = "KOJA AFRICA"
APP_TAGLINE = "Assignment Questions • Academic Answers • Learning Resources"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()


# ============================================================
# SUPPORTED FILES
# ============================================================

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "rtf",
    "odt",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "csv",
}

ALLOWED_MIME_TYPES = {
    "pdf": "application/pdf",

    "doc": "application/msword",
    "docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),

    "txt": "text/plain",
    "rtf": "application/rtf",
    "odt": "application/vnd.oasis.opendocument.text",

    "xls": "application/vnd.ms-excel",
    "xlsx": (
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),

    "ppt": "application/vnd.ms-powerpoint",
    "pptx": (
        "application/vnd.openxmlformats-officedocument."
        "presentationml.presentation"
    ),

    "csv": "text/csv",
}


# ============================================================
# BASIC HTML
# ============================================================

BASE_HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>{{ title or "KOJA AFRICA" }}</title>

<style>
:root {
    --bg:#f4f7fb;
    --card:#ffffff;
    --text:#182230;
    --muted:#64748b;
    --primary:#155eef;
    --primary2:#0b4bc4;
    --danger:#dc2626;
    --success:#15803d;
    --border:#e2e8f0;
    --dark:#0f172a;
}

* {
    box-sizing:border-box;
}

body {
    margin:0;
    background:var(--bg);
    color:var(--text);
    font-family:
        Inter,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}

a {
    color:var(--primary);
    text-decoration:none;
}

a:hover {
    text-decoration:underline;
}

.nav {
    background:var(--dark);
    color:white;
    padding:14px 20px;
    position:sticky;
    top:0;
    z-index:100;
}

.nav-inner {
    max-width:1200px;
    margin:auto;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:15px;
}

.brand {
    color:white;
    font-weight:800;
    font-size:20px;
    text-decoration:none;
}

.brand:hover {
    text-decoration:none;
}

.nav-links {
    display:flex;
    gap:12px;
    align-items:center;
    flex-wrap:wrap;
}

.nav-links a {
    color:#e2e8f0;
    font-size:14px;
}

.container {
    max-width:1200px;
    margin:25px auto;
    padding:0 15px;
}

.card {
    background:var(--card);
    border:1px solid var(--border);
    border-radius:14px;
    padding:20px;
    margin-bottom:18px;
    box-shadow:0 5px 20px rgba(15,23,42,.04);
}

.grid {
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:16px;
}

.grid-2 {
    display:grid;
    grid-template-columns:repeat(2,1fr);
    gap:16px;
}

@media(max-width:800px) {
    .grid,
    .grid-2 {
        grid-template-columns:1fr;
    }

    .nav-inner {
        align-items:flex-start;
        flex-direction:column;
    }
}

h1,h2,h3 {
    margin-top:0;
}

.muted {
    color:var(--muted);
}

.stat {
    font-size:30px;
    font-weight:800;
}

.btn {
    display:inline-block;
    border:0;
    border-radius:9px;
    padding:10px 15px;
    background:var(--primary);
    color:white;
    cursor:pointer;
    font-weight:700;
    text-decoration:none;
}

.btn:hover {
    background:var(--primary2);
    text-decoration:none;
}

.btn.secondary {
    background:#475569;
}

.btn.success {
    background:var(--success);
}

.btn.danger {
    background:var(--danger);
}

.btn.light {
    background:#e2e8f0;
    color:#172033;
}

input,
textarea,
select {
    width:100%;
    padding:11px 12px;
    border:1px solid #cbd5e1;
    border-radius:8px;
    background:white;
    color:#111827;
    font:inherit;
}

textarea {
    min-height:120px;
    resize:vertical;
}

label {
    display:block;
    font-weight:700;
    margin-bottom:6px;
}

.form-group {
    margin-bottom:15px;
}

table {
    width:100%;
    border-collapse:collapse;
}

th,
td {
    padding:10px;
    border-bottom:1px solid var(--border);
    text-align:left;
    vertical-align:top;
}

th {
    background:#f8fafc;
}

.table-wrap {
    overflow-x:auto;
}

.flash {
    padding:12px 15px;
    border-radius:9px;
    margin-bottom:12px;
    background:#e0ecff;
    border:1px solid #bfd3ff;
}

.flash.error {
    background:#fee2e2;
    border-color:#fecaca;
}

.flash.success {
    background:#dcfce7;
    border-color:#bbf7d0;
}

.badge {
    display:inline-block;
    padding:4px 8px;
    border-radius:999px;
    background:#e2e8f0;
    font-size:12px;
    font-weight:700;
}

.badge.success {
    background:#dcfce7;
    color:#166534;
}

.badge.warning {
    background:#fef3c7;
    color:#92400e;
}

.badge.danger {
    background:#fee2e2;
    color:#991b1b;
}

.badge.blue {
    background:#dbeafe;
    color:#1e40af;
}

.hero {
    padding:35px 20px;
    background:linear-gradient(135deg,#0f172a,#155eef);
    color:white;
    border-radius:18px;
    margin-bottom:20px;
}

.logo-brain {
    font-size:45px;
    margin-bottom:10px;
}

.actions {
    display:flex;
    gap:8px;
    flex-wrap:wrap;
}

footer {
    text-align:center;
    color:var(--muted);
    padding:30px 15px;
}

pre.error {
    white-space:pre-wrap;
    background:#0f172a;
    color:#f8fafc;
    padding:15px;
    border-radius:8px;
    overflow:auto;
}
</style>
</head>

<body>

<nav class="nav">
<div class="nav-inner">

<a class="brand" href="{{ url_for('home') }}">
    KOJA AFRICA
</a>

<div class="nav-links">

{% if session.get("user_id") %}
    <a href="{{ url_for('dashboard') }}">Dashboard</a>
    <a href="{{ url_for('assignments') }}">Assignments</a>
    <a href="{{ url_for('documents') }}">Library</a>
    <a href="{{ url_for('questions') }}">Questions</a>

    {% if session.get("role") == "admin" %}
        <a href="{{ url_for('admin_dashboard') }}">Admin</a>
    {% endif %}

    <a href="{{ url_for('logout') }}">Logout</a>
{% else %}
    <a href="{{ url_for('login') }}">Login</a>
    <a href="{{ url_for('register') }}">Register</a>
{% endif %}

</div>
</div>
</nav>

<div class="container">

{% with messages = get_flashed_messages(with_categories=true) %}
{% for category, message in messages %}
<div class="flash {{ category }}">{{ message }}</div>
{% endfor %}
{% endwith %}

{{ body|safe }}

</div>

<footer>
    <strong>KOJA AFRICA</strong><br>
    Assignment Questions • Academic Answers • Learning Resources
</footer>

</body>
</html>
"""


# ============================================================
# SUPABASE HELPERS
# ============================================================

def require_config():
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured.")

    if not SUPABASE_SECRET_KEY:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY "
            "is not configured."
        )


def supabase_headers(extra=None):
    require_config()

    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
    }

    if extra:
        headers.update(extra)

    return headers


def supabase_request(
    method,
    path,
    json_data=None,
    data=None,
    headers=None,
    timeout=30,
    params=None,
):
    require_config()

    url = f"{SUPABASE_URL}{path}"

    req_headers = supabase_headers(headers)

    if json_data is not None:
        req_headers["Content-Type"] = "application/json"

    response = requests.request(
        method=method,
        url=url,
        headers=req_headers,
        json=json_data,
        data=data,
        params=params,
        timeout=timeout,
    )

    return response


def auth_headers():
    key = SUPABASE_ANON_KEY or SUPABASE_SECRET_KEY

    return {
        "apikey": key,
        "Content-Type": "application/json",
    }


def auth_request(method, path, json_data=None, token=None):
    require_config()

    headers = auth_headers()

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return requests.request(
        method=method,
        url=f"{SUPABASE_URL}{path}",
        headers=headers,
        json=json_data,
        timeout=30,
    )


def db_get(table, params=None):
    response = supabase_request(
        "GET",
        f"/rest/v1/{table}",
        params=params or {"select": "*"},
    )

    if not response.ok:
        logger.error(
            "Database GET failed for %s: %s %s",
            table,
            response.status_code,
            response.text,
        )

        raise RuntimeError(
            f"Database GET failed for {table}: "
            f"{response.status_code} {response.text[:500]}"
        )

    return response.json()


def db_insert(table, payload, returning=True):
    headers = {
        "Prefer": "return=representation"
        if returning
        else "return=minimal"
    }

    response = supabase_request(
        "POST",
        f"/rest/v1/{table}",
        json_data=payload,
        headers=headers,
    )

    if not response.ok:
        logger.error(
            "Database INSERT failed for %s: %s %s",
            table,
            response.status_code,
            response.text,
        )

        raise RuntimeError(
            f"Database INSERT failed for {table}: "
            f"{response.status_code} {response.text[:500]}"
        )

    if returning and response.text:
        return response.json()

    return []


def db_patch(table, params, payload, returning=True):
    headers = {
        "Prefer": "return=representation"
        if returning
        else "return=minimal"
    }

    response = supabase_request(
        "PATCH",
        f"/rest/v1/{table}",
        json_data=payload,
        headers=headers,
        params=params,
    )

    if not response.ok:
        logger.error(
            "Database PATCH failed for %s: %s %s",
            table,
            response.status_code,
            response.text,
        )

        raise RuntimeError(
            f"Database PATCH failed for {table}: "
            f"{response.status_code} {response.text[:500]}"
        )

    if returning and response.text:
        return response.json()

    return []


def db_delete(table, params):
    response = supabase_request(
        "DELETE",
        f"/rest/v1/{table}",
        params=params,
    )

    if not response.ok:
        raise RuntimeError(
            f"Database DELETE failed for {table}: "
            f"{response.status_code} {response.text[:500]}"
        )

    return True


# ============================================================
# AUTH
# ============================================================

def create_auth_user(email, password, name):
    response = auth_request(
        "POST",
        "/auth/v1/signup",
        {
            "email": email,
            "password": password,
            "data": {
                "name": name
            },
        },
    )

    if not response.ok:
        try:
            error = response.json()
        except Exception:
            error = response.text

        return None, str(error)

    return response.json(), None


def login_auth_user(email, password):
    response = auth_request(
        "POST",
        "/auth/v1/token?grant_type=password",
        {
            "email": email,
            "password": password,
        },
    )

    if not response.ok:
        try:
            error = response.json()
        except Exception:
            error = response.text

        return None, str(error)

    return response.json(), None


def get_profile(user_id):
    """
    IMPORTANT:
    profiles uses id, not user_id.
    """

    response = supabase_request(
        "GET",
        "/rest/v1/profiles",
        params={
            "id": f"eq.{user_id}",
            "select": "id,name,email,role,created_at",
            "limit": "1",
        },
    )

    if not response.ok:
        logger.error(
            "Profile lookup failed: %s %s",
            response.status_code,
            response.text,
        )
        return None

    rows = response.json()

    if not rows:
        return None

    return rows[0]


def ensure_profile(user):
    user_id = user.get("id")

    if not user_id:
        return None

    profile = get_profile(user_id)

    if profile:
        return profile

    metadata = user.get("user_metadata") or {}

    payload = {
        "id": user_id,
        "name": metadata.get("name", ""),
        "email": user.get("email", ""),
        "role": "student",
    }

    try:
        created = db_insert(
            "profiles",
            payload,
            returning=True,
        )

        if created:
            return created[0]

    except Exception:
        logger.exception("Could not create profile")

    return payload


def current_profile():
    user_id = session.get("user_id")

    if not user_id:
        return None

    return get_profile(user_id)


# ============================================================
# ROLE DECORATORS
# ============================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.", "error")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))

        if session.get("role") != "admin":
            abort(403)

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# CSRF
# ============================================================

def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return session["csrf_token"]


def validate_csrf():
    expected = session.get("csrf_token")
    received = request.form.get("csrf_token")

    if not expected or not received:
        abort(400)

    if not secrets.compare_digest(expected, received):
        abort(400)


@app.context_processor
def inject_globals():
    return {
        "csrf_token": csrf_token,
        "app_name": APP_NAME,
    }


# ============================================================
# FILE HELPERS
# ============================================================

def extension(filename):
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def valid_file(file):
    if not file or not file.filename:
        return False

    ext = extension(file.filename)

    return ext in ALLOWED_EXTENSIONS


def detect_mime(filename, supplied=None):
    ext = extension(filename)

    if ext in ALLOWED_MIME_TYPES:
        return ALLOWED_MIME_TYPES[ext]

    return supplied or mimetypes.guess_type(filename)[0] or "application/octet-stream"


def safe_storage_name(filename, folder):
    original = secure_filename(filename)

    if not original:
        original = "file"

    return (
        f"{folder}/"
        f"{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/"
        f"{uuid.uuid4().hex}_"
        f"{original}"
    )


def storage_upload(file, storage_path, content_type):
    require_config()

    file.stream.seek(0)

    data = file.stream.read()

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{quote(STORAGE_BUCKET, safe='')}/"
        f"{quote(storage_path, safe='/')}"
    )

    headers = supabase_headers(
        {
            "Content-Type": content_type,
            "x-upsert": "false",
        }
    )

    response = requests.post(
        url,
        headers=headers,
        data=data,
        timeout=120,
    )

    if not response.ok:
        logger.error(
            "Storage upload failed: %s %s",
            response.status_code,
            response.text,
        )

        raise RuntimeError(
            f"Storage upload failed: "
            f"{response.status_code} {response.text[:500]}"
        )

    return storage_path


def storage_delete(storage_path):
    if not storage_path:
        return

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{quote(STORAGE_BUCKET, safe='')}/"
    )

    response = requests.delete(
        url,
        headers=supabase_headers(
            {"Content-Type": "application/json"}
        ),
        json={"prefixes": [storage_path]},
        timeout=30,
    )

    if not response.ok:
        logger.warning(
            "Storage delete failed: %s %s",
            response.status_code,
            response.text,
        )


def create_signed_url(storage_path, expires=900):
    if not storage_path:
        return None

    url = (
        f"{SUPABASE_URL}/storage/v1/object/sign/"
        f"{quote(STORAGE_BUCKET, safe='')}/"
        f"{quote(storage_path, safe='/')}"
    )

    response = requests.post(
        url,
        headers=supabase_headers(
            {"Content-Type": "application/json"}
        ),
        json={
            "expiresIn": expires
        },
        timeout=30,
    )

    if not response.ok:
        logger.error(
            "Signed URL failed: %s %s",
            response.status_code,
            response.text,
        )
        return None

    data = response.json()

    signed = data.get("signedURL")

    if not signed:
        return None

    if signed.startswith("http"):
        return signed

    return f"{SUPABASE_URL}/storage/v1{signed}"


# ============================================================
# LOGGING
# ============================================================

def log_event(
    event,
    category="System",
    level="INFO",
    details="",
    user_id=None,
):
    try:
        db_insert(
            "logs",
            {
                "event": event,
                "category": category,
                "level": level,
                "details": details,
                "user_id": user_id or session.get("user_id"),
            },
            returning=False,
        )
    except Exception:
        logger.exception("Could not write log")


def log_document_access(
    document_id,
    action,
    user_id=None,
):
    try:
        db_insert(
            "document_records",
            {
                "document_id": document_id,
                "user_id": user_id or session.get("user_id"),
                "action": action,
                "ip_address": request.headers.get(
                    "X-Forwarded-For",
                    request.remote_addr,
                ),
                "user_agent": request.headers.get(
                    "User-Agent",
                    "",
                ),
            },
            returning=False,
        )
    except Exception:
        logger.exception("Could not write document record")

    try:
        db_insert(
            "document_access_logs",
            {
                "document_id": document_id,
                "user_id": user_id or session.get("user_id"),
                "action": action,
            },
            returning=False,
        )
    except Exception:
        logger.exception("Could not write document access log")


# ============================================================
# PDF ANSWER GENERATION
# ============================================================

def build_answer_pdf(
    assignment_title,
    student_name,
    subject,
    question,
    answer,
):
    output = io.BytesIO()

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "KOJA_TITLE",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        leading=22,
        spaceAfter=12,
    )

    heading_style = ParagraphStyle(
        "KOJA_HEADING",
        parent=styles["Heading2"],
        fontSize=13,
        leading=17,
        spaceBefore=10,
        spaceAfter=7,
    )

    body_style = ParagraphStyle(
        "KOJA_BODY",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=16,
        spaceAfter=8,
    )

    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    story = []

    story.append(
        Paragraph(
            "ANSWERED ASSIGNMENT",
            title_style,
        )
    )

    story.append(
        Paragraph(
            f"<b>Assignment:</b> "
            f"{escape_html(assignment_title)}",
            body_style,
        )
    )

    story.append(
        Paragraph(
            f"<b>Student:</b> "
            f"{escape_html(student_name)}",
            body_style,
        )
    )

    story.append(
        Paragraph(
            f"<b>Subject:</b> "
            f"{escape_html(subject or '')}",
            body_style,
        )
    )

    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            "QUESTION",
            heading_style,
        )
    )

    story.append(
        Paragraph(
            text_to_paragraphs(question),
            body_style,
        )
    )

    story.append(
        Paragraph(
            "ANSWER",
            heading_style,
        )
    )

    story.append(
        Paragraph(
            text_to_paragraphs(answer),
            body_style,
        )
    )

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            "Generated academic document",
            ParagraphStyle(
                "footer",
                parent=styles["BodyText"],
                fontSize=8,
                textColor=colors.grey,
                alignment=TA_CENTER,
            ),
        )
    )

    doc.build(story)

    output.seek(0)

    return output


def escape_html(text):
    if text is None:
        return ""

    text = str(text)

    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def text_to_paragraphs(text):
    text = escape_html(text or "")

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    return text.replace("\n", "<br/>")


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    body = render_template_string(
        """
        <div class="hero">
            <div class="logo-brain">🧠</div>

            <h1>KOJA AFRICA</h1>

            <p>
                Assignment Questions • Academic Answers •
                Learning Resources
            </p>

            {% if not session.get("user_id") %}
            <div class="actions">
                <a class="btn" href="{{ url_for('register') }}">
                    Create Student Account
                </a>

                <a class="btn light" href="{{ url_for('login') }}">
                    Login
                </a>
            </div>
            {% else %}
            <a class="btn" href="{{ url_for('dashboard') }}">
                Open Dashboard
            </a>
            {% endif %}
        </div>

        <div class="grid">

            <div class="card">
                <h3>Assignments</h3>
                <p class="muted">
                    Submit assignment questions as PDF or Word files.
                </p>
            </div>

            <div class="card">
                <h3>Academic Answers</h3>
                <p class="muted">
                    Administrators can upload or generate answer documents.
                </p>
            </div>

            <div class="card">
                <h3>Resources</h3>
                <p class="muted">
                    Store notes, books, past papers and other resources.
                </p>
            </div>

        </div>
        """
    )

    return render_template_string(
        BASE_HTML,
        title="KOJA AFRICA",
        body=body,
    )


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        validate_csrf()

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "error",
            )
            return redirect(url_for("register"))

        user, error = create_auth_user(
            email,
            password,
            name,
        )

        if error:
            flash(
                f"Registration failed: {error}",
                "error",
            )
            return redirect(url_for("register"))

        auth_user = user.get("user") or user

        if auth_user:
            profile_payload = {
                "id": auth_user["id"],
                "name": name,
                "email": email,
                "role": "student",
            }

            try:
                db_insert(
                    "profiles",
                    profile_payload,
                    returning=False,
                )
            except Exception as exc:
                logger.warning(
                    "Profile creation after signup failed: %s",
                    exc,
                )

        session.clear()
        session["csrf_token"] = secrets.token_urlsafe(32)

        flash(
            "Account created. Check your email if email confirmation "
            "is enabled, then log in.",
            "success",
        )

        return redirect(url_for("login"))

    body = render_template_string(
        """
        <div class="card">
            <h1>Create Student Account</h1>

            <form method="post">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="form-group">
                    <label>Name</label>
                    <input
                        name="name"
                        required
                        maxlength="150"
                    >
                </div>

                <div class="form-group">
                    <label>Email</label>
                    <input
                        type="email"
                        name="email"
                        required
                    >
                </div>

                <div class="form-group">
                    <label>Password</label>
                    <input
                        type="password"
                        name="password"
                        minlength="6"
                        required
                    >
                </div>

                <button class="btn">
                    Create Account
                </button>

            </form>
        </div>
        """
    )

    return render_template_string(
        BASE_HTML,
        title="Register",
        body=body,
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        validate_csrf()

        email = request.form.get(
            "email",
            "",
        ).strip().lower()

        password = request.form.get(
            "password",
            "",
        )

        user, error = login_auth_user(
            email,
            password,
        )

        if error:
            flash(
                f"Login failed: {error}",
                "error",
            )
            return redirect(url_for("login"))

        auth_user = user.get("user")

        if not auth_user:
            flash(
                "Supabase did not return a user.",
                "error",
            )
            return redirect(url_for("login"))

        profile = ensure_profile(auth_user)

        if not profile:
            flash(
                "Login succeeded, but your profile could not be loaded.",
                "error",
            )
            return redirect(url_for("login"))

        role = (
            profile.get("role") or "student"
        ).lower()

        if (
            ADMIN_EMAIL
            and email == ADMIN_EMAIL
        ):
            role = "admin"

            try:
                db_patch(
                    "profiles",
                    {
                        "id": f"eq.{auth_user['id']}"
                    },
                    {
                        "role": "admin"
                    },
                    returning=False,
                )
            except Exception:
                logger.exception(
                    "Could not update admin role"
                )

        session.clear()

        session["csrf_token"] = secrets.token_urlsafe(32)
        session["user_id"] = auth_user["id"]
        session["email"] = auth_user.get("email", email)
        session["name"] = profile.get("name", "")
        session["role"] = role
        session["access_token"] = user.get("access_token")

        log_event(
            "User logged in",
            category="Authentication",
            user_id=auth_user["id"],
        )

        if role == "admin":
            return redirect(url_for("admin_dashboard"))

        return redirect(url_for("dashboard"))

    body = render_template_string(
        """
        <div class="card">
            <h1>Login</h1>

            <form method="post">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="form-group">
                    <label>Email</label>
                    <input
                        type="email"
                        name="email"
                        required
                    >
                </div>

                <div class="form-group">
                    <label>Password</label>
                    <input
                        type="password"
                        name="password"
                        required
                    >
                </div>

                <button class="btn">
                    Login
                </button>

            </form>

            <p>
                <a href="{{ url_for('forgot_password') }}">
                    Forgot password?
                </a>
            </p>

        </div>
        """
    )

    return render_template_string(
        BASE_HTML,
        title="Login",
        body=body,
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():
    user_id = session.get("user_id")

    if user_id:
        log_event(
            "User logged out",
            category="Authentication",
            user_id=user_id,
        )

    session.clear()

    flash(
        "You have been logged out.",
        "success",
    )

    return redirect(url_for("home"))


# ============================================================
# FORGOT PASSWORD
# ============================================================

@app.route(
    "/forgot-password",
    methods=["GET", "POST"],
)
def forgot_password():

    if request.method == "POST":
        validate_csrf()

        email = request.form.get(
            "email",
            "",
        ).strip().lower()

        if not email:
            flash(
                "Enter your email address.",
                "error",
            )
            return redirect(
                url_for("forgot_password")
            )

        response = auth_request(
            "POST",
            "/auth/v1/recover",
            {
                "email": email,
            },
        )

        if not response.ok:
            flash(
                "Password recovery request failed. "
                "Check the email and Supabase Auth configuration.",
                "error",
            )
        else:
            flash(
                "If the account exists, Supabase has sent a "
                "password recovery email.",
                "success",
            )

        return redirect(url_for("login"))

    body = render_template_string(
        """
        <div class="card">
            <h1>Forgot Password</h1>

            <p class="muted">
                Enter the email address associated with your account.
            </p>

            <form method="post">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="form-group">
                    <label>Email</label>

                    <input
                        type="email"
                        name="email"
                        required
                    >
                </div>

                <button class="btn">
                    Send Recovery Email
                </button>

            </form>
        </div>
        """
    )

    return render_template_string(
        BASE_HTML,
        title="Forgot Password",
        body=body,
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    user_id = session["user_id"]

    try:
        assignments_data = db_get(
            "assignments",
            {
                "student_id": f"eq.{user_id}",
                "select": "*",
                "order": "created_at.desc",
                "limit": "10",
            },
        )
    except Exception as exc:
        logger.exception(exc)
        assignments_data = []

    try:
        questions_data = db_get(
            "questions",
            {
                "student_id": f"eq.{user_id}",
                "select": "*",
                "order": "created_at.desc",
                "limit": "10",
            },
        )
    except Exception:
        questions_data = []

    body = render_template_string(
        """
        <div class="hero">
            <div class="logo-brain">🧠</div>

            <h1>
                Welcome,
                {{ session.get("name") or session.get("email") }}
            </h1>

            <p>
                {{ session.get("role", "student")|capitalize }}
            </p>
        </div>

        <div class="grid">

            <div class="card">
                <h3>My Assignments</h3>
                <div class="stat">
                    {{ assignments|length }}
                </div>
                <a class="btn" href="{{ url_for('assignments') }}">
                    Open Assignments
                </a>
            </div>

            <div class="card">
                <h3>My Questions</h3>
                <div class="stat">
                    {{ questions|length }}
                </div>
                <a class="btn" href="{{ url_for('questions') }}">
                    Open Questions
                </a>
            </div>

            <div class="card">
                <h3>Library</h3>
                <a class="btn" href="{{ url_for('documents') }}">
                    Browse Library
                </a>
            </div>

        </div>

        <div class="card">
            <h2>Recent Assignments</h2>

            {% if assignments %}
            <div class="table-wrap">
            <table>
                <tr>
                    <th>Title</th>
                    <th>Subject</th>
                    <th>Status</th>
                    <th>Date</th>
                </tr>

                {% for item in assignments %}
                <tr>
                    <td>
                        <a href="{{ url_for(
                            'assignment_detail',
                            assignment_id=item.id
                        ) }}">
                            {{ item.title }}
                        </a>
                    </td>

                    <td>
                        {{ item.subject or "-" }}
                    </td>

                    <td>
                        <span class="badge blue">
                            {{ item.status }}
                        </span>
                    </td>

                    <td>
                        {{ item.created_at }}
                    </td>
                </tr>
                {% endfor %}

            </table>
            </div>

            {% else %}
            <p class="muted">
                You have not submitted an assignment yet.
            </p>
            {% endif %}
        </div>
        """,
        assignments=assignments_data,
        questions=questions_data,
    )

    return render_template_string(
        BASE_HTML,
        title="Dashboard",
        body=body,
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments")
@login_required
def assignments():

    user_id = session["user_id"]

    if session.get("role") == "admin":

        rows = db_get(
            "assignments",
            {
                "select": "*",
                "order": "created_at.desc",
                "limit": "100",
            },
        )

    else:

        rows = db_get(
            "assignments",
            {
                "student_id": f"eq.{user_id}",
                "select": "*",
                "order": "created_at.desc",
                "limit": "100",
            },
        )

    body = render_template_string(
        """
        <div class="actions" style="margin-bottom:15px;">

            <a class="btn"
               href="{{ url_for('new_assignment') }}">
                Upload Assignment
            </a>

            {% if session.get("role") == "admin" %}
            <a class="btn success"
               href="{{ url_for('admin_new_assignment') }}">
                Assign to Student
            </a>
            {% endif %}

        </div>

        <div class="card">

            <h1>Assignments</h1>

            <div class="table-wrap">
            <table>

            <tr>
                <th>Title</th>
                <th>Student</th>
                <th>Subject</th>
                <th>Status</th>
                <th>Question</th>
                <th>Answer</th>
                <th></th>
            </tr>

            {% for item in rows %}

            <tr>

                <td>{{ item.title }}</td>

                <td>
                    {{ item.student_name or item.email or "-" }}
                </td>

                <td>{{ item.subject or "-" }}</td>

                <td>
                    <span class="badge">
                        {{ item.status }}
                    </span>
                </td>

                <td>
                    {% if item.file_path %}
                    <a href="{{ url_for(
                        'assignment_file',
                        assignment_id=item.id,
                        kind='question'
                    ) }}">
                        View
                    </a>
                    {% else %}
                    No file
                    {% endif %}
                </td>

                <td>
                    {% if item.answer_file_path %}
                    <a href="{{ url_for(
                        'assignment_file',
                        assignment_id=item.id,
                        kind='answer'
                    ) }}">
                        Answer
                    </a>
                    {% else %}
                    Not answered
                    {% endif %}
                </td>

                <td>
                    <a class="btn light"
                       href="{{ url_for(
                           'assignment_detail',
                           assignment_id=item.id
                       ) }}">
                        Open
                    </a>
                </td>

            </tr>

            {% else %}

            <tr>
                <td colspan="7">
                    No assignments found.
                </td>
            </tr>

            {% endfor %}

            </table>
            </div>

        </div>
        """,
        rows=rows,
    )

    return render_template_string(
        BASE_HTML,
        title="Assignments",
        body=body,
    )


# ============================================================
# NEW STUDENT ASSIGNMENT
# ============================================================

@app.route(
    "/assignments/new",
    methods=["GET", "POST"],
)
@login_required
def new_assignment():

    if request.method == "POST":
        validate_csrf()

        title = request.form.get(
            "title",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        subject = request.form.get(
            "subject",
            "",
        ).strip()

        course = request.form.get(
            "course",
            "",
        ).strip()

        class_level = request.form.get(
            "class_level",
            "",
        ).strip()

        question = request.form.get(
            "question",
            "",
        ).strip()

        file = request.files.get("question_file")

        if not title:
            flash(
                "Assignment title is required.",
                "error",
            )
            return redirect(url_for("new_assignment"))

        if not file and not question:
            flash(
                "Enter a question or upload a question file.",
                "error",
            )
            return redirect(url_for("new_assignment"))

        student_id = session["user_id"]

        student_name = session.get("name", "")
        email = session.get("email", "")

        file_path = None
        file_name = None
        file_size = 0
        mime_type = "application/pdf"

        try:

            if file and file.filename:

                if not valid_file(file):
                    flash(
                        "Unsupported question file type.",
                        "error",
                    )
                    return redirect(
                        url_for("new_assignment")
                    )

                file_name = secure_filename(
                    file.filename
                )

                file.stream.seek(0)
                file_size = len(
                    file.stream.read()
                )
                file.stream.seek(0)

                mime_type = detect_mime(
                    file_name,
                    file.mimetype,
                )

                file_path = safe_storage_name(
                    file_name,
                    "assignments/questions",
                )

                storage_upload(
                    file,
                    file_path,
                    mime_type,
                )

            payload = {
                "student_id": student_id,
                "title": title,
                "description": description,
                "subject": subject,
                "course": course,
                "class_level": class_level,
                "file_name": file_name,
                "file_path": file_path,
                "file_size": file_size,
                "mime_type": mime_type,
                "status": "submitted",
                "email": email,
                "question": question,
                "student_name": student_name,
            }

            created = db_insert(
                "assignments",
                payload,
                returning=True,
            )

            assignment_id = (
                created[0]["id"]
                if created
                else None
            )

            if assignment_id:
                log_event(
                    "Student uploaded assignment",
                    category="Assignments",
                    user_id=student_id,
                )

            flash(
                "Assignment submitted successfully.",
                "success",
            )

            return redirect(
                url_for("assignments")
            )

        except Exception as exc:

            logger.exception(
                "Assignment upload failed"
            )

            if file_path:
                storage_delete(file_path)

            flash(
                f"Assignment upload failed: {exc}",
                "error",
            )

            return redirect(
                url_for("new_assignment")
            )

    body = render_template_string(
        """
        <div class="card">

            <h1>Upload Assignment</h1>

            <p class="muted">
                You can type the question, upload a PDF/Word document,
                or provide both.
            </p>

            <form method="post"
                  enctype="multipart/form-data">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="form-group">
                    <label>Title</label>
                    <input
                        name="title"
                        required
                    >
                </div>

                <div class="form-group">
                    <label>Description</label>
                    <textarea
                        name="description"
                    ></textarea>
                </div>

                <div class="grid-2">

                    <div class="form-group">
                        <label>Subject</label>
                        <input name="subject">
                    </div>

                    <div class="form-group">
                        <label>Course</label>
                        <input name="course">
                    </div>

                </div>

                <div class="form-group">
                    <label>Class / Level</label>
                    <input name="class_level">
                </div>

                <div class="form-group">
                    <label>Question</label>
                    <textarea
                        name="question"
                        placeholder="Type the assignment question here..."
                    ></textarea>
                </div>

                <div class="form-group">
                    <label>
                        Question File
                    </label>

                    <input
                        type="file"
                        name="question_file"
                        accept=".pdf,.doc,.docx,.txt,.rtf,.odt,.xls,.xlsx,.ppt,.pptx,.csv"
                    >

                    <small class="muted">
                        PDF, Word, Excel, PowerPoint, TXT, RTF,
                        ODT and CSV.
                    </small>
                </div>

                <button class="btn">
                    Submit Assignment
                </button>

            </form>

        </div>
        """
    )

    return render_template_string(
        BASE_HTML,
        title="Upload Assignment",
        body=body,
    )


# ============================================================
# ADMIN ASSIGNMENT
# ============================================================

@app.route(
    "/admin/assignments/new",
    methods=["GET", "POST"],
)
@admin_required
def admin_new_assignment():

    if request.method == "POST":
        validate_csrf()

        student_id = request.form.get(
            "student_id",
            "",
        ).strip()

        email = request.form.get(
            "email",
            "",
        ).strip().lower()

        title = request.form.get(
            "title",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        subject = request.form.get(
            "subject",
            "",
        ).strip()

        course = request.form.get(
            "course",
            "",
        ).strip()

        class_level = request.form.get(
            "class_level",
            "",
        ).strip()

        question = request.form.get(
            "question",
            "",
        ).strip()

        file = request.files.get(
            "question_file"
        )

        if not student_id:
            flash(
                "Student ID is required.",
                "error",
            )
            return redirect(
                url_for("admin_new_assignment")
            )

        if not title:
            flash(
                "Assignment title is required.",
                "error",
            )
            return redirect(
                url_for("admin_new_assignment")
            )

        if not file and not question:
            flash(
                "Provide a question or question file.",
                "error",
            )
            return redirect(
                url_for("admin_new_assignment")
            )

        file_path = None
        file_name = None
        file_size = 0
        mime_type = "application/pdf"

        try:

            student_profile = get_profile(
                student_id
            )

            if not student_profile:
                flash(
                    "Student profile was not found.",
                    "error",
                )
                return redirect(
                    url_for("admin_new_assignment")
                )

            student_name = student_profile.get(
                "name",
                "",
            )

            if not email:
                email = student_profile.get(
                    "email",
                    "",
                )

            if file and file.filename:

                if not valid_file(file):
                    flash(
                        "Unsupported question file.",
                        "error",
                    )
                    return redirect(
                        url_for("admin_new_assignment")
                    )

                file_name = secure_filename(
                    file.filename
                )

                file.stream.seek(0)
                file_size = len(
                    file.stream.read()
                )
                file.stream.seek(0)

                mime_type = detect_mime(
                    file_name,
                    file.mimetype,
                )

                file_path = safe_storage_name(
                    file_name,
                    "assignments/questions",
                )

                storage_upload(
                    file,
                    file_path,
                    mime_type,
                )

            payload = {
                "student_id": student_id,
                "title": title,
                "description": description,
                "subject": subject,
                "course": course,
                "class_level": class_level,
                "file_name": file_name,
                "file_path": file_path,
                "file_size": file_size,
                "mime_type": mime_type,
                "status": "assigned",
                "email": email,
                "question": question,
                "student_name": student_name,
                "reviewed_by": session["user_id"],
            }

            db_insert(
                "assignments",
                payload,
                returning=True,
            )

            log_event(
                "Admin assigned assignment to student",
                category="Assignments",
                user_id=session["user_id"],
            )

            flash(
                "Assignment assigned successfully.",
                "success",
            )

            return redirect(
                url_for("assignments")
            )

        except Exception as exc:

            logger.exception(exc)

            if file_path:
                storage_delete(file_path)

            flash(
                f"Could not create assignment: {exc}",
                "error",
            )

            return redirect(
                url_for("admin_new_assignment")
            )

    try:
        students = db_get(
            "profiles",
            {
                "role": "eq.student",
                "select": "id,name,email,role",
                "order": "name.asc",
                "limit": "500",
            },
        )
    except Exception:
        students = []

    body = render_template_string(
        """
        <div class="card">

            <h1>Assign Work to Student</h1>

            <form method="post"
                  enctype="multipart/form-data">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="form-group">
                    <label>Student</label>

                    <select
                        name="student_id"
                        required
                    >

                        <option value="">
                            Select student
                        </option>

                        {% for student in students %}

                        <option value="{{ student.id }}">
                            {{ student.name }}
                            —
                            {{ student.email }}
                        </option>

                        {% endfor %}

                    </select>
                </div>

                <div class="form-group">
                    <label>Student Email (optional)</label>
                    <input
                        type="email"
                        name="email"
                    >
                </div>

                <div class="form-group">
                    <label>Assignment Title</label>
                    <input
                        name="title"
                        required
                    >
                </div>

                <div class="grid-2">

                    <div class="form-group">
                        <label>Subject</label>
                        <input name="subject">
                    </div>

                    <div class="form-group">
                        <label>Course</label>
                        <input name="course">
                    </div>

                </div>

                <div class="form-group">
                    <label>Class / Level</label>
                    <input name="class_level">
                </div>

                <div class="form-group">
                    <label>Description</label>
                    <textarea name="description"></textarea>
                </div>

                <div class="form-group">
                    <label>Question</label>
                    <textarea name="question"></textarea>
                </div>

                <div class="form-group">
                    <label>Question PDF / Word / Other</label>

                    <input
                        type="file"
                        name="question_file"
                        accept=".pdf,.doc,.docx,.txt,.rtf,.odt,.xls,.xlsx,.ppt,.pptx,.csv"
                    >
                </div>

                <button class="btn success">
                    Assign to Student
                </button>

            </form>

        </div>
        """,
        students=students,
    )

    return render_template_string(
        BASE_HTML,
        title="Assign Assignment",
        body=body,
    )


# ============================================================
# ASSIGNMENT DETAIL
# ============================================================

@app.route(
    "/assignments/<assignment_id>"
)
@login_required
def assignment_detail(assignment_id):

    rows = db_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        },
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    user_id = session["user_id"]

    if (
        session.get("role") != "admin"
        and assignment.get("student_id") != user_id
    ):
        abort(403)

    try:
        responses = db_get(
            "assignment_responses",
            {
                "assignment_id": f"eq.{assignment_id}",
                "select": "*",
                "order": "created_at.asc",
            },
        )
    except Exception:
        responses = []

    try:
        answer_rows = db_get(
            "assignment_answers",
            {
                "assignment_id": f"eq.{assignment_id}",
                "select": "*",
                "order": "created_at.desc",
                "limit": "20",
            },
        )
    except Exception:
        answer_rows = []

    body = render_template_string(
        """
        <div class="card">

            <h1>{{ assignment.title }}</h1>

            <p>
                <span class="badge blue">
                    {{ assignment.status }}
                </span>
            </p>

            <p>
                <strong>Subject:</strong>
                {{ assignment.subject or "-" }}
            </p>

            <p>
                <strong>Course:</strong>
                {{ assignment.course or "-" }}
            </p>

            <p>
                <strong>Class:</strong>
                {{ assignment.class_level or "-" }}
            </p>

            <p>
                {{ assignment.description or "" }}
            </p>

            {% if assignment.question %}
            <div class="card">
                <h3>Question</h3>
                <p>
                    {{ assignment.question }}
                </p>
            </div>
            {% endif %}

            <div class="actions">

                {% if assignment.file_path %}
                <a class="btn"
                   href="{{ url_for(
                       'assignment_file',
                       assignment_id=assignment.id,
                       kind='question'
                   ) }}">
                    Open Question File
                </a>
                {% endif %}

                {% if assignment.answer_file_path %}
                <a class="btn success"
                   href="{{ url_for(
                       'assignment_file',
                       assignment_id=assignment.id,
                       kind='answer'
                   ) }}">
                    Open Answer
                </a>
                {% endif %}

            </div>

        </div>

        {% if session.get("role") == "admin" %}

        <div class="card">

            <h2>Admin Answer</h2>

            <form method="post"
                  action="{{ url_for(
                      'answer_assignment',
                      assignment_id=assignment.id
                  ) }}"
                  enctype="multipart/form-data">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="form-group">
                    <label>Answer Text</label>
                    <textarea
                        name="answer_text"
                    ></textarea>
                </div>

                <div class="form-group">
                    <label>
                        Upload Answer PDF / Word / Other
                    </label>

                    <input
                        type="file"
                        name="answer_file"
                        accept=".pdf,.doc,.docx,.txt,.rtf,.odt,.xls,.xlsx,.ppt,.pptx,.csv"
                    >
                </div>

                <div class="actions">

                    <button
                        class="btn success"
                        name="action"
                        value="answer"
                    >
                        Save Answer
                    </button>

                    <button
                        class="btn"
                        name="action"
                        value="generate_pdf"
                    >
                        Generate Answer PDF
                    </button>

                </div>

            </form>

        </div>

        <div class="card">

            <h2>Update Status</h2>

            <form method="post"
                  action="{{ url_for(
                      'update_assignment_status',
                      assignment_id=assignment.id
                  ) }}">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <select name="status">

                    {% for status in statuses %}

                    <option
                        value="{{ status }}"
                        {% if assignment.status == status %}
                        selected
                        {% endif %}
                    >
                        {{ status }}
                    </option>

                    {% endfor %}

                </select>

                <br><br>

                <textarea
                    name="admin_comment"
                    placeholder="Admin comment"
                >{{ assignment.admin_comment or "" }}</textarea>

                <br>

                <button class="btn">
                    Update Assignment
                </button>

            </form>

        </div>

        {% endif %}

        <div class="card">

            <h2>Responses / Comments</h2>

            {% for response in responses %}

            <div class="card">

                <p>
                    {{ response.response_text or "" }}
                </p>

                {% if response.file_path %}
                <a
                    href="{{ url_for(
                        'response_file',
                        response_id=response.id
                    ) }}"
                    class="btn light"
                >
                    Open Attachment
                </a>
                {% endif %}

                <small class="muted">
                    {{ response.created_at }}
                </small>

            </div>

            {% else %}

            <p class="muted">
                No responses yet.
            </p>

            {% endfor %}

            <form method="post"
                  action="{{ url_for(
                      'add_assignment_response',
                      assignment_id=assignment.id
                  ) }}"
                  enctype="multipart/form-data">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="form-group">
                    <label>Comment</label>
                    <textarea
                        name="response_text"
                    ></textarea>
                </div>

                <div class="form-group">
                    <label>Attachment</label>
                    <input
                        type="file"
                        name="response_file"
                        accept=".pdf,.doc,.docx,.txt,.rtf,.odt,.xls,.xlsx,.ppt,.pptx,.csv"
                    >
                </div>

                <button class="btn">
                    Send Response
                </button>

            </form>

        </div>

        <div class="card">

            <h2>Answer Records</h2>

            {% for answer in answer_rows %}

            <div class="card">

                <span class="badge success">
                    {{ answer.status }}
                </span>

                <p>
                    {{ answer.answer_text or "" }}
                </p>

                {% if answer.answer_file_path %}

                <a class="btn success"
                   href="{{ url_for(
                       'assignment_answer_file',
                       answer_id=answer.id
                   ) }}">
                    Open Answer File
                </a>

                {% endif %}

            </div>

            {% else %}

            <p class="muted">
                No answer record yet.
            </p>

            {% endfor %}

        </div>
        """,
        assignment=assignment,
        responses=responses,
        answer_rows=answer_rows,
        statuses=[
            "assigned",
            "submitted",
            "received",
            "reviewing",
            "answered",
            "completed",
            "rejected",
        ],
    )

    return render_template_string(
        BASE_HTML,
        title=assignment["title"],
        body=body,
    )


# ============================================================
# ANSWER ASSIGNMENT
# ============================================================

@app.route(
    "/assignments/<assignment_id>/answer",
    methods=["POST"],
)
@admin_required
def answer_assignment(assignment_id):

    validate_csrf()

    rows = db_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        },
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    answer_text = request.form.get(
        "answer_text",
        "",
    ).strip()

    answer_file = request.files.get(
        "answer_file"
    )

    action = request.form.get(
        "action",
        "answer",
    )

    if (
        not answer_text
        and not answer_file
        and action != "generate_pdf"
    ):
        flash(
            "Provide answer text or an answer file.",
            "error",
        )
        return redirect(
            url_for(
                "assignment_detail",
                assignment_id=assignment_id,
            )
        )

    file_path = None
    file_name = None

    try:

        if answer_file and answer_file.filename:

            if not valid_file(answer_file):
                flash(
                    "Unsupported answer file type.",
                    "error",
                )
                return redirect(
                    url_for(
                        "assignment_detail",
                        assignment_id=assignment_id,
                    )
                )

            file_name = secure_filename(
                answer_file.filename
            )

            answer_file.stream.seek(0)
            file_size = len(
                answer_file.stream.read()
            )
            answer_file.stream.seek(0)

            mime_type = detect_mime(
                file_name,
                answer_file.mimetype,
            )

            file_path = safe_storage_name(
                file_name,
                "assignments/answers",
            )

            storage_upload(
                answer_file,
                file_path,
                mime_type,
            )

        # Generate PDF if requested.
        if action == "generate_pdf":

            if not answer_text:
                flash(
                    "Enter the answer text before generating a PDF.",
                    "error",
                )
                return redirect(
                    url_for(
                        "assignment_detail",
                        assignment_id=assignment_id,
                    )
                )

            pdf = build_answer_pdf(
                assignment_title=assignment.get(
                    "title",
                    "",
                ),
                student_name=assignment.get(
                    "student_name",
                    "",
                ),
                subject=assignment.get(
                    "subject",
                    "",
                ),
                question=assignment.get(
                    "question",
                    "",
                ),
                answer=answer_text,
            )

            generated_name = (
                secure_filename(
                    assignment.get(
                        "title",
                        "assignment",
                    )
                )
                or "assignment"
            )

            generated_name += "_answered.pdf"

            file_name = generated_name

            file_path = (
                f"assignments/answers/"
                f"{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/"
                f"{uuid.uuid4().hex}_"
                f"{secure_filename(generated_name)}"
            )

            pdf.seek(0)

            class UploadedBytes:
                def __init__(self, stream, filename):
                    self.stream = stream
                    self.filename = filename

            fake_file = UploadedBytes(
                pdf,
                generated_name,
            )

            storage_upload(
                fake_file,
                file_path,
                "application/pdf",
            )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        # Record in assignment_answers
        db_insert(
            "assignment_answers",
            {
                "assignment_id": assignment_id,
                "student_id": assignment.get(
                    "student_id"
                ),
                "answer_text": answer_text or None,
                "answer_file_name": file_name,
                "answer_file_path": file_path,
                "generated_by": "admin",
                "status": "answered",
            },
            returning=False,
        )

        # Update assignment itself.
        db_patch(
            "assignments",
            {
                "id": f"eq.{assignment_id}"
            },
            {
                "answer_file_name": file_name,
                "answer_file_path": file_path,
                "answered_at": now,
                "answered_by": session["user_id"],
                "status": "answered",
                "reviewed_by": session["user_id"],
            },
            returning=False,
        )

        log_event(
            "Assignment answered",
            category="Assignments",
            user_id=session["user_id"],
        )

        flash(
            "Assignment answer saved successfully.",
            "success",
        )

    except Exception as exc:

        logger.exception(
            "Answer upload failed"
        )

        if file_path:
            storage_delete(file_path)

        flash(
            f"Could not save answer: {exc}",
            "error",
        )

    return redirect(
        url_for(
            "assignment_detail",
            assignment_id=assignment_id,
        )
    )


# ============================================================
# UPDATE ASSIGNMENT STATUS
# ============================================================

@app.route(
    "/assignments/<assignment_id>/status",
    methods=["POST"],
)
@admin_required
def update_assignment_status(assignment_id):

    validate_csrf()

    status = request.form.get(
        "status",
        "reviewing",
    ).strip()

    comment = request.form.get(
        "admin_comment",
        "",
    ).strip()

    allowed = {
        "assigned",
        "submitted",
        "received",
        "reviewing",
        "answered",
        "completed",
        "rejected",
    }

    if status not in allowed:
        abort(400)

    db_patch(
        "assignments",
        {
            "id": f"eq.{assignment_id}"
        },
        {
            "status": status,
            "admin_comment": comment,
            "reviewed_by": session["user_id"],
        },
        returning=False,
    )

    log_event(
        f"Assignment status changed to {status}",
        category="Assignments",
        user_id=session["user_id"],
    )

    flash(
        "Assignment status updated.",
        "success",
    )

    return redirect(
        url_for(
            "assignment_detail",
            assignment_id=assignment_id,
        )
    )


# ============================================================
# ASSIGNMENT RESPONSE
# ============================================================

@app.route(
    "/assignments/<assignment_id>/response",
    methods=["POST"],
)
@login_required
def add_assignment_response(assignment_id):

    validate_csrf()

    rows = db_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        },
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    if (
        session.get("role") != "admin"
        and assignment.get("student_id")
        != session["user_id"]
    ):
        abort(403)

    response_text = request.form.get(
        "response_text",
        "",
    ).strip()

    file = request.files.get(
        "response_file"
    )

    if not response_text and not file:
        flash(
            "Enter a response or attach a file.",
            "error",
        )
        return redirect(
            url_for(
                "assignment_detail",
                assignment_id=assignment_id,
            )
        )

    file_path = None
    file_name = None
    file_size = 0
    mime_type = None

    try:

        if file and file.filename:

            if not valid_file(file):
                flash(
                    "Unsupported response file.",
                    "error",
                )
                return redirect(
                    url_for(
                        "assignment_detail",
                        assignment_id=assignment_id,
                    )
                )

            file_name = secure_filename(
                file.filename
            )

            file.stream.seek(0)
            file_size = len(
                file.stream.read()
            )
            file.stream.seek(0)

            mime_type = detect_mime(
                file_name,
                file.mimetype,
            )

            file_path = safe_storage_name(
                file_name,
                "assignments/responses",
            )

            storage_upload(
                file,
                file_path,
                mime_type,
            )

        admin_id = (
            session["user_id"]
            if session.get("role") == "admin"
            else None
        )

        db_insert(
            "assignment_responses",
            {
                "assignment_id": assignment_id,
                "admin_id": admin_id,
                "response_text": response_text or None,
                "file_name": file_name,
                "file_path": file_path,
                "file_size": file_size,
                "mime_type": mime_type,
            },
            returning=False,
        )

        log_event(
            "Assignment response added",
            category="Assignments",
        )

        flash(
            "Response sent.",
            "success",
        )

    except Exception as exc:

        logger.exception(exc)

        if file_path:
            storage_delete(file_path)

        flash(
            f"Could not send response: {exc}",
            "error",
        )

    return redirect(
        url_for(
            "assignment_detail",
            assignment_id=assignment_id,
        )
    )


# ============================================================
# ASSIGNMENT QUESTION FILE
# ============================================================

@app.route(
    "/assignments/<assignment_id>/file/<kind>"
)
@login_required
def assignment_file(
    assignment_id,
    kind,
):

    rows = db_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        },
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    if (
        session.get("role") != "admin"
        and assignment.get("student_id")
        != session["user_id"]
    ):
        abort(403)

    if kind == "question":
        path = assignment.get(
            "file_path"
        )
    elif kind == "answer":
        path = assignment.get(
            "answer_file_path"
        )
    else:
        abort(404)

    if not path:
        abort(404)

    signed = create_signed_url(
        path,
        expires=600,
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# ASSIGNMENT ANSWER FILE
# ============================================================

@app.route(
    "/assignment-answers/<answer_id>/file"
)
@login_required
def assignment_answer_file(answer_id):

    rows = db_get(
        "assignment_answers",
        {
            "id": f"eq.{answer_id}",
            "select": "*",
            "limit": "1",
        },
    )

    if not rows:
        abort(404)

    answer = rows[0]

    assignment_rows = db_get(
        "assignments",
        {
            "id": f"eq.{answer['assignment_id']}",
            "select": "id,student_id",
            "limit": "1",
        },
    )

    if not assignment_rows:
        abort(404)

    assignment = assignment_rows[0]

    if (
        session.get("role") != "admin"
        and assignment.get("student_id")
        != session["user_id"]
    ):
        abort(403)

    signed = create_signed_url(
        answer["answer_file_path"],
        expires=600,
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# RESPONSE FILE
# ============================================================

@app.route(
    "/responses/<response_id>/file"
)
@login_required
def response_file(response_id):

    rows = db_get(
        "assignment_responses",
        {
            "id": f"eq.{response_id}",
            "select": "*",
            "limit": "1",
        },
    )

    if not rows:
        abort(404)

    response_row = rows[0]

    assignment_rows = db_get(
        "assignments",
        {
            "id": f"eq.{response_row['assignment_id']}",
            "select": "id,student_id",
            "limit": "1",
        },
    )

    if not assignment_rows:
        abort(404)

    assignment = assignment_rows[0]

    if (
        session.get("role") != "admin"
        and assignment.get("student_id")
        != session["user_id"]
    ):
        abort(403)

    signed = create_signed_url(
        response_row["file_path"],
        expires=600,
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# DOCUMENT LIBRARY
# ============================================================

@app.route("/documents")
@login_required
def documents():

    search = request.args.get(
        "search",
        "",
    ).strip()

    params = {
        "select": "*",
        "is_active": "eq.true",
        "order": "created_at.desc",
        "limit": "100",
    }

    if search:
        escaped = search.replace(
            ",",
            " ",
        )

        params["or"] = (
            f"(title.ilike.*{escaped}*,"
            f"description.ilike.*{escaped}*,"
            f"subject.ilike.*{escaped}*,"
            f"course.ilike.*{escaped}*)"
        )

    rows = db_get(
        "documents",
        params,
    )

    body = render_template_string(
        """
        <div class="card">

            <h1>Academic Library</h1>

            <form method="get">

                <div class="grid-2">

                    <input
                        name="search"
                        value="{{ search }}"
                        placeholder="Search documents..."
                    >

                    <button class="btn">
                        Search
                    </button>

                </div>

            </form>

        </div>

        {% if session.get("role") == "admin" %}
        <div class="card">
            <a class="btn"
               href="{{ url_for('admin_upload_document') }}">
                Upload Document
            </a>

            <a class="btn success"
               href="{{ url_for('admin_upload_resource') }}">
                Upload Resource
            </a>
        </div>
        {% endif %}

        <div class="grid">

        {% for item in rows %}

        <div class="card">

            <h3>
                {{ item.title }}
            </h3>

            <p class="muted">
                {{ item.description or "" }}
            </p>

            <p>
                <span class="badge">
                    {{ item.document_type }}
                </span>
            </p>

            <p>
                {{ item.subject or "" }}
                {% if item.class_level %}
                • {{ item.class_level }}
                {% endif %}
            </p>

            <p class="muted">
                Views: {{ item.view_count }}
                • Downloads: {{ item.download_count }}
            </p>

            <div class="actions">

                <a class="btn"
                   href="{{ url_for(
                       'view_document',
                       document_id=item.id
                   ) }}">
                    View
                </a>

                <a class="btn success"
                   href="{{ url_for(
                       'download_document',
                       document_id=item.id
                   ) }}">
                    Download
                </a>

                {% if session.get("role") == "admin" %}

                <form method="post"
                      action="{{ url_for(
                          'toggle_document',
                          document_id=item.id
                      ) }}">

                    <input
                        type="hidden"
                        name="csrf_token"
                        value="{{ csrf_token() }}"
                    >

                    <button class="btn danger">
                        Hide
                    </button>

                </form>

                {% endif %}

            </div>

        </div>

        {% else %}

        <div class="card">
            <p>No documents found.</p>
        </div>

        {% endfor %}

        </div>
        """,
        rows=rows,
        search=search,
    )

    return render_template_string(
        BASE_HTML,
        title="Library",
        body=body,
    )


# ============================================================
# ADMIN DOCUMENT UPLOAD
# ============================================================

@app.route(
    "/admin/documents/upload",
    methods=["GET", "POST"],
)
@admin_required
def admin_upload_document():

    if request.method == "POST":
        validate_csrf()

        title = request.form.get(
            "title",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        document_type = request.form.get(
            "document_type",
            "academic",
        ).strip()

        subject = request.form.get(
            "subject",
            "",
        ).strip()

        course = request.form.get(
            "course",
            "",
        ).strip()

        class_level = request.form.get(
            "class_level",
            "",
        ).strip()

        is_public = (
            request.form.get("is_public")
            == "on"
        )

        file = request.files.get(
            "file"
        )

        if not title or not file:
            flash(
                "Title and file are required.",
                "error",
            )
            return redirect(
                url_for(
                    "admin_upload_document"
                )
            )

        if not valid_file(file):
            flash(
                "Unsupported document type.",
                "error",
            )
            return redirect(
                url_for(
                    "admin_upload_document"
                )
            )

        file_name = secure_filename(
            file.filename
        )

        file.stream.seek(0)
        file_size = len(
            file.stream.read()
        )
        file.stream.seek(0)

        mime_type = detect_mime(
            file_name,
            file.mimetype,
        )

        file_path = safe_storage_name(
            file_name,
            "documents",
        )

        try:

            storage_upload(
                file,
                file_path,
                mime_type,
            )

            db_insert(
                "documents",
                {
                    "title": title,
                    "description": description,
                    "document_type": document_type,
                    "subject": subject,
                    "course": course,
                    "class_level": class_level,
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_url": None,
                    "file_size": file_size,
                    "mime_type": mime_type,
                    "uploaded_by": session["user_id"],
                    "is_public": is_public,
                    "is_active": True,
                },
                returning=False,
            )

            log_event(
                "Document uploaded",
                category="Documents",
            )

            flash(
                "Document uploaded.",
                "success",
            )

            return redirect(
                url_for("documents")
            )

        except Exception as exc:

            logger.exception(exc)

            storage_delete(file_path)

            flash(
                f"Upload failed: {exc}",
                "error",
            )

    body = render_template_string(
        """
        <div class="card">

            <h1>Upload Academic Document</h1>

            <form method="post"
                  enctype="multipart/form-data">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="form-group">
                    <label>Title</label>
                    <input
                        name="title"
                        required
                    >
                </div>

                <div class="form-group">
                    <label>Description</label>
                    <textarea name="description"></textarea>
                </div>

                <div class="grid-2">

                    <div class="form-group">
                        <label>Document Type</label>
                        <select name="document_type">
                            <option>academic</option>
                            <option>past_paper</option>
                            <option>notes</option>
                            <option>book</option>
                            <option>assignment</option>
                            <option>answer</option>
                            <option>other</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label>Subject</label>
                        <input name="subject">
                    </div>

                </div>

                <div class="grid-2">

                    <div class="form-group">
                        <label>Course</label>
                        <input name="course">
                    </div>

                    <div class="form-group">
                        <label>Class / Level</label>
                        <input name="class_level">
                    </div>

                </div>

                <div class="form-group">
                    <label>File</label>
                    <input
                        type="file"
                        name="file"
                        required
                        accept=".pdf,.doc,.docx,.txt,.rtf,.odt,.xls,.xlsx,.ppt,.pptx,.csv"
                    >
                </div>

                <div class="form-group">
                    <label>
                        <input
                            type="checkbox"
                            name="is_public"
                        >
                        Public document
                    </label>
                </div>

                <button class="btn">
                    Upload
                </button>

            </form>

        </div>
        """
    )

    return render_template_string(
        BASE_HTML,
        title="Upload Document",
        body=body,
    )


# ============================================================
# VIEW DOCUMENT
# ============================================================

@app.route(
    "/documents/<document_id>/view"
)
@login_required
def view_document(document_id):

    rows = db_get(
        "documents",
        {
            "id": f"eq.{document_id}",
            "is_active": "eq.true",
            "select": "*",
            "limit": "1",
        },
    )

    if not rows:
        abort(404)

    document = rows[0]

    db_patch(
        "documents",
        {
            "id": f"eq.{document_id}"
        },
        {
            "view_count": int(
                document.get("view_count") or 0
            ) + 1,
        },
        returning=False,
    )

    log_document_access(
        document_id,
        "view",
    )

    signed = create_signed_url(
        document["file_path"],
        expires=600,
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# DOWNLOAD DOCUMENT
# ============================================================

@app.route(
    "/documents/<document_id>/download"
)
@login_required
def download_document(document_id):

    rows = db_get(
        "documents",
        {
            "id": f"eq.{document_id}",
            "is_active": "eq.true",
            "select": "*",
            "limit": "1",
        },
    )

    if not rows:
        abort(404)

    document = rows[0]

    db_patch(
        "documents",
        {
            "id": f"eq.{document_id}"
        },
        {
            "download_count": int(
                document.get("download_count") or 0
            ) + 1,
        },
        returning=False,
    )

    db_insert(
        "download_history",
        {
            "user_id": session["user_id"],
            "document_id": document_id,
            "file_name": document.get(
                "file_name"
            ),
        },
        returning=False,
    )

    log_document_access(
        document_id,
        "download",
    )

    signed = create_signed_url(
        document["file_path"],
        expires=600,
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# TOGGLE DOCUMENT
# ============================================================

@app.route(
    "/admin/documents/<document_id>/toggle",
    methods=["POST"],
)
@admin_required
def toggle_document(document_id):

    validate_csrf()

    rows = db_get(
        "documents",
        {
            "id": f"eq.{document_id}",
            "select": "id,is_active",
            "limit": "1",
        },
    )

    if not rows:
        abort(404)

    current = rows[0]["is_active"]

    db_patch(
        "documents",
        {
            "id": f"eq.{document_id}"
        },
        {
            "is_active": not current
        },
        returning=False,
    )

    flash(
        "Document visibility updated.",
        "success",
    )

    return redirect(
        url_for("documents")
    )


# ============================================================
# QUESTIONS
# ============================================================

@app.route("/questions")
@login_required
def questions():

    if session.get("role") == "admin":

        rows = db_get(
            "questions",
            {
                "select": "*",
                "order": "created_at.desc",
                "limit": "100",
            },
        )

    else:

        rows = db_get(
            "questions",
            {
                "student_id": f"eq.{session['user_id']}",
                "select": "*",
                "order": "created_at.desc",
                "limit": "100",
            },
        )

    body = render_template_string(
        """
        <div class="actions"
             style="margin-bottom:15px;">

            <a class="btn"
               href="{{ url_for('new_question') }}">
                Ask Question
            </a>

        </div>

        <div class="card">

            <h1>Questions</h1>

            <div class="table-wrap">

            <table>

            <tr>
                <th>Question</th>
                <th>Student</th>
                <th>Subject</th>
                <th>Status</th>
                <th>Answer</th>
            </tr>

            {% for item in rows %}

            <tr>

                <td>
                    {{ item.question }}
                </td>

                <td>
                    {{ item.student_name }}
                </td>

                <td>
                    {{ item.subject or "-" }}
                </td>

                <td>
                    <span class="badge">
                        {{ item.status or "pending" }}
                    </span>
                </td>

                <td>
                    {{ item.answer or "Not answered" }}
                </td>

            </tr>

            {% else %}

            <tr>
                <td colspan="5">
                    No questions found.
                </td>
            </tr>

            {% endfor %}

            </table>

            </div>

        </div>
        """,
        rows=rows,
    )

    return render_template_string(
        BASE_HTML,
        title="Questions",
        body=body,
    )


# ============================================================
# NEW QUESTION
# ============================================================

@app.route(
    "/questions/new",
    methods=["GET", "POST"],
)
@login_required
def new_question():

    if request.method == "POST":

        validate_csrf()

        question_text = request.form.get(
            "question",
            "",
        ).strip()

        subject = request.form.get(
            "subject",
            "",
        ).strip()

        course = request.form.get(
            "course",
            "",
        ).strip()

        class_level = request.form.get(
            "class_level",
            "",
        ).strip()

        if not question_text:
            flash(
                "Question is required.",
                "error",
            )
            return redirect(
                url_for("new_question")
            )

        db_insert(
            "questions",
            {
                "student_id": session["user_id"],
                "student_name": session.get(
                    "name",
                    "",
                ),
                "question": question_text,
                "answer": "",
                "answer_by": "",
                "subject": subject,
                "course": course,
                "class_level": class_level,
                "status": "pending",
            },
            returning=False,
        )

        log_event(
            "Student submitted question",
            category="Questions",
        )

        flash(
            "Question submitted.",
            "success",
        )

        return redirect(
            url_for("questions")
        )

    body = render_template_string(
        """
        <div class="card">

            <h1>Ask Academic Question</h1>

            <form method="post">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="grid-2">

                    <div class="form-group">
                        <label>Subject</label>
                        <input name="subject">
                    </div>

                    <div class="form-group">
                        <label>Course</label>
                        <input name="course">
                    </div>

                </div>

                <div class="form-group">
                    <label>Class / Level</label>
                    <input name="class_level">
                </div>

                <div class="form-group">
                    <label>Question</label>
                    <textarea
                        name="question"
                        required
                    ></textarea>
                </div>

                <button class="btn">
                    Submit Question
                </button>

            </form>

        </div>
        """
    )

    return render_template_string(
        BASE_HTML,
        title="Ask Question",
        body=body,
    )


# ============================================================
# ADMIN ANSWER QUESTION
# ============================================================

@app.route(
    "/admin/questions/<question_id>/answer",
    methods=["POST"],
)
@admin_required
def answer_question(question_id):

    validate_csrf()

    answer = request.form.get(
        "answer",
        "",
    ).strip()

    if not answer:
        flash(
            "Answer cannot be empty.",
            "error",
        )
        return redirect(
            url_for("admin_dashboard")
        )

    db_patch(
        "questions",
        {
            "id": f"eq.{question_id}"
        },
        {
            "answer": answer,
            "answer_by": session.get(
                "name",
                "Admin",
            ),
            "answered_by": session["user_id"],
            "answered_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "status": "answered",
        },
        returning=False,
    )

    # Also preserve the answer in the answers table.
    try:

        db_insert(
            "answers",
            {
                "question_id": question_id,
                "admin_id": session["user_id"],
                "answer": answer,
            },
            returning=False,
        )

    except Exception:
        logger.exception(
            "Could not create answers record"
        )

    flash(
        "Question answered.",
        "success",
    )

    return redirect(
        url_for("admin_dashboard")
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    def count(table):
        try:
            rows = db_get(
                table,
                {
                    "select": "id",
                    "limit": "1000",
                },
            )
            return len(rows)
        except Exception:
            return 0

    stats = {
        "students": count("profiles"),
        "assignments": count("assignments"),
        "questions": count("questions"),
        "documents": count("documents"),
        "resources": count("resources"),
        "products": count("products"),
        "payments": count("payments"),
        "purchases": count("purchases"),
    }

    try:
        recent_questions = db_get(
            "questions",
            {
                "select": "*",
                "order": "created_at.desc",
                "limit": "20",
            },
        )
    except Exception:
        recent_questions = []

    body = render_template_string(
        """
        <div class="hero">
            <h1>KOJA AFRICA Admin</h1>

            <p>
                Administration and academic content management.
            </p>
        </div>

        <div class="grid">

            {% for key, value in stats.items() %}

            <div class="card">
                <h3>
                    {{ key.replace("_", " ")|title }}
                </h3>

                <div class="stat">
                    {{ value }}
                </div>
            </div>

            {% endfor %}

        </div>

        <div class="card">

            <h2>Management</h2>

            <div class="actions">

                <a class="btn"
                   href="{{ url_for(
                       'admin_new_assignment'
                   ) }}">
                    Assign Work
                </a>

                <a class="btn"
                   href="{{ url_for(
                       'admin_upload_document'
                   ) }}">
                    Upload Document
                </a>

                <a class="btn"
                   href="{{ url_for(
                       'admin_upload_resource'
                   ) }}">
                    Upload Resource
                </a>

                <a class="btn"
                   href="{{ url_for(
                       'admin_products'
                   ) }}">
                    Products
                </a>

                <a class="btn"
                   href="{{ url_for(
                       'admin_payments'
                   ) }}">
                    Payments
                </a>

                <a class="btn"
                   href="{{ url_for(
                       'admin_logs'
                   ) }}">
                    Activity Logs
                </a>

            </div>

        </div>

        <div class="card">

            <h2>Recent Questions</h2>

            {% for q in recent_questions %}

            <div class="card">

                <strong>
                    {{ q.student_name }}
                </strong>

                <p>
                    {{ q.question }}
                </p>

                <p>
                    <span class="badge">
                        {{ q.status }}
                    </span>
                </p>

                {% if q.status != "answered" %}

                <form method="post"
                      action="{{ url_for(
                          'answer_question',
                          question_id=q.id
                      ) }}">

                    <input
                        type="hidden"
                        name="csrf_token"
                        value="{{ csrf_token() }}"
                    >

                    <textarea
                        name="answer"
                        placeholder="Write answer..."
                        required
                    ></textarea>

                    <br>

                    <button class="btn success">
                        Answer
                    </button>

                </form>

                {% endif %}

            </div>

            {% else %}

            <p>No questions.</p>

            {% endfor %}

        </div>
        """,
        stats=stats,
        recent_questions=recent_questions,
    )

    return render_template_string(
        BASE_HTML,
        title="Admin",
        body=body,
    )


# ============================================================
# RESOURCES
# ============================================================

@app.route("/resources")
@login_required
def resources():

    rows = db_get(
        "resources",
        {
            "is_active": "eq.true",
            "select": "*",
            "order": "created_at.desc",
            "limit": "100",
        },
    )

    body = render_template_string(
        """
        <div class="card">

            <h1>Resources</h1>

            {% if session.get("role") == "admin" %}

            <a class="btn"
               href="{{ url_for(
                   'admin_upload_resource'
               ) }}">
                Upload Resource
            </a>

            {% endif %}

        </div>

        <div class="grid">

        {% for item in rows %}

        <div class="card">

            <h3>{{ item.title }}</h3>

            <p>
                {{ item.description or "" }}
            </p>

            <p class="muted">
                {{ item.subject or "" }}
                {% if item.level %}
                • {{ item.level }}
                {% endif %}
            </p>

            {% if item.is_paid %}

            <span class="badge warning">
                Paid: {{ item.price }}
            </span>

            {% else %}

            <span class="badge success">
                Free
            </span>

            {% endif %}

            <br><br>

            {% if item.file_path %}

            <a class="btn"
               href="{{ url_for(
                   'resource_file',
                   resource_id=item.id
               ) }}">
                Open
            </a>

            {% endif %}

        </div>

        {% else %}

        <div class="card">
            No resources found.
        </div>

        {% endfor %}

        </div>
        """,
        rows=rows,
    )

    return render_template_string(
        BASE_HTML,
        title="Resources",
        body=body,
    )


# ============================================================
# ADMIN RESOURCE UPLOAD
# ============================================================

@app.route(
    "/admin/resources/upload",
    methods=["GET", "POST"],
)
@admin_required
def admin_upload_resource():

    if request.method == "POST":

        validate_csrf()

        title = request.form.get(
            "title",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        subject = request.form.get(
            "subject",
            "",
        ).strip()

        level = request.form.get(
            "level",
            "",
        ).strip()

        try:
            price = float(
                request.form.get(
                    "price",
                    "0",
                )
            )
        except Exception:
            price = 0

        is_paid = (
            request.form.get("is_paid")
            == "on"
        )

        file = request.files.get(
            "file"
        )

        if not title or not file:
            flash(
                "Title and file are required.",
                "error",
            )
            return redirect(
                url_for(
                    "admin_upload_resource"
                )
            )

        if not valid_file(file):
            flash(
                "Unsupported resource file.",
                "error",
            )
            return redirect(
                url_for(
                    "admin_upload_resource"
                )
            )

        file_name = secure_filename(
            file.filename
        )

        file.stream.seek(0)
        file_size = len(
            file.stream.read()
        )
        file.stream.seek(0)

        mime_type = detect_mime(
            file_name,
            file.mimetype,
        )

        file_path = safe_storage_name(
            file_name,
            "resources",
        )

        try:

            storage_upload(
                file,
                file_path,
                mime_type,
            )

            db_insert(
                "resources",
                {
                    "uploaded_by": session["user_id"],
                    "title": title,
                    "description": description,
                    "subject": subject,
                    "level": level,
                    "file_name": file_name,
                    "file_path": file_path,
                    "price": price,
                    "is_paid": is_paid,
                    "is_active": True,
                },
                returning=False,
            )

            log_event(
                "Resource uploaded",
                category="Resources",
            )

            flash(
                "Resource uploaded.",
                "success",
            )

            return redirect(
                url_for("resources")
            )

        except Exception as exc:

            logger.exception(exc)

            storage_delete(file_path)

            flash(
                f"Resource upload failed: {exc}",
                "error",
            )

    body = render_template_string(
        """
        <div class="card">

            <h1>Upload Resource</h1>

            <form method="post"
                  enctype="multipart/form-data">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="form-group">
                    <label>Title</label>
                    <input
                        name="title"
                        required
                    >
                </div>

                <div class="form-group">
                    <label>Description</label>
                    <textarea name="description"></textarea>
                </div>

                <div class="grid-2">

                    <div class="form-group">
                        <label>Subject</label>
                        <input name="subject">
                    </div>

                    <div class="form-group">
                        <label>Level</label>
                        <input name="level">
                    </div>

                </div>

                <div class="form-group">
                    <label>Price</label>
                    <input
                        type="number"
                        step="0.01"
                        min="0"
                        name="price"
                        value="0"
                    >
                </div>

                <div class="form-group">

                    <label>
                        <input
                            type="checkbox"
                            name="is_paid"
                        >
                        Paid resource
                    </label>

                </div>

                <div class="form-group">
                    <label>File</label>

                    <input
                        type="file"
                        name="file"
                        required
                        accept=".pdf,.doc,.docx,.txt,.rtf,.odt,.xls,.xlsx,.ppt,.pptx,.csv"
                    >
                </div>

                <button class="btn">
                    Upload Resource
                </button>

            </form>

        </div>
        """
    )

    return render_template_string(
        BASE_HTML,
        title="Upload Resource",
        body=body,
    )


# ============================================================
# RESOURCE FILE
# ============================================================

@app.route(
    "/resources/<resource_id>/file"
)
@login_required
def resource_file(resource_id):

    rows = db_get(
        "resources",
        {
            "id": f"eq.{resource_id}",
            "is_active": "eq.true",
            "select": "*",
            "limit": "1",
        },
    )

    if not rows:
        abort(404)

    resource = rows[0]

    if resource.get("is_paid"):

        purchase_rows = db_get(
            "resource_purchases",
            {
                "resource_id": f"eq.{resource_id}",
                "user_id": f"eq.{session['user_id']}",
                "select": "*",
                "limit": "1",
            },
        )

        if not purchase_rows:
            abort(403)

    signed = create_signed_url(
        resource["file_path"],
        expires=600,
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# PRODUCTS
# ============================================================

@app.route("/admin/products")
@admin_required
def admin_products():

    rows = db_get(
        "products",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "100",
        },
    )

    body = render_template_string(
        """
        <div class="card">

            <h1>Products</h1>

            <a class="btn"
               href="{{ url_for(
                   'new_product'
               ) }}">
                Create Product
            </a>

        </div>

        <div class="card">

        <div class="table-wrap">

        <table>

        <tr>
            <th>Title</th>
            <th>Price</th>
            <th>Type</th>
            <th>Free</th>
            <th>Published</th>
        </tr>

        {% for item in rows %}

        <tr>

            <td>{{ item.title }}</td>

            <td>
                {{ item.price }}
                {{ item.currency }}
            </td>

            <td>{{ item.product_type }}</td>

            <td>{{ item.is_free }}</td>

            <td>{{ item.is_published }}</td>

        </tr>

        {% endfor %}

        </table>

        </div>

        </div>
        """,
        rows=rows,
    )

    return render_template_string(
        BASE_HTML,
        title="Products",
        body=body,
    )


# ============================================================
# NEW PRODUCT
# ============================================================

@app.route(
    "/admin/products/new",
    methods=["GET", "POST"],
)
@admin_required
def new_product():

    if request.method == "POST":

        validate_csrf()

        title = request.form.get(
            "title",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        try:
            price = float(
                request.form.get(
                    "price",
                    "0",
                )
            )
        except Exception:
            price = 0

        product_type = request.form.get(
            "product_type",
            "document",
        )

        is_free = (
            request.form.get("is_free")
            == "on"
        )

        is_published = (
            request.form.get("is_published")
            == "on"
        )

        if not title:
            flash(
                "Product title is required.",
                "error",
            )
            return redirect(
                url_for("new_product")
            )

        db_insert(
            "products",
            {
                "title": title,
                "description": description,
                "price": price,
                "currency": "ZMW",
                "product_type": product_type,
                "is_free": is_free,
                "is_published": is_published,
                "created_by": session["user_id"],
            },
            returning=False,
        )

        flash(
            "Product created.",
            "success",
        )

        return redirect(
            url_for("admin_products")
        )

    body = render_template_string(
        """
        <div class="card">

            <h1>Create Product</h1>

            <form method="post">

                <input
                    type="hidden"
                    name="csrf_token"
                    value="{{ csrf_token() }}"
                >

                <div class="form-group">
                    <label>Title</label>
                    <input
                        name="title"
                        required
                    >
                </div>

                <div class="form-group">
                    <label>Description</label>
                    <textarea name="description"></textarea>
                </div>

                <div class="form-group">
                    <label>Price (ZMW)</label>
                    <input
                        type="number"
                        step="0.01"
                        name="price"
                        value="0"
                    >
                </div>

                <div class="form-group">
                    <label>Product Type</label>
                    <select name="product_type">
                        <option>document</option>
                        <option>resource</option>
                        <option>book</option>
                        <option>past_paper</option>
                        <option>notes</option>
                        <option>other</option>
                    </select>
                </div>

                <label>
                    <input
                        type="checkbox"
                        name="is_free"
                    >
                    Free
                </label>

                <br><br>

                <label>
                    <input
                        type="checkbox"
                        name="is_published"
                    >
                    Published
                </label>

                <br><br>

                <button class="btn">
                    Create Product
                </button>

            </form>

        </div>
        """
    )

    return render_template_string(
        BASE_HTML,
        title="Create Product",
        body=body,
    )


# ============================================================
# PAYMENTS
# ============================================================

@app.route("/admin/payments")
@admin_required
def admin_payments():

    rows = db_get(
        "payments",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "200",
        },
    )

    body = render_template_string(
        """
        <div class="card">

            <h1>Payments</h1>

            <div class="table-wrap">

            <table>

            <tr>
                <th>User</th>
                <th>Amount</th>
                <th>Currency</th>
                <th>Status</th>
                <th>Reference</th>
                <th>Date</th>
            </tr>

            {% for item in rows %}

            <tr>
                <td>{{ item.user_id }}</td>
                <td>{{ item.amount }}</td>
                <td>{{ item.currency }}</td>
                <td>{{ item.status }}</td>
                <td>{{ item.transaction_reference }}</td>
                <td>{{ item.created_at }}</td>
            </tr>

            {% endfor %}

            </table>

            </div>

        </div>
        """,
        rows=rows,
    )

    return render_template_string(
        BASE_HTML,
        title="Payments",
        body=body,
    )


# ============================================================
# ADMIN LOGS
# ============================================================

@app.route("/admin/logs")
@admin_required
def admin_logs():

    rows = db_get(
        "logs",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "200",
        },
    )

    body = render_template_string(
        """
        <div class="card">

            <h1>Activity Logs</h1>

            <div class="table-wrap">

            <table>

            <tr>
                <th>Event</th>
                <th>Category</th>
                <th>Level</th>
                <th>Details</th>
                <th>User</th>
                <th>Date</th>
            </tr>

            {% for item in rows %}

            <tr>
                <td>{{ item.event }}</td>
                <td>{{ item.category }}</td>
                <td>{{ item.level }}</td>
                <td>{{ item.details }}</td>
                <td>{{ item.user_id }}</td>
                <td>{{ item.created_at }}</td>
            </tr>

            {% endfor %}

            </table>

            </div>

        </div>
        """,
        rows=rows,
    )

    return render_template_string(
        BASE_HTML,
        title="Logs",
        body=body,
    )


# ============================================================
# ADMIN STUDENTS
# ============================================================

@app.route("/admin/students")
@admin_required
def admin_students():

    rows = db_get(
        "profiles",
        {
            "select": "id,name,email,role,created_at",
            "order": "created_at.desc",
            "limit": "500",
        },
    )

    body = render_template_string(
        """
        <div class="card">

            <h1>Students</h1>

            <div class="table-wrap">

            <table>

            <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>ID</th>
                <th>Created</th>
            </tr>

            {% for student in rows %}

            <tr>
                <td>{{ student.name }}</td>
                <td>{{ student.email }}</td>
                <td>{{ student.role }}</td>
                <td>{{ student.id }}</td>
                <td>{{ student.created_at }}</td>
            </tr>

            {% endfor %}

            </table>

            </div>

        </div>
        """,
        rows=rows,
    )

    return render_template_string(
        BASE_HTML,
        title="Students",
        body=body,
    )


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile")
@login_required
def profile():

    profile_data = current_profile()

    body = render_template_string(
        """
        <div class="card">

            <h1>My Profile</h1>

            <p>
                <strong>Name:</strong>
                {{ profile.name }}
            </p>

            <p>
                <strong>Email:</strong>
                {{ profile.email }}
            </p>

            <p>
                <strong>Role:</strong>
                {{ profile.role }}
            </p>

            <p>
                <strong>User ID:</strong>
                {{ profile.id }}
            </p>

        </div>
        """,
        profile=profile_data or {},
    )

    return render_template_string(
        BASE_HTML,
        title="Profile",
        body=body,
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    if not SUPABASE_URL:
        return jsonify(
            {
                "status": "error",
                "message": "SUPABASE_URL is missing",
            }
        ), 500

    if not SUPABASE_SECRET_KEY:
        return jsonify(
            {
                "status": "error",
                "message": "Supabase server key is missing",
            }
        ), 500

    return jsonify(
        {
            "status": "ok",
            "app": APP_NAME,
            "supabase_configured": True,
        }
    )


# ============================================================
# API: CURRENT USER
# ============================================================

@app.route("/api/me")
@login_required
def api_me():

    return jsonify(
        {
            "id": session.get("user_id"),
            "email": session.get("email"),
            "name": session.get("name"),
            "role": session.get("role"),
        }
    )


# ============================================================
# API: DASHBOARD COUNTS
# ============================================================

@app.route("/api/dashboard")
@login_required
def api_dashboard():

    user_id = session["user_id"]

    try:

        assignments = db_get(
            "assignments",
            {
                "student_id": f"eq.{user_id}",
                "select": "id",
                "limit": "1000",
            },
        )

    except Exception:
        assignments = []

    try:

        questions = db_get(
            "questions",
            {
                "student_id": f"eq.{user_id}",
                "select": "id",
                "limit": "1000",
            },
        )

    except Exception:
        questions = []

    return jsonify(
        {
            "assignments": len(assignments),
            "questions": len(questions),
        }
    )


# ============================================================
# SECURITY HEADERS
# ============================================================

@app.after_request
def security_headers(response):

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    response.headers[
        "Permissions-Policy"
    ] = (
        "camera=(), microphone=(), geolocation=()"
    )

    return response


# ============================================================
# ERROR PAGES
# ============================================================

@app.errorhandler(400)
def bad_request(error):

    body = """
    <div class="card">
        <h1>400 — Bad Request</h1>

        <p>
            The request could not be understood.
            Your session may have expired or the form
            security token may no longer be valid.
        </p>

        <a class="btn" href="/">
            Return Home
        </a>
    </div>
    """

    return render_template_string(
        BASE_HTML,
        title="Bad Request",
        body=body,
    ), 400


@app.errorhandler(403)
def forbidden(error):

    body = """
    <div class="card">
        <h1>403 — Access Denied</h1>

        <p>
            You do not have permission to access this page.
        </p>

        <a class="btn" href="/">
            Return Home
        </a>
    </div>
    """

    return render_template_string(
        BASE_HTML,
        title="Forbidden",
        body=body,
    ), 403


@app.errorhandler(404)
def not_found(error):

    body = """
    <div class="card">
        <h1>404 — Not Found</h1>

        <p>
            The requested page or file does not exist.
        </p>

        <a class="btn" href="/">
            Return Home
        </a>
    </div>
    """

    return render_template_string(
        BASE_HTML,
        title="Not Found",
        body=body,
    ), 404


@app.errorhandler(413)
def too_large(error):

    body = """
    <div class="card">
        <h1>413 — File Too Large</h1>

        <p>
            The uploaded file is larger than the configured
            upload limit.
        </p>

        <a class="btn" href="/">
            Return Home
        </a>
    </div>
    """

    return render_template_string(
        BASE_HTML,
        title="File Too Large",
        body=body,
    ), 413


@app.errorhandler(500)
def internal_error(error):

    logger.exception(
        "Unhandled application error"
    )

    body = """
    <div class="card">
        <h1>500 — Server Error</h1>

        <p>
            KOJA AFRICA encountered an unexpected server error.
            Check the Render logs for the technical details.
        </p>

        <a class="btn" href="/">
            Return Home
        </a>
    </div>
    """

    return render_template_string(
        BASE_HTML,
        title="Server Error",
        body=body,
    ), 500


# ============================================================
# STARTUP
# ============================================================

@app.before_request
def startup_checks():

    # Keep the session CSRF token stable for the life
    # of the current session. Do not rotate it on every request.
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000",
        )
    )

    host = os.environ.get(
        "HOST",
        "0.0.0.0",
    )

    logger.info(
        "%s starting on %s:%s",
        APP_NAME,
        host,
        port,
    )

    app.run(
        host=host,
        port=port,
        debug=False,
    )
