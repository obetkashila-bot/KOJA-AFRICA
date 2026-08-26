# ============================================================
# KOJA AFRICA
# KNOWLEDGE • QUESTIONS • ANSWERS
#
# COMPLETE SINGLE-FILE FLASK APPLICATION
#
# STUDENT + ADMIN ACADEMIC PORTAL
#
# FEATURES
# ------------------------------------------------------------
# STUDENT
#   - Register
#   - Login / Logout
#   - Dashboard
#   - Ask academic questions
#   - Upload documents
#   - Upload multiple photos
#   - Take photo using phone camera
#   - View own questions
#   - View administrator answers
#   - View administrator attachments
#
# ADMIN
#   - Secure admin login
#   - Dashboard
#   - View all questions
#   - Search/filter questions
#   - Read student attachments
#   - Answer questions
#   - Upload documents
#   - Take photos using camera
#   - Send attachments to students
#   - Configuration
#
# STORAGE
# ------------------------------------------------------------
# Local JSON + local file storage always available
# Optional Supabase PostgreSQL REST synchronization
#
# DEPLOYMENT
# ------------------------------------------------------------
# Render
# Railway
# VPS
# Local Python
# Pydroid 3
#
# NO SQLITE
# NO psycopg
# NO psycopg2
#
# ============================================================

import os
import json
import uuid
import hashlib
import secrets
import threading
import html
from datetime import datetime, timezone
from functools import wraps

import requests

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template_string,
    flash,
    send_from_directory,
    abort,
    jsonify
)


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_SECRET_KEY"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# Safer cookie settings.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Set this to true behind HTTPS in production.
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get(
        "KOJA_COOKIE_SECURE",
        "false"
    ).lower() == "true"
)


# ============================================================
# DIRECTORIES
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "koja_data"
)

UPLOAD_DIR = os.path.join(
    DATA_DIR,
    "uploads"
)

STUDENT_UPLOAD_DIR = os.path.join(
    UPLOAD_DIR,
    "student"
)

ADMIN_UPLOAD_DIR = os.path.join(
    UPLOAD_DIR,
    "admin"
)

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STUDENT_UPLOAD_DIR, exist_ok=True)
os.makedirs(ADMIN_UPLOAD_DIR, exist_ok=True)


USERS_FILE = os.path.join(
    DATA_DIR,
    "users.json"
)

QUESTIONS_FILE = os.path.join(
    DATA_DIR,
    "questions.json"
)

LOCK = threading.RLock()


# ============================================================
# ADMIN
# ============================================================

ADMIN_EMAIL = os.environ.get(
    "KOJA_ADMIN_EMAIL",
    "admin@koja.africa"
).strip().lower()

ADMIN_PASSWORD = os.environ.get(
    "KOJA_ADMIN_PASSWORD",
    "ChangeMe123!"
)


# ============================================================
# SUPABASE
# ============================================================

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    ""
).strip().rstrip("/")

SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    ""
).strip()

STORAGE_BUCKET = os.environ.get(
    "KOJA_STORAGE_BUCKET",
    "koja-files"
).strip()


# ============================================================
# ALLOWED FILE TYPES
# ============================================================

ALLOWED_EXTENSIONS = {
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "webp",
    "gif",
    "doc",
    "docx",
    "txt",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "csv"
}

IMAGE_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp",
    "gif"
}


# ============================================================
# JSON DATABASE
# ============================================================

def ensure_json_file(path, default):

    if not os.path.exists(path):

        with open(
            path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                default,
                file,
                indent=2,
                ensure_ascii=False
            )


ensure_json_file(
    USERS_FILE,
    []
)

ensure_json_file(
    QUESTIONS_FILE,
    []
)


def read_json(path):

    try:

        with LOCK:

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as file:

                value = json.load(file)

                if isinstance(value, list):
                    return value

                return []

    except Exception:

        return []


def write_json(path, data):

    with LOCK:

        temporary = (
            path
            + "."
            + str(uuid.uuid4())
            + ".tmp"
        )

        with open(
            temporary,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False
            )

        os.replace(
            temporary,
            path
        )


# ============================================================
# TIME
# ============================================================

def now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# HTML ESCAPING
# ============================================================

def esc(value):

    return html.escape(
        str(value or ""),
        quote=True
    )


# ============================================================
# PASSWORD SECURITY
# ============================================================

PBKDF2_ITERATIONS = 300_000


def hash_password(password):

    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS
    )

    return (
        salt
        + "$"
        + digest.hex()
    )


def verify_password(
    password,
    stored
):

    try:

        salt, digest = stored.split(
            "$",
            1
        )

        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PBKDF2_ITERATIONS
        ).hex()

        return secrets.compare_digest(
            check,
            digest
        )

    except Exception:

        return False


# ============================================================
# USERS
# ============================================================

def get_users():

    return read_json(
        USERS_FILE
    )


def save_users(data):

    write_json(
        USERS_FILE,
        data
    )


def find_user(email):

    email = (
        email or ""
    ).strip().lower()

    for user in get_users():

        if (
            user.get("email", "")
            .strip()
            .lower()
            == email
        ):

            return user

    return None


def find_user_by_id(user_id):

    for user in get_users():

        if (
            str(user.get("id"))
            == str(user_id)
        ):

            return user

    return None


def create_admin():

    data = get_users()

    existing = None

    for user in data:

        if (
            user.get("email", "")
            .lower()
            == ADMIN_EMAIL
        ):

            existing = user
            break

    if existing:

        existing["role"] = "admin"
        existing["name"] = "KOJA Administrator"

        # Environment variable is authoritative.
        existing["password"] = hash_password(
            ADMIN_PASSWORD
        )

        save_users(data)

        return

    data.append({

        "id": str(uuid.uuid4()),

        "name":
            "KOJA Administrator",

        "email":
            ADMIN_EMAIL,

        "password":
            hash_password(
                ADMIN_PASSWORD
            ),

        "role":
            "admin",

        "created_at":
            now_iso()

    })

    save_users(data)


create_admin()


# ============================================================
# SUPABASE
# ============================================================

def supabase_configured():

    return bool(
        SUPABASE_URL
        and SUPABASE_SERVICE_KEY
    )


def supabase_headers():

    return {

        "apikey":
            SUPABASE_SERVICE_KEY,

        "Authorization":
            "Bearer "
            + SUPABASE_SERVICE_KEY,

        "Content-Type":
            "application/json",

        "Prefer":
            "return=minimal"
    }


def supabase_request(
    method,
    endpoint,
    data=None,
    params=None
):

    if not supabase_configured():

        return None

    try:

        response = requests.request(

            method=method,

            url=(
                SUPABASE_URL
                + endpoint
            ),

            headers=supabase_headers(),

            json=data,

            params=params,

            timeout=10
        )

        if response.status_code >= 400:

            print(
                "Supabase error:",
                response.status_code,
                response.text[:500]
            )

            return None

        if not response.text:

            return {}

        try:

            return response.json()

        except Exception:

            return {}

    except Exception as error:

        print(
            "Supabase connection error:",
            error
        )

        return None


def supabase_test():

    if not supabase_configured():

        return False

    try:

        response = requests.get(

            SUPABASE_URL
            + "/rest/v1/",

            headers=supabase_headers(),

            timeout=5
        )

        return response.status_code < 400

    except Exception:

        return False


def supabase_insert(
    table,
    row
):

    return supabase_request(
        "POST",
        "/rest/v1/" + table,
        row
    )


def supabase_update(
    table,
    question_id,
    row
):

    return supabase_request(

        "PATCH",

        "/rest/v1/"
        + table,

        row,

        params={
            "id":
                "eq."
                + str(question_id)
        }
    )


def sync_question(question):

    if not supabase_configured():

        return False

    row = {

        "id":
            question["id"],

        "student_id":
            question["student_id"],

        "student_name":
            question["student_name"],

        "student_email":
            question["student_email"],

        "subject":
            question["subject"],

        "question":
            question["question"],

        "status":
            question["status"],

        "answer":
            question.get(
                "answer",
                ""
            ),

        "created_at":
            question["created_at"],

        "answered_at":
            question.get(
                "answered_at"
            ),

        "answered_by":
            question.get(
                "answered_by"
            )
    }

    result = supabase_insert(
        "koja_questions",
        row
    )

    return result is not None


# ============================================================
# CSRF PROTECTION
# ============================================================

def csrf_token():

    token = session.get(
        "_csrf_token"
    )

    if not token:

        token = secrets.token_urlsafe(32)

        session["_csrf_token"] = token

    return token


def validate_csrf():

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
# AUTHENTICATION
# ============================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get(
            "user_id"
        ):

            flash(
                "Please log in first.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


def is_admin_session():

    return (
        session.get("role")
        == "admin"
        and
        session.get("email", "")
        .strip()
        .lower()
        == ADMIN_EMAIL
    )


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get(
            "user_id"
        ):

            return redirect(
                url_for("login")
            )

        if not is_admin_session():

            flash(
                "Administrator access required.",
                "error"
            )

            return redirect(
                url_for("student_dashboard")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# FILE HELPERS
# ============================================================

def extension_of(filename):

    filename = (
        filename or ""
    ).strip()

    if "." not in filename:

        return ""

    return (
        filename
        .rsplit(".", 1)[1]
        .lower()
    )


def allowed_file(filename):

    return (
        extension_of(filename)
        in ALLOWED_EXTENSIONS
    )


def save_upload(
    uploaded_file,
    category
):

    if not uploaded_file:

        return None

    original_name = (
        uploaded_file.filename
        or ""
    ).strip()

    if not original_name:

        return None

    if not allowed_file(
        original_name
    ):

        return None

    extension = extension_of(
        original_name
    )

    stored_name = (
        str(uuid.uuid4())
        + "."
        + extension
    )

    if category == "student":

        category_dir = STUDENT_UPLOAD_DIR

    elif category == "admin":

        category_dir = ADMIN_UPLOAD_DIR

    else:

        return None

    destination = os.path.join(
        category_dir,
        stored_name
    )

    try:

        uploaded_file.save(
            destination
        )

    except Exception:

        return None

    return {

        "id":
            str(uuid.uuid4()),

        "original_name":
            original_name,

        "stored_name":
            stored_name,

        "category":
            category,

        "extension":
            extension,

        "is_image":
            extension
            in IMAGE_EXTENSIONS,

        "uploaded_at":
            now_iso()

    }


def save_multiple_uploads(
    files,
    category
):

    result = []

    for uploaded_file in files:

        if not uploaded_file:
            continue

        if not uploaded_file.filename:
            continue

        saved = save_upload(
            uploaded_file,
            category
        )

        if saved:

            result.append(saved)

    return result


# ============================================================
# QUESTIONS
# ============================================================

def get_questions():

    return read_json(
        QUESTIONS_FILE
    )


def save_questions(data):

    write_json(
        QUESTIONS_FILE,
        data
    )


def find_question(question_id):

    for question in get_questions():

        if (
            str(question.get("id"))
            == str(question_id)
        ):

            return question

    return None


# ============================================================
# ATTACHMENT HTML
# ============================================================

def attachment_html(
    attachments,
    viewer,
    question_id=None
):

    if not attachments:

        return """
        <p class="muted">
            No attachments.
        </p>
        """

    output = ""

    for attachment in attachments:

        stored = attachment.get(
            "stored_name"
        )

        if not stored:

            continue

        original = esc(
            attachment.get(
                "original_name",
                "Attachment"
            )
        )

        category = attachment.get(
            "category",
            ""
        )

        if viewer == "admin":

            route = url_for(
                "admin_file",
                category=category,
                filename=stored
            )

        else:

            route = url_for(
                "student_file",
                question_id=question_id,
                category=category,
                filename=stored
            )

        if attachment.get(
            "is_image"
        ):

            preview = f"""
            <img
                src="{esc(route)}"
                alt="Uploaded image"
                loading="lazy"
            >
            """

        else:

            preview = ""

        output += f"""

        <div class="attachment">

            <div class="attachment-title">
                📎 {original}
            </div>

            {preview}

            <br>

            <a
                class="btn"
                href="{esc(route)}"
                target="_blank"
                rel="noopener"
            >
                Open Attachment
            </a>

        </div>

        """

    return output


# ============================================================
# MAIN HTML TEMPLATE
# ============================================================

HTML = r"""

<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<meta
    name="theme-color"
    content="#101828"
>

<meta
    name="description"
    content="KOJA AFRICA academic question and answer portal"
>

<title>
{{ title }} - KOJA AFRICA
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

    background: #f4f7fb;

    color: #172033;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    line-height: 1.5;
}

nav {

    background: #101828;

    color: white;

    padding: 14px 18px;

    display: flex;

    align-items: center;

    justify-content: space-between;

    flex-wrap: wrap;

    gap: 10px;

    position: sticky;

    top: 0;

    z-index: 1000;
}

.logo {

    font-size: 22px;

    font-weight: 800;

    letter-spacing: .3px;
}

.k {
    color: #2196f3;
}

.o {
    color: #22c55e;
}

.j {
    color: #ef4444;
}

.a {
    color: #2563eb;
}

.navlinks {

    display: flex;

    flex-wrap: wrap;

    gap: 5px;
}

nav a {

    color: white;

    text-decoration: none;

    padding: 8px 10px;

    border-radius: 7px;

    font-size: 14px;
}

nav a:hover {

    background: #26354d;
}

.container {

    width: 94%;

    max-width: 1150px;

    margin: 22px auto;
}

.card {

    background: white;

    padding: 22px;

    margin-bottom: 20px;

    border-radius: 14px;

    box-shadow:
        0 5px 20px
        rgba(0,0,0,.06);
}

.hero {

    background:
        linear-gradient(
            135deg,
            #101828,
            #2563eb
        );

    color: white;

    padding: 30px;

    border-radius: 16px;

    margin-bottom: 20px;
}

.hero h1 {
    margin-top: 0;
}

.grid {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(190px, 1fr)
        );

    gap: 15px;

    margin-bottom: 20px;
}

.stat {

    background: #eef4ff;

    padding: 20px;

    border-radius: 12px;
}

.stat h2 {

    margin-top: 0;

    font-size: 28px;
}

input,
textarea,
select {

    width: 100%;

    padding: 12px;

    margin-top: 7px;

    margin-bottom: 15px;

    border:
        1px solid #d0d5dd;

    border-radius: 8px;

    font-size: 15px;

    background: white;
}

textarea {

    min-height: 180px;

    resize: vertical;
}

button,
.btn {

    display: inline-block;

    background: #2563eb;

    color: white;

    border: 0;

    padding: 11px 17px;

    border-radius: 8px;

    text-decoration: none;

    cursor: pointer;

    font-size: 14px;
}

button:hover,
.btn:hover {

    opacity: .9;
}

.green {
    background: #16a34a;
}

.red {
    background: #dc2626;
}

.dark {
    background: #111827;
}

.orange {
    background: #ea580c;
}

.purple {
    background: #7c3aed;
}

.badge {

    display: inline-block;

    padding: 5px 10px;

    border-radius: 20px;

    background: #e5e7eb;

    font-size: 12px;
}

.pending {

    background: #ffedd5;

    color: #9a3412;
}

.answered {

    background: #dcfce7;

    color: #166534;
}

.alert {

    background: #dcfce7;

    color: #166534;

    padding: 12px;

    border-radius: 8px;

    margin-bottom: 15px;
}

.alert.error {

    background: #fee2e2;

    color: #991b1b;
}

.question {

    white-space: pre-wrap;

    overflow-wrap: anywhere;

    line-height: 1.65;

    background: #f8fafc;

    padding: 15px;

    border-radius: 8px;
}

.answer {

    white-space: pre-wrap;

    overflow-wrap: anywhere;

    background: #f0fdf4;

    border-left:
        4px solid #16a34a;

    padding: 15px;

    border-radius: 7px;

    line-height: 1.65;
}

.muted {
    color: #667085;
}

.small {
    font-size: 13px;
}

.auth {

    max-width: 500px;

    margin:
        50px auto;
}

table {

    width: 100%;

    border-collapse:
        collapse;
}

th,
td {

    padding: 12px;

    border-bottom:
        1px solid #eee;

    text-align: left;

    vertical-align:
        top;
}

th {

    background: #f8fafc;
}

.upload-box {

    border:
        2px dashed #cbd5e1;

    border-radius: 12px;

    padding: 18px;

    background: #f8fafc;

    margin-bottom: 15px;
}

.upload-actions {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(160px, 1fr)
        );

    gap: 10px;

    margin-bottom: 10px;
}

.upload-button {

    display: block;

    text-align: center;

    background: #111827;

    color: white;

    padding: 12px;

    border-radius: 8px;

    cursor: pointer;

    font-size: 14px;
}

.upload-button.camera {

    background: #7c3aed;
}

.upload-button.document {

    background: #2563eb;
}

.upload-button.photo {

    background: #16a34a;
}

.file-input {

    display: none;
}

.file-list {

    margin-top: 10px;

    font-size: 13px;

    color: #475467;

    overflow-wrap: anywhere;
}

.attachment {

    border:
        1px solid #e4e7ec;

    border-radius: 10px;

    padding: 12px;

    margin-top: 10px;

    background: #fff;
}

.attachment img {

    max-width: 100%;

    max-height: 400px;

    border-radius: 8px;

    margin-top: 8px;
}

.attachment-title {

    font-weight: bold;

    margin-bottom: 7px;
}

.notice {

    padding: 12px;

    border-radius: 8px;

    background: #eff6ff;

    color: #1e40af;

    margin-bottom: 15px;
}

.search-box {

    display: grid;

    grid-template-columns:
        1fr auto;

    gap: 10px;
}

.search-box input {
    margin-bottom: 0;
}

.empty {

    text-align: center;

    padding: 30px;

    color: #667085;
}

.footer {

    text-align: center;

    color: #667085;

    padding: 30px 10px;

    font-size: 13px;
}

hr {

    border: 0;

    border-top:
        1px solid #eaecf0;

    margin: 25px 0;
}

@media(max-width:650px) {

    .container {
        width: 96%;
    }

    nav {
        position: relative;
    }

    .search-box {
        grid-template-columns: 1fr;
    }

    table {
        display: block;
        overflow-x: auto;
    }

}

</style>

</head>

<body>

<nav>

<div class="logo">

<span class="k">k</span><span class="o">o</span><span class="j">j</span><span class="a">a</span>
AFRICA

</div>

{% if session.get("user_id") %}

<div class="navlinks">

{% if session.get("role") == "admin" %}

<a href="{{ url_for('admin_dashboard') }}">
Admin
</a>

<a href="{{ url_for('admin_config') }}">
Configuration
</a>

{% else %}

<a href="{{ url_for('student_dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('ask_question') }}">
Ask Question
</a>

{% endif %}

<a href="{{ url_for('logout') }}">
Logout
</a>

</div>

{% endif %}

</nav>

<div class="container">

{% with messages =
get_flashed_messages(
with_categories=true
) %}

{% for category, message in messages %}

<div class="alert {{ category }}">

{{ message }}

</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</div>

<div class="footer">

KOJA AFRICA • Knowledge • Questions • Answers

</div>

</body>

</html>

"""


# ============================================================
# RENDER
# ============================================================

def render_page(
    title,
    content
):

    return render_template_string(

        HTML,

        title=title,

        content=content
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    if not session.get(
        "user_id"
    ):

        return redirect(
            url_for("login")
        )

    if is_admin_session():

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


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        validate_csrf()

        email = (
            request.form.get(
                "email",
                ""
            )
            .strip()
            .lower()
        )

        password = request.form.get(
            "password",
            ""
        )

        if not email or not password:

            flash(
                "Enter your email and password.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        # ----------------------------------------------------
        # ADMIN LOGIN
        # ----------------------------------------------------

        if (
            email == ADMIN_EMAIL
            and secrets.compare_digest(
                password,
                ADMIN_PASSWORD
            )
        ):

            session.clear()

            session["user_id"] = "ADMIN"
            session["email"] = ADMIN_EMAIL
            session["name"] = "KOJA Administrator"
            session["role"] = "admin"

            csrf_token()

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        # ----------------------------------------------------
        # STUDENT LOGIN
        # ----------------------------------------------------

        user = find_user(email)

        if (
            not user
            or user.get("role") != "student"
            or not verify_password(
                password,
                user.get(
                    "password",
                    ""
                )
            )
        ):

            flash(
                "Invalid email or password.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        session.clear()

        session["user_id"] = user["id"]
        session["email"] = user["email"]
        session["name"] = user["name"]
        session["role"] = "student"

        csrf_token()

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    token = csrf_token()

    content = f"""

    <div class="auth card">

        <h1>
            KOJA AFRICA
        </h1>

        <p class="muted">
            Knowledge • Questions • Answers
        </p>

        <form method="post">

            <input
                type="hidden"
                name="_csrf"
                value="{esc(token)}"
            >

            <label>
                Email
            </label>

            <input
                type="email"
                name="email"
                autocomplete="email"
                required
            >

            <label>
                Password
            </label>

            <input
                type="password"
                name="password"
                autocomplete="current-password"
                required
            >

            <button>
                Login
            </button>

        </form>

        <hr>

        <p>
            New student?
            <a href="{url_for('register')}">
                Create Student Account
            </a>
        </p>

    </div>

    """

    return render_page(
        "Login",
        content
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

        validate_csrf()

        name = (
            request.form.get(
                "name",
                ""
            )
            .strip()
        )

        email = (
            request.form.get(
                "email",
                ""
            )
            .strip()
            .lower()
        )

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

        if "@" not in email:

            flash(
                "Enter a valid email address.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if email == ADMIN_EMAIL:

            flash(
                "That email is reserved for the administrator.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
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

        if find_user(email):

            flash(
                "An account with this email already exists.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        data = get_users()

        data.append({

            "id":
                str(uuid.uuid4()),

            "name":
                name,

            "email":
                email,

            "password":
                hash_password(
                    password
                ),

            "role":
                "student",

            "created_at":
                now_iso()

        })

        save_users(data)

        flash(
            "Account created successfully. You can now log in.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    token = csrf_token()

    content = f"""

    <div class="auth card">

        <h1>
            Student Registration
        </h1>

        <form method="post">

            <input
                type="hidden"
                name="_csrf"
                value="{esc(token)}"
            >

            <label>
                Full Name
            </label>

            <input
                type="text"
                name="name"
                autocomplete="name"
                required
            >

            <label>
                Email
            </label>

            <input
                type="email"
                name="email"
                autocomplete="email"
                required
            >

            <label>
                Password
            </label>

            <input
                type="password"
                name="password"
                minlength="6"
                autocomplete="new-password"
                required
            >

            <label>
                Confirm Password
            </label>

            <input
                type="password"
                name="confirm"
                minlength="6"
                autocomplete="new-password"
                required
            >

            <button>
                Create Account
            </button>

        </form>

        <p>
            <a href="{url_for('login')}">
                Already have an account?
            </a>
        </p>

    </div>

    """

    return render_page(
        "Register",
        content
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/student")
@login_required
def student_dashboard():

    if is_admin_session():

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    user_id = session.get(
        "user_id"
    )

    my_questions = [

        q

        for q in get_questions()

        if str(
            q.get("student_id")
        )
        == str(user_id)

    ]

    my_questions.sort(

        key=lambda q:
            q.get(
                "created_at",
                ""
            ),

        reverse=True
    )

    total = len(
        my_questions
    )

    answered = sum(

        1

        for q in my_questions

        if q.get("status")
        == "Answered"

    )

    pending = sum(

        1

        for q in my_questions

        if q.get("status")
        == "Pending"

    )

    cards = ""

    for q in my_questions:

        subject = esc(
            q.get(
                "subject",
                "Question"
            )
        )

        status = esc(
            q.get(
                "status",
                "Pending"
            )
        )

        badge = (
            "answered"
            if status == "Answered"
            else "pending"
        )

        question_text = esc(
            q.get(
                "question",
                ""
            )
        )

        answer = q.get(
            "answer",
            ""
        )

        if answer:

            answer_html = f"""

            <div class="answer">
                {esc(answer)}
            </div>

            """

        else:

            answer_html = """

            <p class="muted">
                Waiting for administrator answer.
            </p>

            """

        student_files = attachment_html(

            q.get(
                "attachments",
                []
            ),

            "student",

            q.get("id")
        )

        admin_files = attachment_html(

            q.get(
                "answer_attachments",
                []
            ),

            "student",

            q.get("id")
        )

        cards += f"""

        <div class="card">

            <h2>
                {subject}
            </h2>

            <span class="badge {badge}">
                {status}
            </span>

            <p class="muted small">
                Submitted:
                {esc(
                    q.get(
                        "created_at",
                        ""
                    )
                )}
            </p>

            <h3>
                Your Question
            </h3>

            <div class="question">
                {question_text}
            </div>

            <h3>
                Your Attachments
            </h3>

            {student_files}

            <hr>

            <h3>
                Administrator Answer
            </h3>

            {answer_html}

            <h3>
                Administrator Attachments
            </h3>

            {admin_files}

        </div>

        """

    if not cards:

        cards = """

        <div class="card empty">

            <h2>
                No questions yet.
            </h2>

            <p>
                Submit your first academic question.
            </p>

            <a
                class="btn"
                href="/student/ask"
            >
                Ask Your First Question
            </a>

        </div>

        """

    content = f"""

    <div class="hero">

        <h1>
            Welcome, {esc(session.get("name"))}
        </h1>

        <p>
            Ask academic questions,
            upload assignments and receive
            answers from KOJA administrators.
        </p>

        <a
            class="btn"
            href="{url_for('ask_question')}"
        >
            Ask Question
        </a>

    </div>

    <div class="grid">

        <div class="stat">

            <h2>
                {total}
            </h2>

            <p>
                Total Questions
            </p>

        </div>

        <div class="stat">

            <h2>
                {answered}
            </h2>

            <p>
                Answered
            </p>

        </div>

        <div class="stat">

            <h2>
                {pending}
            </h2>

            <p>
                Pending
            </p>

        </div>

    </div>

    <h2>
        My Questions
    </h2>

    {cards}

    """

    return render_page(
        "Student Dashboard",
        content
    )


# ============================================================
# ASK QUESTION
# ============================================================

@app.route(
    "/student/ask",
    methods=["GET", "POST"]
)
@login_required
def ask_question():

    if is_admin_session():

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if request.method == "POST":

        validate_csrf()

        subject = (
            request.form.get(
                "subject",
                ""
            )
            .strip()
        )

        question_text = (
            request.form.get(
                "question",
                ""
            )
            .strip()
        )

        if len(subject) < 2:

            flash(
                "Enter a subject.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        if len(question_text) < 3:

            flash(
                "Enter your question.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        uploaded_files = request.files.getlist(
            "attachments"
        )

        attachments = save_multiple_uploads(

            uploaded_files,

            "student"
        )

        has_files = any(

            file
            and file.filename

            for file in uploaded_files

        )

        if (
            has_files
            and not attachments
        ):

            flash(
                "No valid attachment was uploaded. "
                "Check the file type and 10 MB limit.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        item = {

            "id":
                str(uuid.uuid4()),

            "student_id":
                session.get(
                    "user_id"
                ),

            "student_name":
                session.get(
                    "name"
                ),

            "student_email":
                session.get(
                    "email"
                ),

            "subject":
                subject,

            "question":
                question_text,

            "attachments":
                attachments,

            "status":
                "Pending",

            "answer":
                "",

            "answer_attachments":
                [],

            "answered_at":
                None,

            "answered_by":
                None,

            "created_at":
                now_iso()

        }

        data = get_questions()

        data.append(item)

        save_questions(data)

        sync_question(item)

        flash(
            "Question submitted successfully.",
            "success"
        )

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    token = csrf_token()

    content = f"""

    <div class="card">

        <h1>
            Ask a Question
        </h1>

        <p class="muted">
            Type your academic question.
            You can upload documents, photos,
            or take a new photo using your phone.
        </p>

        <form
            method="post"
            enctype="multipart/form-data"
        >

            <input
                type="hidden"
                name="_csrf"
                value="{esc(token)}"
            >

            <label>
                Subject
            </label>

            <input
                type="text"
                name="subject"
                placeholder="e.g. Chemistry"
                required
            >

            <label>
                Question
            </label>

            <textarea
                name="question"
                placeholder="Write your academic question..."
                required
            ></textarea>

            <div class="upload-box">

                <h3>
                    📎 Add Files
                </h3>

                <p class="small muted">
                    Maximum total request size: 10 MB.
                </p>

                <div class="upload-actions">

                    <label
                        class="upload-button camera"
                        for="cameraInput"
                    >
                        📷 Take Photo
                    </label>

                    <input
                        id="cameraInput"
                        class="file-input"
                        type="file"
                        name="attachments"
                        accept="image/*"
                        capture="environment"
                        onchange="showFiles()"
                    >

                    <label
                        class="upload-button photo"
                        for="photoInput"
                    >
                        🖼️ Choose Photos
                    </label>

                    <input
                        id="photoInput"
                        class="file-input"
                        type="file"
                        name="attachments"
                        accept="image/*"
                        multiple
                        onchange="showFiles()"
                    >

                    <label
                        class="upload-button document"
                        for="documentInput"
                    >
                        📄 Choose Documents
                    </label>

                    <input
                        id="documentInput"
                        class="file-input"
                        type="file"
                        name="attachments"
                        accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.webp"
                        multiple
                        onchange="showFiles()"
                    >

                </div>

                <div
                    id="fileList"
                    class="file-list"
                >
                    No files selected.
                </div>

            </div>

            <button type="submit">
                Submit Question
            </button>

        </form>

    </div>

    <script>

    function showFiles() {

        const inputs = [

            document.getElementById("cameraInput"),

            document.getElementById("photoInput"),

            document.getElementById("documentInput")

        ];

        let names = [];

        inputs.forEach(function(input) {

            if (!input) return;

            for (
                let i = 0;
                i < input.files.length;
                i++
            ) {

                names.push(
                    input.files[i].name
                );

            }

        });

        const list =
            document.getElementById("fileList");

        if (!names.length) {

            list.innerText =
                "No files selected.";

            return;
        }

        list.innerHTML =
            "<strong>Selected:</strong><br>"
            + names
                .map(function(name) {
                    return escapeHtml(name);
                })
                .join("<br>");

    }

    function escapeHtml(text) {

        const div =
            document.createElement("div");

        div.textContent = text;

        return div.innerHTML;

    }

    </script>

    """

    return render_page(
        "Ask Question",
        content
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    search = (
        request.args.get(
            "q",
            ""
        )
        .strip()
        .lower()
    )

    status_filter = (
        request.args.get(
            "status",
            ""
        )
        .strip()
        .lower()
    )

    data = get_questions()

    data.sort(

        key=lambda q:
            q.get(
                "created_at",
                ""
            ),

        reverse=True
    )

    total = len(data)

    pending = sum(

        1

        for q in data

        if q.get("status")
        == "Pending"

    )

    answered = sum(

        1

        for q in data

        if q.get("status")
        == "Answered"

    )

    filtered = []

    for q in data:

        searchable = " ".join([

            str(q.get(
                "student_name",
                ""
            )),

            str(q.get(
                "student_email",
                ""
            )),

            str(q.get(
                "subject",
                ""
            )),

            str(q.get(
                "question",
                ""
            ))

        ]).lower()

        if search and search not in searchable:
            continue

        if (
            status_filter
            and status_filter != "all"
            and q.get(
                "status",
                ""
            ).lower()
            != status_filter
        ):
            continue

        filtered.append(q)

    rows = ""

    for q in filtered:

        status = q.get(
            "status",
            "Pending"
        )

        badge = (
            "answered"
            if status == "Answered"
            else "pending"
        )

        question_preview = (
            str(
                q.get(
                    "question",
                    ""
                )
            )[:180]
        )

        rows += f"""

        <tr>

            <td>

                <strong>
                    {esc(
                        q.get(
                            "student_name",
                            ""
                        )
                    )}
                </strong>

                <br>

                <small>
                    {esc(
                        q.get(
                            "student_email",
                            ""
                        )
                    )}
                </small>

            </td>

            <td>
                {esc(
                    q.get(
                        "subject",
                        ""
                    )
                )}
            </td>

            <td>
                {esc(question_preview)}
                {"..." if len(
                    str(q.get("question",""))
                ) > 180 else ""}
            </td>

            <td>

                <span class="badge {badge}">
                    {esc(status)}
                </span>

                <br>

                <small>
                    📎
                    {len(
                        q.get(
                            "attachments",
                            []
                        )
                    )}
                    attachment(s)
                </small>

            </td>

            <td>

                <a
                    class="btn"
                    href="{url_for(
                        'admin_question',
                        question_id=q.get('id')
                    )}"
                >
                    Open
                </a>

            </td>

        </tr>

        """

    if not rows:

        rows = """

        <tr>

            <td colspan="5">
                No questions match your search.
            </td>

        </tr>

        """

    content = f"""

    <div class="hero">

        <h1>
            KOJA Administrator
        </h1>

        <p>
            Manage student academic questions,
            attachments and answers.
        </p>

    </div>

    <div class="grid">

        <div class="stat">

            <h2>
                {total}
            </h2>

            <p>
                Total Questions
            </p>

        </div>

        <div class="stat">

            <h2>
                {pending}
            </h2>

            <p>
                Pending
            </p>

        </div>

        <div class="stat">

            <h2>
                {answered}
            </h2>

            <p>
                Answered
            </p>

        </div>

        <div class="stat">

            <h2>
                ⚙️
            </h2>

            <p>
                <a href="{url_for('admin_config')}">
                    Configuration
                </a>
            </p>

        </div>

    </div>

    <div class="card">

        <h2>
            Student Questions
        </h2>

        <form
            method="get"
            class="search-box"
        >

            <input
                type="search"
                name="q"
                value="{esc(search)}"
                placeholder="Search student, subject or question..."
            >

            <select name="status">

                <option
                    value=""
                    {"selected" if not status_filter else ""}
                >
                    All Statuses
                </option>

                <option
                    value="pending"
                    {"selected" if status_filter == "pending" else ""}
                >
                    Pending
                </option>

                <option
                    value="answered"
                    {"selected" if status_filter == "answered" else ""}
                >
                    Answered
                </option>

            </select>

            <button type="submit">
                Search
            </button>

        </form>

    </div>

    <div class="card">

        <div style="overflow-x:auto">

            <table>

                <thead>

                    <tr>

                        <th>
                            Student
                        </th>

                        <th>
                            Subject
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

                </thead>

                <tbody>

                    {rows}

                </tbody>

            </table>

        </div>

    </div>

    """

    return render_page(
        "Administrator",
        content
    )


# ============================================================
# ADMIN QUESTION
# ============================================================

@app.route(
    "/admin/question/<question_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_question(question_id):

    data = get_questions()

    question = None
    question_index = None

    for index, item in enumerate(data):

        if (
            str(item.get("id"))
            == str(question_id)
        ):

            question = item
            question_index = index
            break

    if question is None:

        flash(
            "Question not found.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if request.method == "POST":

        validate_csrf()

        answer = (
            request.form.get(
                "answer",
                ""
            )
            .strip()
        )

        if len(answer) < 2:

            flash(
                "Write an answer first.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_question",
                    question_id=question_id
                )
            )

        uploaded_files = request.files.getlist(
            "answer_attachments"
        )

        new_attachments = (
            save_multiple_uploads(
                uploaded_files,
                "admin"
            )
        )

        has_files = any(

            file
            and file.filename

            for file in uploaded_files

        )

        if (
            has_files
            and not new_attachments
        ):

            flash(
                "The selected attachment could not be uploaded.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_question",
                    question_id=question_id
                )
            )

        old_attachments = question.get(
            "answer_attachments",
            []
        )

        question["answer"] = answer

        question["status"] = "Answered"

        question["answer_attachments"] = (
            old_attachments
            + new_attachments
        )

        question["answered_at"] = now_iso()

        question["answered_by"] = (
            session.get("email")
        )

        data[question_index] = question

        save_questions(data)

        if supabase_configured():

            supabase_update(

                "koja_questions",

                question_id,

                {

                    "answer":
                        answer,

                    "status":
                        "Answered",

                    "answered_at":
                        question[
                            "answered_at"
                        ],

                    "answered_by":
                        question[
                            "answered_by"
                        ]

                }
            )

        flash(
            "Answer sent to the student.",
            "success"
        )

        return redirect(
            url_for(
                "admin_question",
                question_id=question_id
            )
        )

    student_files = attachment_html(

        question.get(
            "attachments",
            []
        ),

        "admin"
    )

    admin_files = attachment_html(

        question.get(
            "answer_attachments",
            []
        ),

        "admin"
    )

    token = csrf_token()

    content = f"""

    <div class="card">

        <a href="{url_for('admin_dashboard')}">
            ← Back to Admin Dashboard
        </a>

        <h1>
            {esc(
                question.get(
                    "subject",
                    ""
                )
            )}
        </h1>

        <p>
            <strong>
                Student:
            </strong>

            {esc(
                question.get(
                    "student_name",
                    ""
                )
            )}
        </p>

        <p>
            <strong>
                Email:
            </strong>

            {esc(
                question.get(
                    "student_email",
                    ""
                )
            )}
        </p>

        <p>

            <strong>
                Status:
            </strong>

            <span class="badge">

                {esc(
                    question.get(
                        "status",
                        ""
                    )
                )}

            </span>

        </p>

        <p class="muted small">

            Submitted:
            {esc(
                question.get(
                    "created_at",
                    ""
                )
            )}

        </p>

        <hr>

        <h2>
            Student Question
        </h2>

        <div class="question">

            {esc(
                question.get(
                    "question",
                    ""
                )
            )}

        </div>

    </div>

    <div class="card">

        <h2>
            📎 Student Attachments
        </h2>

        {student_files}

    </div>

    <div class="card">

        <h2>
            ✍️ Answer Student
        </h2>

        <form
            method="post"
            enctype="multipart/form-data"
        >

            <input
                type="hidden"
                name="_csrf"
                value="{esc(token)}"
            >

            <label>
                Academic Answer
            </label>

            <textarea
                name="answer"
                required
                placeholder="Write the academic answer..."
            >{esc(
                question.get(
                    "answer",
                    ""
                )
            )}</textarea>

            <div class="upload-box">

                <h3>
                    📎 Attach to Answer
                </h3>

                <p class="small muted">
                    These files will become available
                    to the student after you send the answer.
                </p>

                <div class="upload-actions">

                    <label
                        class="upload-button camera"
                        for="adminCamera"
                    >
                        📷 Take Photo
                    </label>

                    <input
                        id="adminCamera"
                        class="file-input"
                        type="file"
                        name="answer_attachments"
                        accept="image/*"
                        capture="environment"
                        onchange="showAdminFiles()"
                    >

                    <label
                        class="upload-button photo"
                        for="adminPhoto"
                    >
                        🖼️ Choose Photos
                    </label>

                    <input
                        id="adminPhoto"
                        class="file-input"
                        type="file"
                        name="answer_attachments"
                        accept="image/*"
                        multiple
                        onchange="showAdminFiles()"
                    >

                    <label
                        class="upload-button document"
                        for="adminDocuments"
                    >
                        📄 Choose Documents
                    </label>

                    <input
                        id="adminDocuments"
                        class="file-input"
                        type="file"
                        name="answer_attachments"
                        accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.webp"
                        multiple
                        onchange="showAdminFiles()"
                    >

                </div>

                <div
                    id="adminFileList"
                    class="file-list"
                >
                    No files selected.
                </div>

            </div>

            <button
                type="submit"
                class="green"
            >
                Send Answer to Student
            </button>

        </form>

    </div>

    <div class="card">

        <h2>
            Previously Sent Attachments
        </h2>

        {admin_files}

    </div>

    <script>

    function showAdminFiles() {

        const inputs = [

            document.getElementById("adminCamera"),

            document.getElementById("adminPhoto"),

            document.getElementById("adminDocuments")

        ];

        let names = [];

        inputs.forEach(function(input) {

            if (!input) return;

            for (
                let i = 0;
                i < input.files.length;
                i++
            ) {

                names.push(
                    input.files[i].name
                );

            }

        });

        const list =
            document.getElementById(
                "adminFileList"
            );

        if (!names.length) {

            list.innerText =
                "No files selected.";

            return;
        }

        list.innerHTML =
            "<strong>Selected:</strong><br>"
            + names
                .map(function(name) {
                    return escapeHtml(name);
                })
                .join("<br>");

    }

    function escapeHtml(text) {

        const div =
            document.createElement("div");

        div.textContent = text;

        return div.innerHTML;

    }

    </script>

    """

    return render_page(
        "Answer Question",
        content
    )


# ============================================================
# ADMIN FILE ACCESS
# ============================================================

@app.route(
    "/admin/file/<category>/<filename>"
)
@admin_required
def admin_file(
    category,
    filename
):

    if category not in {
        "student",
        "admin"
    }:

        abort(404)

    # Confirm that the file actually belongs
    # to an attachment known to the system.
    found = False

    for question in get_questions():

        attachment_groups = [

            question.get(
                "attachments",
                []
            ),

            question.get(
                "answer_attachments",
                []
            )

        ]

        for group in attachment_groups:

            for attachment in group:

                if (
                    attachment.get(
                        "category"
                    )
                    == category
                    and
                    attachment.get(
                        "stored_name"
                    )
                    == filename
                ):

                    found = True
                    break

            if found:
                break

        if found:
            break

    if not found:

        abort(404)

    directory = (
        STUDENT_UPLOAD_DIR
        if category == "student"
        else ADMIN_UPLOAD_DIR
    )

    return send_from_directory(
        directory,
        filename,
        as_attachment=False
    )


# ============================================================
# STUDENT FILE ACCESS
# ============================================================

@app.route(
    "/student/file/<question_id>/<category>/<filename>"
)
@login_required
def student_file(
    question_id,
    category,
    filename
):

    if is_admin_session():

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    question = find_question(
        question_id
    )

    if not question:

        abort(404)

    # Student can only access
    # their own question.
    if str(
        question.get(
            "student_id"
        )
    ) != str(
        session.get(
            "user_id"
        )
    ):

        abort(403)

    if category == "student":

        attachments = question.get(
            "attachments",
            []
        )

    elif category == "admin":

        attachments = question.get(
            "answer_attachments",
            []
        )

    else:

        abort(404)

    authorized = False

    for attachment in attachments:

        if (
            attachment.get(
                "stored_name"
            )
            == filename
        ):

            authorized = True
            break

    if not authorized:

        abort(404)

    directory = (
        STUDENT_UPLOAD_DIR
        if category == "student"
        else ADMIN_UPLOAD_DIR
    )

    return send_from_directory(
        directory,
        filename,
        as_attachment=False
    )


# ============================================================
# ADMIN CONFIGURATION
# ============================================================

@app.route("/admin/config")
@admin_required
def admin_config():

    configured = (
        supabase_configured()
    )

    connected = (
        supabase_test()
        if configured
        else False
    )

    configured_class = (
        "answered"
        if configured
        else "pending"
    )

    connected_class = (
        "answered"
        if connected
        else "pending"
    )

    configured_text = (
        "YES"
        if configured
        else "NO"
    )

    connected_text = (
        "WORKING"
        if connected
        else "UNAVAILABLE"
    )

    content = f"""

    <div class="hero">

        <h1>
            System Configuration
        </h1>

        <p>
            KOJA AFRICA system status.
        </p>

    </div>

    <div class="card">

        <h2>
            Supabase
        </h2>

        <p>

            Configured:

            <span class="badge {configured_class}">
                {configured_text}
            </span>

        </p>

        <p>

            Connection:

            <span class="badge {connected_class}">
                {connected_text}
            </span>

        </p>

        <hr>

        <h3>
            Supabase URL
        </h3>

        <pre>{esc(
            SUPABASE_URL
            if SUPABASE_URL
            else "Not configured"
        )}</pre>

        <h3>
            Service Key
        </h3>

        <pre>{
            "Configured — hidden"
            if SUPABASE_SERVICE_KEY
            else "Not configured"
        }</pre>

        <h3>
            Storage Bucket
        </h3>

        <pre>{esc(STORAGE_BUCKET)}</pre>

    </div>

    <div class="card">

        <h2>
            Local Fallback
        </h2>

        <div class="notice">

            Local JSON database and local uploads
            are enabled.

        </div>

        <p>
            The application can operate without
            Supabase.
        </p>

        <p class="muted">

            Important:
            platforms such as Render may use
            ephemeral filesystems depending on
            the service configuration. For a
            production application, persistent
            external storage/database should be
            configured.

        </p>

    </div>

    <div class="card">

        <h2>
            Application Information
        </h2>

        <p>
            <strong>Application:</strong>
            KOJA AFRICA
        </p>

        <p>
            <strong>Storage:</strong>
            Local fallback + optional Supabase
        </p>

        <p>
            <strong>Maximum request:</strong>
            10 MB
        </p>

        <p>
            <strong>Allowed uploads:</strong>
            PDF, Word, Excel, PowerPoint,
            TXT, CSV and images
        </p>

    </div>

    """

    return render_page(
        "Configuration",
        content
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({

        "status":
            "ok",

        "application":
            "KOJA AFRICA",

        "supabase_configured":
            supabase_configured(),

        "supabase_connected":
            supabase_test()
            if supabase_configured()
            else False,

        "fallback":
            True

    })


# ============================================================
# ERROR: 413
# ============================================================

@app.errorhandler(413)
def too_large(error):

    flash(
        "Maximum upload size is 10 MB.",
        "error"
    )

    if session.get(
        "user_id"
    ):

        if is_admin_session():

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        return redirect(
            url_for(
                "ask_question"
            )
        )

    return redirect(
        url_for("login")
    )


# ============================================================
# ERROR: 400
# ============================================================

@app.errorhandler(400)
def bad_request(error):

    message = getattr(
        error,
        "description",
        "Bad request."
    )

    return render_page(

        "Bad Request",

        f"""

        <div class="card">

            <h1>
                Bad Request
            </h1>

            <p>
                {esc(message)}
            </p>

            <a
                class="btn"
                href="{url_for('home')}"
            >
                Go Home
            </a>

        </div>

        """

    ), 400


# ============================================================
# ERROR: 403
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    return render_page(

        "Access Denied",

        """

        <div class="card">

            <h1>
                Access Denied
            </h1>

            <p>
                You do not have permission
                to access this resource.
            </p>

            <a
                class="btn"
                href="/"
            >
                Go Home
            </a>

        </div>

        """

    ), 403


# ============================================================
# ERROR: 404
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return render_page(

        "Not Found",

        """

        <div class="card">

            <h1>
                Page Not Found
            </h1>

            <p>
                The requested page does not exist.
            </p>

            <a
                class="btn"
                href="/"
            >
                Go Home
            </a>

        </div>

        """

    ), 404


# ============================================================
# ERROR: 500
# ============================================================

@app.errorhandler(500)
def server_error(error):

    return render_page(

        "Portal Error",

        """

        <div class="card">

            <h1>
                KOJA is still running
            </h1>

            <p>
                An unexpected server error occurred.
                Please try again.
            </p>

            <a
                class="btn"
                href="/"
            >
                Go Home
            </a>

        </div>

        """

    ), 500


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "9999"
        )
    )

    print()
    print("=" * 60)
    print("KOJA AFRICA")
    print("Knowledge • Questions • Answers")
    print("=" * 60)
    print(
        "ADMIN EMAIL:",
        ADMIN_EMAIL
    )
    print(
        "SUPABASE:",
        supabase_configured()
    )
    print(
        "FALLBACK:",
        "ENABLED"
    )
    print(
        "UPLOADS:",
        UPLOAD_DIR
    )
    print(
        "PORT:",
        port
    )
    print("=" * 60)
    print()

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
