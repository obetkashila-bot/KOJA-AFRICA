import os
import uuid
import logging
from io import BytesIO
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
    flash,
    jsonify,
    send_file,
    render_template_string,
)

load_dotenv()

# ============================================================
# KOJA AFRICA
# Production Flask Application
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_IN_RENDER"
)

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
).rstrip("/")

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
)

SUPABASE_BUCKET = os.getenv(
    "SUPABASE_BUCKET",
    "koja-files"
)

ADMIN_EMAIL = os.getenv(
    "ADMIN_EMAIL",
    ""
).strip().lower()

MAX_FILE_SIZE = 15 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "jpg",
    "jpeg",
    "png",
    "webp"
}

logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger("koja")


# ============================================================
# CONFIGURATION
# ============================================================

def configured():
    return bool(
        SUPABASE_URL
        and SUPABASE_SERVICE_KEY
    )


def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def current_user():
    return session.get("user")


def user_id():
    u = current_user()

    if not u:
        return None

    return u.get("id")


def is_logged_in():
    return bool(current_user())


def is_admin():
    u = current_user()

    if not u:
        return False

    email = (
        u.get("email", "")
        .strip()
        .lower()
    )

    return (
        ADMIN_EMAIL
        and email == ADMIN_EMAIL
    )


# ============================================================
# AUTH DECORATORS
# ============================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):

        if not is_logged_in():
            flash(
                "Please log in to continue."
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

        if not is_logged_in():
            return redirect(
                url_for("login")
            )

        if not is_admin():
            flash(
                "Administrator access required."
            )
            return redirect(
                url_for("dashboard")
            )

        return view(
            *args,
            **kwargs
        )

    return wrapped


# ============================================================
# SUPABASE HEADERS
# ============================================================

def rest_headers(prefer=None):

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type":
            "application/json"
    }

    if prefer:
        headers["Prefer"] = prefer

    return headers


# ============================================================
# SUPABASE REST HELPERS
# ============================================================

def supabase_get(
    table,
    params=None
):
    try:

        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=rest_headers(),
            params=params or {},
            timeout=30
        )

        if not response.ok:
            logger.error(
                "Supabase GET %s: %s",
                table,
                response.text
            )
            return None, response.text

        return response.json(), None

    except Exception as exc:

        logger.exception(
            "Supabase GET failed"
        )

        return None, str(exc)


def supabase_insert(
    table,
    payload
):
    try:

        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=rest_headers(
                "return=representation"
            ),
            json=payload,
            timeout=30
        )

        if not response.ok:
            logger.error(
                "Supabase INSERT %s: %s",
                table,
                response.text
            )
            return None, response.text

        try:
            return response.json(), None
        except Exception:
            return [], None

    except Exception as exc:

        logger.exception(
            "Supabase INSERT failed"
        )

        return None, str(exc)


def supabase_update(
    table,
    filters,
    payload
):
    params = {}

    for key, value in filters.items():
        params[key] = f"eq.{value}"

    try:

        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=rest_headers(
                "return=representation"
            ),
            params=params,
            json=payload,
            timeout=30
        )

        if not response.ok:
            logger.error(
                "Supabase UPDATE %s: %s",
                table,
                response.text
            )
            return None, response.text

        try:
            return response.json(), None
        except Exception:
            return [], None

    except Exception as exc:

        logger.exception(
            "Supabase UPDATE failed"
        )

        return None, str(exc)


# ============================================================
# SUPABASE AUTH
# ============================================================

def signup(
    email,
    password
):
    try:

        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers={
                "apikey":
                    SUPABASE_SERVICE_KEY,
                "Content-Type":
                    "application/json"
            },
            json={
                "email": email,
                "password": password
            },
            timeout=30
        )

        if not response.ok:
            logger.error(
                "Signup error: %s",
                response.text
            )
            return None, response.text

        return response.json(), None

    except Exception as exc:

        return None, str(exc)


def login_user(
    email,
    password
):
    try:

        response = requests.post(
            f"{SUPABASE_URL}/auth/v1/token"
            "?grant_type=password",
            headers={
                "apikey":
                    SUPABASE_SERVICE_KEY,
                "Content-Type":
                    "application/json"
            },
            json={
                "email": email,
                "password": password
            },
            timeout=30
        )

        if not response.ok:
            logger.error(
                "Login error: %s",
                response.text
            )
            return None, response.text

        return response.json(), None

    except Exception as exc:

        return None, str(exc)


# ============================================================
# FILE STORAGE
# ============================================================

def extension_allowed(filename):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in ALLOWED_EXTENSIONS


def upload_file(
    file,
    folder
):

    if not file:
        return None, "No file supplied."

    filename = file.filename or ""

    if not extension_allowed(
        filename
    ):
        return (
            None,
            "This file type is not supported."
        )

    filename = filename.replace(
        "\\",
        "_"
    ).replace(
        "/",
        "_"
    )

    file.seek(0)

    content = file.read()

    if len(content) > MAX_FILE_SIZE:
        return (
            None,
            "File size cannot exceed 15 MB."
        )

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    object_path = (
        f"{folder}/"
        f"{uuid.uuid4().hex}."
        f"{extension}"
    )

    content_type = (
        file.mimetype
        or "application/octet-stream"
    )

    headers = {
        "apikey":
            SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type":
            content_type,
        "x-upsert":
            "false"
    }

    try:

        response = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{SUPABASE_BUCKET}/"
            f"{object_path}",
            headers=headers,
            data=content,
            timeout=60
        )

        if not response.ok:

            logger.error(
                "Storage upload: %s",
                response.text
            )

            return (
                None,
                response.text
            )

        return {
            "path":
                object_path,
            "filename":
                filename,
            "content_type":
                content_type,
            "size":
                len(content)
        }, None

    except Exception as exc:

        logger.exception(
            "Storage upload failed"
        )

        return None, str(exc)


def download_file(
    object_path
):

    headers = {
        "apikey":
            SUPABASE_SERVICE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_SERVICE_KEY}"
    }

    try:

        response = requests.get(
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{SUPABASE_BUCKET}/"
            f"{object_path}",
            headers=headers,
            timeout=60
        )

        if not response.ok:
            return (
                None,
                response.text
            )

        return response.content, None

    except Exception as exc:

        return None, str(exc)


# ============================================================
# PAGE TEMPLATE
# ============================================================

BASE_HTML = """
<!doctype html>
<html lang="en">

<head>

<meta charset="utf-8">

<meta name="viewport"
      content="width=device-width,
               initial-scale=1">

<title>
{{ title }} | KOJA AFRICA
</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #f5f7fb;
    color: #172033;
    font-family:
        Arial,
        Helvetica,
        sans-serif;
}

.topbar {
    background: #10233f;
    color: white;
    padding: 16px 20px;
}

.topbar-inner {
    max-width: 1180px;
    margin: auto;
}

.brand {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: .4px;
}

.nav {
    margin-top: 12px;
}

.nav a {
    display: inline-block;
    color: white;
    text-decoration: none;
    margin-right: 18px;
    margin-bottom: 6px;
    font-size: 14px;
}

.container {
    max-width: 1180px;
    margin: auto;
    padding: 25px 18px;
}

.hero {
    background: white;
    border-radius: 14px;
    padding: 30px;
    margin-bottom: 22px;
    border: 1px solid #e4e8ef;
}

.hero-primary {
    background:
        linear-gradient(
            135deg,
            #123b68,
            #1d5d8f
        );
    color: white;
    border: none;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(260px, 1fr)
        );
    gap: 18px;
}

.card {
    background: white;
    border: 1px solid #e3e7ee;
    border-radius: 14px;
    padding: 21px;
    margin-bottom: 18px;
}

.card h2,
.card h3 {
    margin-top: 0;
}

.btn {
    display: inline-block;
    padding: 11px 17px;
    border-radius: 8px;
    border: none;
    text-decoration: none;
    cursor: pointer;
    background: #1769aa;
    color: white;
    font-size: 14px;
}

.btn-secondary {
    background: #374151;
}

.btn-success {
    background: #087f5b;
}

.btn-warning {
    background: #a15c00;
}

.btn-danger {
    background: #b42318;
}

input,
textarea,
select {
    width: 100%;
    padding: 12px;
    border: 1px solid #cfd6df;
    border-radius: 8px;
    margin-top: 6px;
    margin-bottom: 15px;
    font-size: 15px;
    background: white;
}

textarea {
    min-height: 140px;
    resize: vertical;
}

label {
    font-weight: 600;
    font-size: 14px;
}

.status {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 20px;
    background: #edf1f5;
    font-size: 13px;
}

.status-online {
    background: #e7f6ef;
    color: #087f5b;
}

.status-pending {
    background: #fff5df;
    color: #8a5300;
}

.status-approved {
    background: #e7f6ef;
    color: #087f5b;
}

.status-rejected {
    background: #fdeceb;
    color: #b42318;
}

.location {
    font-weight: 600;
    color: #1558a0;
}

.muted {
    color: #687386;
    font-size: 14px;
}

.alert {
    background: #fff5df;
    border: 1px solid #f2d59b;
    padding: 12px;
    border-radius: 8px;
    margin-bottom: 15px;
}

.table-wrap {
    overflow-x: auto;
}

table {
    width: 100%;
    border-collapse: collapse;
    background: white;
}

th,
td {
    text-align: left;
    padding: 12px;
    border-bottom: 1px solid #e5e7eb;
}

th {
    background: #f7f8fa;
}

footer {
    text-align: center;
    padding: 35px 20px;
    color: #6b7280;
    font-size: 13px;
}

@media(max-width:600px) {

    .hero {
        padding: 22px;
    }

    .container {
        padding: 18px 12px;
    }

    .nav a {
        margin-right: 12px;
    }

}

</style>

</head>

<body>

<header class="topbar">

<div class="topbar-inner">

<div class="brand">
KOJA AFRICA
</div>

<div class="nav">

<a href="{{ url_for('home') }}">
Home
</a>

{% if logged %}

<a href="{{ url_for('dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('assignments') }}">
Assignments
</a>

<a href="{{ url_for('drivers') }}">
Drivers & Delivery
</a>

<a href="{{ url_for('professionals') }}">
Professional Services
</a>

{% if admin %}

<a href="{{ url_for('admin_dashboard') }}">
Administration
</a>

{% endif %}

<a href="{{ url_for('logout') }}">
Logout
</a>

{% else %}

<a href="{{ url_for('login') }}">
Login
</a>

<a href="{{ url_for('register') }}">
Create Account
</a>

{% endif %}

</div>

</div>

</header>

<main class="container">

{% with messages =
get_flashed_messages() %}

{% for message in messages %}

<div class="alert">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content | safe }}

</main>

<footer>
KOJA AFRICA
<br>
Academic Services |
Drivers & Delivery |
Professional Services
</footer>

</body>

</html>
"""


def page(
    content,
    title="KOJA AFRICA"
):

    return render_template_string(
        BASE_HTML,
        content=content,
        title=title,
        logged=is_logged_in(),
        admin=is_admin()
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    content = """
<section class="hero hero-primary">

<h1>KOJA AFRICA</h1>

<p>
A professional platform connecting people
with academic assistance, transport and
delivery services, and professional services.
</p>

{% if not logged %}

<a class="btn"
   href="/register">
Create Account
</a>

<a class="btn btn-secondary"
   href="/login">
Login
</a>

{% endif %}

</section>

<div class="grid">

<div class="card">

<h2>Assignments</h2>

<p>
Submit academic questions, documents,
PDF files, Word documents or images.
Track the status and receive the completed
answer securely.
</p>

<a class="btn"
   href="/assignments">
Open Assignments
</a>

</div>

<div class="card">

<h2>Drivers & Delivery</h2>

<p>
Find approved drivers who are currently
online, view their exact location names,
and request transport or delivery services.
</p>

<a class="btn btn-success"
   href="/drivers">
Find Drivers
</a>

</div>

<div class="card">

<h2>Professional Services</h2>

<p>
Find approved professionals such as doctors,
lawyers, teachers and other service providers.
</p>

<a class="btn btn-warning"
   href="/professionals">
Find Professionals
</a>

</div>

</div>
"""

    return page(
        content,
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
                "Email and password are required."
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

        result, error = signup(
            email,
            password
        )

        if error:

            flash(
                "Registration failed: "
                + str(error)
            )

            return redirect(
                url_for("register")
            )

        flash(
            "Account created. Please log in."
        )

        return redirect(
            url_for("login")
        )

    content = """
<div class="hero">

<h1>Create Account</h1>

<p class="muted">
Create one KOJA AFRICA account to use
the available services.
</p>

<form method="POST">

<label>Email</label>

<input type="email"
       name="email"
       required>

<label>Password</label>

<input type="password"
       name="password"
       minlength="6"
       required>

<button class="btn">
Create Account
</button>

</form>

</div>
"""

    return page(
        content,
        "Create Account"
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

        result, error = login_user(
            email,
            password
        )

        if error:

            flash(
                "Invalid email or password."
            )

            return redirect(
                url_for("login")
            )

        auth_user = (
            result.get("user")
            or {}
        )

        session.clear()

        session["user"] = {
            "id":
                auth_user.get("id"),
            "email":
                auth_user.get("email")
                or email
        }

        if is_admin():

            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("dashboard")
        )

    content = """
<div class="hero">

<h1>Login</h1>

<form method="POST">

<label>Email</label>

<input type="email"
       name="email"
       required>

<label>Password</label>

<input type="password"
       name="password"
       required>

<button class="btn">
Login
</button>

</form>

</div>
"""

    return page(
        content,
        "Login"
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
# CLIENT DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    email = current_user().get(
        "email",
        ""
    )

    content = f"""
<section class="hero">

<h1>Client Dashboard</h1>

<p>
Signed in as:
<strong>{email}</strong>
</p>

</section>

<div class="grid">

<div class="card">

<h2>Assignments</h2>

<p>
Submit and manage your academic questions.
</p>

<a class="btn"
   href="/assignments">
Open
</a>

<a class="btn btn-secondary"
   href="/assignments/new">
New Assignment
</a>

</div>

<div class="card">

<h2>Drivers & Delivery</h2>

<p>
Find an available driver and request
transport or delivery.
</p>

<a class="btn btn-success"
   href="/drivers">
Find Drivers
</a>

</div>

<div class="card">

<h2>Professional Services</h2>

<p>
Find and book approved professionals.
</p>

<a class="btn btn-warning"
   href="/professionals">
Browse Professionals
</a>

</div>

</div>
"""

    return page(
        content,
        "Dashboard"
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments")
@login_required
def assignments():

    rows, error = supabase_get(
        "assignments",
        {
            "student_id":
                f"eq.{user_id()}",
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    if error:

        flash(
            "Unable to load assignments."
        )

        rows = []

    cards = ""

    for item in rows or []:

        status = (
            item.get("status")
            or "pending"
        )

        cards += f"""
<div class="card">

<h3>
{item.get("title") or "Untitled Assignment"}
</h3>

<p>
<strong>Subject:</strong>
{item.get("subject") or ""}
</p>

<p>
<strong>Status:</strong>
<span class="status">
{status}
</span>
</p>

<p class="muted">
Submitted:
{item.get("created_at") or ""}
</p>

<a class="btn"
   href="/assignments/{item.get('id')}">
View
</a>

</div>
"""

    content = f"""
<section class="hero">

<h1>Assignments</h1>

<p>
Submit academic questions and receive
completed answers from the administration.
</p>

<a class="btn"
   href="/assignments/new">
New Assignment
</a>

</section>

<div class="grid">

{cards or
'<div class="card">No assignments have been submitted.</div>'}

</div>
"""

    return page(
        content,
        "Assignments"
    )


@app.route(
    "/assignments/new",
    methods=["GET", "POST"]
)
@login_required
def new_assignment():

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        question_file = request.files.get(
            "question_file"
        )

        if not title:
            flash("Assignment title is required.")
            return redirect(request.url)

        if not subject:
            flash("Subject is required.")
            return redirect(request.url)

        if not description:
            flash("Question is required.")
            return redirect(request.url)

        file_note = ""

        if (
            question_file
            and question_file.filename
        ):

            info, error = upload_file(
                question_file,
                "assignment-questions"
            )

            if error:

                flash(
                    "Question file upload failed: "
                    + str(error)
                )

                return redirect(
                    request.url
                )

            file_note = (
                "QUESTION_FILE|"
                + info["path"]
                + "|"
                + info["filename"]
                + "|"
                + info["content_type"]
            )

        payload = {
            "id":
                str(uuid.uuid4()),

            "student_id":
                user_id(),

            "title":
                title,

            "subject":
                subject,

            "description":
                description,

            "status":
                "pending",

            "admin_note":
                file_note,

            "answer_text":
                None
        }

        result, error = supabase_insert(
            "assignments",
            payload
        )

        if error:

            flash(
                "Could not save assignment: "
                + str(error)
            )

            return redirect(
                request.url
            )

        flash(
            "Assignment submitted successfully."
        )

        return redirect(
            url_for("assignments")
        )

    content = """
<section class="hero">

<h1>New Assignment</h1>

<p class="muted">
Send your question to the administration.
</p>

<form method="POST"
      enctype="multipart/form-data">

<label>Assignment Title</label>

<input name="title"
       required>

<label>Subject</label>

<input name="subject"
       required>

<label>Question</label>

<textarea name="description"
          required></textarea>

<label>
Question File
</label>

<input type="file"
       name="question_file"
       accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp">

<button class="btn">
Submit Assignment
</button>

</form>

</section>
"""

    return page(
        content,
        "New Assignment"
    )


@app.route(
    "/assignments/<assignment_id>"
)
@login_required
def assignment_detail(
    assignment_id
):

    rows, error = supabase_get(
        "assignments",
        {
            "id":
                f"eq.{assignment_id}",
            "student_id":
                f"eq.{user_id()}",
            "select":
                "*"
        }
    )

    if error or not rows:

        flash(
            "Assignment not found."
        )

        return redirect(
            url_for("assignments")
        )

    item = rows[0]

    content = f"""
<section class="hero">

<h1>
{item.get("title") or ""}
</h1>

<p>
<strong>Subject:</strong>
{item.get("subject") or ""}
</p>

<p>
<strong>Status:</strong>
<span class="status">
{item.get("status") or "pending"}
</span>
</p>

</section>

<div class="card">

<h2>Question</h2>

<p>
{item.get("description") or ""}
</p>

</div>

<div class="card">

<h2>Answer</h2>

<p>
{item.get("answer_text")
 or "The answer is not yet available."}
</p>

</div>

<a class="btn"
   href="/assignments">
Back to Assignments
</a>
"""

    return page(
        content,
        "Assignment"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    assignment_rows, _ = supabase_get(
        "assignments",
        {
            "select":
                "id,status"
        }
    )

    driver_rows, _ = supabase_get(
        "driver_profiles",
        {
            "select":
                "id,status,is_online"
        }
    )

    delivery_rows, _ = supabase_get(
        "delivery_requests",
        {
            "select":
                "id,status"
        }
    )

    provider_rows, _ = supabase_get(
        "service_providers",
        {
            "select":
                "id,status,is_available"
        }
    )

    assignments_count = len(
        assignment_rows or []
    )

    pending_assignments = sum(
        1
        for x in (
            assignment_rows or []
        )
        if (
            x.get("status")
            == "pending"
        )
    )

    drivers_count = len(
        driver_rows or []
    )

    pending_drivers = sum(
        1
        for x in (
            driver_rows or []
        )
        if (
            x.get("status")
            == "pending"
        )
    )

    deliveries_count = len(
        delivery_rows or []
    )

    professionals_count = len(
        provider_rows or []
    )

    pending_professionals = sum(
        1
        for x in (
            provider_rows or []
        )
        if (
            x.get("status")
            == "pending"
        )
    )

    content = f"""
<section class="hero">

<h1>Administration</h1>

<p>
KOJA AFRICA management portal.
</p>

</section>

<div class="grid">

<div class="card">

<h2>Assignments</h2>

<p>
Total:
<strong>{assignments_count}</strong>
</p>

<p>
Pending:
<strong>{pending_assignments}</strong>
</p>

<a class="btn"
   href="/admin/assignments">
Manage Assignments
</a>

</div>

<div class="card">

<h2>Drivers</h2>

<p>
Total:
<strong>{drivers_count}</strong>
</p>

<p>
Pending:
<strong>{pending_drivers}</strong>
</p>

<a class="btn btn-success"
   href="/admin/drivers">
Manage Drivers
</a>

</div>

<div class="card">

<h2>Deliveries</h2>

<p>
Requests:
<strong>{deliveries_count}</strong>
</p>

<a class="btn btn-success"
   href="/admin/deliveries">
Manage Deliveries
</a>

</div>

<div class="card">

<h2>Professionals</h2>

<p>
Total:
<strong>{professionals_count}</strong>
</p>

<p>
Pending:
<strong>{pending_professionals}</strong>
</p>

<a class="btn btn-warning"
   href="/admin/professionals">
Manage Professionals
</a>

</div>

</div>
"""

    return page(
        content,
        "Administration"
    )


# ============================================================
# ADMIN ASSIGNMENTS
# ============================================================

@app.route("/admin/assignments")
@admin_required
def admin_assignments():

    rows, error = supabase_get(
        "assignments",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    cards = ""

    for item in rows or []:

        cards += f"""
<div class="card">

<h3>
{item.get("title") or ""}
</h3>

<p>
Student:
{item.get("student_id")}
</p>

<p>
Subject:
{item.get("subject") or ""}
</p>

<p>
Status:
<span class="status">
{item.get("status") or ""}
</span>
</p>

<a class="btn"
   href="/admin/assignments/{item.get('id')}">
Process
</a>

</div>
"""

    content = f"""
<section class="hero">

<h1>Assignment Management</h1>

<p>
Review submitted questions, prepare answers,
and approve completed work.
</p>

</section>

<div class="grid">

{cards or
'<div class="card">No assignments found.</div>'}

</div>
"""

    return page(
        content,
        "Assignment Management"
    )


@app.route(
    "/admin/assignments/<assignment_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_assignment(
    assignment_id
):

    rows, error = supabase_get(
        "assignments",
        {
            "id":
                f"eq.{assignment_id}",
            "select":
                "*"
        }
    )

    if error or not rows:

        flash(
            "Assignment not found."
        )

        return redirect(
            url_for("admin_assignments")
        )

    item = rows[0]

    if request.method == "POST":

        status = request.form.get(
            "status",
            "in_progress"
        )

        answer_text = request.form.get(
            "answer_text",
            ""
        ).strip()

        admin_note = request.form.get(
            "admin_note",
            ""
        ).strip()

        answer_file = request.files.get(
            "answer_file"
        )

        if (
            answer_file
            and answer_file.filename
        ):

            info, upload_error = upload_file(
                answer_file,
                "assignment-answers"
            )

            if upload_error:

                flash(
                    "Answer upload failed: "
                    + str(upload_error)
                )

                return redirect(
                    request.url
                )

            if admin_note:
                admin_note += "\n"

            admin_note += (
                "ANSWER_FILE|"
                + info["path"]
                + "|"
                + info["filename"]
                + "|"
                + info["content_type"]
            )

        update_data = {
            "status":
                status,

            "admin_note":
                admin_note,

            "answer_text":
                answer_text,

            "updated_at":
                utc_now()
        }

        if status in (
            "completed",
            "approved"
        ):
            update_data[
                "completed_at"
            ] = utc_now()

        result, update_error = (
            supabase_update(
                "assignments",
                {
                    "id":
                        assignment_id
                },
                update_data
            )
        )

        if update_error:

            flash(
                "Assignment update failed: "
                + str(update_error)
            )

        else:

            flash(
                "Assignment updated successfully."
            )

        return redirect(
            request.url
        )

    content = f"""
<section class="hero">

<h1>
{item.get("title") or ""}
</h1>

<p>
<strong>Subject:</strong>
{item.get("subject") or ""}
</p>

<p>
<strong>Student:</strong>
{item.get("student_id")}
</p>

<p>
<strong>Status:</strong>
{item.get("status") or ""}
</p>

</section>

<div class="card">

<h2>Question</h2>

<p>
{item.get("description") or ""}
</p>

</div>

<div class="card">

<h2>Process Assignment</h2>

<form method="POST"
      enctype="multipart/form-data">

<label>Status</label>

<select name="status">

<option value="pending">
Pending
</option>

<option value="in_progress">
In Progress
</option>

<option value="completed">
Completed
</option>

<option value="approved">
Approved
</option>

</select>

<label>Admin Note</label>

<textarea name="admin_note">{item.get("admin_note") or ""}</textarea>

<label>Answer</label>

<textarea name="answer_text">{item.get("answer_text") or ""}</textarea>

<label>Answer File</label>

<input type="file"
       name="answer_file"
       accept=".pdf,.doc,.docx">

<button class="btn">
Save
</button>

</form>

</div>
"""

    return page(
        content,
        "Process Assignment"
    )


# ============================================================
# DRIVER REGISTRATION
# ============================================================

@app.route(
    "/drivers/register",
    methods=["GET", "POST"]
)
@login_required
def driver_register():

    if request.method == "POST":

        vehicle_type = request.form.get(
            "vehicle_type",
            ""
        ).strip()

        vehicle_number = request.form.get(
            "vehicle_number",
            ""
        ).strip()

        license_number = request.form.get(
            "license_number",
            ""
        ).strip()

        location_name = request.form.get(
            "location_name",
            ""
        ).strip()

        if not vehicle_type:
            flash("Vehicle type is required.")
            return redirect(request.url)

        if not vehicle_number:
            flash("Vehicle number is required.")
            return redirect(request.url)

        if not license_number:
            flash("License number is required.")
            return redirect(request.url)

        if not location_name:
            flash("Exact location name is required.")
            return redirect(request.url)

        payload = {
            "id":
                str(uuid.uuid4()),

            "provider_id":
                user_id(),

            "vehicle_type":
                vehicle_type,

            "vehicle_number":
                vehicle_number,

            "license_number":
                license_number,

            "status":
                "pending",

            "is_online":
                False,

            "latitude":
                None,

            "longitude":
                None,

            "location_name":
                location_name,

            "last_location_update":
                None
        }

        result, error = supabase_insert(
            "driver_profiles",
            payload
        )

        if error:

            flash(
                "Driver registration failed: "
                + str(error)
            )

            return redirect(
                request.url
            )

        flash(
            "Driver registration submitted for approval."
        )

        return redirect(
            url_for("drivers")
        )

    content = """
<section class="hero">

<h1>Driver Registration</h1>

<p>
Register your vehicle for transport and
delivery services. Your profile must be
approved before clients can request you.
</p>

<form method="POST">

<label>Vehicle Type</label>

<input name="vehicle_type"
       placeholder="Car, motorcycle, van"
       required>

<label>Vehicle Number</label>

<input name="vehicle_number"
       required>

<label>License Number</label>

<input name="license_number"
       required>

<label>Exact Location Name</label>

<input name="location_name"
       placeholder="Example: Kitwe City Centre"
       required>

<button class="btn btn-success">
Submit Registration
</button>

</form>

</section>
"""

    return page(
        content,
        "Driver Registration"
    )


# ============================================================
# DRIVER LIST
# ============================================================

@app.route("/drivers")
@login_required
def drivers():

    rows, error = supabase_get(
        "driver_profiles",
        {
            "status":
                "eq.approved",

            "is_online":
                "eq.true",

            "select":
                "*",

            "order":
                "last_location_update.desc"
        }
    )

    if error:

        flash(
            "Unable to load available drivers."
        )

        rows = []

    cards = ""

    for driver in rows or []:

        cards += f"""
<div class="card">

<h2>
{driver.get("vehicle_type") or "Driver"}
</h2>

<p>
<strong>Vehicle:</strong>
{driver.get("vehicle_number") or ""}
</p>

<p class="location">
Current location:
{driver.get("location_name")
 or "Location unavailable"}
</p>

<p>
<span class="status status-online">
ONLINE
</span>
</p>

<form method="POST"
      action="/delivery/request">

<input type="hidden"
       name="driver_id"
       value="{driver.get("id")}">

<label>Service</label>

<select name="service_type">

<option value="delivery">
Delivery
</option>

<option value="ride">
Ride
</option>

</select>

<label>Pickup Location</label>

<input name="pickup_location"
       required
       placeholder="Exact pickup location">

<label>Destination</label>

<input name="destination_location"
       required
       placeholder="Exact destination">

<label>Notes</label>

<textarea name="notes"
          placeholder="Additional instructions"></textarea>

<button class="btn btn-success">
Request Driver
</button>

</form>

</div>
"""

    content = f"""
<section class="hero">

<h1>Drivers & Delivery</h1>

<p>
Available approved drivers are displayed
with their latest location name.
</p>

<a class="btn btn-success"
   href="/drivers/register">
Register as Driver
</a>

</section>

<div class="grid">

{cards or
'<div class="card">There are currently no online drivers.</div>'}

</div>
"""

    return page(
        content,
        "Drivers & Delivery"
    )


# ============================================================
# DRIVER GPS UPDATE
# ============================================================

@app.route(
    "/driver/location",
    methods=["POST"]
)
@login_required
def update_driver_location():

    rows, error = supabase_get(
        "driver_profiles",
        {
            "provider_id":
                f"eq.{user_id()}",
            "select":
                "id"
        }
    )

    if error or not rows:

        return jsonify({
            "success": False,
            "message":
                "Driver profile not found."
        }), 404

    driver_id = rows[0]["id"]

    try:

        latitude = float(
            request.form.get(
                "latitude"
            )
        )

        longitude = float(
            request.form.get(
                "longitude"
            )
        )

    except Exception:

        return jsonify({
            "success": False,
            "message":
                "Invalid GPS coordinates."
        }), 400

    location_name = request.form.get(
        "location_name",
        ""
    ).strip()

    if not location_name:

        return jsonify({
            "success": False,
            "message":
                "Exact location name is required."
        }), 400

    result, error = supabase_update(
        "driver_profiles",
        {
            "id":
                driver_id
        },
        {
            "latitude":
                latitude,

            "longitude":
                longitude,

            "location_name":
                location_name,

            "is_online":
                True,

            "last_location_update":
                utc_now(),

            "updated_at":
                utc_now()
        }
    )

    if error:

        return jsonify({
            "success": False,
            "message":
                error
        }), 500

    return jsonify({
        "success": True,
        "location_name":
            location_name
    })


# ============================================================
# DRIVER ONLINE / OFFLINE
# ============================================================

@app.route(
    "/driver/status",
    methods=["POST"]
)
@login_required
def driver_status():

    rows, error = supabase_get(
        "driver_profiles",
        {
            "provider_id":
                f"eq.{user_id()}",
            "select":
                "id,status"
        }
    )

    if error or not rows:

        flash(
            "Driver profile not found."
        )

        return redirect(
            url_for("drivers")
        )

    driver = rows[0]

    if driver.get("status") != "approved":

        flash(
            "Your driver profile has not been approved."
        )

        return redirect(
            url_for("drivers")
        )

    online = (
        request.form.get(
            "is_online",
            "false"
        ).lower()
        == "true"
    )

    result, update_error = supabase_update(
        "driver_profiles",
        {
            "id":
                driver["id"]
        },
        {
            "is_online":
                online,

            "updated_at":
                utc_now()
        }
    )

    if update_error:

        flash(
            "Could not update driver status."
        )

    else:

        flash(
            "Driver status updated."
        )

    return redirect(
        url_for("drivers")
    )


# ============================================================
# DELIVERY REQUEST
# ============================================================

@app.route(
    "/delivery/request",
    methods=["POST"]
)
@login_required
def create_delivery_request():

    driver_id = request.form.get(
        "driver_id"
    ) or None

    service_type = request.form.get(
        "service_type",
        "delivery"
    ).strip()

    pickup_location = request.form.get(
        "pickup_location",
        ""
    ).strip()

    destination_location = request.form.get(
        "destination_location",
        ""
    ).strip()

    notes = request.form.get(
        "notes",
        ""
    ).strip()

    if not pickup_location:

        flash(
            "Pickup location is required."
        )

        return redirect(
            url_for("drivers")
        )

    if not destination_location:

        flash(
            "Destination is required."
        )

        return redirect(
            url_for("drivers")
        )

    payload = {
        "id":
            str(uuid.uuid4()),

        "customer_id":
            user_id(),

        "driver_id":
            driver_id,

        "pickup_location":
            pickup_location,

        "delivery_location":
            destination_location,

        "latitude":
            None,

        "longitude":
            None,

        "status":
            "pending",

        "notes":
            notes,

        "service_type":
            service_type,

        "destination_location":
            destination_location,

        "pickup_latitude":
            None,

        "pickup_longitude":
            None,

        "destination_latitude":
            None,

        "destination_longitude":
            None,

        "requested_at":
            utc_now()
    }

    result, error = supabase_insert(
        "delivery_requests",
        payload
    )

    if error:

        flash(
            "Request failed: "
            + str(error)
        )

        return redirect(
            url_for("drivers")
        )

    flash(
        "Request sent successfully."
    )

    return redirect(
        url_for("my_deliveries")
    )


# ============================================================
# CLIENT DELIVERY REQUESTS
# ============================================================

@app.route("/deliveries")
@login_required
def my_deliveries():

    rows, error = supabase_get(
        "delivery_requests",
        {
            "customer_id":
                f"eq.{user_id()}",
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    cards = ""

    for item in rows or []:

        cards += f"""
<div class="card">

<h2>
{(
    item.get("service_type")
    or "delivery"
).title()}
</h2>

<p>
<strong>Pickup:</strong>
{item.get("pickup_location") or ""}
</p>

<p>
<strong>Destination:</strong>
{item.get("destination_location") or ""}
</p>

<p>
<strong>Status:</strong>
<span class="status">
{item.get("status") or "pending"}
</span>
</p>

<p class="muted">
Requested:
{item.get("requested_at")
 or item.get("created_at")
 or ""}
</p>

</div>
"""

    content = f"""
<section class="hero">

<h1>My Delivery & Ride Requests</h1>

</section>

<div class="grid">

{cards or
'<div class="card">No requests have been made.</div>'}

</div>
"""

    return page(
        content,
        "My Requests"
    )


# ============================================================
# PROFESSIONAL REGISTRATION
# ============================================================

@app.route(
    "/professionals/register",
    methods=["GET", "POST"]
)
@login_required
def professional_register():

    if request.method == "POST":

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        profession = request.form.get(
            "profession",
            ""
        ).strip()

        specialty = request.form.get(
            "specialty",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        available_days = request.form.get(
            "available_days",
            ""
        ).strip()

        start_time = request.form.get(
            "start_time"
        ) or None

        end_time = request.form.get(
            "end_time"
        ) or None

        if not full_name:

            flash(
                "Full name is required."
            )

            return redirect(request.url)

        if not phone:

            flash(
                "Phone number is required."
            )

            return redirect(request.url)

        if not profession:

            flash(
                "Profession is required."
            )

            return redirect(request.url)

        payload = {
            "id":
                str(uuid.uuid4()),

            "user_id":
                user_id(),

            "full_name":
                full_name,

            "phone":
                phone,

            "email":
                current_user().get(
                    "email"
                ),

            "profession":
                profession,

            "specialty":
                specialty,

            "description":
                description,

            "available_days":
                available_days,

            "start_time":
                start_time,

            "end_time":
                end_time,

            "status":
                "pending",

            "is_available":
                False
        }

        result, error = supabase_insert(
            "service_providers",
            payload
        )

        if error:

            flash(
                "Professional registration failed: "
                + str(error)
            )

            return redirect(
                request.url
            )

        flash(
            "Professional registration submitted for approval."
        )

        return redirect(
            url_for("professionals")
        )

    content = """
<section class="hero">

<h1>Professional Registration</h1>

<p>
Doctors, lawyers, teachers and other
professionals can register their services.
</p>

<form method="POST">

<label>Full Name</label>

<input name="full_name"
       required>

<label>Phone Number</label>

<input name="phone"
       required>

<label>Profession</label>

<select name="profession"
        required>

<option value="">
Select profession
</option>

<option>
Doctor
</option>

<option>
Lawyer
</option>

<option>
Teacher
</option>

<option>
Other
</option>

</select>

<label>Specialty</label>

<input name="specialty">

<label>Description</label>

<textarea name="description"></textarea>

<label>Available Days</label>

<input name="available_days"
       placeholder="Monday-Friday">

<label>Start Time</label>

<input type="time"
       name="start_time">

<label>End Time</label>

<input type="time"
       name="end_time">

<button class="btn btn-warning">
Submit Registration
</button>

</form>

</section>
"""

    return page(
        content,
        "Professional Registration"
    )


# ============================================================
# PROFESSIONAL SEARCH
# ============================================================

@app.route("/professionals")
@login_required
def professionals():

    search = request.args.get(
        "q",
        ""
    ).strip()

    params = {
        "status":
            "eq.approved",

        "is_available":
            "eq.true",

        "select":
            "*",

        "order":
            "created_at.desc"
    }

    if search:

        params["or"] = (
            "("
            "full_name.ilike.*"
            + search
            + "*,"
            "profession.ilike.*"
            + search
            + "*,"
            "specialty.ilike.*"
            + search
            + "*"
            ")"
        )

    rows, error = supabase_get(
        "service_providers",
        params
    )

    if error:
        rows = []

    cards = ""

    for provider in rows or []:

        cards += f"""
<div class="card">

<h2>
{provider.get("full_name") or ""}
</h2>

<p>
<strong>Profession:</strong>
{provider.get("profession") or ""}
</p>

<p>
<strong>Specialty:</strong>
{provider.get("specialty") or ""}
</p>

<p>
{provider.get("description") or ""}
</p>

<p>
<strong>Phone:</strong>
{provider.get("phone") or ""}
</p>

<a class="btn btn-warning"
   href="/professionals/{provider.get('id')}">
View Professional
</a>

</div>
"""

    content = f"""
<section class="hero">

<h1>Professional Services</h1>

<form method="GET">

<label>
Search
</label>

<input name="q"
       value="{search}"
       placeholder="Doctor, lawyer, teacher or specialty">

<button class="btn btn-warning">
Search
</button>

</form>

<a class="btn btn-secondary"
   href="/professionals/register">
Register as Professional
</a>

</section>

<div class="grid">

{cards or
'<div class="card">No available professionals found.</div>'}

</div>
"""

    return page(
        content,
        "Professional Services"
    )


# ============================================================
# PROFESSIONAL PROFILE
# ============================================================

@app.route(
    "/professionals/<provider_id>"
)
@login_required
def professional_detail(
    provider_id
):

    rows, error = supabase_get(
        "service_providers",
        {
            "id":
                f"eq.{provider_id}",

            "status":
                "eq.approved",

            "select":
                "*"
        }
    )

    if error or not rows:

        flash(
            "Professional not found."
        )

        return redirect(
            url_for("professionals")
        )

    provider = rows[0]

    content = f"""
<section class="hero">

<h1>
{provider.get("full_name") or ""}
</h1>

<p>
<strong>Profession:</strong>
{provider.get("profession") or ""}
</p>

<p>
<strong>Specialty:</strong>
{provider.get("specialty") or ""}
</p>

<p>
{provider.get("description") or ""}
</p>

<p>
<strong>Phone:</strong>
{provider.get("phone") or ""}
</p>

<p>
<strong>Available days:</strong>
{provider.get("available_days") or ""}
</p>

<p>
<strong>Hours:</strong>
{provider.get("start_time") or ""}
-
{provider.get("end_time") or ""}
</p>

</section>

<div class="card">

<h2>Appointment</h2>

<p>
The professional is available for booking.
</p>

<a class="btn btn-warning"
   href="/professionals/book/{provider_id}">
Request Appointment
</a>

</div>
"""

    return page(
        content,
        "Professional"
    )


# ============================================================
# PROFESSIONAL BOOKING
#
# IMPORTANT:
# The exact professional_bookings schema was not supplied.
# This route deliberately does not invent database columns.
# ============================================================

@app.route(
    "/professionals/book/<provider_id>"
)
@login_required
def professional_booking_notice(
    provider_id
):

    rows, error = supabase_get(
        "service_providers",
        {
            "id":
                f"eq.{provider_id}",

            "status":
                "eq.approved",

            "select":
                "*"
        }
    )

    if error or not rows:

        flash(
            "Professional not found."
        )

        return redirect(
            url_for("professionals")
        )

    provider = rows[0]

    content = f"""
<section class="hero">

<h1>Request Appointment</h1>

<p>
Professional:
<strong>
{provider.get("full_name") or ""}
</strong>
</p>

<p>
Profession:
{provider.get("profession") or ""}
</p>

</section>

<div class="card">

<p>
The professional booking system is connected
to the existing booking database. The exact
booking-table columns must be used here before
a production booking record is inserted.
</p>

<p class="muted">
This page intentionally does not guess or alter
your existing database structure.
</p>

<a class="btn"
   href="/professionals">
Back to Professionals
</a>

</div>
"""

    return page(
        content,
        "Appointment"
    )


# ============================================================
# ADMIN DRIVERS
# ============================================================

@app.route("/admin/drivers")
@admin_required
def admin_drivers():

    rows, error = supabase_get(
        "driver_profiles",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    cards = ""

    for driver in rows or []:

        cards += f"""
<div class="card">

<h2>
{driver.get("vehicle_type") or ""}
</h2>

<p>
<strong>Vehicle:</strong>
{driver.get("vehicle_number") or ""}
</p>

<p>
<strong>License:</strong>
{driver.get("license_number") or ""}
</p>

<p>
<strong>Location:</strong>
{driver.get("location_name") or ""}
</p>

<p>
<strong>Status:</strong>
{driver.get("status") or ""}
</p>

<p>
<strong>Online:</strong>
{driver.get("is_online")}
</p>

<form method="POST"
      action="/admin/drivers/{driver.get('id')}">

<label>Status</label>

<select name="status">

<option value="pending">
Pending
</option>

<option value="approved">
Approved
</option>

<option value="rejected">
Rejected
</option>

</select>

<button class="btn">
Save
</button>

</form>

</div>
"""

    content = f"""
<section class="hero">

<h1>Driver Management</h1>

<p>
Review and approve driver registrations.
</p>

</section>

<div class="grid">

{cards or
'<div class="card">No driver registrations.</div>'}

</div>
"""

    return page(
        content,
        "Driver Management"
    )


@app.route(
    "/admin/drivers/<driver_id>",
    methods=["POST"]
)
@admin_required
def admin_driver_update(
    driver_id
):

    status = request.form.get(
        "status",
        "pending"
    )

    if status not in (
        "pending",
        "approved",
        "rejected"
    ):

        flash(
            "Invalid driver status."
        )

        return redirect(
            url_for("admin_drivers")
        )

    result, error = supabase_update(
        "driver_profiles",
        {
            "id":
                driver_id
        },
        {
            "status":
                status,

            "updated_at":
                utc_now()
        }
    )

    flash(
        "Driver updated successfully."
        if not error
        else "Driver update failed."
    )

    return redirect(
        url_for("admin_drivers")
    )


# ============================================================
# ADMIN DELIVERIES
# ============================================================

@app.route("/admin/deliveries")
@admin_required
def admin_deliveries():

    rows, error = supabase_get(
        "delivery_requests",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    cards = ""

    for item in rows or []:

        cards += f"""
<div class="card">

<h2>
{(
    item.get("service_type")
    or "Delivery"
).title()}
</h2>

<p>
<strong>Customer:</strong>
{item.get("customer_id")}
</p>

<p>
<strong>Driver:</strong>
{item.get("driver_id")
 or "Not assigned"}
</p>

<p>
<strong>Pickup:</strong>
{item.get("pickup_location") or ""}
</p>

<p>
<strong>Destination:</strong>
{item.get("destination_location") or ""}
</p>

<p>
<strong>Status:</strong>
{item.get("status") or ""}
</p>

<form method="POST"
      action="/admin/deliveries/{item.get('id')}">

<select name="status">

<option value="pending">
Pending
</option>

<option value="accepted">
Accepted
</option>

<option value="started">
Started
</option>

<option value="completed">
Completed
</option>

<option value="cancelled">
Cancelled
</option>

</select>

<button class="btn btn-success">
Update
</button>

</form>

</div>
"""

    content = f"""
<section class="hero">

<h1>Delivery Management</h1>

<p>
Manage ride and delivery requests.
</p>

</section>

<div class="grid">

{cards or
'<div class="card">No delivery requests.</div>'}

</div>
"""

    return page(
        content,
        "Delivery Management"
    )


@app.route(
    "/admin/deliveries/<delivery_id>",
    methods=["POST"]
)
@admin_required
def admin_delivery_update(
    delivery_id
):

    status = request.form.get(
        "status",
        "pending"
    )

    data = {
        "status":
            status,

        "updated_at":
            utc_now()
    }

    if status == "accepted":
        data["accepted_at"] = utc_now()

    elif status == "started":
        data["started_at"] = utc_now()

    elif status == "completed":
        data["completed_at"] = utc_now()

    result, error = supabase_update(
        "delivery_requests",
        {
            "id":
                delivery_id
        },
        data
    )

    flash(
        "Delivery updated successfully."
        if not error
        else "Delivery update failed."
    )

    return redirect(
        url_for("admin_deliveries")
    )


# ============================================================
# ADMIN PROFESSIONALS
# ============================================================

@app.route("/admin/professionals")
@admin_required
def admin_professionals():

    rows, error = supabase_get(
        "service_providers",
        {
            "select":
                "*",
            "order":
                "created_at.desc"
        }
    )

    cards = ""

    for provider in rows or []:

        cards += f"""
<div class="card">

<h2>
{provider.get("full_name") or ""}
</h2>

<p>
<strong>Profession:</strong>
{provider.get("profession") or ""}
</p>

<p>
<strong>Specialty:</strong>
{provider.get("specialty") or ""}
</p>

<p>
<strong>Phone:</strong>
{provider.get("phone") or ""}
</p>

<p>
<strong>Status:</strong>
{provider.get("status") or ""}
</p>

<p>
<strong>Available:</strong>
{provider.get("is_available")}
</p>

<form method="POST"
      action="/admin/professionals/{provider.get('id')}">

<label>Status</label>

<select name="status">

<option value="pending">
Pending
</option>

<option value="approved">
Approved
</option>

<option value="rejected">
Rejected
</option>

</select>

<label>

<input type="checkbox"
       name="is_available"
       style="width:auto">

 Available to clients

</label>

<br><br>

<button class="btn btn-warning">
Save
</button>

</form>

</div>
"""

    content = f"""
<section class="hero">

<h1>Professional Management</h1>

<p>
Approve professionals and control their
availability.
</p>

</section>

<div class="grid">

{cards or
'<div class="card">No professional registrations.</div>'}

</div>
"""

    return page(
        content,
        "Professional Management"
    )


@app.route(
    "/admin/professionals/<provider_id>",
    methods=["POST"]
)
@admin_required
def admin_professional_update(
    provider_id
):

    status = request.form.get(
        "status",
        "pending"
    )

    available = (
        "is_available"
        in request.form
    )

    result, error = supabase_update(
        "service_providers",
        {
            "id":
                provider_id
        },
        {
            "status":
                status,

            "is_available":
                available,

            "updated_at":
                utc_now()
        }
    )

    flash(
        "Professional updated successfully."
        if not error
        else "Professional update failed."
    )

    return redirect(
        url_for("admin_professionals")
    )


# ============================================================
# ADMIN BOOKINGS
#
# This route is intentionally omitted until the exact
# professional_bookings schema is confirmed.
# ============================================================


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

        "database_configured":
            configured(),

        "services": [
            "assignments",
            "drivers_and_delivery",
            "professional_services"
        ]
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return page(
        """
<div class="card">

<h1>Page Not Found</h1>

<p>
The requested page does not exist.
</p>

<a class="btn"
   href="/">
Return Home
</a>

</div>
""",
        "Page Not Found"
    ), 404


@app.errorhandler(500)
def server_error(error):

    logger.exception(
        "Internal server error"
    )

    return page(
        """
<div class="card">

<h1>Server Error</h1>

<p>
An unexpected server error occurred.
Please check the Render logs for the
technical details.
</p>

<a class="btn"
   href="/">
Return Home
</a>

</div>
""",
        "Server Error"
    ), 500


# ============================================================
# APPLICATION START
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
