# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# STUDENT + ADMIN ACADEMIC PORTAL
#
# Features:
#   - Student registration/login
#   - Student dashboard as default
#   - Ask questions
#   - Upload files
#   - Student question history
#   - Administrator dashboard
#   - Admin reads questions
#   - Admin views attachments
#   - Admin answers questions
#   - Student receives answers
#   - Admin-only configuration
#   - Supabase REST API support
#   - Automatic local fallback if Supabase is unavailable
#
# Run:
#   pip install flask requests
#   python app.py
#
# ============================================================

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
    send_from_directory,
    flash,
)

# ============================================================
# APP CONFIGURATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "KOJA_CHANGE_THIS_SECRET_KEY_2026"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "koja_data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")

DATA_LOCK = threading.Lock()

# ============================================================
# ENVIRONMENT
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")

SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY", ""
).strip()

SUPABASE_PUBLISHABLE_KEY = os.environ.get(
    "SUPABASE_PUBLISHABLE_KEY", ""
).strip()

STORAGE_BUCKET = os.environ.get(
    "KOJA_STORAGE_BUCKET",
    "koja-files"
).strip()

ADMIN_EMAIL = os.environ.get(
    "KOJA_ADMIN_EMAIL",
    "admin@koja.africa"
).strip().lower()

ADMIN_PASSWORD = os.environ.get(
    "KOJA_ADMIN_PASSWORD",
    "ChangeMe123!"
)

# ============================================================
# FALLBACK DATA
# ============================================================

def ensure_json_file(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)


ensure_json_file(USERS_FILE, [])
ensure_json_file(QUESTIONS_FILE, [])


def read_json(path, default):
    try:
        with DATA_LOCK:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    with DATA_LOCK:
        temporary = path + ".tmp"

        with open(
            temporary,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

        os.replace(temporary, path)


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
        salt, digest = stored.split("$", 1)

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
# USER MANAGEMENT
# ============================================================

def get_users():
    return read_json(USERS_FILE, [])


def save_users(users):
    write_json(USERS_FILE, users)


def find_user(email):
    email = email.lower().strip()

    for user in get_users():
        if user.get("email", "").lower() == email:
            return user

    return None


def create_user(name, email, password):
    users = get_users()

    email = email.lower().strip()

    if find_user(email):
        return False, "An account with that email already exists."

    user = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "email": email,
        "password": hash_password(password),
        "role": "student",
        "created_at": datetime.utcnow().isoformat()
    }

    users.append(user)

    save_users(users)

    return True, "Account created successfully."


# ============================================================
# QUESTION STORAGE
# ============================================================

def get_questions():
    return read_json(QUESTIONS_FILE, [])


def save_questions(questions):
    write_json(QUESTIONS_FILE, questions)


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
        "Authorization": "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
    }


def supabase_request(
    method,
    endpoint,
    data=None,
    timeout=8
):
    if not supabase_configured():
        return None

    try:
        response = requests.request(
            method,
            SUPABASE_URL + endpoint,
            headers=supabase_headers(),
            json=data,
            timeout=timeout
        )

        if response.status_code >= 400:
            return None

        if not response.text:
            return {}

        return response.json()

    except Exception:
        return None


def test_supabase():
    if not supabase_configured():
        return False, "Supabase is not configured."

    try:
        response = requests.get(
            SUPABASE_URL + "/rest/v1/",
            headers=supabase_headers(),
            timeout=5
        )

        if response.status_code < 400:
            return True, "Supabase connection is working."

        return False, (
            "Supabase returned HTTP "
            + str(response.status_code)
        )

    except Exception as e:
        return False, str(e)


# ============================================================
# OPTIONAL SUPABASE TABLE SUPPORT
# ============================================================

def supabase_insert(table, row):
    return supabase_request(
        "POST",
        "/rest/v1/" + table,
        row
    )


def supabase_update(table, filters, row):
    endpoint = "/rest/v1/" + table

    if filters:
        endpoint += "?" + "&".join(
            f"{k}=eq.{v}"
            for k, v in filters.items()
        )

    return supabase_request(
        "PATCH",
        endpoint,
        row
    )


def sync_user_to_supabase(user):
    if not supabase_configured():
        return

    try:
        row = {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "created_at": user["created_at"],
        }

        supabase_insert("koja_users", row)

    except Exception:
        pass


def sync_question_to_supabase(question):
    if not supabase_configured():
        return

    try:
        row = {
            "id": question["id"],
            "student_id": question["student_id"],
            "student_name": question["student_name"],
            "student_email": question["student_email"],
            "subject": question["subject"],
            "question": question["question"],
            "attachment": question.get("attachment"),
            "status": question["status"],
            "answer": question.get("answer"),
            "created_at": question["created_at"],
            "answered_at": question.get("answered_at"),
        }

        supabase_insert(
            "koja_questions",
            row
        )

    except Exception:
        pass


# ============================================================
# AUTHENTICATION
# ============================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        if session.get("role") != "admin":
            flash(
                "Administrator access required.",
                "error"
            )

            return redirect(
                url_for("student_dashboard")
            )

        return view(*args, **kwargs)

    return wrapped


# ============================================================
# ADMIN AUTO LOGIN ACCOUNT
# ============================================================

def ensure_admin():
    users = get_users()

    for user in users:
        if (
            user.get("email") == ADMIN_EMAIL
            and user.get("role") == "admin"
        ):
            return

    admin = {
        "id": str(uuid.uuid4()),
        "name": "KOJA Administrator",
        "email": ADMIN_EMAIL,
        "password": hash_password(ADMIN_PASSWORD),
        "role": "admin",
        "created_at": datetime.utcnow().isoformat()
    }

    users.append(admin)

    save_users(users)


ensure_admin()


# ============================================================
# FILE UPLOAD
# ============================================================

ALLOWED_EXTENSIONS = {
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


def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    return extension in ALLOWED_EXTENSIONS


def save_uploaded_file(file):
    if not file:
        return None

    original = file.filename or ""

    if not allowed_file(original):
        return None

    extension = original.rsplit(".", 1)[1].lower()

    generated = (
        str(uuid.uuid4())
        + "."
        + extension
    )

    destination = os.path.join(
        UPLOAD_DIR,
        generated
    )

    file.save(destination)

    return {
        "original_name": original,
        "stored_name": generated
    }


# ============================================================
# COMMON HTML
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
    font-family:
        Arial,
        Helvetica,
        sans-serif;
    background: #f4f7fb;
    color: #172033;
}

.navbar {
    background: #101828;
    color: white;
    padding: 15px 22px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 15px;
    flex-wrap: wrap;
}

.logo {
    font-size: 23px;
    font-weight: 800;
}

.logo span:nth-child(1) {
    color: #2196f3;
}

.logo span:nth-child(2) {
    color: #22c55e;
}

.logo span:nth-child(3) {
    color: #ef4444;
}

.logo span:nth-child(4) {
    color: #2563eb;
}

.nav-links {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.nav-links a {
    color: white;
    text-decoration: none;
    padding: 8px 11px;
    border-radius: 7px;
}

.nav-links a:hover {
    background: #26354d;
}

.container {
    width: min(1100px, 94%);
    margin: 25px auto;
}

.card {
    background: white;
    border-radius: 14px;
    padding: 22px;
    margin-bottom: 20px;
    box-shadow:
        0 5px 22px rgba(0,0,0,.06);
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(210px, 1fr));
    gap: 17px;
}

.stat {
    padding: 22px;
    border-radius: 13px;
    background: #eef4ff;
}

.stat h2 {
    margin: 0 0 5px;
}

input,
textarea,
select {
    width: 100%;
    padding: 12px;
    border: 1px solid #d0d5dd;
    border-radius: 8px;
    margin-top: 7px;
    margin-bottom: 15px;
    font-size: 15px;
}

textarea {
    min-height: 150px;
    resize: vertical;
}

button,
.btn {
    border: none;
    background: #2563eb;
    color: white;
    padding: 11px 17px;
    border-radius: 8px;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
    font-size: 14px;
}

button:hover,
.btn:hover {
    opacity: .9;
}

.btn-green {
    background: #16a34a;
}

.btn-red {
    background: #dc2626;
}

.btn-dark {
    background: #111827;
}

.badge {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 20px;
    font-size: 12px;
    background: #e5e7eb;
}

.badge-green {
    background: #dcfce7;
    color: #166534;
}

.badge-orange {
    background: #ffedd5;
    color: #9a3412;
}

.badge-blue {
    background: #dbeafe;
    color: #1e40af;
}

.alert {
    padding: 12px 15px;
    border-radius: 8px;
    background: #e0f2fe;
    margin-bottom: 15px;
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
    padding: 11px;
    text-align: left;
    border-bottom: 1px solid #eaecf0;
    vertical-align: top;
}

th {
    background: #f8fafc;
}

.question {
    white-space: pre-wrap;
    line-height: 1.65;
}

.answer {
    background: #f0fdf4;
    border-left: 4px solid #16a34a;
    padding: 17px;
    border-radius: 8px;
    white-space: pre-wrap;
    line-height: 1.65;
}

.muted {
    color: #667085;
}

.auth {
    max-width: 500px;
    margin: 60px auto;
}

.hero {
    padding: 30px;
    background: linear-gradient(
        135deg,
        #101828,
        #1d4ed8
    );
    color: white;
    border-radius: 16px;
    margin-bottom: 22px;
}

.small {
    font-size: 13px;
}

pre {
    white-space: pre-wrap;
    word-break: break-word;
}

@media(max-width: 650px) {

    table {
        display: block;
        overflow-x: auto;
    }

    .container {
        width: 96%;
    }

}

</style>

</head>

<body>

<div class="navbar">

    <div class="logo">
        <span>k</span><span>o</span><span>j</span><span>a</span>
        AFRICA
    </div>

    {% if session.get("user_id") %}

        <div class="nav-links">

        {% if session.get("role") == "admin" %}

            <a href="{{ url_for('admin_dashboard') }}">
                Admin
            </a>

            <a href="{{ url_for('admin_config') }}">
                Configuration
            </a>

        {% else %}

            <a href="{{ url_for('student_dashboard') }}">
                Dashboard
            </a>

            <a href="{{ url_for('ask_question') }}">
                Ask Question
            </a>

        {% endif %}

            <a href="{{ url_for('logout') }}">
                Logout
            </a>

        </div>

    {% endif %}

</div>

<div class="container">

{% with messages = get_flashed_messages(with_categories=true) %}

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
def index():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))

    return redirect(url_for("student_dashboard"))


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

        user = find_user(email)

        if not user:
            flash(
                "Invalid email or password.",
                "error"
            )

            return redirect(url_for("login"))

        if not verify_password(
            password,
            user.get("password", "")
        ):
            flash(
                "Invalid email or password.",
                "error"
            )

            return redirect(url_for("login"))

        session.clear()

        session["user_id"] = user["id"]
        session["email"] = user["email"]
        session["name"] = user["name"]
        session["role"] = user["role"]

        if user["role"] == "admin":
            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("student_dashboard")
        )

    content = """
    <div class="auth card">

        <h1>KOJA AFRICA</h1>

        <p class="muted">
            Assignment Questions • Academic Answers
        </p>

        <form method="post">

            <label>Email</label>
            <input
                type="email"
                name="email"
                required
                autocomplete="email"
            >

            <label>Password</label>
            <input
                type="password"
                name="password"
                required
                autocomplete="current-password"
            >

            <button type="submit">
                Login
            </button>

        </form>

        <hr>

        <p>
            New student?
            <a href="/register">Create an account</a>
        </p>

    </div>
    """

    return page("Login", content)


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
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

        if len(password) < 6:
            flash(
                "Password must be at least 6 characters.",
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

        ok, message = create_user(
            name,
            email,
            password
        )

        if not ok:
            flash(message, "error")

            return redirect(
                url_for("register")
            )

        user = find_user(email)

        if user:
            sync_user_to_supabase(user)

        flash(
            "Account created. You can now login.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    content = """
    <div class="auth card">

        <h1>Create Student Account</h1>

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
                Register
            </button>

        </form>

        <p>
            Already registered?
            <a href="/login">Login</a>
        </p>

    </div>
    """

    return page("Register", content)


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

    if session.get("role") == "admin":
        return redirect(
            url_for("admin_dashboard")
        )

    questions = [
        q for q in get_questions()
        if q.get("student_id") == session["user_id"]
    ]

    questions.sort(
        key=lambda x: x.get("created_at", ""),
        reverse=True
    )

    rows = ""

    for q in questions:

        status = q.get(
            "status",
            "Pending"
        )

        if status == "Answered":
            badge = "badge-green"
        elif status == "Pending":
            badge = "badge-orange"
        else:
            badge = "badge-blue"

        answer = q.get("answer")

        if answer:
            answer_html = f"""
            <div class="answer">
                {answer}
            </div>
            """
        else:
            answer_html = """
            <p class="muted">
                Waiting for administrator response.
            </p>
            """

        attachment = q.get("attachment")

        attachment_html = ""

        if attachment:
            attachment_html = f"""
            <p>
                <strong>Attachment:</strong>
                {attachment.get("original_name")}
            </p>
            """

        rows += f"""
        <div class="card">

            <h3>
                {q.get("subject", "Question")}
            </h3>

            <p>
                <span class="badge {badge}">
                    {status}
                </span>
            </p>

            <p class="small muted">
                Submitted:
                {q.get("created_at", "")}
            </p>

            {attachment_html}

            <h4>Your Question</h4>

            <div class="question">
                {q.get("question", "")}
            </div>

            <h4>Administrator Answer</h4>

            {answer_html}

        </div>
        """

    if not rows:
        rows = """
        <div class="card">
            <h3>No questions yet.</h3>

            <p>
                Ask your first academic question and
                the administrator will respond.
            </p>

            <a class="btn"
               href="/student/ask">
                Ask a Question
            </a>
        </div>
        """

    content = f"""

    <div class="hero">

        <h1>
            Welcome, {session.get("name", "Student")}
        </h1>

        <p>
            Ask questions, upload assignments and
            receive academic answers.
        </p>

        <a class="btn"
           href="/student/ask">
            Ask a Question
        </a>

    </div>

    <div class="grid">

        <div class="stat">
            <h2>{len(questions)}</h2>
            <p>Total Questions</p>
        </div>

        <div class="stat">
            <h2>
                {sum(
                    1 for q in questions
                    if q.get("status") == "Answered"
                )}
            </h2>
            <p>Answered</p>
        </div>

        <div class="stat">
            <h2>
                {sum(
                    1 for q in questions
                    if q.get("status") == "Pending"
                )}
            </h2>
            <p>Pending</p>
        </div>

    </div>

    <h2>My Questions</h2>

    {rows}

    """

    return page(
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

    if session.get("role") == "admin":
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

        attachment_file = request.files.get(
            "attachment"
        )

        if len(subject) < 2:
            flash(
                "Please enter a subject.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        if len(question_text) < 3:
            flash(
                "Please enter your question.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )

        attachment = None

        if attachment_file and attachment_file.filename:

            attachment = save_uploaded_file(
                attachment_file
            )

            if not attachment:
                flash(
                    "Unsupported attachment type.",
                    "error"
                )

                return redirect(
                    url_for("ask_question")
                )

        question = {
            "id": str(uuid.uuid4()),
            "student_id": session["user_id"],
            "student_name": session["name"],
            "student_email": session["email"],
            "subject": subject,
            "question": question_text,
            "attachment": attachment,
            "status": "Pending",
            "answer": "",
            "answered_at": None,
            "answered_by": None,
            "created_at": datetime.utcnow().isoformat()
        }

        questions = get_questions()

        questions.append(question)

        save_questions(questions)

        sync_question_to_supabase(
            question
        )

        flash(
            "Your question has been submitted.",
            "success"
        )

        return redirect(
            url_for("student_dashboard")
        )

    content = """
    <div class="card">

        <h1>Ask a Question</h1>

        <p class="muted">
            Submit your academic question below.
            You may attach an assignment, PDF,
            image or other supported document.
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

            <label>Your Question</label>

            <textarea
                name="question"
                placeholder="Type your question here..."
                required
            ></textarea>

            <label>
                Attachment
                <span class="small muted">
                    (optional, maximum 10 MB)
                </span>
            </label>

            <input
                type="file"
                name="attachment"
                accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.txt,.ppt,.pptx,.xls,.xlsx"
            >

            <button type="submit">
                Submit Question
            </button>

        </form>

    </div>
    """

    return page(
        "Ask Question",
        content
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    questions = get_questions()

    questions.sort(
        key=lambda x: x.get("created_at", ""),
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

    table = ""

    for q in questions:

        status = q.get(
            "status",
            "Pending"
        )

        if status == "Answered":
            badge = "badge-green"
        else:
            badge = "badge-orange"

        table += f"""
        <tr>

            <td>
                <strong>
                    {q.get("student_name", "")}
                </strong>

                <br>

                <span class="small muted">
                    {q.get("student_email", "")}
                </span>
            </td>

            <td>
                {q.get("subject", "")}
            </td>

            <td>
                {q.get("question", "")[:100]}
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

    content = f"""

    <div class="hero">

        <h1>Administrator Dashboard</h1>

        <p>
            Manage student questions and academic answers.
        </p>

    </div>

    <div class="grid">

        <div class="stat">
            <h2>{total}</h2>
            <p>Total Questions</p>
        </div>

        <div class="stat">
            <h2>{pending}</h2>
            <p>Waiting for Answer</p>
        </div>

        <div class="stat">
            <h2>{answered}</h2>
            <p>Answered</p>
        </div>

        <div class="stat">
            <h2>
                <a href="/admin/config">
                    System
                </a>
            </h2>
            <p>Configuration</p>
        </div>

    </div>

    <div class="card">

        <h2>Student Questions</h2>

        <div style="overflow-x:auto">

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
                {table if table else
                '<tr><td colspan="5">No questions yet.</td></tr>'}
            </tbody>

        </table>

        </div>

    </div>

    """

    return page(
        "Admin Dashboard",
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

    questions = get_questions()

    question = None

    for q in questions:
        if q.get("id") == question_id:
            question = q
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
                "Please write an answer.",
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
        question["answered_by"] = session.get(
            "email"
        )

        save_questions(questions)

        if supabase_configured():

            supabase_update(
                "koja_questions",
                {"id": question_id},
                {
                    "answer": answer,
                    "status": "Answered",
                    "answered_at": question["answered_at"],
                    "answered_by": question["answered_by"]
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

            <a
                class="btn"
                href="/admin/file/{attachment.get("stored_name")}"
                target="_blank"
            >
                Open Attachment
            </a>

        </div>
        """

    existing_answer = question.get(
        "answer",
        ""
    )

    content = f"""

    <div class="card">

        <a href="/admin">
            ← Back to Admin Dashboard
        </a>

        <h1>
            {question.get("subject", "")}
        </h1>

        <p>
            <strong>Student:</strong>
            {question.get("student_name", "")}
        </p>

        <p>
            <strong>Email:</strong>
            {question.get("student_email", "")}
        </p>

        <p>
            <strong>Status:</strong>
            {question.get("status", "")}
        </p>

        <p class="muted small">
            Submitted:
            {question.get("created_at", "")}
        </p>

        <hr>

        <h2>Student Question</h2>

        <div class="question">
            {question.get("question", "")}
        </div>

    </div>

    {attachment_html}

    <div class="card">

        <h2>
            Answer Student
        </h2>

        <form method="post">

            <textarea
                name="answer"
                placeholder="Write the academic answer..."
                required
            >{existing_answer}</textarea>

            <button
                type="submit"
                class="btn-green"
            >
                Send Answer to Student
            </button>

        </form>

    </div>

    """

    return page(
        "Answer Question",
        content
    )


# ============================================================
# ADMIN FILE ACCESS
# ============================================================

@app.route(
    "/admin/file/<filename>"
)
@admin_required
def admin_file(filename):

    return send_from_directory(
        UPLOAD_DIR,
        filename,
        as_attachment=False
    )


# ============================================================
# STUDENT FILE ACCESS
# ============================================================

@app.route(
    "/student/file/<question_id>"
)
@login_required
def student_file(question_id):

    questions = get_questions()

    question = next(
        (
            q for q in questions
            if q.get("id") == question_id
        ),
        None
    )

    if not question:
        return "File not found", 404

    if (
        question.get("student_id")
        != session.get("user_id")
    ):
        return "Access denied", 403

    attachment = question.get(
        "attachment"
    )

    if not attachment:
        return "No attachment", 404

    return send_from_directory(
        UPLOAD_DIR,
        attachment["stored_name"],
        as_attachment=False
    )


# ============================================================
# ADMIN CONFIGURATION
# ============================================================

@app.route("/admin/config")
@admin_required
def admin_config():

    configured = supabase_configured()

    status_text = (
        "Configured"
        if configured
        else "Not configured"
    )

    status_class = (
        "badge-green"
        if configured
        else "badge-orange"
    )

    connected = False
    message = ""

    if configured:
        connected, message = test_supabase()
    else:
        message = (
            "The portal is running in local fallback mode."
        )

    content = f"""

    <div class="hero">

        <h1>System Configuration</h1>

        <p>
            This page is visible to administrators only.
        </p>

    </div>

    <div class="card">

        <h2>Supabase</h2>

        <p>
            Configuration:
            <span class="badge {status_class}">
                {status_text}
            </span>
        </p>

        <p>
            Connection:
            <span class="badge {
                "badge-green"
                if connected
                else "badge-orange"
            }">
                {
                    "Working"
                    if connected
                    else "Unavailable"
                }
            </span>
        </p>

        <hr>

        <p>
            <strong>Supabase URL</strong>
        </p>

        <pre>
{
    SUPABASE_URL
    if SUPABASE_URL
    else "Not configured"
}
        </pre>

        <p>
            <strong>Publishable Key</strong>
        </p>

        <pre>
{
    "Configured"
    if SUPABASE_PUBLISHABLE_KEY
    else "Not configured"
}
        </pre>

        <p>
            <strong>Service Key</strong>
        </p>

        <pre>
{
    "Configured — hidden"
    if SUPABASE_SERVICE_KEY
    else "Not configured"
}
        </pre>

        <p>
            <strong>Storage Bucket</strong>
        </p>

        <pre>{STORAGE_BUCKET}</pre>

        <hr>

        <h3>Connection Message</h3>

        <pre>{message}</pre>

    </div>

    <div class="card">

        <h2>Fallback Mode</h2>

        <p>
            The portal is designed not to stop simply because
            Supabase is unavailable.
        </p>

        <p>
            When Supabase cannot be reached, student accounts,
            questions and uploaded files continue using the
            server's local storage.
        </p>

        <p class="muted">
            On hosting platforms with ephemeral storage,
            configure Supabase for permanent production data.
        </p>

    </div>

    """

    return page(
        "Configuration",
        content
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    supabase_ok, _ = test_supabase()

    return {
        "status": "ok",
        "application": "KOJA AFRICA",
        "supabase_configured": supabase_configured(),
        "supabase_connected": supabase_ok,
        "mode": (
            "supabase"
            if supabase_ok
            else "fallback"
        )
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def too_large(error):

    flash(
        "File is too large. Maximum size is 10 MB.",
        "error"
    )

    if session.get("user_id"):
        return redirect(
            url_for("ask_question")
        )

    return redirect(
        url_for("login")
    )


@app.errorhandler(404)
def not_found(error):

    return page(
        "Not Found",
        """
        <div class="card">

            <h1>Page Not Found</h1>

            <p>
                The page you requested does not exist.
            </p>

            <a class="btn" href="/">
                Go Home
            </a>

        </div>
        """
    ), 404


@app.errorhandler(500)
def server_error(error):

    return page(
        "Portal Error",
        """
        <div class="card">

            <h1>KOJA is still running</h1>

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
        "Supabase configured:",
        supabase_configured()
    )
    print(
        "Storage bucket:",
        STORAGE_BUCKET
    )
    print(
        "Admin email:",
        ADMIN_EMAIL
    )
    print(
        "Fallback mode available: YES"
    )
    print(
        "Student dashboard: /student"
    )
    print(
        "Admin dashboard: /admin"
    )
    print(
        "Admin configuration: /admin/config"
    )
    print("=" * 60)
    print()

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
