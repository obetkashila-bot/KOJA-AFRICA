# ============================================================
# KOJA ZM
# Knowledge • Questions • Answers
#
# SINGLE-FILE WEBSITE PORTAL
#
# FEATURES
#   • Student portal
#   • Admin portal
#   • Questions
#   • Answers
#   • Assignments
#   • Resources
#   • Notifications
#   • Payments status
#   • Supabase REST API
#   • Supabase Storage
#   • Graceful fallback when Supabase is unavailable
#
# NO SQLITE
# NO psycopg
# NO psycopg2
#
# RUN:
#   python app.py
#
# DEFAULT FALLBACK ADMIN:
#   username: admin
#   password: kojaadmin
#
# IMPORTANT:
# Change the fallback password before real deployment.
# ============================================================

import os
import uuid
import secrets
import hashlib
import hmac
from datetime import datetime
from functools import wraps

import requests

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    render_template_string,
    flash,
)


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "KOJA_SECRET_KEY",
    secrets.token_hex(32)
)

APP_NAME = "KOJA ZM"
APP_TAGLINE = "Assignment Questions • Academic Answers"

PORT = int(os.environ.get("PORT", "5000"))

# ============================================================
# SUPABASE CONFIGURATION
# ============================================================

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    ""
).strip().rstrip("/")

SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY",
    ""
).strip()

SUPABASE_PUBLISHABLE_KEY = os.environ.get(
    "SUPABASE_PUBLISHABLE_KEY",
    ""
).strip()

STORAGE_BUCKET = os.environ.get(
    "KOJA_STORAGE_BUCKET",
    "koja-assignments"
).strip()


# ============================================================
# FALLBACK ADMIN
# ============================================================

FALLBACK_ADMIN_USERNAME = os.environ.get(
    "KOJA_ADMIN_USERNAME",
    "admin"
)

FALLBACK_ADMIN_PASSWORD = os.environ.get(
    "KOJA_ADMIN_PASSWORD",
    "kojaadmin"
)


# ============================================================
# RUNTIME MODE
# ============================================================

SUPABASE_CONFIGURED = bool(
    SUPABASE_URL and SUPABASE_SERVICE_KEY
)

SUPABASE_ONLINE = False


# ============================================================
# FALLBACK DATA
#
# This is memory-based fallback data.
# It allows the portal to operate when Supabase is unavailable.
# Data disappears when the Python process restarts.
# ============================================================

FALLBACK_USERS = []

FALLBACK_QUESTIONS = [
    {
        "id": "demo-question-1",
        "title": "What is photosynthesis?",
        "subject": "Biology",
        "question": (
            "Explain the process of photosynthesis "
            "and state its importance."
        ),
        "answer": (
            "Photosynthesis is the process by which green plants "
            "use light energy to convert carbon dioxide and water "
            "into glucose and oxygen. Chlorophyll absorbs light "
            "energy needed for the process."
        ),
        "status": "Published",
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "id": "demo-question-2",
        "title": "What is a chemical reaction?",
        "subject": "Chemistry",
        "question": (
            "Define a chemical reaction and give one example."
        ),
        "answer": (
            "A chemical reaction is a process in which one or more "
            "substances are transformed into new substances with "
            "different chemical properties."
        ),
        "status": "Published",
        "created_at": datetime.utcnow().isoformat(),
    },
]

FALLBACK_ASSIGNMENTS = []

FALLBACK_RESOURCES = []

FALLBACK_NOTIFICATIONS = [
    {
        "id": "notification-1",
        "title": "Welcome to KOJA ZM",
        "message": (
            "KOJA ZM is ready. You can access assignments, "
            "questions and academic resources."
        ),
        "created_at": datetime.utcnow().isoformat(),
    }
]

FALLBACK_PAYMENTS = []


# ============================================================
# HELPERS
# ============================================================

def now():
    return datetime.utcnow().isoformat()


def hash_password(password):
    return hashlib.sha256(
        password.encode("utf-8")
    ).hexdigest()


def check_password(password, password_hash):
    return hmac.compare_digest(
        hash_password(password),
        password_hash
    )


def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def supabase_request(
    method,
    table,
    data=None,
    params=None,
    timeout=8
):
    """
    Attempts Supabase REST API.

    Failure NEVER crashes the portal.
    """

    global SUPABASE_ONLINE

    if not SUPABASE_CONFIGURED:
        SUPABASE_ONLINE = False
        return None

    try:
        response = requests.request(
            method=method,
            url=f"{SUPABASE_URL}/rest/v1/{table}",
            headers=supabase_headers(),
            json=data,
            params=params,
            timeout=timeout,
        )

        if response.status_code >= 200 and response.status_code < 300:
            SUPABASE_ONLINE = True

            if response.text:
                try:
                    return response.json()
                except Exception:
                    return response.text

            return True

        SUPABASE_ONLINE = False
        return None

    except Exception:
        SUPABASE_ONLINE = False
        return None


def current_mode():
    if SUPABASE_CONFIGURED and SUPABASE_ONLINE:
        return "SUPABASE"

    if SUPABASE_CONFIGURED:
        return "FALLBACK / SUPABASE OFFLINE"

    return "FALLBACK / SUPABASE NOT CONFIGURED"


# ============================================================
# DATABASE-STYLE FUNCTIONS
# ============================================================

def get_questions():
    result = supabase_request(
        "GET",
        "questions",
        params={
            "select": "*",
            "order": "created_at.desc"
        }
    )

    if isinstance(result, list):
        return result

    return FALLBACK_QUESTIONS


def get_users():
    result = supabase_request(
        "GET",
        "users",
        params={
            "select": "id,email,name,role,created_at",
            "order": "created_at.desc"
        }
    )

    if isinstance(result, list):
        return result

    return FALLBACK_USERS


def get_assignments():
    result = supabase_request(
        "GET",
        "assignments",
        params={
            "select": "*",
            "order": "created_at.desc"
        }
    )

    if isinstance(result, list):
        return result

    return FALLBACK_ASSIGNMENTS


def get_resources():
    result = supabase_request(
        "GET",
        "resources",
        params={
            "select": "*",
            "order": "created_at.desc"
        }
    )

    if isinstance(result, list):
        return result

    return FALLBACK_RESOURCES


def get_notifications():
    result = supabase_request(
        "GET",
        "notifications",
        params={
            "select": "*",
            "order": "created_at.desc"
        }
    )

    if isinstance(result, list):
        return result

    return FALLBACK_NOTIFICATIONS


def insert_record(table, record, fallback_list):
    result = supabase_request(
        "POST",
        table,
        data=record
    )

    if result is not None:
        return True

    fallback_list.insert(0, record)

    return True


# ============================================================
# AUTH DECORATORS
# ============================================================

def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))

        return function(*args, **kwargs)

    return wrapper


def student_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("student_logged_in"):
            return redirect(url_for("student_login"))

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# BASE HTML
# ============================================================

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>{{ title }} - KOJA ZM</title>

<style>

* {
    box-sizing: border-box;
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

.navbar {
    background: #111827;
    color: white;
    padding: 15px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;
    flex-wrap: wrap;
}

.logo {
    font-size: 23px;
    font-weight: 800;
}

.logo span:nth-child(1) {
    color: #2563eb;
}

.logo span:nth-child(2) {
    color: #16a34a;
}

.logo span:nth-child(3) {
    color: #dc2626;
}

.logo span:nth-child(4) {
    color: #1d4ed8;
}

.nav-links {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.nav-links a {
    color: white;
    text-decoration: none;
    padding: 8px 12px;
    border-radius: 7px;
}

.nav-links a:hover {
    background: #263244;
}

.container {
    width: min(1200px, 94%);
    margin: 25px auto;
}

.hero {
    background: white;
    padding: 35px;
    border-radius: 18px;
    margin-bottom: 25px;
    box-shadow:
        0 5px 20px rgba(0,0,0,.06);
}

.hero h1 {
    margin-top: 0;
    font-size: 35px;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(220px, 1fr));
    gap: 18px;
}

.card {
    background: white;
    padding: 22px;
    border-radius: 15px;
    box-shadow:
        0 5px 18px rgba(0,0,0,.06);
}

.card h3 {
    margin-top: 0;
}

.stat {
    font-size: 32px;
    font-weight: 800;
}

.btn {
    display: inline-block;
    border: none;
    background: #2563eb;
    color: white;
    text-decoration: none;
    padding: 11px 16px;
    border-radius: 8px;
    cursor: pointer;
    margin: 3px;
}

.btn:hover {
    opacity: .9;
}

.btn-danger {
    background: #dc2626;
}

.btn-green {
    background: #16a34a;
}

.btn-dark {
    background: #111827;
}

.form-card {
    max-width: 600px;
    margin: 30px auto;
    background: white;
    padding: 30px;
    border-radius: 16px;
    box-shadow:
        0 5px 20px rgba(0,0,0,.08);
}

input,
textarea,
select {
    width: 100%;
    padding: 12px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    margin: 7px 0 15px;
    font-size: 15px;
}

textarea {
    min-height: 130px;
    resize: vertical;
}

label {
    font-weight: 600;
}

table {
    width: 100%;
    border-collapse: collapse;
    background: white;
}

th,
td {
    padding: 12px;
    border-bottom: 1px solid #e5e7eb;
    text-align: left;
}

th {
    background: #111827;
    color: white;
}

.table-wrap {
    overflow-x: auto;
}

.alert {
    padding: 14px;
    background: #fff7ed;
    border-left: 5px solid #f97316;
    border-radius: 8px;
    margin-bottom: 15px;
}

.success {
    background: #ecfdf5;
    border-left-color: #16a34a;
}

.warning {
    background: #fffbeb;
    border-left-color: #eab308;
}

.badge {
    display: inline-block;
    padding: 5px 9px;
    border-radius: 20px;
    background: #e5e7eb;
    font-size: 12px;
    font-weight: 700;
}

.footer {
    text-align: center;
    padding: 35px;
    color: #6b7280;
}

.mobile-menu {
    display: none;
}

@media(max-width:700px) {

    .hero {
        padding: 22px;
    }

    .hero h1 {
        font-size: 27px;
    }

    table {
        font-size: 13px;
    }
}

</style>
</head>

<body>

<nav class="navbar">

<div class="logo">
<span>k</span><span>o</span><span>j</span><span>a</span>
<span style="color:white;"> ZM</span>
</div>

<div class="nav-links">

<a href="{{ url_for('home') }}">Home</a>

<a href="{{ url_for('questions') }}">
Questions
</a>

<a href="{{ url_for('resources') }}">
Resources
</a>

<a href="{{ url_for('assignments') }}">
Assignments
</a>

<a href="{{ url_for('admin_login') }}">
Admin
</a>

</div>

</nav>

<div class="container">

{% with messages = get_flashed_messages() %}
{% for message in messages %}
<div class="alert success">
{{ message }}
</div>
{% endfor %}
{% endwith %}

{{ content|safe }}

</div>

<div class="footer">
KOJA ZM © 2026<br>
Knowledge • Questions • Answers
</div>

</body>
</html>
"""


def page(title, content):
    return render_template_string(
        BASE_HTML,
        title=title,
        content=content
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    questions = get_questions()
    resources = get_resources()
    assignments = get_assignments()

    content = f"""
    <section class="hero">

        <h1>KOJA ZM</h1>

        <p>
        Knowledge • Questions • Answers
        </p>

        <p>
        Assignment Questions • Academic Answers
        • Learning Resources
        </p>

        <a class="btn"
           href="{url_for('questions')}">
           Browse Questions
        </a>

        <a class="btn btn-green"
           href="{url_for('student_login')}">
           Student Login
        </a>

    </section>

    <div class="grid">

        <div class="card">
            <h3>Questions</h3>
            <div class="stat">
                {len(questions)}
            </div>
            <p>Academic questions and answers.</p>
        </div>

        <div class="card">
            <h3>Resources</h3>
            <div class="stat">
                {len(resources)}
            </div>
            <p>Learning materials and documents.</p>
        </div>

        <div class="card">
            <h3>Assignments</h3>
            <div class="stat">
                {len(assignments)}
            </div>
            <p>Academic assignments.</p>
        </div>

        <div class="card">
            <h3>System</h3>
            <div class="stat" style="font-size:18px;">
                {current_mode()}
            </div>
            <p>
                KOJA continues operating even when
                Supabase is unavailable.
            </p>
        </div>

    </div>
    """

    return page("Home", content)


# ============================================================
# QUESTIONS
# ============================================================

@app.route("/questions")
def questions():

    records = get_questions()

    cards = ""

    for q in records:

        cards += f"""
        <div class="card">

            <span class="badge">
            {q.get("subject", "General")}
            </span>

            <h3>
            {q.get("title", "Question")}
            </h3>

            <p>
            {q.get("question", "")}
            </p>

            <details>
                <summary>
                View Answer
                </summary>

                <p>
                {q.get("answer", "Answer unavailable.")}
                </p>
            </details>

        </div>
        """

    content = f"""
    <div class="hero">
        <h1>Academic Questions</h1>

        <p>
        Find questions and academic answers.
        </p>
    </div>

    <div class="grid">
        {cards or '<div class="card">No questions available.</div>'}
    </div>
    """

    return page("Questions", content)


# ============================================================
# RESOURCES
# ============================================================

@app.route("/resources")
def resources():

    records = get_resources()

    rows = ""

    for r in records:

        rows += f"""
        <tr>
            <td>{r.get("title", "")}</td>
            <td>{r.get("subject", "")}</td>
            <td>{r.get("type", "Resource")}</td>
            <td>
                <a class="btn"
                   href="{r.get('url', '#')}">
                   Open
                </a>
            </td>
        </tr>
        """

    content = f"""
    <div class="hero">
        <h1>Learning Resources</h1>
        <p>Academic resources available through KOJA.</p>
    </div>

    <div class="card table-wrap">

    <table>

        <tr>
            <th>Title</th>
            <th>Subject</th>
            <th>Type</th>
            <th>Action</th>
        </tr>

        {rows or '''
        <tr>
            <td colspan="4">
            No resources available.
            </td>
        </tr>
        '''}

    </table>

    </div>
    """

    return page("Resources", content)


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments")
def assignments():

    records = get_assignments()

    cards = ""

    for a in records:

        cards += f"""
        <div class="card">

            <h3>
            {a.get("title", "Assignment")}
            </h3>

            <p>
            <strong>Subject:</strong>
            {a.get("subject", "")}
            </p>

            <p>
            {a.get("description", "")}
            </p>

        </div>
        """

    content = f"""
    <div class="hero">

        <h1>Assignments</h1>

        <p>
        Access academic assignments.
        </p>

    </div>

    <div class="grid">

        {cards or
        '<div class="card">No assignments available.</div>'}

    </div>
    """

    return page("Assignments", content)


# ============================================================
# STUDENT LOGIN
# ============================================================

@app.route("/login")
def student_login():

    content = f"""
    <div class="form-card">

        <h2>Student Login</h2>

        <form method="POST"
              action="{url_for('student_login_post')}">

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

            <button class="btn">
                Login
            </button>

        </form>

        <p>
        Don't have an account?
        <a href="{url_for('student_register')}">
        Register
        </a>
        </p>

    </div>
    """

    return page("Student Login", content)


@app.route("/login", methods=["POST"])
def student_login_post():

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    password = request.form.get(
        "password",
        ""
    )

    result = supabase_request(
        "GET",
        "users",
        params={
            "select": "*",
            "email": f"eq.{email}"
        }
    )

    if isinstance(result, list) and result:

        user = result[0]

        if check_password(
            password,
            user.get("password_hash", "")
        ):

            session["student_logged_in"] = True
            session["student_email"] = email

            return redirect(url_for("student_dashboard"))

    for user in FALLBACK_USERS:

        if user.get("email") == email:

            if check_password(
                password,
                user.get("password_hash", "")
            ):

                session["student_logged_in"] = True
                session["student_email"] = email

                return redirect(
                    url_for("student_dashboard")
                )

    flash("Invalid student login.")

    return redirect(url_for("student_login"))


# ============================================================
# STUDENT REGISTRATION
# ============================================================

@app.route("/register")
def student_register():

    content = f"""
    <div class="form-card">

        <h2>Create Student Account</h2>

        <form method="POST"
              action="{url_for('student_register_post')}">

            <label>Name</label>

            <input
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

            <button class="btn btn-green">
                Create Account
            </button>

        </form>

    </div>
    """

    return page("Register", content)


@app.route("/register", methods=["POST"])
def student_register_post():

    name = request.form.get("name", "").strip()
    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    password = request.form.get(
        "password",
        ""
    )

    if not name or not email or not password:

        flash("All fields are required.")

        return redirect(
            url_for("student_register")
        )

    record = {
        "id": str(uuid.uuid4()),
        "name": name,
        "email": email,
        "password_hash": hash_password(password),
        "role": "student",
        "created_at": now(),
    }

    inserted = insert_record(
        "users",
        record,
        FALLBACK_USERS
    )

    if inserted:

        flash(
            "Account created. You can now log in."
        )

    return redirect(
        url_for("student_login")
    )


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route("/student")
@student_required
def student_dashboard():

    email = session.get(
        "student_email",
        ""
    )

    notifications = get_notifications()

    notification_html = ""

    for n in notifications[:10]:

        notification_html += f"""
        <div class="card">
            <h3>{n.get("title", "")}</h3>
            <p>{n.get("message", "")}</p>
        </div>
        """

    content = f"""
    <section class="hero">

        <h1>Student Dashboard</h1>

        <p>
        Welcome, {email}
        </p>

        <a class="btn"
           href="{url_for('questions')}">
           Questions
        </a>

        <a class="btn btn-green"
           href="{url_for('resources')}">
           Resources
        </a>

        <a class="btn btn-dark"
           href="{url_for('student_logout')}">
           Logout
        </a>

    </section>

    <h2>Notifications</h2>

    <div class="grid">

        {notification_html or
        '<div class="card">No notifications.</div>'}

    </div>
    """

    return page(
        "Student Dashboard",
        content
    )


@app.route("/student/logout")
def student_logout():

    session.pop("student_logged_in", None)
    session.pop("student_email", None)

    return redirect(url_for("home"))


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route("/admin")
def admin_login():

    if session.get("admin_logged_in"):

        return redirect(
            url_for("admin_dashboard")
        )

    content = f"""
    <div class="form-card">

        <h2>KOJA ZM Administration</h2>

        <p>
        Secure administrator access.
        </p>

        <div class="alert warning">

        Current system mode:
        <strong>
        {current_mode()}
        </strong>

        </div>

        <form method="POST"
              action="{url_for('admin_login_post')}">

            <label>Admin Username</label>

            <input
                name="username"
                autocomplete="username"
                required
            >

            <label>Admin Password</label>

            <input
                type="password"
                name="password"
                autocomplete="current-password"
                required
            >

            <button class="btn btn-dark">
                Admin Login
            </button>

        </form>

    </div>
    """

    return page(
        "Admin Login",
        content
    )


@app.route("/admin/login", methods=["POST"])
def admin_login_post():

    username = request.form.get(
        "username",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    # --------------------------------------------------------
    # EMERGENCY FALLBACK ADMIN
    # --------------------------------------------------------

    if (
        hmac.compare_digest(
            username,
            FALLBACK_ADMIN_USERNAME
        )
        and
        hmac.compare_digest(
            password,
            FALLBACK_ADMIN_PASSWORD
        )
    ):

        session["admin_logged_in"] = True
        session["admin_username"] = username

        flash(
            "Admin access granted."
        )

        return redirect(
            url_for("admin_dashboard")
        )

    # --------------------------------------------------------
    # SUPABASE ADMIN
    # --------------------------------------------------------

    result = supabase_request(
        "GET",
        "admins",
        params={
            "select": "*",
            "username": f"eq.{username}"
        }
    )

    if isinstance(result, list) and result:

        admin = result[0]

        stored_hash = admin.get(
            "password_hash",
            ""
        )

        if check_password(
            password,
            stored_hash
        ):

            session["admin_logged_in"] = True
            session["admin_username"] = username

            return redirect(
                url_for("admin_dashboard")
            )

    flash("Invalid administrator credentials.")

    return redirect(
        url_for("admin_login")
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():

    users = get_users()
    questions_data = get_questions()
    assignments_data = get_assignments()
    resources_data = get_resources()
    notifications = get_notifications()

    status_class = (
        "success"
        if SUPABASE_ONLINE
        else "warning"
    )

    content = f"""
    <section class="hero">

        <h1>KOJA ZM Admin Dashboard</h1>

        <p>
        Administrator:
        <strong>
        {session.get("admin_username", "admin")}
        </strong>
        </p>

        <div class="alert {status_class}">

            <strong>System mode:</strong>
            {current_mode()}

            <br><br>

            The portal remains accessible even when
            Supabase is not configured.

        </div>

        <a class="btn btn-danger"
           href="{url_for('admin_logout')}">
           Logout
        </a>

    </section>

    <div class="grid">

        <div class="card">
            <h3>Users</h3>
            <div class="stat">{len(users)}</div>
            <a href="{url_for('admin_users')}"
               class="btn">
               Manage
            </a>
        </div>

        <div class="card">
            <h3>Questions</h3>
            <div class="stat">
                {len(questions_data)}
            </div>
            <a href="{url_for('admin_questions')}"
               class="btn">
               Manage
            </a>
        </div>

        <div class="card">
            <h3>Assignments</h3>
            <div class="stat">
                {len(assignments_data)}
            </div>
            <a href="{url_for('admin_assignments')}"
               class="btn">
               Manage
            </a>
        </div>

        <div class="card">
            <h3>Resources</h3>
            <div class="stat">
                {len(resources_data)}
            </div>
            <a href="{url_for('admin_resources')}"
               class="btn">
               Manage
            </a>
        </div>

        <div class="card">
            <h3>Notifications</h3>
            <div class="stat">
                {len(notifications)}
            </div>
            <a href="{url_for('admin_notifications')}"
               class="btn">
               Manage
            </a>
        </div>

        <div class="card">
            <h3>System</h3>

            <p>
            Supabase configured:
            <strong>
            {"YES" if SUPABASE_CONFIGURED else "NO"}
            </strong>
            </p>

            <p>
            Supabase online:
            <strong>
            {"YES" if SUPABASE_ONLINE else "NO"}
            </strong>
            </p>

            <a href="{url_for('admin_system')}"
               class="btn btn-dark">
               System Status
            </a>

        </div>

    </div>
    """

    return page(
        "Admin Dashboard",
        content
    )


# ============================================================
# ADMIN USERS
# ============================================================

@app.route("/admin/users")
@admin_required
def admin_users():

    users = get_users()

    rows = ""

    for u in users:

        rows += f"""
        <tr>

            <td>
            {u.get("name", "")}
            </td>

            <td>
            {u.get("email", "")}
            </td>

            <td>
            {u.get("role", "student")}
            </td>

            <td>
            {u.get("created_at", "")}
            </td>

        </tr>
        """

    content = f"""
    <div class="hero">

        <h1>Users</h1>

        <a class="btn"
           href="{url_for('admin_dashboard')}">
           Dashboard
        </a>

    </div>

    <div class="card table-wrap">

        <table>

        <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Created</th>
        </tr>

        {rows or '''
        <tr>
            <td colspan="4">
            No users found.
            </td>
        </tr>
        '''}

        </table>

    </div>
    """

    return page(
        "Admin Users",
        content
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route("/admin/questions")
@admin_required
def admin_questions():

    records = get_questions()

    rows = ""

    for q in records:

        rows += f"""
        <tr>

            <td>
            {q.get("title", "")}
            </td>

            <td>
            {q.get("subject", "")}
            </td>

            <td>
            {q.get("status", "Published")}
            </td>

        </tr>
        """

    content = f"""
    <div class="hero">

        <h1>Manage Questions</h1>

        <a class="btn btn-green"
           href="{url_for('admin_add_question')}">
           Add Question
        </a>

        <a class="btn"
           href="{url_for('admin_dashboard')}">
           Dashboard
        </a>

    </div>

    <div class="card table-wrap">

        <table>

        <tr>
            <th>Title</th>
            <th>Subject</th>
            <th>Status</th>
        </tr>

        {rows}

        </table>

    </div>
    """

    return page(
        "Admin Questions",
        content
    )


@app.route("/admin/questions/add")
@admin_required
def admin_add_question():

    content = f"""
    <div class="form-card">

        <h2>Add Academic Question</h2>

        <form method="POST"
              action="{url_for('admin_add_question_post')}">

            <label>Title</label>

            <input
                name="title"
                required
            >

            <label>Subject</label>

            <input
                name="subject"
                required
            >

            <label>Question</label>

            <textarea
                name="question"
                required
            ></textarea>

            <label>Answer</label>

            <textarea
                name="answer"
                required
            ></textarea>

            <button class="btn btn-green">
                Save Question
            </button>

        </form>

    </div>
    """

    return page(
        "Add Question",
        content
    )


@app.route(
    "/admin/questions/add",
    methods=["POST"]
)
@admin_required
def admin_add_question_post():

    record = {
        "id": str(uuid.uuid4()),
        "title": request.form.get(
            "title",
            ""
        ).strip(),

        "subject": request.form.get(
            "subject",
            ""
        ).strip(),

        "question": request.form.get(
            "question",
            ""
        ).strip(),

        "answer": request.form.get(
            "answer",
            ""
        ).strip(),

        "status": "Published",
        "created_at": now(),
    }

    insert_record(
        "questions",
        record,
        FALLBACK_QUESTIONS
    )

    flash("Question saved successfully.")

    return redirect(
        url_for("admin_questions")
    )


# ============================================================
# ADMIN ASSIGNMENTS
# ============================================================

@app.route("/admin/assignments")
@admin_required
def admin_assignments():

    records = get_assignments()

    rows = ""

    for a in records:

        rows += f"""
        <tr>

            <td>{a.get("title", "")}</td>

            <td>{a.get("subject", "")}</td>

            <td>{a.get("created_at", "")}</td>

        </tr>
        """

    content = f"""
    <div class="hero">

        <h1>Manage Assignments</h1>

        <a class="btn btn-green"
           href="{url_for('admin_add_assignment')}">
           Add Assignment
        </a>

        <a class="btn"
           href="{url_for('admin_dashboard')}">
           Dashboard
        </a>

    </div>

    <div class="card table-wrap">

        <table>

            <tr>
                <th>Title</th>
                <th>Subject</th>
                <th>Created</th>
            </tr>

            {rows}

        </table>

    </div>
    """

    return page(
        "Admin Assignments",
        content
    )


@app.route("/admin/assignments/add")
@admin_required
def admin_add_assignment():

    content = f"""
    <div class="form-card">

        <h2>Add Assignment</h2>

        <form method="POST"
              action="{url_for('admin_add_assignment_post')}">

            <label>Title</label>

            <input
                name="title"
                required
            >

            <label>Subject</label>

            <input
                name="subject"
                required
            >

            <label>Description</label>

            <textarea
                name="description"
                required
            ></textarea>

            <button class="btn btn-green">
                Save Assignment
            </button>

        </form>

    </div>
    """

    return page(
        "Add Assignment",
        content
    )


@app.route(
    "/admin/assignments/add",
    methods=["POST"]
)
@admin_required
def admin_add_assignment_post():

    record = {
        "id": str(uuid.uuid4()),

        "title": request.form.get(
            "title",
            ""
        ).strip(),

        "subject": request.form.get(
            "subject",
            ""
        ).strip(),

        "description": request.form.get(
            "description",
            ""
        ).strip(),

        "created_at": now(),
    }

    insert_record(
        "assignments",
        record,
        FALLBACK_ASSIGNMENTS
    )

    flash("Assignment saved.")

    return redirect(
        url_for("admin_assignments")
    )


# ============================================================
# ADMIN RESOURCES
# ============================================================

@app.route("/admin/resources")
@admin_required
def admin_resources():

    records = get_resources()

    rows = ""

    for r in records:

        rows += f"""
        <tr>

            <td>{r.get("title", "")}</td>

            <td>{r.get("subject", "")}</td>

            <td>{r.get("type", "")}</td>

            <td>
            <a href="{r.get('url', '#')}"
               class="btn">
               Open
            </a>
            </td>

        </tr>
        """

    content = f"""
    <div class="hero">

        <h1>Manage Resources</h1>

        <a class="btn btn-green"
           href="{url_for('admin_add_resource')}">
           Add Resource
        </a>

        <a class="btn"
           href="{url_for('admin_dashboard')}">
           Dashboard
        </a>

    </div>

    <div class="card table-wrap">

        <table>

            <tr>
                <th>Title</th>
                <th>Subject</th>
                <th>Type</th>
                <th>Action</th>
            </tr>

            {rows}

        </table>

    </div>
    """

    return page(
        "Admin Resources",
        content
    )


@app.route("/admin/resources/add")
@admin_required
def admin_add_resource():

    content = f"""
    <div class="form-card">

        <h2>Add Resource</h2>

        <form method="POST"
              action="{url_for('admin_add_resource_post')}">

            <label>Title</label>

            <input
                name="title"
                required
            >

            <label>Subject</label>

            <input
                name="subject"
                required
            >

            <label>Type</label>

            <select name="type">

                <option>PDF</option>
                <option>Video</option>
                <option>Document</option>
                <option>Link</option>

            </select>

            <label>Resource URL</label>

            <input
                name="url"
                placeholder="https://..."
                required
            >

            <button class="btn btn-green">
                Save Resource
            </button>

        </form>

    </div>
    """

    return page(
        "Add Resource",
        content
    )


@app.route(
    "/admin/resources/add",
    methods=["POST"]
)
@admin_required
def admin_add_resource_post():

    record = {
        "id": str(uuid.uuid4()),

        "title": request.form.get(
            "title",
            ""
        ).strip(),

        "subject": request.form.get(
            "subject",
            ""
        ).strip(),

        "type": request.form.get(
            "type",
            "Resource"
        ).strip(),

        "url": request.form.get(
            "url",
            "#"
        ).strip(),

        "created_at": now(),
    }

    insert_record(
        "resources",
        record,
        FALLBACK_RESOURCES
    )

    flash("Resource saved.")

    return redirect(
        url_for("admin_resources")
    )


# ============================================================
# ADMIN NOTIFICATIONS
# ============================================================

@app.route("/admin/notifications")
@admin_required
def admin_notifications():

    records = get_notifications()

    cards = ""

    for n in records:

        cards += f"""
        <div class="card">

            <h3>
            {n.get("title", "")}
            </h3>

            <p>
            {n.get("message", "")}
            </p>

            <small>
            {n.get("created_at", "")}
            </small>

        </div>
        """

    content = f"""
    <div class="hero">

        <h1>Notifications</h1>

        <a class="btn btn-green"
           href="{url_for('admin_add_notification')}">
           New Notification
        </a>

        <a class="btn"
           href="{url_for('admin_dashboard')}">
           Dashboard
        </a>

    </div>

    <div class="grid">

        {cards}

    </div>
    """

    return page(
        "Admin Notifications",
        content
    )


@app.route("/admin/notifications/add")
@admin_required
def admin_add_notification():

    content = f"""
    <div class="form-card">

        <h2>Create Notification</h2>

        <form method="POST"
              action="{url_for('admin_add_notification_post')}">

            <label>Title</label>

            <input
                name="title"
                required
            >

            <label>Message</label>

            <textarea
                name="message"
                required
            ></textarea>

            <button class="btn btn-green">
                Publish
            </button>

        </form>

    </div>
    """

    return page(
        "New Notification",
        content
    )


@app.route(
    "/admin/notifications/add",
    methods=["POST"]
)
@admin_required
def admin_add_notification_post():

    record = {
        "id": str(uuid.uuid4()),

        "title": request.form.get(
            "title",
            ""
        ).strip(),

        "message": request.form.get(
            "message",
            ""
        ).strip(),

        "created_at": now(),
    }

    insert_record(
        "notifications",
        record,
        FALLBACK_NOTIFICATIONS
    )

    flash("Notification published.")

    return redirect(
        url_for("admin_notifications")
    )


# ============================================================
# ADMIN SYSTEM
# ============================================================

@app.route("/admin/system")
@admin_required
def admin_system():

    content = f"""
    <div class="hero">

        <h1>System Status</h1>

        <a class="btn"
           href="{url_for('admin_dashboard')}">
           Dashboard
        </a>

    </div>

    <div class="grid">

        <div class="card">

            <h3>Application</h3>

            <p>
            <strong>ONLINE</strong>
            </p>

        </div>

        <div class="card">

            <h3>Supabase Configuration</h3>

            <p>
            {
                "Configured"
                if SUPABASE_CONFIGURED
                else "Not Configured"
            }
            </p>

        </div>

        <div class="card">

            <h3>Supabase Connection</h3>

            <p>
            {
                "ONLINE"
                if SUPABASE_ONLINE
                else "OFFLINE / NOT TESTED"
            }
            </p>

        </div>

        <div class="card">

            <h3>Current Mode</h3>

            <p>
            {current_mode()}
            </p>

        </div>

        <div class="card">

            <h3>Storage Bucket</h3>

            <p>
            {STORAGE_BUCKET}
            </p>

        </div>

        <div class="card">

            <h3>Architecture</h3>

            <p>
            Flask + Supabase REST API
            </p>

            <p>
            Graceful degradation enabled.
            </p>

        </div>

    </div>
    """

    return page(
        "System Status",
        content
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop("admin_logged_in", None)
    session.pop("admin_username", None)

    return redirect(
        url_for("admin_login")
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "application": APP_NAME,
        "mode": current_mode(),
        "supabase_configured": SUPABASE_CONFIGURED,
        "supabase_online": SUPABASE_ONLINE,
        "time": now(),
    })


# ============================================================
# API STATUS
# ============================================================

@app.route("/api/status")
def api_status():

    return jsonify({
        "application": APP_NAME,
        "status": "online",
        "mode": current_mode(),
        "supabase": {
            "configured": SUPABASE_CONFIGURED,
            "online": SUPABASE_ONLINE,
        },
        "fallback": True,
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    content = """
    <div class="hero">

        <h1>404</h1>

        <p>
        The page you requested does not exist.
        </p>

        <a class="btn" href="/">
        Return Home
        </a>

    </div>
    """

    return page(
        "Page Not Found",
        content
    ), 404


@app.errorhandler(500)
def internal_error(error):

    content = """
    <div class="hero">

        <h1>KOJA is still running</h1>

        <p>
        A server operation failed, but the portal
        itself remains available.
        </p>

        <a class="btn" href="/">
        Return Home
        </a>

    </div>
    """

    return page(
        "Temporary Error",
        content
    ), 500


# ============================================================
# STARTUP
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("KOJA ZM")
    print("Knowledge • Questions • Answers")
    print("=" * 60)

    if SUPABASE_CONFIGURED:

        print("Supabase configuration: FOUND")

        # Test connection without preventing startup.
        try:

            test = supabase_request(
                "GET",
                "questions",
                params={
                    "select": "id",
                    "limit": "1"
                }
            )

            if test is not None:
                SUPABASE_ONLINE = True
                print("Supabase: ONLINE")

            else:
                print(
                    "Supabase: OFFLINE"
                )

        except Exception:
            SUPABASE_ONLINE = False
            print(
                "Supabase: OFFLINE"
            )

    else:

        print(
            "Supabase configuration: NOT FOUND"
        )

        print(
            "Starting in FALLBACK mode."
        )

    print()
    print(
        "Admin username:",
        FALLBACK_ADMIN_USERNAME
    )

    print(
        "Admin password:",
        FALLBACK_ADMIN_PASSWORD
    )

    print()
    print(
        "Portal will start even without Supabase."
    )

    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
