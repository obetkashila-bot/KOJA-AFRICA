import os
import io
import uuid
import secrets
import logging
from functools import wraps
from datetime import datetime, timezone

import requests

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
    jsonify,
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
)
from reportlab.lib.units import mm


# ============================================================
# CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "KOJA_SECRET_KEY",
    secrets.token_hex(32)
)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

STORAGE_BUCKET = os.environ.get(
    "KOJA_STORAGE_BUCKET",
    "koja-assignments"
)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

OPENAI_MODEL = os.environ.get(
    "OPENAI_MODEL",
    "gpt-5"
)

ADMIN_EMAIL = os.environ.get(
    "KOJA_ADMIN_EMAIL",
    ""
)

ADMIN_PASSWORD = os.environ.get(
    "KOJA_ADMIN_PASSWORD",
    ""
)

APP_NAME = "KOJA AFRICA"
APP_TAGLINE = "Assignment Questions • Academic Answers • Learning Resources"

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "txt",
    "csv",
}


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("koja")


# ============================================================
# BASIC CHECKS
# ============================================================

def configuration_error():
    missing = []

    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")

    if not SUPABASE_SERVICE_KEY:
        missing.append("SUPABASE_SERVICE_KEY")

    if not app.secret_key:
        missing.append("KOJA_SECRET_KEY")

    return missing


# ============================================================
# SUPABASE REST
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


def supabase_request(
    method,
    table,
    params=None,
    data=None,
    prefer=None,
    timeout=30,
):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "Supabase environment variables are not configured."
        )

    url = f"{SUPABASE_URL}/rest/v1/{table}"

    headers = supabase_headers()

    if prefer:
        headers["Prefer"] = prefer

    response = requests.request(
        method,
        url,
        headers=headers,
        params=params,
        json=data,
        timeout=timeout,
    )

    if not response.ok:
        logger.error(
            "Supabase error %s: %s",
            response.status_code,
            response.text,
        )

    return response


def db_select(
    table,
    params=None,
):
    response = supabase_request(
        "GET",
        table,
        params=params,
    )

    if not response.ok:
        raise RuntimeError(response.text)

    if not response.text:
        return []

    return response.json()


def db_insert(
    table,
    data,
    select="*",
):
    response = supabase_request(
        "POST",
        table,
        params={
            "select": select
        },
        data=data,
        prefer="return=representation",
    )

    if not response.ok:
        raise RuntimeError(response.text)

    if not response.text:
        return []

    return response.json()


def db_update(
    table,
    filters,
    data,
    select="*",
):
    params = dict(filters)
    params["select"] = select

    response = supabase_request(
        "PATCH",
        table,
        params=params,
        data=data,
        prefer="return=representation",
    )

    if not response.ok:
        raise RuntimeError(response.text)

    if not response.text:
        return []

    return response.json()


def db_delete(
    table,
    filters,
):
    response = supabase_request(
        "DELETE",
        table,
        params=filters,
        prefer="return=minimal",
    )

    if not response.ok:
        raise RuntimeError(response.text)

    return True


# ============================================================
# STORAGE
# ============================================================

def storage_upload(
    file_bytes,
    path,
    content_type="application/octet-stream",
):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase is not configured.")

    path = path.lstrip("/")

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{path}"
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
            f"Storage upload failed: {response.text}"
        )

    return path


def storage_download(path):
    path = (path or "").lstrip("/")

    if not path:
        raise RuntimeError("Missing storage path.")

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}/{path}"
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
            f"Storage download failed: {response.text}"
        )

    return response.content


def storage_delete(path):
    if not path:
        return

    path = path.lstrip("/")

    url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{STORAGE_BUCKET}"
    )

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }

    requests.delete(
        url,
        headers=headers,
        json={
            "prefixes": [path]
        },
        timeout=30,
    )


# ============================================================
# HELPERS
# ============================================================

def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_EXTENSIONS


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def current_user():
    return session.get("user")


def is_admin():
    user = current_user()

    return bool(
        user and
        user.get("role") == "admin"
    )


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        if not current_user():
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):

        if not is_admin():
            flash("Administrator access required.", "danger")
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


def get_assignment(assignment_id):
    rows = db_select(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        },
    )

    return rows[0] if rows else None


def get_document(document_id):
    rows = db_select(
        "document_library",
        {
            "id": f"eq.{document_id}",
            "select": "*",
            "limit": "1",
        },
    )

    return rows[0] if rows else None


def get_assignment_answer(assignment_id):
    rows = db_select(
        "assignment_answers",
        {
            "assignment_id": f"eq.{assignment_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        },
    )

    return rows[0] if rows else None


def safe_text(value, max_length=20000):
    if value is None:
        return ""

    return str(value).strip()[:max_length]


# ============================================================
# PDF GENERATION
# ============================================================

def build_answer_pdf(
    title,
    subject,
    student_name,
    question,
    answer,
):
    output = io.BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "KOJATitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        leading=22,
        spaceAfter=10,
    )

    heading_style = ParagraphStyle(
        "KOJAHeading",
        parent=styles["Heading2"],
        fontSize=12,
        leading=16,
        spaceBefore=8,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "KOJABody",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=15,
        spaceAfter=8,
    )

    story = []

    story.append(
        Paragraph(
            APP_NAME,
            title_style,
        )
    )

    story.append(
        Paragraph(
            APP_TAGLINE,
            ParagraphStyle(
                "Tag",
                parent=body_style,
                alignment=TA_CENTER,
                fontSize=9,
            ),
        )
    )

    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            f"<b>Assignment:</b> {safe_text(title)}",
            body_style,
        )
    )

    story.append(
        Paragraph(
            f"<b>Subject:</b> {safe_text(subject)}",
            body_style,
        )
    )

    story.append(
        Paragraph(
            f"<b>Student:</b> {safe_text(student_name)}",
            body_style,
        )
    )

    story.append(
        Paragraph(
            "QUESTION",
            heading_style,
        )
    )

    question_html = safe_text(question).replace(
        "\n",
        "<br/>",
    )

    story.append(
        Paragraph(
            question_html,
            body_style,
        )
    )

    story.append(
        Paragraph(
            "ANSWER",
            heading_style,
        )
    )

    answer_html = safe_text(answer).replace(
        "\n",
        "<br/>",
    )

    story.append(
        Paragraph(
            answer_html,
            body_style,
        )
    )

    story.append(Spacer(1, 15))

    story.append(
        Paragraph(
            f"Generated by {APP_NAME}",
            ParagraphStyle(
                "Footer",
                parent=body_style,
                alignment=TA_CENTER,
                fontSize=8,
            ),
        )
    )

    document.build(story)

    output.seek(0)

    return output.getvalue()


# ============================================================
# AI
# ============================================================

def ai_answer(
    question,
    subject="",
    course="",
    class_level="",
):
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured on Render."
        )

    prompt = f"""
You are the academic assistant for {APP_NAME}.

Provide a clear, accurate educational answer.

Subject: {subject}
Course: {course}
Class level: {class_level}

Question:
{question}

Instructions:
1. Answer the actual question directly.
2. Explain important concepts.
3. Show calculations where applicable.
4. Use headings where useful.
5. Do not invent sources.
6. If the question is ambiguous, state the assumption.
7. Make the answer suitable for a student.
"""

    return openai_response(
        prompt,
        use_web=False,
    )


def ai_research(
    question,
):
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured on Render."
        )

    prompt = f"""
You are KOJA AFRICA Research Assistant.

Research and explain the following question:

{question}

Give a structured research response containing:

1. Direct answer
2. Explanation
3. Important evidence or findings
4. Practical examples where useful
5. Limitations or uncertainty
6. Sources/references when available

Do not fabricate references.
Distinguish established facts from uncertainty.
"""

    return openai_response(
        prompt,
        use_web=True,
    )


def openai_response(
    prompt,
    use_web=False,
):
    """
    Calls the OpenAI Responses API.

    The request is intentionally made server-side so the
    OpenAI API key is never exposed to the browser.
    """

    url = "https://api.openai.com/v1/responses"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENAI_MODEL,
        "input": prompt,
    }

    if use_web:
        payload["tools"] = [
            {
                "type": "web_search_preview"
            }
        ]

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            f"OpenAI error: {response.text}"
        )

    data = response.json()

    text = data.get("output_text")

    if text:
        return text

    # Fallback parser
    output = data.get("output", [])

    parts = []

    for item in output:

        content = item.get("content", [])

        for content_item in content:

            if content_item.get("type") in (
                "output_text",
                "text",
            ):
                text_value = content_item.get(
                    "text",
                    "",
                )

                if text_value:
                    parts.append(text_value)

    result = "\n\n".join(parts).strip()

    if not result:
        raise RuntimeError(
            "The AI returned no text."
        )

    return result


# ============================================================
# GLOBAL TEMPLATE
# ============================================================

BASE_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>{{ title or "KOJA AFRICA" }}</title>

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

nav {
    background: #102a43;
    color: white;
    padding: 14px;
}

nav .brand {
    font-size: 20px;
    font-weight: bold;
}

nav a {
    color: white;
    text-decoration: none;
    margin-right: 15px;
}

.container {
    max-width: 1100px;
    margin: 25px auto;
    padding: 0 15px;
}

.card {
    background: white;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 18px;
    box-shadow: 0 2px 10px rgba(0,0,0,.06);
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(220px, 1fr));
    gap: 15px;
}

input,
textarea,
select {
    width: 100%;
    padding: 11px;
    margin-top: 6px;
    margin-bottom: 12px;
    border: 1px solid #ccd5e0;
    border-radius: 8px;
    font-size: 15px;
}

textarea {
    min-height: 130px;
}

button,
.btn {
    display: inline-block;
    border: 0;
    padding: 10px 16px;
    border-radius: 8px;
    background: #1261a0;
    color: white;
    cursor: pointer;
    text-decoration: none;
}

.btn-danger {
    background: #c0392b;
}

.btn-success {
    background: #218c5a;
}

.btn-dark {
    background: #172033;
}

.flash {
    padding: 12px;
    border-radius: 8px;
    background: #fff3cd;
    margin-bottom: 15px;
}

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    text-align: left;
    padding: 10px;
    border-bottom: 1px solid #e5e9ef;
}

.answer {
    white-space: pre-wrap;
    line-height: 1.6;
}

.hero {
    text-align: center;
    padding: 40px 10px;
}

.small {
    color: #667085;
    font-size: 13px;
}

.stat {
    font-size: 30px;
    font-weight: bold;
}

@media(max-width:700px) {
    nav a {
        display: inline-block;
        margin-top: 8px;
    }

    table {
        font-size: 13px;
    }
}
</style>
</head>

<body>

<nav>
<div class="container" style="margin:0 auto;">
<span class="brand">KOJA AFRICA</span>

{% if session.get("user") %}
<a href="{{ url_for('dashboard') }}">Dashboard</a>

{% if session.get("user", {}).get("role") == "admin" %}
<a href="{{ url_for('admin_assignments') }}">Assignments</a>
{% endif %}

<a href="{{ url_for('research') }}">AI Research</a>
<a href="{{ url_for('documents') }}">Library</a>
<a href="{{ url_for('logout') }}">Logout</a>

{% else %}

<a href="{{ url_for('login') }}">Login</a>
<a href="{{ url_for('register') }}">Register</a>

{% endif %}
</div>
</nav>

<div class="container">

{% with messages = get_flashed_messages() %}
{% for message in messages %}
<div class="flash">{{ message }}</div>
{% endfor %}
{% endwith %}

{{ content|safe }}

</div>

</body>
</html>
"""


def page(content, title="KOJA AFRICA"):
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
<div class="hero">

<h1>KOJA AFRICA</h1>

<p>
Assignment Questions • Academic Answers • Learning Resources
</p>

<div style="margin-top:25px;">

<a class="btn"
   href="/login">
Student Login
</a>

<a class="btn btn-dark"
   href="/register">
Create Account
</a>

</div>

</div>

<div class="grid">

<div class="card">
<h3>Assignments</h3>
<p>Upload and manage academic assignments.</p>
</div>

<div class="card">
<h3>Answered Assignments</h3>
<p>Students can access completed answers.</p>
</div>

<div class="card">
<h3>AI Research</h3>
<p>Ask academic and research questions.</p>
</div>

<div class="card">
<h3>Document Library</h3>
<p>Access academic learning resources.</p>
</div>

</div>
"""

    return page(content)


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        email = safe_text(
            request.form.get("email"),
            255,
        ).lower()

        password = request.form.get(
            "password",
            "",
        )

        name = safe_text(
            request.form.get("student_name"),
            255,
        )

        if not email or not password or not name:
            flash("All fields are required.")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.")
            return redirect(url_for("register"))

        try:

            existing = db_select(
                "assignments",
                {
                    "email": f"eq.{email}",
                    "select": "email",
                    "limit": "1",
                },
            )

            # Registration information is stored in session.
            # Since the supplied schema does not contain a users
            # table, the application does not invent one.

            user_id = str(uuid.uuid4())

            session["user"] = {
                "id": user_id,
                "email": email,
                "student_name": name,
                "role": "student",
            }

            flash("Account created. You are now logged in.")

            return redirect(url_for("dashboard"))

        except Exception as exc:
            logger.exception(exc)
            flash("Registration failed.")
            return redirect(url_for("register"))

    content = """
<div class="card">

<h2>Create Student Account</h2>

<form method="post">

<label>Student name</label>
<input name="student_name" required>

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

    return page(content, "Register")


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = safe_text(
            request.form.get("email"),
            255,
        ).lower()

        password = request.form.get(
            "password",
            "",
        )

        # ----------------------------------------------------
        # ADMIN LOGIN
        # ----------------------------------------------------

        if (
            ADMIN_EMAIL
            and ADMIN_PASSWORD
            and email == ADMIN_EMAIL.lower()
            and secrets.compare_digest(
                password,
                ADMIN_PASSWORD,
            )
        ):

            session["user"] = {
                "id": str(uuid.uuid4()),
                "email": ADMIN_EMAIL,
                "student_name": "Administrator",
                "role": "admin",
            }

            return redirect(url_for("dashboard"))

        # ----------------------------------------------------
        # STUDENT LOGIN
        # ----------------------------------------------------

        # Because your supplied database schema has no users/auth
        # table, student authentication is session-based in this
        # single-file version.

        if email and password:

            session["user"] = {
                "id": str(uuid.uuid4()),
                "email": email,
                "student_name": email.split("@")[0],
                "role": "student",
            }

            return redirect(url_for("dashboard"))

        flash("Invalid login details.")

    content = """
<div class="card">

<h2>Login</h2>

<form method="post">

<label>Email</label>
<input type="email" name="email" required>

<label>Password</label>
<input type="password" name="password" required>

<button type="submit">
Login
</button>

</form>

</div>
"""

    return page(content, "Login")


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    user = current_user()

    if user.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))

    email = user.get("email")

    try:

        assignments = db_select(
            "assignments",
            {
                "email": f"eq.{email}",
                "select": "*",
                "order": "created_at.desc",
            },
        )

    except Exception as exc:
        logger.exception(exc)
        assignments = []

    rows = ""

    for assignment in assignments:

        answer = get_assignment_answer(
            assignment["id"]
        )

        answer_link = ""

        if answer and (
            answer.get("answer_file_path")
        ):

            answer_link = f"""
<a class="btn btn-success"
   href="/assignment/{assignment['id']}/answer/download">
Download Answer
</a>
"""

        rows += f"""
<tr>

<td>{safe_text(assignment.get('title'))}</td>

<td>{safe_text(assignment.get('subject'))}</td>

<td>{safe_text(assignment.get('status'))}</td>

<td>
{answer_link}
</td>

</tr>
"""

    content = f"""
<div class="card">

<h2>Student Dashboard</h2>

<p>
Welcome, <b>{safe_text(user.get('student_name'))}</b>
</p>

<a class="btn"
href="/assignment/upload">
Upload Assignment
</a>

<a class="btn btn-dark"
href="/research">
AI Research Chat
</a>

</div>

<div class="card">

<h3>My Assignments</h3>

<table>

<tr>
<th>Title</th>
<th>Subject</th>
<th>Status</th>
<th>Answer</th>
</tr>

{rows}

</table>

</div>
"""

    return page(content, "Student Dashboard")


# ============================================================
# UPLOAD ASSIGNMENT
# ============================================================

@app.route(
    "/assignment/upload",
    methods=["GET", "POST"],
)
@login_required
def upload_assignment():

    if is_admin():
        flash("Administrators should use the admin dashboard.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        title = safe_text(
            request.form.get("title"),
            255,
        )

        description = safe_text(
            request.form.get("description"),
            5000,
        )

        subject = safe_text(
            request.form.get("subject"),
            255,
        )

        course = safe_text(
            request.form.get("course"),
            255,
        )

        class_level = safe_text(
            request.form.get("class_level"),
            255,
        )

        question = safe_text(
            request.form.get("question"),
            10000,
        )

        file = request.files.get("file")

        if not title:
            flash("Assignment title is required.")
            return redirect(
                url_for("upload_assignment")
            )

        if not file or not file.filename:
            flash("Please select an assignment file.")
            return redirect(
                url_for("upload_assignment")
            )

        if not allowed_file(file.filename):
            flash("Unsupported file type.")
            return redirect(
                url_for("upload_assignment")
            )

        try:

            file_bytes = file.read()

            if len(file_bytes) > 20 * 1024 * 1024:
                flash("File is too large.")
                return redirect(
                    url_for("upload_assignment")
                )

            assignment_id = str(uuid.uuid4())

            original_name = secure_filename(
                file.filename
            )

            storage_path = (
                f"assignments/"
                f"{assignment_id}/"
                f"{original_name}"
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

            user = current_user()

            data = {
                "id": assignment_id,
                "student_id": user.get("id"),
                "title": title,
                "description": description,
                "subject": subject,
                "course": course,
                "class_level": class_level,
                "file_name": original_name,
                "file_path": storage_path,
                "file_size": len(file_bytes),
                "mime_type": content_type,
                "status": "submitted",
                "email": user.get("email"),
                "question": question,
                "student_name": user.get("student_name"),
            }

            db_insert(
                "assignments",
                data,
            )

            flash("Assignment uploaded successfully.")

            return redirect(
                url_for("dashboard")
            )

        except Exception as exc:

            logger.exception(exc)

            flash(
                "Assignment could not be saved: "
                + str(exc)
            )

    content = """
<div class="card">

<h2>Upload Assignment</h2>

<form
    method="post"
    enctype="multipart/form-data"
>

<label>Title</label>
<input name="title" required>

<label>Subject</label>
<input name="subject">

<label>Course</label>
<input name="course">

<label>Class level</label>
<input name="class_level">

<label>Description</label>
<textarea name="description"></textarea>

<label>Question</label>
<textarea
    name="question"
    placeholder="Paste the assignment question here if available."
></textarea>

<label>Assignment file</label>
<input
    type="file"
    name="file"
    required
>

<button type="submit">
Upload Assignment
</button>

</form>

</div>
"""

    return page(content, "Upload Assignment")


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    try:

        assignments = db_select(
            "assignments",
            {
                "select": "*",
                "order": "created_at.desc",
            },
        )

    except Exception as exc:

        logger.exception(exc)

        assignments = []

    try:

        documents = db_select(
            "document_library",
            {
                "select": "*",
                "order": "created_at.desc",
            },
        )

    except Exception:
        documents = []

    content = f"""
<div class="grid">

<div class="card">
<h3>Assignments</h3>
<div class="stat">{len(assignments)}</div>
</div>

<div class="card">
<h3>Documents</h3>
<div class="stat">{len(documents)}</div>
</div>

</div>

<div class="card">

<h2>Administrator Dashboard</h2>

<a class="btn"
href="/admin/assignments">
Manage Assignments
</a>

<a class="btn btn-dark"
href="/research">
AI Research
</a>

<a class="btn btn-success"
href="/admin/document/upload">
Upload Library Document
</a>

</div>
"""

    return page(content, "Admin Dashboard")


# ============================================================
# ADMIN ASSIGNMENTS
# ============================================================

@app.route("/admin/assignments")
@admin_required
def admin_assignments():

    try:

        assignments = db_select(
            "assignments",
            {
                "select": "*",
                "order": "created_at.desc",
            },
        )

    except Exception as exc:

        logger.exception(exc)

        flash("Could not load assignments.")
        assignments = []

    rows = ""

    for a in assignments:

        assignment_id = a["id"]

        answer = get_assignment_answer(
            assignment_id
        )

        answer_status = (
            answer.get("status")
            if answer
            else "Not answered"
        )

        rows += f"""
<tr>

<td>
{safe_text(a.get('title'))}
</td>

<td>
{safe_text(a.get('student_name'))}
</td>

<td>
{safe_text(a.get('email'))}
</td>

<td>
{safe_text(a.get('subject'))}
</td>

<td>
{safe_text(a.get('status'))}
</td>

<td>
{safe_text(answer_status)}
</td>

<td>

<a class="btn"
href="/admin/assignment/{assignment_id}">
Open
</a>

</td>

</tr>
"""

    content = f"""
<div class="card">

<h2>Assignments</h2>

<table>

<tr>
<th>Title</th>
<th>Student</th>
<th>Email</th>
<th>Subject</th>
<th>Status</th>
<th>Answer</th>
<th>Action</th>
</tr>

{rows}

</table>

</div>
"""

    return page(content, "Assignments")


# ============================================================
# ADMIN OPEN ASSIGNMENT
# ============================================================

@app.route(
    "/admin/assignment/<assignment_id>"
)
@admin_required
def admin_assignment(assignment_id):

    assignment = get_assignment(
        assignment_id
    )

    if not assignment:
        abort(404)

    answer = get_assignment_answer(
        assignment_id
    )

    existing_answer = ""

    if answer:
        existing_answer = safe_text(
            answer.get("answer_text"),
            20000,
        )

    content = f"""
<div class="card">

<h2>{safe_text(assignment.get('title'))}</h2>

<p>
<b>Student:</b>
{safe_text(assignment.get('student_name'))}
</p>

<p>
<b>Email:</b>
{safe_text(assignment.get('email'))}
</p>

<p>
<b>Subject:</b>
{safe_text(assignment.get('subject'))}
</p>

<p>
<b>Course:</b>
{safe_text(assignment.get('course'))}
</p>

<p>
<b>Class:</b>
{safe_text(assignment.get('class_level'))}
</p>

<p>
<a class="btn"
href="/assignment/{assignment_id}/download">
Download Original Assignment
</a>
</p>

<h3>Question</h3>

<div class="answer">
{safe_text(assignment.get('question'))}
</div>

</div>

<div class="card">

<h2>AI Answer</h2>

<form
method="post"
action="/admin/assignment/{assignment_id}/ai-answer"
>

<button type="submit">
Generate AI Answer
</button>

</form>

</div>

<div class="card">

<h2>Write / Edit Answer</h2>

<form
method="post"
action="/admin/assignment/{assignment_id}/answer"
>

<textarea
name="answer"
style="min-height:400px;"
required
>{existing_answer}</textarea>

<button type="submit">
Save Answer
</button>

</form>

</div>
"""

    return page(content, "Assignment")


# ============================================================
# ADMIN AI ANSWER
# ============================================================

@app.route(
    "/admin/assignment/<assignment_id>/ai-answer",
    methods=["POST"],
)
@admin_required
def admin_ai_answer(assignment_id):

    assignment = get_assignment(
        assignment_id
    )

    if not assignment:
        abort(404)

    question = (
        assignment.get("question")
        or assignment.get("description")
        or ""
    )

    if not question:

        flash(
            "This assignment does not contain a question."
        )

        return redirect(
            url_for(
                "admin_assignment",
                assignment_id=assignment_id,
            )
        )

    try:

        answer = ai_answer(
            question=question,
            subject=assignment.get("subject") or "",
            course=assignment.get("course") or "",
            class_level=assignment.get("class_level") or "",
        )

        user = current_user()

        existing = get_assignment_answer(
            assignment_id
        )

        data = {
            "assignment_id": assignment_id,
            "student_id": assignment.get("student_id"),
            "answer_text": answer,
            "generated_by": "OpenAI",
            "status": "draft",
            "updated_at": now_iso(),
        }

        if existing:

            db_update(
                "assignment_answers",
                {
                    "id": f"eq.{existing['id']}"
                },
                data,
            )

        else:

            data["id"] = str(uuid.uuid4())

            db_insert(
                "assignment_answers",
                data,
            )

        flash("AI answer generated.")

    except Exception as exc:

        logger.exception(exc)

        flash(
            "AI answer failed: "
            + str(exc)
        )

    return redirect(
        url_for(
            "admin_assignment",
            assignment_id=assignment_id,
        )
    )


# ============================================================
# ADMIN SAVE ANSWER
# ============================================================

@app.route(
    "/admin/assignment/<assignment_id>/answer",
    methods=["POST"],
)
@admin_required
def save_assignment_answer(assignment_id):

    assignment = get_assignment(
        assignment_id
    )

    if not assignment:
        abort(404)

    answer_text = safe_text(
        request.form.get("answer"),
        50000,
    )

    if not answer_text:
        flash("Answer cannot be empty.")
        return redirect(
            url_for(
                "admin_assignment",
                assignment_id=assignment_id,
            )
        )

    try:

        user = current_user()

        pdf_bytes = build_answer_pdf(
            title=assignment.get("title") or "Assignment",
            subject=assignment.get("subject") or "",
            student_name=assignment.get("student_name") or "",
            question=assignment.get("question") or "",
            answer=answer_text,
        )

        pdf_name = (
            secure_filename(
                assignment.get("title")
                or "assignment"
            )
            + "_answered.pdf"
        )

        pdf_path = (
            f"answer-pdfs/"
            f"{assignment_id}/"
            f"{uuid.uuid4()}_{pdf_name}"
        )

        storage_upload(
            pdf_bytes,
            pdf_path,
            "application/pdf",
        )

        existing = get_assignment_answer(
            assignment_id
        )

        answer_data = {
            "assignment_id": assignment_id,
            "student_id": assignment.get("student_id"),
            "answer_text": answer_text,
            "answer_file_name": pdf_name,
            "answer_file_path": pdf_path,
            "generated_by": user.get("email"),
            "status": "published",
            "updated_at": now_iso(),
        }

        if existing:

            db_update(
                "assignment_answers",
                {
                    "id": f"eq.{existing['id']}"
                },
                answer_data,
            )

        else:

            answer_data["id"] = str(uuid.uuid4())

            db_insert(
                "assignment_answers",
                answer_data,
            )

        # Update assignment itself using the columns
        # that actually exist in your table.

        db_update(
            "assignments",
            {
                "id": f"eq.{assignment_id}"
            },
            {
                "answer_file_name": pdf_name,
                "answer_file_path": pdf_path,
                "answered_at": now_iso(),
                "answered_by": user.get("id"),
                "status": "answered",
                "updated_at": now_iso(),
            },
        )

        flash(
            "Answer saved and PDF generated successfully."
        )

    except Exception as exc:

        logger.exception(exc)

        flash(
            "Could not save answer: "
            + str(exc)
        )

    return redirect(
        url_for(
            "admin_assignment",
            assignment_id=assignment_id,
        )
    )


# ============================================================
# DOWNLOAD ORIGINAL ASSIGNMENT
# ============================================================

@app.route(
    "/assignment/<assignment_id>/download"
)
@login_required
def download_assignment(assignment_id):

    assignment = get_assignment(
        assignment_id
    )

    if not assignment:
        abort(404)

    user = current_user()

    if (
        user.get("role") != "admin"
        and assignment.get("email") != user.get("email")
    ):
        abort(403)

    try:

        file_bytes = storage_download(
            assignment.get("file_path")
        )

        filename = (
            assignment.get("file_name")
            or "assignment"
        )

        return send_file(
            io.BytesIO(file_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype=assignment.get(
                "mime_type",
                "application/octet-stream",
            ),
        )

    except Exception as exc:

        logger.exception(exc)

        abort(404)


# ============================================================
# DOWNLOAD ANSWER
# ============================================================

@app.route(
    "/assignment/<assignment_id>/answer/download"
)
@login_required
def download_answer(assignment_id):

    assignment = get_assignment(
        assignment_id
    )

    if not assignment:
        abort(404)

    user = current_user()

    if (
        user.get("role") != "admin"
        and assignment.get("email") != user.get("email")
    ):
        abort(403)

    answer = get_assignment_answer(
        assignment_id
    )

    if not answer:
        abort(404)

    path = answer.get(
        "answer_file_path"
    ) or assignment.get(
        "answer_file_path"
    )

    if not path:
        abort(404)

    try:

        file_bytes = storage_download(path)

        filename = (
            answer.get("answer_file_name")
            or assignment.get("answer_file_name")
            or "answered_assignment.pdf"
        )

        return send_file(
            io.BytesIO(file_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf",
        )

    except Exception as exc:

        logger.exception(exc)

        abort(404)


# ============================================================
# AI RESEARCH CHAT
# ============================================================

@app.route(
    "/research",
    methods=["GET", "POST"],
)
@login_required
def research():

    result = ""

    question = ""

    if request.method == "POST":

        question = safe_text(
            request.form.get("question"),
            10000,
        )

        if not question:

            flash("Enter a research question.")

        else:

            try:

                result = ai_research(
                    question
                )

            except Exception as exc:

                logger.exception(exc)

                flash(
                    "Research request failed: "
                    + str(exc)
                )

    result_html = ""

    if result:

        result_html = f"""
<div class="card">

<h2>Research Result</h2>

<div class="answer">
{safe_text(result, 50000)}
</div>

</div>
"""

    content = f"""
<div class="card">

<h2>KOJA AI Research Chat</h2>

<p>
Ask questions about science, education,
technology, agriculture, business, history,
or other academic topics.
</p>

<form method="post">

<textarea
name="question"
placeholder="Example: Explain the factors affecting the rate of a chemical reaction."
required
>{safe_text(question)}</textarea>

<button type="submit">
Research
</button>

</form>

</div>

{result_html}
"""

    return page(content, "AI Research")


# ============================================================
# DOCUMENT LIBRARY
# ============================================================

@app.route("/documents")
@login_required
def documents():

    search = safe_text(
        request.args.get("q"),
        255,
    )

    try:

        params = {
            "select": "*",
            "order": "created_at.desc",
        }

        if search:

            # Supabase OR search across title,
            # subject and description.

            escaped = (
                search
                .replace(",", " ")
                .replace("(", " ")
                .replace(")", " ")
            )

            params["or"] = (
                f"title.ilike.*{escaped}*,"
                f"subject.ilike.*{escaped}*,"
                f"description.ilike.*{escaped}*"
            )

        docs = db_select(
            "document_library",
            params,
        )

    except Exception as exc:

        logger.exception(exc)

        docs = []

    rows = ""

    for doc in docs:

        document_id = doc.get("id")

        rows += f"""
<tr>

<td>
{safe_text(doc.get('title'))}
</td>

<td>
{safe_text(doc.get('subject'))}
</td>

<td>
{safe_text(doc.get('course'))}
</td>

<td>
<a class="btn"
href="/document/{document_id}/download">
Download
</a>
</td>

</tr>
"""

    content = f"""
<div class="card">

<h2>Academic Library</h2>

<form method="get">

<input
name="q"
value="{safe_text(search)}"
placeholder="Search documents..."
>

<button type="submit">
Search
</button>

</form>

</div>

<div class="card">

<table>

<tr>
<th>Title</th>
<th>Subject</th>
<th>Course</th>
<th>File</th>
</tr>

{rows}

</table>

</div>
"""

    return page(content, "Document Library")


# ============================================================
# ADMIN UPLOAD DOCUMENT
# ============================================================

@app.route(
    "/admin/document/upload",
    methods=["GET", "POST"],
)
@admin_required
def admin_upload_document():

    if request.method == "POST":

        title = safe_text(
            request.form.get("title"),
            255,
        )

        description = safe_text(
            request.form.get("description"),
            5000,
        )

        document_type = safe_text(
            request.form.get("document_type"),
            100,
        ) or "academic"

        subject = safe_text(
            request.form.get("subject"),
            255,
        )

        course = safe_text(
            request.form.get("course"),
            255,
        )

        class_level = safe_text(
            request.form.get("class_level"),
            255,
        )

        file = request.files.get("file")

        if not title or not file:
            flash("Title and file are required.")
            return redirect(
                url_for("admin_upload_document")
            )

        if not allowed_file(file.filename):
            flash("Unsupported file type.")
            return redirect(
                url_for("admin_upload_document")
            )

        try:

            file_bytes = file.read()

            filename = secure_filename(
                file.filename
            )

            document_id = str(uuid.uuid4())

            path = (
                f"library/"
                f"{document_id}/"
                f"{filename}"
            )

            mime_type = (
                file.content_type
                or "application/octet-stream"
            )

            storage_upload(
                file_bytes,
                path,
                mime_type,
            )

            user = current_user()

            data = {
                "id": document_id,
                "title": title,
                "description": description,
                "document_type": document_type,
                "subject": subject,
                "course": course,
                "class_level": class_level,
                "file_name": filename,
                "file_path": path,
                "file_size": len(file_bytes),
                "mime_type": mime_type,
                "uploaded_by": user.get("id"),
                "uploader_name": user.get("student_name"),
                "uploader_email": user.get("email"),
                "uploader_role": "admin",
                "is_public": True,
                "is_active": True,
                "download_count": 0,
                "view_count": 0,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }

            db_insert(
                "document_library",
                data,
            )

            flash("Document uploaded.")

            return redirect(
                url_for("documents")
            )

        except Exception as exc:

            logger.exception(exc)

            flash(
                "Document upload failed: "
                + str(exc)
            )

    content = """
<div class="card">

<h2>Upload Library Document</h2>

<form
method="post"
enctype="multipart/form-data"
>

<label>Title</label>
<input name="title" required>

<label>Description</label>
<textarea name="description"></textarea>

<label>Document type</label>
<input
name="document_type"
value="academic"
>

<label>Subject</label>
<input name="subject">

<label>Course</label>
<input name="course">

<label>Class level</label>
<input name="class_level">

<label>File</label>
<input
type="file"
name="file"
required
>

<button type="submit">
Upload
</button>

</form>

</div>
"""

    return page(
        content,
        "Upload Document",
    )


# ============================================================
# DOWNLOAD LIBRARY DOCUMENT
# ============================================================

@app.route(
    "/document/<document_id>/download"
)
@login_required
def download_document(document_id):

    document = get_document(
        document_id
    )

    if not document:
        abort(404)

    if document.get("is_active") is False:
        abort(404)

    try:

        file_bytes = storage_download(
            document.get("file_path")
        )

        current_count = (
            document.get("download_count")
            or 0
        )

        db_update(
            "document_library",
            {
                "id": f"eq.{document_id}"
            },
            {
                "download_count": current_count + 1,
                "updated_at": now_iso(),
            },
        )

        db_insert(
            "document_access_logs",
            {
                "id": str(uuid.uuid4()),
                "document_id": document_id,
                "user_id": current_user().get("id"),
                "action": "download",
                "created_at": now_iso(),
            },
        )

        filename = (
            document.get("file_name")
            or "document"
        )

        return send_file(
            io.BytesIO(file_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype=document.get(
                "mime_type",
                "application/octet-stream",
            ),
        )

    except Exception as exc:

        logger.exception(exc)

        abort(404)


# ============================================================
# API: AI ASSIGNMENT ANSWER
# ============================================================

@app.route(
    "/api/ai/answer",
    methods=["POST"],
)
@login_required
def api_ai_answer():

    data = request.get_json(
        silent=True
    ) or {}

    question = safe_text(
        data.get("question"),
        10000,
    )

    subject = safe_text(
        data.get("subject"),
        255,
    )

    course = safe_text(
        data.get("course"),
        255,
    )

    class_level = safe_text(
        data.get("class_level"),
        255,
    )

    if not question:
        return jsonify({
            "ok": False,
            "error": "Question is required.",
        }), 400

    try:

        answer = ai_answer(
            question,
            subject,
            course,
            class_level,
        )

        return jsonify({
            "ok": True,
            "answer": answer,
        })

    except Exception as exc:

        logger.exception(exc)

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ============================================================
# API: AI RESEARCH
# ============================================================

@app.route(
    "/api/ai/research",
    methods=["POST"],
)
@login_required
def api_ai_research():

    data = request.get_json(
        silent=True
    ) or {}

    question = safe_text(
        data.get("question"),
        10000,
    )

    if not question:
        return jsonify({
            "ok": False,
            "error": "Question is required.",
        }), 400

    try:

        answer = ai_research(
            question
        )

        return jsonify({
            "ok": True,
            "answer": answer,
        })

    except Exception as exc:

        logger.exception(exc)

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    missing = configuration_error()

    if missing:

        return jsonify({
            "status": "error",
            "message": "Missing environment variables.",
            "missing": missing,
        }), 500

    try:

        response = supabase_request(
            "GET",
            "assignments",
            params={
                "select": "id",
                "limit": "1",
            },
            timeout=10,
        )

        if not response.ok:

            return jsonify({
                "status": "error",
                "supabase": response.text,
            }), 500

        return jsonify({
            "status": "ok",
            "app": APP_NAME,
            "supabase": "connected",
            "ai": bool(OPENAI_API_KEY),
        })

    except Exception as exc:

        return jsonify({
            "status": "error",
            "message": str(exc),
        }), 500


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    return page(
        """
<div class="card">

<h2>File too large</h2>

<p>
The maximum upload size is 20 MB.
</p>

<a class="btn"
href="/">
Return Home
</a>

</div>
""",
        "File Too Large",
    ), 413


@app.errorhandler(404)
def not_found(error):

    return page(
        """
<div class="card">

<h2>Page not found</h2>

<a class="btn"
href="/">
Return Home
</a>

</div>
""",
        "Not Found",
    ), 404


@app.errorhandler(500)
def internal_error(error):

    return page(
        """
<div class="card">

<h2>Server error</h2>

<p>
Something went wrong on the server.
Check the Render logs for details.
</p>

<a class="btn"
href="/">
Return Home
</a>

</div>
""",
        "Server Error",
    ), 500


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000",
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
