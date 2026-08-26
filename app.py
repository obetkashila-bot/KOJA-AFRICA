import os
import json
import uuid
import hashlib
import secrets
import threading
from datetime import datetime
from functools import wraps
from html import escape

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
    abort
)


# ============================================================
# KOJA AFRICA
# KNOWLEDGE • QUESTIONS • ANSWERS
#
# COMPLETE STUDENT + ADMIN ACADEMIC PORTAL
#
# FEATURES
# ------------------------------------------------------------
# STUDENT
#   - Register
#   - Login
#   - Dashboard
#   - Ask academic questions
#   - Upload documents
#   - Upload photos
#   - Take photos using phone camera
#   - View own questions
#   - View administrator answers
#   - View administrator attachments
#
# ADMIN
#   - Secure admin login
#   - Dashboard
#   - Pending Questions
#   - Previous Answers
#   - Read student questions
#   - View student attachments
#   - Answer questions
#   - Upload files with answers
#   - Take photos using camera
#   - Upload standalone academic resources
#   - View uploaded resources
#   - Configuration
#
# STORAGE
#   - Local fallback
#   - Optional Supabase
#
# DEPLOYMENT
#   - Render
#   - Railway
#   - VPS
#   - Local Python / Pydroid 3
#
# ============================================================


app = Flask(__name__)


# ============================================================
# SECURITY
# ============================================================

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_KOJA_SECRET_KEY_2026"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


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

RESOURCE_UPLOAD_DIR = os.path.join(
    UPLOAD_DIR,
    "resources"
)

os.makedirs(
    DATA_DIR,
    exist_ok=True
)

os.makedirs(
    UPLOAD_DIR,
    exist_ok=True
)

os.makedirs(
    STUDENT_UPLOAD_DIR,
    exist_ok=True
)

os.makedirs(
    ADMIN_UPLOAD_DIR,
    exist_ok=True
)

os.makedirs(
    RESOURCE_UPLOAD_DIR,
    exist_ok=True
)


# ============================================================
# JSON FILES
# ============================================================

USERS_FILE = os.path.join(
    DATA_DIR,
    "users.json"
)

QUESTIONS_FILE = os.path.join(
    DATA_DIR,
    "questions.json"
)

RESOURCES_FILE = os.path.join(
    DATA_DIR,
    "resources.json"
)

LOCK = threading.Lock()


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
# FILE TYPES
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
# DATABASE HELPERS
# ============================================================

def ensure_file(path, default):

    if not os.path.exists(path):

        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                default,
                f,
                indent=2,
                ensure_ascii=False
            )


ensure_file(
    USERS_FILE,
    []
)

ensure_file(
    QUESTIONS_FILE,
    []
)

ensure_file(
    RESOURCES_FILE,
    []
)


def read_json(path):

    try:

        with LOCK:

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as f:

                return json.load(f)

    except Exception:

        return []


def write_json(path, data):

    with LOCK:

        temp = path + ".tmp"

        with open(
            temp,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

        os.replace(
            temp,
            path
        )


# ============================================================
# PASSWORD SECURITY
# ============================================================

def hash_password(password):

    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200000
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
            200000
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

def users():

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

    for user in users():

        if (
            user.get(
                "email",
                ""
            ).lower()
            == email
        ):

            return user

    return None


def create_admin():

    data = users()

    found = None

    for user in data:

        if (
            user.get(
                "email",
                ""
            ).lower()
            == ADMIN_EMAIL
        ):

            found = user
            break

    if found:

        found["role"] = "admin"

        found["name"] = (
            "KOJA Administrator"
        )

        found["password"] = (
            hash_password(
                ADMIN_PASSWORD
            )
        )

        save_users(data)

        return

    admin = {

        "id":
            "ADMIN",

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
            datetime.utcnow().isoformat()
    }

    data.append(admin)

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
            "application/json"
    }


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


def supabase_request(
    method,
    endpoint,
    data=None
):

    if not supabase_configured():

        return None

    try:

        response = requests.request(
            method,
            SUPABASE_URL + endpoint,
            headers=supabase_headers(),
            json=data,
            timeout=8
        )

        if response.status_code >= 400:

            return None

        if not response.text:

            return {}

        return response.json()

    except Exception:

        return None


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
        + table
        + "?id=eq."
        + str(question_id),
        row
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
        or
        session.get(
            "email",
            ""
        ).strip().lower()
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
                url_for(
                    "student_dashboard"
                )
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
    file,
    category
):

    if not file:

        return None

    original_name = (
        file.filename or ""
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

        directory = STUDENT_UPLOAD_DIR

    elif category == "admin":

        directory = ADMIN_UPLOAD_DIR

    elif category == "resources":

        directory = RESOURCE_UPLOAD_DIR

    else:

        return None

    os.makedirs(
        directory,
        exist_ok=True
    )

    destination = os.path.join(
        directory,
        stored_name
    )

    file.save(
        destination
    )

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
            in IMAGE_EXTENSIONS
    }


def save_multiple_uploads(
    files,
    category
):

    attachments = []

    for file in files:

        if not file:

            continue

        if not file.filename:

            continue

        saved = save_upload(
            file,
            category
        )

        if saved:

            attachments.append(
                saved
            )

    return attachments


# ============================================================
# QUESTIONS
# ============================================================

def questions():

    return read_json(
        QUESTIONS_FILE
    )


def save_questions(data):

    write_json(
        QUESTIONS_FILE,
        data
    )


# ============================================================
# RESOURCES
# ============================================================

def resources():

    return read_json(
        RESOURCES_FILE
    )


def save_resources(data):

    write_json(
        RESOURCES_FILE,
        data
    )


# ============================================================
# SUPABASE QUESTION SYNC
# ============================================================

def sync_question(question):

    if not supabase_configured():

        return

    try:

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
                )
        }

        supabase_insert(
            "koja_questions",
            row
        )

    except Exception:

        pass


# ============================================================
# HTML
# ============================================================

HTML = """

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

<title>
{{ title }} - KOJA AFRICA
</title>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    background: #f4f7fb;

    color: #172033;

    font-family:
        Arial,
        Helvetica,
        sans-serif;
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

.teal {
    background: #0f766e;
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

    line-height: 1.65;

    background: #f8fafc;

    padding: 15px;

    border-radius: 8px;
}

.answer {

    white-space: pre-wrap;

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

.action-grid {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px, 1fr)
        );

    gap: 12px;

    margin-bottom: 20px;
}

.action-card {

    padding: 20px;

    border-radius: 12px;

    color: white;

    text-decoration: none;

    display: block;
}

.action-card h3 {

    margin-top: 0;

    font-size: 19px;
}

.action-card p {

    margin-bottom: 0;

    opacity: .9;

    font-size: 13px;
}

.resource-card {

    border:
        1px solid #e4e7ec;

    padding: 16px;

    border-radius: 10px;

    margin-bottom: 12px;

    background: #fff;
}

.resource-card h3 {
    margin-top: 0;
}

@media(max-width:650px) {

    .container {
        width: 96%;
    }

    table {
        display: block;
        overflow-x: auto;
    }

    nav {
        position: relative;
    }

}

</style>

</head>

<body>

<nav>

<div class="logo">

<span class="k">k</span>
<span class="o">o</span>
<span class="j">j</span>
<span class="a">a</span>

AFRICA

</div>

{% if session.get("user_id") %}

<div class="navlinks">

{% if session.get("role") == "admin" %}

<a href="/admin">
Admin
</a>

<a href="/admin/upload">
Upload
</a>

<a href="/admin/answers">
Previous Answers
</a>

<a href="/admin/config">
Configuration
</a>

{% else %}

<a href="/student">
Dashboard
</a>

<a href="/student/ask">
Ask Question
</a>

{% endif %}

<a href="/logout">
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

</body>

</html>

"""


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

        name = escape(
            attachment.get(
                "original_name",
                "Attachment"
            )
        )

        stored = attachment.get(
            "stored_name"
        )

        category = attachment.get(
            "category",
            ""
        )

        if not stored:

            continue

        if viewer == "admin":

            route = (
                "/admin/file/"
                + category
                + "/"
                + stored
            )

        else:

            route = (
                "/student/file/"
                + str(question_id)
                + "/"
                + category
                + "/"
                + stored
            )

        is_image = bool(
            attachment.get(
                "is_image"
            )
        )

        if is_image:

            preview = f"""
            <img
                src="{route}"
                alt="Uploaded image"
            >
            """

        else:

            preview = ""

        output += f"""

        <div class="attachment">

            <div class="attachment-title">
                📎 {name}
            </div>

            {preview}

            <br>

            <a
                class="btn"
                href="{route}"
                target="_blank"
            >
                Open Attachment
            </a>

        </div>

        """

    return output


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
            url_for("admin_dashboard")
        )

    return redirect(
        url_for("student_dashboard")
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

        # ADMIN LOGIN
        if (
            email == ADMIN_EMAIL
            and secrets.compare_digest(
                password,
                ADMIN_PASSWORD
            )
        ):

            session.clear()

            session["user_id"] = "ADMIN"

            session["email"] = (
                ADMIN_EMAIL
            )

            session["name"] = (
                "KOJA Administrator"
            )

            session["role"] = "admin"

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        # STUDENT LOGIN
        user = find_user(
            email
        )

        if not user:

            flash(
                "Invalid email or password.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        if not verify_password(
            password,
            user.get(
                "password",
                ""
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

        session["user_id"] = (
            user["id"]
        )

        session["email"] = (
            user["email"]
        )

        session["name"] = (
            user["name"]
        )

        session["role"] = "student"

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    content = """

    <div class="auth card">

        <h1>
            KOJA AFRICA
        </h1>

        <p class="muted">
            Knowledge • Questions • Answers
        </p>

        <form method="post">

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
            <a href="/register">
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

        data = users()

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
                datetime.utcnow().isoformat()
        })

        save_users(data)

        flash(
            "Account created successfully.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    content = """

    <div class="auth card">

        <h1>
            Student Registration
        </h1>

        <form method="post">

            <label>
                Full Name
            </label>

            <input
                type="text"
                name="name"
                required
            >

            <label>
                Email
            </label>

            <input
                type="email"
                name="email"
                required
            >

            <label>
                Password
            </label>

            <input
                type="password"
                name="password"
                minlength="6"
                required
            >

            <label>
                Confirm Password
            </label>

            <input
                type="password"
                name="confirm"
                minlength="6"
                required
            >

            <button>
                Create Account
            </button>

        </form>

        <p>
            <a href="/login">
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

    all_questions = questions()

    my_questions = [

        q

        for q in all_questions

        if q.get(
            "student_id"
        )
        == session.get(
            "user_id"
        )
    ]

    my_questions.sort(
        key=lambda q:
            q.get(
                "created_at",
                ""
            ),
        reverse=True
    )

    cards = ""

    for q in my_questions:

        status = q.get(
            "status",
            "Pending"
        )

        badge = (
            "answered"
            if status == "Answered"
            else "pending"
        )

        subject = escape(
            str(
                q.get(
                    "subject",
                    "Question"
                )
            )
        )

        question_text = escape(
            str(
                q.get(
                    "question",
                    ""
                )
            )
        )

        answer = escape(
            str(
                q.get(
                    "answer",
                    ""
                )
            )
        )

        if answer:

            answer_html = f"""
            <div class="answer">
                {answer}
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
                {escape(str(status))}
            </span>

            <p class="muted small">
                Submitted:
                {escape(str(q.get(
                    "created_at",
                    ""
                )))}
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

        <div class="card">

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

    content = f"""

    <div class="hero">

        <h1>
            Welcome,
            {escape(str(session.get("name")))}
        </h1>

        <p>
            Ask academic questions,
            upload assignments and
            receive answers.
        </p>

        <a
            class="btn"
            href="/student/ask"
        >
            Ask Question
        </a>

    </div>

    <div class="grid">

        <div class="stat">
            <h2>{total}</h2>
            <p>Total Questions</p>
        </div>

        <div class="stat">
            <h2>{answered}</h2>
            <p>Answered</p>
        </div>

        <div class="stat">
            <h2>{pending}</h2>
            <p>Pending</p>
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

        uploaded_files = (
            request.files.getlist(
                "attachments"
            )
        )

        attachments = save_multiple_uploads(
            uploaded_files,
            "student"
        )

        has_named_files = any(
            f and f.filename
            for f in uploaded_files
        )

        if (
            has_named_files
            and not attachments
        ):

            flash(
                "No valid attachment was uploaded.",
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
                datetime.utcnow().isoformat()
        }

        data = questions()

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

    content = """

    <div class="card">

        <h1>
            Ask a Question
        </h1>

        <p class="muted">
            Type your academic question.
            You can upload documents or use
            your phone camera.
        </p>

        <form
            method="post"
            enctype="multipart/form-data"
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
                placeholder="Write your question..."
                required
            ></textarea>

            <div class="upload-box">

                <h3>
                    📎 Add Files
                </h3>

                <p class="small muted">
                    Maximum total request size:
                    10 MB.
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
                        🖼️ Choose Photo
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

            document.getElementById(
                "cameraInput"
            ),

            document.getElementById(
                "photoInput"
            ),

            document.getElementById(
                "documentInput"
            )

        ];

        let names = [];

        inputs.forEach(
            function(input) {

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

            }
        );

        const list =
            document.getElementById(
                "fileList"
            );

        if (!names.length) {

            list.innerText =
                "No files selected.";

            return;

        }

        list.innerHTML =
            "<strong>Selected:</strong><br>"
            + names.join("<br>");

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

    data = questions()

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

    resources_count = len(
        resources()
    )

    content = f"""

    <div class="hero">

        <h1>
            KOJA Administrator
        </h1>

        <p>
            Manage student questions,
            answers and academic resources.
        </p>

    </div>

    <div class="action-grid">

        <a
            href="/admin/pending"
            class="action-card orange"
        >

            <h3>
                ⏳ Pending Questions
            </h3>

            <p>
                View questions waiting
                for an administrator answer.
            </p>

        </a>

        <a
            href="/admin/answers"
            class="action-card green"
        >

            <h3>
                ✅ Previous Answers
            </h3>

            <p>
                View questions that have
                already been answered.
            </p>

        </a>

        <a
            href="/admin/upload"
            class="action-card purple"
        >

            <h3>
                📤 Upload Resource
            </h3>

            <p>
                Upload academic documents,
                photos and learning resources.
            </p>

        </a>

        <a
            href="/admin/resources"
            class="action-card teal"
        >

            <h3>
                📚 Resources
            </h3>

            <p>
                View files uploaded directly
                by the administrator.
            </p>

        </a>

        <a
            href="/admin/config"
            class="action-card dark"
        >

            <h3>
                ⚙️ Configuration
            </h3>

            <p>
                Check Supabase and system
                configuration.
            </p>

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
                {resources_count}
            </h2>

            <p>
                Uploaded Resources
            </p>

        </div>

    </div>

    <div class="card">

        <h2>
            Recent Questions
        </h2>

        <p class="muted">
            Use the buttons above to manage
            pending questions and previous answers.
        </p>

    </div>

    """

    return render_page(
        "Administrator",
        content
    )


# ============================================================
# ADMIN PENDING QUESTIONS
# ============================================================

@app.route("/admin/pending")
@admin_required
def admin_pending():

    data = [

        q

        for q in questions()

        if q.get(
            "status"
        )
        != "Answered"

    ]

    data.sort(
        key=lambda q:
            q.get(
                "created_at",
                ""
            ),
        reverse=True
    )

    cards = ""

    for q in data:

        student_name = escape(
            str(
                q.get(
                    "student_name",
                    ""
                )
            )
        )

        subject = escape(
            str(
                q.get(
                    "subject",
                    ""
                )
            )
        )

        question_text = escape(
            str(
                q.get(
                    "question",
                    ""
                )
            )
        )

        cards += f"""

        <div class="card">

            <span class="badge pending">
                Pending
            </span>

            <h2>
                {subject}
            </h2>

            <p>
                <strong>
                    Student:
                </strong>

                {student_name}
            </p>

            <div class="question">
                {question_text[:1000]}
            </div>

            <br>

            <a
                class="btn orange"
                href="/admin/question/{q.get("id")}"
            >
                Open & Answer
            </a>

        </div>

        """

    if not cards:

        cards = """

        <div class="card">

            <h2>
                No pending questions.
            </h2>

            <p class="muted">
                All student questions have
                been answered.
            </p>

        </div>

        """

    content = f"""

    <div class="card">

        <a href="/admin">
            ← Admin Dashboard
        </a>

        <h1>
            ⏳ Pending Questions
        </h1>

        <p class="muted">
            These questions still require
            administrator attention.
        </p>

    </div>

    {cards}

    """

    return render_page(
        "Pending Questions",
        content
    )


# ============================================================
# ADMIN PREVIOUS ANSWERS
# ============================================================

@app.route("/admin/answers")
@admin_required
def admin_answers():

    data = [

        q

        for q in questions()

        if q.get(
            "status"
        )
        == "Answered"

    ]

    data.sort(
        key=lambda q:
            q.get(
                "answered_at",
                q.get(
                    "created_at",
                    ""
                )
            ),
        reverse=True
    )

    cards = ""

    for q in data:

        student_name = escape(
            str(
                q.get(
                    "student_name",
                    ""
                )
            )
        )

        subject = escape(
            str(
                q.get(
                    "subject",
                    ""
                )
            )
        )

        answer = escape(
            str(
                q.get(
                    "answer",
                    ""
                )
            )
        )

        answer_attachments = len(
            q.get(
                "answer_attachments",
                []
            )
        )

        cards += f"""

        <div class="card">

            <span class="badge answered">
                Answered
            </span>

            <h2>
                {subject}
            </h2>

            <p>
                <strong>
                    Student:
                </strong>

                {student_name}
            </p>

            <p class="muted small">
                Answered:
                {escape(str(
                    q.get(
                        "answered_at",
                        ""
                    )
                ))}
            </p>

            <h3>
                Answer
            </h3>

            <div class="answer">
                {answer}
            </div>

            <p class="small muted">
                📎 {answer_attachments}
                answer attachment(s)
            </p>

            <a
                class="btn green"
                href="/admin/question/{q.get("id")}"
            >
                Open Answer
            </a>

        </div>

        """

    if not cards:

        cards = """

        <div class="card">

            <h2>
                No previous answers.
            </h2>

            <p class="muted">
                Answered questions will
                appear here.
            </p>

        </div>

        """

    content = f"""

    <div class="card">

        <a href="/admin">
            ← Admin Dashboard
        </a>

        <h1>
            ✅ Previous Answers
        </h1>

        <p class="muted">
            This page contains answered
            student questions only.
        </p>

    </div>

    {cards}

    """

    return render_page(
        "Previous Answers",
        content
    )


# ============================================================
# ADMIN QUESTION / ANSWER
# ============================================================

@app.route(
    "/admin/question/<question_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_question(
    question_id
):

    data = questions()

    question = None

    for item in data:

        if (
            item.get("id")
            == question_id
        ):

            question = item
            break

    if not question:

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

        uploaded_files = (
            request.files.getlist(
                "answer_attachments"
            )
        )

        new_attachments = (
            save_multiple_uploads(
                uploaded_files,
                "admin"
            )
        )

        has_named_files = any(
            f and f.filename
            for f in uploaded_files
        )

        if (
            has_named_files
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

        question["status"] = (
            "Answered"
        )

        question["answer_attachments"] = (
            old_attachments
            + new_attachments
        )

        question["answered_at"] = (
            datetime.utcnow().isoformat()
        )

        question["answered_by"] = (
            session.get(
                "email"
            )
        )

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

    student_attachments = (
        question.get(
            "attachments",
            []
        )
    )

    student_attachment_html = (
        attachment_html(
            student_attachments,
            "admin"
        )
    )

    admin_attachments = (
        question.get(
            "answer_attachments",
            []
        )
    )

    admin_attachment_html = (
        attachment_html(
            admin_attachments,
            "admin"
        )
    )

    subject = escape(
        str(
            question.get(
                "subject",
                ""
            )
        )
    )

    student_name = escape(
        str(
            question.get(
                "student_name",
                ""
            )
        )
    )

    student_email = escape(
        str(
            question.get(
                "student_email",
                ""
            )
        )
    )

    question_text = escape(
        str(
            question.get(
                "question",
                ""
            )
        )
    )

    answer_text = escape(
        str(
            question.get(
                "answer",
                ""
            )
        )
    )

    status = escape(
        str(
            question.get(
                "status",
                "Pending"
            )
        )
    )

    content = f"""

    <div class="card">

        <a href="/admin/pending">
            ← Pending Questions
        </a>

        <h1>
            {subject}
        </h1>

        <p>
            <strong>
                Student:
            </strong>

            {student_name}
        </p>

        <p>
            <strong>
                Email:
            </strong>

            {student_email}
        </p>

        <p>

            <strong>
                Status:
            </strong>

            <span class="badge">
                {status}
            </span>

        </p>

        <p class="muted small">
            Submitted:
            {escape(str(
                question.get(
                    "created_at",
                    ""
                )
            ))}
        </p>

        <hr>

        <h2>
            Student Question
        </h2>

        <div class="question">
            {question_text}
        </div>

    </div>

    <div class="card">

        <h2>
            📎 Student Attachments
        </h2>

        {student_attachment_html}

    </div>

    <div class="card">

        <h2>
            ✍️ Answer Student
        </h2>

        <form
            method="post"
            enctype="multipart/form-data"
        >

            <label>
                Academic Answer
            </label>

            <textarea
                name="answer"
                required
                placeholder="Write the academic answer..."
            >{answer_text}</textarea>

            <div class="upload-box">

                <h3>
                    📤 Upload With Answer
                </h3>

                <p class="small muted">
                    These files will be available
                    to this student after you
                    send the answer.
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
                        🖼️ Choose Photo
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

        {admin_attachment_html}

    </div>

    <script>

    function showAdminFiles() {

        const inputs = [

            document.getElementById(
                "adminCamera"
            ),

            document.getElementById(
                "adminPhoto"
            ),

            document.getElementById(
                "adminDocuments"
            )

        ];

        let names = [];

        inputs.forEach(
            function(input) {

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

            }
        );

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
            + names.join("<br>");

    }

    </script>

    """

    return render_page(
        "Answer Question",
        content
    )


# ============================================================
# ADMIN STANDALONE UPLOAD
# ============================================================

@app.route(
    "/admin/upload",
    methods=["GET", "POST"]
)
@admin_required
def admin_upload():

    if request.method == "POST":

        title = (
            request.form.get(
                "title",
                ""
            )
            .strip()
        )

        subject = (
            request.form.get(
                "subject",
                ""
            )
            .strip()
        )

        description = (
            request.form.get(
                "description",
                ""
            )
            .strip()
        )

        files = request.files.getlist(
            "resource_files"
        )

        if not title:

            flash(
                "Enter a resource title.",
                "error"
            )

            return redirect(
                url_for("admin_upload")
            )

        if not files:

            flash(
                "Choose at least one file.",
                "error"
            )

            return redirect(
                url_for("admin_upload")
            )

        saved_files = (
            save_multiple_uploads(
                files,
                "resources"
            )
        )

        if not saved_files:

            flash(
                "No valid file was uploaded.",
                "error"
            )

            return redirect(
                url_for("admin_upload")
            )

        resource = {

            "id":
                str(uuid.uuid4()),

            "title":
                title,

            "subject":
                subject,

            "description":
                description,

            "files":
                saved_files,

            "uploaded_by":
                session.get(
                    "email"
                ),

            "created_at":
                datetime.utcnow().isoformat()
        }

        data = resources()

        data.append(
            resource
        )

        save_resources(data)

        flash(
            "Resource uploaded successfully.",
            "success"
        )

        return redirect(
            url_for(
                "admin_resources"
            )
        )

    content = """

    <div class="card">

        <a href="/admin">
            ← Admin Dashboard
        </a>

        <h1>
            📤 Upload Academic Resource
        </h1>

        <p class="muted">
            Upload a document, PDF, image,
            spreadsheet or presentation directly
            from the administrator panel.
        </p>

        <form
            method="post"
            enctype="multipart/form-data"
        >

            <label>
                Resource Title
            </label>

            <input
                type="text"
                name="title"
                placeholder="e.g. Grade 10 Chemistry Notes"
                required
            >

            <label>
                Subject
            </label>

            <input
                type="text"
                name="subject"
                placeholder="e.g. Chemistry"
            >

            <label>
                Description
            </label>

            <textarea
                name="description"
                placeholder="Describe this resource..."
            ></textarea>

            <div class="upload-box">

                <h3>
                    📎 Select Resource
                </h3>

                <div class="upload-actions">

                    <label
                        class="upload-button camera"
                        for="resourceCamera"
                    >
                        📷 Take Photo
                    </label>

                    <input
                        id="resourceCamera"
                        class="file-input"
                        type="file"
                        name="resource_files"
                        accept="image/*"
                        capture="environment"
                        onchange="showResourceFiles()"
                    >

                    <label
                        class="upload-button photo"
                        for="resourcePhoto"
                    >
                        🖼️ Choose Photo
                    </label>

                    <input
                        id="resourcePhoto"
                        class="file-input"
                        type="file"
                        name="resource_files"
                        accept="image/*"
                        multiple
                        onchange="showResourceFiles()"
                    >

                    <label
                        class="upload-button document"
                        for="resourceDocuments"
                    >
                        📄 Choose Documents
                    </label>

                    <input
                        id="resourceDocuments"
                        class="file-input"
                        type="file"
                        name="resource_files"
                        accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.webp"
                        multiple
                        onchange="showResourceFiles()"
                    >

                </div>

                <div
                    id="resourceFileList"
                    class="file-list"
                >
                    No files selected.
                </div>

            </div>

            <button
                type="submit"
                class="purple"
            >
                Upload Resource
            </button>

        </form>

    </div>

    <script>

    function showResourceFiles() {

        const inputs = [

            document.getElementById(
                "resourceCamera"
            ),

            document.getElementById(
                "resourcePhoto"
            ),

            document.getElementById(
                "resourceDocuments"
            )

        ];

        let names = [];

        inputs.forEach(
            function(input) {

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

            }
        );

        const list =
            document.getElementById(
                "resourceFileList"
            );

        if (!names.length) {

            list.innerText =
                "No files selected.";

            return;
        }

        list.innerHTML =
            "<strong>Selected:</strong><br>"
            + names.join("<br>");

    }

    </script>

    """

    return render_page(
        "Upload Resource",
        content
    )


# ============================================================
# ADMIN RESOURCES
# ============================================================

@app.route("/admin/resources")
@admin_required
def admin_resources():

    data = resources()

    data.sort(
        key=lambda r:
            r.get(
                "created_at",
                ""
            ),
        reverse=True
    )

    cards = ""

    for resource in data:

        title = escape(
            str(
                resource.get(
                    "title",
                    "Resource"
                )
            )
        )

        subject = escape(
            str(
                resource.get(
                    "subject",
                    ""
                )
            )
        )

        description = escape(
            str(
                resource.get(
                    "description",
                    ""
                )
            )
        )

        files_html = ""

        for file in resource.get(
            "files",
            []
        ):

            stored = file.get(
                "stored_name"
            )

            if not stored:
                continue

            name = escape(
                str(
                    file.get(
                        "original_name",
                        "File"
                    )
                )
            )

            route = (
                "/admin/resource-file/"
                + stored
            )

            files_html += f"""

            <div class="attachment">

                <div class="attachment-title">
                    📎 {name}
                </div>

                <a
                    class="btn teal"
                    href="{route}"
                    target="_blank"
                >
                    Open File
                </a>

            </div>

            """

        cards += f"""

        <div class="resource-card">

            <h3>
                📚 {title}
            </h3>

            <p>
                <strong>
                    Subject:
                </strong>

                {subject or "General"}
            </p>

            <p>
                {description}
            </p>

            <p class="muted small">

                Uploaded:
                {escape(str(
                    resource.get(
                        "created_at",
                        ""
                    )
                ))}

            </p>

            {files_html}

        </div>

        """

    if not cards:

        cards = """

        <div class="card">

            <h2>
                No resources uploaded.
            </h2>

            <a
                class="btn purple"
                href="/admin/upload"
            >
                Upload First Resource
            </a>

        </div>

        """

    content = f"""

    <div class="card">

        <a href="/admin">
            ← Admin Dashboard
        </a>

        <h1>
            📚 Academic Resources
        </h1>

        <p class="muted">
            Resources uploaded directly
            from the administrator panel.
        </p>

        <a
            class="btn purple"
            href="/admin/upload"
        >
            📤 Upload New Resource
        </a>

    </div>

    {cards}

    """

    return render_page(
        "Resources",
        content
    )


# ============================================================
# ADMIN RESOURCE FILE
# ============================================================

@app.route(
    "/admin/resource-file/<filename>"
)
@admin_required
def admin_resource_file(
    filename
):

    allowed = False

    for resource in resources():

        for file in resource.get(
            "files",
            []
        ):

            if (
                file.get(
                    "stored_name"
                )
                == filename
            ):

                allowed = True
                break

        if allowed:
            break

    if not allowed:

        abort(404)

    return send_from_directory(
        RESOURCE_UPLOAD_DIR,
        filename
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

    if category == "student":

        directory = STUDENT_UPLOAD_DIR

    elif category == "admin":

        directory = ADMIN_UPLOAD_DIR

    else:

        abort(404)

    allowed = False

    data = questions()

    for q in data:

        for attachment in q.get(
            "attachments",
            []
        ):

            if (
                attachment.get(
                    "stored_name"
                )
                == filename
                and category == "student"
            ):

                allowed = True
                break

        for attachment in q.get(
            "answer_attachments",
            []
        ):

            if (
                attachment.get(
                    "stored_name"
                )
                == filename
                and category == "admin"
            ):

                allowed = True
                break

        if allowed:
            break

    if not allowed:

        abort(404)

    return send_from_directory(
        directory,
        filename
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

    question = None

    for item in questions():

        if (
            item.get("id")
            == question_id
        ):

            question = item
            break

    if not question:

        return (
            "File not found",
            404
        )

    if (
        question.get(
            "student_id"
        )
        != session.get(
            "user_id"
        )
    ):

        return (
            "Access denied",
            403
        )

    if category == "student":

        attachments = (
            question.get(
                "attachments",
                []
            )
        )

        directory = (
            STUDENT_UPLOAD_DIR
        )

    elif category == "admin":

        attachments = (
            question.get(
                "answer_attachments",
                []
            )
        )

        directory = (
            ADMIN_UPLOAD_DIR
        )

    else:

        return (
            "Invalid file category",
            404
        )

    allowed = False

    for attachment in attachments:

        if (
            attachment.get(
                "stored_name"
            )
            == filename
        ):

            allowed = True
            break

    if not allowed:

        return (
            "File not found",
            404
        )

    return send_from_directory(
        directory,
        filename
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

    config_badge = (
        "answered"
        if configured
        else "pending"
    )

    connection_badge = (
        "answered"
        if connected
        else "pending"
    )

    content = f"""

    <div class="hero">

        <h1>
            System Configuration
        </h1>

        <p>
            Administrator configuration
            and connection status.
        </p>

    </div>

    <div class="card">

        <h2>
            Supabase
        </h2>

        <p>

            Configured:

            <span class="badge {config_badge}">

                {
                    "YES"
                    if configured
                    else "NO"
                }

            </span>

        </p>

        <p>

            Connection:

            <span class="badge {connection_badge}">

                {
                    "WORKING"
                    if connected
                    else "UNAVAILABLE"
                }

            </span>

        </p>

        <hr>

        <h3>
            Supabase URL
        </h3>

        <pre>
{
    escape(
        SUPABASE_URL
    )
    if SUPABASE_URL
    else "Not configured"
}
        </pre>

        <h3>
            Service Key
        </h3>

        <pre>
{
    "Configured — hidden"
    if SUPABASE_SERVICE_KEY
    else "Not configured"
}
        </pre>

        <h3>
            Storage Bucket
        </h3>

        <pre>
{escape(STORAGE_BUCKET)}
        </pre>

    </div>

    <div class="card">

        <h2>
            Fallback Storage
        </h2>

        <div class="notice">

            KOJA can continue operating
            using local storage when
            Supabase is unavailable.

        </div>

        <p>

            Student accounts,
            questions and uploaded files
            are stored locally.

        </p>

        <p class="muted">

            On hosting platforms such as
            Render, local filesystem storage
            may not be permanent. Configure
            persistent database/storage for
            production.

        </p>

    </div>

    """

    return render_page(
        "Configuration",
        content
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return {

        "status":
            "ok",

        "application":
            "KOJA AFRICA",

        "supabase_configured":
            supabase_configured(),

        "supabase_connected":
            supabase_test(),

        "fallback":
            True

    }


# ============================================================
# 413
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
# 404
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
# 500
# ============================================================

@app.errorhandler(500)
def server_error(error):

    return render_page(

        "Portal Error",

        """

        <div class="card">

            <h1>
                KOJA encountered an error
            </h1>

            <p>
                An unexpected error occurred.
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
        "ADMIN:",
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
