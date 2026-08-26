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
    Flask, request, redirect, url_for, session,
    render_template_string, flash, send_from_directory
)

# ============================================================
# KOJA AFRICA
# STUDENT + ADMIN PORTAL
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "koja-africa-secret-change-this-2026"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "koja_data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")

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
)

# ============================================================
# JSON DATABASE
# ============================================================

def ensure_file(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)


ensure_file(USERS_FILE, [])
ensure_file(QUESTIONS_FILE, [])


def read_json(path):
    try:
        with LOCK:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return []


def write_json(path, data):
    with LOCK:
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


def find_user(email):

    email = email.strip().lower()

    for user in users():

        if user.get("email", "").lower() == email:
            return user

    return None


def save_users(data):
    write_json(USERS_FILE, data)


def create_admin():

    data = users()

    # Remove duplicate admin records
    found = None

    for user in data:

        if user.get("email", "").lower() == ADMIN_EMAIL:

            found = user
            break

    if found:

        found["role"] = "admin"

        # Keep environment password authoritative
        found["password"] = hash_password(
            ADMIN_PASSWORD
        )

        found["name"] = "KOJA Administrator"

        save_users(data)

        return

    admin = {
        "id": str(uuid.uuid4()),
        "name": "KOJA Administrator",
        "email": ADMIN_EMAIL,
        "password": hash_password(
            ADMIN_PASSWORD
        ),
        "role": "admin",
        "created_at": datetime.utcnow().isoformat()
    }

    data.append(admin)

    save_users(data)


create_admin()


# ============================================================
# SUPABASE
# ============================================================

def supabase_configured():

    return bool(
        SUPABASE_URL and
        SUPABASE_SERVICE_KEY
    )


def supabase_headers():

    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization":
            "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json"
    }


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

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not session.get("user_id"):
            return redirect(
                url_for("login")
            )

        # IMPORTANT:
        # Admin is identified by email.
        # This prevents an incorrect role value
        # from blocking the real administrator.

        email = session.get(
            "email",
            ""
        ).lower()

        if email != ADMIN_EMAIL:

            flash(
                "Administrator access required.",
                "error"
            )

            return redirect(
                url_for("student_dashboard")
            )

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# HTML
# ============================================================

HTML = """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>{{ title }} - KOJA AFRICA</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #f4f7fb;
    font-family: Arial, sans-serif;
    color: #172033;
}

nav {
    background: #101828;
    color: white;
    padding: 15px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}

.logo {
    font-size: 23px;
    font-weight: bold;
}

.k {color:#2196f3;}
.o {color:#22c55e;}
.j {color:#ef4444;}
.a {color:#2563eb;}

nav a {
    color: white;
    text-decoration: none;
    margin: 4px;
    padding: 8px 12px;
    border-radius: 7px;
}

nav a:hover {
    background: #26354d;
}

.container {
    width: 94%;
    max-width: 1100px;
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
    padding: 30px;
    border-radius: 15px;
    margin-bottom: 20px;
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
}

.stat {
    background: #eef4ff;
    padding: 20px;
    border-radius: 12px;
}

input,
textarea {
    width: 100%;
    padding: 12px;
    margin-top: 7px;
    margin-bottom: 15px;
    border: 1px solid #d0d5dd;
    border-radius: 8px;
    font-size: 15px;
}

textarea {
    min-height: 160px;
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

.green {
    background: #16a34a;
}

.red {
    background: #dc2626;
}

.dark {
    background: #111827;
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

.question {
    white-space: pre-wrap;
    line-height: 1.6;
}

.answer {
    white-space: pre-wrap;
    background: #f0fdf4;
    border-left: 4px solid #16a34a;
    padding: 15px;
    border-radius: 7px;
    line-height: 1.6;
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

table {
    width: 100%;
    border-collapse: collapse;
}

th,
td {
    padding: 12px;
    border-bottom: 1px solid #eee;
    text-align: left;
}

th {
    background: #f8fafc;
}

.auth {
    max-width: 500px;
    margin: 50px auto;
}

.muted {
    color: #667085;
}

pre {
    white-space: pre-wrap;
    word-break: break-word;
}

@media(max-width:650px) {

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
    <span class="k">k</span>
    <span class="o">o</span>
    <span class="j">j</span>
    <span class="a">a</span>
    AFRICA
</div>

{% if session.get("user_id") %}

<div>

{% if session.get("email","").lower()
      == admin_email.lower() %}

<a href="/admin">Admin</a>

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


def render_page(title, content):

    return render_template_string(
        HTML,
        title=title,
        content=content,
        admin_email=ADMIN_EMAIL
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

    if (
        session.get("email", "").lower()
        == ADMIN_EMAIL.lower()
    ):

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

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        # ----------------------------------------------------
        # ADMIN LOGIN
        # ----------------------------------------------------

        if (
            email == ADMIN_EMAIL and
            secrets.compare_digest(
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

        # ----------------------------------------------------
        # STUDENT LOGIN
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
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password": hash_password(password),
            "role": "student",
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

    # Admin cannot use student dashboard
    if (
        session.get("email", "").lower()
        == ADMIN_EMAIL.lower()
    ):

        return redirect(
            url_for("admin_dashboard")
        )

    all_questions = read_json(
        QUESTIONS_FILE
    )

    questions = [
        q for q in all_questions
        if q.get("student_id")
        == session.get("user_id")
    ]

    questions.sort(
        key=lambda q:
        q.get("created_at", ""),
        reverse=True
    )

    cards = ""

    for q in questions:

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
{answer}
</div>
"""

        else:

            answer_html = """
<p class="muted">
Waiting for administrator answer.
</p>
"""

        attachment = q.get(
            "attachment"
        )

        attachment_html = ""

        if attachment:

            attachment_html = f"""
<p>
<strong>Attachment:</strong>
{attachment.get("original_name")}
</p>

<a class="btn"
href="/student/file/{q["id"]}"
target="_blank">
Open Attachment
</a>
"""

        cards += f"""

<div class="card">

<h2>
{q.get("subject","Question")}
</h2>

<span class="badge {badge}">
{status}
</span>

<p class="muted">
Submitted:
{q.get("created_at","")}
</p>

{attachment_html}

<h3>Your Question</h3>

<div class="question">
{q.get("question","")}
</div>

<h3>Administrator Answer</h3>

{answer_html}

</div>

"""

    if not cards:

        cards = """

<div class="card">

<h2>No questions yet.</h2>

<p>
You have not submitted any questions.
</p>

<a class="btn"
href="/student/ask">
Ask Your First Question
</a>

</div>

"""

    content = f"""

<div class="hero">

<h1>
Welcome, {session.get("name")}
</h1>

<p>
Ask academic questions and receive answers
from the KOJA administrator.
</p>

<a class="btn"
href="/student/ask">
Ask Question
</a>

</div>

<div class="grid">

<div class="stat">

<h2>{len(questions)}</h2>

<p>Total Questions</p>

</div>

<div class="stat">

<h2>
{
sum(
1 for q in questions
if q.get("status") == "Answered"
)
}
</h2>

<p>Answered</p>

</div>

<div class="stat">

<h2>
{
sum(
1 for q in questions
if q.get("status") == "Pending"
)
}
</h2>

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
# ASK QUESTION
# ============================================================

@app.route(
    "/student/ask",
    methods=["GET", "POST"]
)
@login_required
def ask_question():

    if (
        session.get("email", "").lower()
        == ADMIN_EMAIL.lower()
    ):

        return redirect(
            url_for("admin_dashboard")
        )

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        question = request.form.get(
            "question",
            ""
        ).strip()

        file = request.files.get(
            "attachment"
        )

        if len(subject) < 2:

            flash(
                "Enter a subject.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        if len(question) < 3:

            flash(
                "Enter your question.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        attachment = None

        if file and file.filename:

            original = file.filename

            allowed = {
                "pdf",
                "png",
                "jpg",
                "jpeg",
                "doc",
                "docx",
                "txt",
                "ppt",
                "pptx",
                "xls",
                "xlsx"
            }

            if "." not in original:

                flash(
                    "Invalid file.",
                    "error"
                )

                return redirect(
                    url_for("ask_question")
                )

            extension = original.rsplit(
                ".",
                1
            )[1].lower()

            if extension not in allowed:

                flash(
                    "Unsupported file type.",
                    "error"
                )

                return redirect(
                    url_for("ask_question")
                )

            stored = (
                str(uuid.uuid4())
                + "."
                + extension
            )

            file.save(
                os.path.join(
                    UPLOAD_DIR,
                    stored
                )
            )

            attachment = {
                "original_name": original,
                "stored_name": stored
            }

        item = {

            "id": str(uuid.uuid4()),

            "student_id":
                session.get("user_id"),

            "student_name":
                session.get("name"),

            "student_email":
                session.get("email"),

            "subject": subject,

            "question": question,

            "attachment": attachment,

            "status": "Pending",

            "answer": "",

            "answered_at": None,

            "answered_by": None,

            "created_at":
                datetime.utcnow().isoformat()
        }

        data = read_json(
            QUESTIONS_FILE
        )

        data.append(item)

        write_json(
            QUESTIONS_FILE,
            data
        )

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
You can type your question and upload
an assignment or supporting document.
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
placeholder="Write your question..."
required
></textarea>

<label>
Attachment
</label>

<input
type="file"
name="attachment"
>

<button>
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

    questions = read_json(
        QUESTIONS_FILE
    )

    questions.sort(
        key=lambda q:
        q.get("created_at", ""),
        reverse=True
    )

    total = len(questions)

    pending = sum(
        1 for q in questions
        if q.get("status") == "Pending"
    )

    answered = sum(
        1 for q in questions
        if q.get("status") == "Answered"
    )

    rows = ""

    for q in questions:

        status = q.get(
            "status",
            "Pending"
        )

        badge = (
            "answered"
            if status == "Answered"
            else "pending"
        )

        rows += f"""

<tr>

<td>
<strong>
{q.get("student_name","")}
</strong>

<br>

<small>
{q.get("student_email","")}
</small>

</td>

<td>
{q.get("subject","")}
</td>

<td>
{q.get("question","")[:120]}
</td>

<td>
<span class="badge {badge}">
{status}
</span>
</td>

<td>

<a class="btn"
href="/admin/question/{q.get("id")}">
Open
</a>

</td>

</tr>

"""

    if not rows:

        rows = """
<tr>
<td colspan="5">
No student questions yet.
</td>
</tr>
"""

    content = f"""

<div class="hero">

<h1>KOJA Administrator</h1>

<p>
Read student questions, open attachments
and send answers.
</p>

</div>

<div class="grid">

<div class="stat">

<h2>{total}</h2>

<p>Total Questions</p>

</div>

<div class="stat">

<h2>{pending}</h2>

<p>Pending</p>

</div>

<div class="stat">

<h2>{answered}</h2>

<p>Answered</p>

</div>

</div>

<div class="card">

<h2>Student Questions</h2>

<table>

<thead>

<tr>

<th>Student</th>
<th>Subject</th>
<th>Question</th>
<th>Status</th>
<th>Action</th>

</tr>

</thead>

<tbody>

{rows}

</tbody>

</table>

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

    data = read_json(
        QUESTIONS_FILE
    )

    question = None

    for item in data:

        if item.get("id") == question_id:

            question = item
            break

    if not question:

        flash(
            "Question not found.",
            "error"
        )

        return redirect(
            url_for("admin_dashboard")
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

        question["answer"] = answer

        question["status"] = "Answered"

        question["answered_at"] = (
            datetime.utcnow().isoformat()
        )

        question["answered_by"] = (
            session.get("email")
        )

        write_json(
            QUESTIONS_FILE,
            data
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

    attachment = question.get(
        "attachment"
    )

    attachment_html = ""

    if attachment:

        attachment_html = f"""

<div class="card">

<h3>Student Attachment</h3>

<p>
{attachment.get("original_name")}
</p>

<a class="btn"
href="/admin/file/{attachment.get("stored_name")}"
target="_blank">
Open Attachment
</a>

</div>

"""

    content = f"""

<div class="card">

<a href="/admin">
← Back to Admin Dashboard
</a>

<h1>
{question.get("subject","")}
</h1>

<p>
<strong>Student:</strong>
{question.get("student_name","")}
</p>

<p>
<strong>Email:</strong>
{question.get("student_email","")}
</p>

<p>
<strong>Status:</strong>
{question.get("status","")}
</p>

<hr>

<h2>Student Question</h2>

<div class="question">
{question.get("question","")}
</div>

</div>

{attachment_html}

<div class="card">

<h2>Answer Student</h2>

<form method="post">

<textarea
name="answer"
required
placeholder="Write your academic answer..."
>{question.get("answer","")}</textarea>

<button class="green">
Send Answer to Student
</button>

</form>

</div>

"""

    return render_page(
        "Answer Question",
        content
    )


# ============================================================
# ADMIN FILE
# ============================================================

@app.route(
    "/admin/file/<filename>"
)
@admin_required
def admin_file(filename):

    return send_from_directory(
        UPLOAD_DIR,
        filename
    )


# ============================================================
# STUDENT FILE
# ============================================================

@app.route(
    "/student/file/<question_id>"
)
@login_required
def student_file(question_id):

    data = read_json(
        QUESTIONS_FILE
    )

    question = next(
        (
            q for q in data
            if q.get("id") == question_id
        ),
        None
    )

    if not question:

        return "File not found", 404

    if question.get(
        "student_id"
    ) != session.get("user_id"):

        return "Access denied", 403

    attachment = question.get(
        "attachment"
    )

    if not attachment:

        return "No attachment", 404

    return send_from_directory(
        UPLOAD_DIR,
        attachment["stored_name"]
    )


# ============================================================
# ADMIN CONFIGURATION
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

<h1>System Configuration</h1>

<p>
Administrator-only configuration.
</p>

</div>

<div class="card">

<h2>Supabase</h2>

<p>

Configured:

<span class="badge {
"answered" if configured else "pending"
}">

{
"YES"
if configured
else "NO"
}

</span>

</p>

<p>

Connection:

<span class="badge {
"answered" if connected else "pending"
}">

{
"WORKING"
if connected
else "UNAVAILABLE"
}

</span>

</p>

<hr>

<h3>Supabase URL</h3>

<pre>
{
SUPABASE_URL
if SUPABASE_URL
else "Not configured"
}
</pre>

<h3>Service Key</h3>

<pre>
{
"Configured — hidden"
if SUPABASE_SERVICE_KEY
else "Not configured"
}
</pre>

<h3>Storage Bucket</h3>

<pre>
{STORAGE_BUCKET}
</pre>

</div>

<div class="card">

<h2>Fallback Mode</h2>

<p>
KOJA continues operating using local server
storage when Supabase is unavailable.
</p>

<p class="muted">
For permanent production storage on Render,
Supabase should eventually be configured.
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
# ERRORS
# ============================================================

@app.errorhandler(413)
def too_large(error):

    flash(
        "Maximum file size is 10 MB.",
        "error"
    )

    return redirect(
        url_for("ask_question")
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

<a class="btn"
href="/">
Go Home
</a>

</div>

"""
    ), 404


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
    print("=" * 60)
    print("ADMIN EMAIL:", ADMIN_EMAIL)
    print("SUPABASE:", supabase_configured())
    print("FALLBACK: ENABLED")
    print("PORT:", port)
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
