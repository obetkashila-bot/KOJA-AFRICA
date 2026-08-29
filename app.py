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
    get_flashed_messages,
    send_file,
    abort,
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER

from docx import Document
from openpyxl import Workbook


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "change-this-koja-secret-key"
)

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

APP_NAME = "KOJA AFRICA"
APP_TAGLINE = "Assignment Questions • Academic Answers • Learning Resources"

STORAGE_BUCKET = os.environ.get(
    "SUPABASE_STORAGE_BUCKET",
    "koja-assignments"
)

ADMIN_EMAIL = os.environ.get(
    "ADMIN_EMAIL",
    "admin@koja-africa.com"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "ChangeThisAdminPassword123!"
)


# ============================================================
# VALIDATION
# ============================================================

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "png",
    "jpg",
    "jpeg",
    "webp",
    "txt",
}

MAX_FILE_SIZE = 15 * 1024 * 1024


def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()

    return ext in ALLOWED_EXTENSIONS


def utc_now():
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# SUPABASE REST
# ============================================================

def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def supabase_request(
    method,
    table,
    params=None,
    data=None,
    headers=None,
    timeout=30,
):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL or SUPABASE_SERVICE_KEY is missing."
        )

    url = f"{SUPABASE_URL}/rest/v1/{table}"

    final_headers = supabase_headers()

    if headers:
        final_headers.update(headers)

    response = requests.request(
        method,
        url,
        params=params,
        json=data,
        headers=final_headers,
        timeout=timeout,
    )

    if not response.ok:
        logging.error(
            "Supabase %s %s failed: %s",
            method,
            table,
            response.text,
        )

        raise RuntimeError(
            f"Database request failed: "
            f"{response.status_code} {response.text}"
        )

    if not response.text:
        return []

    try:
        return response.json()
    except Exception:
        return response.text


def db_select(
    table,
    columns="*",
    filters=None,
    limit=None,
    order=None,
):
    params = {
        "select": columns,
    }

    if filters:
        params.update(filters)

    if limit:
        params["limit"] = str(limit)

    if order:
        params["order"] = order

    return supabase_request(
        "GET",
        table,
        params=params,
    )


def db_insert(table, data, returning=True):
    headers = {}

    if returning:
        headers["Prefer"] = "return=representation"

    return supabase_request(
        "POST",
        table,
        data=data,
        headers=headers,
    )


def db_update(table, filters, data):
    params = filters

    headers = {
        "Prefer": "return=representation"
    }

    return supabase_request(
        "PATCH",
        table,
        params=params,
        data=data,
        headers=headers,
    )


def db_delete(table, filters):
    return supabase_request(
        "DELETE",
        table,
        params=filters,
    )


# ============================================================
# STORAGE
# ============================================================

def storage_upload(file_bytes, storage_path, content_type):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase configuration missing.")

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{storage_path}"
    )

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    response = requests.post(
        url,
        headers=headers,
        data=file_bytes,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Storage upload failed: "
            f"{response.status_code} {response.text}"
        )

    return storage_path


def storage_download(storage_path):
    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{storage_path}"
    )

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Storage download failed: "
            f"{response.status_code} {response.text}"
        )

    return response.content


def storage_delete(storage_path):
    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}"
    )

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }

    response = requests.delete(
        url,
        headers=headers,
        json={
            "prefixes": [storage_path]
        },
        timeout=30,
    )

    return response.ok


# ============================================================
# LOGIN HELPERS
# ============================================================

def current_user():
    return session.get("user")


def current_email():
    user = current_user()

    if not user:
        return None

    return user.get("email")


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please login first.", "warning")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        user = current_user()

        if not user:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))

        if not user.get("is_admin"):
            flash("Administrator access required.", "danger")
            return redirect(url_for("dashboard"))

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# DATABASE HELPERS
# ============================================================

def find_profile(email):
    rows = db_select(
        "profiles",
        filters={
            "email": f"eq.{email}"
        },
        limit=1,
    )

    if rows:
        return rows[0]

    return None


def create_profile(email, name, password_hash, is_admin=False):

    data = {
        "email": email,
        "full_name": name,
        "password_hash": password_hash,
        "is_admin": is_admin,
        "created_at": utc_now(),
    }

    try:
        result = db_insert("profiles", data)

        if isinstance(result, list) and result:
            return result[0]

    except Exception as exc:
        logging.exception("Profile creation failed")

        # Some databases may not contain all optional fields.
        # Try a smaller insert.
        try:
            fallback = {
                "email": email,
                "full_name": name,
                "password_hash": password_hash,
            }

            result = db_insert("profiles", fallback)

            if isinstance(result, list) and result:
                return result[0]

        except Exception:
            raise exc

    return data


def verify_user(email, password):

    profile = find_profile(email)

    if not profile:
        return None

    password_hash = profile.get("password_hash")

    if not password_hash:
        return None

    try:
        valid = check_password_hash(
            password_hash,
            password,
        )
    except Exception:
        valid = False

    if not valid:
        return None

    return profile


def log_activity(action, description=""):

    user = current_user()

    email = None

    if user:
        email = user.get("email")

    data = {
        "action": action,
        "description": description,
        "email": email,
        "created_at": utc_now(),
    }

    try:
        db_insert(
            "activity_logs",
            data,
            returning=False,
        )
    except Exception:
        logging.exception("Activity log failed")


# ============================================================
# FILE RECORD
# ============================================================

def save_assignment_file(
    assignment_id,
    original_filename,
    storage_path,
    content_type,
    file_size,
    file_role="question",
):

    data = {
        "assignment_id": assignment_id,
        "original_filename": original_filename,
        "storage_path": storage_path,
        "content_type": content_type,
        "file_size": file_size,
        "file_role": file_role,
        "created_at": utc_now(),
    }

    try:
        result = db_insert(
            "assignment_files",
            data,
        )

        if isinstance(result, list) and result:
            return result[0]

    except Exception:
        logging.exception(
            "Could not save assignment file record"
        )

    return data


# ============================================================
# PDF GENERATION
# ============================================================

def build_pdf(
    title,
    student_name,
    question,
    answer,
):

    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50,
    )

    styles = getSampleStyleSheet()

    title_style = styles["Title"]
    title_style.alignment = TA_CENTER

    heading = styles["Heading2"]
    normal = styles["BodyText"]

    story = []

    story.append(
        Paragraph(
            "KOJA AFRICA",
            title_style,
        )
    )

    story.append(
        Spacer(1, 15)
    )

    story.append(
        Paragraph(
            title,
            heading,
        )
    )

    story.append(
        Spacer(1, 10)
    )

    story.append(
        Paragraph(
            f"<b>Student:</b> {student_name}",
            normal,
        )
    )

    story.append(
        Spacer(1, 15)
    )

    story.append(
        Paragraph(
            "<b>Question</b>",
            heading,
        )
    )

    story.append(
        Paragraph(
            question.replace("\n", "<br/>"),
            normal,
        )
    )

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            "<b>Answer</b>",
            heading,
        )
    )

    safe_answer = answer.replace(
        "\n",
        "<br/>",
    )

    story.append(
        Paragraph(
            safe_answer,
            normal,
        )
    )

    story.append(
        Spacer(1, 30)
    )

    story.append(
        Paragraph(
            "Generated by KOJA AFRICA",
            normal,
        )
    )

    document.build(story)

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# WORD GENERATION
# ============================================================

def build_docx(
    title,
    student_name,
    question,
    answer,
):

    document = Document()

    document.add_heading(
        "KOJA AFRICA",
        0,
    )

    document.add_heading(
        title,
        level=1,
    )

    document.add_paragraph(
        f"Student: {student_name}"
    )

    document.add_heading(
        "Question",
        level=2,
    )

    document.add_paragraph(
        question
    )

    document.add_heading(
        "Answer",
        level=2,
    )

    document.add_paragraph(
        answer
    )

    document.add_paragraph(
        "Generated by KOJA AFRICA"
    )

    buffer = io.BytesIO()

    document.save(buffer)

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# EXCEL GENERATION
# ============================================================

def build_xlsx(
    title,
    student_name,
    question,
    answer,
):

    workbook = Workbook()

    sheet = workbook.active

    sheet.title = "Assignment Answer"

    sheet["A1"] = "KOJA AFRICA"

    sheet["A2"] = "Assignment"

    sheet["B2"] = title

    sheet["A3"] = "Student"

    sheet["B3"] = student_name

    sheet["A5"] = "Question"

    sheet["B5"] = question

    sheet["A7"] = "Answer"

    sheet["B7"] = answer

    sheet.column_dimensions["A"].width = 25

    sheet.column_dimensions["B"].width = 100

    buffer = io.BytesIO()

    workbook.save(buffer)

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# COMMON PAGE
# ============================================================

BASE_HTML = """
<!doctype html>
<html lang="en">
<head>

<meta charset="utf-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>{{ title }} - KOJA AFRICA</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f4f7fb;
    color: #172033;
}

.nav {
    background: #0b3d91;
    color: white;
    padding: 14px 18px;
}

.nav-inner {
    max-width: 1100px;
    margin: auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;
    flex-wrap: wrap;
}

.brand {
    font-size: 22px;
    font-weight: bold;
}

.nav a {
    color: white;
    text-decoration: none;
    margin: 4px 7px;
}

.container {
    max-width: 1100px;
    margin: 25px auto;
    padding: 0 15px;
}

.card {
    background: white;
    border-radius: 12px;
    padding: 22px;
    margin-bottom: 18px;
    box-shadow: 0 2px 12px rgba(0,0,0,.07);
}

h1, h2, h3 {
    margin-top: 0;
}

input,
textarea,
select {
    width: 100%;
    padding: 12px;
    margin-top: 6px;
    margin-bottom: 14px;
    border: 1px solid #ccd3df;
    border-radius: 8px;
    font-size: 15px;
}

textarea {
    min-height: 180px;
    resize: vertical;
}

button,
.btn {
    display: inline-block;
    background: #0b3d91;
    color: white;
    border: 0;
    border-radius: 8px;
    padding: 11px 16px;
    cursor: pointer;
    text-decoration: none;
    margin: 4px;
}

.btn-green {
    background: #138a4b;
}

.btn-red {
    background: #b42318;
}

.btn-dark {
    background: #172033;
}

.grid {
    display: grid;
    grid-template-columns: repeat(
        auto-fit,
        minmax(220px, 1fr)
    );
    gap: 15px;
}

.stat {
    padding: 20px;
    border-radius: 10px;
    background: #eef4ff;
}

.stat strong {
    display: block;
    font-size: 30px;
    margin-bottom: 5px;
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

.badge {
    display: inline-block;
    padding: 5px 9px;
    border-radius: 15px;
    background: #e8eef8;
}

.flash {
    padding: 12px;
    margin-bottom: 12px;
    border-radius: 8px;
    background: #eef4ff;
}

.footer {
    text-align: center;
    padding: 30px;
    color: #687386;
}

@media(max-width:600px) {

    table {
        display: block;
        overflow-x: auto;
    }

    .nav-inner {
        align-items: flex-start;
    }

}

</style>

</head>

<body>

<div class="nav">

<div class="nav-inner">

<div class="brand">
KOJA AFRICA
</div>

<div>

<a href="{{ url_for('home') }}">Home</a>

{% if session.get('user') %}

<a href="{{ url_for('dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('new_assignment') }}">
Ask Question
</a>

<a href="{{ url_for('assignments') }}">
My Assignments
</a>

{% if session.get('user', {}).get('is_admin') %}

<a href="{{ url_for('admin_dashboard') }}">
Admin
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
Register
</a>

{% endif %}

</div>

</div>

</div>

<div class="container">

{% for category, message in get_flashed_messages(with_categories=true) %}

<div class="flash">
{{ message }}
</div>

{% endfor %}

{{ body|safe }}

</div>

<div class="footer">

KOJA AFRICA<br>

Assignment Questions • Academic Answers • Learning Resources

</div>

</body>
</html>
"""


def page(title, body):
    return render_template_string(
        BASE_HTML,
        title=title,
        body=body,
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    body = """
    <div class="card">

    <h1>KOJA AFRICA</h1>

    <p>
    Assignment Questions • Academic Answers •
    Learning Resources
    </p>

    <p>
    Submit academic questions, upload assignments
    and receive completed answers.
    </p>

    <a class="btn" href="/register">
    Create Student Account
    </a>

    <a class="btn btn-dark" href="/login">
    Login
    </a>

    </div>

    <div class="grid">

    <div class="card">
    <h3>Ask Questions</h3>
    <p>
    Send an academic question directly through
    your KOJA account.
    </p>
    </div>

    <div class="card">
    <h3>Upload Assignments</h3>
    <p>
    Upload PDF, Word or supported question files.
    </p>
    </div>

    <div class="card">
    <h3>Download Answers</h3>
    <p>
    Completed answers can be provided in
    PDF, Word and Excel formats.
    </p>
    </div>

    </div>
    """

    return page(
        "Home",
        body,
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"],
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
                "All fields are required.",
                "warning",
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "warning",
            )

            return redirect(
                url_for("register")
            )

        try:

            existing = find_profile(email)

            if existing:
                flash(
                    "An account with that email already exists.",
                    "warning",
                )

                return redirect(
                    url_for("login")
                )

            password_hash = generate_password_hash(
                password
            )

            profile = create_profile(
                email,
                name,
                password_hash,
                False,
            )

            session["user"] = {
                "id": profile.get("id"),
                "email": email,
                "full_name": name,
                "is_admin": False,
            }

            log_activity(
                "register",
                "New student account created",
            )

            flash(
                "Account created successfully.",
                "success",
            )

            return redirect(
                url_for("dashboard")
            )

        except Exception as exc:

            logging.exception(
                "Registration error"
            )

            flash(
                f"Registration error: {exc}",
                "danger",
            )

    body = """

    <div class="card">

    <h1>Create Account</h1>

    <form method="post">

    <label>Full name</label>

    <input
        name="name"
        required
        placeholder="Your full name"
    >

    <label>Email</label>

    <input
        type="email"
        name="email"
        required
        placeholder="you@example.com"
    >

    <label>Password</label>

    <input
        type="password"
        name="password"
        required
        minlength="6"
        placeholder="At least 6 characters"
    >

    <button type="submit">
    Create Account
    </button>

    </form>

    </div>

    """

    return page(
        "Register",
        body,
    )


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"],
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

        if not email or not password:
            flash(
                "Enter email and password.",
                "warning",
            )

            return redirect(
                url_for("login")
            )

        try:

            profile = verify_user(
                email,
                password,
            )

            if not profile:

                # Built-in emergency admin login.
                # Change ADMIN_PASSWORD in Render.
                if (
                    email == ADMIN_EMAIL
                    and password == ADMIN_PASSWORD
                ):

                    session["user"] = {
                        "id": "admin",
                        "email": ADMIN_EMAIL,
                        "full_name": "KOJA Administrator",
                        "is_admin": True,
                    }

                    return redirect(
                        url_for("admin_dashboard")
                    )

                flash(
                    "Invalid email or password.",
                    "danger",
                )

                return redirect(
                    url_for("login")
                )

            session["user"] = {
                "id": profile.get("id"),
                "email": profile.get("email"),
                "full_name": profile.get(
                    "full_name",
                    profile.get("name", "")
                ),
                "is_admin": bool(
                    profile.get("is_admin", False)
                ),
            }

            log_activity(
                "login",
                "User logged in",
            )

            if profile.get("is_admin"):
                return redirect(
                    url_for("admin_dashboard")
                )

            return redirect(
                url_for("dashboard")
            )

        except Exception as exc:

            logging.exception(
                "Login error"
            )

            flash(
                f"Login error: {exc}",
                "danger",
            )

    body = """

    <div class="card">

    <h1>Login</h1>

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

    <p>
    Don't have an account?
    <a href="/register">Create one</a>
    </p>

    </div>

    """

    return page(
        "Login",
        body,
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success",
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    email = current_email()

    try:

        rows = db_select(
            "assignments",
            filters={
                "student_email": f"eq.{email}"
            },
            limit=100,
            order="created_at.desc",
        )

    except Exception:

        rows = []

    pending = 0
    processing = 0
    completed = 0

    for item in rows:

        status = str(
            item.get(
                "status",
                ""
            )
        ).lower()

        if status == "pending":
            pending += 1

        elif status == "processing":
            processing += 1

        elif status == "completed":
            completed += 1

    body = f"""

    <div class="card">

    <h1>
    Welcome, {current_user().get('full_name', 'Student')}
    </h1>

    <p>
    Submit questions and manage your assignments.
    </p>

    </div>

    <div class="grid">

    <div class="stat">
    <strong>{len(rows)}</strong>
    Total Assignments
    </div>

    <div class="stat">
    <strong>{pending}</strong>
    Pending
    </div>

    <div class="stat">
    <strong>{processing}</strong>
    Processing
    </div>

    <div class="stat">
    <strong>{completed}</strong>
    Completed
    </div>

    </div>

    <div class="card">

    <h2>Quick Actions</h2>

    <a class="btn"
       href="/assignment/new">
       Ask Question / Upload Assignment
    </a>

    <a class="btn btn-dark"
       href="/assignments">
       View My Assignments
    </a>

    </div>

    """

    return page(
        "Dashboard",
        body,
    )


# ============================================================
# NEW ASSIGNMENT
# ============================================================

@app.route(
    "/assignment/new",
    methods=["GET", "POST"],
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

        question = request.form.get(
            "question",
            ""
        ).strip()

        file = request.files.get(
            "question_file"
        )

        if not title:
            title = "Assignment Question"

        if not question and (
            not file or not file.filename
        ):
            flash(
                "Enter a question or upload a question file.",
                "warning",
            )

            return redirect(
                url_for("new_assignment")
            )

        try:

            assignment_data = {
                "student_email": current_email(),
                "title": title,
                "subject": subject,
                "question": question,
                "status": "Pending",
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }

            try:

                result = db_insert(
                    "assignments",
                    assignment_data,
                )

            except Exception as first_error:

                logging.exception(
                    "Full assignment insert failed"
                )

                # Compatibility fallback.
                fallback = {
                    "student_email": current_email(),
                    "title": title,
                    "question": question,
                    "status": "Pending",
                }

                try:
                    result = db_insert(
                        "assignments",
                        fallback,
                    )

                except Exception:
                    raise first_error

            if not result:
                raise RuntimeError(
                    "Assignment was not created."
                )

            assignment = result[0]

            assignment_id = assignment.get("id")

            if not assignment_id:
                raise RuntimeError(
                    "Assignment was created but no ID was returned."
                )

            # ------------------------------------------------
            # QUESTION FILE
            # ------------------------------------------------

            if file and file.filename:

                if not allowed_file(
                    file.filename
                ):
                    flash(
                        "Unsupported file type.",
                        "danger",
                    )

                    return redirect(
                        url_for("new_assignment")
                    )

                file_bytes = file.read()

                if len(file_bytes) > MAX_FILE_SIZE:
                    flash(
                        "File is too large.",
                        "danger",
                    )

                    return redirect(
                        url_for("new_assignment")
                    )

                original_name = secure_filename(
                    file.filename
                )

                extension = original_name.rsplit(
                    ".",
                    1
                )[-1].lower()

                storage_path = (
                    f"questions/"
                    f"{assignment_id}/"
                    f"{uuid.uuid4().hex}."
                    f"{extension}"
                )

                content_type = (
                    file.content_type
                    or "application/octet-stream"
                )

                storage_upload(
                    file_bytes,
                    storage_path,
                    content_type,
                )

                save_assignment_file(
                    assignment_id,
                    original_name,
                    storage_path,
                    content_type,
                    len(file_bytes),
                    "question",
                )

            log_activity(
                "assignment_created",
                f"Assignment {assignment_id} submitted",
            )

            flash(
                "Assignment submitted successfully.",
                "success",
            )

            return redirect(
                url_for(
                    "assignment_detail",
                    assignment_id=assignment_id,
                )
            )

        except Exception as exc:

            logging.exception(
                "Assignment creation failed"
            )

            flash(
                f"Could not submit assignment: {exc}",
                "danger",
            )

    body = """

    <div class="card">

    <h1>Assignment Request</h1>

    <p>
    Ask a question or upload your assignment.
    </p>

    <form
        method="post"
        enctype="multipart/form-data"
    >

    <label>Assignment title</label>

    <input
        name="title"
        placeholder="Example: Chemistry Assignment 1"
    >

    <label>Subject</label>

    <input
        name="subject"
        placeholder="Example: Chemistry"
    >

    <label>Ask your question</label>

    <textarea
        name="question"
        placeholder="Type your assignment question here..."
    ></textarea>

    <label>
    Upload question
    </label>

    <input
        type="file"
        name="question_file"
        accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.webp,.txt"
    >

    <p>
    Supported: PDF, Word, Excel, images and text files.
    Maximum: 15 MB.
    </p>

    <button type="submit">
    Submit Assignment
    </button>

    </form>

    </div>

    """

    return page(
        "Assignment Request",
        body,
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments")
@login_required
def assignments():

    email = current_email()

    try:

        rows = db_select(
            "assignments",
            filters={
                "student_email": f"eq.{email}"
            },
            limit=200,
            order="created_at.desc",
        )

    except Exception as exc:

        logging.exception(
            "Assignment listing failed"
        )

        flash(
            f"Could not load assignments: {exc}",
            "danger",
        )

        rows = []

    html = """

    <div class="card">

    <h1>My Assignments</h1>

    <a class="btn"
       href="/assignment/new">
       New Assignment
    </a>

    </div>

    """

    if not rows:

        html += """
        <div class="card">
        <p>No assignments submitted yet.</p>
        </div>
        """

    else:

        html += """
        <div class="card">

        <table>

        <tr>
        <th>Title</th>
        <th>Subject</th>
        <th>Status</th>
        <th>Date</th>
        <th></th>
        </tr>
        """

        for item in rows:

            assignment_id = item.get(
                "id",
                ""
            )

            title = item.get(
                "title",
                "Assignment"
            )

            subject = item.get(
                "subject",
                ""
            )

            status = item.get(
                "status",
                "Pending"
            )

            created = item.get(
                "created_at",
                ""
            )

            html += f"""

            <tr>

            <td>{title}</td>

            <td>{subject}</td>

            <td>
            <span class="badge">
            {status}
            </span>
            </td>

            <td>{created}</td>

            <td>
            <a class="btn"
               href="/assignment/{assignment_id}">
               Open
            </a>
            </td>

            </tr>

            """

        html += """
        </table>

        </div>
        """

    return page(
        "My Assignments",
        html,
    )


# ============================================================
# ASSIGNMENT DETAIL
# ============================================================

@app.route(
    "/assignment/<assignment_id>"
)
@login_required
def assignment_detail(
    assignment_id
):

    try:

        rows = db_select(
            "assignments",
            filters={
                "id": f"eq.{assignment_id}",
                "student_email": f"eq.{current_email()}",
            },
            limit=1,
        )

        if not rows:
            abort(404)

        assignment = rows[0]

        files = db_select(
            "assignment_files",
            filters={
                "assignment_id":
                    f"eq.{assignment_id}"
            },
            limit=100,
            order="created_at.desc",
        )

    except Exception as exc:

        logging.exception(
            "Assignment detail error"
        )

        flash(
            f"Could not load assignment: {exc}",
            "danger",
        )

        return redirect(
            url_for("assignments")
        )

    html = f"""

    <div class="card">

    <h1>{assignment.get('title', 'Assignment')}</h1>

    <p>
    <b>Subject:</b>
    {assignment.get('subject', '')}
    </p>

    <p>
    <b>Status:</b>
    <span class="badge">
    {assignment.get('status', 'Pending')}
    </span>
    </p>

    <h2>Question</h2>

    <p>
    {str(assignment.get('question', '')).replace(chr(10), '<br>')}
    </p>

    </div>

    """

    if files:

        html += """
        <div class="card">

        <h2>Files</h2>
        """

        for file in files:

            file_id = file.get(
                "id"
            )

            name = file.get(
                "original_filename",
                "File"
            )

            role = file.get(
                "file_role",
                "question"
            )

            html += f"""

            <p>
            <b>{name}</b>
            ({role})

            <a class="btn"
               href="/file/{file_id}">
               Download
            </a>
            </p>

            """

        html += """
        </div>
        """

    status = str(
        assignment.get(
            "status",
            ""
        )
    ).lower()

    if status == "completed":

        html += """

        <div class="card">

        <h2>Completed Answer</h2>

        <p>
        Your assignment has been processed.
        </p>

        """

        answer = assignment.get(
            "answer",
            ""
        )

        if answer:

            html += f"""

            <div class="card">
            {str(answer).replace(chr(10), '<br>')}
            </div>

            """

        html += f"""

        <a class="btn"
           href="/answer/{assignment_id}/pdf">
           Download PDF
        </a>

        <a class="btn btn-green"
           href="/answer/{assignment_id}/docx">
           Download Word
        </a>

        <a class="btn btn-dark"
           href="/answer/{assignment_id}/xlsx">
           Download Excel
        </a>

        </div>

        """

    return page(
        "Assignment",
        html,
    )


# ============================================================
# FILE DOWNLOAD
# ============================================================

@app.route(
    "/file/<file_id>"
)
@login_required
def download_question_file(file_id):

    try:

        files = db_select(
            "assignment_files",
            filters={
                "id": f"eq.{file_id}"
            },
            limit=1,
        )

        if not files:
            abort(404)

        file_record = files[0]

        assignment_id = file_record.get(
            "assignment_id"
        )

        assignments_rows = db_select(
            "assignments",
            filters={
                "id": f"eq.{assignment_id}"
            },
            limit=1,
        )

        if not assignments_rows:
            abort(404)

        assignment = assignments_rows[0]

        user = current_user()

        if (
            not user.get("is_admin")
            and assignment.get("student_email")
            != current_email()
        ):
            abort(403)

        content = storage_download(
            file_record.get(
                "storage_path"
            )
        )

        filename = file_record.get(
            "original_filename",
            "download",
        )

        content_type = file_record.get(
            "content_type",
            "application/octet-stream",
        )

        return send_file(
            io.BytesIO(content),
            as_attachment=True,
            download_name=filename,
            mimetype=content_type,
        )

    except Exception as exc:

        logging.exception(
            "File download error"
        )

        flash(
            f"File download failed: {exc}",
            "danger",
        )

        return redirect(
            url_for("assignments")
        )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    try:

        assignments_rows = db_select(
            "assignments",
            limit=500,
            order="created_at.desc",
        )

    except Exception as exc:

        logging.exception(
            "Admin assignment query failed"
        )

        assignments_rows = []

        flash(
            f"Could not load assignments: {exc}",
            "danger",
        )

    try:

        profiles = db_select(
            "profiles",
            limit=500,
            order="created_at.desc",
        )

    except Exception:

        profiles = []

    pending = 0
    processing = 0
    completed = 0

    for item in assignments_rows:

        status = str(
            item.get(
                "status",
                ""
            )
        ).lower()

        if status == "pending":
            pending += 1

        elif status == "processing":
            processing += 1

        elif status == "completed":
            completed += 1

    html = f"""

    <div class="card">

    <h1>KOJA AFRICA Admin</h1>

    <div class="grid">

    <div class="stat">
    <strong>{len(profiles)}</strong>
    Users
    </div>

    <div class="stat">
    <strong>{len(assignments_rows)}</strong>
    Assignments
    </div>

    <div class="stat">
    <strong>{pending}</strong>
    Pending
    </div>

    <div class="stat">
    <strong>{completed}</strong>
    Completed
    </div>

    </div>

    </div>

    <div class="card">

    <h2>Assignment Requests</h2>

    """

    if not assignments_rows:

        html += "<p>No assignments.</p>"

    else:

        html += """

        <table>

        <tr>
        <th>Student</th>
        <th>Title</th>
        <th>Subject</th>
        <th>Status</th>
        <th>Action</th>
        </tr>

        """

        for item in assignments_rows:

            aid = item.get(
                "id",
                ""
            )

            html += f"""

            <tr>

            <td>
            {item.get('student_email', '')}
            </td>

            <td>
            {item.get('title', '')}
            </td>

            <td>
            {item.get('subject', '')}
            </td>

            <td>
            <span class="badge">
            {item.get('status', 'Pending')}
            </span>
            </td>

            <td>
            <a class="btn"
               href="/admin/assignment/{aid}">
               Process
            </a>
            </td>

            </tr>

            """

        html += "</table>"

    html += "</div>"

    return page(
        "Admin Dashboard",
        html,
    )


# ============================================================
# ADMIN PROCESS ASSIGNMENT
# ============================================================

@app.route(
    "/admin/assignment/<assignment_id>",
    methods=["GET", "POST"],
)
@admin_required
def admin_assignment(
    assignment_id
):

    try:

        rows = db_select(
            "assignments",
            filters={
                "id": f"eq.{assignment_id}"
            },
            limit=1,
        )

        if not rows:
            abort(404)

        assignment = rows[0]

    except Exception as exc:

        flash(
            f"Could not load assignment: {exc}",
            "danger",
        )

        return redirect(
            url_for("admin_dashboard")
        )

    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        )

        if action == "processing":

            try:

                db_update(
                    "assignments",
                    {
                        "id":
                            f"eq.{assignment_id}"
                    },
                    {
                        "status": "Processing",
                        "updated_at": utc_now(),
                    },
                )

                log_activity(
                    "assignment_processing",
                    f"{assignment_id} moved to processing",
                )

                flash(
                    "Assignment marked as processing.",
                    "success",
                )

            except Exception as exc:

                flash(
                    f"Could not update status: {exc}",
                    "danger",
                )

            return redirect(
                url_for(
                    "admin_assignment",
                    assignment_id=assignment_id,
                )
            )

        if action == "complete":

            answer = request.form.get(
                "answer",
                ""
            ).strip()

            if not answer:

                flash(
                    "Enter the answer before completing the assignment.",
                    "warning",
                )

                return redirect(
                    url_for(
                        "admin_assignment",
                        assignment_id=assignment_id,
                    )
                )

            try:

                db_update(
                    "assignments",
                    {
                        "id":
                            f"eq.{assignment_id}"
                    },
                    {
                        "answer": answer,
                        "status": "Completed",
                        "updated_at": utc_now(),
                        "completed_at": utc_now(),
                    },
                )

                # Notification
                notification = {
                    "student_email":
                        assignment.get(
                            "student_email"
                        ),
                    "title":
                        "Assignment Completed",
                    "message":
                        "Your assignment answer is ready for download.",
                    "created_at":
                        utc_now(),
                }

                try:

                    db_insert(
                        "notifications",
                        notification,
                        returning=False,
                    )

                except Exception:

                    logging.exception(
                        "Notification creation failed"
                    )

                log_activity(
                    "assignment_completed",
                    f"{assignment_id} completed",
                )

                flash(
                    "Assignment completed successfully.",
                    "success",
                )

                return redirect(
                    url_for(
                        "admin_assignment",
                        assignment_id=assignment_id,
                    )
                )

            except Exception as exc:

                logging.exception(
                    "Assignment completion failed"
                )

                flash(
                    f"Could not complete assignment: {exc}",
                    "danger",
                )

    try:

        files = db_select(
            "assignment_files",
            filters={
                "assignment_id":
                    f"eq.{assignment_id}"
            },
            limit=100,
            order="created_at.desc",
        )

    except Exception:

        files = []

    html = f"""

    <div class="card">

    <h1>Process Assignment</h1>

    <p>
    <b>Student:</b>
    {assignment.get('student_email', '')}
    </p>

    <p>
    <b>Title:</b>
    {assignment.get('title', '')}
    </p>

    <p>
    <b>Subject:</b>
    {assignment.get('subject', '')}
    </p>

    <p>
    <b>Status:</b>
    <span class="badge">
    {assignment.get('status', 'Pending')}
    </span>
    </p>

    <h2>Question</h2>

    <div class="card">

    {str(assignment.get('question', '')).replace(chr(10), '<br>')}

    </div>

    """

    if files:

        html += """

        <h2>Uploaded Files</h2>
        """

        for file_record in files:

            file_id = file_record.get(
                "id"
            )

            filename = file_record.get(
                "original_filename",
                "File"
            )

            html += f"""

            <p>
            {filename}

            <a class="btn"
               href="/file/{file_id}">
               Download
            </a>
            </p>

            """

    html += """

    <hr>

    <form method="post">

    <input
        type="hidden"
        name="action"
        value="processing"
    >

    <button type="submit">
    Mark Processing
    </button>

    </form>

    <h2>Write Answer</h2>

    <form method="post">

    <input
        type="hidden"
        name="action"
        value="complete"
    >

    <textarea
        name="answer"
        placeholder="Write the completed academic answer here..."
        required
    ></textarea>

    <button
        type="submit"
        class="btn-green"
    >
    Complete Assignment
    </button>

    </form>

    </div>

    """

    return page(
        "Process Assignment",
        html,
    )


# ============================================================
# ANSWER DOWNLOADS
# ============================================================

def get_completed_assignment(
    assignment_id
):

    rows = db_select(
        "assignments",
        filters={
            "id":
                f"eq.{assignment_id}"
        },
        limit=1,
    )

    if not rows:
        abort(404)

    assignment = rows[0]

    user = current_user()

    if (
        not user.get("is_admin")
        and assignment.get("student_email")
        != current_email()
    ):
        abort(403)

    if str(
        assignment.get(
            "status",
            ""
        )
    ).lower() != "completed":

        flash(
            "This assignment has not been completed yet.",
            "warning",
        )

        abort(404)

    return assignment


@app.route(
    "/answer/<assignment_id>/pdf"
)
@login_required
def answer_pdf(assignment_id):

    assignment = get_completed_assignment(
        assignment_id
    )

    data = build_pdf(
        assignment.get(
            "title",
            "Assignment Answer"
        ),
        assignment.get(
            "student_email",
            ""
        ),
        assignment.get(
            "question",
            ""
        ),
        assignment.get(
            "answer",
            ""
        ),
    )

    log_download(
        assignment_id,
        "pdf",
    )

    return send_file(
        io.BytesIO(data),
        as_attachment=True,
        download_name=(
            f"KOJA-Answer-{assignment_id}.pdf"
        ),
        mimetype="application/pdf",
    )


@app.route(
    "/answer/<assignment_id>/docx"
)
@login_required
def answer_docx(assignment_id):

    assignment = get_completed_assignment(
        assignment_id
    )

    data = build_docx(
        assignment.get(
            "title",
            "Assignment Answer"
        ),
        assignment.get(
            "student_email",
            ""
        ),
        assignment.get(
            "question",
            ""
        ),
        assignment.get(
            "answer",
            ""
        ),
    )

    log_download(
        assignment_id,
        "docx",
    )

    return send_file(
        io.BytesIO(data),
        as_attachment=True,
        download_name=(
            f"KOJA-Answer-{assignment_id}.docx"
        ),
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )


@app.route(
    "/answer/<assignment_id>/xlsx"
)
@login_required
def answer_xlsx(assignment_id):

    assignment = get_completed_assignment(
        assignment_id
    )

    data = build_xlsx(
        assignment.get(
            "title",
            "Assignment Answer"
        ),
        assignment.get(
            "student_email",
            ""
        ),
        assignment.get(
            "question",
            ""
        ),
        assignment.get(
            "answer",
            ""
        ),
    )

    log_download(
        assignment_id,
        "xlsx",
    )

    return send_file(
        io.BytesIO(data),
        as_attachment=True,
        download_name=(
            f"KOJA-Answer-{assignment_id}.xlsx"
        ),
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )


# ============================================================
# DOWNLOAD LOG
# ============================================================

def log_download(
    assignment_id,
    file_type,
):

    data = {
        "assignment_id":
            assignment_id,
        "student_email":
            current_email(),
        "file_type":
            file_type,
        "downloaded_at":
            utc_now(),
    }

    try:

        db_insert(
            "downloads",
            data,
            returning=False,
        )

    except Exception:

        logging.exception(
            "Download logging failed"
        )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@login_required
def notifications():

    try:

        rows = db_select(
            "notifications",
            filters={
                "student_email":
                    f"eq.{current_email()}"
            },
            limit=100,
            order="created_at.desc",
        )

    except Exception:

        rows = []

    html = """

    <div class="card">

    <h1>Notifications</h1>

    """

    if not rows:

        html += """
        <p>No notifications.</p>
        """

    else:

        for notification in rows:

            html += f"""

            <div class="card">

            <h3>
            {notification.get('title', 'Notification')}
            </h3>

            <p>
            {notification.get('message', '')}
            </p>

            <small>
            {notification.get('created_at', '')}
            </small>

            </div>

            """

    html += "</div>"

    return page(
        "Notifications",
        html,
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    result = {
        "status": "ok",
        "application": APP_NAME,
        "time": utc_now(),
        "supabase_configured":
            bool(
                SUPABASE_URL
                and SUPABASE_SERVICE_KEY
            ),
    }

    return result


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def error_404(error):

    return page(
        "Page Not Found",
        """
        <div class="card">

        <h1>404</h1>

        <p>
        The requested page was not found.
        </p>

        <a class="btn" href="/">
        Return Home
        </a>

        </div>
        """,
    ), 404


@app.errorhandler(500)
def error_500(error):

    logging.exception(
        "Unhandled application error"
    )

    return page(
        "Application Error",
        """
        <div class="card">

        <h1>Application Error</h1>

        <p>
        KOJA AFRICA encountered an internal error.
        </p>

        <p>
        Please try again.
        </p>

        <a class="btn" href="/">
        Return Home
        </a>

        </div>
        """,
    ), 500


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
