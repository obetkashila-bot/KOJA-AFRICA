import os
import json
import uuid
import hashlib
import secrets
from datetime import datetime, timezone
from functools import wraps

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
    make_response,
)

# ============================================================
# KOJA AFRICA
# KNOWLEDGE • QUESTIONS • ANSWERS
#
# SINGLE-FILE FLASK APPLICATION
#
# PUBLIC
#   Home
#   Log In
#   Create Account
#
# STUDENT
#   Dashboard
#   Ask Question
#   My Questions
#   Research
#   Documents
#   Upload documents to Admin
#   Download documents sent by Admin
#
# ADMIN
#   Dashboard
#   Questions
#   Answers
#   Documents
#   Receive student documents
#   Send documents to individual students
#   Download documents
#   Logs
#
# NOTE:
# This version uses local JSON/filesystem storage because it is
# designed as a single-file Flask application.
# For production on Render, use persistent storage/Supabase.
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    secrets.token_hex(32)
)

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
    "students"
)

ADMIN_UPLOAD_DIR = os.path.join(
    UPLOAD_DIR,
    "admin"
)

os.makedirs(STUDENT_UPLOAD_DIR, exist_ok=True)
os.makedirs(ADMIN_UPLOAD_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.json")
DOCUMENTS_FILE = os.path.join(DATA_DIR, "documents.json")

MAX_FILE_SIZE = 15 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "txt",
    "jpg", "jpeg", "png",
    "xls", "xlsx",
    "ppt", "pptx",
    "csv"
}


# ============================================================
# JSON STORAGE
# ============================================================

def ensure_file(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)


ensure_file(USERS_FILE, [])
ensure_file(QUESTIONS_FILE, [])
ensure_file(LOGS_FILE, [])
ensure_file(DOCUMENTS_FILE, [])


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


def write_json(path, data):
    temp = path + ".tmp"

    with open(temp, "w", encoding="utf-8") as f:
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
    salt = secrets.token_bytes(16)

    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        150000
    )

    return salt.hex() + "$" + key.hex()


def verify_password(password, stored):
    try:
        salt_hex, key_hex = stored.split("$")

        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            150000
        )

        return secrets.compare_digest(
            actual,
            expected
        )

    except Exception:
        return False


# ============================================================
# ADMIN ACCOUNT
# ============================================================

def ensure_admin():
    users = read_json(USERS_FILE, [])

    for user in users:
        if user.get("role") == "admin":
            return

    admin_password = os.environ.get(
        "KOJA_ADMIN_PASSWORD",
        "ChangeMe123!"
    )

    admin_email = os.environ.get(
        "KOJA_ADMIN_EMAIL",
        "admin@koja.africa"
    ).strip().lower()

    users.append({
        "id": str(uuid.uuid4()),
        "name": "KOJA Administrator",
        "email": admin_email,
        "password": hash_password(admin_password),
        "role": "admin",
        "created_at": datetime.now(
            timezone.utc
        ).isoformat()
    })

    write_json(USERS_FILE, users)


ensure_admin()


# ============================================================
# LOGGING
# ============================================================

def log_event(
    event,
    category="System",
    level="INFO",
    details=""
):
    logs = read_json(LOGS_FILE, [])

    logs.append({
        "id": str(uuid.uuid4()),
        "event": event,
        "category": category,
        "level": level,
        "details": details,
        "time": datetime.now(
            timezone.utc
        ).isoformat(),
        "user_id": session.get("user_id")
    })

    logs = logs[-5000:]

    write_json(LOGS_FILE, logs)


# ============================================================
# AUTHENTICATION
# ============================================================

def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    users = read_json(USERS_FILE, [])

    return next(
        (
            u for u in users
            if u.get("id") == user_id
        ),
        None
    )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):

        if not current_user():
            flash(
                "Please log in first.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):

        user = current_user()

        if not user:
            flash(
                "Please log in first.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        if user.get("role") != "admin":
            abort(403)

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# USER HELPERS
# ============================================================

def get_user_by_id(user_id):
    users = read_json(USERS_FILE, [])

    return next(
        (
            u for u in users
            if u.get("id") == user_id
        ),
        None
    )


def get_students():
    users = read_json(USERS_FILE, [])

    return [
        u for u in users
        if u.get("role") == "student"
    ]


# ============================================================
# FILE HELPERS
# ============================================================

def allowed_file(filename):
    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in ALLOWED_EXTENSIONS


def safe_filename(filename):
    filename = os.path.basename(filename or "")
    filename = filename.replace("\x00", "")
    return filename[:200]


def save_uploaded_file(file, directory):
    if not file or not file.filename:
        return None

    original = safe_filename(file.filename)

    if not allowed_file(original):
        raise ValueError(
            "This file type is not allowed."
        )

    data = file.read()

    if len(data) > MAX_FILE_SIZE:
        raise ValueError(
            "File is too large. Maximum size is 15 MB."
        )

    stored_name = (
        str(uuid.uuid4())
        + "_"
        + original
    )

    path = os.path.join(
        directory,
        stored_name
    )

    with open(path, "wb") as f:
        f.write(data)

    return {
        "original_name": original,
        "stored_name": stored_name,
        "size": len(data)
    }


def format_size(size):
    try:
        size = int(size)
    except Exception:
        return ""

    if size < 1024:
        return f"{size} B"

    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


def html_escape(value):
    """
    Basic HTML escaping for values inserted into HTML
    strings generated by this single-file application.
    """
    if value is None:
        return ""

    text = str(value)

    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ============================================================
# CSS
# ============================================================

CSS = """
<style>

* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    padding: 0;
    font-family:
        Arial,
        Helvetica,
        sans-serif;
    background: #f4f7fb;
    color: #111827;
}

body {
    min-height: 100vh;
}

a {
    text-decoration: none;
}

.topbar {
    width: 100%;
    background: #061b49;
    color: white;
    box-shadow:
        0 4px 18px rgba(0,0,0,.15);
}

.topbar-inner {
    width: 100%;
    max-width: 1400px;
    margin: auto;
    min-height: 72px;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
}

.logo {
    color: white;
    font-size: 30px;
    font-weight: 900;
    letter-spacing: 1px;
}

.logo .k {
    color: #2196f3;
}

.logo .o {
    color: #43a047;
}

.logo .j {
    color: #e53935;
}

.logo .a {
    color: #1565c0;
}

.logo small {
    display: block;
    text-align: center;
    font-size: 8px;
    letter-spacing: 5px;
    color: #cbd5e1;
}

.public-nav,
.private-nav {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 7px;
}

.public-nav a {
    padding: 11px 17px;
    border-radius: 8px;
    font-weight: 700;
}

.login-btn {
    color: white;
    border: 1px solid #60a5fa;
}

.register-btn {
    background: #1976d2;
    color: white;
}

.private-nav a {
    color: white;
    padding: 10px 12px;
    border-radius: 7px;
    font-weight: 700;
    font-size: 14px;
}

.private-nav a:hover {
    background: rgba(255,255,255,.12);
}

.logout {
    border: 1px solid #93c5fd;
}

.container {
    width: 100%;
    max-width: 1200px;
    margin: auto;
    padding: 25px 18px 60px;
}

.card {
    background: white;
    border-radius: 15px;
    padding: 25px;
    margin-bottom: 20px;
    box-shadow:
        0 8px 30px rgba(15,23,42,.07);
}

.hero {
    background: white;
    text-align: center;
    border-radius: 18px;
    padding: 70px 25px;
    margin-top: 25px;
    box-shadow:
        0 10px 35px rgba(15,23,42,.07);
}

.hero h1 {
    margin: 0;
    font-size: clamp(38px, 7vw, 70px);
}

.hero p {
    max-width: 760px;
    margin: 18px auto;
    color: #64748b;
    font-size: 18px;
    line-height: 1.7;
}

.hero-buttons {
    margin-top: 25px;
}

.btn,
button {
    display: inline-block;
    border: 0;
    padding: 12px 18px;
    border-radius: 8px;
    background: #1976d2;
    color: white;
    font-weight: 700;
    cursor: pointer;
}

.btn.green {
    background: #2e7d32;
}

.btn.dark {
    background: #061b49;
}

.btn.red {
    background: #c62828;
}

.btn.gray {
    background: #475569;
}

input,
textarea,
select {
    width: 100%;
    padding: 13px;
    margin: 7px 0 15px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font: inherit;
}

textarea {
    min-height: 180px;
}

label {
    display: block;
    margin-top: 10px;
    font-weight: 700;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
}

.stat {
    background: white;
    border-radius: 14px;
    padding: 25px;
    text-align: center;
    box-shadow:
        0 7px 25px rgba(0,0,0,.06);
}

.stat h2 {
    margin: 0;
    font-size: 35px;
}

.question {
    white-space: pre-wrap;
    background: #f8fafc;
    padding: 18px;
    border-radius: 10px;
    line-height: 1.7;
}

.answer {
    white-space: pre-wrap;
    background: #eff6ff;
    padding: 18px;
    border-radius: 10px;
    line-height: 1.7;
}

.document-box {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 16px;
    border-radius: 10px;
    margin-top: 12px;
}

.alert {
    max-width: 1200px;
    margin: 15px auto;
    padding: 13px 18px;
    border-radius: 8px;
    background: #dbeafe;
}

.alert.error {
    background: #fee2e2;
    color: #991b1b;
}

.alert.success {
    background: #dcfce7;
    color: #166534;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    padding: 12px;
    border-bottom:
        1px solid #e5e7eb;
    text-align: left;
    vertical-align: top;
}

.table-wrap {
    overflow-x: auto;
}

.badge {
    display: inline-block;
    padding: 5px 9px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 700;
}

.pending {
    background: #fef3c7;
    color: #92400e;
}

.answered {
    background: #dcfce7;
    color: #166534;
}

.muted {
    color: #64748b;
}

.empty {
    padding: 25px;
    text-align: center;
    color: #64748b;
}

footer {
    text-align: center;
    padding: 35px 20px;
    color: #64748b;
}

@media(max-width:900px) {

    .topbar-inner {
        flex-direction: column;
        align-items: flex-start;
    }

    .public-nav,
    .private-nav {
        width: 100%;
    }

    .private-nav {
        overflow-x: auto;
        flex-wrap: nowrap;
    }

    .hero {
        padding: 45px 20px;
    }
}

</style>
"""


# ============================================================
# PUBLIC LAYOUT
# ============================================================

PUBLIC_LAYOUT = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0"
>

<meta
    name="description"
    content="KOJA AFRICA - Knowledge, Questions and Answers"
>

<meta
    name="robots"
    content="index, follow"
>

<title>{{ title }} | KOJA AFRICA</title>

""" + CSS + """

</head>

<body>

<header class="topbar">

<div class="topbar-inner">

<a
    class="logo"
    href="{{ url_for('home') }}"
>

<span class="k">k</span><span
class="o">o</span><span
class="j">j</span><span
class="a">a</span>

<small>AFRICA</small>

</a>

<nav class="public-nav">

<a
    class="login-btn"
    href="{{ url_for('login') }}"
>
Log In
</a>

<a
    class="register-btn"
    href="{{ url_for('register') }}"
>
Create Account
</a>

</nav>

</div>

</header>

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

<main class="container">

{{ content|safe }}

</main>

<footer>

<strong>KOJA AFRICA</strong>

<br>

Knowledge • Questions • Answers

<br><br>

Academic Research • Learning • Questions

</footer>

</body>

</html>
"""


# ============================================================
# PRIVATE LAYOUT
# ============================================================

PRIVATE_LAYOUT = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0"
>

<meta
    name="robots"
    content="noindex, nofollow"
>

<title>{{ title }} | KOJA AFRICA</title>

""" + CSS + """

</head>

<body>

<header class="topbar">

<div class="topbar-inner">

<a
    class="logo"
    href="{{ url_for('home') }}"
>

<span class="k">k</span><span
class="o">o</span><span
class="j">j</span><span
class="a">a</span>

<small>AFRICA</small>

</a>

<nav class="private-nav">

{% if session.get("role") == "admin" %}

<a href="{{ url_for('admin_dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('admin_questions') }}">
Questions
</a>

<a href="{{ url_for('admin_answers') }}">
Answers
</a>

<a href="{{ url_for('admin_documents') }}">
Documents
</a>

<a href="{{ url_for('admin_logs') }}">
Logs
</a>

{% else %}

<a href="{{ url_for('student_dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('ask_question') }}">
Ask Question
</a>

<a href="{{ url_for('student_questions') }}">
My Questions
</a>

<a href="{{ url_for('research') }}">
Research
</a>

<a href="{{ url_for('student_documents') }}">
Documents
</a>

{% endif %}

<a
    class="logout"
    href="{{ url_for('logout') }}"
>
Logout
</a>

</nav>

</div>

</header>

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

<main class="container">

{{ content|safe }}

</main>

<footer>

<strong>KOJA AFRICA</strong>

<br>

Knowledge • Questions • Answers

</footer>

</body>

</html>
"""


def public_page(title, content):
    return render_template_string(
        PUBLIC_LAYOUT,
        title=title,
        content=content
    )


def private_page(title, content):
    return render_template_string(
        PRIVATE_LAYOUT,
        title=title,
        content=content
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    content = """
<section class="hero">

<h1>
<span style="color:#1976d2;">K</span><span
style="color:#2e7d32;">O</span><span
style="color:#d32f2f;">J</span><span
style="color:#1565c0;">A</span>
</h1>

<h2>KOJA AFRICA</h2>

<p>
Knowledge • Questions • Answers
</p>

<p>
A platform for academic questions,
research, learning resources and
educational support.
</p>

<div class="hero-buttons">

<a
    class="btn dark"
    href="{{ url_for('login') }}"
>
Log In
</a>

<a
    class="btn"
    href="{{ url_for('register') }}"
>
Create Account
</a>

</div>

</section>
"""

    response = make_response(
        public_page(
            "Home",
            render_template_string(content)
        )
    )

    response.headers[
        "X-Robots-Tag"
    ] = "index, follow"

    return response


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

        if not name or not email or not password:
            flash(
                "Complete all fields.",
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

        users = read_json(
            USERS_FILE,
            []
        )

        if any(
            u.get("email") == email
            for u in users
        ):
            flash(
                "An account with that email already exists.",
                "error"
            )
            return redirect(
                url_for("register")
            )

        user = {
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password": hash_password(password),
            "role": "student",
            "created_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

        users.append(user)

        write_json(
            USERS_FILE,
            users
        )

        log_event(
            "Student Account Created",
            "Authentication",
            "INFO",
            email
        )

        flash(
            "Account created successfully. Please log in.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    content = """
<div class="card">

<h1>Create Account</h1>

<form method="post">

<label>Name</label>

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

<button type="submit">
Create Account
</button>

</form>

</div>
"""

    return public_page(
        "Create Account",
        content
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

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        users = read_json(
            USERS_FILE,
            []
        )

        user = next(
            (
                u for u in users
                if u.get("email") == email
            ),
            None
        )

        if not user or not verify_password(
            password,
            user.get("password", "")
        ):
            log_event(
                "Failed Login",
                "Authentication",
                "WARNING",
                email
            )

            flash(
                "Invalid email or password.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        session.clear()

        session["user_id"] = user["id"]
        session["role"] = user["role"]

        log_event(
            "Login",
            "Authentication",
            "INFO",
            email
        )

        if user["role"] == "admin":
            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("student_dashboard")
        )

    content = """
<div class="card">

<h1>Log In</h1>

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
Log In
</button>

</form>

</div>
"""

    return public_page(
        "Log In",
        content
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    if current_user():
        log_event(
            "Logout",
            "Authentication",
            "INFO"
        )

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

    user = current_user()

    if user["role"] == "admin":
        return redirect(
            url_for("admin_dashboard")
        )

    questions = read_json(
        QUESTIONS_FILE,
        []
    )

    documents = read_json(
        DOCUMENTS_FILE,
        []
    )

    mine = [
        q for q in questions
        if q.get("student_id") == user["id"]
    ]

    answered = sum(
        1 for q in mine
        if q.get("answer")
    )

    received_documents = [
        d for d in documents
        if d.get("direction") == "admin_to_student"
        and d.get("recipient_id") == user["id"]
    ]

    name = html_escape(
        user.get("name")
    )

    content = f"""
<div class="card">

<h1>
Welcome, {name}
</h1>

<p>
KOJA AFRICA Student Portal
</p>

</div>

<div class="grid">

<div class="stat">
<h2>{len(mine)}</h2>
<p>My Questions</p>
</div>

<div class="stat">
<h2>{answered}</h2>
<p>Answered</p>
</div>

<div class="stat">
<h2>{len(received_documents)}</h2>
<p>Documents Received</p>
</div>

</div>

<div class="card">

<a class="btn"
   href="{url_for('ask_question')}">
Ask Question
</a>

<a class="btn dark"
   href="{url_for('research')}">
Research
</a>

<a class="btn green"
   href="{url_for('student_documents')}">
My Documents
</a>

</div>
"""

    return private_page(
        "Student Dashboard",
        content
    )


# ============================================================
# ASK QUESTION
# ============================================================

@app.route(
    "/ask",
    methods=["GET", "POST"]
)
@login_required
def ask_question():

    user = current_user()

    if user["role"] == "admin":
        return redirect(
            url_for("admin_dashboard")
        )

    if request.method == "POST":

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

        question = {
            "id": str(uuid.uuid4()),
            "student_id": user["id"],
            "student_name": user["name"],
            "question": question_text,
            "answer": "",
            "answer_by": "",
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "answered_at": "",
            "attachments": [],
            "answer_attachments": []
        }

        file = request.files.get(
            "document"
        )

        if file and file.filename:

            try:
                saved = save_uploaded_file(
                    file,
                    STUDENT_UPLOAD_DIR
                )

                question["attachments"].append(
                    saved
                )

            except ValueError as exc:
                flash(
                    str(exc),
                    "error"
                )

                return redirect(
                    url_for("ask_question")
                )

        questions = read_json(
            QUESTIONS_FILE,
            []
        )

        questions.append(question)

        write_json(
            QUESTIONS_FILE,
            questions
        )

        log_event(
            "Question Submitted",
            "Questions",
            "INFO",
            question["id"]
        )

        flash(
            "Your question has been submitted.",
            "success"
        )

        return redirect(
            url_for("student_questions")
        )

    content = """
<div class="card">

<h1>Ask KOJA</h1>

<form
    method="post"
    enctype="multipart/form-data"
>

<label>Question</label>

<textarea
    name="question"
    required
></textarea>

<label>
Optional supporting document
</label>

<input
    type="file"
    name="document"
>

<p class="muted">
Allowed: PDF, Word, Excel, PowerPoint,
text, images and CSV. Maximum 15 MB.
</p>

<button type="submit">
Submit Question
</button>

</form>

</div>
"""

    return private_page(
        "Ask Question",
        content
    )


# ============================================================
# STUDENT QUESTIONS
# ============================================================

@app.route("/student/questions")
@login_required
def student_questions():

    user = current_user()

    questions = read_json(
        QUESTIONS_FILE,
        []
    )

    mine = [
        q for q in questions
        if q.get("student_id") == user["id"]
    ]

    blocks = []

    for q in reversed(mine):

        question_text = html_escape(
            q.get("question")
        )

        status = (
            "Answered"
            if q.get("answer")
            else "Pending"
        )

        status_class = (
            "answered"
            if q.get("answer")
            else "pending"
        )

        attachment_html = ""

        for attachment in q.get(
            "attachments",
            []
        ):

            attachment_html += f"""
<div class="document-box">

<strong>
Your supporting document
</strong>

<br><br>

{html_escape(
    attachment.get("original_name")
)}

<br><br>

<a
    class="btn gray"
    href="{url_for(
        'student_question_file',
        question_id=q.get('id'),
        stored_name=attachment.get('stored_name')
    )}"
>
Download
</a>

</div>
"""

        answer_html = ""

        if q.get("answer"):

            answer_html = f"""
<h3>Answer</h3>

<div class="answer">
{html_escape(q.get("answer"))}
</div>
"""

        answer_files = ""

        for attachment in q.get(
            "answer_attachments",
            []
        ):

            answer_files += f"""
<div class="document-box">

<strong>
Document from KOJA Administration
</strong>

<br><br>

{html_escape(
    attachment.get("original_name")
)}

<br><br>

<a
    class="btn green"
    href="{url_for(
        'student_answer_file',
        question_id=q.get('id'),
        stored_name=attachment.get('stored_name')
    )}"
>
Download Document
</a>

</div>
"""

        blocks.append(f"""
<div class="card">

<h3>
{question_text}
</h3>

<p>
<span class="badge {status_class}">
{status}
</span>
</p>

{attachment_html}

{answer_html}

{answer_files}

</div>
""")

    content = """
<div class="card">

<h1>My Questions</h1>

<p>
Only your own questions and their answers
are shown here.
</p>

</div>
"""

    if blocks:
        content += "".join(blocks)

    else:
        content += """
<div class="card">

<div class="empty">
You have not submitted a question yet.
</div>

<a
    class="btn"
    href="/ask"
>
Ask Question
</a>

</div>
"""

    return private_page(
        "My Questions",
        content
    )


# ============================================================
# STUDENT RESEARCH
# ============================================================

@app.route("/research")
@login_required
def research():

    questions = read_json(
        QUESTIONS_FILE,
        []
    )

    answered = [
        q for q in questions
        if q.get("answer")
    ]

    blocks = []

    for q in reversed(answered):

        blocks.append(f"""
<div class="card">

<h2>
{html_escape(q.get("question"))}
</h2>

<div class="answer">
{html_escape(q.get("answer"))}
</div>

</div>
""")

    content = """
<div class="card">

<h1>Research</h1>

<p>
Only answered academic questions are
available in the research area.
Unanswered student questions are private.
</p>

</div>
"""

    content += "".join(blocks)

    return private_page(
        "Research",
        content
    )


# ============================================================
# STUDENT DOCUMENTS
#
# STUDENT -> ADMIN
# ADMIN -> STUDENT
# ============================================================

@app.route(
    "/student/documents",
    methods=["GET", "POST"]
)
@login_required
def student_documents():

    user = current_user()

    if user.get("role") == "admin":
        return redirect(
            url_for("admin_documents")
        )

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        file = request.files.get(
            "document"
        )

        if not title:
            flash(
                "Enter a document title.",
                "error"
            )
            return redirect(
                url_for("student_documents")
            )

        if not file or not file.filename:
            flash(
                "Select a document.",
                "error"
            )
            return redirect(
                url_for("student_documents")
            )

        try:
            saved = save_uploaded_file(
                file,
                STUDENT_UPLOAD_DIR
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )
            return redirect(
                url_for("student_documents")
            )

        documents = read_json(
            DOCUMENTS_FILE,
            []
        )

        document = {
            "id": str(uuid.uuid4()),
            "direction": "student_to_admin",

            "sender_id": user["id"],
            "sender_name": user["name"],

            "recipient_id": "",
            "recipient_name": "KOJA Administration",

            "title": title,
            "description": description,

            "original_name": saved["original_name"],
            "stored_name": saved["stored_name"],
            "size": saved["size"],

            "created_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

        documents.append(document)

        write_json(
            DOCUMENTS_FILE,
            documents
        )

        log_event(
            "Student Document Submitted",
            "Documents",
            "INFO",
            saved["original_name"]
        )

        flash(
            "Your document has been sent to KOJA Administration.",
            "success"
        )

        return redirect(
            url_for("student_documents")
        )

    documents = read_json(
        DOCUMENTS_FILE,
        []
    )

    sent = [
        d for d in documents
        if d.get("direction") == "student_to_admin"
        and d.get("sender_id") == user["id"]
    ]

    received = [
        d for d in documents
        if d.get("direction") == "admin_to_student"
        and d.get("recipient_id") == user["id"]
    ]

    received_rows = []

    for d in reversed(received):

        received_rows.append(f"""
<tr>

<td>
{html_escape(d.get("created_at", ""))}
</td>

<td>
<strong>
{html_escape(d.get("title", ""))}
</strong>
</td>

<td>
{html_escape(d.get("original_name", ""))}
<br>
<span class="muted">
{format_size(d.get("size", 0))}
</span>
</td>

<td>
{html_escape(d.get("description", ""))}
</td>

<td>

<a
    class="btn green"
    href="{url_for(
        'student_document_download',
        document_id=d.get('id')
    )}"
>
Download
</a>

</td>

</tr>
""")

    sent_rows = []

    for d in reversed(sent):

        sent_rows.append(f"""
<tr>

<td>
{html_escape(d.get("created_at", ""))}
</td>

<td>
{html_escape(d.get("title", ""))}
</td>

<td>
{html_escape(d.get("original_name", ""))}
<br>
<span class="muted">
{format_size(d.get("size", 0))}
</span>
</td>

<td>
Sent to KOJA Administration
</td>

</tr>
""")

    if not received_rows:
        received_html = """
<div class="empty">
No documents have been sent to you yet.
</div>
"""
    else:
        received_html = f"""
<div class="table-wrap">

<table>

<tr>
<th>Date</th>
<th>Title</th>
<th>File</th>
<th>Description</th>
<th>Download</th>
</tr>

{''.join(received_rows)}

</table>

</div>
"""

    if not sent_rows:
        sent_html = """
<div class="empty">
You have not sent a document yet.
</div>
"""
    else:
        sent_html = f"""
<div class="table-wrap">

<table>

<tr>
<th>Date</th>
<th>Title</th>
<th>File</th>
<th>Status</th>
</tr>

{''.join(sent_rows)}

</table>

</div>
"""

    content = f"""
<div class="card">

<h1>My Documents</h1>

<p>
Send documents to KOJA Administration and
download documents sent specifically to you.
</p>

</div>

<div class="card">

<h2>Send Document To KOJA Administration</h2>

<form
    method="post"
    enctype="multipart/form-data"
>

<label>Document Title</label>

<input
    type="text"
    name="title"
    placeholder="Assignment, research work, report..."
    required
>

<label>Description</label>

<textarea
    name="description"
    placeholder="Optional description"
    style="min-height:120px;"
></textarea>

<label>Document</label>

<input
    type="file"
    name="document"
    required
>

<p class="muted">
Maximum file size: 15 MB.
</p>

<button type="submit">
Send Document
</button>

</form>

</div>

<div class="card">

<h2>Documents Received From KOJA</h2>

{received_html}

</div>

<div class="card">

<h2>Documents I Sent</h2>

{sent_html}

</div>
"""

    return private_page(
        "My Documents",
        content
    )


# ============================================================
# STUDENT DOWNLOAD ADMIN DOCUMENT
#
# SECURITY:
# Student can only download a document where
# recipient_id equals the logged-in user's ID.
# ============================================================

@app.route(
    "/student/documents/download/<document_id>"
)
@login_required
def student_document_download(document_id):

    user = current_user()

    if user.get("role") == "admin":
        return redirect(
            url_for("admin_documents")
        )

    documents = read_json(
        DOCUMENTS_FILE,
        []
    )

    document = next(
        (
            d for d in documents
            if d.get("id") == document_id
            and d.get("direction") == "admin_to_student"
            and d.get("recipient_id") == user["id"]
        ),
        None
    )

    if not document:
        abort(403)

    filename = document.get("stored_name")

    if not filename:
        abort(404)

    path = os.path.join(
        ADMIN_UPLOAD_DIR,
        filename
    )

    if not os.path.isfile(path):
        abort(404)

    log_event(
        "Student Document Downloaded",
        "Documents",
        "INFO",
        document.get("original_name", filename)
    )

    return send_from_directory(
        ADMIN_UPLOAD_DIR,
        filename,
        as_attachment=True
    )


# ============================================================
# STUDENT DOWNLOAD OWN QUESTION ATTACHMENT
# ============================================================

@app.route(
    "/student/question-file/<question_id>/<stored_name>"
)
@login_required
def student_question_file(
    question_id,
    stored_name
):

    user = current_user()

    if user.get("role") == "admin":
        abort(403)

    questions = read_json(
        QUESTIONS_FILE,
        []
    )

    question = next(
        (
            q for q in questions
            if q.get("id") == question_id
            and q.get("student_id") == user["id"]
        ),
        None
    )

    if not question:
        abort(403)

    attachment = next(
        (
            a for a in question.get("attachments", [])
            if a.get("stored_name") == stored_name
        ),
        None
    )

    if not attachment:
        abort(404)

    path = os.path.join(
        STUDENT_UPLOAD_DIR,
        stored_name
    )

    if not os.path.isfile(path):
        abort(404)

    return send_from_directory(
        STUDENT_UPLOAD_DIR,
        stored_name,
        as_attachment=True
    )


# ============================================================
# STUDENT DOWNLOAD ADMIN ANSWER DOCUMENT
#
# Only the student who owns the question can download it.
# ============================================================

@app.route(
    "/student/answer-file/<question_id>/<stored_name>"
)
@login_required
def student_answer_file(
    question_id,
    stored_name
):

    user = current_user()

    if user.get("role") == "admin":
        abort(403)

    questions = read_json(
        QUESTIONS_FILE,
        []
    )

    question = next(
        (
            q for q in questions
            if q.get("id") == question_id
            and q.get("student_id") == user["id"]
        ),
        None
    )

    if not question:
        abort(403)

    attachment = next(
        (
            a for a in question.get("answer_attachments", [])
            if a.get("stored_name") == stored_name
        ),
        None
    )

    if not attachment:
        abort(404)

    path = os.path.join(
        ADMIN_UPLOAD_DIR,
        stored_name
    )

    if not os.path.isfile(path):
        abort(404)

    log_event(
        "Student Answer Document Downloaded",
        "Documents",
        "INFO",
        attachment.get("original_name", stored_name)
    )

    return send_from_directory(
        ADMIN_UPLOAD_DIR,
        stored_name,
        as_attachment=True
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    users = read_json(
        USERS_FILE,
        []
    )

    questions = read_json(
        QUESTIONS_FILE,
        []
    )

    documents = read_json(
        DOCUMENTS_FILE,
        []
    )

    logs = read_json(
        LOGS_FILE,
        []
    )

    students = [
        u for u in users
        if u.get("role") == "student"
    ]

    answered = [
        q for q in questions
        if q.get("answer")
    ]

    received = [
        d for d in documents
        if d.get("direction") == "student_to_admin"
    ]

    sent = [
        d for d in documents
        if d.get("direction") == "admin_to_student"
    ]

    content = f"""
<div class="card">

<h1>KOJA AFRICA ADMIN</h1>

<p>
Private administration area.
</p>

</div>

<div class="grid">

<div class="stat">
<h2>{len(students)}</h2>
<p>Students</p>
</div>

<div class="stat">
<h2>{len(questions)}</h2>
<p>Questions</p>
</div>

<div class="stat">
<h2>{len(answered)}</h2>
<p>Answered</p>
</div>

<div class="stat">
<h2>{len(received)}</h2>
<p>Student Documents</p>
</div>

<div class="stat">
<h2>{len(sent)}</h2>
<p>Documents Sent</p>
</div>

<div class="stat">
<h2>{len(logs)}</h2>
<p>Logs</p>
</div>

</div>

<div class="card">

<a
    class="btn"
    href="{url_for('admin_questions')}"
>
Questions
</a>

<a
    class="btn green"
    href="{url_for('admin_documents')}"
>
Documents
</a>

<a
    class="btn dark"
    href="{url_for('admin_answers')}"
>
Answers
</a>

</div>
"""

    return private_page(
        "Admin Dashboard",
        content
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    questions = read_json(
        QUESTIONS_FILE,
        []
    )

    blocks = []

    for q in reversed(questions):

        status = (
            "Answered"
            if q.get("answer")
            else "Pending"
        )

        status_class = (
            "answered"
            if q.get("answer")
            else "pending"
        )

        attachment_html = ""

        for attachment in q.get(
            "attachments",
            []
        ):

            attachment_html += f"""
<div class="document-box">

<strong>
Student Document
</strong>

<br><br>

{html_escape(
    attachment.get("original_name")
)}

<br><br>

<a
    class="btn gray"
    href="{url_for(
        'admin_question_file',
        question_id=q.get('id'),
        stored_name=attachment.get('stored_name')
    )}"
>
Download Student Document
</a>

</div>
"""

        blocks.append(f"""
<div class="card">

<h2>
{html_escape(q.get("question"))}
</h2>

<p>
Student:
<strong>
{html_escape(q.get("student_name"))}
</strong>
</p>

<p>
<span class="badge {status_class}">
{status}
</span>
</p>

{attachment_html}

<a
    class="btn"
    href="{url_for(
        'admin_answer',
        question_id=q.get('id')
    )}"
>
Answer Question
</a>

</div>
""")

    content = """
<div class="card">

<h1>Questions</h1>

<p>
Only administrators can see submitted
student questions.
</p>

</div>
"""

    content += "".join(blocks)

    if not blocks:
        content += """
<div class="card">
<div class="empty">
No questions have been submitted.
</div>
</div>
"""

    return private_page(
        "Questions",
        content
    )


# ============================================================
# ADMIN ANSWER QUESTION
# ============================================================

@app.route(
    "/admin/answer/<question_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_answer(question_id):

    questions = read_json(
        QUESTIONS_FILE,
        []
    )

    question = next(
        (
            q for q in questions
            if q.get("id") == question_id
        ),
        None
    )

    if not question:
        abort(404)

    if request.method == "POST":

        answer = request.form.get(
            "answer",
            ""
        ).strip()

        if not answer:
            flash(
                "Enter an answer.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_answer",
                    question_id=question_id
                )
            )

        question["answer"] = answer

        admin = current_user()

        question["answer_by"] = admin.get("name")

        question["answered_at"] = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        if "answer_attachments" not in question:
            question["answer_attachments"] = []

        file = request.files.get(
            "document"
        )

        if file and file.filename:

            try:
                saved = save_uploaded_file(
                    file,
                    ADMIN_UPLOAD_DIR
                )

                question[
                    "answer_attachments"
                ].append(saved)

            except ValueError as exc:
                flash(
                    str(exc),
                    "error"
                )

                return redirect(
                    url_for(
                        "admin_answer",
                        question_id=question_id
                    )
                )

        write_json(
            QUESTIONS_FILE,
            questions
        )

        log_event(
            "Question Answered",
            "Answers",
            "INFO",
            question_id
        )

        flash(
            "Answer saved successfully.",
            "success"
        )

        return redirect(
            url_for(
                "admin_questions"
            )
        )

    existing_files = ""

    for attachment in question.get(
        "answer_attachments",
        []
    ):

        existing_files += f"""
<div class="document-box">
{html_escape(
    attachment.get("original_name")
)}
</div>
"""

    content = f"""
<div class="card">

<h1>Answer Question</h1>

<p>
Student:
<strong>
{html_escape(question.get("student_name"))}
</strong>
</p>

<div class="question">
{html_escape(question.get("question"))}
</div>

{existing_files}

<form
    method="post"
    enctype="multipart/form-data"
>

<label>
Answer
</label>

<textarea
    name="answer"
    required
>{html_escape(question.get("answer", ""))}</textarea>

<label>
Attach answer document
</label>

<input
    type="file"
    name="document"
>

<p class="muted">
The student who submitted this question
will be able to download this document.
Maximum 15 MB.
</p>

<button type="submit">
Save Answer
</button>

</form>

</div>
"""

    return private_page(
        "Answer Question",
        content
    )


# ============================================================
# ADMIN ANSWERS
# ============================================================

@app.route("/admin/answers")
@admin_required
def admin_answers():

    questions = read_json(
        QUESTIONS_FILE,
        []
    )

    answered = [
        q for q in questions
        if q.get("answer")
    ]

    blocks = []

    for q in reversed(answered):

        blocks.append(f"""
<div class="card">

<h2>
{html_escape(q.get("question"))}
</h2>

<div class="answer">
{html_escape(q.get("answer"))}
</div>

<p>
Student:
{html_escape(q.get("student_name"))}
</p>

<p>
Answered by:
{html_escape(q.get("answer_by", "Admin"))}
</p>

</div>
""")

    content = """
<div class="card">

<h1>Answers</h1>

<p>
This section is visible only to administrators.
</p>

</div>
"""

    content += "".join(blocks)

    return private_page(
        "Answers",
        content
    )


# ============================================================
# ADMIN DOCUMENTS
#
# ADMIN CAN:
#   1. Receive documents from students.
#   2. Send documents to individual students.
#   3. Download both types.
# ============================================================

@app.route(
    "/admin/documents",
    methods=["GET", "POST"]
)
@admin_required
def admin_documents():

    admin = current_user()

    students = get_students()

    if request.method == "POST":

        student_id = request.form.get(
            "student_id",
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

        file = request.files.get(
            "document"
        )

        student = get_user_by_id(
            student_id
        )

        if not student or student.get("role") != "student":
            flash(
                "Please select a valid student.",
                "error"
            )

            return redirect(
                url_for("admin_documents")
            )

        if not title:
            flash(
                "Enter a document title.",
                "error"
            )

            return redirect(
                url_for("admin_documents")
            )

        if not file or not file.filename:
            flash(
                "Select a document.",
                "error"
            )

            return redirect(
                url_for("admin_documents")
            )

        try:
            saved = save_uploaded_file(
                file,
                ADMIN_UPLOAD_DIR
            )

        except ValueError as exc:
            flash(
                str(exc),
                "error"
            )

            return redirect(
                url_for("admin_documents")
            )

        documents = read_json(
            DOCUMENTS_FILE,
            []
        )

        document = {
            "id": str(uuid.uuid4()),
            "direction": "admin_to_student",

            "sender_id": admin["id"],
            "sender_name": admin["name"],

            "recipient_id": student["id"],
            "recipient_name": student["name"],

            "title": title,
            "description": description,

            "original_name": saved["original_name"],
            "stored_name": saved["stored_name"],
            "size": saved["size"],

            "created_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

        documents.append(document)

        write_json(
            DOCUMENTS_FILE,
            documents
        )

        log_event(
            "Document Sent To Student",
            "Documents",
            "INFO",
            f'{saved["original_name"]} -> {student["email"]}'
        )

        flash(
            f'Document sent to {student["name"]}.',
            "success"
        )

        return redirect(
            url_for("admin_documents")
        )

    documents = read_json(
        DOCUMENTS_FILE,
        []
    )

    received = [
        d for d in documents
        if d.get("direction") == "student_to_admin"
    ]

    sent = [
        d for d in documents
        if d.get("direction") == "admin_to_student"
    ]

    student_options = []

    for student in students:

        student_options.append(
            f"""
<option value="{html_escape(student.get("id"))}">
{html_escape(student.get("name"))}
-
{html_escape(student.get("email"))}
</option>
"""
        )

    received_rows = []

    for d in reversed(received):

        received_rows.append(f"""
<tr>

<td>
{html_escape(d.get("created_at", ""))}
</td>

<td>
<strong>
{html_escape(d.get("sender_name", "Student"))}
</strong>
</td>

<td>
{html_escape(d.get("title", ""))}
</td>

<td>
{html_escape(d.get("original_name", ""))}
<br>
<span class="muted">
{format_size(d.get("size", 0))}
</span>
</td>

<td>

<a
    class="btn"
    href="{url_for(
        'admin_document_download',
        document_id=d.get('id')
    )}"
>
Download
</a>

</td>

</tr>
""")

    sent_rows = []

    for d in reversed(sent):

        sent_rows.append(f"""
<tr>

<td>
{html_escape(d.get("created_at", ""))}
</td>

<td>
{html_escape(d.get("recipient_name", ""))}
</td>

<td>
{html_escape(d.get("title", ""))}
</td>

<td>
{html_escape(d.get("original_name", ""))}
<br>
<span class="muted">
{format_size(d.get("size", 0))}
</span>
</td>

<td>

<a
    class="btn"
    href="{url_for(
        'admin_document_download',
        document_id=d.get('id')
    )}"
>
Download
</a>

</td>

</tr>
""")

    if not received_rows:
        received_html = """
<div class="empty">
No documents have been received from students.
</div>
"""
    else:
        received_html = f"""
<div class="table-wrap">

<table>

<tr>
<th>Date</th>
<th>Student</th>
<th>Title</th>
<th>File</th>
<th>Download</th>
</tr>

{''.join(received_rows)}

</table>

</div>
"""

    if not sent_rows:
        sent_html = """
<div class="empty">
No documents have been sent to students.
</div>
"""
    else:
        sent_html = f"""
<div class="table-wrap">

<table>

<tr>
<th>Date</th>
<th>Student</th>
<th>Title</th>
<th>File</th>
<th>Download</th>
</tr>

{''.join(sent_rows)}

</table>

</div>
"""

    content = f"""
<div class="card">

<h1>Documents</h1>

<p>
This area is private to administrators.
</p>

</div>

<div class="card">

<h2>Send Document To Student</h2>

<form
    method="post"
    enctype="multipart/form-data"
>

<label>Student</label>

<select
    name="student_id"
    required
>

<option value="">
Select student
</option>

{''.join(student_options)}

</select>

<label>Document Title</label>

<input
    type="text"
    name="title"
    required
>

<label>Description</label>

<textarea
    name="description"
    placeholder="Optional description"
    style="min-height:120px;"
></textarea>

<label>Document</label>

<input
    type="file"
    name="document"
    required
>

<p class="muted">
The selected student will be the only student
allowed to download this document.
Maximum 15 MB.
</p>

<button type="submit">
Send Document
</button>

</form>

</div>

<div class="card">

<h2>Documents Received From Students</h2>

{received_html}

</div>

<div class="card">

<h2>Documents Sent To Students</h2>

{sent_html}

</div>
"""

    return private_page(
        "Documents",
        content
    )


# ============================================================
# ADMIN DOCUMENT DOWNLOAD
# ============================================================

@app.route(
    "/admin/documents/download/<document_id>"
)
@admin_required
def admin_document_download(document_id):

    documents = read_json(
        DOCUMENTS_FILE,
        []
    )

    document = next(
        (
            d for d in documents
            if d.get("id") == document_id
        ),
        None
    )

    if not document:
        abort(404)

    filename = document.get(
        "stored_name"
    )

    if not filename:
        abort(404)

    direction = document.get(
        "direction"
    )

    if direction == "student_to_admin":
        directory = STUDENT_UPLOAD_DIR
    else:
        directory = ADMIN_UPLOAD_DIR

    path = os.path.join(
        directory,
        filename
    )

    if not os.path.isfile(path):
        abort(404)

    log_event(
        "Admin Document Downloaded",
        "Documents",
        "INFO",
        document.get(
            "original_name",
            filename
        )
    )

    return send_from_directory(
        directory,
        filename,
        as_attachment=True
    )


# ============================================================
# ADMIN QUESTION ATTACHMENT
# ============================================================

@app.route(
    "/admin/question-file/<question_id>/<stored_name>"
)
@admin_required
def admin_question_file(
    question_id,
    stored_name
):

    questions = read_json(
        QUESTIONS_FILE,
        []
    )

    question = next(
        (
            q for q in questions
            if q.get("id") == question_id
        ),
        None
    )

    if not question:
        abort(404)

    attachment = next(
        (
            a for a in question.get("attachments", [])
            if a.get("stored_name") == stored_name
        ),
        None
    )

    if not attachment:
        abort(404)

    path = os.path.join(
        STUDENT_UPLOAD_DIR,
        stored_name
    )

    if not os.path.isfile(path):
        abort(404)

    log_event(
        "Admin Student Attachment Downloaded",
        "Documents",
        "INFO",
        attachment.get(
            "original_name",
            stored_name
        )
    )

    return send_from_directory(
        STUDENT_UPLOAD_DIR,
        stored_name,
        as_attachment=True
    )


# ============================================================
# ADMIN LOGS
# ============================================================

@app.route("/admin/logs")
@admin_required
def admin_logs():

    logs = read_json(
        LOGS_FILE,
        []
    )

    rows = []

    for item in reversed(logs[-500:]):

        rows.append(f"""
<tr>

<td>
{html_escape(item.get("time", ""))}
</td>

<td>
{html_escape(item.get("event", ""))}
</td>

<td>
{html_escape(item.get("category", ""))}
</td>

<td>
{html_escape(item.get("level", ""))}
</td>

<td>
{html_escape(item.get("details", ""))}
</td>

</tr>
""")

    content = f"""
<div class="card">

<h1>System Logs</h1>

<p>
Private administrator information.
Students cannot access this page.
</p>

<div class="table-wrap">

<table>

<tr>
<th>Time</th>
<th>Event</th>
<th>Category</th>
<th>Level</th>
<th>Details</th>
</tr>

{''.join(rows)}

</table>

</div>

</div>
"""

    return private_page(
        "Logs",
        content
    )


# ============================================================
# SECURITY HEADERS
# ============================================================

@app.after_request
def security_headers(response):

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "SAMEORIGIN"

    response.headers[
        "Referrer-Policy"
    ] = "strict-origin-when-cross-origin"

    private_prefixes = (
        "/admin",
        "/student",
        "/ask",
        "/research"
    )

    if request.path.startswith(
        private_prefixes
    ):

        response.headers[
            "Cache-Control"
        ] = (
            "no-store, "
            "no-cache, "
            "must-revalidate, "
            "private"
        )

        response.headers[
            "Pragma"
        ] = "no-cache"

        response.headers[
            "X-Robots-Tag"
        ] = "noindex, nofollow, noarchive"

    return response


# ============================================================
# ERROR PAGES
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    return public_page(
        "Access Denied",
        """
<div class="card">

<h1>Access Denied</h1>

<p>
You do not have permission to access
this page or document.
</p>

<a
    class="btn"
    href="/"
>
Return Home
</a>

</div>
"""
    ), 403


@app.errorhandler(404)
def not_found(error):

    return public_page(
        "Page Not Found",
        """
<div class="card">

<h1>Page Not Found</h1>

<p>
The requested page does not exist.
</p>

<a
    class="btn"
    href="/"
>
Return Home
</a>

</div>
"""
    ), 404


# ============================================================
# ROBOTS
# ============================================================

@app.route("/robots.txt")
def robots():

    text = """User-agent: *
Allow: /

Disallow: /admin
Disallow: /student
Disallow: /ask
Disallow: /research
Disallow: /logout
Disallow: /student/documents
"""

    response = make_response(text)

    response.headers[
        "Content-Type"
    ] = "text/plain"

    return response


# ============================================================
# SITEMAP
# ============================================================

@app.route("/sitemap.xml")
def sitemap():

    base = request.url_root.rstrip("/")

    xml = f"""<?xml version="1.0"
encoding="UTF-8"?>

<urlset
xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">

<url>
<loc>{base}/</loc>
</url>

<url>
<loc>{base}/login</loc>
</url>

<url>
<loc>{base}/register</loc>
</url>

</urlset>
"""

    response = make_response(xml)

    response.headers[
        "Content-Type"
    ] = "application/xml"

    return response


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

    print("=" * 60)
    print("KOJA AFRICA")
    print("Knowledge • Questions • Answers")
    print("=" * 60)
    print("PUBLIC:")
    print("  Home")
    print("  Log In")
    print("  Create Account")
    print()
    print("ADMIN:")
    print("  Dashboard")
    print("  Questions")
    print("  Answers")
    print("  Documents")
    print("  Logs")
    print()
    print("STUDENT:")
    print("  Dashboard")
    print("  Ask Question")
    print("  My Questions")
    print("  Research")
    print("  Documents")
    print()
    print("Server:", f"http://0.0.0.0:{port}")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
