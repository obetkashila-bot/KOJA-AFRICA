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
# PUBLIC:
#   Home
#   Log In
#   Create Account
#
# ADMIN:
#   Dashboard
#   Questions
#   Answers
#   Upload Documents
#   Downloads
#   Logs
#
# STUDENT:
#   Dashboard
#   Ask Question
#   My Questions
#   Research
#   Downloads
#
# IMPORTANT:
# Public pages NEVER contain admin/student navigation.
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

USERS_FILE = os.path.join(
    DATA_DIR,
    "users.json"
)

QUESTIONS_FILE = os.path.join(
    DATA_DIR,
    "questions.json"
)

LOGS_FILE = os.path.join(
    DATA_DIR,
    "logs.json"
)

DOCUMENTS_FILE = os.path.join(
    DATA_DIR,
    "documents.json"
)


# ============================================================
# FILE HELPERS
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
                indent=2
            )


ensure_file(USERS_FILE, [])
ensure_file(QUESTIONS_FILE, [])
ensure_file(LOGS_FILE, [])
ensure_file(DOCUMENTS_FILE, [])


def read_json(path, default=None):
    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []


def write_json(path, data):
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

    return (
        salt.hex()
        + "$"
        + key.hex()
    )


def verify_password(password, stored):
    try:
        salt_hex, key_hex = stored.split("$")

        salt = bytes.fromhex(
            salt_hex
        )

        expected = bytes.fromhex(
            key_hex
        )

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
    users = read_json(
        USERS_FILE,
        []
    )

    for user in users:
        if user.get("role") == "admin":
            return

    admin_password = os.environ.get(
        "KOJA_ADMIN_PASSWORD"
    )

    if not admin_password:
        admin_password = "ChangeMe123!"

    admin = {
        "id": str(uuid.uuid4()),
        "name": "KOJA Administrator",
        "email": os.environ.get(
            "KOJA_ADMIN_EMAIL",
            "admin@koja.africa"
        ).lower(),
        "password": hash_password(
            admin_password
        ),
        "role": "admin",
        "created_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    users.append(admin)

    write_json(
        USERS_FILE,
        users
    )


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
    logs = read_json(
        LOGS_FILE,
        []
    )

    logs.append({
        "id": str(uuid.uuid4()),
        "event": event,
        "category": category,
        "level": level,
        "details": details,
        "time": datetime.now(
            timezone.utc
        ).isoformat(),
        "user_id": session.get(
            "user_id"
        )
    })

    # Keep the log file manageable.
    logs = logs[-5000:]

    write_json(
        LOGS_FILE,
        logs
    )


# ============================================================
# AUTH HELPERS
# ============================================================

def current_user():
    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return None

    users = read_json(
        USERS_FILE,
        []
    )

    for user in users:
        if user.get("id") == user_id:
            return user

    return None


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

        return view(
            *args,
            **kwargs
        )

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()

        if not user:
            return redirect(
                url_for("login")
            )

        if user.get("role") != "admin":
            abort(403)

        return view(
            *args,
            **kwargs
        )

    return wrapped


# ============================================================
# COMMON CSS
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

/* =========================================================
   DARK BLUE TOP BAR
   ========================================================= */

.topbar {
    width: 100%;
    background: #061b49;
    color: white;
    box-shadow:
        0 4px 18px rgba(0,0,0,.15);
}

.topbar-inner {
    width: 100%;
    max-width: 1300px;
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

/* =========================================================
   PUBLIC NAVIGATION
   ONLY LOGIN + CREATE ACCOUNT
   ========================================================= */

.public-nav {
    display: flex;
    align-items: center;
    gap: 10px;
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

/* =========================================================
   PRIVATE NAVIGATION
   ========================================================= */

.private-nav {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 5px;
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

/* =========================================================
   CONTENT
   ========================================================= */

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
        repeat(
            auto-fit,
            minmax(200px, 1fr)
        );
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

footer {
    text-align: center;
    padding: 35px 20px;
    color: #64748b;
}

@media(max-width:700px) {

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
    }

    .hero {
        padding: 45px 20px;
    }
}

</style>
"""


# ============================================================
# PUBLIC LAYOUT
#
# CRITICAL:
# There is NO admin/student navigation here.
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

<a class="logo"
   href="{{ url_for('home') }}">

<span class="k">k</span><span
class="o">o</span><span
class="j">j</span><span
class="a">a</span>

<small>AFRICA</small>

</a>

<!-- =====================================================
     PUBLIC NAVIGATION
     THESE ARE THE ONLY PUBLIC NAVIGATION BUTTONS
     ===================================================== -->

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

<a class="logo"
   href="{{ url_for('home') }}">

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
#
# PUBLIC HTML CONTAINS ONLY:
# LOG IN
# CREATE ACCOUNT
# ============================================================

@app.route("/")
def home():

    # Deliberately do NOT pass user navigation
    # into the public home page.

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
    href="/login"
>
    Log In
</a>

<a
    class="btn"
    href="/register"
>
    Create Account
</a>

</div>

</section>
"""

    response = make_response(
        public_page(
            "Home",
            content
        )
    )

    # Tell search engines that this is the
    # public landing page.
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
            "password": hash_password(
                password
            ),
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
                url_for(
                    "admin_dashboard"
                )
            )

        return redirect(
            url_for(
                "student_dashboard"
            )
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

    mine = [
        q for q in questions
        if q.get("student_id")
        == user["id"]
    ]

    answered = sum(
        1 for q in mine
        if q.get("answer")
    )

    content = f"""
<div class="card">

<h1>
Welcome, {user.get("name")}
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

</div>

<div class="card">

<a class="btn"
   href="/ask">
Ask Question
</a>

<a class="btn dark"
   href="/research">
Research
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
            "attachments": []
        }

        file = request.files.get(
            "document"
        )

        if file and file.filename:

            original = file.filename

            safe_name = (
                str(uuid.uuid4())
                + "_"
                + original.replace(
                    "/",
                    "_"
                ).replace(
                    "\\",
                    "_"
                )
            )

            path = os.path.join(
                STUDENT_UPLOAD_DIR,
                safe_name
            )

            file.save(path)

            question[
                "attachments"
            ].append({
                "original_name": original,
                "stored_name": safe_name
            })

        questions = read_json(
            QUESTIONS_FILE,
            []
        )

        questions.append(
            question
        )

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
            url_for(
                "student_questions"
            )
        )

    content = """
<div class="card">

<h1>Ask KOJA</h1>

<form
    method="post"
    enctype="multipart/form-data"
>

<label>
Question
</label>

<textarea
    name="question"
    required
></textarea>

<label>
Upload document
</label>

<input
    type="file"
    name="document"
>

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
        if q.get("student_id")
        == user["id"]
    ]

    blocks = []

    for q in reversed(mine):

        answer = q.get("answer")

        status = (
            "Answered"
            if answer
            else "Pending"
        )

        answer_html = ""

        if answer:
            answer_html = f"""
<h3>Answer</h3>

<div class="answer">
{answer}
</div>
"""

        blocks.append(f"""
<div class="card">

<h3>
{q.get("question")}
</h3>

<p>
Status:
<strong>{status}</strong>
</p>

{answer_html}

</div>
""")

    content = "".join(blocks)

    if not content:
        content = """
<div class="card">

<h1>My Questions</h1>

<p>
You have not submitted a question yet.
</p>

<a class="btn"
   href="/ask">
Ask Question
</a>

</div>
"""

    return private_page(
        "My Questions",
        content
    )


# ============================================================
# RESEARCH
#
# IMPORTANT:
# Do not expose unanswered questions.
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
{q.get("question")}
</h2>

<div class="answer">
{q.get("answer")}
</div>

</div>
""")

    content = """
<div class="card">

<h1>Research</h1>

<p>
Only questions that have been answered
are available in the research area.
</p>

</div>
"""

    content += "".join(blocks)

    return private_page(
        "Research",
        content
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
<h2>{len(documents)}</h2>
<p>Documents</p>
</div>

<div class="stat">
<h2>{len(logs)}</h2>
<p>Logs</p>
</div>

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

        blocks.append(f"""
<div class="card">

<h2>
{q.get("question")}
</h2>

<p>
Student:
{q.get("student_name")}
</p>

<p>
Status:
<strong>{status}</strong>
</p>

<a
 class="btn"
 href="/admin/answer/{q.get("id")}"
>
Answer Question
</a>

</div>
""")

    content = """
<div class="card">

<h1>Questions</h1>

</div>
""" + "".join(blocks)

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

        question["answer_by"] = (
            admin.get("name")
        )

        question["answered_at"] = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        question[
            "answer_attachments"
        ] = question.get(
            "answer_attachments",
            []
        )

        file = request.files.get(
            "document"
        )

        if file and file.filename:

            original = file.filename

            safe_name = (
                str(uuid.uuid4())
                + "_"
                + original.replace(
                    "/",
                    "_"
                ).replace(
                    "\\",
                    "_"
                )
            )

            path = os.path.join(
                ADMIN_UPLOAD_DIR,
                safe_name
            )

            file.save(path)

            question[
                "answer_attachments"
            ].append({
                "original_name": original,
                "stored_name": safe_name
            })

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

    content = f"""
<div class="card">

<h1>Answer Question</h1>

<div class="question">
{question.get("question")}
</div>

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
>{question.get("answer", "")}</textarea>

<label>
Upload answer document
</label>

<input
    type="file"
    name="document"
>

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
{q.get("question")}
</h2>

<div class="answer">
{q.get("answer")}
</div>

<p>
Answered by:
{q.get("answer_by", "Admin")}
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
""" + "".join(blocks)

    return private_page(
        "Answers",
        content
    )


# ============================================================
# ADMIN DOCUMENT UPLOAD
# ============================================================

@app.route(
    "/admin/documents",
    methods=["GET", "POST"]
)
@admin_required
def admin_documents():

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        file = request.files.get(
            "document"
        )

        if not title or not file:
            flash(
                "Title and document are required.",
                "error"
            )

            return redirect(
                url_for(
                    "admin_documents"
                )
            )

        original = file.filename

        safe_name = (
            str(uuid.uuid4())
            + "_"
            + original.replace(
                "/",
                "_"
            ).replace(
                "\\",
                "_"
            )
        )

        path = os.path.join(
            ADMIN_UPLOAD_DIR,
            safe_name
        )

        file.save(path)

        documents = read_json(
            DOCUMENTS_FILE,
            []
        )

        document = {
            "id": str(uuid.uuid4()),
            "title": title,
            "original_name": original,
            "stored_name": safe_name,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

        documents.append(
            document
        )

        write_json(
            DOCUMENTS_FILE,
            documents
        )

        log_event(
            "Document Uploaded",
            "Documents",
            "INFO",
            original
        )

        flash(
            "Document uploaded.",
            "success"
        )

        return redirect(
            url_for(
                "admin_documents"
            )
        )

    documents = read_json(
        DOCUMENTS_FILE,
        []
    )

    rows = []

    for d in reversed(documents):

        rows.append(f"""
<tr>

<td>
{d.get("title")}
</td>

<td>
{d.get("original_name")}
</td>

<td>

<a
 class="btn"
 href="/admin/download/{d.get("id")}"
>
Download
</a>

</td>

</tr>
""")

    content = f"""
<div class="card">

<h1>Upload Documents</h1>

<form
    method="post"
    enctype="multipart/form-data"
>

<label>
Document title
</label>

<input
    type="text"
    name="title"
    required
>

<label>
Document
</label>

<input
    type="file"
    name="document"
    required
>

<button type="submit">
Upload Document
</button>

</form>

</div>

<div class="card">

<h2>Documents</h2>

<div class="table-wrap">

<table>

<tr>
<th>Title</th>
<th>File</th>
<th>Download</th>
</tr>

{''.join(rows)}

</table>

</div>

</div>
"""

    return private_page(
        "Documents",
        content
    )


# ============================================================
# ADMIN DOWNLOAD DOCUMENT
# ============================================================

@app.route(
    "/admin/download/<document_id>"
)
@admin_required
def admin_download(document_id):

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

    log_event(
        "Admin Document Downloaded",
        "Documents",
        "INFO",
        filename
    )

    return send_from_directory(
        ADMIN_UPLOAD_DIR,
        filename,
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
{item.get("time", "")}
</td>

<td>
{item.get("event", "")}
</td>

<td>
{item.get("category", "")}
</td>

<td>
{item.get("level", "")}
</td>

<td>
{item.get("details", "")}
</td>

</tr>
""")

    content = f"""
<div class="card">

<h1>System Logs</h1>

<p>
Private administrator information.
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
#
# Prevent public pages from accidentally being indexed as
# private pages.
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

    # Private/admin routes must not be cached.
    if (
        request.path.startswith("/admin")
        or request.path.startswith("/student")
        or request.path.startswith("/ask")
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
this page.
</p>

<a class="btn"
   href="/">
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

<a class="btn"
   href="/">
Return Home
</a>

</div>
"""
    ), 404


# ============================================================
# ROBOTS.TXT
# ============================================================

@app.route("/robots.txt")
def robots():

    text = """User-agent: *
Allow: /

Disallow: /admin
Disallow: /student
Disallow: /ask
Disallow: /logout

"""

    response = make_response(
        text
    )

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

    response = make_response(
        xml
    )

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
    print("  Downloads")
    print()
    print("STUDENT:")
    print("  Dashboard")
    print("  Ask Question")
    print("  My Questions")
    print("  Research")
    print()
    print("Server:", f"http://0.0.0.0:{port}")
    print("=" * 60)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
