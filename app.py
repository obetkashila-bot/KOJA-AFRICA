# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# SINGLE-FILE FLASK APPLICATION
#
# Flask + Supabase REST API + Supabase Private Storage
# Flutterwave Standard Payments
# ReportLab PDF generation
#
# Designed for:
#   Render
#   Railway
#   VPS
#   Pydroid 3
#
# NO SQLITE
# NO psycopg
# NO psycopg2
#
# ============================================================

import os
import io
import uuid
import html
import mimetypes
import secrets
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from functools import wraps

import requests

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
    Response,
    render_template_string,
    jsonify
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle
)
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)


# ============================================================
# APPLICATION
# ============================================================

APP_NAME = "KOJA AFRICA"

APP_TAGLINE = (
    "Assignment Questions • Academic Answers • Learning Resources"
)


# ============================================================
# ENVIRONMENT HELPERS
# ============================================================

def env(name, default=""):
    value = os.environ.get(name, default)
    return str(value).strip()


# ============================================================
# SUPABASE
# ============================================================

SUPABASE_URL = env("SUPABASE_URL").rstrip("/")

SUPABASE_SERVICE_KEY = env(
    "SUPABASE_SERVICE_KEY"
)

if not SUPABASE_SERVICE_KEY:
    SUPABASE_SERVICE_KEY = env(
        "SUPABASE_SERVICE_ROLE_KEY"
    )

STORAGE_BUCKET = env(
    "KOJA_STORAGE_BUCKET",
    "koja-assignments"
)


# ============================================================
# FLUTTERWAVE
# ============================================================

FLW_SECRET_KEY = env(
    "FLW_SECRET_KEY"
)

FLW_SECRET_HASH = env(
    "FLW_SECRET_HASH"
)

FLW_BASE_URL = (
    "https://api.flutterwave.com/v3"
)

PAYMENT_CURRENCY = env(
    "KOJA_PAYMENT_CURRENCY",
    "ZMW"
).upper()

DEFAULT_ANSWER_PRICE = env(
    "KOJA_PAYMENT_AMOUNT",
    "10.00"
)


# ============================================================
# PUBLIC URL
# ============================================================

KOJA_BASE_URL = env(
    "KOJA_BASE_URL"
).rstrip("/")


# ============================================================
# SECURITY
# ============================================================

SECRET_KEY = env(
    "KOJA_SECRET_KEY"
)

if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(48)


# ============================================================
# SERVER
# ============================================================

HOST = env(
    "HOST",
    "0.0.0.0"
)

try:
    PORT = int(
        env(
            "PORT",
            "5000"
        )
    )
except ValueError:
    PORT = 5000


# ============================================================
# HTTPS
# ============================================================

HTTPS_ENABLED = (
    env(
        "KOJA_HTTPS",
        "0"
    ) == "1"
)


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = SECRET_KEY

app.config["MAX_CONTENT_LENGTH"] = (
    10 * 1024 * 1024
)

app.config["SESSION_COOKIE_HTTPONLY"] = True

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["SESSION_COOKIE_SECURE"] = HTTPS_ENABLED


# ============================================================
# AFRICAN COUNTRIES
# ============================================================

AFRICAN_COUNTRIES = [
    "Algeria",
    "Angola",
    "Benin",
    "Botswana",
    "Burkina Faso",
    "Burundi",
    "Cabo Verde",
    "Cameroon",
    "Central African Republic",
    "Chad",
    "Comoros",
    "Democratic Republic of the Congo",
    "Republic of the Congo",
    "Côte d'Ivoire",
    "Djibouti",
    "Egypt",
    "Equatorial Guinea",
    "Eritrea",
    "Eswatini",
    "Ethiopia",
    "Gabon",
    "Gambia",
    "Ghana",
    "Guinea",
    "Guinea-Bissau",
    "Kenya",
    "Lesotho",
    "Liberia",
    "Libya",
    "Madagascar",
    "Malawi",
    "Mali",
    "Mauritania",
    "Mauritius",
    "Morocco",
    "Mozambique",
    "Namibia",
    "Niger",
    "Nigeria",
    "Rwanda",
    "São Tomé and Príncipe",
    "Senegal",
    "Seychelles",
    "Sierra Leone",
    "Somalia",
    "South Africa",
    "South Sudan",
    "Sudan",
    "Tanzania",
    "Togo",
    "Tunisia",
    "Uganda",
    "Zambia",
    "Zimbabwe"
]


# ============================================================
# SUBJECTS
# ============================================================

SUBJECTS = [
    "Mathematics",
    "English",
    "Chemistry",
    "Biology",
    "Physics",
    "Computer Science",
    "Information Technology",
    "Engineering",
    "Agriculture",
    "Business",
    "Accounting",
    "Economics",
    "Education",
    "Geography",
    "History",
    "Civic Education",
    "Law",
    "Medicine",
    "Nursing",
    "Social Sciences",
    "Environmental Science",
    "Other"
]


# ============================================================
# FILE TYPES
# ============================================================

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "pdf",
    "doc",
    "docx",
    "txt",
    "ppt",
    "pptx",
    "xls",
    "xlsx"
}


# ============================================================
# DATABASE
# ============================================================

def database_ready():

    return bool(
        SUPABASE_URL
        and SUPABASE_SERVICE_KEY
        and SUPABASE_URL.startswith("https://")
    )


def db_headers():

    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": (
            "Bearer "
            + SUPABASE_SERVICE_KEY
        ),
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


def rest_url(table):

    return (
        SUPABASE_URL
        + "/rest/v1/"
        + table
    )


def db_select(
    table,
    params=None
):

    if not database_ready():
        raise RuntimeError(
            "Supabase is not configured."
        )

    response = requests.get(
        rest_url(table),
        headers=db_headers(),
        params=params or {},
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            "Database SELECT failed: "
            + response.text
        )

    if not response.text:
        return []

    return response.json()


def db_insert(
    table,
    data
):

    if not database_ready():
        raise RuntimeError(
            "Supabase is not configured."
        )

    headers = db_headers()

    headers["Prefer"] = (
        "return=representation"
    )

    response = requests.post(
        rest_url(table),
        headers=headers,
        json=data,
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            "Database INSERT failed: "
            + response.text
        )

    if not response.text:
        return []

    return response.json()


def db_update(
    table,
    filters,
    data
):

    if not database_ready():
        raise RuntimeError(
            "Supabase is not configured."
        )

    params = {}

    for key, value in filters.items():

        params[key] = (
            "eq."
            + str(value)
        )

    headers = db_headers()

    headers["Prefer"] = (
        "return=representation"
    )

    response = requests.patch(
        rest_url(table),
        headers=headers,
        params=params,
        json=data,
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            "Database UPDATE failed: "
            + response.text
        )

    if not response.text:
        return []

    return response.json()


def db_delete(
    table,
    filters
):

    if not database_ready():
        raise RuntimeError(
            "Supabase is not configured."
        )

    params = {}

    for key, value in filters.items():

        params[key] = (
            "eq."
            + str(value)
        )

    response = requests.delete(
        rest_url(table),
        headers=db_headers(),
        params=params,
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            "Database DELETE failed: "
            + response.text
        )

    return True


# ============================================================
# TIME
# ============================================================

def current_time():

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# MONEY
# ============================================================

def decimal_price(value):

    try:

        amount = Decimal(
            str(value)
        )

        if amount <= 0:
            raise InvalidOperation

        return amount.quantize(
            Decimal("0.01")
        )

    except Exception:

        return Decimal("10.00")


def money(value):

    return format(
        decimal_price(value),
        ".2f"
    )


# ============================================================
# USERS
# ============================================================

def get_user_by_username(
    username,
    role=None
):

    params = {
        "username": "eq." + username,
        "select": "*",
        "limit": "1"
    }

    if role:
        params["role"] = (
            "eq." + role
        )

    rows = db_select(
        "users",
        params
    )

    return (
        rows[0]
        if rows
        else None
    )


def get_user_by_id(
    user_id
):

    rows = db_select(
        "users",
        {
            "id": (
                "eq."
                + str(user_id)
            ),
            "select": "*",
            "limit": "1"
        }
    )

    return (
        rows[0]
        if rows
        else None
    )


def email_exists(
    email
):

    rows = db_select(
        "users",
        {
            "email": (
                "eq."
                + email
            ),
            "select": "id",
            "limit": "1"
        }
    )

    return bool(rows)


# ============================================================
# QUESTIONS
# ============================================================

def get_question(
    question_id
):

    rows = db_select(
        "questions",
        {
            "id": (
                "eq."
                + str(question_id)
            ),
            "select": "*",
            "limit": "1"
        }
    )

    return (
        rows[0]
        if rows
        else None
    )


def get_student_question(
    question_id,
    user_id
):

    rows = db_select(
        "questions",
        {
            "id": (
                "eq."
                + str(question_id)
            ),
            "user_id": (
                "eq."
                + str(user_id)
            ),
            "select": "*",
            "limit": "1"
        }
    )

    return (
        rows[0]
        if rows
        else None
    )


# ============================================================
# ANSWERS
# ============================================================

def get_answer(
    question_id
):

    rows = db_select(
        "answers",
        {
            "question_id": (
                "eq."
                + str(question_id)
            ),
            "select": "*",
            "limit": "1"
        }
    )

    return (
        rows[0]
        if rows
        else None
    )


# ============================================================
# PAYMENTS
# ============================================================

def get_payment_by_tx_ref(
    tx_ref
):

    rows = db_select(
        "payments",
        {
            "tx_ref": (
                "eq."
                + tx_ref
            ),
            "select": "*",
            "limit": "1"
        }
    )

    return (
        rows[0]
        if rows
        else None
    )


def get_paid_payment(
    student_id,
    question_id
):

    rows = db_select(
        "payments",
        {
            "student_id": (
                "eq."
                + str(student_id)
            ),
            "question_id": (
                "eq."
                + str(question_id)
            ),
            "status": "eq.paid",
            "select": "*",
            "order": "id.desc",
            "limit": "1"
        }
    )

    return (
        rows[0]
        if rows
        else None
    )


def has_paid_for_pdf(
    student_id,
    question_id
):

    return bool(
        get_paid_payment(
            student_id,
            question_id
        )
    )


# ============================================================
# STORAGE
# ============================================================

def allowed_file(
    filename
):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = (
        filename
        .rsplit(".", 1)[1]
        .lower()
    )

    return (
        extension
        in ALLOWED_EXTENSIONS
    )


def storage_upload_stream(
    stream,
    storage_path,
    original_name,
    content_type
):

    if not database_ready():

        raise RuntimeError(
            "Supabase is not configured."
        )

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + STORAGE_BUCKET
        + "/"
        + storage_path
    )

    headers = {
        "Authorization": (
            "Bearer "
            + SUPABASE_SERVICE_KEY
        ),
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": content_type,
        "x-upsert": "false"
    }

    response = requests.post(
        url,
        headers=headers,
        data=stream,
        timeout=120
    )

    if not response.ok:

        raise RuntimeError(
            "Storage upload failed: "
            + response.text
        )

    return {
        "original_name": original_name,
        "storage_path": storage_path,
        "content_type": content_type
    }


def storage_upload(
    file_storage,
    folder
):

    if (
        not file_storage
        or not file_storage.filename
    ):
        return None

    original = secure_filename(
        file_storage.filename
    )

    if not original:
        raise ValueError(
            "Invalid filename."
        )

    if not allowed_file(original):
        raise ValueError(
            "Unsupported file type."
        )

    extension = ""

    if "." in original:

        extension = (
            "."
            + original
            .rsplit(".", 1)[1]
            .lower()
        )

    storage_path = (
        folder
        + "/"
        + uuid.uuid4().hex
        + extension
    )

    content_type = (
        file_storage.mimetype
        or mimetypes.guess_type(
            original
        )[0]
        or "application/octet-stream"
    )

    return storage_upload_stream(
        file_storage.stream,
        storage_path,
        original,
        content_type
    )


def storage_upload_bytes(
    data,
    storage_path,
    original_name,
    content_type="application/pdf"
):

    return storage_upload_stream(
        io.BytesIO(data),
        storage_path,
        original_name,
        content_type
    )


def storage_get(
    path
):

    if not path:
        return None

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + STORAGE_BUCKET
        + "/"
        + path
    )

    try:

        response = requests.get(
            url,
            headers={
                "Authorization": (
                    "Bearer "
                    + SUPABASE_SERVICE_KEY
                ),
                "apikey": SUPABASE_SERVICE_KEY
            },
            timeout=120
        )

        if response.ok:
            return response

    except Exception:
        pass

    return None


def storage_delete(
    path
):

    if not path:
        return

    if not database_ready():
        return

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + STORAGE_BUCKET
        + "/"
        + path
    )

    try:

        requests.delete(
            url,
            headers={
                "Authorization": (
                    "Bearer "
                    + SUPABASE_SERVICE_KEY
                ),
                "apikey": SUPABASE_SERVICE_KEY
            },
            timeout=30
        )

    except Exception:
        pass


def send_storage_file(
    path,
    filename
):

    response = storage_get(path)

    if response is None:
        abort(404)

    safe_filename = (
        secure_filename(filename)
        or "download"
    )

    content_type = (
        response.headers.get(
            "Content-Type"
        )
        or "application/octet-stream"
    )

    return Response(
        response.content,
        headers={
            "Content-Type": content_type,
            "Content-Disposition": (
                'attachment; filename="'
                + safe_filename
                + '"'
            )
        }
    )


# ============================================================
# PDF
# ============================================================

def build_answer_pdf(
    question,
    answer
):

    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=45,
        bottomMargin=45
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "KojaTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=20,
        leading=25,
        spaceAfter=15
    )

    heading_style = ParagraphStyle(
        "KojaHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=18,
        spaceBefore=10,
        spaceAfter=7
    )

    body_style = ParagraphStyle(
        "KojaBody",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=17,
        spaceAfter=9
    )

    story = []

    story.append(
        Paragraph(
            "KOJA AFRICA",
            title_style
        )
    )

    story.append(
        Paragraph(
            "Academic Answer",
            heading_style
        )
    )

    story.append(
        Paragraph(
            "<b>Subject:</b> "
            + html.escape(
                str(
                    question.get(
                        "subject",
                        ""
                    )
                )
            ),
            body_style
        )
    )

    story.append(
        Paragraph(
            "<b>Student:</b> "
            + html.escape(
                str(
                    question.get(
                        "student_name",
                        ""
                    )
                )
            ),
            body_style
        )
    )

    story.append(
        Spacer(1, 10)
    )

    story.append(
        Paragraph(
            "QUESTION",
            heading_style
        )
    )

    question_text = html.escape(
        str(
            question.get(
                "question",
                ""
            )
        )
    ).replace(
        "\n",
        "<br/>"
    )

    story.append(
        Paragraph(
            question_text,
            body_style
        )
    )

    story.append(
        Spacer(1, 10)
    )

    story.append(
        Paragraph(
            "ANSWER",
            heading_style
        )
    )

    answer_text = html.escape(
        str(
            answer.get(
                "answer",
                ""
            )
        )
    ).replace(
        "\n",
        "<br/>"
    )

    story.append(
        Paragraph(
            answer_text,
            body_style
        )
    )

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            "Generated by KOJA AFRICA",
            body_style
        )
    )

    document.build(story)

    buffer.seek(0)

    return buffer.read()


def generate_and_store_answer_pdf(
    question,
    answer
):

    pdf_data = build_answer_pdf(
        question,
        answer
    )

    filename = (
        "KOJA_Answer_"
        + str(question["id"])
        + ".pdf"
    )

    storage_path = (
        "answer-pdfs/"
        + uuid.uuid4().hex
        + ".pdf"
    )

    return storage_upload_bytes(
        pdf_data,
        storage_path,
        filename,
        "application/pdf"
    )


# ============================================================
# AUTH
# ============================================================

def student_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if session.get("role") != "student":

            flash(
                "Please log in as a student."
            )

            return redirect(
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if session.get("role") != "admin":

            flash(
                "Administrator login required."
            )

            return redirect(
                url_for("admin_login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# NOTIFICATION COUNT
# ============================================================

def unread_count():

    if session.get("role") != "student":
        return 0

    try:

        rows = db_select(
            "questions",
            {
                "user_id": (
                    "eq."
                    + str(
                        session["user_id"]
                    )
                ),
                "status": "eq.Answered",
                "answer_seen": "eq.0",
                "select": "id"
            }
        )

        return len(rows)

    except Exception:
        return 0


# ============================================================
# HTML
# ============================================================

PAGE = """
<!doctype html>

<html>

<head>

<meta charset="utf-8">

<meta name="viewport"
content="width=device-width,initial-scale=1">

<meta name="theme-color"
content="#071426">

<title>
{{ title }} - KOJA Africa
</title>

<style>

*{
box-sizing:border-box;
}

body{
margin:0;
font-family:Arial,Helvetica,sans-serif;
background:#eef2f7;
color:#172033;
}

nav{
background:#071426;
color:white;
padding:14px;
}

.nav{
max-width:1150px;
margin:auto;
display:flex;
justify-content:space-between;
align-items:center;
gap:10px;
flex-wrap:wrap;
}

.logo{
font-size:25px;
font-weight:bold;
}

.logo small{
display:block;
font-size:11px;
font-weight:normal;
opacity:.7;
}

.links{
display:flex;
gap:5px;
flex-wrap:wrap;
}

.links a{
color:white;
text-decoration:none;
padding:8px 10px;
border-radius:6px;
}

.links a:hover{
background:#1e293b;
}

.container{
max-width:1150px;
margin:25px auto;
padding:0 15px;
}

.card{
background:white;
border-radius:13px;
padding:20px;
margin-bottom:18px;
box-shadow:0 3px 14px rgba(0,0,0,.07);
}

.hero{
background:linear-gradient(
135deg,
#071426,
#1d4ed8
);
color:white;
border-radius:15px;
padding:40px 25px;
margin-bottom:20px;
}

.hero h1{
font-size:36px;
margin-top:0;
}

.btn{
display:inline-block;
background:#2563eb;
color:white;
border:0;
border-radius:7px;
padding:10px 15px;
text-decoration:none;
cursor:pointer;
}

.btn:hover{
opacity:.9;
}

.green{
background:#15803d;
}

.red{
background:#dc2626;
}

.gray{
background:#475569;
}

.orange{
background:#d97706;
}

.purple{
background:#7c3aed;
}

.price{
font-size:25px;
font-weight:bold;
color:#15803d;
}

.stats{
display:grid;
grid-template-columns:
repeat(auto-fit,minmax(160px,1fr));
gap:15px;
margin-bottom:20px;
}

.stat{
background:white;
padding:20px;
border-radius:10px;
}

.num{
font-size:30px;
font-weight:bold;
color:#1e3a8a;
}

.question{
border-left:5px solid #2563eb;
}

.answer{
border-left:5px solid #16a34a;
background:#f0fdf4;
}

.payment{
border-left:5px solid #d97706;
background:#fffbeb;
}

.badge{
display:inline-block;
padding:5px 10px;
border-radius:20px;
font-size:12px;
font-weight:bold;
}

.pending{
background:#fef3c7;
color:#92400e;
}

.answered{
background:#dcfce7;
color:#166534;
}

.paid{
background:#dcfce7;
color:#166534;
}

.unpaid{
background:#fee2e2;
color:#991b1b;
}

.actions{
display:flex;
gap:8px;
flex-wrap:wrap;
margin-top:15px;
}

.text{
white-space:pre-wrap;
line-height:1.75;
}

.small{
font-size:13px;
color:#64748b;
}

.flash{
padding:12px;
border-radius:7px;
background:#dbeafe;
color:#1e40af;
margin-bottom:15px;
}

.empty{
text-align:center;
padding:40px;
color:#64748b;
}

.footer{
text-align:center;
padding:35px;
color:#64748b;
font-size:13px;
}

.error{
background:#fee2e2;
color:#991b1b;
padding:15px;
border-radius:8px;
}

.success{
background:#dcfce7;
color:#166534;
padding:15px;
border-radius:8px;
}

.info{
background:#e0f2fe;
color:#075985;
padding:15px;
border-radius:8px;
}

.form{
margin-bottom:16px;
}

label{
display:block;
font-weight:bold;
margin-bottom:7px;
}

input,
select,
textarea{
width:100%;
padding:12px;
border:1px solid #cbd5e1;
border-radius:7px;
font-size:15px;
font-family:inherit;
background:white;
}

textarea{
resize:vertical;
}

input:focus,
select:focus,
textarea:focus{
outline:none;
border-color:#2563eb;
box-shadow:
0 0 0 2px
rgba(37,99,235,.12);
}

table{
width:100%;
border-collapse:collapse;
}

th,td{
padding:10px;
border-bottom:
1px solid #e2e8f0;
text-align:left;
}

@media(max-width:650px){

.hero{
padding:25px 18px;
}

.hero h1{
font-size:27px;
}

.links a{
font-size:12px;
}

table{
display:block;
overflow-x:auto;
}

}

</style>

</head>

<body>

<nav>

<div class="nav">

<div class="logo">

KOJA AFRICA

<small>
Assignment Questions • Academic Answers
</small>

</div>

<div class="links">

{% if session.get("role") == "student" %}

<a href="{{ url_for('student_dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('submit_question') }}">
Ask
</a>

<a href="{{ url_for('my_questions') }}">
Questions
</a>

<a href="{{ url_for('notifications') }}">
Notifications
{% if unread_count %}
({{ unread_count }})
{% endif %}
</a>

<a href="{{ url_for('payments_history') }}">
Payments
</a>

<a href="{{ url_for('logout') }}">
Logout
</a>

{% elif session.get("role") == "admin" %}

<a href="{{ url_for('admin_dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('admin_questions') }}">
Questions
</a>

<a href="{{ url_for('admin_payments') }}">
Payments
</a>

<a href="{{ url_for('logout') }}">
Logout
</a>

{% else %}

<a href="{{ url_for('index') }}">
Home
</a>

<a href="{{ url_for('login') }}">
Login
</a>

<a href="{{ url_for('register') }}">
Register
</a>

{% endif %}

</div>

</div>

</nav>

<div class="container">

{% with messages =
get_flashed_messages() %}

{% for message in messages %}

<div class="flash">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</div>

<div class="footer">

<b>KOJA AFRICA</b>

<br>

Assignment Questions • Academic Answers

<br><br>

Connecting students with academic help across Africa.

</div>

</body>

</html>
"""


# ============================================================
# PAGE RENDERER
# ============================================================

def page(
    content,
    title="KOJA"
):

    return render_template_string(
        PAGE,
        content=render_template_string(
            content,
            countries=AFRICAN_COUNTRIES,
            subjects=SUBJECTS,
            payment_currency=PAYMENT_CURRENCY
        ),
        title=title,
        unread_count=unread_count()
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    return page(
        """
<div class="hero">

<h1>KOJA AFRICA</h1>

<h2>
Assignment Questions & Academic Answers
</h2>

<p>
Ask assignment questions, receive academic
answers and purchase downloadable PDF
answer resources.
</p>

<div class="actions">

<a class="btn"
href="{{ url_for('register') }}">
Create Student Account
</a>

<a class="btn gray"
href="{{ url_for('login') }}">
Student Login
</a>

<a class="btn green"
href="{{ url_for('admin_login') }}">
Administrator
</a>

</div>

</div>

<div class="stats">

<div class="stat">
<div class="num">🌍</div>
Africa-wide
</div>

<div class="stat">
<div class="num">📚</div>
Academic Questions
</div>

<div class="stat">
<div class="num">📄</div>
PDF Resources
</div>

<div class="stat">
<div class="num">💳</div>
Secure Payments
</div>

</div>

<div class="card">

<h2>How KOJA Works</h2>

<p>1. Create a student account.</p>
<p>2. Submit your assignment question.</p>
<p>3. KOJA reviews the question.</p>
<p>4. Administrator writes the answer.</p>
<p>5. Student reads the answer for free.</p>
<p>6. Student pays for the PDF.</p>
<p>7. Flutterwave processes payment.</p>
<p>8. KOJA verifies the transaction.</p>
<p>9. PDF becomes downloadable.</p>

</div>

<div class="card">

<h2>System Status</h2>

{% if database_ready %}
<div class="success">
Supabase configured.
</div>
{% else %}
<div class="error">
Supabase is not configured.
</div>
{% endif %}

<br>

{% if flutterwave_ready %}
<div class="success">
Flutterwave configured.
</div>
{% else %}
<div class="error">
Flutterwave is not configured.
</div>
{% endif %}

</div>
        """,
        "Home"
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

        name = request.form.get(
            "name",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip().lower()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        country = request.form.get(
            "country",
            ""
        ).strip()

        institution = request.form.get(
            "institution",
            ""
        ).strip()

        academic_level = request.form.get(
            "academic_level",
            ""
        ).strip()

        if not all(
            [
                name,
                username,
                email,
                password,
                country
            ]
        ):

            flash(
                "Complete all required fields."
            )

            return redirect(
                url_for("register")
            )

        if country not in AFRICAN_COUNTRIES:

            flash(
                "Select a valid African country."
            )

            return redirect(
                url_for("register")
            )

        if len(username) < 3:

            flash(
                "Username must contain at least 3 characters."
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters."
            )

            return redirect(
                url_for("register")
            )

        try:

            if get_user_by_username(
                username
            ):

                flash(
                    "Username already exists."
                )

                return redirect(
                    url_for("register")
                )

            if email_exists(email):

                flash(
                    "Email already exists."
                )

                return redirect(
                    url_for("register")
                )

            db_insert(
                "users",
                {
                    "name": name,
                    "username": username,
                    "email": email,
                    "password":
                        generate_password_hash(
                            password
                        ),
                    "role": "student",
                    "country": country,
                    "institution": institution,
                    "academic_level":
                        academic_level,
                    "created_at":
                        current_time()
                }
            )

            flash(
                "Account created successfully."
            )

            return redirect(
                url_for("login")
            )

        except Exception as error:

            flash(
                "Registration failed: "
                + str(error)
            )

    return page(
        """
<div class="card">

<h1>Create KOJA Account</h1>

<form method="POST">

<div class="form">
<label>Full Name</label>
<input name="name" required>
</div>

<div class="form">
<label>Username</label>
<input name="username" required>
</div>

<div class="form">
<label>Email</label>
<input
name="email"
type="email"
required>
</div>

<div class="form">
<label>Country</label>

<select name="country" required>

<option value="">
Select country
</option>

{% for country in countries %}

<option value="{{ country }}">
{{ country }}
</option>

{% endfor %}

</select>

</div>

<div class="form">
<label>Institution</label>
<input
name="institution"
placeholder="University / College / School">
</div>

<div class="form">
<label>Academic Level</label>

<select name="academic_level">

<option value="">
Select level
</option>

<option>Certificate</option>
<option>Diploma</option>
<option>Undergraduate</option>
<option>Postgraduate</option>
<option>Master's</option>
<option>PhD</option>

</select>

</div>

<div class="form">
<label>Password</label>
<input
name="password"
type="password"
minlength="6"
required>
</div>

<button class="btn">
Create Account
</button>

</form>

</div>
        """,
        "Register"
    )


# ============================================================
# STUDENT LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        try:

            user = get_user_by_username(
                username,
                "student"
            )

            if (
                user
                and check_password_hash(
                    user["password"],
                    password
                )
            ):

                session.clear()

                session["user_id"] = user["id"]
                session["name"] = user["name"]
                session["username"] = user["username"]
                session["role"] = "student"

                return redirect(
                    url_for(
                        "student_dashboard"
                    )
                )

            flash(
                "Invalid username or password."
            )

        except Exception as error:

            flash(
                "Login error: "
                + str(error)
            )

    return page(
        """
<div class="card">

<h1>Student Login</h1>

<form method="POST">

<div class="form">

<label>Username</label>

<input
name="username"
required>

</div>

<div class="form">

<label>Password</label>

<input
name="password"
type="password"
required>

</div>

<button class="btn">
Login
</button>

</form>

<br>

<p>
Don't have an account?
<a href="{{ url_for('register') }}">
Register
</a>
</p>

</div>
        """,
        "Login"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("index")
    )


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/student")
@student_required
def student_dashboard():

    try:

        questions = db_select(
            "questions",
            {
                "user_id": (
                    "eq."
                    + str(
                        session["user_id"]
                    )
                ),
                "select": "*",
                "order": "id.desc"
            }
        )

    except Exception as error:

        flash(
            "Could not load questions: "
            + str(error)
        )

        questions = []

    total = len(questions)

    pending = len(
        [
            q for q in questions
            if q.get("status") == "Pending"
        ]
    )

    answered = len(
        [
            q for q in questions
            if q.get("status") == "Answered"
        ]
    )

    return page(
        """
<div class="hero">

<h1>
Welcome, {{ session.get("name") }}
</h1>

<p>
KOJA AFRICA academic assistance portal.
</p>

<a class="btn"
href="{{ url_for('submit_question') }}">
Ask New Question
</a>

</div>

<div class="stats">

<div class="stat">
<div class="num">{{ total }}</div>
Questions
</div>

<div class="stat">
<div class="num">{{ pending }}</div>
Pending
</div>

<div class="stat">
<div class="num">{{ answered }}</div>
Answered
</div>

</div>

<div class="card">

<h2>Recent Questions</h2>

{% for q in questions[:10] %}

<div class="card question">

<h3>
{{ q["subject"] }}
</h3>

<p>
{{ q["question"][:250] }}
</p>

{% if q["status"] == "Answered" %}

<span class="badge answered">
Answered
</span>

{% else %}

<span class="badge pending">
Pending
</span>

{% endif %}

<div class="actions">

<a class="btn"
href="{{ url_for(
'view_question',
question_id=q['id']
) }}">
Open
</a>

</div>

</div>

{% else %}

<p>No questions yet.</p>

{% endfor %}

</div>
        """,
        "Dashboard"
    )


# ============================================================
# SUBMIT QUESTION
# ============================================================

@app.route(
    "/submit",
    methods=["GET", "POST"]
)
@student_required
def submit_question():

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        question = request.form.get(
            "question",
            ""
        ).strip()

        attachment = request.files.get(
            "attachment"
        )

        if not subject or not question:

            flash(
                "Subject and question are required."
            )

            return redirect(
                url_for("submit_question")
            )

        if subject not in SUBJECTS:

            flash(
                "Select a valid subject."
            )

            return redirect(
                url_for("submit_question")
            )

        uploaded = None

        try:

            if (
                attachment
                and attachment.filename
            ):

                uploaded = storage_upload(
                    attachment,
                    "questions"
                )

            db_insert(
                "questions",
                {
                    "user_id":
                        session["user_id"],

                    "student_name":
                        session["name"],

                    "subject":
                        subject,

                    "question":
                        question,

                    "attachment_name":
                        (
                            uploaded["original_name"]
                            if uploaded
                            else None
                        ),

                    "attachment_file":
                        (
                            uploaded["storage_path"]
                            if uploaded
                            else None
                        ),

                    "status":
                        "Pending",

                    "answer_seen":
                        0,

                    "answer_price":
                        str(
                            decimal_price(
                                DEFAULT_ANSWER_PRICE
                            )
                        ),

                    "created_at":
                        current_time()
                }
            )

            flash(
                "Question submitted successfully."
            )

            return redirect(
                url_for("my_questions")
            )

        except Exception as error:

            if uploaded:
                storage_delete(
                    uploaded["storage_path"]
                )

            flash(
                "Submission failed: "
                + str(error)
            )

    return page(
        """
<div class="card">

<h1>Ask KOJA</h1>

<div class="info">

Write the complete assignment question.
Attachments are limited to 10 MB.

</div>

<br>

<form
method="POST"
enctype="multipart/form-data">

<div class="form">

<label>Subject</label>

<select name="subject" required>

<option value="">
Select subject
</option>

{% for subject in subjects %}

<option value="{{ subject }}">
{{ subject }}
</option>

{% endfor %}

</select>

</div>

<div class="form">

<label>Assignment Question</label>

<textarea
name="question"
rows="10"
required
placeholder="Write your complete assignment question..."
></textarea>

</div>

<div class="form">

<label>Attachment</label>

<input
type="file"
name="attachment">

</div>

<button class="btn">
Submit Question
</button>

</form>

</div>
        """,
        "Ask Question"
    )


# ============================================================
# MY QUESTIONS
# ============================================================

@app.route("/my-questions")
@student_required
def my_questions():

    try:

        questions = db_select(
            "questions",
            {
                "user_id": (
                    "eq."
                    + str(
                        session["user_id"]
                    )
                ),
                "select": "*",
                "order": "id.desc"
            }
        )

    except Exception as error:

        flash(
            "Could not load questions: "
            + str(error)
        )

        questions = []

    return page(
        """
<div class="card">

<h1>My Questions</h1>

<a class="btn"
href="{{ url_for('submit_question') }}">
+ New Question
</a>

</div>

{% for q in questions %}

<div class="card question">

<h2>
{{ q["subject"] }}
</h2>

<p class="small">
{{ q["created_at"] }}
</p>

<div class="text">
{{ q["question"] }}
</div>

<br>

{% if q["status"] == "Answered" %}

<span class="badge answered">
Answered
</span>

{% else %}

<span class="badge pending">
Pending
</span>

{% endif %}

<div class="actions">

<a class="btn"
href="{{ url_for(
'view_question',
question_id=q['id']
) }}">
View
</a>

{% if q.get("attachment_file") %}

<a class="btn purple"
href="{{ url_for(
'download_question_file',
question_id=q['id']
) }}">
Download Assignment
</a>

{% endif %}

</div>

</div>

{% else %}

<div class="card empty">
No questions yet.
</div>

{% endfor %}
        """,
        "My Questions"
    )


# ============================================================
# VIEW QUESTION
# ============================================================

@app.route(
    "/question/<int:question_id>"
)
@student_required
def view_question(
    question_id
):

    question = get_student_question(
        question_id,
        session["user_id"]
    )

    if not question:
        abort(404)

    answer = get_answer(
        question_id
    )

    if answer:

        try:

            db_update(
                "questions",
                {
                    "id": question_id,
                    "user_id":
                        session["user_id"]
                },
                {
                    "answer_seen": 1
                }
            )

        except Exception:
            pass

    paid = False

    if answer:

        paid = has_paid_for_pdf(
            session["user_id"],
            question_id
        )

    price = money(
        question.get(
            "answer_price",
            DEFAULT_ANSWER_PRICE
        )
    )

    return page(
        """
<div class="card question">

<h1>
{{ question["subject"] }}
</h1>

<p class="small">
{{ question["created_at"] }}
</p>

<h3>Your Question</h3>

<div class="text">
{{ question["question"] }}
</div>

{% if question.get("attachment_file") %}

<div class="actions">

<a class="btn purple"
href="{{ url_for(
'download_question_file',
question_id=question['id']
) }}">
Download Assignment
</a>

</div>

{% endif %}

</div>

{% if answer %}

<div class="card answer">

<h2>KOJA Answer</h2>

<div class="text">
{{ answer["answer"] }}
</div>

<p class="small">
Answered {{ answer["answered_at"] }}
</p>

</div>

{% if answer.get("pdf_file") %}

<div class="card payment">

<h2>PDF Answer</h2>

{% if paid %}

<div class="success">
Payment confirmed.
Your PDF is unlocked.
</div>

<div class="actions">

<a class="btn green"
href="{{ url_for(
'download_answer_pdf',
question_id=question['id']
) }}">
Download Paid PDF
</a>

</div>

{% else %}

<div class="info">

The answer is free to read.
The downloadable PDF requires payment.

</div>

<br>

<div class="price">

{{ price }} {{ payment_currency }}

</div>

<div class="actions">

<a class="btn orange"
href="{{ url_for(
'start_pdf_payment',
question_id=question['id']
) }}">

Pay {{ price }} {{ payment_currency }}

</a>

</div>

{% endif %}

</div>

{% endif %}

{% else %}

<div class="card">

<h2>Answer Pending</h2>

<p>
The administrator has not answered this
question yet.
</p>

</div>

{% endif %}
        """,
        "Question"
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@student_required
def notifications():

    try:

        questions = db_select(
            "questions",
            {
                "user_id": (
                    "eq."
                    + str(
                        session["user_id"]
                    )
                ),
                "status": "eq.Answered",
                "select": "*",
                "order": "id.desc"
            }
        )

    except Exception as error:

        flash(
            "Could not load notifications: "
            + str(error)
        )

        questions = []

    return page(
        """
<div class="card">

<h1>Notifications</h1>

<p>
Questions that have received answers
appear here.
</p>

</div>

{% for q in questions %}

<div class="card">

<h2>
{{ q["subject"] }}
</h2>

{% if q.get("answer_seen", 0) == 0 %}

<span class="badge unpaid">
NEW
</span>

{% else %}

<span class="badge answered">
READ
</span>

{% endif %}

<div class="actions">

<a class="btn green"
href="{{ url_for(
'view_question',
question_id=q['id']
) }}">
Read Answer
</a>

</div>

</div>

{% else %}

<div class="card empty">
No answers yet.
</div>

{% endfor %}
        """,
        "Notifications"
    )


# ============================================================
# DOWNLOAD QUESTION FILE
# ============================================================

@app.route(
    "/download/question/<int:question_id>"
)
@student_required
def download_question_file(
    question_id
):

    question = get_student_question(
        question_id,
        session["user_id"]
    )

    if not question:
        abort(404)

    path = question.get(
        "attachment_file"
    )

    if not path:
        abort(404)

    return send_storage_file(
        path,
        question.get(
            "attachment_name"
        ) or "assignment"
    )


# ============================================================
# START FLUTTERWAVE PAYMENT
# ============================================================

@app.route(
    "/pay/pdf/<int:question_id>"
)
@student_required
def start_pdf_payment(
    question_id
):

    question = get_student_question(
        question_id,
        session["user_id"]
    )

    if not question:
        abort(404)

    answer = get_answer(
        question_id
    )

    if not answer:
        flash(
            "The answer is not available yet."
        )

        return redirect(
            url_for(
                "view_question",
                question_id=question_id
            )
        )

    if not answer.get("pdf_file"):

        flash(
            "The PDF has not been generated yet."
        )

        return redirect(
            url_for(
                "view_question",
                question_id=question_id
            )
        )

    if has_paid_for_pdf(
        session["user_id"],
        question_id
    ):

        return redirect(
            url_for(
                "download_answer_pdf",
                question_id=question_id
            )
        )

    if not FLW_SECRET_KEY:

        flash(
            "Flutterwave is not configured."
        )

        return redirect(
            url_for(
                "view_question",
                question_id=question_id
            )
        )

    amount = decimal_price(
        question.get(
            "answer_price",
            DEFAULT_ANSWER_PRICE
        )
    )

    tx_ref = (
        "KOJA-"
        + str(question_id)
        + "-"
        + uuid.uuid4().hex
    )

    existing_payment = (
        get_payment_by_tx_ref(tx_ref)
    )

    if existing_payment:

        flash(
            "Payment reference collision. Please try again."
        )

        return redirect(
            url_for(
                "view_question",
                question_id=question_id
            )
        )

    payment_rows = db_insert(
        "payments",
        {
            "student_id":
                session["user_id"],

            "question_id":
                question_id,

            "tx_ref":
                tx_ref,

            "amount":
                str(amount),

            "currency":
                PAYMENT_CURRENCY,

            "status":
                "pending",

            "created_at":
                current_time()
        }
    )

    if not payment_rows:

        flash(
            "Could not create payment record."
        )

        return redirect(
            url_for(
                "view_question",
                question_id=question_id
            )
        )

    redirect_url = (
        KOJA_BASE_URL
        + url_for(
            "flutterwave_callback"
        )
        if KOJA_BASE_URL
        else url_for(
            "flutterwave_callback",
            _external=True
        )
    )

    user = get_user_by_id(
        session["user_id"]
    )

    customer_email = (
        user.get("email", "")
        if user
        else ""
    )

    customer_name = (
        user.get("name")
        if user
        else session.get(
            "name",
            "KOJA Student"
        )
    )

    payload = {
        "tx_ref": tx_ref,

        "amount": str(amount),

        "currency":
            PAYMENT_CURRENCY,

        "redirect_url":
            redirect_url,

        "customer": {
            "email":
                customer_email,

            "name":
                customer_name
        },

        "customizations": {
            "title":
                "KOJA AFRICA",

            "description":
                "Academic Answer PDF"
        },

        "configurations": {
            "session_duration":
                30,

            "max_retry_attempt":
                5
        }
    }

    try:

        response = requests.post(
            FLW_BASE_URL
            + "/payments",

            headers={
                "Authorization":
                    "Bearer "
                    + FLW_SECRET_KEY,

                "Content-Type":
                    "application/json",

                "Accept":
                    "application/json"
            },

            json=payload,

            timeout=45
        )

        data = response.json()

    except Exception as error:

        db_update(
            "payments",
            {"tx_ref": tx_ref},
            {
                "status": "failed",
                "verified_at":
                    current_time()
            }
        )

        flash(
            "Flutterwave connection failed: "
            + str(error)
        )

        return redirect(
            url_for(
                "view_question",
                question_id=question_id
            )
        )

    if (
        response.ok
        and data.get("status") == "success"
        and data.get("data")
        and data["data"].get("link")
    ):

        return redirect(
            data["data"]["link"]
        )

    db_update(
        "payments",
        {"tx_ref": tx_ref},
        {
            "status": "failed",
            "verified_at":
                current_time()
        }
    )

    flash(
        "Flutterwave could not create payment."
    )

    return redirect(
        url_for(
            "view_question",
            question_id=question_id
        )
    )


# ============================================================
# FLUTTERWAVE VERIFY FUNCTION
# ============================================================

def verify_flutterwave_transaction(
    transaction_id
):

    if not FLW_SECRET_KEY:
        raise RuntimeError(
            "Flutterwave secret key is missing."
        )

    response = requests.get(
        FLW_BASE_URL
        + "/transactions/"
        + str(transaction_id)
        + "/verify",

        headers={
            "Authorization":
                "Bearer "
                + FLW_SECRET_KEY,

            "Content-Type":
                "application/json",

            "Accept":
                "application/json"
        },

        timeout=45
    )

    if not response.ok:

        raise RuntimeError(
            "Flutterwave verification failed: "
            + response.text
        )

    data = response.json()

    transaction = data.get(
        "data"
    )

    if not transaction:

        raise RuntimeError(
            "No transaction data returned."
        )

    return transaction


# ============================================================
# PAYMENT VALIDATION
# ============================================================

def validate_payment_transaction(
    payment,
    transaction
):

    expected_tx_ref = str(
        payment.get(
            "tx_ref",
            ""
        )
    )

    expected_currency = str(
        payment.get(
            "currency",
            PAYMENT_CURRENCY
        )
    ).upper()

    try:

        expected_amount = Decimal(
            str(
                payment.get(
                    "amount",
                    "0"
                )
            )
        )

    except Exception:

        return False

    actual_status = str(
        transaction.get(
            "status",
            ""
        )
    ).lower()

    actual_tx_ref = str(
        transaction.get(
            "tx_ref",
            ""
        )
    )

    actual_currency = str(
        transaction.get(
            "currency",
            ""
        )
    ).upper()

    try:

        actual_amount = Decimal(
            str(
                transaction.get(
                    "amount",
                    "0"
                )
            )
        )

    except Exception:

        actual_amount = Decimal("0")

    return (
        actual_status == "successful"
        and actual_tx_ref == expected_tx_ref
        and actual_currency == expected_currency
        and actual_amount >= expected_amount
    )


# ============================================================
# FLUTTERWAVE CALLBACK
# ============================================================

@app.route(
    "/payment/flutterwave/callback"
)
def flutterwave_callback():

    tx_ref = request.args.get(
        "tx_ref",
        ""
    ).strip()

    transaction_id = request.args.get(
        "transaction_id",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip().lower()

    if not tx_ref:

        return payment_result_page(
            None,
            False,
            "Missing payment reference."
        ), 400

    payment = get_payment_by_tx_ref(
        tx_ref
    )

    if not payment:

        return payment_result_page(
            None,
            False,
            "Payment record was not found."
        ), 404

    if payment.get("status") == "paid":

        return payment_result_page(
            payment,
            True,
            "Payment was already verified."
        )

    if status == "failed":

        db_update(
            "payments",
            {"tx_ref": tx_ref},
            {
                "status": "failed",
                "verified_at":
                    current_time()
            }
        )

        payment["status"] = "failed"

        return payment_result_page(
            payment,
            False,
            "Flutterwave reported that the payment failed."
        )

    if not transaction_id:

        return payment_result_page(
            payment,
            False,
            "No transaction ID was returned."
        )

    try:

        transaction = (
            verify_flutterwave_transaction(
                transaction_id
            )
        )

    except Exception as error:

        return payment_result_page(
            payment,
            False,
            str(error)
        )

    valid = validate_payment_transaction(
        payment,
        transaction
    )

    if not valid:

        db_update(
            "payments",
            {"tx_ref": tx_ref},
            {
                "status": "failed",

                "flutterwave_transaction_id":
                    str(
                        transaction.get(
                            "id",
                            transaction_id
                        )
                    ),

                "verified_at":
                    current_time()
            }
        )

        return payment_result_page(
            payment,
            False,
            "Payment verification failed. The PDF remains locked."
        )

    db_update(
        "payments",
        {"tx_ref": tx_ref},
        {
            "status": "paid",

            "flutterwave_transaction_id":
                str(
                    transaction.get(
                        "id",
                        transaction_id
                    )
                ),

            "paid_at":
                current_time(),

            "verified_at":
                current_time()
        }
    )

    paid_payment = (
        get_payment_by_tx_ref(
            tx_ref
        )
    )

    return payment_result_page(
        paid_payment or payment,
        True,
        "Payment verified successfully."
    )


# ============================================================
# FLUTTERWAVE WEBHOOK
# ============================================================

@app.route(
    "/webhook/flutterwave",
    methods=["POST"]
)
def flutterwave_webhook():

    if not FLW_SECRET_HASH:

        return jsonify({
            "status": "disabled"
        }), 200

    received_hash = request.headers.get(
        "verif-hash",
        ""
    )

    if (
        not received_hash
        or received_hash != FLW_SECRET_HASH
    ):

        return jsonify({
            "status": "unauthorized"
        }), 401

    payload = request.get_json(
        silent=True
    ) or {}

    transaction_id = payload.get(
        "id"
    )

    data = payload.get(
        "data"
    ) or {}

    if not transaction_id:

        transaction_id = data.get(
            "id"
        )

    if not transaction_id:

        return jsonify({
            "status": "ignored"
        }), 200

    tx_ref = data.get(
        "tx_ref"
    )

    if not tx_ref:

        return jsonify({
            "status": "ignored"
        }), 200

    try:

        payment = get_payment_by_tx_ref(
            str(tx_ref)
        )

        if not payment:

            return jsonify({
                "status": "ignored"
            }), 200

        transaction = (
            verify_flutterwave_transaction(
                transaction_id
            )
        )

        valid = (
            validate_payment_transaction(
                payment,
                transaction
            )
        )

        if valid:

            db_update(
                "payments",
                {
                    "tx_ref":
                        str(tx_ref)
                },
                {
                    "status": "paid",

                    "flutterwave_transaction_id":
                        str(
                            transaction.get(
                                "id",
                                transaction_id
                            )
                        ),

                    "paid_at":
                        current_time(),

                    "verified_at":
                        current_time()
                }
            )

        else:

            db_update(
                "payments",
                {
                    "tx_ref":
                        str(tx_ref)
                },
                {
                    "status": "failed",
                    "verified_at":
                        current_time()
                }
            )

    except Exception as error:

        print(
            "Webhook processing error:",
            error
        )

    return jsonify({
        "status": "received"
    }), 200


# ============================================================
# PAYMENT RESULT
# ============================================================

def payment_result_page(
    payment,
    success,
    message
):

    if not payment:

        return page(
            """
<div class="card">

<h1>Payment Error</h1>

<div class="error">
{{ message }}
</div>

<br>

<a class="btn"
href="{{ url_for('index') }}">
KOJA Home
</a>

</div>
            """,
            "Payment"
        )

    question_id = payment.get(
        "question_id"
    )

    if success:

        content = """
<div class="card">

<h1>Payment Successful</h1>

<div class="success">

{{ message }}

<br><br>

Your payment has been verified by KOJA.

</div>

<div class="actions">

<a class="btn green"
href="{{ url_for(
'download_answer_pdf',
question_id=question_id
) }}">
Download PDF Answer
</a>

<a class="btn gray"
href="{{ url_for(
'view_question',
question_id=question_id
) }}">
Return to Answer
</a>

</div>

</div>
        """

    else:

        content = """
<div class="card">

<h1>Payment Not Completed</h1>

<div class="error">

{{ message }}

</div>

<p>
Your PDF remains locked until payment
is successfully verified.
</p>

<div class="actions">

<a class="btn"
href="{{ url_for(
'view_question',
question_id=question_id
) }}">
Return to Question
</a>

</div>

</div>
        """

    return page(
        content,
        "Payment"
    )


# ============================================================
# PAID PDF DOWNLOAD
# ============================================================

@app.route(
    "/download/answer-pdf/<int:question_id>"
)
@student_required
def download_answer_pdf(
    question_id
):

    question = get_student_question(
        question_id,
        session["user_id"]
    )

    if not question:
        abort(404)

    answer = get_answer(
        question_id
    )

    if not answer:
        abort(404)

    path = answer.get(
        "pdf_file"
    )

    if not path:
        abort(404)

    payment = get_paid_payment(
        session["user_id"],
        question_id
    )

    if not payment:

        flash(
            "Payment required before downloading the PDF."
        )

        return redirect(
            url_for(
                "view_question",
                question_id=question_id
            )
        )

    return send_storage_file(
        path,
        answer.get(
            "pdf_name"
        ) or "KOJA_Answer.pdf"
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        try:

            admin = get_user_by_username(
                username,
                "admin"
            )

            if (
                admin
                and check_password_hash(
                    admin["password"],
                    password
                )
            ):

                session.clear()

                session["user_id"] = admin["id"]
                session["name"] = admin["name"]
                session["username"] = admin["username"]
                session["role"] = "admin"

                return redirect(
                    url_for(
                        "admin_dashboard"
                    )
                )

            flash(
                "Invalid administrator credentials."
            )

        except Exception as error:

            flash(
                "Admin login error: "
                + str(error)
            )

    return page(
        """
<div class="card">

<h1>KOJA Administrator</h1>

<form method="POST">

<div class="form">

<label>Username</label>

<input
name="username"
required>

</div>

<div class="form">

<label>Password</label>

<input
name="password"
type="password"
required>

</div>

<button class="btn">
Administrator Login
</button>

</form>

</div>
        """,
        "Admin Login"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    try:

        questions = db_select(
            "questions",
            {
                "select": "*",
                "order": "id.desc"
            }
        )

        students = db_select(
            "users",
            {
                "role": "eq.student",
                "select": "id"
            }
        )

        payments = db_select(
            "payments",
            {
                "select": "*"
            }
        )

    except Exception as error:

        flash(
            "Could not load administrator data: "
            + str(error)
        )

        questions = []
        students = []
        payments = []

    pending = len(
        [
            q for q in questions
            if q.get("status") == "Pending"
        ]
    )

    answered = len(
        [
            q for q in questions
            if q.get("status") == "Answered"
        ]
    )

    paid = len(
        [
            p for p in payments
            if p.get("status") == "paid"
        ]
    )

    return page(
        """
<div class="hero">

<h1>KOJA Administrator</h1>

<p>
Manage student questions, answers,
PDF prices and payments.
</p>

<div class="actions">

<a class="btn"
href="{{ url_for('admin_questions') }}">
Manage Questions
</a>

<a class="btn green"
href="{{ url_for('admin_payments') }}">
Payments
</a>

</div>

</div>

<div class="stats">

<div class="stat">
<div class="num">{{ questions|length }}</div>
Total Questions
</div>

<div class="stat">
<div class="num">{{ pending }}</div>
Pending
</div>

<div class="stat">
<div class="num">{{ answered }}</div>
Answered
</div>

<div class="stat">
<div class="num">{{ students|length }}</div>
Students
</div>

<div class="stat">
<div class="num">{{ paid }}</div>
Paid Transactions
</div>

</div>
        """,
        "Admin Dashboard"
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    search = request.args.get(
        "search",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()

    params = {
        "select": "*",
        "order": "id.desc"
    }

    if status in (
        "Pending",
        "Answered"
    ):

        params["status"] = (
            "eq."
            + status
        )

    if search:

        safe_search = (
            search
            .replace("*", "")
            .replace(",", " ")
            .strip()
        )

        if safe_search:

            value = (
                "*"
                + safe_search
                + "*"
            )

            params["or"] = (
                "(student_name.ilike."
                + value
                + ",subject.ilike."
                + value
                + ",question.ilike."
                + value
                + ")"
            )

    try:

        questions = db_select(
            "questions",
            params
        )

    except Exception as error:

        questions = []

        flash(
            "Search failed: "
            + str(error)
        )

    return page(
        """
<div class="card">

<h1>Questions</h1>

<form method="GET">

<div class="form">

<label>Search</label>

<input
name="search"
value="{{ search }}"
placeholder="Student, subject or question">

</div>

<div class="form">

<label>Status</label>

<select name="status">

<option value="">
All
</option>

<option
value="Pending"
{% if status == "Pending" %}
selected
{% endif %}
>
Pending
</option>

<option
value="Answered"
{% if status == "Answered" %}
selected
{% endif %}
>
Answered
</option>

</select>

</div>

<button class="btn">
Search
</button>

</form>

</div>

{% for q in questions %}

<div class="card question">

<h2>
{{ q["student_name"] }}
</h2>

<p>
<b>{{ q["subject"] }}</b>
</p>

<p>
{{ q["question"][:400] }}
</p>

<p>

PDF Price:

<b>
{{ q.get("answer_price", 10) }}
{{ payment_currency }}
</b>

</p>

{% if q["status"] == "Answered" %}

<span class="badge answered">
Answered
</span>

{% else %}

<span class="badge pending">
Pending
</span>

{% endif %}

<div class="actions">

<a class="btn"
href="{{ url_for(
'admin_view_question',
question_id=q['id']
) }}">
Open
</a>

</div>

</div>

{% else %}

<div class="card empty">
No questions found.
</div>

{% endfor %}
        """,
        "Admin Questions"
    )


# ============================================================
# ADMIN QUESTION
# ============================================================

@app.route(
    "/admin/question/<int:question_id>"
)
@admin_required
def admin_view_question(
    question_id
):

    question = get_question(
        question_id
    )

    if not question:
        abort(404)

    answer = get_answer(
        question_id
    )

    return page(
        """
<div class="card question">

<h1>
{{ question["subject"] }}
</h1>

<p>
<b>Student:</b>
{{ question["student_name"] }}
</p>

<p class="small">
{{ question["created_at"] }}
</p>

<h3>Assignment Question</h3>

<div class="text">
{{ question["question"] }}
</div>

{% if question.get("attachment_file") %}

<div class="actions">

<a class="btn purple"
href="{{ url_for(
'admin_download_question',
question_id=question['id']
) }}">
Download Assignment
</a>

{% endif %}

</div>

</div>

<div class="card">

<h2>

{% if answer %}
Update Answer
{% else %}
Write Answer
{% endif %}

</h2>

<form
method="POST"
action="{{ url_for(
'write_answer',
question_id=question['id']
) }}">

<div class="form">

<label>
PDF Answer Price
({{ payment_currency }})
</label>

<input
name="answer_price"
type="number"
min="0.01"
step="0.01"
value="{{ question.get('answer_price', 10) }}"
required>

</div>

<div class="form">

<label>Academic Answer</label>

<textarea
name="answer"
rows="16"
required>{% if answer %}{{ answer["answer"] }}{% endif %}</textarea>

</div>

<div class="form">

<label>
Optional Additional Answer File
</label>

<input
type="file"
name="answer_attachment">

</div>

<button class="btn green">

{% if answer %}
Update Answer
{% else %}
Send Answer
{% endif %}

</button>

</form>

{% if answer and answer.get("attachment_file") %}

<br>

<a class="btn purple"
href="{{ url_for(
'admin_download_answer',
question_id=question['id']
) }}">
Download Additional Answer File
</a>

{% endif %}

</div>
        """,
        "Answer Question"
    )


# ============================================================
# WRITE ANSWER
# ============================================================

@app.route(
    "/admin/question/<int:question_id>/answer",
    methods=["POST"]
)
@admin_required
def write_answer(
    question_id
):

    text = request.form.get(
        "answer",
        ""
    ).strip()

    price_text = request.form.get(
        "answer_price",
        DEFAULT_ANSWER_PRICE
    ).strip()

    attachment = request.files.get(
        "answer_attachment"
    )

    if not text:

        flash(
            "Answer cannot be empty."
        )

        return redirect(
            url_for(
                "admin_view_question",
                question_id=question_id
            )
        )

    try:

        price = Decimal(
            price_text
        ).quantize(
            Decimal("0.01")
        )

    except Exception:

        flash(
            "Invalid PDF price."
        )

        return redirect(
            url_for(
                "admin_view_question",
                question_id=question_id
            )
        )

    if price <= 0:

        flash(
            "PDF price must be greater than zero."
        )

        return redirect(
            url_for(
                "admin_view_question",
                question_id=question_id
            )
        )

    question = get_question(
        question_id
    )

    if not question:
        abort(404)

    uploaded = None
    new_pdf = None

    try:

        db_update(
            "questions",
            {"id": question_id},
            {
                "answer_price":
                    str(price)
            }
        )

        if (
            attachment
            and attachment.filename
        ):

            uploaded = storage_upload(
                attachment,
                "answers"
            )

        existing = get_answer(
            question_id
        )

        if existing:

            update = {
                "answer":
                    text,

                "answered_at":
                    current_time()
            }

            old_file = existing.get(
                "attachment_file"
            )

            if uploaded:

                update[
                    "attachment_name"
                ] = uploaded[
                    "original_name"
                ]

                update[
                    "attachment_file"
                ] = uploaded[
                    "storage_path"
                ]

            db_update(
                "answers",
                {
                    "id":
                        existing["id"]
                },
                update
            )

            if uploaded and old_file:
                storage_delete(old_file)

        else:

            rows = db_insert(
                "answers",
                {
                    "question_id":
                        question_id,

                    "answer":
                        text,

                    "attachment_name":
                        (
                            uploaded["original_name"]
                            if uploaded
                            else None
                        ),

                    "attachment_file":
                        (
                            uploaded["storage_path"]
                            if uploaded
                            else None
                        ),

                    "answered_at":
                        current_time()
                }
            )

            if not rows:
                raise RuntimeError(
                    "Could not create answer."
                )

        current_answer = get_answer(
            question_id
        )

        if not current_answer:

            raise RuntimeError(
                "Answer could not be loaded."
            )

        new_pdf = (
            generate_and_store_answer_pdf(
                question,
                current_answer
            )
        )

        old_pdf = current_answer.get(
            "pdf_file"
        )

        db_update(
            "answers",
            {
                "id":
                    current_answer["id"]
            },
            {
                "pdf_file":
                    new_pdf[
                        "storage_path"
                    ],

                "pdf_name":
                    new_pdf[
                        "original_name"
                    ]
            }
        )

        if old_pdf:
            storage_delete(old_pdf)

        db_update(
            "questions",
            {"id": question_id},
            {
                "status":
                    "Answered",

                "answer_seen":
                    0
            }
        )

        flash(
            "Answer saved and PDF generated successfully."
        )

    except Exception as error:

        if uploaded:
            storage_delete(
                uploaded["storage_path"]
            )

        if new_pdf:
            storage_delete(
                new_pdf["storage_path"]
            )

        flash(
            "Could not save answer: "
            + str(error)
        )

    return redirect(
        url_for(
            "admin_view_question",
            question_id=question_id
        )
    )


# ============================================================
# ADMIN QUESTION DOWNLOAD
# ============================================================

@app.route(
    "/admin/download/question/<int:question_id>"
)
@admin_required
def admin_download_question(
    question_id
):

    question = get_question(
        question_id
    )

    if not question:
        abort(404)

    path = question.get(
        "attachment_file"
    )

    if not path:
        abort(404)

    return send_storage_file(
        path,
        question.get(
            "attachment_name"
        ) or "assignment"
    )


# ============================================================
# ADMIN ANSWER FILE
# ============================================================

@app.route(
    "/admin/download/answer/<int:question_id>"
)
@admin_required
def admin_download_answer(
    question_id
):

    answer = get_answer(
        question_id
    )

    if not answer:
        abort(404)

    path = answer.get(
        "attachment_file"
    )

    if not path:
        abort(404)

    return send_storage_file(
        path,
        answer.get(
            "attachment_name"
        ) or "answer"
    )


# ============================================================
# ADMIN PAYMENTS
# ============================================================

@app.route(
    "/admin/payments"
)
@admin_required
def admin_payments():

    try:

        payments = db_select(
            "payments",
            {
                "select": "*",
                "order": "id.desc"
            }
        )

    except Exception as error:

        payments = []

        flash(
            "Could not load payments: "
            + str(error)
        )

    total_paid = Decimal("0")

    for payment in payments:

        if payment.get(
            "status"
        ) == "paid":

            try:

                total_paid += Decimal(
                    str(
                        payment.get(
                            "amount",
                            "0"
                        )
                    )
                )

            except Exception:
                pass

    return page(
        """
<div class="card">

<h1>Payment History</h1>

<h2>

Total Paid:

{{ total_paid }}

{{ payment_currency }}

</h2>

</div>

<div class="card">

<table>

<tr>

<th>ID</th>
<th>Student</th>
<th>Question</th>
<th>Amount</th>
<th>Status</th>
<th>Reference</th>

</tr>

{% for p in payments %}

<tr>

<td>{{ p["id"] }}</td>

<td>{{ p["student_id"] }}</td>

<td>{{ p["question_id"] }}</td>

<td>
{{ p["amount"] }}
{{ payment_currency }}
</td>

<td>

{% if p["status"] == "paid" %}

<span class="badge paid">
PAID
</span>

{% elif p["status"] == "pending" %}

<span class="badge pending">
PENDING
</span>

{% else %}

<span class="badge unpaid">
{{ p["status"]|upper }}
</span>

{% endif %}

</td>

<td>
{{ p["tx_ref"] }}
</td>

</tr>

{% else %}

<tr>

<td colspan="6">
No payments yet.
</td>

</tr>

{% endfor %}

</table>

</div>
        """,
        "Payments"
    ).replace(
        "{{ total_paid }}",
        money(total_paid)
    )


# ============================================================
# STUDENT PAYMENTS
# ============================================================

@app.route("/payments")
@student_required
def payments_history():

    try:

        payments = db_select(
            "payments",
            {
                "student_id": (
                    "eq."
                    + str(
                        session["user_id"]
                    )
                ),
                "select": "*",
                "order": "id.desc"
            }
        )

    except Exception as error:

        payments = []

        flash(
            "Could not load payment history: "
            + str(error)
        )

    return page(
        """
<div class="card">

<h1>My Payments</h1>

</div>

<div class="card">

<table>

<tr>

<th>Question</th>
<th>Amount</th>
<th>Status</th>
<th>Date</th>

</tr>

{% for p in payments %}

<tr>

<td>
{{ p["question_id"] }}
</td>

<td>
{{ p["amount"] }}
{{ payment_currency }}
</td>

<td>

{% if p["status"] == "paid" %}

<span class="badge paid">
PAID
</span>

{% elif p["status"] == "pending" %}

<span class="badge pending">
PENDING
</span>

{% else %}

<span class="badge unpaid">
{{ p["status"]|upper }}
</span>

{% endif %}

</td>

<td>
{{ p["created_at"] }}
</td>

</tr>

{% else %}

<tr>

<td colspan="4">
No payments yet.
</td>

</tr>

{% endfor %}

</table>

</div>
        """,
        "My Payments"
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    if not database_ready():

        return {
            "status": "error",
            "application": APP_NAME,
            "database": "not configured"
        }, 500

    try:

        db_select(
            "users",
            {
                "select": "id",
                "limit": "1"
            }
        )

        return {
            "status": "ok",
            "application": APP_NAME,
            "database": "connected",
            "storage": STORAGE_BUCKET,
            "flutterwave":
                bool(FLW_SECRET_KEY)
        }

    except Exception as error:

        return {
            "status": "error",
            "database": "not connected",
            "error": str(error)
        }, 500


# ============================================================
# STATUS
# ============================================================

@app.route("/status")
def status():

    return {
        "application": APP_NAME,
        "supabase_configured":
            database_ready(),
        "storage_bucket":
            STORAGE_BUCKET,
        "flutterwave_configured":
            bool(FLW_SECRET_KEY),
        "currency":
            PAYMENT_CURRENCY,
        "host":
            HOST,
        "port":
            PORT,
        "https":
            HTTPS_ENABLED
    }


# ============================================================
# ERROR 413
# ============================================================

@app.errorhandler(413)
def too_large(error):

    return (
        "File too large. Maximum allowed size is 10 MB.",
        413
    )


# ============================================================
# ERROR 404
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return (
        page(
            """
<div class="card empty">

<h1>404</h1>

<h2>Page Not Found</h2>

<a class="btn"
href="{{ url_for('index') }}">
KOJA Home
</a>

</div>
            """,
            "404"
        ),
        404
    )


# ============================================================
# ERROR 500
# ============================================================

@app.errorhandler(500)
def server_error(error):

    return (
        page(
            """
<div class="card">

<h1>Server Error</h1>

<div class="error">

KOJA encountered a server-side error.

</div>

<br>

<a class="btn"
href="{{ url_for('index') }}">
Return Home
</a>

</div>
            """,
            "Server Error"
        ),
        500
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print("KOJA AFRICA")
    print("=" * 60)

    print(
        "Supabase configured:",
        database_ready()
    )

    print(
        "Storage bucket:",
        STORAGE_BUCKET
    )

    print(
        "Flutterwave configured:",
        bool(FLW_SECRET_KEY)
    )

    print(
        "Flutterwave webhook hash:",
        bool(FLW_SECRET_HASH)
    )

    print(
        "Payment currency:",
        PAYMENT_CURRENCY
    )

    print(
        "Host:",
        HOST
    )

    print(
        "Port:",
        PORT
    )

    print("=" * 60)
    print()

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
        threaded=True,
        use_reloader=False
    )
