import os
import json
import uuid
import hashlib
import secrets
import threading
from datetime import datetime
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
    abort
)

# ============================================================
# KOJA AFRICA
# KNOWLEDGE • QUESTIONS • ANSWERS
#
# COMPLETE STUDENT + ADMIN PORTAL
#
# ADMIN:
#   Dashboard
#   Questions
#   Previous Answers
#   Open Question
#   Answer Question
#   Upload With Answer
#   Take Photo
#   Choose Photo
#   Choose Documents
#
# STUDENT:
#   Register
#   Login
#   Dashboard
#   Ask Question
#   Upload documents/photos
#   Receive answers
#   Receive administrator attachments
#
# STORAGE:
#   Local JSON + local uploads
#   Optional Supabase connection
# ============================================================

app = Flask(__name__)

# ============================================================
# SECURITY
# ============================================================

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "koja-africa-change-this-secret"
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
# HTML ESCAPING
# ============================================================

def esc(value):
    """
    Safely escape values before putting them
    into generated HTML.
    """
    from markupsafe import escape
    return str(escape(value if value is not None else ""))


# ============================================================
# JSON DATABASE
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


def read_json(path):

    try:

        with LOCK:

            with open(
                path,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

                if isinstance(data, list):
                    return data

                return []

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

    return salt + "$" + digest.hex()


def verify_password(password, stored):

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
    return read_json(USERS_FILE)


def save_users(data):
    write_json(USERS_FILE, data)


def find_user(email):

    email = (
        email or ""
    ).strip().lower()

    for user in users():

        if (
            user.get("email", "")
            .strip()
            .lower()
            == email
        ):

            return user

    return None


def create_admin():

    data = users()

    found = None

    for user in data:

        if (
            user.get("email", "")
            .strip()
            .lower()
            == ADMIN_EMAIL
        ):

            found = user
            break

    if found:

        found["role"] = "admin"
        found["name"] = "KOJA Administrator"

        found["password"] = hash_password(
            ADMIN_PASSWORD
        )

        save_users(data)

        return

    data.append({

        "id": str(uuid.uuid4()),

        "name": "KOJA Administrator",

        "email": ADMIN_EMAIL,

        "password": hash_password(
            ADMIN_PASSWORD
        ),

        "role": "admin",

        "created_at":
            datetime.utcnow().isoformat()

    })

    save_users(data)


create_admin()


# ============================================================
# QUESTIONS DATABASE
# ============================================================

def questions():
    return read_json(QUESTIONS_FILE)


def save_questions(data):
    write_json(
        QUESTIONS_FILE,
        data
    )


def find_question(question_id):

    for question in questions():

        if str(
            question.get("id")
        ) == str(question_id):

            return question

    return None


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

            SUPABASE_URL
            + endpoint,

            headers=supabase_headers(),

            json=data,

            timeout=10

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
# AUTH
# ============================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("user_id"):

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

        if not session.get("user_id"):

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
# FILE FUNCTIONS
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

    else:

        return None

    destination = os.path.join(
        directory,
        stored_name
    )

    try:

        file.save(destination)

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
            in IMAGE_EXTENSIONS

    }


def save_multiple_uploads(
    files,
    category
):

    result = []

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
            result.append(saved)

    return result


# ============================================================
# ATTACHMENT DISPLAY
# ============================================================

def attachment_html(
    attachments,
    viewer,
    question_id=None
):

    if not attachments:

        return """
        <div class="empty-files">
            No attachments.
        </div>
        """

    html = ""

    for attachment in attachments:

        name = esc(
            attachment.get(
                "original_name",
                "Attachment"
            )
        )

        stored = attachment.get(
            "stored_name",
            ""
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

        if attachment.get(
            "is_image"
        ):

            preview = f"""
            <img
                class="attachment-image"
                src="{route}"
                alt="Uploaded image"
            >
            """

        else:

            preview = ""

        html += f"""

        <div class="attachment">

            <div class="attachment-name">
                📎 {name}
            </div>

            {preview}

            <a
                class="btn small-btn"
                href="{route}"
                target="_blank"
            >
                Open File
            </a>

        </div>

        """

    return html


# ============================================================
# MAIN HTML
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

    padding: 13px 18px;

    display: flex;

    justify-content: space-between;

    align-items: center;

    flex-wrap: wrap;

    gap: 10px;

    position: sticky;

    top: 0;

    z-index: 999;

}

.logo {

    font-size: 23px;

    font-weight: 900;

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

    gap: 6px;

    flex-wrap: wrap;

}

nav a {

    color: white;

    text-decoration: none;

    padding: 8px 11px;

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

    font-size: 30px;

}

.stat-button {

    display: block;

    text-decoration: none;

    color: inherit;

}

.stat-button:hover {

    transform: translateY(-2px);

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

    min-height: 190px;

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

    background: #16a34a !important;

}

.red {

    background: #dc2626 !important;

}

.dark {

    background: #111827 !important;

}

.orange {

    background: #ea580c !important;

}

.purple {

    background: #7c3aed !important;

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

    line-height: 1.7;

    background: #f8fafc;

    padding: 16px;

    border-radius: 9px;

}

.answer {

    white-space: pre-wrap;

    background: #f0fdf4;

    border-left:
        4px solid #16a34a;

    padding: 16px;

    border-radius: 8px;

    line-height: 1.7;

}

.muted {

    color: #667085;

}

.small {

    font-size: 13px;

}

.auth {

    max-width: 500px;

    margin: 50px auto;

}

table {

    width: 100%;

    border-collapse: collapse;

}

th,
td {

    padding: 12px;

    border-bottom:
        1px solid #eee;

    text-align: left;

    vertical-align: top;

}

th {

    background: #f8fafc;

}

.upload-box {

    border:
        2px dashed #cbd5e1;

    border-radius: 12px;

    padding: 20px;

    background: #f8fafc;

    margin: 15px 0;

}

.upload-actions {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(170px, 1fr)
        );

    gap: 10px;

}

.upload-button {

    display: block;

    text-align: center;

    color: white;

    padding: 14px;

    border-radius: 9px;

    cursor: pointer;

    font-size: 14px;

    font-weight: bold;

}

.camera {

    background: #7c3aed;

}

.photo {

    background: #16a34a;

}

.document {

    background: #2563eb;

}

.file-input {

    display: none;

}

.file-list {

    margin-top: 14px;

    font-size: 13px;

    color: #475467;

    background: white;

    padding: 10px;

    border-radius: 8px;

}

.attachment {

    border:
        1px solid #e4e7ec;

    border-radius: 10px;

    padding: 13px;

    margin-top: 10px;

    background: #fff;

}

.attachment-name {

    font-weight: bold;

    margin-bottom: 10px;

}

.attachment-image {

    max-width: 100%;

    max-height: 450px;

    display: block;

    border-radius: 8px;

    margin-bottom: 10px;

}

.small-btn {

    padding: 8px 12px;

    font-size: 13px;

}

.empty-files {

    color: #667085;

    padding: 10px 0;

}

.notice {

    padding: 13px;

    border-radius: 8px;

    background: #eff6ff;

    color: #1e40af;

    margin-bottom: 15px;

}

.admin-action-bar {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px, 1fr)
        );

    gap: 12px;

    margin-bottom: 20px;

}

.admin-action {

    display: block;

    padding: 18px;

    border-radius: 12px;

    color: white;

    text-decoration: none;

    font-weight: bold;

}

.admin-action span {

    display: block;

    font-size: 26px;

    margin-bottom: 7px;

}

.action-blue {

    background: #2563eb;

}

.action-green {

    background: #16a34a;

}

.action-purple {

    background: #7c3aed;

}

.action-orange {

    background: #ea580c;

}

.answer-box {

    border:
        2px solid #16a34a;

    background: #f0fdf4;

    padding: 20px;

    border-radius: 12px;

}

.answer-box h3 {

    color: #166534;

}

.upload-title {

    font-size: 20px;

    font-weight: 800;

    margin-bottom: 5px;

}

.big-upload {

    border:
        2px dashed #7c3aed;

    background: #faf5ff;

    padding: 22px;

    border-radius: 13px;

    margin-top: 18px;

}

@media(max-width:650px) {

    .container {

        width: 96%;

    }

    nav {

        position: relative;

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

<a href="/admin">
Dashboard
</a>

<a href="/admin/questions">
Questions
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
# HOME
# ============================================================

@app.route("/")
def home():

    if not session.get("user_id"):

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

        # ----------------------------------------------------
        # ADMIN
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

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        # ----------------------------------------------------
        # STUDENT
        # ----------------------------------------------------

        user = find_user(email)

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

        session["user_id"] = user["id"]
        session["email"] = user["email"]
        session["name"] = user["name"]
        session["role"] = "student"

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    content = """

    <div class="auth card">

        <h1>KOJA AFRICA</h1>

        <p class="muted">
            Knowledge • Questions • Answers
        </p>

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
                hash_password(password),

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
            url_for("admin_dashboard")
        )

    data = [

        q

        for q in questions()

        if q.get("student_id")
        == session.get("user_id")

    ]

    data.sort(

        key=lambda x:
            x.get(
                "created_at",
                ""
            ),

        reverse=True

    )

    total = len(data)

    answered = sum(

        1

        for q in data

        if q.get("status")
        == "Answered"

    )

    pending = total - answered

    cards = ""

    for q in data:

        subject = esc(
            q.get(
                "subject",
                "Question"
            )
        )

        status = q.get(
            "status",
            "Pending"
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
                {esc(status)}
            </span>

            <p class="muted small">
                Submitted:
                {esc(q.get("created_at", ""))}
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
                Administrator Files
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
                Ask Question
            </a>

        </div>

        """

    content = f"""

    <div class="hero">

        <h1>
            Welcome, {esc(session.get("name"))}
        </h1>

        <p>
            Ask academic questions and
            receive answers from KOJA.
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
# STUDENT ASK QUESTION
# ============================================================

@app.route(
    "/student/ask",
    methods=["GET", "POST"]
)
@login_required
def ask_question():

    if is_admin_session():

        return redirect(
            url_for("admin_dashboard")
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

        files = request.files.getlist(
            "attachments"
        )

        attachments = save_multiple_uploads(
            files,
            "student"
        )

        has_files = any(
            f and f.filename
            for f in files
        )

        if has_files and not attachments:

            flash(
                "The selected file type is not allowed.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        item = {

            "id":
                str(uuid.uuid4()),

            "student_id":
                session.get("user_id"),

            "student_name":
                session.get("name"),

            "student_email":
                session.get("email"),

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
            url_for("student_dashboard")
        )

    content = """

    <div class="card">

        <h1>
            Ask a Question
        </h1>

        <p class="muted">
            Write your academic question
            and attach documents or photos.
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

                <div class="upload-actions">

                    <label
                        class="upload-button camera"
                        for="studentCamera"
                    >
                        📷 Take Photo
                    </label>

                    <input
                        id="studentCamera"
                        class="file-input"
                        type="file"
                        name="attachments"
                        accept="image/*"
                        capture="environment"
                        onchange="showStudentFiles()"
                    >

                    <label
                        class="upload-button photo"
                        for="studentPhoto"
                    >
                        🖼️ Choose Photo
                    </label>

                    <input
                        id="studentPhoto"
                        class="file-input"
                        type="file"
                        name="attachments"
                        accept="image/*"
                        multiple
                        onchange="showStudentFiles()"
                    >

                    <label
                        class="upload-button document"
                        for="studentDocuments"
                    >
                        📄 Choose Documents
                    </label>

                    <input
                        id="studentDocuments"
                        class="file-input"
                        type="file"
                        name="attachments"
                        accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.webp"
                        multiple
                        onchange="showStudentFiles()"
                    >

                </div>

                <div
                    id="studentFileList"
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

    function showStudentFiles() {

        const ids = [
            "studentCamera",
            "studentPhoto",
            "studentDocuments"
        ];

        let names = [];

        ids.forEach(function(id) {

            const input =
                document.getElementById(id);

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
                "studentFileList"
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

    total = len(data)

    pending = sum(
        1
        for q in data
        if q.get("status") != "Answered"
    )

    answered = sum(
        1
        for q in data
        if q.get("status") == "Answered"
    )

    content = f"""

    <div class="hero">

        <h1>
            KOJA Administrator
        </h1>

        <p>
            Manage student questions,
            answers and uploaded files.
        </p>

    </div>

    <div class="admin-action-bar">

        <a
            class="admin-action action-blue"
            href="/admin/questions"
        >
            <span>📚</span>
            Questions
            <small>
                Open and answer student questions
            </small>
        </a>

        <a
            class="admin-action action-green"
            href="/admin/answers"
        >
            <span>✅</span>
            Previous Answers
            <small>
                View answers already sent
            </small>
        </a>

        <a
            class="admin-action action-purple"
            href="/admin/config"
        >
            <span>⚙️</span>
            Configuration
            <small>
                System configuration
            </small>
        </a>

    </div>

    <div class="grid">

        <div class="stat">
            <h2>{total}</h2>
            <p>Total Questions</p>
        </div>

        <div class="stat">
            <h2>{pending}</h2>
            <p>Pending Questions</p>
        </div>

        <div class="stat">
            <h2>{answered}</h2>
            <p>Previous Answers</p>
        </div>

    </div>

    <div class="card">

        <h2>
            Administrator Instructions
        </h2>

        <div class="notice">

            <strong>
                To answer a student:
            </strong>

            <br><br>

            1. Click <strong>Questions</strong>.

            <br>

            2. Click <strong>Open</strong>
            beside a question.

            <br>

            3. Write the answer.

            <br>

            4. Click
            <strong>Upload With Answer</strong>
            if you want to send files.

            <br>

            5. Choose
            <strong>Take Photo</strong>,
            <strong>Choose Photo</strong>
            or
            <strong>Choose Documents</strong>.

            <br>

            6. Click
            <strong>Send Answer + Files</strong>.

        </div>

    </div>

    """

    return render_page(
        "Admin Dashboard",
        content
    )


# =================================
# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    data = questions()

    # ONLY UNANSWERED QUESTIONS
    data = [
        q for q in data
        if q.get("status") != "Answered"
    ]

    data.sort(
        key=lambda q: q.get("created_at", ""),
        reverse=True
    )

    rows = ""

    for q in data:

        question_id = q.get("id", "")

        student_name = esc(
            q.get("student_name", "")
        )

        student_email = esc(
            q.get("student_email", "")
        )

        subject = esc(
            q.get("subject", "")
        )

        question_text = esc(
            q.get("question", "")
        )

        if len(question_text) > 180:
            question_text = question_text[:180] + "..."

        attachments = q.get(
            "attachments",
            []
        )

        rows += f"""
        <tr>

            <td>
                <strong>
                    {student_name}
                </strong>

                <br>

                <small class="muted">
                    {student_email}
                </small>
            </td>

            <td>
                <strong>
                    {subject}
                </strong>
            </td>

            <td>
                {question_text}
            </td>

            <td>

                <span class="badge pending">
                    Pending
                </span>

                <br><br>

                📎 {len(attachments)} file(s)

            </td>

            <td>

                <div style="
                    display:flex;
                    flex-direction:column;
                    gap:8px;
                    min-width:170px;
                ">

                    <a
                        class="btn"
                        href="/admin/question/{question_id}"
                    >
                        👁️ Open
                    </a>

                    <a
                        class="btn purple"
                        href="/admin/question/{question_id}/upload"
                    >
                        📎 Upload With Answer
                    </a>

                </div>

            </td>

        </tr>
        """

    if not rows:

        rows = """
        <tr>

            <td colspan="5">

                <div class="notice">

                    <strong>
                        No pending questions.
                    </strong>

                    <br><br>

                    All student questions have
                    already been answered.

                </div>

                <a
                    class="btn green"
                    href="/admin/answers"
                >
                    ✅ View Previous Answers
                </a>

            </td>

        </tr>
        """

    content = f"""

    <div class="hero">

        <h1>
            📚 Student Questions
        </h1>

        <p>
            Open a question to read it,
            answer it, or upload an answer file.
        </p>

    </div>


    <!-- ADMIN ACTION BUTTONS -->

    <div class="admin-action-bar">

        <a
            class="admin-action action-blue"
            href="/admin/questions"
        >

            <span>
                📚
            </span>

            Questions

            <small>
                Pending student questions
            </small>

        </a>


        <a
            class="admin-action action-green"
            href="/admin/answers"
        >

            <span>
                ✅
            </span>

            Previous Answers

            <small>
                View answers already sent
            </small>

        </a>


        <a
            class="admin-action action-purple"
            href="/admin/config"
        >

            <span>
                ⚙️
            </span>

            Configuration

            <small>
                System configuration
            </small>

        </a>

    </div>


    <!-- QUESTIONS -->

    <div class="card">

        <h2>
            Pending Questions
        </h2>

        <p class="muted">
            Each question now has its own
            <strong>Open</strong> and
            <strong>Upload With Answer</strong>
            buttons.
        </p>

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
                            Actions
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
        "Questions",
        content
    )
# ============================================================
# ADMIN PREVIOUS ANSWERS
# ============================================================

@app.route("/admin/answers")
@admin_required
def admin_answers():

    data = questions()

    data = [

        q

        for q in data

        if q.get("status")
        == "Answered"

    ]

    data.sort(

        key=lambda q:
            q.get(
                "answered_at",
                ""
            ),

        reverse=True

    )

    cards = ""

    for q in data:

        answer_files = q.get(
            "answer_attachments",
            []
        )

        cards += f"""

        <div class="card">

            <h2>
                {esc(q.get("subject", ""))}
            </h2>

            <span class="badge answered">
                Answered
            </span>

            <p>

                <strong>
                    Student:
                </strong>

                {esc(q.get("student_name", ""))}

                <br>

                <strong>
                    Email:
                </strong>

                {esc(q.get("student_email", ""))}

            </p>

            <p class="muted small">

                Answered:
                {esc(q.get("answered_at", ""))}

            </p>

            <h3>
                Question
            </h3>

            <div class="question">
                {esc(q.get("question", ""))}
            </div>

            <h3>
                Previous Answer
            </h3>

            <div class="answer">
                {esc(q.get("answer", ""))}
            </div>

            <p>

                📎
                <strong>
                    {len(answer_files)}
                </strong>
                attachment(s) sent with answer.

            </p>

            <a
                class="btn"
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

            <p>
                Answered questions will
                appear here.
            </p>

        </div>

        """

    content = f"""

    <div class="card">

        <h1>
            ✅ Previous Answers
        </h1>

        <p class="muted">
            This section contains questions
            that have already received answers.
        </p>

        <a
            class="btn"
            href="/admin/questions"
        >
            ← Questions
        </a>

    </div>

    {cards}

    """

    return render_page(
        "Previous Answers",
        content
    )


# ============================================================
# ADMIN OPEN QUESTION
# ============================================================

@app.route(
    "/admin/question/<question_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_question(question_id):

    question = find_question(
        question_id
    )

    if not question:

        flash(
            "Question not found.",
            "error"
        )

        return redirect(
            url_for("admin_questions")
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

        data = questions()

        for item in data:

            if str(
                item.get("id")
            ) == str(question_id):

                item["answer"] = answer

                item["status"] = "Answered"

                item["answered_at"] = (
                    datetime.utcnow().isoformat()
                )

                item["answered_by"] = (
                    session.get("email")
                )

                break

        save_questions(data)

        supabase_update(

            "koja_questions",

            question_id,

            {

                "answer":
                    answer,

                "status":
                    "Answered",

                "answered_at":
                    datetime.utcnow().isoformat()

            }

        )

        flash(
            "Answer saved. You can now add files using Upload With Answer.",
            "success"
        )

        return redirect(
            url_for(
                "admin_upload_answer",
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

    previous_files = attachment_html(

        question.get(
            "answer_attachments",
            []
        ),

        "admin"

    )

    current_answer = esc(
        question.get(
            "answer",
            ""
        )
    )

    content = f"""

    <div class="card">

        <a href="/admin/questions">
            ← Back to Questions
        </a>

        <h1>
            {esc(question.get("subject", ""))}
        </h1>

        <p>

            <strong>
                Student:
            </strong>

            {esc(question.get("student_name", ""))}

            <br>

            <strong>
                Email:
            </strong>

            {esc(question.get("student_email", ""))}

        </p>

        <p>

            <strong>
                Status:
            </strong>

            <span class="badge {
                "answered"
                if question.get("status") == "Answered"
                else "pending"
            }">

                {esc(question.get("status", "Pending"))}

            </span>

        </p>

    </div>

    <div class="card">

        <h2>
            Student Question
        </h2>

        <div class="question">

            {esc(question.get("question", ""))}

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

        <form method="post">

            <label>
                Academic Answer
            </label>

            <textarea
                name="answer"
                required
                placeholder="Write the academic answer..."
            >{current_answer}</textarea>

            <button
                type="submit"
                class="green"
            >
                Save Answer
            </button>

        </form>

        <br>

        <a
            class="btn purple"
            href="/admin/question/{question_id}/upload"
        >
            📎 Upload With Answer
        </a>

    </div>

    <div class="card">

        <h2>
            📎 Files Previously Sent
        </h2>

        {previous_files}

    </div>

    """

    return render_page(
        "Open Question",
        content
    )


# ============================================================
# ADMIN UPLOAD WITH ANSWER
#
# THIS IS THE IMPORTANT NEW PAGE
# ============================================================

@app.route(
    "/admin/question/<question_id>/upload",
    methods=["GET", "POST"]
)
@admin_required
def admin_upload_answer(question_id):

    question = find_question(
        question_id
    )

    if not question:

        flash(
            "Question not found.",
            "error"
        )

        return redirect(
            url_for("admin_questions")
        )

    if request.method == "POST":

        answer = (
            request.form.get(
                "answer",
                ""
            )
            .strip()
        )

        files = request.files.getlist(
            "answer_attachments"
        )

        attachments = save_multiple_uploads(
            files,
            "admin"
        )

        has_files = any(
            f and f.filename
            for f in files
        )

        if not answer:

            answer = question.get(
                "answer",
                ""
            ).strip()

        if len(answer) < 2:

            flash(
                "Write an answer before sending.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_upload_answer",
                    question_id=question_id
                )
            )

        if has_files and not attachments:

            flash(
                "No valid files were uploaded. Check the file type.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_upload_answer",
                    question_id=question_id
                )
            )

        data = questions()

        for item in data:

            if str(
                item.get("id")
            ) == str(question_id):

                item["answer"] = answer

                item["status"] = "Answered"

                item["answered_at"] = (
                    datetime.utcnow().isoformat()
                )

                item["answered_by"] = (
                    session.get("email")
                )

                existing = item.get(
                    "answer_attachments",
                    []
                )

                if not isinstance(
                    existing,
                    list
                ):

                    existing = []

                existing.extend(
                    attachments
                )

                item["answer_attachments"] = (
                    existing
                )

                break

        save_questions(data)

        updated = find_question(
            question_id
        )

        if updated:

            supabase_update(

                "koja_questions",

                question_id,

                {

                    "answer":
                        updated.get(
                            "answer",
                            ""
                        ),

                    "status":
                        "Answered",

                    "answered_at":
                        updated.get(
                            "answered_at"
                        )

                }

            )

        if attachments:

            flash(
                "Answer and file(s) sent successfully to the student.",
                "success"
            )

        else:

            flash(
                "Answer sent successfully. No file was attached.",
                "success"
            )

        return redirect(
            url_for(
                "admin_answers"
            )
        )

    existing_files = attachment_html(

        question.get(
            "answer_attachments",
            []
        ),

        "admin"

    )

    content = f"""

    <div class="card">

        <a href="/admin/question/{question_id}">
            ← Back to Question
        </a>

        <h1>
            📎 Upload With Answer
        </h1>

        <p class="muted">
            This page sends the academic answer
            and files directly to the student.
        </p>

    </div>

    <div class="card">

        <h2>
            Student
        </h2>

        <p>

            <strong>
                Name:
            </strong>

            {esc(question.get("student_name", ""))}

            <br>

            <strong>
                Email:
            </strong>

            {esc(question.get("student_email", ""))}

        </p>

        <h3>
            Question
        </h3>

        <div class="question">

            {esc(question.get("question", ""))}

        </div>

    </div>

    <div class="card">

        <form
            method="post"
            enctype="multipart/form-data"
        >

            <div class="answer-box">

                <h2>
                    ✍️ Answer
                </h2>

                <textarea
                    name="answer"
                    required
                    placeholder="Write your academic answer..."
                >{esc(question.get("answer", ""))}</textarea>

            </div>

            <div class="big-upload">

                <div class="upload-title">
                    📎 Upload With Answer
                </div>

                <p class="muted">

                    Choose one or more files
                    to send together with
                    your answer.

                </p>

                <div class="upload-actions">

                    <!-- TAKE PHOTO -->

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
                        onchange="showAnswerFiles()"
                    >

                    <!-- CHOOSE PHOTO -->

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
                        onchange="showAnswerFiles()"
                    >

                    <!-- CHOOSE DOCUMENTS -->

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
                        onchange="showAnswerFiles()"
                    >

                </div>

                <div
                    id="answerFileList"
                    class="file-list"
                >
                    No files selected.
                </div>

            </div>

            <br>

            <button
                type="submit"
                class="green"
            >
                ✅ Send Answer + Files
            </button>

        </form>

    </div>

    <div class="card">

        <h2>
            📎 Previously Sent Files
        </h2>

        {existing_files}

    </div>

    <script>

    function showAnswerFiles() {

        const ids = [

            "adminCamera",

            "adminPhoto",

            "adminDocuments"

        ];

        let names = [];

        ids.forEach(function(id) {

            const input =
                document.getElementById(id);

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
                "answerFileList"
            );

        if (!names.length) {

            list.innerText =
                "No files selected.";

            return;

        }

        list.innerHTML =
            "<strong>Selected files:</strong><br>"
            + names.join("<br>");

    }

    </script>

    """

    return render_page(
        "Upload With Answer",
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

    if category == "student":

        directory = STUDENT_UPLOAD_DIR

    elif category == "admin":

        directory = ADMIN_UPLOAD_DIR

    else:

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
            url_for("admin_dashboard")
        )

    question = find_question(
        question_id
    )

    if not question:

        return (
            "File not found",
            404
        )

    if (
        question.get("student_id")
        != session.get("user_id")
    ):

        return (
            "Access denied",
            403
        )

    if category == "student":

        attachments = question.get(
            "attachments",
            []
        )

        directory = STUDENT_UPLOAD_DIR

    elif category == "admin":

        attachments = question.get(
            "answer_attachments",
            []
        )

        directory = ADMIN_UPLOAD_DIR

    else:

        return (
            "Invalid category",
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
# ADMIN CONFIG
# ============================================================

@app.route("/admin/config")
@admin_required
def admin_config():

    configured = supabase_configured()

    connected = (
        supabase_test()
        if configured
        else False
    )

    content = f"""

    <div class="hero">

        <h1>
            ⚙️ System Configuration
        </h1>

        <p>
            KOJA AFRICA administrator configuration.
        </p>

    </div>

    <div class="card">

        <h2>
            Supabase
        </h2>

        <p>

            Configured:

            <span class="badge {
                "answered"
                if configured
                else "pending"
            }">

                {"YES" if configured else "NO"}

            </span>

        </p>

        <p>

            Connection:

            <span class="badge {
                "answered"
                if connected
                else "pending"
            }">

                {
                    "WORKING"
                    if connected
                    else "UNAVAILABLE"
                }

            </span>

        </p>

        <h3>
            Supabase URL
        </h3>

        <pre>
{esc(SUPABASE_URL if SUPABASE_URL else "Not configured")}
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
{esc(STORAGE_BUCKET)}
        </pre>

    </div>

    <div class="card">

        <h2>
            Local Storage
        </h2>

        <div class="notice">

            Local fallback storage is enabled.

        </div>

        <p>
            Student accounts, questions and
            uploaded files are stored locally
            when Supabase is unavailable.
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

        "local_fallback":
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

    if is_admin_session():

        return redirect(
            url_for("admin_dashboard")
        )

    if session.get("user_id"):

        return redirect(
            url_for("ask_question")
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

        "KOJA Error",

        """

        <div class="card">

            <h1>
                KOJA is still running
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
# START SERVER
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
    print("ADMIN:", ADMIN_EMAIL)
    print(
        "SUPABASE:",
        supabase_configured()
    )
    print("LOCAL FALLBACK: ENABLED")
    print("UPLOAD LIMIT: 10 MB")
    print("PORT:", port)
    print("=" * 60)
    print()

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
