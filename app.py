# ============================================================
# KOJA ZM
# Knowledge • Questions • Answers
#
# SINGLE-FILE FLASK WEBSITE PORTAL
#
# GRACEFUL DEGRADATION:
# - App starts without Supabase
# - App starts without Flutterwave
# - Bad external configuration does not crash the portal
# - Supabase is used automatically when configured correctly
# - Flutterwave is used automatically when configured correctly
# - Local fallback storage is used when external services fail
#
# DEPLOYMENT:
# Render / Railway / VPS / Pydroid 3
# ============================================================

import os
import uuid
import json
import hashlib
import secrets
import logging
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
    send_file,
    flash
)

# ============================================================
# APP
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "koja-development-secret-change-this"
)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

logging.basicConfig(level=logging.INFO)

# ============================================================
# CONFIGURATION
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

FLUTTERWAVE_SECRET_KEY = os.environ.get(
    "FLUTTERWAVE_SECRET_KEY",
    ""
).strip()

FLUTTERWAVE_PUBLIC_KEY = os.environ.get(
    "FLUTTERWAVE_PUBLIC_KEY",
    ""
).strip()

STORAGE_BUCKET = os.environ.get(
    "KOJA_STORAGE_BUCKET",
    "koja-files"
)

ADMIN_EMAIL = os.environ.get(
    "ADMIN_EMAIL",
    "admin@koja.edu"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "admin123"
)

# ============================================================
# RUNTIME STATUS
# ============================================================

SUPABASE_OK = False
FLUTTERWAVE_OK = False

# ============================================================
# LOCAL FALLBACK DATABASE
# ============================================================

DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "koja_data"
)

os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions.json")
NOTIFICATIONS_FILE = os.path.join(DATA_DIR, "notifications.json")
PURCHASES_FILE = os.path.join(DATA_DIR, "purchases.json")


def load_json(path, default):
    try:
        if not os.path.exists(path):
            return default

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        app.logger.warning(
            "Could not read %s: %s",
            path,
            e
        )
        return default


def save_json(path, data):
    try:
        temp = path + ".tmp"

        with open(temp, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

        os.replace(temp, path)

        return True

    except Exception as e:
        app.logger.error(
            "Could not save %s: %s",
            path,
            e
        )

        return False


# ============================================================
# INITIAL DATA
# ============================================================

def initialize_local_data():

    users = load_json(USERS_FILE, [])

    if not isinstance(users, list):
        users = []

    admin_exists = any(
        u.get("email", "").lower()
        == ADMIN_EMAIL.lower()
        for u in users
    )

    if not admin_exists:
        users.append({
            "id": str(uuid.uuid4()),
            "name": "KOJA Administrator",
            "email": ADMIN_EMAIL.lower(),
            "password": hash_password(ADMIN_PASSWORD),
            "role": "admin",
            "created_at": datetime.utcnow().isoformat()
        })

        save_json(USERS_FILE, users)

    if not os.path.exists(QUESTIONS_FILE):
        save_json(QUESTIONS_FILE, [])

    if not os.path.exists(NOTIFICATIONS_FILE):
        save_json(NOTIFICATIONS_FILE, [])

    if not os.path.exists(PURCHASES_FILE):
        save_json(PURCHASES_FILE, [])


# ============================================================
# PASSWORD
# ============================================================

def hash_password(password):
    salt = secrets.token_hex(16)

    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        200000
    ).hex()

    return f"{salt}${hashed}"


def verify_password(password, stored):

    try:
        salt, hashed = stored.split("$", 1)

        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            200000
        ).hex()

        return secrets.compare_digest(
            check,
            hashed
        )

    except Exception:
        return False


# ============================================================
# SUPABASE
# ============================================================

def supabase_headers():

    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": (
            "Bearer " +
            SUPABASE_SERVICE_KEY
        ),
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def check_supabase():

    global SUPABASE_OK

    if not SUPABASE_URL:
        SUPABASE_OK = False
        return False

    if not SUPABASE_SERVICE_KEY:
        SUPABASE_OK = False
        return False

    try:

        response = requests.get(
            SUPABASE_URL + "/rest/v1/",
            headers=supabase_headers(),
            timeout=5
        )

        SUPABASE_OK = (
            response.status_code < 500
        )

        return SUPABASE_OK

    except Exception as e:

        app.logger.warning(
            "Supabase unavailable: %s",
            e
        )

        SUPABASE_OK = False
        return False


def supabase_request(
    method,
    table,
    payload=None,
    params=None
):

    if not SUPABASE_URL:
        return None

    if not SUPABASE_SERVICE_KEY:
        return None

    try:

        url = (
            SUPABASE_URL +
            "/rest/v1/" +
            table
        )

        response = requests.request(
            method,
            url,
            headers=supabase_headers(),
            json=payload,
            params=params,
            timeout=10
        )

        if response.status_code >= 400:

            app.logger.warning(
                "Supabase %s error %s: %s",
                table,
                response.status_code,
                response.text[:500]
            )

            return None

        if not response.text:
            return []

        return response.json()

    except Exception as e:

        app.logger.warning(
            "Supabase request failed: %s",
            e
        )

        return None


# ============================================================
# FLUTTERWAVE
# ============================================================

def check_flutterwave():

    global FLUTTERWAVE_OK

    if not FLUTTERWAVE_SECRET_KEY:

        FLUTTERWAVE_OK = False
        return False

    try:

        response = requests.get(
            "https://api.flutterwave.com/v3/banks/zm",
            headers={
                "Authorization":
                    "Bearer " +
                    FLUTTERWAVE_SECRET_KEY
            },
            timeout=5
        )

        FLUTTERWAVE_OK = (
            response.status_code < 500
        )

        return FLUTTERWAVE_OK

    except Exception as e:

        app.logger.warning(
            "Flutterwave unavailable: %s",
            e
        )

        FLUTTERWAVE_OK = False
        return False


# ============================================================
# DATA ACCESS
# ============================================================

def get_users():

    if SUPABASE_OK:

        result = supabase_request(
            "GET",
            "users",
            params={
                "select": "*"
            }
        )

        if result is not None:
            return result

    return load_json(
        USERS_FILE,
        []
    )


def get_questions():

    if SUPABASE_OK:

        result = supabase_request(
            "GET",
            "questions",
            params={
                "select": "*",
                "order": "created_at.desc"
            }
        )

        if result is not None:
            return result

    return load_json(
        QUESTIONS_FILE,
        []
    )


def save_question(question):

    if SUPABASE_OK:

        result = supabase_request(
            "POST",
            "questions",
            question
        )

        if result is not None:
            return result

    questions = load_json(
        QUESTIONS_FILE,
        []
    )

    questions.append(question)

    save_json(
        QUESTIONS_FILE,
        questions
    )

    return [question]


def save_user(user):

    if SUPABASE_OK:

        result = supabase_request(
            "POST",
            "users",
            user
        )

        if result is not None:
            return result

    users = load_json(
        USERS_FILE,
        []
    )

    users.append(user)

    save_json(
        USERS_FILE,
        users
    )

    return [user]


# ============================================================
# AUTH DECORATORS
# ============================================================

def login_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect(
                url_for("login")
            )

        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if session.get("role") != "admin":
            return redirect(
                url_for("login")
            )

        return fn(*args, **kwargs)

    return wrapper


# ============================================================
# TEMPLATE
# ============================================================

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width,initial-scale=1">

<title>{{ title }} — KOJA</title>

<style>

* {
    box-sizing:border-box;
}

body {
    margin:0;
    font-family:
        Arial,
        Helvetica,
        sans-serif;
    background:#f5f7fb;
    color:#172033;
}

nav {
    background:#ffffff;
    border-bottom:1px solid #e5e7eb;
    padding:15px 20px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:15px;
    position:sticky;
    top:0;
    z-index:100;
}

.logo {
    font-size:25px;
    font-weight:900;
    letter-spacing:1px;
}

.logo span:nth-child(1) {
    color:#2563eb;
}

.logo span:nth-child(2) {
    color:#16a34a;
}

.logo span:nth-child(3) {
    color:#dc2626;
}

.logo span:nth-child(4) {
    color:#1d4ed8;
}

nav a {
    text-decoration:none;
    color:#334155;
    margin-left:12px;
    font-weight:600;
}

.container {
    max-width:1150px;
    margin:auto;
    padding:25px 18px;
}

.hero {
    background:linear-gradient(
        135deg,
        #1d4ed8,
        #2563eb
    );
    color:white;
    padding:50px 25px;
    border-radius:20px;
    margin-bottom:25px;
}

.hero h1 {
    font-size:42px;
    margin:0 0 12px;
}

.hero p {
    font-size:18px;
    line-height:1.6;
}

.grid {
    display:grid;
    grid-template-columns:
        repeat(auto-fit,minmax(230px,1fr));
    gap:18px;
}

.card {
    background:white;
    border-radius:16px;
    padding:22px;
    box-shadow:
        0 5px 20px
        rgba(0,0,0,.06);
}

.card h3 {
    margin-top:0;
}

.btn {
    display:inline-block;
    background:#2563eb;
    color:white;
    border:0;
    border-radius:10px;
    padding:12px 18px;
    text-decoration:none;
    cursor:pointer;
    font-weight:700;
}

.btn.secondary {
    background:#475569;
}

.btn.success {
    background:#16a34a;
}

input,
textarea,
select {
    width:100%;
    padding:13px;
    border:1px solid #cbd5e1;
    border-radius:10px;
    margin:7px 0 15px;
    font-size:16px;
}

label {
    font-weight:700;
}

.alert {
    padding:13px;
    border-radius:10px;
    background:#fff7ed;
    border:1px solid #fed7aa;
    margin-bottom:15px;
}

.status {
    display:inline-block;
    padding:7px 10px;
    border-radius:20px;
    background:#dcfce7;
    color:#166534;
    font-size:13px;
    font-weight:bold;
}

.status.off {
    background:#fee2e2;
    color:#991b1b;
}

footer {
    text-align:center;
    padding:35px;
    color:#64748b;
}

.question {
    border-left:4px solid #2563eb;
    margin-bottom:15px;
}

.small {
    font-size:13px;
    color:#64748b;
}

</style>

</head>

<body>

<nav>

<a href="{{ url_for('home') }}"
   style="text-decoration:none">

<div class="logo">
<span>K</span><span>O</span><span>J</span><span>A</span>
</div>

</a>

<div>

<a href="{{ url_for('home') }}">
Home
</a>

<a href="{{ url_for('questions') }}">
Questions
</a>

{% if session.get("user_id") %}

<a href="{{ url_for('dashboard') }}">
Dashboard
</a>

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

</nav>

<div class="container">

{% with messages = get_flashed_messages() %}

{% for message in messages %}

<div class="alert">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</div>

<footer>

<strong>KOJA</strong><br>

Knowledge • Questions • Answers

<br><br>

Assignment Questions • Academic Answers

</footer>

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

    content = render_template_string("""
<div class="hero">

<h1>KOJA</h1>

<p>
Knowledge • Questions • Answers
</p>

<p>
Assignment Questions • Academic Answers
• Learning Resources
</p>

<a class="btn"
   href="{{ url_for('questions') }}">
Explore Questions
</a>

</div>

<div class="grid">

<div class="card">

<h3>📚 Academic Questions</h3>

<p>
Ask questions and access academic
learning resources.
</p>

</div>

<div class="card">

<h3>📝 Assignments</h3>

<p>
Submit and manage your academic
questions.
</p>

</div>

<div class="card">

<h3>📖 Learning Resources</h3>

<p>
Build a searchable collection of
educational resources.
</p>

</div>

<div class="card">

<h3>🌍 Global Access</h3>

<p>
Designed to work through the internet
from anywhere.
</p>

</div>

</div>

<br>

<div class="card">

<h3>System status</h3>

<p>
Portal:
<span class="status">ONLINE</span>
</p>

<p>
Supabase:
{% if supabase %}
<span class="status">CONNECTED</span>
{% else %}
<span class="status off">FALLBACK MODE</span>
{% endif %}
</p>

<p>
Payments:
{% if flutterwave %}
<span class="status">AVAILABLE</span>
{% else %}
<span class="status off">DISABLED</span>
{% endif %}
</p>

</div>

""",
        supabase=SUPABASE_OK,
        flutterwave=FLUTTERWAVE_OK
    )

    return page(
        "Home",
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

        if not name or not email or not password:

            flash(
                "Please complete all fields."
            )

            return redirect(
                url_for("register")
            )

        users = get_users()

        if any(
            u.get("email", "").lower()
            == email
            for u in users
        ):

            flash(
                "An account with this email already exists."
            )

            return redirect(
                url_for("login")
            )

        user = {
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "password": hash_password(password),
            "role": "student",
            "created_at":
                datetime.utcnow().isoformat()
        }

        save_user(user)

        flash(
            "Account created successfully."
        )

        return redirect(
            url_for("login")
        )

    content = """
<h2>Create KOJA Account</h2>

<div class="card">

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

<button class="btn"
        type="submit">
Create Account
</button>

</form>

</div>
"""

    return page(
        "Register",
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

        users = get_users()

        user = next(
            (
                u for u in users
                if u.get("email", "").lower()
                == email
            ),
            None
        )

        if user and verify_password(
            password,
            user.get("password", "")
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["email"] = user["email"]
            session["name"] = user.get(
                "name",
                ""
            )
            session["role"] = user.get(
                "role",
                "student"
            )

            return redirect(
                url_for("dashboard")
            )

        flash(
            "Invalid email or password."
        )

    content = """
<h2>Login</h2>

<div class="card">

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

<button class="btn"
        type="submit">
Login
</button>

</form>

</div>
"""

    return page(
        "Login",
        content
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
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    questions = get_questions()

    my_questions = [
        q for q in questions
        if q.get("user_id")
        == session.get("user_id")
    ]

    content = render_template_string("""
<h2>
Welcome, {{ name }}
</h2>

<div class="grid">

<div class="card">

<h3>My Questions</h3>

<p style="font-size:30px">
{{ count }}
</p>

</div>

<div class="card">

<h3>Account</h3>

<p>
{{ email }}
</p>

</div>

<div class="card">

<h3>Portal</h3>

<p>
<span class="status">ONLINE</span>
</p>

</div>

</div>

<br>

<div class="card">

<h3>Submit a Question</h3>

<form method="POST"
      action="{{ url_for('ask') }}">

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
    rows="6"
    placeholder="Write your question..."
    required
></textarea>

<button class="btn"
        type="submit">
Submit Question
</button>

</form>

</div>

<br>

<h2>My Recent Questions</h2>

{% for q in my_questions[-10:]|reverse %}

<div class="card question">

<h3>
{{ q.get("subject") }}
</h3>

<p>
{{ q.get("question") }}
</p>

<p class="small">
{{ q.get("created_at") }}
</p>

</div>

{% else %}

<div class="card">
<p>
You have not submitted any questions yet.
</p>
</div>

{% endfor %}

""",
        name=session.get("name"),
        email=session.get("email"),
        count=len(my_questions),
        my_questions=my_questions
    )

    return page(
        "Dashboard",
        content
    )


# ============================================================
# ASK QUESTION
# ============================================================

@app.route(
    "/ask",
    methods=["POST"]
)
@login_required
def ask():

    subject = request.form.get(
        "subject",
        ""
    ).strip()

    question_text = request.form.get(
        "question",
        ""
    ).strip()

    if not subject or not question_text:

        flash(
            "Subject and question are required."
        )

        return redirect(
            url_for("dashboard")
        )

    question = {
        "id": str(uuid.uuid4()),
        "user_id":
            session.get("user_id"),
        "student_name":
            session.get("name"),
        "subject": subject,
        "question": question_text,
        "status": "Pending",
        "answer": "",
        "created_at":
            datetime.utcnow().isoformat()
    }

    save_question(question)

    flash(
        "Question submitted successfully."
    )

    return redirect(
        url_for("dashboard")
    )


# ============================================================
# QUESTIONS
# ============================================================

@app.route("/questions")
def questions():

    all_questions = get_questions()

    content = render_template_string("""
<h2>Academic Questions</h2>

<div class="card">

<form method="GET">

<input
    type="search"
    name="q"
    value="{{ search }}"
    placeholder="Search questions..."
>

<button class="btn"
        type="submit">
Search
</button>

</form>

</div>

<br>

{% for item in questions %}

<div class="card question">

<h3>
{{ item.get("subject") }}
</h3>

<p>
{{ item.get("question") }}
</p>

{% if item.get("answer") %}

<hr>

<h4>Answer</h4>

<p>
{{ item.get("answer") }}
</p>

{% endif %}

<p class="small">
Status:
{{ item.get("status", "Pending") }}
</p>

</div>

{% else %}

<div class="card">

<p>
No questions found.
</p>

</div>

{% endfor %}

""",
        questions=(
            [
                q for q in all_questions
                if search.lower()
                in (
                    q.get("question", "") +
                    " " +
                    q.get("subject", "")
                ).lower()
            ]
            if (
                search :=
                request.args.get(
                    "q",
                    ""
                ).strip()
            )
            else all_questions
        )
    )

    return page(
        "Questions",
        content
    )


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    users = get_users()
    questions = get_questions()

    content = render_template_string("""
<h2>KOJA Administration</h2>

<div class="grid">

<div class="card">

<h3>Users</h3>

<p style="font-size:30px">
{{ users|length }}
</p>

</div>

<div class="card">

<h3>Questions</h3>

<p style="font-size:30px">
{{ questions|length }}
</p>

</div>

<div class="card">

<h3>Supabase</h3>

<p>
{% if supabase %}
<span class="status">
CONNECTED
</span>
{% else %}
<span class="status off">
FALLBACK
</span>
{% endif %}
</p>

</div>

<div class="card">

<h3>Flutterwave</h3>

<p>
{% if flutterwave %}
<span class="status">
AVAILABLE
</span>
{% else %}
<span class="status off">
DISABLED
</span>
{% endif %}
</p>

</div>

</div>

<br>

<h2>Submitted Questions</h2>

{% for q in questions|reverse %}

<div class="card question">

<h3>
{{ q.get("subject") }}
</h3>

<p>
{{ q.get("question") }}
</p>

<p class="small">
Student:
{{ q.get("student_name") }}
</p>

<form method="POST"
      action="{{ url_for(
          'answer_question',
          question_id=q.get('id')
      ) }}">

<textarea
    name="answer"
    rows="5"
    placeholder="Write academic answer..."
>{{ q.get("answer", "") }}</textarea>

<button class="btn success"
        type="submit">
Save Answer
</button>

</form>

</div>

{% endfor %}

""",
        users=users,
        questions=questions,
        supabase=SUPABASE_OK,
        flutterwave=FLUTTERWAVE_OK
    )

    return page(
        "Admin",
        content
    )


# ============================================================
# ADMIN ANSWER
# ============================================================

@app.route(
    "/admin/answer/<question_id>",
    methods=["POST"]
)
@admin_required
def answer_question(question_id):

    answer = request.form.get(
        "answer",
        ""
    ).strip()

    questions = get_questions()

    found = False

    for q in questions:

        if q.get("id") == question_id:

            q["answer"] = answer

            q["status"] = (
                "Answered"
                if answer
                else "Pending"
            )

            found = True

            break

    if found:

        if SUPABASE_OK:

            supabase_request(
                "PATCH",
                "questions",
                {
                    "answer": answer,
                    "status":
                        "Answered"
                        if answer
                        else "Pending"
                },
                {
                    "id":
                        "eq." +
                        question_id
                }
            )

        save_json(
            QUESTIONS_FILE,
            questions
        )

        flash(
            "Answer saved."
        )

    return redirect(
        url_for("admin")
    )


# ============================================================
# API STATUS
# ============================================================

@app.route("/api/status")
def api_status():

    return jsonify({
        "status": "online",
        "application": "KOJA",
        "supabase": SUPABASE_OK,
        "flutterwave": FLUTTERWAVE_OK,
        "mode":
            "cloud"
            if SUPABASE_OK
            else "fallback",
        "timestamp":
            datetime.utcnow().isoformat()
    })


# ============================================================
# API QUESTIONS
# ============================================================

@app.route("/api/questions")
def api_questions():

    return jsonify({
        "success": True,
        "data": get_questions()
    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return "KOJA ONLINE", 200


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return page(
        "Page Not Found",
        """
        <div class="card">
        <h2>Page not found</h2>
        <p>
        The page you requested does not exist.
        </p>
        <a class="btn"
           href="/">
        Return Home
        </a>
        </div>
        """
    ), 404


@app.errorhandler(413)
def file_too_large(error):

    return page(
        "File Too Large",
        """
        <div class="card">
        <h2>File too large</h2>
        <p>
        The maximum upload size is 10 MB.
        </p>
        </div>
        """
    ), 413


@app.errorhandler(500)
def server_error(error):

    app.logger.exception(
        "Unexpected server error"
    )

    return page(
        "Temporary Error",
        """
        <div class="card">
        <h2>KOJA is still running</h2>
        <p>
        A temporary problem occurred while
        processing this request.
        </p>
        <a class="btn"
           href="/">
        Return Home
        </a>
        </div>
        """
    ), 500


# ============================================================
# STARTUP
# ============================================================

initialize_local_data()

check_supabase()
check_flutterwave()

app.logger.info(
    "========================================"
)

app.logger.info(
    "KOJA started"
)

app.logger.info(
    "Supabase: %s",
    "CONNECTED"
    if SUPABASE_OK
    else "FALLBACK MODE"
)

app.logger.info(
    "Flutterwave: %s",
    "AVAILABLE"
    if FLUTTERWAVE_OK
    else "DISABLED"
)

app.logger.info(
    "========================================"
)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
