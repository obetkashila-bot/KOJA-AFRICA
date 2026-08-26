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
    abort,
    Response
)

# ============================================================
# KOJA AFRICA
# KNOWLEDGE • QUESTIONS • ANSWERS
#
# PUBLIC WEBSITE + STUDENT PORTAL + ADMIN PORTAL
#
# GOOGLE SEARCH READY
# ============================================================

app = Flask(__name__)

# ============================================================
# SECURITY
# ============================================================

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_SECRET_IN_RENDER"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# ============================================================
# SITE
# ============================================================

SITE_URL = "https://koja-africa.onrender.com"

GOOGLE_VERIFICATION = (
    "u4nfIf5MfXm0iVvECSQeYAov4Tz4601ayY5kYzNc4ko"
)

SITE_NAME = "KOJA AFRICA"

SITE_DESCRIPTION = (
    "KOJA AFRICA provides academic questions, "
    "assignment support, research assistance, "
    "learning resources and academic answers."
)

# ============================================================
# DIRECTORIES
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

for directory in [
    DATA_DIR,
    UPLOAD_DIR,
    STUDENT_UPLOAD_DIR,
    ADMIN_UPLOAD_DIR
]:
    os.makedirs(directory, exist_ok=True)

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
# HELPERS
# ============================================================

def now():
    return datetime.utcnow().isoformat()


def esc(value):
    from markupsafe import escape
    return str(escape(value if value is not None else ""))


# ============================================================
# JSON STORAGE
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


ensure_file(USERS_FILE, [])
ensure_file(QUESTIONS_FILE, [])


def read_json(path):
    try:
        with LOCK:
            with open(
                path,
                "r",
                encoding="utf-8"
            ) as f:
                data = json.load(f)

        return data if isinstance(data, list) else []

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

        os.replace(temp, path)


# ============================================================
# PASSWORDS
# ============================================================

def hash_password(password):
    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        200000
    )

    return salt + "$" + digest.hex()


def verify_password(password, stored):
    try:
        salt, digest = stored.split("$", 1)

        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt.encode(),
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

    for user in data:
        if (
            user.get("email", "")
            .strip()
            .lower()
            == ADMIN_EMAIL
        ):
            user["role"] = "admin"
            user["name"] = "KOJA Administrator"

            # Keep existing password unless the
            # account has no password.
            if not user.get("password"):
                user["password"] = hash_password(
                    ADMIN_PASSWORD
                )

            save_users(data)
            return

    data.append({
        "id": "ADMIN",
        "name": "KOJA Administrator",
        "email": ADMIN_EMAIL,
        "password": hash_password(
            ADMIN_PASSWORD
        ),
        "role": "admin",
        "created_at": now()
    })

    save_users(data)


create_admin()


# ============================================================
# QUESTIONS
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
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type":
            "application/json"
    }


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
            timeout=10
        )

        if response.status_code >= 400:
            return None

        if not response.text:
            return {}

        return response.json()

    except Exception:
        return None


def supabase_insert(table, row):
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


def supabase_test():
    if not supabase_configured():
        return False

    try:
        response = requests.get(
            SUPABASE_URL + "/rest/v1/",
            headers=supabase_headers(),
            timeout=5
        )

        return response.status_code < 400

    except Exception:
        return False


def sync_question(question):
    if not supabase_configured():
        return

    row = {
        "id": question["id"],
        "student_id": question["student_id"],
        "student_name": question["student_name"],
        "student_email": question["student_email"],
        "subject": question["subject"],
        "question": question["question"],
        "status": question["status"],
        "answer": question.get("answer", ""),
        "created_at": question["created_at"],
        "answered_at": question.get("answered_at")
    }

    supabase_insert(
        "koja_questions",
        row
    )


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
        session.get("role") == "admin"
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
# FILES
# ============================================================

def extension_of(filename):
    filename = (
        filename or ""
    ).strip()

    if "." not in filename:
        return ""

    return filename.rsplit(
        ".",
        1
    )[1].lower()


def allowed_file(filename):
    return (
        extension_of(filename)
        in ALLOWED_EXTENSIONS
    )


def save_upload(file, category):
    if not file or not file.filename:
        return None

    original = file.filename.strip()

    if not allowed_file(original):
        return None

    extension = extension_of(original)

    stored = (
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
        stored
    )

    try:
        file.save(destination)
    except Exception:
        return None

    return {
        "id": str(uuid.uuid4()),
        "original_name": original,
        "stored_name": stored,
        "category": category,
        "extension": extension,
        "is_image":
            extension in IMAGE_EXTENSIONS
    }


def save_multiple_uploads(
    files,
    category
):
    result = []

    for file in files:
        if not file or not file.filename:
            continue

        saved = save_upload(
            file,
            category
        )

        if saved:
            result.append(saved)

    return result


def attachment_html(
    attachments,
    viewer,
    question_id=None
):
    if not attachments:
        return (
            '<div class="empty-files">'
            'No attachments.'
            '</div>'
        )

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

        preview = ""

        if attachment.get("is_image"):
            preview = f"""
            <img
                class="attachment-image"
                src="{route}"
                alt="Uploaded file"
            >
            """

        html += f"""
        <div class="attachment">
            <strong>📎 {name}</strong>
            {preview}
            <a
                class="btn small"
                href="{route}"
                target="_blank"
            >
                Open File
            </a>
        </div>
        """

    return html


# ============================================================
# HTML TEMPLATE
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

<meta name="theme-color" content="#101828">

<meta
    name="google-site-verification"
    content="u4nfIf5MfXm0iVvECSQeYAov4Tz4601ayY5kYzNc4ko"
>

<meta
    name="description"
    content="KOJA AFRICA provides academic questions, assignment support, research assistance, learning resources and academic answers."
>

<meta
    name="robots"
    content="index, follow"
>

<meta
    name="googlebot"
    content="index, follow"
>

<link
    rel="canonical"
    href="{{ canonical_url }}"
>

<meta
    property="og:title"
    content="KOJA AFRICA - Knowledge, Questions & Answers"
>

<meta
    property="og:description"
    content="Academic questions, assignments, research support and learning resources."
>

<meta
    property="og:url"
    content="{{ canonical_url }}"
>

<meta
    property="og:type"
    content="website"
>

<title>{{ title }} - KOJA AFRICA</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #f4f7fb;
    color: #172033;
    font-family: Arial, Helvetica, sans-serif;
}

nav {
    background: #101828;
    color: white;
    padding: 14px 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}

.logo {
    font-size: 23px;
    font-weight: 900;
}

.k { color: #2196f3; }
.o { color: #22c55e; }
.j { color: #ef4444; }
.a { color: #2563eb; }

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
}

nav a:hover {
    background: #26354d;
}

.container {
    width: 94%;
    max-width: 1150px;
    margin: 25px auto;
}

.card {
    background: white;
    padding: 22px;
    margin-bottom: 20px;
    border-radius: 14px;
    box-shadow: 0 5px 20px rgba(0,0,0,.06);
}

.hero {
    background: linear-gradient(
        135deg,
        #101828,
        #2563eb
    );
    color: white;
    padding: 40px 28px;
    border-radius: 18px;
    margin-bottom: 20px;
}

.hero h1 {
    font-size: 42px;
    margin-top: 0;
}

.hero p {
    font-size: 18px;
    line-height: 1.7;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(190px, 1fr));
    gap: 15px;
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

input,
textarea,
select {
    width: 100%;
    padding: 12px;
    margin-top: 7px;
    margin-bottom: 15px;
    border: 1px solid #d0d5dd;
    border-radius: 8px;
    font-size: 15px;
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
}

.btn.green,
button.green {
    background: #16a34a;
}

.btn.purple {
    background: #7c3aed;
}

.btn.red {
    background: #dc2626;
}

.small {
    padding: 8px 12px;
    font-size: 13px;
}

.auth {
    max-width: 500px;
    margin: 45px auto;
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

.muted {
    color: #667085;
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
    border-left: 4px solid #16a34a;
    padding: 16px;
    border-radius: 8px;
    line-height: 1.7;
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

.notice {
    padding: 13px;
    border-radius: 8px;
    background: #eff6ff;
    color: #1e40af;
    margin-bottom: 15px;
}

.upload-box,
.big-upload {
    border: 2px dashed #cbd5e1;
    border-radius: 12px;
    padding: 20px;
    background: #f8fafc;
    margin: 15px 0;
}

.upload-actions {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(170px, 1fr));
    gap: 10px;
}

.upload-button {
    display: block;
    text-align: center;
    color: white;
    padding: 14px;
    border-radius: 9px;
    cursor: pointer;
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
    border: 1px solid #e4e7ec;
    border-radius: 10px;
    padding: 13px;
    margin-top: 10px;
    background: white;
}

.attachment-image {
    max-width: 100%;
    max-height: 450px;
    display: block;
    border-radius: 8px;
    margin: 10px 0;
}

.empty-files {
    color: #667085;
    padding: 10px 0;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    padding: 12px;
    border-bottom: 1px solid #eee;
    text-align: left;
    vertical-align: top;
}

th {
    background: #f8fafc;
}

@media(max-width:650px) {

    .container {
        width: 96%;
    }

    .hero h1 {
        font-size: 32px;
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

<div class="navlinks">

{% if session.get("user_id") %}

{% if session.get("role") == "admin" %}

<a href="/admin">Dashboard</a>
<a href="/admin/questions">Questions</a>
<a href="/admin/answers">Answers</a>
<a href="/admin/config">Configuration</a>

{% else %}

<a href="/student">Dashboard</a>
<a href="/student/ask">Ask Question</a>

{% endif %}

<a href="/logout">Logout</a>

{% else %}

<a href="/">Home</a>
<a href="/login">Login</a>
<a href="/register">Register</a>

{% endif %}

</div>

</nav>

<div class="container">

{% with messages =
get_flashed_messages(with_categories=true) %}

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
    content,
    canonical=None
):

    return render_template_string(
        HTML,
        title=title,
        content=content,
        canonical_url=(
            canonical
            or SITE_URL
        )
    )


# ============================================================
# PUBLIC HOME PAGE
# ============================================================

@app.route("/")
def home():

    content = """
    <div class="hero">

        <h1>KOJA AFRICA</h1>

        <p>
            Knowledge • Questions • Answers
        </p>

        <p>
            A platform for academic questions,
            assignment support, research assistance
            and learning resources.
        </p>

        <a
            class="btn"
            href="/register"
        >
            Create Student Account
        </a>

        <a
            class="btn"
            href="/login"
        >
            Login
        </a>

    </div>

    <div class="grid">

        <div class="card">
            <h2>Ask Questions</h2>
            <p>
                Submit academic questions
                through the KOJA platform.
            </p>
        </div>

        <div class="card">
            <h2>Upload Work</h2>
            <p>
                Attach documents and photos
                to your questions.
            </p>
        </div>

        <div class="card">
            <h2>Receive Answers</h2>
            <p>
                View academic answers and
                administrator attachments.
            </p>
        </div>

    </div>

    <div class="card">

        <h2>About KOJA AFRICA</h2>

        <p>
            KOJA AFRICA is a knowledge platform
            designed to connect students with
            academic questions, answers,
            assignments and learning resources.
        </p>

        <p>
            Students can register, submit questions,
            attach academic documents or photos,
            and return to their dashboard to view
            answers.
        </p>

    </div>
    """

    return render_page(
        "Knowledge, Questions & Answers",
        content,
        SITE_URL + "/"
    )


# ============================================================
# ROBOTS.TXT
# ============================================================

@app.route("/robots.txt")
def robots():

    text = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /student
Disallow: /login
Disallow: /register
Disallow: /logout
Disallow: /admin/
Disallow: /student/

Sitemap: {SITE_URL}/sitemap.xml
"""

    return Response(
        text,
        mimetype="text/plain"
    )


# ============================================================
# SITEMAP
# ============================================================

@app.route("/sitemap.xml")
def sitemap():

    urls = [
        SITE_URL + "/",
        SITE_URL + "/login",
        SITE_URL + "/register"
    ]

    xml_urls = ""

    for address in urls:
        xml_urls += f"""
        <url>
            <loc>{address}</loc>
        </url>
        """

    xml = f"""<?xml version="1.0"
encoding="UTF-8"?>

<urlset
xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">

{xml_urls}

</urlset>
"""

    return Response(
        xml,
        mimetype="application/xml"
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
                url_for("admin_dashboard")
            )

        user = find_user(email)

        if not user or not verify_password(
            password,
            user.get("password", "")
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
            url_for("student_dashboard")
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

            <button type="submit">
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
        content,
        SITE_URL + "/login"
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

        if email == ADMIN_EMAIL:
            flash(
                "That email is reserved.",
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
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password": hash_password(password),
            "role": "student",
            "created_at": now()
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

        <h1>Student Registration</h1>

        <form method="post">

            <label>Full Name</label>

            <input
                type="text"
                name="name"
                required
            >

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

            <label>Confirm Password</label>

            <input
                type="password"
                name="confirm"
                minlength="6"
                required
            >

            <button type="submit">
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
        content,
        SITE_URL + "/register"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():
    session.clear()

    return redirect(
        url_for("home")
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
        key=lambda q:
            q.get("created_at", ""),
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

        status = q.get(
            "status",
            "Pending"
        )

        badge = (
            "answered"
            if status == "Answered"
            else "pending"
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
                Waiting for an answer.
            </p>
            """

        student_files = attachment_html(
            q.get("attachments", []),
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
                {esc(q.get("subject", ""))}
            </h2>

            <span class="badge {badge}">
                {esc(status)}
            </span>

            <p class="muted">
                {esc(q.get("created_at", ""))}
            </p>

            <h3>Your Question</h3>

            <div class="question">
                {esc(q.get("question", ""))}
            </div>

            <h3>Your Attachments</h3>

            {student_files}

            <h3>Administrator Answer</h3>

            {answer_html}

            <h3>Administrator Files</h3>

            {admin_files}

        </div>
        """

    if not cards:
        cards = """
        <div class="card">

            <h2>No questions yet.</h2>

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
            receive answers through KOJA AFRICA.
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

    <h2>My Questions</h2>

    {cards}
    """

    return render_page(
        "Student Dashboard",
        content
    )


# ============================================================
# STUDENT ASK
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

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        question_text = request.form.get(
            "question",
            ""
        ).strip()

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

        item = {
            "id": str(uuid.uuid4()),
            "student_id":
                session.get("user_id"),
            "student_name":
                session.get("name"),
            "student_email":
                session.get("email"),
            "subject": subject,
            "question": question_text,
            "attachments": attachments,
            "status": "Pending",
            "answer": "",
            "answer_attachments": [],
            "answered_at": None,
            "answered_by": None,
            "created_at": now()
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

        <h1>Ask a Question</h1>

        <p class="muted">
            Write your academic question and
            attach documents or photographs.
        </p>

        <form
            method="post"
            enctype="multipart/form-data"
        >

            <label>Subject</label>

            <input
                type="text"
                name="subject"
                placeholder="e.g. Chemistry"
                required
            >

            <label>Question</label>

            <textarea
                name="question"
                placeholder="Write your academic question..."
                required
            ></textarea>

            <div class="upload-box">

                <h3>📎 Attach Files</h3>

                <div class="upload-actions">

                    <label
                        class="upload-button camera"
                        for="camera"
                    >
                        📷 Take Photo
                    </label>

                    <input
                        id="camera"
                        class="file-input"
                        type="file"
                        name="attachments"
                        accept="image/*"
                        capture="environment"
                    >

                    <label
                        class="upload-button photo"
                        for="photo"
                    >
                        🖼️ Choose Photo
                    </label>

                    <input
                        id="photo"
                        class="file-input"
                        type="file"
                        name="attachments"
                        accept="image/*"
                        multiple
                    >

                    <label
                        class="upload-button document"
                        for="documents"
                    >
                        📄 Choose Documents
                    </label>

                    <input
                        id="documents"
                        class="file-input"
                        type="file"
                        name="attachments"
                        accept=".pdf,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx,.csv,.png,.jpg,.jpeg,.webp"
                        multiple
                    >

                </div>

            </div>

            <button type="submit">
                Submit Question
            </button>

        </form>

    </div>
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

    answered = total - pending

    content = f"""

    <div class="hero">

        <h1>KOJA Administrator</h1>

        <p>
            Manage student questions,
            academic answers and attachments.
        </p>

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
            <p>Answered Questions</p>
        </div>

    </div>

    <div class="card">

        <a
            class="btn"
            href="/admin/questions"
        >
            📚 Questions
        </a>

        <a
            class="btn green"
            href="/admin/answers"
        >
            ✅ Previous Answers
        </a>

        <a
            class="btn purple"
            href="/admin/config"
        >
            ⚙️ Configuration
        </a>

    </div>
    """

    return render_page(
        "Admin Dashboard",
        content
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    data = [
        q for q in questions()
        if q.get("status") != "Answered"
    ]

    data.sort(
        key=lambda q:
            q.get("created_at", ""),
        reverse=True
    )

    rows = ""

    for q in data:

        question_id = q.get("id")

        text = esc(
            q.get("question", "")
        )

        if len(text) > 200:
            text = text[:200] + "..."

        rows += f"""
        <tr>

            <td>
                <strong>
                    {esc(q.get("student_name", ""))}
                </strong>
                <br>
                <small>
                    {esc(q.get("student_email", ""))}
                </small>
            </td>

            <td>
                {esc(q.get("subject", ""))}
            </td>

            <td>
                {text}
            </td>

            <td>
                <span class="badge pending">
                    Pending
                </span>
            </td>

            <td>

                <a
                    class="btn"
                    href="/admin/question/{question_id}"
                >
                    Open
                </a>

                <a
                    class="btn purple"
                    href="/admin/question/{question_id}/upload"
                >
                    Upload With Answer
                </a>

            </td>

        </tr>
        """

    if not rows:
        rows = """
        <tr>
            <td colspan="5">
                <div class="notice">
                    No pending questions.
                </div>
            </td>
        </tr>
        """

    content = f"""

    <div class="card">

        <h1>📚 Student Questions</h1>

        <p>
            Open a question to read it and
            provide an academic answer.
        </p>

    </div>

    <div class="card">

        <div style="overflow-x:auto">

            <table>

                <thead>

                    <tr>
                        <th>Student</th>
                        <th>Subject</th>
                        <th>Question</th>
                        <th>Status</th>
                        <th>Actions</th>
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

        answer = request.form.get(
            "answer",
            ""
        ).strip()

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
                item["answered_at"] = now()
                item["answered_by"] = session.get(
                    "email"
                )

                break

        save_questions(data)

        supabase_update(
            "koja_questions",
            question_id,
            {
                "answer": answer,
                "status": "Answered",
                "answered_at": now()
            }
        )

        flash(
            "Answer saved.",
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

    answer_files = attachment_html(
        question.get(
            "answer_attachments",
            []
        ),
        "admin"
    )

    content = f"""

    <div class="card">

        <a href="/admin/questions">
            ← Questions
        </a>

        <h1>
            {esc(question.get("subject", ""))}
        </h1>

        <p>
            <strong>Student:</strong>
            {esc(question.get("student_name", ""))}
            <br>
            <strong>Email:</strong>
            {esc(question.get("student_email", ""))}
        </p>

    </div>

    <div class="card">

        <h2>Student Question</h2>

        <div class="question">
            {esc(question.get("question", ""))}
        </div>

        <h2>Student Attachments</h2>

        {student_files}

    </div>

    <div class="card">

        <h2>✍️ Academic Answer</h2>

        <form method="post">

            <textarea
                name="answer"
                required
                placeholder="Write the academic answer..."
            >{esc(question.get("answer", ""))}</textarea>

            <button
                class="green"
                type="submit"
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

        <h2>Previously Sent Files</h2>

        {answer_files}

    </div>
    """

    return render_page(
        "Open Question",
        content
    )


# ============================================================
# ADMIN UPLOAD WITH ANSWER
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

        answer = request.form.get(
            "answer",
            ""
        ).strip()

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

        files = request.files.getlist(
            "answer_attachments"
        )

        attachments = save_multiple_uploads(
            files,
            "admin"
        )

        data = questions()

        for item in data:

            if str(
                item.get("id")
            ) == str(question_id):

                item["answer"] = answer
                item["status"] = "Answered"
                item["answered_at"] = now()
                item["answered_by"] = session.get(
                    "email"
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

                item["answer_attachments"] = existing

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
                    "status": "Answered",
                    "answered_at":
                        updated.get(
                            "answered_at"
                        )
                }
            )

        flash(
            "Answer sent successfully.",
            "success"
        )

        return redirect(
            url_for("admin_answers")
        )

    existing = attachment_html(
        question.get(
            "answer_attachments",
            []
        ),
        "admin"
    )

    content = f"""

    <div class="card">

        <a href="/admin/questions">
            ← Questions
        </a>

        <h1>
            📎 Upload With Answer
        </h1>

        <p>
            Student:
            <strong>
                {esc(question.get("student_name", ""))}
            </strong>
        </p>

        <div class="question">
            {esc(question.get("question", ""))}
        </div>

    </div>

    <div class="card">

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
            >{esc(question.get("answer", ""))}</textarea>

            <div class="big-upload">

                <h2>
                    📎 Attach Answer Files
                </h2>

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
                    >

                </div>

            </div>

            <br>

            <button
                class="green"
                type="submit"
            >
                ✅ Send Answer + Files
            </button>

        </form>

    </div>

    <div class="card">

        <h2>Previously Sent Files</h2>

        {existing}

    </div>
    """

    return render_page(
        "Upload With Answer",
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
        if q.get("status")
        == "Answered"
    ]

    data.sort(
        key=lambda q:
            q.get("answered_at", ""),
        reverse=True
    )

    cards = ""

    for q in data:

        cards += f"""

        <div class="card">

            <h2>
                {esc(q.get("subject", ""))}
            </h2>

            <span class="badge answered">
                Answered
            </span>

            <p>
                <strong>Student:</strong>
                {esc(q.get("student_name", ""))}
                <br>
                <strong>Email:</strong>
                {esc(q.get("student_email", ""))}
            </p>

            <h3>Question</h3>

            <div class="question">
                {esc(q.get("question", ""))}
            </div>

            <h3>Answer</h3>

            <div class="answer">
                {esc(q.get("answer", ""))}
            </div>

            <a
                class="btn"
                href="/admin/question/{q.get("id")}"
            >
                Open
            </a>

        </div>

        """

    if not cards:
        cards = """
        <div class="card">
            <h2>No previous answers.</h2>
        </div>
        """

    return render_page(
        "Previous Answers",
        cards
    )


# ============================================================
# FILE ACCESS
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
        return "File not found", 404

    if (
        question.get("student_id")
        != session.get("user_id")
    ):
        return "Access denied", 403

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
        return "Invalid category", 404

    for attachment in attachments:

        if (
            attachment.get(
                "stored_name"
            )
            == filename
        ):

            return send_from_directory(
                directory,
                filename
            )

    return "File not found", 404


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

    <div class="card">

        <h1>⚙️ Configuration</h1>

        <h2>Supabase</h2>

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
                {"WORKING" if connected else "UNAVAILABLE"}
            </span>
        </p>

        <p>
            Storage bucket:
            <strong>
                {esc(STORAGE_BUCKET)}
            </strong>
        </p>

        <p class="muted">
            Service key is configured server-side
            and is never displayed.
        </p>

    </div>

    <div class="card">

        <h2>Local Fallback</h2>

        <p>
            Local JSON storage and local uploads
            are enabled as a fallback.
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
        "status": "ok",
        "application": SITE_NAME,
        "supabase_configured":
            supabase_configured(),
        "supabase_connected":
            supabase_test(),
        "local_fallback": True
    }


# ============================================================
# ERRORS
# ============================================================

@app.errorhandler(413)
def too_large(error):

    flash(
        "Maximum upload size is 10 MB.",
        "error"
    )

    if session.get("user_id"):

        if is_admin_session():
            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("ask_question")
        )

    return redirect(
        url_for("login")
    )


@app.errorhandler(404)
def not_found(error):

    return render_page(
        "Not Found",
        """
        <div class="card">
            <h1>Page Not Found</h1>
            <p>
                The requested page does not exist.
            </p>
            <a class="btn" href="/">
                Go Home
            </a>
        </div>
        """
    ), 404


@app.errorhandler(500)
def server_error(error):

    return render_page(
        "KOJA Error",
        """
        <div class="card">
            <h1>KOJA AFRICA</h1>
            <p>
                An unexpected error occurred.
                Please try again.
            </p>
            <a class="btn" href="/">
                Go Home
            </a>
        </div>
        """
    ), 500

# ============================================================
# GOOGLE SEARCH CONSOLE VERIFICATION
# ============================================================

@app.route("/google4d3d8178b7b4659e.html")
def google_verification():

    return "google-site-verification: google4d3d8178b7b4659e.html"
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

    print("=" * 60)
    print("KOJA AFRICA")
    print("Knowledge • Questions • Answers")
    print("=" * 60)
    print("SITE:", SITE_URL)
    print("ADMIN:", ADMIN_EMAIL)
    print(
        "SUPABASE:",
        supabase_configured()
    )
    print("UPLOAD LIMIT: 10 MB")
    print("PORT:", port)
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
