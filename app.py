# ============================================================
# KOJA AFRICA
# Single-file Flask + Supabase application
#
# Supports:
# - Student registration/login
# - Password recovery
# - Admin login
# - Student dashboard
# - Admin dashboard
# - Assignment/question upload
# - PDF/DOC/DOCX uploads
# - Admin answer upload
# - PDF answer generation
# - Assignment responses
# - Academic questions and answers
# - Documents/library
# - Resources
# - Products/purchases/payment records
# - Download/view logging
# - Private Supabase Storage
# - Signed URLs
# - CSRF protection
# - Render deployment
# ============================================================

import os
import io
import re
import uuid
import hmac
import hashlib
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
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
)
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from dotenv import load_dotenv

# ------------------------------------------------------------
# ENVIRONMENT
# ------------------------------------------------------------

load_dotenv()

APP_NAME = "KOJA AFRICA"

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

SECRET_KEY = os.getenv("SECRET_KEY", "")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

# Storage buckets
ASSIGNMENT_BUCKET = os.getenv(
    "ASSIGNMENT_BUCKET",
    "koja-assignments"
)

ANSWER_BUCKET = os.getenv(
    "ANSWER_BUCKET",
    "koja-answers"
)

DOCUMENT_BUCKET = os.getenv(
    "DOCUMENT_BUCKET",
    "koja-documents"
)

RESOURCE_BUCKET = os.getenv(
    "RESOURCE_BUCKET",
    "koja-resources"
)

# Optional admin email list.
# Example:
# ADMIN_EMAILS=admin@example.com,another@example.com
ADMIN_EMAILS = {
    x.strip().lower()
    for x in os.getenv("ADMIN_EMAILS", "").split(",")
    if x.strip()
}

if not SECRET_KEY:
    # For production you should set SECRET_KEY in Render.
    SECRET_KEY = secrets.token_hex(32)

if not SUPABASE_URL:
    logging.warning("SUPABASE_URL is not configured.")

if not SUPABASE_SERVICE_ROLE_KEY:
    logging.warning(
        "SUPABASE_SERVICE_ROLE_KEY is not configured."
    )

# ------------------------------------------------------------
# FLASK
# ------------------------------------------------------------

app = Flask(__name__)
app.secret_key = SECRET_KEY

app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv(
        "SESSION_COOKIE_SECURE",
        "1"
    ) == "1",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja_africa")

# ------------------------------------------------------------
# FILE TYPES
# ------------------------------------------------------------

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "rtf",
    "odt",
}

MIME_TYPES = {
    ".pdf": "application/pdf",

    ".doc": "application/msword",

    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),

    ".txt": "text/plain",

    ".rtf": "application/rtf",

    ".odt": (
        "application/vnd.oasis.opendocument.text"
    ),
}


# ============================================================
# SECURITY HELPERS
# ============================================================

def csrf_token():
    """
    Stable CSRF token for the current browser session.

    Unlike regenerating the token on every request, this prevents
    legitimate forms from failing because an old/stale session
    suddenly contains a different token.
    """
    token = session.get("_csrf_token")

    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token

    return token


@app.context_processor
def inject_globals():
    return {
        "app_name": APP_NAME,
        "csrf_token": csrf_token(),
        "current_user": session.get("user"),
        "is_admin": session.get("role") == "admin",
    }


@app.before_request
def csrf_check():
    """
    Validate CSRF on state-changing requests.

    GET/HEAD/OPTIONS are intentionally ignored.
    """
    if request.method in {
        "GET",
        "HEAD",
        "OPTIONS",
    }:
        return

    submitted = request.form.get("_csrf", "")

    expected = session.get("_csrf_token", "")

    if not expected or not submitted:
        abort(400)

    if not hmac.compare_digest(
        str(submitted),
        str(expected)
    ):
        abort(400)


@app.errorhandler(400)
def bad_request(error):
    return render_template_string(
        ERROR_PAGE,
        code=400,
        message=(
            "The request could not be understood. "
            "Please refresh the page and try again."
        ),
    ), 400


@app.errorhandler(403)
def forbidden(error):
    return render_template_string(
        ERROR_PAGE,
        code=403,
        message="You are not allowed to perform this action.",
    ), 403


@app.errorhandler(404)
def not_found(error):
    return render_template_string(
        ERROR_PAGE,
        code=404,
        message="The page you requested was not found.",
    ), 404


@app.errorhandler(413)
def too_large(error):
    return render_template_string(
        ERROR_PAGE,
        code=413,
        message=(
            f"The uploaded file is too large. "
            f"Maximum size is {MAX_UPLOAD_MB} MB."
        ),
    ), 413


# ============================================================
# SUPABASE HELPERS
# ============================================================

def service_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": (
            f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
        ),
        "Content-Type": "application/json",
    }


def anon_headers():
    key = SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY

    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def rest_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"


def supabase_get(
    table,
    params=None,
    limit=None,
):
    params = dict(params or {})

    if limit is not None:
        params.setdefault("limit", str(limit))

    response = requests.get(
        rest_url(table),
        headers=service_headers(),
        params=params,
        timeout=30,
    )

    if not response.ok:
        logger.error(
            "Supabase GET %s failed: %s",
            table,
            response.text[:1000],
        )
        raise RuntimeError(
            f"Database GET failed for {table}"
        )

    return response.json()


def supabase_insert(
    table,
    data,
    select="*",
):
    response = requests.post(
        rest_url(table),
        headers={
            **service_headers(),
            "Prefer": "return=representation",
        },
        params={"select": select},
        json=data,
        timeout=30,
    )

    if not response.ok:
        logger.error(
            "Supabase INSERT %s failed: %s",
            table,
            response.text[:2000],
        )
        raise RuntimeError(
            f"Database INSERT failed for {table}: "
            f"{response.text[:500]}"
        )

    return response.json()


def supabase_update(
    table,
    filters,
    data,
    select="*",
):
    params = dict(filters or {})
    params["select"] = select

    response = requests.patch(
        rest_url(table),
        headers={
            **service_headers(),
            "Prefer": "return=representation",
        },
        params=params,
        json=data,
        timeout=30,
    )

    if not response.ok:
        logger.error(
            "Supabase UPDATE %s failed: %s",
            table,
            response.text[:2000],
        )
        raise RuntimeError(
            f"Database UPDATE failed for {table}: "
            f"{response.text[:500]}"
        )

    return response.json()


def supabase_delete(table, filters):
    response = requests.delete(
        rest_url(table),
        headers=service_headers(),
        params=filters,
        timeout=30,
    )

    if not response.ok:
        logger.error(
            "Supabase DELETE %s failed: %s",
            table,
            response.text[:1000],
        )
        raise RuntimeError(
            f"Database DELETE failed for {table}"
        )

    return True


# ============================================================
# SUPABASE AUTH
# ============================================================

def auth_signup(email, password):
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/signup",
        headers={
            "apikey": SUPABASE_ANON_KEY
            or SUPABASE_SERVICE_ROLE_KEY,
            "Content-Type": "application/json",
        },
        json={
            "email": email,
            "password": password,
        },
        timeout=30,
    )

    return response


def auth_login(email, password):
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/token",
        headers={
            "apikey": SUPABASE_ANON_KEY
            or SUPABASE_SERVICE_ROLE_KEY,
            "Content-Type": "application/json",
        },
        params={
            "grant_type": "password"
        },
        json={
            "email": email,
            "password": password,
        },
        timeout=30,
    )

    return response


def auth_recovery(email):
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/recover",
        headers={
            "apikey": SUPABASE_ANON_KEY
            or SUPABASE_SERVICE_ROLE_KEY,
            "Content-Type": "application/json",
        },
        json={
            "email": email
        },
        timeout=30,
    )

    return response


# ============================================================
# USER / ROLE HELPERS
# ============================================================

def get_profile(user_id):
    rows = supabase_get(
        "profiles",
        {
            "id": f"eq.{user_id}",
            "select": "id,name,email,role,created_at",
        },
        limit=1,
    )

    return rows[0] if rows else None


def get_user_role(user_id, email=None):
    profile = get_profile(user_id)

    if profile:
        role = (profile.get("role") or "student").lower()

        if role in {
            "admin",
            "administrator",
        }:
            return "admin"

    if email and email.lower() in ADMIN_EMAILS:
        return "admin"

    return "student"


def current_user_id():
    user = session.get("user") or {}
    return user.get("id")


def current_email():
    user = session.get("user") or {}
    return user.get("email")


def logged_in():
    return bool(current_user_id())


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not logged_in():
            flash(
                "Please log in first.",
                "warning",
            )
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not logged_in():
            return redirect(url_for("login"))

        if session.get("role") != "admin":
            abort(403)

        return view(*args, **kwargs)

    return wrapped


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
        supabase_insert(
            "logs",
            {
                "event": str(event),
                "category": str(category),
                "level": str(level),
                "details": str(details or ""),
                "user_id": user_id,
            },
            select="id",
        )
    except Exception as exc:
        logger.warning(
            "Could not write log: %s",
            exc,
        )


def record_document_action(
    document_id,
    action,
    user_id=None,
):
    try:
        supabase_insert(
            "document_access_logs",
            {
                "document_id": document_id,
                "user_id": user_id,
                "action": action,
            },
            select="id",
        )
    except Exception as exc:
        logger.warning(
            "Document access log failed: %s",
            exc,
        )

    try:
        supabase_insert(
            "document_records",
            {
                "document_id": document_id,
                "user_id": user_id,
                "action": action,
                "ip_address": request.headers.get(
                    "X-Forwarded-For",
                    request.remote_addr,
                ),
                "user_agent": (
                    request.headers.get(
                        "User-Agent",
                        ""
                    )[:1000]
                ),
            },
            select="id",
        )
    except Exception as exc:
        logger.warning(
            "Document record failed: %s",
            exc,
        )


# ============================================================
# FILE HELPERS
# ============================================================

def extension_of(filename):
    filename = secure_filename(filename or "")

    if "." not in filename:
        return ""

    return filename.rsplit(".", 1)[1].lower()


def allowed_file(filename):
    return (
        extension_of(filename)
        in ALLOWED_EXTENSIONS
    )


def safe_original_name(filename):
    filename = secure_filename(
        filename or "file"
    )

    if not filename:
        filename = "file"

    return filename[:200]


def storage_path(prefix, original_name):
    ext = extension_of(original_name)

    random_name = str(uuid.uuid4())

    if ext:
        random_name += "." + ext

    return f"{prefix}/{random_name}"


def upload_to_storage(
    bucket,
    path,
    file_storage,
    content_type=None,
):
    file_storage.stream.seek(0)

    data = file_storage.read()

    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"Maximum upload size is "
            f"{MAX_UPLOAD_MB} MB."
        )

    content_type = (
        content_type
        or file_storage.mimetype
        or "application/octet-stream"
    )

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{bucket}/{path}"
    )

    response = requests.post(
        url,
        headers={
            "Authorization":
                f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "apikey":
                SUPABASE_SERVICE_ROLE_KEY,
            "Content-Type":
                content_type,
            "x-upsert":
                "false",
        },
        data=data,
        timeout=120,
    )

    if not response.ok:
        logger.error(
            "Storage upload failed: %s",
            response.text[:2000],
        )
        raise RuntimeError(
            "Storage upload failed."
        )

    return path, len(data), content_type


def delete_from_storage(bucket, path):
    if not path:
        return

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{bucket}"
    )

    try:
        response = requests.delete(
            url,
            headers={
                "Authorization":
                    f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "apikey":
                    SUPABASE_SERVICE_ROLE_KEY,
                "Content-Type":
                    "application/json",
            },
            json={
                "prefixes": [path]
            },
            timeout=30,
        )

        if not response.ok:
            logger.warning(
                "Storage delete failed: %s",
                response.text[:1000],
            )

    except Exception as exc:
        logger.warning(
            "Storage delete exception: %s",
            exc,
        )


def create_signed_url(
    bucket,
    path,
    expires=900,
):
    if not path:
        return None

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"sign/{bucket}/{path}"
    )

    response = requests.post(
        url,
        headers={
            "Authorization":
                f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "apikey":
                SUPABASE_SERVICE_ROLE_KEY,
            "Content-Type":
                "application/json",
        },
        json={
            "expiresIn": expires
        },
        timeout=30,
    )

    if not response.ok:
        logger.error(
            "Signed URL failed: %s",
            response.text[:1000],
        )
        return None

    data = response.json()

    signed = data.get("signedURL")

    if not signed:
        signed = data.get("signedUrl")

    if not signed:
        return None

    if signed.startswith("http"):
        return signed

    return SUPABASE_URL + "/storage/v1" + signed


def get_upload(
    field_name,
    required=False,
):
    file = request.files.get(field_name)

    if not file:
        if required:
            raise ValueError(
                f"{field_name} is required."
            )

        return None

    filename = safe_original_name(
        file.filename
    )

    if not filename:
        if required:
            raise ValueError(
                f"{field_name} is required."
            )

        return None

    if not allowed_file(filename):
        raise ValueError(
            "Unsupported file type. "
            "Allowed: PDF, DOC, DOCX, TXT, RTF and ODT."
        )

    file.stream.seek(0, 2)
    size = file.stream.tell()
    file.stream.seek(0)

    if size > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"File exceeds {MAX_UPLOAD_MB} MB."
        )

    return file


# ============================================================
# PDF ANSWER GENERATOR
# ============================================================

def clean_pdf_text(text):
    if not text:
        return ""

    text = str(text)

    text = text.replace(
        "&",
        "&amp;"
    )

    text = text.replace(
        "<",
        "&lt;"
    )

    text = text.replace(
        ">",
        "&gt;"
    )

    text = text.replace(
        "\n",
        "<br/>"
    )

    return text


def build_answer_pdf(
    title,
    student_name,
    subject,
    question,
    answer,
):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50,
        title="Answered Assignment",
        author=APP_NAME,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "KOJATitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        leading=22,
        spaceAfter=18,
    )

    heading_style = ParagraphStyle(
        "KOJAHeading",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        spaceBefore=10,
        spaceAfter=8,
    )

    body_style = ParagraphStyle(
        "KOJABody",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=16,
        spaceAfter=10,
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
            f"{clean_pdf_text(title)}",
            body_style,
        )
    )

    story.append(
        Paragraph(
            f"<b>Student:</b> "
            f"{clean_pdf_text(student_name)}",
            body_style,
        )
    )

    if subject:
        story.append(
            Paragraph(
                f"<b>Subject:</b> "
                f"{clean_pdf_text(subject)}",
                body_style,
            )
        )

    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "QUESTION",
            heading_style,
        )
    )

    story.append(
        Paragraph(
            clean_pdf_text(question),
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
            clean_pdf_text(answer),
            body_style,
        )
    )

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            "Generated academic document",
            ParagraphStyle(
                "Footer",
                parent=body_style,
                alignment=TA_CENTER,
                fontSize=8,
            ),
        )
    )

    doc.build(story)

    buffer.seek(0)

    return buffer


# ============================================================
# TEMPLATES
# ============================================================

BASE_HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>
<title>{{ title or app_name }}</title>

<style>
:root {
    --bg: #f5f7fb;
    --card: #ffffff;
    --text: #172033;
    --muted: #697386;
    --primary: #174ea6;
    --primary2: #0b57d0;
    --danger: #b42318;
    --success: #027a48;
    --border: #d9dee8;
}

body.dark {
    --bg: #101318;
    --card: #191d24;
    --text: #f1f3f5;
    --muted: #aeb5c0;
    --border: #333943;
}

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family:
        Arial,
        Helvetica,
        sans-serif;
    background: var(--bg);
    color: var(--text);
}

nav {
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 12px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    position: sticky;
    top: 0;
    z-index: 50;
}

.brand {
    font-weight: 800;
    font-size: 20px;
    color: var(--primary);
}

.navlinks {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

a {
    color: var(--primary);
    text-decoration: none;
}

.navlinks a,
button,
.btn {
    border: 0;
    border-radius: 9px;
    padding: 9px 12px;
    cursor: pointer;
}

.navlinks a {
    background: transparent;
}

button,
.btn {
    background: var(--primary);
    color: white;
    display: inline-block;
}

.btn.secondary {
    background: #64748b;
}

.btn.danger {
    background: var(--danger);
}

.btn.success {
    background: var(--success);
}

.container {
    width: min(1180px, 94%);
    margin: 25px auto;
}

.hero {
    background:
        linear-gradient(
            135deg,
            var(--primary),
            #0a2c63
        );
    color: white;
    padding: 35px;
    border-radius: 18px;
    margin-bottom: 22px;
}

.hero h1 {
    margin-top: 0;
}

.brain {
    width: 85px;
    height: 85px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: rgba(255,255,255,.15);
    font-size: 42px;
    margin-bottom: 15px;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(230px, 1fr));
    gap: 15px;
}

.card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px;
    margin-bottom: 15px;
}

.card h3,
.card h2 {
    margin-top: 0;
}

table {
    width: 100%;
    border-collapse: collapse;
    background: var(--card);
}

th,
td {
    border-bottom: 1px solid var(--border);
    padding: 10px;
    text-align: left;
    vertical-align: top;
}

th {
    font-size: 13px;
}

input,
textarea,
select {
    width: 100%;
    padding: 11px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--card);
    color: var(--text);
    margin: 5px 0 12px;
}

textarea {
    min-height: 130px;
    resize: vertical;
}

label {
    font-weight: 700;
    font-size: 13px;
}

.alert {
    padding: 12px;
    border-radius: 8px;
    margin-bottom: 10px;
    background: #fff3cd;
    color: #664d03;
}

.alert.success {
    background: #d1e7dd;
    color: #0f5132;
}

.alert.error {
    background: #f8d7da;
    color: #842029;
}

.badge {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 999px;
    background: #e7edf8;
    font-size: 12px;
}

.muted {
    color: var(--muted);
}

.stat {
    font-size: 30px;
    font-weight: 800;
}

.actions {
    display: flex;
    gap: 7px;
    flex-wrap: wrap;
}

.small {
    font-size: 12px;
}

footer {
    text-align: center;
    padding: 30px;
    color: var(--muted);
}

@media(max-width:700px) {
    nav {
        align-items: flex-start;
        flex-direction: column;
    }

    table {
        font-size: 13px;
    }

    .hero {
        padding: 22px;
    }
}
</style>

<script>
function toggleDark() {
    document.body.classList.toggle("dark");
    localStorage.setItem(
        "koja_dark",
        document.body.classList.contains("dark")
    );
}

document.addEventListener("DOMContentLoaded", function() {
    if (localStorage.getItem("koja_dark") === "1") {
        document.body.classList.add("dark");
    }
});
</script>
</head>

<body>

<nav>
    <div class="brand">KOJA AFRICA</div>

    <div class="navlinks">
        {% if current_user %}
            {% if is_admin %}
                <a href="{{ url_for('admin_dashboard') }}">
                    Admin
                </a>
            {% else %}
                <a href="{{ url_for('dashboard') }}">
                    Dashboard
                </a>
            {% endif %}

            <a href="{{ url_for('documents') }}">
                Library
            </a>

            <a href="{{ url_for('questions') }}">
                Questions
            </a>

            <a href="{{ url_for('toggle_theme') }}">
                Theme
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
    </div>
</nav>

<div class="container">

{% with messages = get_flashed_messages(
    with_categories=true
) %}

{% for category, message in messages %}
<div class="alert
    {% if category == 'success' %}success
    {% elif category == 'error' %}error
    {% endif %}
">
    {{ message }}
</div>
{% endfor %}

{% endwith %}

{{ body|safe }}

</div>

<footer>
    KOJA AFRICA · Academic Questions · Answers · Resources
</footer>

</body>
</html>
"""


ERROR_PAGE = """
<div class="card" style="text-align:center">
    <h1>{{ code }}</h1>
    <p>{{ message }}</p>
    <a class="btn" href="{{ url_for('index') }}">
        Return Home
    </a>
</div>
"""


def page(title, body):
    return render_template_string(
        BASE_HTML,
        title=title,
        body=render_template_string(
            body,
            **request.view_args,
        ),
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():
    if logged_in():
        if session.get("role") == "admin":
            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("dashboard")
        )

    return page(
        "KOJA AFRICA",
        """
        <div class="hero">
            <div class="brain">🧠</div>
            <h1>KOJA AFRICA</h1>
            <p>
                Assignment Questions · Academic Answers
                · Learning Resources
            </p>

            <div class="actions">
                <a class="btn" href="{{ url_for('login') }}">
                    Login
                </a>

                <a class="btn secondary"
                   href="{{ url_for('register') }}">
                    Create Account
                </a>
            </div>
        </div>

        <div class="grid">

            <div class="card">
                <h3>Assignments</h3>
                <p>
                    Submit PDF, Word and other supported
                    academic files.
                </p>
            </div>

            <div class="card">
                <h3>Answers</h3>
                <p>
                    Receive answers and downloadable
                    answered assignment documents.
                </p>
            </div>

            <div class="card">
                <h3>Academic Library</h3>
                <p>
                    Access notes, books, past papers
                    and other academic resources.
                </p>
            </div>

            <div class="card">
                <h3>Protected Files</h3>
                <p>
                    Files are stored privately and
                    delivered through temporary signed URLs.
                </p>
            </div>

        </div>
        """,
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

        name = (
            request.form.get("name", "")
            .strip()
        )

        email = (
            request.form.get("email", "")
            .strip()
            .lower()
        )

        password = request.form.get(
            "password",
            ""
        )

        if not name:
            flash(
                "Please enter your name.",
                "error",
            )
            return redirect(
                url_for("register")
            )

        if not email or "@" not in email:
            flash(
                "Please enter a valid email.",
                "error",
            )
            return redirect(
                url_for("register")
            )

        if len(password) < 6:
            flash(
                "Password must contain at least "
                "6 characters.",
                "error",
            )
            return redirect(
                url_for("register")
            )

        try:
            response = auth_signup(
                email,
                password,
            )

            if not response.ok:
                data = response.json()

                message = data.get(
                    "msg"
                ) or data.get(
                    "message"
                ) or "Registration failed."

                flash(
                    message,
                    "error",
                )

                return redirect(
                    url_for("register")
                )

            data = response.json()

            user = data.get("user") or {}

            user_id = user.get("id")

            if user_id:

                existing = get_profile(
                    user_id
                )

                if not existing:
                    supabase_insert(
                        "profiles",
                        {
                            "id": user_id,
                            "name": name,
                            "email": email,
                            "role": "student",
                        },
                    )

            flash(
                "Account created. Check your email if "
                "email confirmation is enabled.",
                "success",
            )

            return redirect(
                url_for("login")
            )

        except Exception as exc:

            logger.exception(
                "Registration error"
            )

            flash(
                f"Registration error: {exc}",
                "error",
            )

    return page(
        "Register",
        """
        <div class="card">

            <h2>Create Student Account</h2>

            <form method="post">

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Name</label>
                <input
                    name="name"
                    required
                    autocomplete="name"
                >

                <label>Email</label>
                <input
                    type="email"
                    name="email"
                    required
                    autocomplete="email"
                >

                <label>Password</label>
                <input
                    type="password"
                    name="password"
                    required
                    minlength="6"
                    autocomplete="new-password"
                >

                <button type="submit">
                    Create Account
                </button>

            </form>

        </div>
        """,
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

        email = (
            request.form.get("email", "")
            .strip()
            .lower()
        )

        password = request.form.get(
            "password",
            ""
        )

        try:
            response = auth_login(
                email,
                password,
            )

            if not response.ok:

                try:
                    data = response.json()

                    message = data.get(
                        "error_description"
                    ) or data.get(
                        "msg"
                    ) or "Invalid login details."

                except Exception:
                    message = (
                        "Invalid login details."
                    )

                flash(
                    message,
                    "error",
                )

                return redirect(
                    url_for("login")
                )

            data = response.json()

            auth_user = data.get(
                "user"
            ) or {}

            user_id = auth_user.get(
                "id"
            )

            if not user_id:
                raise RuntimeError(
                    "Supabase did not return a user ID."
                )

            profile = get_profile(
                user_id
            )

            role = get_user_role(
                user_id,
                email,
            )

            if not profile:

                supabase_insert(
                    "profiles",
                    {
                        "id": user_id,
                        "name": (
                            auth_user.get(
                                "user_metadata",
                                {}
                            ).get(
                                "name",
                                email.split("@")[0],
                            )
                        ),
                        "email": email,
                        "role": role,
                    },
                )

            session.clear()

            session["user"] = {
                "id": user_id,
                "email": email,
                "name": (
                    profile.get("name")
                    if profile
                    else email.split("@")[0]
                ),
            }

            session["role"] = role

            csrf_token()

            log_event(
                "User logged in",
                category="Authentication",
                user_id=user_id,
            )

            if role == "admin":
                return redirect(
                    url_for("admin_dashboard")
                )

            return redirect(
                url_for("dashboard")
            )

        except Exception as exc:

            logger.exception(
                "Login error"
            )

            flash(
                f"Login error: {exc}",
                "error",
            )

    return page(
        "Login",
        """
        <div class="card">

            <h2>Login</h2>

            <form method="post">

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Email</label>
                <input
                    type="email"
                    name="email"
                    required
                    autocomplete="email"
                >

                <label>Password</label>
                <input
                    type="password"
                    name="password"
                    required
                    autocomplete="current-password"
                >

                <button type="submit">
                    Login
                </button>

            </form>

            <p>
                <a href="{{ url_for('forgot_password') }}">
                    Forgot password?
                </a>
            </p>

        </div>
        """,
    )


# ============================================================
# PASSWORD RECOVERY
# ============================================================

@app.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():

    if request.method == "POST":

        email = (
            request.form.get("email", "")
            .strip()
            .lower()
        )

        if not email:
            flash(
                "Enter your email address.",
                "error",
            )
            return redirect(
                url_for("forgot_password")
            )

        try:

            response = auth_recovery(
                email
            )

            # Do not reveal whether an email
            # exists in the system.
            if response.ok:
                flash(
                    "If the account exists, "
                    "a password recovery email has "
                    "been sent.",
                    "success",
                )
            else:
                flash(
                    "If the account exists, "
                    "a password recovery email has "
                    "been sent.",
                    "success",
                )

        except Exception:
            flash(
                "If the account exists, "
                "a password recovery email has "
                "been sent.",
                "success",
            )

        return redirect(
            url_for("login")
        )

    return page(
        "Forgot Password",
        """
        <div class="card">

            <h2>Reset Password</h2>

            <form method="post">

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Email</label>

                <input
                    type="email"
                    name="email"
                    required
                >

                <button type="submit">
                    Send Recovery Email
                </button>

            </form>

        </div>
        """,
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    user_id = current_user_id()

    if user_id:
        log_event(
            "User logged out",
            category="Authentication",
            user_id=user_id,
        )

    session.clear()

    return redirect(
        url_for("index")
    )


# ============================================================
# THEME
# ============================================================

@app.route("/toggle-theme")
def toggle_theme():
    return redirect(
        request.referrer
        or url_for("index")
    )


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    if session.get("role") == "admin":
        return redirect(
            url_for("admin_dashboard")
        )

    uid = current_user_id()

    assignments = supabase_get(
        "assignments",
        {
            "student_id": f"eq.{uid}",
            "select": "*",
            "order": "created_at.desc",
        },
        limit=100,
    )

    questions = supabase_get(
        "questions",
        {
            "student_id": f"eq.{uid}",
            "select": "*",
            "order": "created_at.desc",
        },
        limit=50,
    )

    documents = supabase_get(
        "documents",
        {
            "is_active": "eq.true",
            "select": (
                "id,title,description,document_type,"
                "subject,course,class_level,file_name,"
                "is_public,view_count,download_count,"
                "created_at"
            ),
            "order": "created_at.desc",
        },
        limit=20,
    )

    return page(
        "Student Dashboard",
        """
        <div class="hero">
            <div class="brain">🧠</div>

            <h1>
                Welcome,
                {{ session.get('user', {}).get('name', 'Student') }}
            </h1>

            <p>
                Manage your assignments, questions and
                academic resources.
            </p>
        </div>

        <div class="grid">

            <div class="card">
                <h3>Assignments</h3>
                <div class="stat">
                    {{ assignments|length }}
                </div>
            </div>

            <div class="card">
                <h3>Questions</h3>
                <div class="stat">
                    {{ questions|length }}
                </div>
            </div>

            <div class="card">
                <h3>Resources</h3>
                <div class="stat">
                    {{ documents|length }}
                </div>
            </div>

        </div>

        <div class="card">
            <h2>Upload Assignment</h2>

            <form
                method="post"
                action="{{ url_for('student_upload_assignment') }}"
                enctype="multipart/form-data"
            >

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Title</label>
                <input name="title" required>

                <label>Description</label>
                <textarea name="description"></textarea>

                <label>Subject</label>
                <input name="subject">

                <label>Course</label>
                <input name="course">

                <label>Class Level</label>
                <input name="class_level">

                <label>Question</label>
                <textarea
                    name="question"
                    placeholder="Optional: type the question here"
                ></textarea>

                <label>PDF / Word Question File</label>

                <input
                    type="file"
                    name="file"
                    accept=".pdf,.doc,.docx,.txt,.rtf,.odt"
                >

                <button type="submit">
                    Submit Assignment
                </button>

            </form>
        </div>

        <div class="card">
            <h2>My Assignments</h2>

            {% if assignments %}

            <table>

            <tr>
                <th>Title</th>
                <th>Subject</th>
                <th>Status</th>
                <th>Created</th>
                <th>Action</th>
            </tr>

            {% for a in assignments %}

            <tr>

                <td>
                    {{ a.title }}
                </td>

                <td>
                    {{ a.subject or "-" }}
                </td>

                <td>
                    <span class="badge">
                        {{ a.status }}
                    </span>
                </td>

                <td>
                    {{ a.created_at }}
                </td>

                <td>

                    <div class="actions">

                        {% if a.file_path %}
                        <a
                            class="btn"
                            href="{{ url_for(
                                'assignment_file',
                                assignment_id=a.id
                            ) }}"
                        >
                            Question
                        </a>
                        {% endif %}

                        {% if a.answer_file_path %}
                        <a
                            class="btn success"
                            href="{{ url_for(
                                'assignment_answer_file',
                                assignment_id=a.id
                            ) }}"
                        >
                            Answer
                        </a>
                        {% endif %}

                    </div>

                </td>

            </tr>

            {% endfor %}

            </table>

            {% else %}

            <p class="muted">
                You have not submitted an assignment yet.
            </p>

            {% endif %}
        </div>

        <div class="card">

            <h2>Ask a Question</h2>

            <form
                method="post"
                action="{{ url_for('create_question') }}"
            >

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Subject</label>
                <input name="subject">

                <label>Course</label>
                <input name="course">

                <label>Class Level</label>
                <input name="class_level">

                <label>Question</label>
                <textarea
                    name="question"
                    required
                ></textarea>

                <button>
                    Submit Question
                </button>

            </form>

        </div>
        """,
    )


# ============================================================
# STUDENT ASSIGNMENT UPLOAD
# ============================================================

@app.route(
    "/student/upload-assignment",
    methods=["POST"]
)
@login_required
def student_upload_assignment():

    if session.get("role") == "admin":
        abort(403)

    uid = current_user_id()

    title = request.form.get(
        "title",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    subject = request.form.get(
        "subject",
        ""
    ).strip()

    course = request.form.get(
        "course",
        ""
    ).strip()

    class_level = request.form.get(
        "class_level",
        ""
    ).strip()

    question = request.form.get(
        "question",
        ""
    ).strip()

    if not title:
        flash(
            "Assignment title is required.",
            "error",
        )
        return redirect(
            url_for("dashboard")
        )

    try:

        file = get_upload(
            "file",
            required=False,
        )

        file_name = None
        file_path = None
        file_size = 0
        mime_type = (
            "application/pdf"
        )

        if file:

            file_name = safe_original_name(
                file.filename
            )

            file_path = storage_path(
                f"assignments/{uid}",
                file_name,
            )

            (
                file_path,
                file_size,
                mime_type,
            ) = upload_to_storage(
                ASSIGNMENT_BUCKET,
                file_path,
                file,
                file.mimetype,
            )

        profile = get_profile(uid)

        student_name = (
            profile.get("name")
            if profile
            else session.get(
                "user",
                {}
            ).get(
                "name",
                ""
            )
        )

        email = (
            session.get(
                "user",
                {}
            ).get(
                "email"
            )
        )

        row = {
            "student_id": uid,
            "title": title,
            "description": description
            or None,
            "subject": subject
            or None,
            "course": course
            or None,
            "class_level": class_level
            or None,
            "file_name": file_name,
            "file_path": file_path,
            "file_size": file_size,
            "mime_type": mime_type,
            "status": "submitted",
            "email": email,
            "question": question
            or None,
            "student_name": student_name,
        }

        result = supabase_insert(
            "assignments",
            row,
        )

        assignment_id = (
            result[0]["id"]
            if result
            else None
        )

        log_event(
            "Student submitted assignment",
            category="Assignments",
            details=(
                f"Assignment ID: {assignment_id}"
            ),
            user_id=uid,
        )

        flash(
            "Assignment submitted successfully.",
            "success",
        )

    except Exception as exc:

        logger.exception(
            "Assignment upload failed"
        )

        flash(
            f"Assignment upload failed: {exc}",
            "error",
        )

    return redirect(
        url_for("dashboard")
    )


# ============================================================
# ASSIGNMENT QUESTION FILE
# ============================================================

@app.route(
    "/assignment/<assignment_id>/file"
)
@login_required
def assignment_file(assignment_id):

    rows = supabase_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    uid = current_user_id()

    if (
        session.get("role") != "admin"
        and assignment.get("student_id") != uid
    ):
        abort(403)

    signed = create_signed_url(
        ASSIGNMENT_BUCKET,
        assignment.get("file_path"),
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# ANSWER FILE
# ============================================================

@app.route(
    "/assignment/<assignment_id>/answer"
)
@login_required
def assignment_answer_file(
    assignment_id
):

    rows = supabase_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    uid = current_user_id()

    if (
        session.get("role") != "admin"
        and assignment.get("student_id") != uid
    ):
        abort(403)

    path = assignment.get(
        "answer_file_path"
    )

    if not path:
        flash(
            "No answer file is available yet.",
            "warning",
        )

        return redirect(
            url_for("dashboard")
        )

    signed = create_signed_url(
        ANSWER_BUCKET,
        path,
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# QUESTIONS
# ============================================================

@app.route("/questions")
@login_required
def questions():

    uid = current_user_id()

    if session.get("role") == "admin":

        rows = supabase_get(
            "questions",
            {
                "select": "*",
                "order": "created_at.desc",
            },
            limit=100,
        )

    else:

        rows = supabase_get(
            "questions",
            {
                "student_id": f"eq.{uid}",
                "select": "*",
                "order": "created_at.desc",
            },
            limit=100,
        )

    return page(
        "Questions",
        """
        <div class="card">

            <h2>
                {% if is_admin %}
                    Student Questions
                {% else %}
                    My Questions
                {% endif %}
            </h2>

            {% if rows %}

            {% for q in rows %}

            <div class="card">

                <h3>
                    {{ q.subject or "Academic Question" }}
                </h3>

                <p>
                    <b>Question:</b>
                    {{ q.question }}
                </p>

                <p>
                    <b>Status:</b>
                    <span class="badge">
                        {{ q.status or "pending" }}
                    </span>
                </p>

                {% if q.answer %}

                <p>
                    <b>Answer:</b><br>
                    {{ q.answer }}
                </p>

                <p class="muted">
                    Answered by:
                    {{ q.answer_by or "Admin" }}
                </p>

                {% else %}

                <p class="muted">
                    This question has not been answered yet.
                </p>

                {% endif %}

                {% if is_admin %}

                <form
                    method="post"
                    action="{{ url_for(
                        'answer_question',
                        question_id=q.id
                    ) }}"
                >

                    <input
                        type="hidden"
                        name="_csrf"
                        value="{{ csrf_token }}"
                    >

                    <label>Answer</label>

                    <textarea
                        name="answer"
                        required
                    >{{ q.answer or "" }}</textarea>

                    <button>
                        Save Answer
                    </button>

                </form>

                {% endif %}

            </div>

            {% endfor %}

            {% else %}

            <p class="muted">
                No questions found.
            </p>

            {% endif %}

        </div>
        """,
    )


@app.route(
    "/question/create",
    methods=["POST"]
)
@login_required
def create_question():

    if session.get("role") == "admin":
        abort(403)

    uid = current_user_id()

    question = request.form.get(
        "question",
        ""
    ).strip()

    if not question:
        flash(
            "Question cannot be empty.",
            "error",
        )
        return redirect(
            url_for("questions")
        )

    profile = get_profile(uid)

    student_name = (
        profile.get("name")
        if profile
        else ""
    )

    try:

        supabase_insert(
            "questions",
            {
                "student_id": uid,
                "student_name": student_name,
                "question": question,
                "answer": "",
                "answer_by": "",
                "subject": (
                    request.form.get(
                        "subject",
                        ""
                    ).strip()
                    or None
                ),
                "course": (
                    request.form.get(
                        "course",
                        ""
                    ).strip()
                    or None
                ),
                "class_level": (
                    request.form.get(
                        "class_level",
                        ""
                    ).strip()
                    or None
                ),
                "status": "pending",
            },
        )

        log_event(
            "Student created academic question",
            category="Questions",
            user_id=uid,
        )

        flash(
            "Question submitted.",
            "success",
        )

    except Exception as exc:

        logger.exception(
            "Question creation failed"
        )

        flash(
            f"Could not submit question: {exc}",
            "error",
        )

    return redirect(
        url_for("questions")
    )


# ============================================================
# ADMIN ANSWER QUESTION
# ============================================================

@app.route(
    "/admin/question/<question_id>/answer",
    methods=["POST"]
)
@admin_required
def answer_question(question_id):

    answer = request.form.get(
        "answer",
        ""
    ).strip()

    if not answer:
        flash(
            "Answer cannot be empty.",
            "error",
        )
        return redirect(
            url_for("questions")
        )

    uid = current_user_id()

    try:

        supabase_update(
            "questions",
            {
                "id": f"eq.{question_id}"
            },
            {
                "answer": answer,
                "answer_by": (
                    current_email()
                    or "Admin"
                ),
                "answered_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "answered_by": uid,
                "status": "answered",
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            },
        )

        log_event(
            "Admin answered academic question",
            category="Questions",
            user_id=uid,
            details=(
                f"Question ID: {question_id}"
            ),
        )

        flash(
            "Answer saved.",
            "success",
        )

    except Exception as exc:

        logger.exception(
            "Answer question failed"
        )

        flash(
            f"Could not save answer: {exc}",
            "error",
        )

    return redirect(
        url_for("questions")
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    assignments = supabase_get(
        "assignments",
        {
            "select": "*",
            "order": "created_at.desc",
        },
        limit=200,
    )

    questions_rows = supabase_get(
        "questions",
        {
            "select": "*",
            "order": "created_at.desc",
        },
        limit=100,
    )

    documents_rows = supabase_get(
        "documents",
        {
            "select": "*",
            "order": "created_at.desc",
        },
        limit=100,
    )

    resources_rows = supabase_get(
        "resources",
        {
            "select": "*",
            "order": "created_at.desc",
        },
        limit=100,
    )

    profiles = supabase_get(
        "profiles",
        {
            "select": "id,name,email,role,created_at",
            "order": "created_at.desc",
        },
        limit=200,
    )

    return page(
        "Admin Dashboard",
        """
        <div class="hero">

            <div class="brain">🧠</div>

            <h1>KOJA AFRICA Admin</h1>

            <p>
                Manage assignments, answers, questions,
                documents and resources.
            </p>

        </div>

        <div class="grid">

            <div class="card">
                <h3>Students</h3>
                <div class="stat">
                    {{ profiles|length }}
                </div>
            </div>

            <div class="card">
                <h3>Assignments</h3>
                <div class="stat">
                    {{ assignments|length }}
                </div>
            </div>

            <div class="card">
                <h3>Questions</h3>
                <div class="stat">
                    {{ questions_rows|length }}
                </div>
            </div>

            <div class="card">
                <h3>Documents</h3>
                <div class="stat">
                    {{ documents_rows|length }}
                </div>
            </div>

        </div>

        <div class="grid">

            <div class="card">

                <h3>Admin Tools</h3>

                <div class="actions">

                    <a
                        class="btn"
                        href="{{ url_for(
                            'admin_assignments'
                        ) }}"
                    >
                        Assignments
                    </a>

                    <a
                        class="btn"
                        href="{{ url_for(
                            'admin_documents'
                        ) }}"
                    >
                        Documents
                    </a>

                    <a
                        class="btn"
                        href="{{ url_for(
                            'admin_resources'
                        ) }}"
                    >
                        Resources
                    </a>

                    <a
                        class="btn"
                        href="{{ url_for(
                            'admin_products'
                        ) }}"
                    >
                        Products
                    </a>

                    <a
                        class="btn"
                        href="{{ url_for(
                            'admin_logs'
                        ) }}"
                    >
                        Logs
                    </a>

                </div>

            </div>

        </div>

        <div class="card">

            <h2>Recent Assignments</h2>

            {% if assignments %}

            <table>

            <tr>
                <th>Student</th>
                <th>Title</th>
                <th>Status</th>
                <th>Action</th>
            </tr>

            {% for a in assignments[:30] %}

            <tr>

                <td>
                    {{ a.student_name or a.email or "-" }}
                </td>

                <td>
                    {{ a.title }}
                </td>

                <td>
                    <span class="badge">
                        {{ a.status }}
                    </span>
                </td>

                <td>
                    <a
                        class="btn"
                        href="{{ url_for(
                            'admin_assignment',
                            assignment_id=a.id
                        ) }}"
                    >
                        Open
                    </a>
                </td>

            </tr>

            {% endfor %}

            </table>

            {% else %}

            <p>No assignments.</p>

            {% endif %}

        </div>
        """,
    )


# ============================================================
# ADMIN ASSIGNMENTS
# ============================================================

@app.route("/admin/assignments")
@admin_required
def admin_assignments():

    assignments = supabase_get(
        "assignments",
        {
            "select": "*",
            "order": "created_at.desc",
        },
        limit=300,
    )

    profiles = supabase_get(
        "profiles",
        {
            "select": "id,name,email,role",
            "order": "name.asc",
        },
        limit=300,
    )

    return page(
        "Admin Assignments",
        """
        <div class="card">

            <h2>Send Assignment to Student</h2>

            <form
                method="post"
                action="{{ url_for(
                    'admin_create_assignment'
                ) }}"
                enctype="multipart/form-data"
            >

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Student</label>

                <select
                    name="student_id"
                    required
                >

                    <option value="">
                        Select student
                    </option>

                    {% for p in profiles %}

                    {% if p.role != "admin" %}

                    <option value="{{ p.id }}">
                        {{ p.name or p.email }}
                        — {{ p.email }}
                    </option>

                    {% endif %}

                    {% endfor %}

                </select>

                <label>Title</label>
                <input name="title" required>

                <label>Description</label>
                <textarea name="description"></textarea>

                <label>Subject</label>
                <input name="subject">

                <label>Course</label>
                <input name="course">

                <label>Class Level</label>
                <input name="class_level">

                <label>Question</label>
                <textarea name="question"></textarea>

                <label>PDF / Word Question</label>
                <input
                    type="file"
                    name="file"
                    accept=".pdf,.doc,.docx,.txt,.rtf,.odt"
                >

                <button>
                    Send Assignment
                </button>

            </form>

        </div>

        <div class="card">

            <h2>All Assignments</h2>

            <table>

            <tr>
                <th>Student</th>
                <th>Title</th>
                <th>Status</th>
                <th>Created</th>
                <th>Open</th>
            </tr>

            {% for a in assignments %}

            <tr>

                <td>
                    {{ a.student_name or a.email or "-" }}
                </td>

                <td>
                    {{ a.title }}
                </td>

                <td>
                    <span class="badge">
                        {{ a.status }}
                    </span>
                </td>

                <td>
                    {{ a.created_at }}
                </td>

                <td>
                    <a
                        class="btn"
                        href="{{ url_for(
                            'admin_assignment',
                            assignment_id=a.id
                        ) }}"
                    >
                        Open
                    </a>
                </td>

            </tr>

            {% endfor %}

            </table>

        </div>
        """,
    )


# ============================================================
# ADMIN CREATE ASSIGNMENT
# ============================================================

@app.route(
    "/admin/assignments/create",
    methods=["POST"]
)
@admin_required
def admin_create_assignment():

    student_id = request.form.get(
        "student_id",
        ""
    ).strip()

    title = request.form.get(
        "title",
        ""
    ).strip()

    if not student_id or not title:
        flash(
            "Student and title are required.",
            "error",
        )
        return redirect(
            url_for("admin_assignments")
        )

    try:

        profiles = supabase_get(
            "profiles",
            {
                "id": f"eq.{student_id}",
                "select": "id,name,email,role",
            },
            limit=1,
        )

        if not profiles:
            flash(
                "Student account was not found.",
                "error",
            )
            return redirect(
                url_for("admin_assignments")
            )

        student = profiles[0]

        file = get_upload(
            "file",
            required=False,
        )

        file_name = None
        file_path = None
        file_size = 0
        mime_type = (
            "application/pdf"
        )

        if file:

            file_name = safe_original_name(
                file.filename
            )

            file_path = storage_path(
                f"assignments/{student_id}",
                file_name,
            )

            (
                file_path,
                file_size,
                mime_type,
            ) = upload_to_storage(
                ASSIGNMENT_BUCKET,
                file_path,
                file,
                file.mimetype,
            )

        result = supabase_insert(
            "assignments",
            {
                "student_id": student_id,
                "title": title,
                "description": (
                    request.form.get(
                        "description",
                        ""
                    ).strip()
                    or None
                ),
                "subject": (
                    request.form.get(
                        "subject",
                        ""
                    ).strip()
                    or None
                ),
                "course": (
                    request.form.get(
                        "course",
                        ""
                    ).strip()
                    or None
                ),
                "class_level": (
                    request.form.get(
                        "class_level",
                        ""
                    ).strip()
                    or None
                ),
                "file_name": file_name,
                "file_path": file_path,
                "file_size": file_size,
                "mime_type": mime_type,
                "status": "assigned",
                "email": student.get("email"),
                "question": (
                    request.form.get(
                        "question",
                        ""
                    ).strip()
                    or None
                ),
                "student_name": student.get(
                    "name",
                    ""
                ),
            },
        )

        assignment_id = (
            result[0]["id"]
            if result
            else ""
        )

        log_event(
            "Admin sent assignment",
            category="Assignments",
            user_id=current_user_id(),
            details=(
                f"Assignment {assignment_id} "
                f"sent to {student_id}"
            ),
        )

        flash(
            "Assignment sent successfully.",
            "success",
        )

    except Exception as exc:

        logger.exception(
            "Admin assignment creation failed"
        )

        flash(
            f"Could not send assignment: {exc}",
            "error",
        )

    return redirect(
        url_for("admin_assignments")
    )


# ============================================================
# ADMIN ASSIGNMENT DETAIL
# ============================================================

@app.route(
    "/admin/assignment/<assignment_id>"
)
@admin_required
def admin_assignment(assignment_id):

    rows = supabase_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    responses = supabase_get(
        "assignment_responses",
        {
            "assignment_id":
                f"eq.{assignment_id}",
            "select": "*",
            "order": "created_at.asc",
        },
        limit=100,
    )

    answers = supabase_get(
        "assignment_answers",
        {
            "assignment_id":
                f"eq.{assignment_id}",
            "select": "*",
            "order": "created_at.desc",
        },
        limit=20,
    )

    return page(
        "Assignment",
        """
        <div class="card">

            <h2>
                {{ assignment.title }}
            </h2>

            <p>
                <b>Student:</b>
                {{ assignment.student_name or assignment.email }}
            </p>

            <p>
                <b>Subject:</b>
                {{ assignment.subject or "-" }}
            </p>

            <p>
                <b>Status:</b>
                <span class="badge">
                    {{ assignment.status }}
                </span>
            </p>

            {% if assignment.question %}

            <h3>Question</h3>

            <div class="card">
                {{ assignment.question }}
            </div>

            {% endif %}

            <div class="actions">

                {% if assignment.file_path %}

                <a
                    class="btn"
                    href="{{ url_for(
                        'admin_assignment_file',
                        assignment_id=assignment.id
                    ) }}"
                >
                    Open Question File
                </a>

                {% endif %}

                {% if assignment.answer_file_path %}

                <a
                    class="btn success"
                    href="{{ url_for(
                        'admin_assignment_answer_file',
                        assignment_id=assignment.id
                    ) }}"
                >
                    Open Answer
                </a>

                {% endif %}

            </div>

        </div>

        <div class="card">

            <h2>Answer Assignment</h2>

            <form
                method="post"
                action="{{ url_for(
                    'admin_answer_assignment',
                    assignment_id=assignment.id
                ) }}"
                enctype="multipart/form-data"
            >

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Answer Text</label>

                <textarea
                    name="answer_text"
                    placeholder="Write the academic answer here"
                ></textarea>

                <label>
                    Upload PDF / Word Answer
                </label>

                <input
                    type="file"
                    name="answer_file"
                    accept=".pdf,.doc,.docx,.txt,.rtf,.odt"
                >

                <label>Status</label>

                <select name="status">

                    <option value="answered">
                        Answered
                    </option>

                    <option value="completed">
                        Completed
                    </option>

                    <option value="reviewing">
                        Reviewing
                    </option>

                    <option value="rejected">
                        Rejected
                    </option>

                </select>

                <label>Admin Comment</label>

                <textarea
                    name="admin_comment"
                >{{ assignment.admin_comment or "" }}</textarea>

                <button class="success">
                    Save Answer
                </button>

            </form>

        </div>

        <div class="card">

            <h2>Response to Student</h2>

            <form
                method="post"
                action="{{ url_for(
                    'admin_add_response',
                    assignment_id=assignment.id
                ) }}"
                enctype="multipart/form-data"
            >

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Response</label>

                <textarea
                    name="response_text"
                ></textarea>

                <label>Attachment</label>

                <input
                    type="file"
                    name="file"
                    accept=".pdf,.doc,.docx,.txt,.rtf,.odt"
                >

                <button>
                    Send Response
                </button>

            </form>

        </div>

        <div class="card">

            <h2>Previous Answers</h2>

            {% for answer in answers %}

            <div class="card">

                <p>
                    <b>Status:</b>
                    {{ answer.status }}
                </p>

                {% if answer.answer_text %}

                <p>
                    {{ answer.answer_text }}
                </p>

                {% endif %}

                {% if answer.answer_file_path %}

                <a
                    class="btn"
                    href="{{ url_for(
                        'assignment_answer_record_file',
                        answer_id=answer.id
                    ) }}"
                >
                    Open Uploaded Answer
                </a>

                {% endif %}

            </div>

            {% else %}

            <p class="muted">
                No answer record yet.
            </p>

            {% endfor %}

        </div>

        <div class="card">

            <h2>Responses</h2>

            {% for r in responses %}

            <div class="card">

                <p>
                    {{ r.response_text or "" }}
                </p>

                {% if r.file_path %}

                <a
                    class="btn"
                    href="{{ url_for(
                        'response_file',
                        response_id=r.id
                    ) }}"
                >
                    Open Attachment
                </a>

                {% endif %}

                <p class="muted small">
                    {{ r.created_at }}
                </p>

            </div>

            {% else %}

            <p class="muted">
                No responses yet.
            </p>

            {% endfor %}

        </div>
        """,
    )


# ============================================================
# ADMIN QUESTION FILE
# ============================================================

@app.route(
    "/admin/assignment/<assignment_id>/file"
)
@admin_required
def admin_assignment_file(assignment_id):

    rows = supabase_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "file_path",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    signed = create_signed_url(
        ASSIGNMENT_BUCKET,
        rows[0].get("file_path"),
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# ADMIN ANSWER FILE
# ============================================================

@app.route(
    "/admin/assignment/<assignment_id>/answer"
)
@admin_required
def admin_assignment_answer_file(
    assignment_id
):

    rows = supabase_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "answer_file_path",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    signed = create_signed_url(
        ANSWER_BUCKET,
        rows[0].get(
            "answer_file_path"
        ),
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# ADMIN ANSWER ASSIGNMENT
# ============================================================

@app.route(
    "/admin/assignment/<assignment_id>/answer",
    methods=["POST"]
)
@admin_required
def admin_answer_assignment(
    assignment_id
):

    rows = supabase_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    uid = current_user_id()

    answer_text = request.form.get(
        "answer_text",
        ""
    ).strip()

    status = request.form.get(
        "status",
        "answered"
    ).strip()

    admin_comment = request.form.get(
        "admin_comment",
        ""
    ).strip()

    try:

        uploaded_file = get_upload(
            "answer_file",
            required=False,
        )

        answer_file_name = (
            assignment.get(
                "answer_file_name"
            )
        )

        answer_file_path = (
            assignment.get(
                "answer_file_path"
            )
        )

        if uploaded_file:

            answer_file_name = safe_original_name(
                uploaded_file.filename
            )

            answer_file_path = storage_path(
                f"answers/{assignment_id}",
                answer_file_name,
            )

            (
                answer_file_path,
                answer_size,
                answer_mime,
            ) = upload_to_storage(
                ANSWER_BUCKET,
                answer_file_path,
                uploaded_file,
                uploaded_file.mimetype,
            )

        # If only answer text exists, generate a PDF.
        if (
            answer_text
            and not answer_file_path
        ):

            pdf = build_answer_pdf(
                title=assignment.get(
                    "title",
                    "Assignment"
                ),
                student_name=assignment.get(
                    "student_name",
                    ""
                ),
                subject=assignment.get(
                    "subject",
                    ""
                ),
                question=(
                    assignment.get(
                        "question"
                    )
                    or assignment.get(
                        "description"
                    )
                    or ""
                ),
                answer=answer_text,
            )

            generated_name = (
                "answered_assignment.pdf"
            )

            answer_file_name = (
                generated_name
            )

            answer_file_path = (
                f"answers/"
                f"{assignment_id}/"
                f"{uuid.uuid4()}.pdf"
            )

            class PDFWrapper:
                def __init__(self, data):
                    self.data = data
                    self.filename = generated_name
                    self.mimetype = "application/pdf"
                    self.stream = io.BytesIO(data)

                def read(self, *args):
                    return self.stream.read(*args)

            wrapper = PDFWrapper(
                pdf.getvalue()
            )

            (
                answer_file_path,
                answer_size,
                answer_mime,
            ) = upload_to_storage(
                ANSWER_BUCKET,
                answer_file_path,
                wrapper,
                "application/pdf",
            )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        # Main assignment answer columns.
        supabase_update(
            "assignments",
            {
                "id": f"eq.{assignment_id}"
            },
            {
                "status": status,
                "admin_comment":
                    admin_comment or None,
                "reviewed_by": uid,
                "answer_file_name":
                    answer_file_name,
                "answer_file_path":
                    answer_file_path,
                "answered_at":
                    now,
                "answered_by":
                    uid,
                "updated_at":
                    now,
            },
        )

        # Separate assignment_answers record.
        supabase_insert(
            "assignment_answers",
            {
                "assignment_id":
                    assignment_id,
                "student_id":
                    assignment.get(
                        "student_id"
                    ),
                "answer_text":
                    answer_text or None,
                "answer_file_name":
                    answer_file_name,
                "answer_file_path":
                    answer_file_path,
                "generated_by":
                    (
                        current_email()
                        or "admin"
                    ),
                "status":
                    status,
            },
        )

        log_event(
            "Admin answered assignment",
            category="Assignments",
            user_id=uid,
            details=(
                f"Assignment ID: "
                f"{assignment_id}"
            ),
        )

        flash(
            "Assignment answer saved successfully.",
            "success",
        )

    except Exception as exc:

        logger.exception(
            "Answer assignment failed"
        )

        flash(
            f"Could not save answer: {exc}",
            "error",
        )

    return redirect(
        url_for(
            "admin_assignment",
            assignment_id=assignment_id,
        )
    )


# ============================================================
# ANSWER RECORD FILE
# ============================================================

@app.route(
    "/admin/answer-record/<answer_id>/file"
)
@admin_required
def assignment_answer_record_file(
    answer_id
):

    rows = supabase_get(
        "assignment_answers",
        {
            "id": f"eq.{answer_id}",
            "select": "answer_file_path",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    signed = create_signed_url(
        ANSWER_BUCKET,
        rows[0].get(
            "answer_file_path"
        ),
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# ADMIN RESPONSE
# ============================================================

@app.route(
    "/admin/assignment/<assignment_id>/response",
    methods=["POST"]
)
@admin_required
def admin_add_response(
    assignment_id
):

    text = request.form.get(
        "response_text",
        ""
    ).strip()

    try:

        file = get_upload(
            "file",
            required=False,
        )

        file_name = None
        file_path = None
        file_size = 0
        mime_type = None

        if file:

            file_name = safe_original_name(
                file.filename
            )

            file_path = storage_path(
                f"responses/{assignment_id}",
                file_name,
            )

            (
                file_path,
                file_size,
                mime_type,
            ) = upload_to_storage(
                ANSWER_BUCKET,
                file_path,
                file,
                file.mimetype,
            )

        if not text and not file_path:
            flash(
                "Enter a response or attach a file.",
                "error",
            )

            return redirect(
                url_for(
                    "admin_assignment",
                    assignment_id=assignment_id,
                )
            )

        supabase_insert(
            "assignment_responses",
            {
                "assignment_id":
                    assignment_id,
                "admin_id":
                    current_user_id(),
                "response_text":
                    text or None,
                "file_name":
                    file_name,
                "file_path":
                    file_path,
                "file_size":
                    file_size,
                "mime_type":
                    mime_type,
            },
        )

        log_event(
            "Admin sent assignment response",
            category="Assignments",
            user_id=current_user_id(),
            details=(
                f"Assignment ID: {assignment_id}"
            ),
        )

        flash(
            "Response sent.",
            "success",
        )

    except Exception as exc:

        logger.exception(
            "Response failed"
        )

        flash(
            f"Could not send response: {exc}",
            "error",
        )

    return redirect(
        url_for(
            "admin_assignment",
            assignment_id=assignment_id,
        )
    )


# ============================================================
# RESPONSE FILE
# ============================================================

@app.route(
    "/response/<response_id>/file"
)
@login_required
def response_file(response_id):

    rows = supabase_get(
        "assignment_responses",
        {
            "id": f"eq.{response_id}",
            "select": "*",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    response = rows[0]

    if session.get("role") != "admin":

        assignment_id = response.get(
            "assignment_id"
        )

        assignments = supabase_get(
            "assignments",
            {
                "id":
                    f"eq.{assignment_id}",
                "select":
                    "student_id",
            },
            limit=1,
        )

        if not assignments:
            abort(403)

        if (
            assignments[0].get(
                "student_id"
            )
            != current_user_id()
        ):
            abort(403)

    signed = create_signed_url(
        ANSWER_BUCKET,
        response.get("file_path"),
    )

    if not signed:
        abort(404)

    return redirect(signed)


# ============================================================
# STUDENT DOCUMENT LIBRARY
# ============================================================

@app.route("/documents")
@login_required
def documents():

    search = request.args.get(
        "q",
        ""
    ).strip()

    params = {
        "is_active": "eq.true",
        "select": "*",
        "order": "created_at.desc",
    }

    if search:
        safe_search = search.replace(
            ",",
            " ",
        )

        params["or"] = (
            f"(title.ilike.*{safe_search}*,"
            f"description.ilike.*{safe_search}*,"
            f"subject.ilike.*{safe_search}*,"
            f"course.ilike.*{safe_search}*)"
        )

    rows = supabase_get(
        "documents",
        params,
        limit=200,
    )

    # Student sees public documents.
    if session.get("role") != "admin":

        rows = [
            row
            for row in rows
            if row.get("is_public") is True
        ]

    return page(
        "Document Library",
        """
        <div class="card">

            <h2>Academic Library</h2>

            <form method="get">

                <input
                    name="q"
                    value="{{ search }}"
                    placeholder="Search documents..."
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

            <p class="muted">
                {{ d.document_type }}
                {% if d.subject %}
                    · {{ d.subject }}
                {% endif %}
            </p>

            <p>
                {{ d.description or "" }}
            </p>

            <p class="small">
                Views: {{ d.view_count or 0 }}
                · Downloads:
                {{ d.download_count or 0 }}
            </p>

            <a
                class="btn"
                href="{{ url_for(
                    'view_document',
                    document_id=d.id
                ) }}"
            >
                View
            </a>

            <a
                class="btn secondary"
                href="{{ url_for(
                    'download_document',
                    document_id=d.id
                ) }}"
            >
                Download
            </a>

        </div>

        {% else %}

        <div class="card">
            No documents found.
        </div>

        {% endfor %}

        </div>
        """,
    )


# ============================================================
# VIEW DOCUMENT
# ============================================================

@app.route(
    "/document/<document_id>/view"
)
@login_required
def view_document(document_id):

    rows = supabase_get(
        "documents",
        {
            "id": f"eq.{document_id}",
            "select": "*",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    doc = rows[0]

    if not doc.get("is_active"):
        abort(404)

    if (
        session.get("role") != "admin"
        and not doc.get("is_public")
    ):
        abort(403)

    signed = create_signed_url(
        DOCUMENT_BUCKET,
        doc.get("file_path"),
    )

    if not signed:
        abort(404)

    try:
        supabase_update(
            "documents",
            {
                "id": f"eq.{document_id}"
            },
            {
                "view_count":
                    int(
                        doc.get(
                            "view_count"
                        )
                        or 0
                    ) + 1,
            },
            select="id",
        )
    except Exception:
        pass

    record_document_action(
        document_id,
        "view",
        current_user_id(),
    )

    return redirect(signed)


# ============================================================
# DOWNLOAD DOCUMENT
# ============================================================

@app.route(
    "/document/<document_id>/download"
)
@login_required
def download_document(document_id):

    rows = supabase_get(
        "documents",
        {
            "id": f"eq.{document_id}",
            "select": "*",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    doc = rows[0]

    if not doc.get("is_active"):
        abort(404)

    if (
        session.get("role") != "admin"
        and not doc.get("is_public")
    ):
        abort(403)

    signed = create_signed_url(
        DOCUMENT_BUCKET,
        doc.get("file_path"),
    )

    if not signed:
        abort(404)

    try:

        supabase_update(
            "documents",
            {
                "id": f"eq.{document_id}"
            },
            {
                "download_count":
                    int(
                        doc.get(
                            "download_count"
                        )
                        or 0
                    ) + 1,
            },
            select="id",
        )

        supabase_insert(
            "download_history",
            {
                "user_id":
                    current_user_id(),
                "document_id":
                    document_id,
                "file_name":
                    doc.get("file_name"),
            },
        )

    except Exception as exc:

        logger.warning(
            "Download history failed: %s",
            exc,
        )

    record_document_action(
        document_id,
        "download",
        current_user_id(),
    )

    log_event(
        "Document downloaded",
        category="Documents",
        user_id=current_user_id(),
        details=(
            f"Document ID: {document_id}"
        ),
    )

    return redirect(signed)


# ============================================================
# ADMIN DOCUMENT MANAGEMENT
# ============================================================

@app.route("/admin/documents")
@admin_required
def admin_documents():

    rows = supabase_get(
        "documents",
        {
            "select": "*",
            "order": "created_at.desc",
        },
        limit=300,
    )

    return page(
        "Admin Documents",
        """
        <div class="card">

            <h2>Upload Academic Document</h2>

            <form
                method="post"
                action="{{ url_for(
                    'admin_upload_document'
                ) }}"
                enctype="multipart/form-data"
            >

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Title</label>
                <input name="title" required>

                <label>Description</label>
                <textarea name="description"></textarea>

                <label>Document Type</label>

                <select name="document_type">

                    <option value="academic">
                        Academic
                    </option>

                    <option value="past_paper">
                        Past Paper
                    </option>

                    <option value="notes">
                        Notes
                    </option>

                    <option value="book">
                        Book
                    </option>

                    <option value="other">
                        Other
                    </option>

                </select>

                <label>Subject</label>
                <input name="subject">

                <label>Course</label>
                <input name="course">

                <label>Class Level</label>
                <input name="class_level">

                <label>File</label>

                <input
                    type="file"
                    name="file"
                    required
                    accept=".pdf,.doc,.docx,.txt,.rtf,.odt"
                >

                <label>
                    <input
                        type="checkbox"
                        name="is_public"
                        value="1"
                    >
                    Public/student-accessible
                </label>

                <br><br>

                <button>
                    Upload Document
                </button>

            </form>

        </div>

        <div class="card">

            <h2>Documents</h2>

            <table>

            <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Public</th>
                <th>Active</th>
                <th>Views</th>
                <th>Downloads</th>
                <th>Action</th>
            </tr>

            {% for d in rows %}

            <tr>

                <td>
                    {{ d.title }}
                </td>

                <td>
                    {{ d.document_type }}
                </td>

                <td>
                    {{ "Yes" if d.is_public else "No" }}
                </td>

                <td>
                    {{ "Yes" if d.is_active else "No" }}
                </td>

                <td>
                    {{ d.view_count or 0 }}
                </td>

                <td>
                    {{ d.download_count or 0 }}
                </td>

                <td>

                    <div class="actions">

                        <a
                            class="btn"
                            href="{{ url_for(
                                'view_document',
                                document_id=d.id
                            ) }}"
                        >
                            View
                        </a>

                        <form
                            method="post"
                            action="{{ url_for(
                                'toggle_document',
                                document_id=d.id
                            ) }}"
                        >

                            <input
                                type="hidden"
                                name="_csrf"
                                value="{{ csrf_token }}"
                            >

                            <button
                                class="secondary"
                            >
                                Toggle
                            </button>

                        </form>

                    </div>

                </td>

            </tr>

            {% endfor %}

            </table>

        </div>
        """,
    )


# ============================================================
# ADMIN UPLOAD DOCUMENT
# ============================================================

@app.route(
    "/admin/documents/upload",
    methods=["POST"]
)
@admin_required
def admin_upload_document():

    title = request.form.get(
        "title",
        ""
    ).strip()

    if not title:
        flash(
            "Title is required.",
            "error",
        )
        return redirect(
            url_for("admin_documents")
        )

    try:

        file = get_upload(
            "file",
            required=True,
        )

        file_name = safe_original_name(
            file.filename
        )

        path = storage_path(
            "documents",
            file_name,
        )

        (
            path,
            size,
            mime,
        ) = upload_to_storage(
            DOCUMENT_BUCKET,
            path,
            file,
            file.mimetype,
        )

        supabase_insert(
            "documents",
            {
                "title": title,
                "description": (
                    request.form.get(
                        "description",
                        ""
                    ).strip()
                    or None
                ),
                "document_type": (
                    request.form.get(
                        "document_type",
                        "academic"
                    ).strip()
                    or "academic"
                ),
                "subject": (
                    request.form.get(
                        "subject",
                        ""
                    ).strip()
                    or None
                ),
                "course": (
                    request.form.get(
                        "course",
                        ""
                    ).strip()
                    or None
                ),
                "class_level": (
                    request.form.get(
                        "class_level",
                        ""
                    ).strip()
                    or None
                ),
                "file_name": file_name,
                "file_path": path,
                "file_size": size,
                "mime_type": mime,
                "uploaded_by":
                    current_user_id(),
                "is_public":
                    bool(
                        request.form.get(
                            "is_public"
                        )
                    ),
                "is_active": True,
            },
        )

        log_event(
            "Admin uploaded document",
            category="Documents",
            user_id=current_user_id(),
            details=file_name,
        )

        flash(
            "Document uploaded.",
            "success",
        )

    except Exception as exc:

        logger.exception(
            "Document upload failed"
        )

        flash(
            f"Document upload failed: {exc}",
            "error",
        )

    return redirect(
        url_for("admin_documents")
    )


# ============================================================
# TOGGLE DOCUMENT
# ============================================================

@app.route(
    "/admin/document/<document_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_document(document_id):

    rows = supabase_get(
        "documents",
        {
            "id": f"eq.{document_id}",
            "select": "is_active",
        },
        limit=1,
    )

    if not rows:
        abort(404)

    active = bool(
        rows[0].get(
            "is_active"
        )
    )

    supabase_update(
        "documents",
        {
            "id": f"eq.{document_id}"
        },
        {
            "is_active": not active,
            "updated_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),
        },
        select="id",
    )

    log_event(
        "Document active state changed",
        category="Documents",
        user_id=current_user_id(),
        details=(
            f"{document_id}: "
            f"{not active}"
        ),
    )

    flash(
        "Document status updated.",
        "success",
    )

    return redirect(
        url_for("admin_documents")
    )


# ============================================================
# RESOURCES
# ============================================================

@app.route("/admin/resources")
@admin_required
def admin_resources():

    rows = supabase_get(
        "resources",
        {
            "select": "*",
            "order": "created_at.desc",
        },
        limit=300,
    )

    return page(
        "Admin Resources",
        """
        <div class="card">

            <h2>Upload Resource</h2>

            <form
                method="post"
                action="{{ url_for(
                    'admin_upload_resource'
                ) }}"
                enctype="multipart/form-data"
            >

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Title</label>
                <input name="title" required>

                <label>Description</label>
                <textarea name="description"></textarea>

                <label>Subject</label>
                <input name="subject">

                <label>Level</label>
                <input name="level">

                <label>Price</label>
                <input
                    type="number"
                    step="0.01"
                    min="0"
                    name="price"
                    value="0"
                >

                <label>
                    <input
                        type="checkbox"
                        name="is_paid"
                        value="1"
                    >
                    Paid resource
                </label>

                <br><br>

                <label>PDF / Word File</label>

                <input
                    type="file"
                    name="file"
                    required
                    accept=".pdf,.doc,.docx,.txt,.rtf,.odt"
                >

                <button>
                    Upload Resource
                </button>

            </form>

        </div>

        <div class="card">

            <h2>Resources</h2>

            <table>

            <tr>
                <th>Title</th>
                <th>Level</th>
                <th>Price</th>
                <th>Paid</th>
                <th>Active</th>
            </tr>

            {% for r in rows %}

            <tr>

                <td>
                    {{ r.title }}
                </td>

                <td>
                    {{ r.level or "-" }}
                </td>

                <td>
                    {{ r.price }}
                </td>

                <td>
                    {{ "Yes" if r.is_paid else "No" }}
                </td>

                <td>
                    {{ "Yes" if r.is_active else "No" }}
                </td>

            </tr>

            {% endfor %}

            </table>

        </div>
        """,
    )


# ============================================================
# RESOURCE UPLOAD
# ============================================================

@app.route(
    "/admin/resources/upload",
    methods=["POST"]
)
@admin_required
def admin_upload_resource():

    try:

        file = get_upload(
            "file",
            required=True,
        )

        filename = safe_original_name(
            file.filename
        )

        path = storage_path(
            "resources",
            filename,
        )

        (
            path,
            size,
            mime,
        ) = upload_to_storage(
            RESOURCE_BUCKET,
            path,
            file,
            file.mimetype,
        )

        price_text = request.form.get(
            "price",
            "0",
        ).strip()

        try:
            price = float(price_text)
        except ValueError:
            price = 0

        is_paid = bool(
            request.form.get(
                "is_paid"
            )
        )

        supabase_insert(
            "resources",
            {
                "uploaded_by":
                    current_user_id(),
                "title":
                    request.form.get(
                        "title",
                        ""
                    ).strip(),
                "description":
                    request.form.get(
                        "description",
                        ""
                    ).strip()
                    or None,
                "subject":
                    request.form.get(
                        "subject",
                        ""
                    ).strip()
                    or None,
                "level":
                    request.form.get(
                        "level",
                        ""
                    ).strip()
                    or None,
                "file_name":
                    filename,
                "file_path":
                    path,
                "price":
                    price,
                "is_paid":
                    is_paid,
                "is_active":
                    True,
            },
        )

        log_event(
            "Admin uploaded resource",
            category="Resources",
            user_id=current_user_id(),
            details=filename,
        )

        flash(
            "Resource uploaded.",
            "success",
        )

    except Exception as exc:

        logger.exception(
            "Resource upload failed"
        )

        flash(
            f"Resource upload failed: {exc}",
            "error",
        )

    return redirect(
        url_for("admin_resources")
    )


# ============================================================
# PRODUCTS
# ============================================================

@app.route("/admin/products")
@admin_required
def admin_products():

    rows = supabase_get(
        "products",
        {
            "select": "*",
            "order": "created_at.desc",
        },
        limit=300,
    )

    return page(
        "Admin Products",
        """
        <div class="card">

            <h2>Create Product</h2>

            <form
                method="post"
                action="{{ url_for(
                    'admin_create_product'
                ) }}"
            >

                <input
                    type="hidden"
                    name="_csrf"
                    value="{{ csrf_token }}"
                >

                <label>Title</label>
                <input name="title" required>

                <label>Description</label>
                <textarea name="description"></textarea>

                <label>Price</label>
                <input
                    type="number"
                    name="price"
                    step="0.01"
                    min="0"
                    value="0"
                >

                <label>Currency</label>
                <input
                    name="currency"
                    value="ZMW"
                >

                <label>Product Type</label>
                <input
                    name="product_type"
                    value="document"
                >

                <label>Storage Path</label>
                <input name="storage_path">

                <label>Original Name</label>
                <input name="original_name">

                <label>
                    <input
                        type="checkbox"
                        name="is_free"
                        value="1"
                    >
                    Free
                </label>

                <br><br>

                <label>
                    <input
                        type="checkbox"
                        name="is_published"
                        value="1"
                    >
                    Publish
                </label>

                <br><br>

                <button>
                    Create Product
                </button>

            </form>

        </div>

        <div class="card">

            <h2>Products</h2>

            <table>

            <tr>
                <th>Title</th>
                <th>Price</th>
                <th>Currency</th>
                <th>Free</th>
                <th>Published</th>
            </tr>

            {% for p in rows %}

            <tr>

                <td>
                    {{ p.title }}
                </td>

                <td>
                    {{ p.price }}
                </td>

                <td>
                    {{ p.currency }}
                </td>

                <td>
                    {{ "Yes" if p.is_free else "No" }}
                </td>

                <td>
                    {{ "Yes" if p.is_published else "No" }}
                </td>

            </tr>

            {% endfor %}

            </table>

        </div>
        """,
    )


# ============================================================
# CREATE PRODUCT
# ============================================================

@app.route(
    "/admin/products/create",
    methods=["POST"]
)
@admin_required
def admin_create_product():

    try:

        price = float(
            request.form.get(
                "price",
                "0"
            )
        )

        supabase_insert(
            "products",
            {
                "title":
                    request.form.get(
                        "title",
                        ""
                    ).strip(),
                "description":
                    request.form.get(
                        "description",
                        ""
                    ).strip(),
                "price":
                    price,
                "currency":
                    request.form.get(
                        "currency",
                        "ZMW"
                    ).strip()
                    or "ZMW",
                "product_type":
                    request.form.get(
                        "product_type",
                        "document"
                    ).strip()
                    or "document",
                "storage_path":
                    request.form.get(
                        "storage_path",
                        ""
                    ).strip()
                    or None,
                "original_name":
                    request.form.get(
                        "original_name",
                        ""
                    ).strip()
                    or None,
                "is_free":
                    bool(
                        request.form.get(
                            "is_free"
                        )
                    ),
                "is_published":
                    bool(
                        request.form.get(
                            "is_published"
                        )
                    ),
                "created_by":
                    current_user_id(),
            },
        )

        log_event(
            "Admin created product",
            category="Products",
            user_id=current_user_id(),
        )

        flash(
            "Product created.",
            "success",
        )

    except Exception as exc:

        logger.exception(
            "Product creation failed"
        )

        flash(
            f"Could not create product: {exc}",
            "error",
        )

    return redirect(
        url_for("admin_products")
    )


# ============================================================
# ADMIN LOGS
# ============================================================

@app.route("/admin/logs")
@admin_required
def admin_logs():

    rows = supabase_get(
        "logs",
        {
            "select": "*",
            "order": "created_at.desc",
        },
        limit=300,
    )

    return page(
        "Logs",
        """
        <div class="card">

            <h2>Activity Logs</h2>

            <table>

            <tr>
                <th>Time</th>
                <th>Event</th>
                <th>Category</th>
                <th>Level</th>
                <th>Details</th>
            </tr>

            {% for log in rows %}

            <tr>

                <td>
                    {{ log.created_at }}
                </td>

                <td>
                    {{ log.event }}
                </td>

                <td>
                    {{ log.category }}
                </td>

                <td>
                    {{ log.level }}
                </td>

                <td>
                    {{ log.details }}
                </td>

            </tr>

            {% endfor %}

            </table>

        </div>
        """,
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "app": APP_NAME,
        "time": datetime.now(
            timezone.utc
        ).isoformat(),
    }


# ============================================================
# 404/OTHER
# ============================================================

@app.route("/favicon.ico")
def favicon():
    return "", 204


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
