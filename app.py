import os
import io
import re
import uuid
import secrets
import logging
from datetime import datetime, timezone, timedelta
from functools import wraps
from html import escape

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
)

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)
from reportlab.lib.enums import TA_CENTER


# ============================================================
# KOJA AFRICA
# KNOWLEDGE • QUESTIONS • ANSWERS
#
# Professional foundation:
#
# Authentication
# Student portal
# Admin portal
# Questions
# Answers
# Private documents
# Document inbox/outbox
# Secure downloads
# Audit logs
# PDF answers
# Future premium resources
# Future subscriptions
# Future payments
# Future institutions
# ============================================================

load_dotenv()


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)


# ============================================================
# ENVIRONMENT
# ============================================================

FLASK_SECRET_KEY = os.getenv(
    "FLASK_SECRET_KEY",
    ""
).strip()

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
).strip().rstrip("/")

SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    ""
).strip()

SUPABASE_SECRET_KEY = os.getenv(
    "SUPABASE_SECRET_KEY",
    ""
).strip()

if not SUPABASE_SECRET_KEY:
    SUPABASE_SECRET_KEY = os.getenv(
        "SUPABASE_SERVICE_KEY",
        ""
    ).strip()

ADMIN_EMAIL = os.getenv(
    "ADMIN_EMAIL",
    ""
).strip().lower()

SUPABASE_BUCKET = os.getenv(
    "SUPABASE_BUCKET",
    "koja-files"
).strip()

MAX_FILE_SIZE = 10 * 1024 * 1024


# ============================================================
# ALLOWED FILES
# ============================================================

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
}


# ============================================================
# CONFIG VALIDATION
# ============================================================

if not FLASK_SECRET_KEY:
    raise RuntimeError(
        "FLASK_SECRET_KEY is missing."
    )

if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL is missing."
    )

if not SUPABASE_ANON_KEY:
    raise RuntimeError(
        "SUPABASE_ANON_KEY is missing."
    )

if not SUPABASE_SECRET_KEY:
    raise RuntimeError(
        "SUPABASE_SECRET_KEY is missing."
    )


app.secret_key = FLASK_SECRET_KEY


# ============================================================
# FLASK SECURITY
# ============================================================

COOKIE_SECURE = (
    os.getenv(
        "COOKIE_SECURE",
        "true"
    ).strip().lower()
    == "true"
)

app.config.update(
    MAX_CONTENT_LENGTH=MAX_FILE_SIZE,

    SESSION_COOKIE_HTTPONLY=True,

    SESSION_COOKIE_SECURE=COOKIE_SECURE,

    SESSION_COOKIE_SAMESITE="Lax",

    PERMANENT_SESSION_LIFETIME=timedelta(
        hours=8
    ),
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s "
        "%(levelname)s "
        "%(name)s "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "koja-africa"
)


# ============================================================
# RATE LIMITING
# ============================================================

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[
        "300 per hour"
    ],
    storage_uri="memory://",
)


# ============================================================
# SUPABASE ENDPOINTS
# ============================================================

SUPABASE_AUTH_URL = (
    f"{SUPABASE_URL}/auth/v1"
)

SUPABASE_REST_URL = (
    f"{SUPABASE_URL}/rest/v1"
)

SUPABASE_STORAGE_URL = (
    f"{SUPABASE_URL}/storage/v1"
)


# ============================================================
# GENERAL HELPERS
# ============================================================

def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def esc(value):
    return escape(
        str(value or "")
    )


def safe_filename(filename):
    filename = os.path.basename(
        filename or ""
    ).strip()

    filename = re.sub(
        r"[^A-Za-z0-9._ -]",
        "_",
        filename
    )

    return filename[:180] or "file"


def allowed_file(filename):
    if "." not in filename:
        return False

    extension = (
        filename.rsplit(
            ".",
            1
        )[1].lower()
    )

    return extension in ALLOWED_EXTENSIONS


def file_extension(filename):
    if "." not in filename:
        return ""

    return (
        filename.rsplit(
            ".",
            1
        )[1]
        .lower()
    )


def format_size(size):
    try:
        size = int(size)
    except Exception:
        return "Unknown"

    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


def document_direction_label(direction):
    if direction == "student_to_admin":
        return "Student → Admin"

    if direction == "admin_to_student":
        return "Admin → Student"

    return direction or "Document"


def document_type_label(filename):
    extension = file_extension(
        filename
    )

    if extension == "pdf":
        return "PDF"

    if extension in {
        "doc",
        "docx"
    }:
        return "Word"

    if extension in {
        "xls",
        "xlsx"
    }:
        return "Excel"

    if extension in {
        "ppt",
        "pptx"
    }:
        return "PowerPoint"

    if extension in {
        "jpg",
        "jpeg",
        "png",
        "webp"
    }:
        return "Image"

    if extension == "txt":
        return "Text"

    return extension.upper() or "FILE"


# ============================================================
# CSRF
# ============================================================

def get_csrf():
    token = session.get(
        "_csrf_token"
    )

    if not token:
        token = secrets.token_urlsafe(32)

        session["_csrf_token"] = token

    return token


def csrf_input():
    return (
        '<input type="hidden" '
        'name="_csrf" '
        f'value="{esc(get_csrf())}">'
    )


def check_csrf():

    submitted = request.form.get(
        "_csrf",
        ""
    )

    stored = session.get(
        "_csrf_token",
        ""
    )

    if (
        not submitted
        or not stored
        or not secrets.compare_digest(
            submitted,
            stored
        )
    ):
        abort(
            400,
            description="Invalid security token."
        )


# ============================================================
# CURRENT USER
# ============================================================

def current_user():
    return session.get("user")


def current_profile():

    user = current_user()

    if not user:
        return None

    rows = rest_get(
        "profiles",
        {
            "id":
                f"eq.{user.get('id')}",
            "limit":
                "1"
        }
    )

    if rows:
        return rows[0]

    return None


# ============================================================
# SUPABASE HEADERS
# ============================================================

def supabase_headers():

    return {
        "apikey":
            SUPABASE_SECRET_KEY,

        "Authorization":
            f"Bearer {SUPABASE_SECRET_KEY}",

        "Content-Type":
            "application/json",
    }


def auth_headers():

    return {
        "apikey":
            SUPABASE_ANON_KEY,

        "Content-Type":
            "application/json",
    }


def storage_headers():

    return {
        "apikey":
            SUPABASE_SECRET_KEY,

        "Authorization":
            f"Bearer {SUPABASE_SECRET_KEY}",
    }


# ============================================================
# SUPABASE GET
# ============================================================

def rest_get(
    table,
    params=None,
    select="*"
):

    try:

        query = {
            "select": select
        }

        if params:
            query.update(params)

        response = requests.get(
            f"{SUPABASE_REST_URL}/{table}",
            headers=supabase_headers(),
            params=query,
            timeout=30,
        )

        if not response.ok:

            logger.error(
                "Supabase GET %s failed: %s",
                table,
                response.text[:1000],
            )

            return []

        data = response.json()

        if not isinstance(
            data,
            list
        ):
            return []

        return data

    except Exception:

        logger.exception(
            "Supabase GET exception"
        )

        return []


# ============================================================
# SUPABASE INSERT
# ============================================================

def rest_insert(
    table,
    payload,
    returning=True
):

    headers = supabase_headers()

    if returning:

        headers["Prefer"] = (
            "return=representation"
        )

    try:

        response = requests.post(
            f"{SUPABASE_REST_URL}/{table}",
            headers=headers,
            json=payload,
            timeout=30,
        )

        if not response.ok:

            logger.error(
                "Supabase INSERT %s failed: %s",
                table,
                response.text[:1000],
            )

            return None

        if not response.text:
            return []

        return response.json()

    except Exception:

        logger.exception(
            "Supabase INSERT exception"
        )

        return None


# ============================================================
# SUPABASE UPDATE
# ============================================================

def rest_update(
    table,
    params,
    payload
):

    headers = supabase_headers()

    headers["Prefer"] = (
        "return=representation"
    )

    try:

        response = requests.patch(
            f"{SUPABASE_REST_URL}/{table}",
            headers=headers,
            params=params,
            json=payload,
            timeout=30,
        )

        if not response.ok:

            logger.error(
                "Supabase UPDATE %s failed: %s",
                table,
                response.text[:1000],
            )

            return None

        if not response.text:
            return []

        return response.json()

    except Exception:

        logger.exception(
            "Supabase UPDATE exception"
        )

        return None


# ============================================================
# SUPABASE DELETE
# ============================================================

def rest_delete(
    table,
    params
):

    try:

        response = requests.delete(
            f"{SUPABASE_REST_URL}/{table}",
            headers=supabase_headers(),
            params=params,
            timeout=30,
        )

        if not response.ok:

            logger.error(
                "Supabase DELETE %s failed: %s",
                table,
                response.text[:1000],
            )

            return False

        return True

    except Exception:

        logger.exception(
            "Supabase DELETE exception"
        )

        return False


# ============================================================
# SUPABASE AUTH
# ============================================================

def supabase_signup(
    email,
    password,
    name
):

    try:

        response = requests.post(
            f"{SUPABASE_AUTH_URL}/signup",
            headers=auth_headers(),
            json={
                "email":
                    email,

                "password":
                    password,

                "data": {
                    "name":
                        name
                }
            },
            timeout=30,
        )

        try:
            data = response.json()
        except ValueError:
            data = {}

        if not response.ok:

            return (
                None,
                (
                    data.get("msg")
                    or data.get("message")
                    or data.get(
                        "error_description"
                    )
                    or "Registration failed."
                )
            )

        return data, None

    except Exception:

        logger.exception(
            "Signup failed"
        )

        return (
            None,
            "Authentication service is temporarily unavailable."
        )


def supabase_login(
    email,
    password
):

    try:

        response = requests.post(
            f"{SUPABASE_AUTH_URL}"
            "/token?grant_type=password",

            headers=auth_headers(),

            json={
                "email":
                    email,

                "password":
                    password
            },

            timeout=30,
        )

        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.ok:

            user = data.get(
                "user"
            )

            if not user:

                return (
                    None,
                    "Supabase did not return a user."
                )

            return data, None

        error_code = data.get(
            "error_code",
            ""
        )

        error_description = data.get(
            "error_description",
            ""
        )

        if error_code == "invalid_credentials":

            return (
                None,
                "Invalid email or password."
            )

        if (
            "email not confirmed"
            in error_description.lower()
        ):

            return (
                None,
                "Please confirm your email before logging in."
            )

        return (
            None,
            (
                data.get("msg")
                or data.get("message")
                or error_description
                or "Invalid email or password."
            )
        )

    except Exception:

        logger.exception(
            "Login failed"
        )

        return (
            None,
            "Authentication service is temporarily unavailable."
        )


# ============================================================
# PROFILE MANAGEMENT
# ============================================================

def ensure_profile(user):

    if not user:
        return None

    user_id = user.get(
        "id"
    )

    email = (
        user.get(
            "email"
        )
        or ""
    ).strip().lower()

    if not user_id:
        return None

    profiles = rest_get(
        "profiles",
        {
            "id":
                f"eq.{user_id}",

            "limit":
                "1"
        }
    )

    if profiles:

        profile = profiles[0]

        if (
            ADMIN_EMAIL
            and email == ADMIN_EMAIL
            and profile.get("role")
            != "admin"
        ):

            updated = rest_update(
                "profiles",
                {
                    "id":
                        f"eq.{user_id}"
                },
                {
                    "role":
                        "admin"
                }
            )

            if updated:
                profile = updated[0]

        return profile

    metadata = (
        user.get(
            "user_metadata"
        )
        or {}
    )

    name = (
        metadata.get("name")
        or metadata.get("full_name")
        or (
            email.split("@")[0]
            if email
            else "Student"
        )
    ).strip()

    role = "student"

    if (
        ADMIN_EMAIL
        and email == ADMIN_EMAIL
    ):
        role = "admin"

    result = rest_insert(
        "profiles",
        {
            "id":
                user_id,

            "name":
                name or "Student",

            "email":
                email,

            "role":
                role
        }
    )

    if result:
        return result[0]

    return None


# ============================================================
# AUTH DECORATORS
# ============================================================

def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not current_user():

            flash(
                "Please log in first.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        return view(
            *args,
            **kwargs
        )

    return wrapped


def admin_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        user = current_user()

        if not user:

            return redirect(
                url_for("login")
            )

        profile = current_profile()

        if (
            not profile
            or profile.get("role")
            != "admin"
        ):

            abort(403)

        return view(
            *args,
            **kwargs
        )

    return wrapped


def student_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        user = current_user()

        if not user:

            return redirect(
                url_for("login")
            )

        profile = current_profile()

        if not profile:

            abort(403)

        if profile.get("role") == "admin":

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        return view(
            *args,
            **kwargs
        )

    return wrapped


# ============================================================
# LOGGING
# ============================================================

def write_log(
    event,
    category="System",
    level="INFO",
    details="",
    user_id=None
):

    try:

        rest_insert(
            "logs",
            {
                "event":
                    str(event)[:500],

                "category":
                    str(category)[:100],

                "level":
                    str(level)[:50],

                "details":
                    str(details)[:4000],

                "user_id":
                    user_id
            },

            returning=False
        )

    except Exception:

        logger.exception(
            "Database logging failed"
        )


# ============================================================
# PRIVATE STORAGE
# ============================================================

def upload_private_file(
    uploaded_file,
    folder
):

    if (
        not uploaded_file
        or not uploaded_file.filename
    ):

        raise ValueError(
            "No file selected."
        )

    filename = safe_filename(
        uploaded_file.filename
    )

    if not allowed_file(filename):

        raise ValueError(
            "Unsupported file type."
        )

    content = uploaded_file.read()

    if not content:

        raise ValueError(
            "The uploaded file is empty."
        )

    if len(content) > MAX_FILE_SIZE:

        raise ValueError(
            "Maximum file size is 10 MB."
        )

    extension = ""

    if "." in filename:

        extension = (
            "."
            + file_extension(filename)
        )

    storage_path = (
        f"{folder.strip('/')}/"
        f"{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/"
        f"{uuid.uuid4().hex}"
        f"{extension}"
    )

    content_type = (
        uploaded_file.mimetype
        or "application/octet-stream"
    )

    headers = storage_headers()

    headers["Content-Type"] = (
        content_type
    )

    response = requests.post(
        f"{SUPABASE_STORAGE_URL}"
        f"/object/{SUPABASE_BUCKET}"
        f"/{storage_path}",

        headers=headers,

        data=content,

        timeout=120,
    )

    if not response.ok:

        logger.error(
            "Storage upload failed: %s",
            response.text[:1000],
        )

        raise RuntimeError(
            "Storage upload failed."
        )

    return {
        "original_name":
            filename,

        "storage_path":
            storage_path,

        "size":
            len(content),

        "content_type":
            content_type,
    }


def download_private_file(
    storage_path
):

    if not storage_path:
        return None

    try:

        response = requests.get(
            f"{SUPABASE_STORAGE_URL}"
            f"/object/{SUPABASE_BUCKET}"
            f"/{storage_path}",

            headers=storage_headers(),

            timeout=120,
        )

        if not response.ok:

            logger.error(
                "Storage download failed: %s",
                response.text[:500],
            )

            return None

        return response.content

    except Exception:

        logger.exception(
            "Storage download failed"
        )

        return None


def delete_private_file(
    storage_path
):

    if not storage_path:
        return False

    try:

        response = requests.delete(
            f"{SUPABASE_STORAGE_URL}"
            f"/object/{SUPABASE_BUCKET}"
            f"/{storage_path}",

            headers=storage_headers(),

            timeout=60,
        )

        return response.ok

    except Exception:

        logger.exception(
            "Storage deletion failed"
        )

        return False


# ============================================================
# PDF ANSWER
# ============================================================

def create_answer_pdf(
    question,
    student_name
):

    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,

        pagesize=A4,

        leftMargin=18 * mm,

        rightMargin=18 * mm,

        topMargin=18 * mm,

        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "KOJATitle",

        parent=styles["Title"],

        alignment=TA_CENTER,

        fontSize=22,

        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        "KOJASubtitle",

        parent=styles["Normal"],

        alignment=TA_CENTER,

        fontSize=10,

        spaceAfter=18,
    )

    heading_style = ParagraphStyle(
        "KOJAHeading",

        parent=styles["Heading2"],

        fontSize=13,

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

    question_text = (
        escape(
            question.get(
                "question",
                ""
            )
        )
        .replace(
            "\n",
            "<br/>"
        )
    )

    answer_text = (
        escape(
            question.get(
                "answer",
                ""
            )
        )
        .replace(
            "\n",
            "<br/>"
        )
    )

    story = [

        Paragraph(
            "KOJA AFRICA",
            title_style
        ),

        Paragraph(
            "Knowledge • Questions • Answers",
            subtitle_style
        ),

        Paragraph(
            "<b>Student:</b> "
            + escape(student_name),
            body_style
        ),

        Paragraph(
            "Question",
            heading_style
        ),

        Paragraph(
            question_text,
            body_style
        ),

        Paragraph(
            "Answer",
            heading_style
        ),

        Paragraph(
            answer_text,
            body_style
        ),

        Spacer(
            1,
            20
        ),

        Paragraph(
            "Generated by KOJA AFRICA",
            subtitle_style
        ),
    ]

    document.build(
        story
    )

    buffer.seek(0)

    return buffer


# ============================================================
# BASE HTML
# ============================================================

BASE_HTML = r"""
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0"
>

<meta
name="theme-color"
content="#061b49"
>

<meta
name="description"
content="KOJA AFRICA — Knowledge, Questions and Answers"
>

<title>
{{ title }} | KOJA AFRICA
</title>

<style>

* {
    box-sizing: border-box;
}

html {
    scroll-behavior: smooth;
}

body {
    margin: 0;
    font-family:
        Arial,
        Helvetica,
        sans-serif;

    background: #f4f7fb;

    color: #172033;
}

a {
    text-decoration: none;
}

header {
    background: #061b49;

    color: white;

    min-height: 68px;

    padding:
        13px 20px;

    display: flex;

    justify-content:
        space-between;

    align-items:
        center;

    gap: 15px;

    position: sticky;

    top: 0;

    z-index: 100;
}

.brand {
    color: white;

    font-size: 23px;

    font-weight: 900;

    white-space: nowrap;
}

.brand span {
    color: #4ea1ff;
}

.nav {
    display: flex;

    gap: 5px;

    flex-wrap: wrap;
}

.nav a {
    color: white;

    padding:
        9px 11px;

    border-radius: 8px;

    font-size: 14px;

    white-space: nowrap;
}

.nav a:hover {
    background: #16366d;
}

.container {
    width:
        min(1200px, 94%);

    margin:
        28px auto;

    min-height: 70vh;
}

.hero {
    background:
        linear-gradient(
            135deg,
            #061b49,
            #0b347f
        );

    color: white;

    border-radius: 22px;

    padding:
        65px 24px;

    text-align: center;

    box-shadow:
        0 15px 45px
        rgba(6,27,73,.15);
}

.hero h1 {
    font-size:
        clamp(35px,8vw,62px);

    margin:
        0 0 12px;
}

.hero p {
    max-width: 760px;

    margin:
        0 auto 25px;

    line-height: 1.7;

    color: #dce8ff;
}

.grid {
    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(220px,1fr)
        );

    gap: 18px;
}

.card {
    background: white;

    border-radius: 16px;

    padding: 22px;

    box-shadow:
        0 5px 20px
        rgba(0,0,0,.06);
}

.card h2,
.card h3 {
    margin-top: 0;
}

.btn {
    display: inline-block;

    border: 0;

    cursor: pointer;

    background: #0d6efd;

    color: white;

    padding:
        11px 17px;

    border-radius: 9px;

    font-weight: 700;

    font-size: 14px;
}

.btn:hover {
    opacity: .9;
}

.btn.dark {
    background: #061b49;
}

.btn.green {
    background: #198754;
}

.btn.red {
    background: #dc3545;
}

.btn.orange {
    background: #e67e22;
}

.btn.light {
    background: white;

    color: #061b49;
}

.actions {
    display: flex;

    gap: 10px;

    flex-wrap: wrap;

    justify-content: center;
}

form {
    background: white;

    border-radius: 16px;

    padding: 22px;

    box-shadow:
        0 5px 20px
        rgba(0,0,0,.06);
}

label {
    display: block;

    margin:
        13px 0 6px;

    font-weight: 700;
}

input,
textarea,
select {
    width: 100%;

    padding: 12px;

    border:
        1px solid #d5dbe5;

    border-radius: 8px;

    font: inherit;

    background: white;
}

input:focus,
textarea:focus,
select:focus {
    outline:
        2px solid #9fc5ff;

    border-color:
        #0d6efd;
}

textarea {
    min-height: 150px;

    resize: vertical;
}

table {
    width: 100%;

    border-collapse:
        collapse;

    background: white;
}

th,
td {
    padding: 12px;

    border-bottom:
        1px solid #e5e9f0;

    text-align: left;

    vertical-align: top;
}

th {
    background: #eef3fb;
}

.tablewrap {
    overflow-x: auto;

    border-radius: 12px;
}

.badge {
    display: inline-block;

    padding:
        5px 9px;

    border-radius: 20px;

    background: #e9f2ff;

    color: #0759a5;

    font-size: 12px;

    font-weight: 700;
}

.badge.green {
    background: #e5f8ed;

    color: #116332;
}

.badge.red {
    background: #ffe8e8;

    color: #8a1111;
}

.badge.orange {
    background: #fff1df;

    color: #8a4b08;
}

.stat {
    font-size: 32px;

    font-weight: 800;

    color: #0d6efd;
}

.flash {
    padding:
        12px 15px;

    margin-bottom: 15px;

    border-radius: 9px;

    background: #e7f1ff;

    color: #063b7a;
}

.flash.error {
    background: #ffe8e8;

    color: #8a1111;
}

.flash.success {
    background: #e5f8ed;

    color: #116332;
}

.flash.warning {
    background: #fff4d9;

    color: #765500;
}

.empty {
    text-align: center;

    padding: 40px;

    color: #687386;
}

.info {
    background: #eef5ff;

    border-left:
        4px solid #0d6efd;

    padding: 14px;

    border-radius: 8px;
}

.answer {
    white-space: pre-wrap;

    line-height: 1.7;

    background: #f7f9fc;

    padding: 15px;

    border-radius: 10px;
}

.question-box {
    line-height: 1.7;

    background: #f7f9fc;

    padding: 15px;

    border-radius: 10px;
}

.document-card {
    border:
        1px solid #e3e8f0;

    border-radius: 14px;

    padding: 18px;

    background: white;

    margin-bottom: 15px;
}

.document-title {
    font-size: 18px;

    font-weight: 800;

    color: #061b49;
}

.document-meta {
    font-size: 13px;

    color: #687386;

    line-height: 1.7;
}

.searchbar {
    display: grid;

    grid-template-columns:
        1fr auto;

    gap: 10px;

    margin-bottom: 20px;
}

.notice {
    padding: 12px;

    border-radius: 10px;

    background: #f1f5fa;

    color: #4d596c;
}

footer {
    text-align: center;

    padding:
        35px 15px;

    color: #697386;
}

small {
    color: #687386;
}

hr {
    border: 0;

    border-top:
        1px solid #e5e9f0;

    margin: 20px 0;
}

.mini-grid {
    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(160px,1fr)
        );

    gap: 12px;
}

.mini-stat {
    padding: 16px;

    border-radius: 12px;

    background: #f7f9fc;
}

.mini-stat strong {
    display: block;

    font-size: 24px;

    color: #061b49;
}

.future {
    border:
        1px dashed #9eb3d3;

    background:
        linear-gradient(
            135deg,
            #f8fbff,
            #eef5ff
        );
}


/* ============================================================
   STARTUP
   ============================================================ */

#startup {
    position: fixed;

    inset: 0;

    z-index: 99999;

    background: #061b49;

    display: flex;

    justify-content: center;

    align-items: center;

    opacity: 1;

    visibility: visible;

    transition:
        opacity 1s ease,
        visibility 1s ease;
}

#startup.hide {
    opacity: 0;

    visibility: hidden;

    pointer-events: none;
}

.startup-content {
    text-align: center;

    color: white;

    animation:
        startupFade 1.5s ease;
}

.startup-logo {
    font-size:
        clamp(48px,14vw,90px);

    font-weight: 900;

    letter-spacing: 3px;

    margin: 0;
}

.startup-logo .k {
    color: #4ea1ff;
}

.startup-logo .o {
    color: #38c172;
}

.startup-logo .j {
    color: #ff4d5d;
}

.startup-logo .a {
    color: #dce8ff;
}

.startup-subtitle {
    margin-top: 10px;

    font-size: 13px;

    letter-spacing: 2px;

    color: #dce8ff;
}

.startup-line {
    width: 70px;

    height: 3px;

    background: white;

    margin:
        20px auto 0;

    border-radius: 20px;

    animation:
        startupLine 1.5s ease infinite;
}

@keyframes startupFade {

    from {
        opacity: 0;

        transform:
            translateY(15px)
            scale(.96);
    }

    to {
        opacity: 1;

        transform:
            translateY(0)
            scale(1);
    }
}

@keyframes startupLine {

    0% {
        transform: scaleX(.3);

        opacity: .3;
    }

    50% {
        transform: scaleX(1);

        opacity: 1;
    }

    100% {
        transform: scaleX(.3);

        opacity: .3;
    }
}


/* ============================================================
   MOBILE
   ============================================================ */

@media(max-width:700px) {

    header {
        flex-direction: column;

        align-items: flex-start;
    }

    .nav {
        overflow-x: auto;

        flex-wrap: nowrap;

        width: 100%;
    }

    .hero {
        padding:
            42px 18px;
    }

    th,
    td {
        min-width: 130px;
    }

    .searchbar {
        grid-template-columns:
            1fr;
    }

}

</style>

</head>

<body>


{% if show_startup %}

<div id="startup">

    <div class="startup-content">

        <h1 class="startup-logo">

            <span class="k">K</span><span class="o">O</span><span class="j">J</span><span class="a">A</span>

        </h1>

        <div class="startup-subtitle">

            KNOWLEDGE • QUESTIONS • ANSWERS

        </div>

        <div class="startup-line"></div>

    </div>

</div>

<script>

(function () {

    const startup =
        document.getElementById("startup");

    if (!startup) {
        return;
    }

    setTimeout(function () {

        startup.classList.add("hide");

    }, 1800);

})();

</script>

{% endif %}


<header>

<a
class="brand"
href="{{ url_for('home') }}"
>
KOJA <span>AFRICA</span>
</a>

<nav class="nav">

{% if session.get("user") %}

    {% if session.get("role") == "admin" %}

        <a
        href="{{ url_for('admin_dashboard') }}"
        >
        Dashboard
        </a>

        <a
        href="{{ url_for('admin_questions') }}"
        >
        Questions
        </a>

        <a
        href="{{ url_for('admin_documents') }}"
        >
        Documents
        </a>

        <a
        href="{{ url_for('admin_users') }}"
        >
        Users
        </a>

        <a
        href="{{ url_for('admin_logs') }}"
        >
        Logs
        </a>

    {% else %}

        <a
        href="{{ url_for('student_dashboard') }}"
        >
        Dashboard
        </a>

        <a
        href="{{ url_for('ask_question') }}"
        >
        Ask
        </a>

        <a
        href="{{ url_for('student_questions') }}"
        >
        My Questions
        </a>

        <a
        href="{{ url_for('student_documents') }}"
        >
        Documents
        </a>

    {% endif %}

    <a
    href="{{ url_for('logout') }}"
    >
    Logout
    </a>

{% else %}

    <a
    href="{{ url_for('login') }}"
    >
    Log In
    </a>

    <a
    href="{{ url_for('register') }}"
    >
    Create Account
    </a>

{% endif %}

</nav>

</header>


<main class="container">

{% with messages =
get_flashed_messages(
with_categories=true
) %}

{% for category, message in messages %}

<div class="flash {{ category }}">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</main>


<footer>

KOJA AFRICA —
Knowledge • Questions • Answers

</footer>


</body>

</html>
"""


# ============================================================
# PAGE RENDERER
# ============================================================

def page(
    content,
    title="KOJA AFRICA",
    show_startup=False
):

    return render_template_string(
        BASE_HTML,

        content=content,

        title=title,

        show_startup=show_startup,
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return page(
        """
<section class="hero">

<h1>
KOJA AFRICA
</h1>

<p>
Assignment Questions • Academic Answers •
Learning Resources
</p>

<div class="actions">

<a
class="btn"
href="/login"
>
Log In
</a>

<a
class="btn light"
href="/register"
>
Create Account
</a>

</div>

</section>

<br>

<div class="grid">

<div class="card">

<h3>
Ask Questions
</h3>

<p>
Submit academic questions securely
and track your answers.
</p>

</div>

<div class="card">

<h3>
Academic Answers
</h3>

<p>
Receive structured academic answers
from the KOJA administration team.
</p>

</div>

<div class="card">

<h3>
Private Documents
</h3>

<p>
Send and receive documents through
KOJA's protected document system.
</p>

</div>

<div class="card future">

<h3>
KOJA Learning Marketplace
</h3>

<p>
Future-ready foundation for premium
learning resources, subscriptions,
institutional services and other
KOJA revenue streams.
</p>

<span class="badge orange">
Coming platform feature
</span>

</div>

</div>
""",

        "Home",

        show_startup=True,
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
@limiter.limit(
    "5 per minute",
    methods=["POST"]
)
def register():

    if request.method == "POST":

        check_csrf()

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        confirm = request.form.get(
            "confirm",
            ""
        )

        if len(name) < 2:

            flash(
                "Enter your full name.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if not re.match(
            r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
            email
        ):

            flash(
                "Enter a valid email address.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 8:

            flash(
                "Password must contain at least 8 characters.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if password != confirm:

            flash(
                "Passwords do not match.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        data, error = supabase_signup(
            email,
            password,
            name
        )

        if error:

            flash(
                error,
                "error"
            )

            return redirect(
                url_for("register")
            )

        user = (
            data.get("user")
            if data
            else None
        )

        if user:

            ensure_profile(
                user
            )

            write_log(
                "New account registration",
                "Authentication",
                "INFO",
                email,
                user.get("id")
            )

        flash(
            "Account created successfully. "
            "If email confirmation is enabled "
            "in Supabase, confirm your email "
            "before logging in.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return page(
        f"""
<div style="max-width:520px;margin:auto">

<h1>
Create Account
</h1>

<form method="post">

{csrf_input()}

<label>
Full Name
</label>

<input
name="name"
required
autocomplete="name"
maxlength="120"
>

<label>
Email
</label>

<input
type="email"
name="email"
required
autocomplete="email"
maxlength="180"
>

<label>
Password
</label>

<input
type="password"
name="password"
required
minlength="8"
autocomplete="new-password"
>

<label>
Confirm Password
</label>

<input
type="password"
name="confirm"
required
minlength="8"
autocomplete="new-password"
>

<br><br>

<button
class="btn"
type="submit"
>
Create Account
</button>

</form>

</div>
""",

        "Create Account"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
@limiter.limit(
    "10 per minute",
    methods=["POST"]
)
def login():

    if request.method == "POST":

        check_csrf()

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
                "error"
            )

            return redirect(
                url_for("login")
            )

        data, error = supabase_login(
            email,
            password
        )

        if error:

            flash(
                error,
                "error"
            )

            return redirect(
                url_for("login")
            )

        user = (
            data.get("user")
            if data
            else None
        )

        if not user:

            flash(
                "Login failed.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        profile = ensure_profile(
            user
        )

        if not profile:

            flash(
                "Your account exists, but "
                "your KOJA profile could not be loaded.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        session.clear()

        session.permanent = True

        session["user"] = {
            "id":
                user.get("id"),

            "email":
                user.get("email"),
        }

        session["role"] = profile.get(
            "role",
            "student"
        )

        session["_csrf_token"] = (
            secrets.token_urlsafe(32)
        )

        write_log(
            "User logged in",
            "Authentication",
            "INFO",
            email,
            user.get("id")
        )

        if profile.get("role") == "admin":

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    return page(
        f"""
<div style="max-width:520px;margin:auto">

<h1>
Log In
</h1>

<form method="post">

{csrf_input()}

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

<br><br>

<button
class="btn"
type="submit"
>
Log In
</button>

</form>

<br>

<div class="card">

No account?

<a href="/register">
Create Account
</a>

</div>

</div>
""",

        "Log In"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    user = current_user()

    if user:

        write_log(
            "User logged out",
            "Authentication",
            "INFO",
            "",
            user.get("id")
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
# STUDENT DASHBOARD
# ============================================================

@app.route("/student")
@student_required
def student_dashboard():

    profile = current_profile()

    student_id = profile["id"]

    questions = rest_get(
        "questions",
        {
            "student_id":
                f"eq.{student_id}",

            "order":
                "created_at.desc"
        }
    )

    received_documents = rest_get(
        "documents",
        {
            "recipient_id":
                f"eq.{student_id}",

            "direction":
                "eq.admin_to_student",

            "order":
                "created_at.desc"
        }
    )

    sent_documents = rest_get(
        "documents",
        {
            "sender_id":
                f"eq.{student_id}",

            "direction":
                "eq.student_to_admin",

            "order":
                "created_at.desc"
        }
    )

    answered = sum(
        bool(q.get("answer"))
        for q in questions
    )

    return page(
        f"""
<h1>
Student Dashboard
</h1>

<p>
Welcome,
<strong>
{esc(profile.get("name", "Student"))}
</strong>
</p>

<div class="grid">

<div class="card">

<h3>
My Questions
</h3>

<div class="stat">
{len(questions)}
</div>

</div>

<div class="card">

<h3>
Answered
</h3>

<div class="stat">
{answered}
</div>

</div>

<div class="card">

<h3>
Received Documents
</h3>

<div class="stat">
{len(received_documents)}
</div>

</div>

<div class="card">

<h3>
Sent Documents
</h3>

<div class="stat">
{len(sent_documents)}
</div>

</div>

</div>

<br>

<div class="card">

<h2>
Document Centre
</h2>

<p>
Your private communication area for
sending documents to KOJA Admin and
receiving documents from KOJA Admin.
</p>

<div class="actions"
style="justify-content:flex-start">

<a
class="btn"
href="/student/documents"
>
Open Documents
</a>

<a
class="btn dark"
href="/student/question/new"
>
Ask Question
</a>

</div>

</div>
""",

        "Student Dashboard"
    )


# ============================================================
# ASK QUESTION
# ============================================================

@app.route(
    "/student/question/new",
    methods=["GET", "POST"]
)
@student_required
@limiter.limit(
    "20 per hour",
    methods=["POST"]
)
def ask_question():

    profile = current_profile()

    if request.method == "POST":

        check_csrf()

        question_text = request.form.get(
            "question",
            ""
        ).strip()

        if not question_text:

            flash(
                "Enter your question.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        if len(question_text) > 20000:

            flash(
                "Question is too long.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        question_id = str(
            uuid.uuid4()
        )

        created = rest_insert(
            "questions",
            {
                "id":
                    question_id,

                "student_id":
                    profile["id"],

                "student_name":
                    profile.get(
                        "name",
                        ""
                    ),

                "question":
                    question_text,

                "answer":
                    "",

                "answer_by":
                    ""
            }
        )

        if not created:

            flash(
                "Question could not be submitted.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        uploaded = request.files.get(
            "file"
        )

        if (
            uploaded
            and uploaded.filename
        ):

            try:

                info = upload_private_file(
                    uploaded,
                    f"questions/{question_id}"
                )

                recorded = rest_insert(
                    "question_files",
                    {
                        "question_id":
                            question_id,

                        "original_name":
                            info[
                                "original_name"
                            ],

                        "storage_path":
                            info[
                                "storage_path"
                            ],

                        "size":
                            info[
                                "size"
                            ],

                        "file_type":
                            "question"
                    },
                    returning=False
                )

                if not recorded:

                    delete_private_file(
                        info[
                            "storage_path"
                        ]
                    )

                    flash(
                        "Question submitted, "
                        "but attachment could not "
                        "be recorded.",
                        "warning"
                    )

            except Exception:

                logger.exception(
                    "Question attachment failed"
                )

                flash(
                    "Question submitted, "
                    "but the attachment failed.",
                    "warning"
                )

        write_log(
            "Question submitted",
            "Questions",
            "INFO",
            question_text[:500],
            profile["id"]
        )

        flash(
            "Your question has been submitted.",
            "success"
        )

        return redirect(
            url_for(
                "student_questions"
            )
        )

    return page(
        f"""
<h1>
Ask a Question
</h1>

<form
method="post"
enctype="multipart/form-data"
>

{csrf_input()}

<label>
Question
</label>

<textarea
name="question"
required
maxlength="20000"
placeholder="Enter your academic question..."
></textarea>

<label>
Attachment
</label>

<small>
Optional. PDF, Word, image, spreadsheet,
presentation or text file. Maximum 10 MB.
</small>

<input
type="file"
name="file"
>

<br><br>

<button
class="btn"
type="submit"
>
Submit Question
</button>

</form>
""",

        "Ask Question"
    )


# ============================================================
# STUDENT QUESTIONS
# ============================================================

@app.route(
    "/student/questions"
)
@student_required
def student_questions():

    profile = current_profile()

    questions = rest_get(
        "questions",
        {
            "student_id":
                f"eq.{profile['id']}",

            "order":
                "created_at.desc"
        }
    )

    blocks = []

    for question in questions:

        files = rest_get(
            "question_files",
            {
                "question_id":
                    f"eq.{question['id']}",

                "order":
                    "created_at.asc"
            }
        )

        question_files = ""
        answer_files = ""

        for file in files:

            link = f"""
<div style="margin:7px 0">

📎

<a
href="/question-file/{file['id']}"
>
{esc(file.get("original_name"))}
</a>

<span class="badge">
{esc(file.get("file_type"))}
</span>

</div>
"""

            if file.get(
                "file_type"
            ) == "answer":

                answer_files += link

            else:

                question_files += link

        answer = question.get(
            "answer",
            ""
        )

        if answer:

            answer_block = f"""
<div class="card">

<h3>
Answer
</h3>

<div class="answer">
{esc(answer)}
</div>

<br>

{answer_files}

<br>

<a
class="btn"
href="/student/question/{question['id']}/pdf"
>
Download Answer PDF
</a>

</div>
"""

        else:

            answer_block = """
<div class="card">

<span class="badge orange">
Waiting for answer
</span>

</div>
"""

        status = (
            "Answered"
            if answer
            else "Waiting"
        )

        badge = (
            "green"
            if answer
            else "orange"
        )

        blocks.append(
            f"""
<div class="card">

<h3>
Question
</h3>

<div class="question-box">
{esc(question.get("question"))}
</div>

<br>

<span class="badge {badge}">
{status}
</span>

<p>
<small>
Submitted:
{esc(question.get("created_at"))}
</small>
</p>

{question_files}

</div>

<br>

{answer_block}

<br>
"""
        )

    content = "".join(
        blocks
    )

    if not content:

        content = """
<div class="card empty">

You have not submitted any
questions yet.

<br><br>

<a
class="btn"
href="/student/question/new"
>
Ask a Question
</a>

</div>
"""

    return page(
        f"""
<h1>
My Questions
</h1>

{content}
""",

        "My Questions"
    )


# ============================================================
# STUDENT ANSWER PDF
# ============================================================

@app.route(
    "/student/question/<question_id>/pdf"
)
@student_required
def student_question_pdf(
    question_id
):

    profile = current_profile()

    rows = rest_get(
        "questions",
        {
            "id":
                f"eq.{question_id}",

            "student_id":
                f"eq.{profile['id']}",

            "limit":
                "1"
        }
    )

    if (
        not rows
        or not rows[0].get("answer")
    ):

        abort(404)

    pdf = create_answer_pdf(
        rows[0],
        profile.get(
            "name",
            "Student"
        )
    )

    write_log(
        "Answer PDF downloaded",
        "Documents",
        "INFO",
        question_id,
        profile["id"]
    )

    return send_file(
        pdf,

        as_attachment=True,

        download_name=(
            f"KOJA_Answer_"
            f"{question_id[:8]}.pdf"
        ),

        mimetype="application/pdf"
    )


# ============================================================
# STUDENT DOCUMENTS
#
# INBOX + OUTBOX
# ============================================================

@app.route(
    "/student/documents",
    methods=["GET", "POST"]
)
@student_required
@limiter.limit(
    "20 per hour",
    methods=["POST"]
)
def student_documents():

    profile = current_profile()

    student_id = profile["id"]

    # ========================================================
    # SEND DOCUMENT TO ADMIN
    # ========================================================

    if request.method == "POST":

        check_csrf()

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        category = request.form.get(
            "category",
            "Academic"
        ).strip()

        uploaded = request.files.get(
            "file"
        )

        if not title:

            flash(
                "Document title is required.",
                "error"
            )

            return redirect(
                url_for("student_documents")
            )

        if not uploaded or not uploaded.filename:

            flash(
                "Please select a document.",
                "error"
            )

            return redirect(
                url_for("student_documents")
            )

        if len(title) > 300:

            flash(
                "Title is too long.",
                "error"
            )

            return redirect(
                url_for("student_documents")
            )

        if len(description) > 4000:

            flash(
                "Description is too long.",
                "error"
            )

            return redirect(
                url_for("student_documents")
            )

        storage_path = None

        try:

            info = upload_private_file(
                uploaded,
                f"documents/student/{student_id}"
            )

            storage_path = (
                info["storage_path"]
            )

            created = rest_insert(
                "documents",
                {
                    "direction":
                        "student_to_admin",

                    "sender_id":
                        student_id,

                    "sender_name":
                        profile.get(
                            "name",
                            "Student"
                        ),

                    "recipient_id":
                        None,

                    "recipient_name":
                        "KOJA Admin",

                    "title":
                        title,

                    "description":
                        description,

                    "original_name":
                        info[
                            "original_name"
                        ],

                    "storage_path":
                        storage_path,

                    "size":
                        info["size"]
                }
            )

            if not created:

                delete_private_file(
                    storage_path
                )

                flash(
                    "The document could not be saved.",
                    "error"
                )

                return redirect(
                    url_for(
                        "student_documents"
                    )
                )

            write_log(
                "Student uploaded document",
                "Documents",
                "INFO",
                (
                    f"{category}: "
                    f"{title}"
                ),
                student_id
            )

            flash(
                "Document sent successfully. "
                "KOJA Admin can now access it.",
                "success"
            )

        except ValueError as error:

            flash(
                str(error),
                "error"
            )

        except Exception:

            logger.exception(
                "Student document upload failed"
            )

            if storage_path:

                delete_private_file(
                    storage_path
                )

            flash(
                "Document upload failed.",
                "error"
            )

        return redirect(
            url_for(
                "student_documents"
            )
        )

    # ========================================================
    # SEARCH
    # ========================================================

    search = request.args.get(
        "q",
        ""
    ).strip().lower()

    # ========================================================
    # INBOX
    # ========================================================

    received_documents = rest_get(
        "documents",
        {
            "recipient_id":
                f"eq.{student_id}",

            "direction":
                "eq.admin_to_student",

            "order":
                "created_at.desc"
        }
    )

    # ========================================================
    # OUTBOX
    # ========================================================

    sent_documents = rest_get(
        "documents",
        {
            "sender_id":
                f"eq.{student_id}",

            "direction":
                "eq.student_to_admin",

            "order":
                "created_at.desc"
        }
    )

    # ========================================================
    # SEARCH FILTER
    # ========================================================

    def matches(document):

        if not search:
            return True

        text = " ".join([
            str(
                document.get(
                    "title",
                    ""
                )
            ),

            str(
                document.get(
                    "description",
                    ""
                )
            ),

            str(
                document.get(
                    "original_name",
                    ""
                )
            )
        ]).lower()

        return search in text

    received_documents = [
        d
        for d in received_documents
        if matches(d)
    ]

    sent_documents = [
        d
        for d in sent_documents
        if matches(d)
    ]

    # ========================================================
    # RECEIVED
    # ========================================================

    received_cards = ""

    for document in received_documents:

        received_cards += f"""
<div class="document-card">

<div class="document-title">
{esc(document.get("title"))}
</div>

<p>
{esc(document.get("description"))}
</p>

<div class="document-meta">

<b>From:</b>
KOJA Admin
<br>

<b>File:</b>
{esc(document.get("original_name"))}
<br>

<b>Type:</b>
{document_type_label(document.get("original_name"))}
<br>

<b>Size:</b>
{format_size(document.get("size"))}
<br>

<b>Received:</b>
{esc(document.get("created_at"))}

</div>

<br>

<a
class="btn"
href="/document/{document['id']}"
>
Download
</a>

</div>
"""

    if not received_cards:

        received_cards = """
<div class="card empty">

No documents have been received
from KOJA Admin.

</div>
"""

    # ========================================================
    # SENT
    # ========================================================

    sent_cards = ""

    for document in sent_documents:

        sent_cards += f"""
<div class="document-card">

<div class="document-title">
{esc(document.get("title"))}
</div>

<p>
{esc(document.get("description"))}
</p>

<div class="document-meta">

<b>To:</b>
KOJA Admin
<br>

<b>File:</b>
{esc(document.get("original_name"))}
<br>

<b>Type:</b>
{document_type_label(document.get("original_name"))}
<br>

<b>Size:</b>
{format_size(document.get("size"))}
<br>

<b>Sent:</b>
{esc(document.get("created_at"))}

</div>

<br>

<span class="badge green">
Delivered to KOJA
</span>

<br><br>

<a
class="btn dark"
href="/document/{document['id']}"
>
Access My Copy
</a>

</div>
"""

    if not sent_cards:

        sent_cards = """
<div class="card empty">

You have not sent any documents
to KOJA Admin yet.

</div>
"""

    return page(
        f"""
<h1>
Document Centre
</h1>

<div class="info">

Your documents are stored in KOJA's
private document storage. Only the
authorized student and KOJA Admin
can access the corresponding files.

</div>

<br>

<div class="card">

<h2>
Send Document to KOJA Admin
</h2>

<form
method="post"
enctype="multipart/form-data"
>

{csrf_input()}

<label>
Document Title
</label>

<input
name="title"
required
maxlength="300"
placeholder="Example: Assignment 1"
/>

<label>
Category
</label>

<select
name="category"
>

<option>
Academic
</option>

<option>
Assignment
</option>

<option>
Application
</option>

<option>
Report
</option>

<option>
Other
</option>

</select>

<label>
Description
</label>

<textarea
name="description"
maxlength="4000"
placeholder="Describe the document..."
></textarea>

<label>
File
</label>

<input
type="file"
name="file"
required
>

<small>
Maximum size: 10 MB.
</small>

<br><br>

<button
class="btn"
type="submit"
>
Send Document
</button>

</form>

</div>

<br>

<form
method="get"
class="searchbar"
>

<input
name="q"
value="{esc(search)}"
placeholder="Search my documents..."
>

<button
class="btn dark"
type="submit"
>
Search
</button>

</form>

<h2>
Inbox — From KOJA Admin
</h2>

{received_cards}

<br>

<h2>
Sent — To KOJA Admin
</h2>

{sent_cards}
""",

        "Document Centre"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    profiles = rest_get(
        "profiles"
    )

    questions = rest_get(
        "questions"
    )

    documents = rest_get(
        "documents"
    )

    waiting = sum(
        not bool(
            q.get("answer")
        )
        for q in questions
    )

    answered = (
        len(questions)
        - waiting
    )

    student_documents = [
        d
        for d in documents
        if d.get("direction")
        == "student_to_admin"
    ]

    admin_documents_sent = [
        d
        for d in documents
        if d.get("direction")
        == "admin_to_student"
    ]

    return page(
        f"""
<h1>
Admin Dashboard
</h1>

<div class="grid">

<div class="card">

<h3>
Users
</h3>

<div class="stat">
{len(profiles)}
</div>

</div>

<div class="card">

<h3>
Questions
</h3>

<div class="stat">
{len(questions)}
</div>

</div>

<div class="card">

<h3>
Answered
</h3>

<div class="stat">
{answered}
</div>

</div>

<div class="card">

<h3>
Waiting
</h3>

<div class="stat">
{waiting}
</div>

</div>

<div class="card">

<h3>
Student Documents
</h3>

<div class="stat">
{len(student_documents)}
</div>

</div>

<div class="card">

<h3>
Sent Documents
</h3>

<div class="stat">
{len(admin_documents_sent)}
</div>

</div>

</div>

<br>

<div class="card">

<h2>
Document Centre
</h2>

<div class="actions"
style="justify-content:flex-start">

<a
class="btn"
href="/admin/documents"
>
Open Documents
</a>

<a
class="btn dark"
href="/admin/questions"
>
Manage Questions
</a>

<a
class="btn"
href="/admin/users"
>
Users
</a>

<a
class="btn"
href="/admin/logs"
>
Logs
</a>

</div>

</div>

<br>

<div class="card future">

<h2>
KOJA Business Foundation
</h2>

<p>
The current platform is deliberately
structured so that revenue features
can be added later without changing
the student/admin document architecture.
</p>

<div class="mini-grid">

<div class="mini-stat">
<strong>
Free
</strong>
Basic learning access
</div>

<div class="mini-stat">
<strong>
Premium
</strong>
Paid resources
</div>

<div class="mini-stat">
<strong>
Institution
</strong>
School services
</div>

<div class="mini-stat">
<strong>
Subscriptions
</strong>
Recurring revenue
</div>

</div>

</div>
""",

        "Admin Dashboard"
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route(
    "/admin/questions"
)
@admin_required
def admin_questions():

    questions = rest_get(
        "questions",
        {
            "order":
                "created_at.desc"
        }
    )

    rows = ""

    for q in questions:

        status = (
            "Answered"
            if q.get("answer")
            else "Waiting"
        )

        badge = (
            "green"
            if q.get("answer")
            else "orange"
        )

        rows += f"""
<tr>

<td>
{esc(q.get("student_name"))}
</td>

<td>
{esc(q.get("question"))}
</td>

<td>

<span class="badge {badge}">
{status}
</span>

</td>

<td>
{esc(q.get("created_at"))}
</td>

<td>

<a
class="btn"
href="/admin/question/{q['id']}"
>
Open
</a>

</td>

</tr>
"""

    if not rows:

        rows = """
<tr>

<td
colspan="5"
class="empty"
>
No questions yet.
</td>

</tr>
"""

    return page(
        f"""
<h1>
Questions
</h1>

<div class="tablewrap">

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
Submitted
</th>

<th>
Action
</th>

</tr>

{rows}

</table>

</div>
""",

        "Admin Questions"
    )


# ============================================================
# ADMIN QUESTION
# ============================================================

@app.route(
    "/admin/question/<question_id>",
    methods=["GET", "POST"]
)
@admin_required
@limiter.limit(
    "60 per hour",
    methods=["POST"]
)
def admin_question(
    question_id
):

    profile = current_profile()

    questions = rest_get(
        "questions",
        {
            "id":
                f"eq.{question_id}",

            "limit":
                "1"
        }
    )

    if not questions:
        abort(404)

    question = questions[0]

    if request.method == "POST":

        check_csrf()

        answer = request.form.get(
            "answer",
            ""
        ).strip()

        if not answer:

            flash(
                "Answer cannot be empty.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_question",
                    question_id=question_id
                )
            )

        if len(answer) > 30000:

            flash(
                "Answer is too long.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_question",
                    question_id=question_id
                )
            )

        updated = rest_update(
            "questions",
            {
                "id":
                    f"eq.{question_id}"
            },
            {
                "answer":
                    answer,

                "answer_by":
                    profile.get(
                        "name",
                        "Admin"
                    ),

                "answered_at":
                    now_iso()
            }
        )

        if updated is None:

            flash(
                "Unable to save the answer.",
                "error"
            )

        else:

            answer_file = request.files.get(
                "answer_file"
            )

            if (
                answer_file
                and answer_file.filename
            ):

                try:

                    info = upload_private_file(
                        answer_file,
                        f"answers/{question_id}"
                    )

                    recorded = rest_insert(
                        "question_files",
                        {
                            "question_id":
                                question_id,

                            "original_name":
                                info[
                                    "original_name"
                                ],

                            "storage_path":
                                info[
                                    "storage_path"
                                ],

                            "size":
                                info[
                                    "size"
                                ],

                            "file_type":
                                "answer"
                        },
                        returning=False
                    )

                    if not recorded:

                        delete_private_file(
                            info[
                                "storage_path"
                            ]
                        )

                        flash(
                            "Answer saved, "
                            "but attachment "
                            "could not be recorded.",
                            "warning"
                        )

                except Exception:

                    logger.exception(
                        "Answer attachment failed"
                    )

                    flash(
                        "Answer saved, "
                        "but attachment failed.",
                        "warning"
                    )

            write_log(
                "Question answered",
                "Questions",
                "INFO",
                question_id,
                profile["id"]
            )

            flash(
                "Answer saved successfully.",
                "success"
            )

        return redirect(
            url_for(
                "admin_question",
                question_id=question_id
            )
        )

    files = rest_get(
        "question_files",
        {
            "question_id":
                f"eq.{question_id}",

            "order":
                "created_at.asc"
        }
    )

    file_links = ""

    for file in files:

        file_links += f"""
<div style="margin:7px 0">

📎

<a
href="/question-file/{file['id']}"
>
{esc(file.get("original_name"))}
</a>

<span class="badge">
{esc(file.get("file_type"))}
</span>

</div>
"""

    status = (
        "Answered"
        if question.get("answer")
        else "Waiting"
    )

    return page(
        f"""
<h1>
Question
</h1>

<div class="card">

<p>

<strong>
Student:
</strong>

{esc(question.get("student_name"))}

</p>

<p>

<strong>
Date:
</strong>

{esc(question.get("created_at"))}

</p>

<p>

<strong>
Status:
</strong>

<span class="badge">
{status}
</span>

</p>

<hr>

<h3>
Question
</h3>

<div class="question-box">

{esc(question.get("question"))}

</div>

<br>

{file_links}

</div>

<br>

<form
method="post"
enctype="multipart/form-data"
>

{csrf_input()}

<h2>
Answer
</h2>

<textarea
name="answer"
required
maxlength="30000"
>{esc(question.get("answer"))}</textarea>

<label>
Answer Attachment
</label>

<input
type="file"
name="answer_file"
>

<br><br>

<button
class="btn green"
type="submit"
>
Save Answer
</button>

</form>
""",

        "Answer Question"
    )


# ============================================================
# ADMIN DOCUMENT CENTRE
#
# INBOX FROM STUDENTS
# OUTBOX TO STUDENTS
# ============================================================

@app.route(
    "/admin/documents",
    methods=["GET", "POST"]
)
@admin_required
@limiter.limit(
    "30 per hour",
    methods=["POST"]
)
def admin_documents():

    profile = current_profile()

    admin_id = profile["id"]

    # ========================================================
    # ADMIN SENDS DOCUMENT
    # ========================================================

    if request.method == "POST":

        check_csrf()

        recipient_id = request.form.get(
            "recipient_id",
            ""
        ).strip()

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        category = request.form.get(
            "category",
            "Academic"
        ).strip()

        uploaded = request.files.get(
            "file"
        )

        if not recipient_id:

            flash(
                "Please select a student.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        if not title:

            flash(
                "Document title is required.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        if not uploaded or not uploaded.filename:

            flash(
                "Please select a document.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        students = rest_get(
            "profiles",
            {
                "id":
                    f"eq.{recipient_id}",

                "role":
                    "eq.student",

                "limit":
                    "1"
            }
        )

        if not students:

            flash(
                "Selected student was not found.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        student = students[0]

        storage_path = None

        try:

            info = upload_private_file(
                uploaded,
                f"documents/admin/{recipient_id}"
            )

            storage_path = (
                info["storage_path"]
            )

            created = rest_insert(
                "documents",
                {
                    "direction":
                        "admin_to_student",

                    "sender_id":
                        admin_id,

                    "sender_name":
                        profile.get(
                            "name",
                            "KOJA Admin"
                        ),

                    "recipient_id":
                        student["id"],

                    "recipient_name":
                        student.get(
                            "name",
                            ""
                        ),

                    "title":
                        title,

                    "description":
                        description,

                    "original_name":
                        info[
                            "original_name"
                        ],

                    "storage_path":
                        storage_path,

                    "size":
                        info["size"]
                }
            )

            if not created:

                delete_private_file(
                    storage_path
                )

                flash(
                    "The document could not be saved.",
                    "error"
                )

                return redirect(
                    url_for(
                        "admin_documents"
                    )
                )

            write_log(
                "Admin sent document",
                "Documents",
                "INFO",
                (
                    f"{category}: "
                    f"{title} -> "
                    f"{student.get('email', '')}"
                ),
                admin_id
            )

            flash(
                "Document sent successfully. "
                "The student can now access it.",
                "success"
            )

        except ValueError as error:

            flash(
                str(error),
                "error"
            )

        except Exception:

            logger.exception(
                "Admin document upload failed"
            )

            if storage_path:

                delete_private_file(
                    storage_path
                )

            flash(
                "Document upload failed.",
                "error"
            )

        return redirect(
            url_for(
                "admin_documents"
            )
        )

    # ========================================================
    # SEARCH
    # ========================================================

    search = request.args.get(
        "q",
        ""
    ).strip().lower()

    # ========================================================
    # STUDENTS
    # ========================================================

    students = rest_get(
        "profiles",
        {
            "role":
                "eq.student",

            "order":
                "name.asc"
        }
    )

    options = ""

    for student in students:

        options += f"""
<option
value="{esc(student['id'])}"
>
{esc(student.get("name"))}
—
{esc(student.get("email"))}
</option>
"""

    # ========================================================
    # INBOX
    # ========================================================

    received_documents = rest_get(
        "documents",
        {
            "direction":
                "eq.student_to_admin",

            "order":
                "created_at.desc"
        }
    )

    # ========================================================
    # OUTBOX
    # ========================================================

    sent_documents = rest_get(
        "documents",
        {
            "direction":
                "eq.admin_to_student",

            "sender_id":
                f"eq.{admin_id}",

            "order":
                "created_at.desc"
        }
    )

    def matches(document):

        if not search:
            return True

        text = " ".join([
            str(
                document.get(
                    "title",
                    ""
                )
            ),

            str(
                document.get(
                    "description",
                    ""
                )
            ),

            str(
                document.get(
                    "original_name",
                    ""
                )
            ),

            str(
                document.get(
                    "sender_name",
                    ""
                )
            ),

            str(
                document.get(
                    "recipient_name",
                    ""
                )
            )
        ]).lower()

        return search in text

    received_documents = [
        d
        for d in received_documents
        if matches(d)
    ]

    sent_documents = [
        d
        for d in sent_documents
        if matches(d)
    ]

    # ========================================================
    # RECEIVED CARDS
    # ========================================================

    received_rows = ""

    for document in received_documents:

        received_rows += f"""
<tr>

<td>
{esc(document.get("sender_name"))}
</td>

<td>
{esc(document.get("title"))}
</td>

<td>
{esc(document.get("original_name"))}
</td>

<td>
{format_size(document.get("size"))}
</td>

<td>
{esc(document.get("created_at"))}
</td>

<td>

<span class="badge orange">
Received
</span>

</td>

<td>

<a
class="btn"
href="/document/{document['id']}"
>
Download
</a>

</td>

</tr>
"""

    if not received_rows:

        received_rows = """
<tr>

<td
colspan="7"
class="empty"
>
No documents received from students.
</td>

</tr>
"""

    # ========================================================
    # SENT ROWS
    # ========================================================

    sent_rows = ""

    for document in sent_documents:

        sent_rows += f"""
<tr>

<td>
{esc(document.get("recipient_name"))}
</td>

<td>
{esc(document.get("title"))}
</td>

<td>
{esc(document.get("original_name"))}
</td>

<td>
{format_size(document.get("size"))}
</td>

<td>
{esc(document.get("created_at"))}
</td>

<td>

<span class="badge green">
Sent
</span>

</td>

<td>

<a
class="btn dark"
href="/document/{document['id']}"
>
Access
</a>

</td>

</tr>
"""

    if not sent_rows:

        sent_rows = """
<tr>

<td
colspan="7"
class="empty"
>
No documents sent to students yet.
</td>

</tr>
"""

    return page(
        f"""
<h1>
Document Centre
</h1>

<div class="info">

This is the administrator's private
document inbox and outbox.

Documents sent by students appear in
the administrator inbox.

Documents sent by the administrator
appear in the selected student's inbox.

</div>

<br>

<div class="card">

<h2>
Send Document to Student
</h2>

<form
method="post"
enctype="multipart/form-data"
>

{csrf_input()}

<label>
Student
</label>

<select
name="recipient_id"
required
>

<option value="">
Select student
</option>

{options}

</select>

<label>
Document Title
</label>

<input
name="title"
required
maxlength="300"
placeholder="Example: Biology Notes"
>

<label>
Category
</label>

<select
name="category"
>

<option>
Academic
</option>

<option>
Assignment
</option>

<option>
Study Material
</option>

<option>
Notice
</option>

<option>
Application
</option>

<option>
Other
</option>

</select>

<label>
Description
</label>

<textarea
name="description"
maxlength="4000"
placeholder="Describe the document..."
></textarea>

<label>
Document
</label>

<input
type="file"
name="file"
required
>

<small>
Maximum file size: 10 MB.
</small>

<br><br>

<button
class="btn"
type="submit"
>
Send to Student
</button>

</form>

</div>

<br>

<form
method="get"
class="searchbar"
>

<input
name="q"
value="{esc(search)}"
placeholder="Search documents, students or filenames..."
>

<button
class="btn dark"
type="submit"
>
Search
</button>

</form>

<h2>
Inbox — Documents Received From Students
</h2>

<div class="tablewrap">

<table>

<tr>

<th>
Student
</th>

<th>
Title
</th>

<th>
File
</th>

<th>
Size
</th>

<th>
Received
</th>

<th>
Status
</th>

<th>
Action
</th>

</tr>

{received_rows}

</table>

</div>

<br><br>

<h2>
Outbox — Documents Sent To Students
</h2>

<div class="tablewrap">

<table>

<tr>

<th>
Student
</th>

<th>
Title
</th>

<th>
File
</th>

<th>
Size
</th>

<th>
Sent
</th>

<th>
Status
</th>

<th>
Action
</th>

</tr>

{sent_rows}

</table>

</div>
""",

        "Document Centre"
    )


# ============================================================
# SECURE DOCUMENT DOWNLOAD
# ============================================================

@app.route(
    "/document/<document_id>"
)
@login_required
def document_download(
    document_id
):

    profile = current_profile()

    if not profile:
        abort(403)

    documents = rest_get(
        "documents",
        {
            "id":
                f"eq.{document_id}",

            "limit":
                "1"
        }
    )

    if not documents:
        abort(404)

    document = documents[0]

    # ========================================================
    # AUTHORIZATION
    # ========================================================

    is_admin = (
        profile.get("role")
        == "admin"
    )

    is_sender = (
        document.get("sender_id")
        == profile.get("id")
    )

    is_recipient = (
        document.get("recipient_id")
        == profile.get("id")
    )

    if not (
        is_admin
        or is_sender
        or is_recipient
    ):

        write_log(
            "Unauthorized document access blocked",
            "Security",
            "WARNING",
            document_id,
            profile["id"]
        )

        abort(403)

    content = download_private_file(
        document.get(
            "storage_path"
        )
    )

    if content is None:

        abort(404)

    write_log(
        "Document downloaded",
        "Documents",
        "INFO",
        (
            f"{document.get('title')} | "
            f"{document.get('original_name')}"
        ),
        profile["id"]
    )

    return send_file(
        io.BytesIO(content),

        as_attachment=True,

        download_name=safe_filename(
            document.get(
                "original_name",
                "document"
            )
        ),

        mimetype=(
            "application/octet-stream"
        )
    )


# ============================================================
# QUESTION FILE DOWNLOAD
# ============================================================

@app.route(
    "/question-file/<file_id>"
)
@login_required
def question_file(
    file_id
):

    profile = current_profile()

    if not profile:
        abort(403)

    files = rest_get(
        "question_files",
        {
            "id":
                f"eq.{file_id}",

            "limit":
                "1"
        }
    )

    if not files:
        abort(404)

    file = files[0]

    questions = rest_get(
        "questions",
        {
            "id":
                f"eq.{file['question_id']}",

            "limit":
                "1"
        }
    )

    if not questions:
        abort(404)

    question = questions[0]

    allowed = (
        profile.get("role")
        == "admin"

        or question.get(
            "student_id"
        )
        == profile.get("id")
    )

    if not allowed:

        write_log(
            "Unauthorized question file access blocked",
            "Security",
            "WARNING",
            file_id,
            profile["id"]
        )

        abort(403)

    content = download_private_file(
        file.get(
            "storage_path"
        )
    )

    if content is None:
        abort(404)

    write_log(
        "Question file downloaded",
        "Files",
        "INFO",
        file.get(
            "original_name",
            ""
        ),
        profile["id"]
    )

    return send_file(
        io.BytesIO(content),

        as_attachment=True,

        download_name=safe_filename(
            file.get(
                "original_name",
                "download"
            )
        ),

        mimetype="application/octet-stream"
    )


# ============================================================
# ADMIN USERS
# ============================================================

@app.route(
    "/admin/users"
)
@admin_required
def admin_users():

    profiles = rest_get(
        "profiles",
        {
            "order":
                "created_at.desc"
        }
    )

    rows = ""

    for profile in profiles:

        role = profile.get(
            "role"
        )

        badge = (
            "green"
            if role == "admin"
            else ""
        )

        rows += f"""
<tr>

<td>
{esc(profile.get("name"))}
</td>

<td>
{esc(profile.get("email"))}
</td>

<td>

<span class="badge {badge}">
{esc(role)}
</span>

</td>

<td>
{esc(profile.get("created_at"))}
</td>

</tr>
"""

    if not rows:

        rows = """
<tr>

<td
colspan="4"
class="empty"
>
No users found.
</td>

</tr>
"""

    return page(
        f"""
<h1>
Users
</h1>

<div class="tablewrap">

<table>

<tr>

<th>
Name
</th>

<th>
Email
</th>

<th>
Role
</th>

<th>
Created
</th>

</tr>

{rows}

</table>

</div>
""",

        "Users"
    )


# ============================================================
# ADMIN LOGS
# ============================================================

@app.route(
    "/admin/logs"
)
@admin_required
def admin_logs():

    logs = rest_get(
        "logs",
        {
            "order":
                "created_at.desc",

            "limit":
                "500"
        }
    )

    rows = ""

    for log in logs:

        rows += f"""
<tr>

<td>
{esc(log.get("created_at"))}
</td>

<td>
{esc(log.get("event"))}
</td>

<td>
{esc(log.get("category"))}
</td>

<td>
{esc(log.get("level"))}
</td>

<td>
{esc(log.get("details"))}
</td>

</tr>
"""

    if not rows:

        rows = """
<tr>

<td
colspan="5"
class="empty"
>
No logs yet.
</td>

</tr>
"""

    return page(
        f"""
<h1>
System Logs
</h1>

<div class="card">

<p>
Administrator-only audit trail.
</p>

<div class="notice">

Important activities such as logins,
question submissions, answers,
document uploads, downloads and
security events are recorded here.

</div>

</div>

<br>

<div class="tablewrap">

<table>

<tr>

<th>
Date
</th>

<th>
Event
</th>

<th>
Category
</th>

<th>
Level
</th>

<th>
Details
</th>

</tr>

{rows}

</table>

</div>
""",

        "System Logs"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route(
    "/health"
)
def health():

    return {
        "status":
            "ok",

        "application":
            "KOJA AFRICA",

        "database":
            "Supabase REST",

        "storage":
            SUPABASE_BUCKET,

        "storage_private":
            True,

        "version":
            "professional-foundation"
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    return page(
        """
<div class="card"
style="text-align:center">

<h1>
403
</h1>

<h2>
Access Denied
</h2>

<p>
You do not have permission
to access this resource.
</p>

<a
class="btn"
href="/"
>
Return Home
</a>

</div>
""",

        "Access Denied"

    ), 403


@app.errorhandler(404)
def not_found(error):

    return page(
        """
<div class="card"
style="text-align:center">

<h1>
404
</h1>

<h2>
Page Not Found
</h2>

<a
class="btn"
href="/"
>
Return Home
</a>

</div>
""",

        "Not Found"

    ), 404


@app.errorhandler(413)
def too_large(error):

    flash(
        "File too large. Maximum size is 10 MB.",
        "error"
    )

    return redirect(
        request.referrer
        or url_for("home")
    )


@app.errorhandler(429)
def too_many_requests(error):

    return page(
        """
<div class="card"
style="text-align:center">

<h1>
429
</h1>

<h2>
Too Many Requests
</h2>

<p>
Please wait a moment and try again.
</p>

<a
class="btn"
href="/"
>
Return Home
</a>

</div>
""",

        "Too Many Requests"

    ), 429


@app.errorhandler(400)
def bad_request(error):

    description = getattr(
        error,
        "description",
        "Bad request."
    )

    return page(
        f"""
<div class="card"
style="text-align:center">

<h1>
400
</h1>

<h2>
Bad Request
</h2>

<p>
{esc(description)}
</p>

<a
class="btn"
href="/"
>
Return Home
</a>

</div>
""",

        "Bad Request"

    ), 400


@app.errorhandler(500)
def internal_error(error):

    logger.exception(
        "Internal server error"
    )

    return page(
        """
<div class="card"
style="text-align:center">

<h1>
500
</h1>

<h2>
Server Error
</h2>

<p>
KOJA AFRICA encountered an
unexpected server error.
</p>

<a
class="btn"
href="/"
>
Return Home
</a>

</div>
""",

        "Server Error"

    ), 500


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

        debug=False
    )
