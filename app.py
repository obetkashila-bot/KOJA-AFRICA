import os
import io
import uuid
import logging
from datetime import datetime, timezone
from functools import wraps

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

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

load_dotenv()

# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# Flask + Supabase REST API
#
# IMPORTANT:
# This version uses public.profiles as the account table.
# It DOES NOT use public.users.
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    os.getenv("SECRET_KEY", "change-this-secret-key")
)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KOJA")

# ============================================================
# SUPABASE CONFIGURATION
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    os.getenv("SUPABASE_KEY", "")
)

STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "koja-files"
)

if not SUPABASE_URL:
    logger.warning("SUPABASE_URL is not configured")

if not SUPABASE_SERVICE_KEY:
    logger.warning("SUPABASE_SERVICE_KEY is not configured")


# ============================================================
# SUPABASE HEADERS
# ============================================================

def supabase_headers(extra=None):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    if extra:
        headers.update(extra)

    return headers


# ============================================================
# DATABASE HELPERS
# ============================================================

def table_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"


def db_get(table, params=None):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase environment variables are missing")

    response = requests.get(
        table_url(table),
        headers=supabase_headers({
            "Accept": "application/json"
        }),
        params=params or {},
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Database GET failed: {response.status_code} {response.text}"
        )

    return response.json()


def db_post(table, data, returning="representation"):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase environment variables are missing")

    headers = supabase_headers({
        "Prefer": f"return={returning}"
    })

    response = requests.post(
        table_url(table),
        headers=headers,
        json=data,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Database POST failed: {response.status_code} {response.text}"
        )

    if not response.text:
        return []

    return response.json()


def db_patch(table, params, data):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase environment variables are missing")

    response = requests.patch(
        table_url(table),
        headers=supabase_headers({
            "Prefer": "return=representation"
        }),
        params=params,
        json=data,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Database PATCH failed: {response.status_code} {response.text}"
        )

    if not response.text:
        return []

    return response.json()


def db_delete(table, params):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase environment variables are missing")

    response = requests.delete(
        table_url(table),
        headers=supabase_headers(),
        params=params,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Database DELETE failed: {response.status_code} {response.text}"
        )

    return True


# ============================================================
# STORAGE
# ============================================================

def storage_object_url(path):
    path = path.lstrip("/")
    return (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{path}"
    )


def storage_upload(path, data, content_type="application/octet-stream"):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase environment variables are missing")

    url = storage_object_url(path)

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    response = requests.post(
        url,
        headers=headers,
        data=data,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Storage upload failed: {response.status_code} "
            f"{response.text}"
        )

    return path


def storage_download(path):
    if not path:
        raise RuntimeError("File path is empty")

    url = storage_object_url(path)

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Storage download failed: {response.status_code} "
            f"{response.text}"
        )

    return response.content, response.headers.get(
        "Content-Type",
        "application/octet-stream"
    )


def storage_delete(path):
    if not path:
        return

    url = storage_object_url(path)

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.delete(
        url,
        headers=headers,
        timeout=30,
    )

    if not response.ok:
        logger.warning(
            "Storage delete failed: %s %s",
            response.status_code,
            response.text
        )


# ============================================================
# USER HELPERS
# ============================================================

def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    try:
        rows = db_get(
            "profiles",
            {
                "id": f"eq.{user_id}",
                "select": "*",
                "limit": "1",
            }
        )

        if rows:
            return rows[0]

    except Exception as exc:
        logger.exception("Could not load current user: %s", exc)

    return None


def is_admin_user(user):
    if not user:
        return False

    return (
        user.get("is_admin") is True
        or str(user.get("role", "")).lower() == "admin"
    )


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login first.", "error")
            return redirect(url_for("login"))

        user = current_user()

        if not user:
            session.clear()
            flash("Your account could not be found.", "error")
            return redirect(url_for("login"))

        if user.get("is_active") is False:
            session.clear()
            flash("Your account has been disabled.", "error")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("user_id"):
            flash("Administrator login required.", "error")
            return redirect(url_for("login"))

        user = current_user()

        if not user:
            session.clear()
            return redirect(url_for("login"))

        if not is_admin_user(user):
            flash("Administrator access required.", "error")
            return redirect(url_for("dashboard"))

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# ACTIVITY LOG
# ============================================================

def log_activity(action, description="", user_id=None, email=None):
    try:
        db_post(
            "activity_logs",
            {
                "user_id": user_id,
                "action": action,
                "description": description,
                "ip_address": request.remote_addr,
                "user_agent": request.headers.get(
                    "User-Agent",
                    ""
                ),
                "email": email,
            },
            returning="minimal",
        )
    except Exception as exc:
        logger.warning(
            "Activity log failed: %s",
            exc
        )


# ============================================================
# HTML
# ============================================================

BASE_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width,initial-scale=1">

<title>{{ title or "KOJA Africa" }}</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f3f6fb;
    color: #172033;
}

nav {
    background: #12479b;
    color: white;
    padding: 16px 5%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
}

.logo {
    font-size: 24px;
    font-weight: bold;
}

nav a {
    color: white;
    text-decoration: none;
    margin: 0 7px;
    font-size: 16px;
}

.container {
    width: 92%;
    max-width: 1100px;
    margin: 25px auto;
}

.card {
    background: white;
    border-radius: 14px;
    padding: 22px;
    margin-bottom: 18px;
    box-shadow: 0 3px 15px rgba(0,0,0,.06);
}

h1, h2, h3 {
    margin-top: 0;
}

input,
textarea,
select {
    width: 100%;
    padding: 13px;
    border: 1px solid #ccd3df;
    border-radius: 8px;
    margin: 7px 0 15px;
    font-size: 15px;
}

textarea {
    min-height: 160px;
    resize: vertical;
}

button,
.btn {
    border: 0;
    border-radius: 8px;
    background: #12479b;
    color: white;
    padding: 12px 18px;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
}

.btn-danger {
    background: #c62828;
}

.btn-success {
    background: #18864b;
}

.btn-secondary {
    background: #555;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(220px, 1fr));
    gap: 15px;
}

.stat {
    background: white;
    border-radius: 14px;
    padding: 20px;
    box-shadow: 0 3px 15px rgba(0,0,0,.06);
}

.stat strong {
    display: block;
    font-size: 30px;
    margin-top: 8px;
}

.flash {
    padding: 14px;
    border-radius: 8px;
    background: #e7f0ff;
    margin-bottom: 15px;
    word-break: break-word;
}

.flash.error {
    background: #ffe8e8;
    color: #8d1717;
}

.flash.success {
    background: #e5f8eb;
    color: #146b32;
}

.question {
    border-left: 5px solid #12479b;
    padding: 15px;
    background: #f7f9fd;
    margin: 12px 0;
    border-radius: 8px;
}

.small {
    color: #667085;
    font-size: 13px;
}

.badge {
    display: inline-block;
    padding: 5px 9px;
    border-radius: 20px;
    background: #e7eefb;
    font-size: 12px;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    padding: 10px;
    border-bottom: 1px solid #ddd;
    text-align: left;
}

pre {
    white-space: pre-wrap;
    word-break: break-word;
}

footer {
    margin-top: 40px;
    padding: 25px;
    text-align: center;
    color: #667085;
}

</style>
</head>

<body>

<nav>

<div class="logo">
KOJA AFRICA
</div>

<div>

<a href="{{ url_for('home') }}">Home</a>

{% if session.get('user_id') %}
<a href="{{ url_for('dashboard') }}">Dashboard</a>
<a href="{{ url_for('my_assignments') }}">My Questions</a>

{% if session.get('is_admin') %}
<a href="{{ url_for('admin_dashboard') }}">Admin</a>
{% endif %}

<a href="{{ url_for('logout') }}">Logout</a>

{% else %}

<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Register</a>

{% endif %}

</div>

</nav>

<div class="container">

{% with messages = get_flashed_messages(with_categories=true) %}

{% for category, message in messages %}

<div class="flash {{ category }}">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</div>

<footer>
KOJA AFRICA —
Knowledge • Questions • Answers
</footer>

</body>
</html>
"""


def render_page(content, title="KOJA Africa"):
    return render_template_string(
        BASE_HTML,
        content=content,
        title=title,
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    content = """
    <div class="card">
        <h1>KOJA AFRICA</h1>

        <h3>
        Assignment Questions • Academic Answers
        </h3>

        <p>
        Submit academic questions, assignments and
        documents and receive answers through KOJA Africa.
        </p>

        <p>
        <a class="btn" href="/register">Create Account</a>
        <a class="btn btn-secondary" href="/login">Login</a>
        </p>
    </div>

    <div class="grid">

        <div class="card">
            <h3>Questions</h3>
            <p>
            Submit your academic questions and assignments.
            </p>
        </div>

        <div class="card">
            <h3>Answers</h3>
            <p>
            Administrators can review and answer submitted
            questions.
            </p>
        </div>

        <div class="card">
            <h3>Documents</h3>
            <p>
            Upload and download supported academic files.
            </p>
        </div>

    </div>
    """

    return render_page(content)


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        institution = request.form.get(
            "institution",
            ""
        ).strip()
        student_number = request.form.get(
            "student_number",
            ""
        ).strip()

        if not name or not email or not password:
            flash(
                "Name, email and password are required.",
                "error"
            )

        elif len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "error"
            )

        else:

            try:

                # ------------------------------------------------
                # IMPORTANT:
                # We check PROFILES, NOT USERS.
                # ------------------------------------------------

                existing = db_get(
                    "profiles",
                    {
                        "email": f"eq.{email}",
                        "select": "id,email",
                        "limit": "1",
                    }
                )

                if existing:
                    flash(
                        "An account with this email already exists.",
                        "error"
                    )

                else:

                    user_id = str(uuid.uuid4())

                    profile = {
                        "id": user_id,
                        "name": name,
                        "full_name": name,
                        "email": email,
                        "role": "student",
                        "password_hash":
                            generate_password_hash(password),
                        "phone": phone or None,
                        "institution": institution or None,
                        "student_number":
                            student_number or None,
                        "is_active": True,
                        "is_admin": False,
                    }

                    # ------------------------------------------------
                    # THIS IS THE CRITICAL FIX.
                    #
                    # No insertion into public.users.
                    # No foreign-key dependency.
                    # ------------------------------------------------

                    created = db_post(
                        "profiles",
                        profile
                    )

                    if not created:
                        raise RuntimeError(
                            "Profile account was not created."
                        )

                    session.clear()

                    session["user_id"] = user_id
                    session["is_admin"] = False
                    session["email"] = email

                    log_activity(
                        "register",
                        "New student account registered",
                        user_id,
                        email
                    )

                    flash(
                        "Registration successful.",
                        "success"
                    )

                    return redirect(
                        url_for("dashboard")
                    )

            except Exception as exc:

                logger.exception(
                    "Registration failed"
                )

                flash(
                    "Registration error: " + str(exc),
                    "error"
                )

    content = """
    <div class="card">

        <h2>Create KOJA Account</h2>

        <form method="POST">

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

            <label>Phone</label>
            <input
                type="text"
                name="phone"
            >

            <label>Institution</label>
            <input
                type="text"
                name="institution"
            >

            <label>Student Number</label>
            <input
                type="text"
                name="student_number"
            >

            <label>Password</label>
            <input
                type="password"
                name="password"
                minlength="6"
                required
            >

            <button type="submit">
                Register
            </button>

        </form>

    </div>
    """

    return render_page(
        content,
        "Register - KOJA Africa"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
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

        try:

            rows = db_get(
                "profiles",
                {
                    "email": f"eq.{email}",
                    "select": "*",
                    "limit": "1",
                }
            )

            if not rows:
                flash(
                    "Invalid email or password.",
                    "error"
                )

            else:

                user = rows[0]

                if user.get("is_active") is False:
                    flash(
                        "Your account is disabled.",
                        "error"
                    )

                else:

                    stored_hash = user.get(
                        "password_hash"
                    )

                    valid = False

                    if stored_hash:
                        try:
                            valid = check_password_hash(
                                stored_hash,
                                password
                            )
                        except Exception:
                            valid = False

                    if valid:

                        session.clear()

                        session["user_id"] = user["id"]
                        session["email"] = user["email"]
                        session["is_admin"] = (
                            is_admin_user(user)
                        )

                        log_activity(
                            "login",
                            "User logged in",
                            user["id"],
                            user["email"]
                        )

                        if is_admin_user(user):
                            return redirect(
                                url_for("admin_dashboard")
                            )

                        return redirect(
                            url_for("dashboard")
                        )

                    flash(
                        "Invalid email or password.",
                        "error"
                    )

        except Exception as exc:

            logger.exception(
                "Login failed"
            )

            flash(
                "Login error: " + str(exc),
                "error"
            )

    content = """
    <div class="card">

        <h2>Login</h2>

        <form method="POST">

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

    </div>
    """

    return render_page(
        content,
        "Login - KOJA Africa"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    user_id = session.get("user_id")
    email = session.get("email")

    if user_id:
        log_activity(
            "logout",
            "User logged out",
            user_id,
            email
        )

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(url_for("home"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    user = current_user()

    try:

        assignments = db_get(
            "assignments",
            {
                "student_id": f"eq.{user['id']}",
                "select": "*",
                "order": "created_at.desc",
            }
        )

    except Exception as exc:

        logger.exception(
            "Dashboard assignments failed"
        )

        assignments = []

        flash(
            "Could not load assignments: " + str(exc),
            "error"
        )

    total = len(assignments)

    answered = len([
        a for a in assignments
        if (
            a.get("answer")
            or a.get("answer_text")
            or a.get("answer_file_path")
            or a.get("answer_path")
            or a.get("answer_pdf_path")
            or a.get("answer_word_path")
        )
    ])

    content = f"""
    <div class="grid">

        <div class="stat">
            <div>Total Questions</div>
            <strong>{total}</strong>
        </div>

        <div class="stat">
            <div>Answered</div>
            <strong>{answered}</strong>
        </div>

        <div class="stat">
            <div>Account</div>
            <strong>Student</strong>
        </div>

    </div>

    <div class="card">

        <h2>Welcome, {user.get('full_name') or user.get('name') or 'Student'}</h2>

        <p>
        Email: {user.get('email', '')}
        </p>

        <p>
        Institution:
        {user.get('institution') or 'Not provided'}
        </p>

        <a class="btn"
           href="/submit-question">
           Submit Question
        </a>

    </div>
    """

    return render_page(
        content,
        "Dashboard - KOJA Africa"
    )


# ============================================================
# SUBMIT QUESTION / ASSIGNMENT
# ============================================================

@app.route(
    "/submit-question",
    methods=["GET", "POST"]
)
@login_required
def submit_question():

    user = current_user()

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        question = request.form.get(
            "question",
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

        uploaded_file = request.files.get(
            "file"
        )

        if not title:
            flash(
                "Please enter a title.",
                "error"
            )

        elif not question and not uploaded_file:
            flash(
                "Enter a question or upload a question file.",
                "error"
            )

        else:

            try:

                assignment_id = str(uuid.uuid4())

                file_name = None
                file_path = None
                file_size = 0
                mime_type = (
                    "application/pdf"
                )

                # ------------------------------------------------
                # Upload question file if provided
                # ------------------------------------------------

                if uploaded_file and uploaded_file.filename:

                    original = uploaded_file.filename

                    extension = os.path.splitext(
                        original
                    )[1].lower()

                    safe_name = (
                        f"{uuid.uuid4()}{extension}"
                    )

                    storage_path = (
                        f"assignments/"
                        f"{user['id']}/"
                        f"{safe_name}"
                    )

                    file_bytes = uploaded_file.read()

                    file_size = len(file_bytes)

                    mime_type = (
                        uploaded_file.mimetype
                        or "application/octet-stream"
                    )

                    storage_upload(
                        storage_path,
                        file_bytes,
                        mime_type
                    )

                    file_name = original
                    file_path = storage_path

                assignment = {

                    "id": assignment_id,

                    "student_id":
                        user["id"],

                    "title":
                        title,

                    "description":
                        description or None,

                    "subject":
                        subject or None,

                    "course":
                        course or None,

                    "class_level":
                        class_level or None,

                    "file_name":
                        file_name,

                    "file_path":
                        file_path,

                    "file_size":
                        file_size,

                    "mime_type":
                        mime_type,

                    "status":
                        "submitted",

                    "email":
                        user.get("email"),

                    "question":
                        question or None,

                    "student_name":
                        user.get("full_name")
                        or user.get("name"),

                    "student_email":
                        user.get("email"),

                    "institution":
                        user.get("institution"),

                }

                db_post(
                    "assignments",
                    assignment
                )

                log_activity(
                    "submit_assignment",
                    f"Submitted: {title}",
                    user["id"],
                    user["email"]
                )

                flash(
                    "Question submitted successfully.",
                    "success"
                )

                return redirect(
                    url_for(
                        "assignment_detail",
                        assignment_id=assignment_id
                    )
                )

            except Exception as exc:

                logger.exception(
                    "Question submission failed"
                )

                flash(
                    "Submission error: " + str(exc),
                    "error"
                )

    content = """
    <div class="card">

        <h2>Submit Academic Question</h2>

        <form
            method="POST"
            enctype="multipart/form-data"
        >

            <label>Title</label>

            <input
                type="text"
                name="title"
                placeholder="Example: Biology Assignment"
                required
            >

            <label>Subject</label>

            <input
                type="text"
                name="subject"
                placeholder="Biology"
            >

            <label>Course</label>

            <input
                type="text"
                name="course"
                placeholder="Example: Diploma in Education"
            >

            <label>Class / Level</label>

            <input
                type="text"
                name="class_level"
                placeholder="Example: Grade 12"
            >

            <label>Question</label>

            <textarea
                name="question"
                placeholder="Write your question here..."
            ></textarea>

            <label>
                Description / Instructions
            </label>

            <textarea
                name="description"
                placeholder="Additional instructions..."
            ></textarea>

            <label>
                Upload Question File
            </label>

            <input
                type="file"
                name="file"
                accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.jpg,.jpeg,.png"
            >

            <button type="submit">
                Submit Question
            </button>

        </form>

    </div>
    """

    return render_page(
        content,
        "Submit Question - KOJA Africa"
    )


# ============================================================
# MY ASSIGNMENTS
# ============================================================

@app.route("/my-assignments")
@login_required
def my_assignments():

    user = current_user()

    try:

        rows = db_get(
            "assignments",
            {
                "student_id": f"eq.{user['id']}",
                "select": "*",
                "order": "created_at.desc",
            }
        )

    except Exception as exc:

        rows = []

        flash(
            "Could not load questions: " + str(exc),
            "error"
        )

    html = """
    <div class="card">
        <h2>My Questions</h2>

        <a class="btn"
           href="/submit-question">
           Submit New Question
        </a>
    </div>
    """

    if not rows:

        html += """
        <div class="card">
            <p>You have not submitted any questions yet.</p>
        </div>
        """

    else:

        for item in rows:

            assignment_id = item.get("id")

            title = (
                item.get("title")
                or "Untitled Question"
            )

            status = (
                item.get("status")
                or "submitted"
            )

            html += f"""
            <div class="card">

                <h3>{title}</h3>

                <p>
                    <span class="badge">
                    {status}
                    </span>
                </p>

                <p>
                Subject:
                {item.get('subject') or 'Not specified'}
                </p>

                <p>
                Submitted:
                {item.get('created_at') or ''}
                </p>

                <a class="btn"
                   href="/assignment/{assignment_id}">
                   View
                </a>

            </div>
            """

    return render_page(
        html,
        "My Questions - KOJA Africa"
    )


# ============================================================
# ASSIGNMENT DETAIL
# ============================================================

@app.route("/assignment/<assignment_id>")
@login_required
def assignment_detail(assignment_id):

    user = current_user()

    try:

        rows = db_get(
            "assignments",
            {
                "id": f"eq.{assignment_id}",
                "select": "*",
                "limit": "1",
            }
        )

        if not rows:
            abort(404)

        assignment = rows[0]

        # Student may only see own assignment.
        if (
            not is_admin_user(user)
            and assignment.get("student_id")
            != user.get("id")
        ):
            abort(403)

    except Exception as exc:

        logger.exception(
            "Assignment detail failed"
        )

        flash(
            "Could not load assignment: " + str(exc),
            "error"
        )

        return redirect(
            url_for("dashboard")
        )

    question = (
        assignment.get("question")
        or assignment.get("description")
        or "No written question."
    )

    answer = (
        assignment.get("answer")
        or assignment.get("answer_text")
    )

    answer_path = (
        assignment.get("answer_file_path")
        or assignment.get("answer_path")
        or assignment.get("answer_pdf_path")
        or assignment.get("answer_word_path")
        or assignment.get("answer_excel_path")
    )

    question_path = (
        assignment.get("file_path")
        or assignment.get("question_path")
    )

    html = f"""
    <div class="card">

        <h2>
        {assignment.get('title') or 'Assignment'}
        </h2>

        <p>
        <span class="badge">
        {assignment.get('status') or 'submitted'}
        </span>
        </p>

        <p>
        <strong>Subject:</strong>
        {assignment.get('subject') or 'Not specified'}
        </p>

        <p>
        <strong>Course:</strong>
        {assignment.get('course') or 'Not specified'}
        </p>

        <p>
        <strong>Class:</strong>
        {assignment.get('class_level') or 'Not specified'}
        </p>

    </div>

    <div class="card">

        <h3>Question</h3>

        <div class="question">
        <pre>{question}</pre>
        </div>
    """

    if question_path:

        html += f"""
        <a class="btn"
           href="/download-assignment/{assignment_id}">
           Download Question File
        </a>
        """

    html += """
    </div>

    <div class="card">

        <h3>Answer</h3>
    """

    if answer:

        html += f"""
        <div class="question">
            <pre>{answer}</pre>
        </div>
        """

    else:

        html += """
        <p>
        Your question has not been answered yet.
        </p>
        """

    if answer_path:

        html += f"""
        <p>
        <a class="btn btn-success"
           href="/download-answer/{assignment_id}">
           Download Answer File
        </a>
        </p>
        """

    html += "</div>"

    return render_page(
        html,
        "Assignment - KOJA Africa"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    try:

        assignments = db_get(
            "assignments",
            {
                "select": "*",
                "order": "created_at.desc",
            }
        )

    except Exception as exc:

        assignments = []

        flash(
            "Could not load assignments: " + str(exc),
            "error"
        )

    try:

        profiles = db_get(
            "profiles",
            {
                "select": "id,name,full_name,email,role,is_admin,is_active,created_at",
                "order": "created_at.desc",
            }
        )

    except Exception:

        profiles = []

    total_users = len(profiles)

    total_assignments = len(assignments)

    pending = len([
        a for a in assignments
        if str(
            a.get("status", "")
        ).lower()
        in (
            "submitted",
            "pending",
            "draft"
        )
    ])

    answered = len([
        a for a in assignments
        if (
            a.get("answer")
            or a.get("answer_text")
            or a.get("answer_file_path")
            or a.get("answer_path")
            or a.get("answer_pdf_path")
            or a.get("answer_word_path")
            or a.get("answer_excel_path")
        )
    ])

    html = f"""
    <h1>Administrator Dashboard</h1>

    <div class="grid">

        <div class="stat">
            Users
            <strong>{total_users}</strong>
        </div>

        <div class="stat">
            Questions
            <strong>{total_assignments}</strong>
        </div>

        <div class="stat">
            Pending
            <strong>{pending}</strong>
        </div>

        <div class="stat">
            Answered
            <strong>{answered}</strong>
        </div>

    </div>

    <div class="card">

        <h2>Administration</h2>

        <a class="btn"
           href="/admin/questions">
           Manage Questions
        </a>

        <a class="btn"
           href="/admin/users">
           Manage Users
        </a>

        <a class="btn"
           href="/admin/create-admin">
           Create Admin
        </a>

    </div>
    """

    return render_page(
        html,
        "Admin Dashboard - KOJA Africa"
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    try:

        assignments = db_get(
            "assignments",
            {
                "select": "*",
                "order": "created_at.desc",
            }
        )

    except Exception as exc:

        assignments = []

        flash(
            "Could not load questions: " + str(exc),
            "error"
        )

    html = """
    <div class="card">
        <h2>Submitted Questions</h2>
    </div>
    """

    if not assignments:

        html += """
        <div class="card">
            <p>No questions have been submitted.</p>
        </div>
        """

    for a in assignments:

        html += f"""
        <div class="card">

            <h3>
            {a.get('title') or 'Untitled'}
            </h3>

            <p>
            Student:
            {a.get('student_name') or 'Unknown'}
            </p>

            <p>
            Email:
            {a.get('student_email')
              or a.get('email')
              or 'Unknown'}
            </p>

            <p>
            Subject:
            {a.get('subject') or 'Not specified'}
            </p>

            <p>
            Status:
            <span class="badge">
            {a.get('status') or 'submitted'}
            </span>
            </p>

            <a class="btn"
               href="/admin/question/{a.get('id')}">
               Open Question
            </a>

        </div>
        """

    return render_page(
        html,
        "Manage Questions - KOJA Africa"
    )


# ============================================================
# ADMIN QUESTION DETAIL
# ============================================================

@app.route(
    "/admin/question/<assignment_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_question(assignment_id):

    admin = current_user()

    rows = db_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    if request.method == "POST":

        answer_text = request.form.get(
            "answer",
            ""
        ).strip()

        admin_notes = request.form.get(
            "admin_notes",
            ""
        ).strip()

        status = request.form.get(
            "status",
            "answered"
        ).strip()

        answer_file = request.files.get(
            "answer_file"
        )

        update = {
            "answer": answer_text or None,
            "answer_text": answer_text or None,
            "admin_notes":
                admin_notes or None,
            "status": status,
            "answered_by": admin["id"],
            "processed_by": admin["id"],
            "processed_at":
                datetime.now(timezone.utc).isoformat(),
            "answered_at":
                datetime.now(timezone.utc).isoformat(),
            "completed_at":
                datetime.now(timezone.utc).isoformat(),
        }

        try:

            # ------------------------------------------------
            # Upload answer file
            # ------------------------------------------------

            if (
                answer_file
                and answer_file.filename
            ):

                original = answer_file.filename

                extension = os.path.splitext(
                    original
                )[1].lower()

                stored_name = (
                    f"{uuid.uuid4()}{extension}"
                )

                storage_path = (
                    f"answers/"
                    f"{assignment.get('student_id') or 'unknown'}/"
                    f"{stored_name}"
                )

                file_bytes = answer_file.read()

                mime = (
                    answer_file.mimetype
                    or "application/octet-stream"
                )

                storage_upload(
                    storage_path,
                    file_bytes,
                    mime
                )

                update["answer_file_name"] = original
                update["answer_file_path"] = storage_path
                update["answer_filename"] = original
                update["answer_path"] = storage_path

                # Keep legacy fields useful.
                if extension == ".pdf":
                    update["answer_pdf_path"] = storage_path

                elif extension in (
                    ".doc",
                    ".docx"
                ):
                    update["answer_word_path"] = storage_path

                elif extension in (
                    ".xls",
                    ".xlsx"
                ):
                    update["answer_excel_path"] = storage_path

            db_patch(
                "assignments",
                {
                    "id": f"eq.{assignment_id}"
                },
                update
            )

            # ------------------------------------------------
            # Also record response in assignment_responses
            # ------------------------------------------------

            response_data = {
                "id": str(uuid.uuid4()),
                "assignment_id":
                    assignment_id,
                "admin_id":
                    admin["id"],
                "response_text":
                    answer_text or None,
            }

            if update.get("answer_file_path"):
                response_data["file_name"] = (
                    update.get("answer_file_name")
                )
                response_data["file_path"] = (
                    update.get("answer_file_path")
                )

            try:

                db_post(
                    "assignment_responses",
                    response_data,
                    returning="minimal"
                )

            except Exception as exc:

                logger.warning(
                    "assignment_responses insert failed: %s",
                    exc
                )

            log_activity(
                "answer_assignment",
                f"Answered assignment {assignment_id}",
                admin["id"],
                admin["email"]
            )

            flash(
                "Answer saved successfully.",
                "success"
            )

            return redirect(
                url_for(
                    "admin_question",
                    assignment_id=assignment_id
                )
            )

        except Exception as exc:

            logger.exception(
                "Answer failed"
            )

            flash(
                "Could not save answer: " + str(exc),
                "error"
            )

    question = (
        assignment.get("question")
        or assignment.get("description")
        or ""
    )

    html = f"""
    <div class="card">

        <h2>
        {assignment.get('title') or 'Question'}
        </h2>

        <p>
        <strong>Student:</strong>
        {assignment.get('student_name') or 'Unknown'}
        </p>

        <p>
        <strong>Email:</strong>
        {assignment.get('student_email')
          or assignment.get('email')
          or 'Unknown'}
        </p>

        <p>
        <strong>Institution:</strong>
        {assignment.get('institution')
          or 'Not provided'}
        </p>

        <p>
        <strong>Subject:</strong>
        {assignment.get('subject')
          or 'Not specified'}
        </p>

    </div>

    <div class="card">

        <h3>Question</h3>

        <div class="question">
            <pre>{question}</pre>
        </div>
    """

    if assignment.get("file_path"):

        html += f"""
        <a class="btn"
           href="/admin/download-question/{assignment_id}">
           Download Question File
        </a>
        """

    html += f"""

    </div>

    <div class="card">

        <h3>Answer Student</h3>

        <form
            method="POST"
            enctype="multipart/form-data"
        >

            <label>Answer</label>

            <textarea
                name="answer"
                placeholder="Write the academic answer here..."
            >{assignment.get('answer') or assignment.get('answer_text') or ''}</textarea>

            <label>Admin Notes</label>

            <textarea
                name="admin_notes"
                placeholder="Internal notes..."
            >{assignment.get('admin_notes') or ''}</textarea>

            <label>Status</label>

            <select name="status">

                <option value="answered">
                    Answered
                </option>

                <option value="completed">
                    Completed
                </option>

                <option value="pending">
                    Pending
                </option>

                <option value="submitted">
                    Submitted
                </option>

            </select>

            <label>
                Upload Answer File
            </label>

            <input
                type="file"
                name="answer_file"
                accept=".pdf,.doc,.docx,.xls,.xlsx,.txt"
            >

            <button
                type="submit"
                class="btn-success"
            >
                Save Answer
            </button>

        </form>

    </div>
    """

    return render_page(
        html,
        "Answer Question - KOJA Africa"
    )


# ============================================================
# ADMIN USERS
# ============================================================

@app.route("/admin/users")
@admin_required
def admin_users():

    try:

        users = db_get(
            "profiles",
            {
                "select": "*",
                "order": "created_at.desc",
            }
        )

    except Exception as exc:

        users = []

        flash(
            "Could not load users: " + str(exc),
            "error"
        )

    html = """
    <div class="card">
        <h2>KOJA Users</h2>
    </div>

    <div class="card">

    <table>

    <tr>
        <th>Name</th>
        <th>Email</th>
        <th>Role</th>
        <th>Admin</th>
        <th>Active</th>
    </tr>
    """

    for user in users:

        html += f"""
        <tr>

            <td>
            {user.get('full_name')
             or user.get('name')
             or ''}
            </td>

            <td>
            {user.get('email') or ''}
            </td>

            <td>
            {user.get('role') or ''}
            </td>

            <td>
            {user.get('is_admin')}
            </td>

            <td>
            {user.get('is_active')}
            </td>

        </tr>
        """

    html += """
    </table>

    </div>
    """

    return render_page(
        html,
        "Users - KOJA Africa"
    )


# ============================================================
# CREATE ADMIN
# ============================================================

@app.route(
    "/admin/create-admin",
    methods=["GET", "POST"]
)
@admin_required
def create_admin():

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
                "All fields are required.",
                "error"
            )

        else:

            try:

                existing = db_get(
                    "profiles",
                    {
                        "email": f"eq.{email}",
                        "select": "id",
                        "limit": "1",
                    }
                )

                if existing:

                    flash(
                        "That email already exists.",
                        "error"
                    )

                else:

                    new_id = str(uuid.uuid4())

                    db_post(
                        "profiles",
                        {
                            "id": new_id,
                            "name": name,
                            "full_name": name,
                            "email": email,
                            "role": "admin",
                            "password_hash":
                                generate_password_hash(password),
                            "is_active": True,
                            "is_admin": True,
                        }
                    )

                    flash(
                        "Administrator created successfully.",
                        "success"
                    )

                    return redirect(
                        url_for("admin_users")
                    )

            except Exception as exc:

                logger.exception(
                    "Admin creation failed"
                )

                flash(
                    "Could not create admin: " + str(exc),
                    "error"
                )

    content = """
    <div class="card">

        <h2>Create Administrator</h2>

        <form method="POST">

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
                Create Administrator
            </button>

        </form>

    </div>
    """

    return render_page(
        content,
        "Create Admin - KOJA Africa"
    )


# ============================================================
# DOWNLOAD QUESTION
# ============================================================

@app.route(
    "/download-assignment/<assignment_id>"
)
@login_required
def download_assignment(assignment_id):

    user = current_user()

    rows = db_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    if (
        not is_admin_user(user)
        and assignment.get("student_id")
        != user.get("id")
    ):
        abort(403)

    path = (
        assignment.get("file_path")
        or assignment.get("question_path")
    )

    if not path:
        flash(
            "There is no question file.",
            "error"
        )

        return redirect(
            url_for(
                "assignment_detail",
                assignment_id=assignment_id
            )
        )

    try:

        data, mime = storage_download(path)

        filename = (
            assignment.get("file_name")
            or assignment.get("question_filename")
            or "question"
        )

        return send_file(
            io.BytesIO(data),
            mimetype=mime,
            as_attachment=True,
            download_name=filename,
        )

    except Exception as exc:

        flash(
            "Could not download file: " + str(exc),
            "error"
        )

        return redirect(
            url_for(
                "assignment_detail",
                assignment_id=assignment_id
            )
        )


# ============================================================
# ADMIN DOWNLOAD QUESTION
# ============================================================

@app.route(
    "/admin/download-question/<assignment_id>"
)
@admin_required
def admin_download_question(assignment_id):

    rows = db_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    path = (
        assignment.get("file_path")
        or assignment.get("question_path")
    )

    if not path:
        abort(404)

    try:

        data, mime = storage_download(path)

        filename = (
            assignment.get("file_name")
            or assignment.get("question_filename")
            or "question"
        )

        return send_file(
            io.BytesIO(data),
            mimetype=mime,
            as_attachment=True,
            download_name=filename,
        )

    except Exception as exc:

        flash(
            "Download failed: " + str(exc),
            "error"
        )

        return redirect(
            url_for(
                "admin_question",
                assignment_id=assignment_id
            )
        )


# ============================================================
# DOWNLOAD ANSWER
# ============================================================

@app.route(
    "/download-answer/<assignment_id>"
)
@login_required
def download_answer(assignment_id):

    user = current_user()

    rows = db_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    if (
        not is_admin_user(user)
        and assignment.get("student_id")
        != user.get("id")
    ):
        abort(403)

    path = (
        assignment.get("answer_file_path")
        or assignment.get("answer_path")
        or assignment.get("answer_pdf_path")
        or assignment.get("answer_word_path")
        or assignment.get("answer_excel_path")
    )

    if not path:
        flash(
            "No answer file is available.",
            "error"
        )

        return redirect(
            url_for(
                "assignment_detail",
                assignment_id=assignment_id
            )
        )

    try:

        data, mime = storage_download(path)

        filename = (
            assignment.get("answer_file_name")
            or assignment.get("answer_filename")
            or "koja-answer"
        )

        return send_file(
            io.BytesIO(data),
            mimetype=mime,
            as_attachment=True,
            download_name=filename,
        )

    except Exception as exc:

        flash(
            "Could not download answer: " + str(exc),
            "error"
        )

        return redirect(
            url_for(
                "assignment_detail",
                assignment_id=assignment_id
            )
        )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    result = {
        "status": "ok",
        "supabase": bool(
            SUPABASE_URL
            and SUPABASE_SERVICE_KEY
        ),
        "profiles_table": False,
        "users_table_used": False,
        "assignments_table": False,
    }

    try:

        profiles = db_get(
            "profiles",
            {
                "select": "id",
                "limit": "1",
            }
        )

        result["profiles_table"] = True
        result["profiles_rows"] = len(profiles)

    except Exception as exc:

        result["profiles_error"] = str(exc)

    try:

        assignments = db_get(
            "assignments",
            {
                "select": "id",
                "limit": "1",
            }
        )

        result["assignments_table"] = True
        result["assignments_rows"] = len(assignments)

    except Exception as exc:

        result["assignments_error"] = str(exc)

    return result


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return render_page(
        """
        <div class="card">
            <h2>Page Not Found</h2>
            <p>The requested page does not exist.</p>
            <a class="btn" href="/">
                Home
            </a>
        </div>
        """,
        "Not Found"
    ), 404


@app.errorhandler(403)
def forbidden(error):

    return render_page(
        """
        <div class="card">
            <h2>Access Denied</h2>
            <p>You do not have permission to access this page.</p>
        </div>
        """,
        "Access Denied"
    ), 403


@app.errorhandler(413)
def too_large(error):

    return render_page(
        """
        <div class="card">
            <h2>File Too Large</h2>
            <p>Maximum upload size is 20 MB.</p>
        </div>
        """,
        "File Too Large"
    ), 413


# ============================================================
# START SERVER
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
