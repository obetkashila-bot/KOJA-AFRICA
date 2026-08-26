# ============================================================
# KOJA AFRICA
# Knowledge • Questions • Answers
#
# SINGLE-FILE FLASK APPLICATION
#
# PUBLIC:
#   - KOJA AFRICA landing page
#   - Log In
#   - Create Account
#
# PRIVATE:
#   - Student dashboard
#   - Student questions
#   - Student answers
#   - Student files
#
# ADMIN:
#   - Dashboard
#   - Questions
#   - Answers
#   - Users
#   - Logs
#
# SECURITY:
#   - Password hashing
#   - Session authentication
#   - Role-based access
#   - Private student questions
#   - Private answers
#   - Protected files
#   - Security logging
#
# RUN:
#   pip install flask werkzeug
#   python app.py
#
# OPEN:
#   http://127.0.0.1:9999
# ============================================================

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
    abort
)

from werkzeug.utils import secure_filename


# ============================================================
# APPLICATION
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    secrets.token_hex(32)
)

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


# ============================================================
# DIRECTORIES
# ============================================================

DATA_DIR = os.path.join(
    BASE_DIR,
    "koja_data"
)

STUDENT_UPLOAD_DIR = os.path.join(
    DATA_DIR,
    "student_uploads"
)

ADMIN_UPLOAD_DIR = os.path.join(
    DATA_DIR,
    "admin_uploads"
)

os.makedirs(DATA_DIR, exist_ok=True)
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


# ============================================================
# CONFIGURATION
# ============================================================

APP_NAME = "KOJA AFRICA"

APP_TAGLINE = (
    "Knowledge • Questions • Answers"
)

SITE_DESCRIPTION = (
    "KOJA Africa is an academic learning "
    "platform for questions, assignments, "
    "research and academic answers."
)

MAX_CONTENT_LENGTH = 10 * 1024 * 1024

app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "png",
    "jpg",
    "jpeg"
}


# ============================================================
# DEFAULT ADMIN
# ============================================================

ADMIN_EMAIL = os.environ.get(
    "KOJA_ADMIN_EMAIL",
    "admin@kojaafrica.com"
)

ADMIN_PASSWORD = os.environ.get(
    "KOJA_ADMIN_PASSWORD",
    "ChangeThisPassword123!"
)


# ============================================================
# JSON DATABASE
# ============================================================

def load_json(path, default):
    try:
        if not os.path.exists(path):
            save_json(path, default)
            return default

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        return data

    except Exception:
        return default


def save_json(path, data):
    temp_path = path + ".tmp"

    with open(
        temp_path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )

    os.replace(
        temp_path,
        path
    )


def get_users():
    return load_json(
        USERS_FILE,
        []
    )


def save_users(users):
    save_json(
        USERS_FILE,
        users
    )


def get_questions():
    return load_json(
        QUESTIONS_FILE,
        []
    )


def save_questions(questions):
    save_json(
        QUESTIONS_FILE,
        questions
    )


def get_logs():
    return load_json(
        LOGS_FILE,
        []
    )


def save_logs(logs):
    save_json(
        LOGS_FILE,
        logs
    )


# ============================================================
# PASSWORD SECURITY
# ============================================================

def hash_password(password):
    salt = secrets.token_bytes(16)

    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        310000
    )

    return (
        salt.hex()
        + "$"
        + key.hex()
    )


def verify_password(password, stored):
    try:
        salt_hex, key_hex = stored.split(
            "$",
            1
        )

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
            310000
        )

        return secrets.compare_digest(
            actual,
            expected
        )

    except Exception:
        return False


# ============================================================
# LOGGING
# ============================================================

def log_event(
    event,
    category="System",
    level="INFO",
    details=""
):
    logs = get_logs()

    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "event": event,
        "category": category,
        "level": level,
        "details": details,
        "user_id": session.get(
            "user_id"
        ),
        "email": session.get(
            "email"
        ),
        "ip": request.remote_addr
    }

    logs.append(entry)

    # Keep logs manageable.
    logs = logs[-5000:]

    save_logs(
        logs
    )


# ============================================================
# INITIALIZE ADMIN
# ============================================================

def initialize_admin():
    users = get_users()

    for user in users:
        if user.get("email") == ADMIN_EMAIL:
            return

    admin = {
        "id": str(uuid.uuid4()),
        "name": "KOJA Administrator",
        "email": ADMIN_EMAIL.lower(),
        "password": hash_password(
            ADMIN_PASSWORD
        ),
        "role": "admin",
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "active": True
    }

    users.append(admin)

    save_users(
        users
    )


initialize_admin()


# ============================================================
# HELPERS
# ============================================================

def current_user():
    user_id = session.get(
        "user_id"
    )

    if not user_id:
        return None

    users = get_users()

    for user in users:
        if user.get("id") == user_id:
            return user

    return None


def is_logged_in():
    return current_user() is not None


def is_admin_session():
    user = current_user()

    return (
        user is not None
        and user.get("role") == "admin"
    )


def find_user(user_id):
    for user in get_users():
        if user.get("id") == user_id:
            return user

    return None


def find_question(question_id):
    for question in get_questions():
        if question.get("id") == question_id:
            return question

    return None


def allowed_file(filename):
    if not filename:
        return False

    if "." not in filename:
        return False

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    return extension in ALLOWED_EXTENSIONS


# ============================================================
# AUTH DECORATORS
# ============================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not is_logged_in():
            flash(
                "Please log in first.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not is_logged_in():
            flash(
                "Administrator login required.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        if not is_admin_session():
            log_event(
                "Unauthorized Admin Access",
                "Security",
                "WARNING"
            )

            abort(403)

        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# BASE HTML
# ============================================================

HTML = r"""
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<meta name="theme-color"
      content="#071a3d">

<meta name="description"
      content="{{ site_description }}">

<meta name="robots"
      content="index, follow">

<title>
    {{ title }} - KOJA AFRICA
</title>

<style>

* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    padding: 0;
    min-height: 100%;
    font-family:
        Arial,
        Helvetica,
        sans-serif;
    background: #f3f6fb;
    color: #111827;
}

body {
    overflow-x: hidden;
}


/* =========================================================
   OPENING ANIMATION
   ========================================================= */

#openingAnimation {

    position: fixed;

    inset: 0;

    z-index: 99999;

    display: flex;

    align-items: center;

    justify-content: center;

    flex-direction: column;

    background:
        linear-gradient(
            135deg,
            #06142f,
            #0b2b5c
        );

    color: white;

    opacity: 1;

    visibility: visible;

    transition:
        opacity .7s ease,
        visibility .7s ease;
}


#openingAnimation.hide {

    opacity: 0;

    visibility: hidden;

    pointer-events: none;
}


.opening-logo {

    font-size:
        clamp(
            70px,
            18vw,
            150px
        );

    font-weight: 900;

    letter-spacing: 5px;

    line-height: 1;

    animation:
        logoIn 1.2s ease forwards;
}


.opening-logo .k {
    color: #1976d2;
}

.opening-logo .o {
    color: #2e7d32;
}

.opening-logo .j {
    color: #d32f2f;
}

.opening-logo .a {
    color: #1565c0;
}


.opening-africa {

    margin-top: 15px;

    font-size: 20px;

    letter-spacing: 8px;

    font-weight: bold;

    opacity: 0;

    animation:
        africaIn 1s ease .5s forwards;
}


.opening-line {

    width: 0;

    height: 3px;

    margin-top: 22px;

    background: white;

    animation:
        lineIn 1s ease .9s forwards;
}


.opening-text {

    margin-top: 18px;

    font-size: 16px;

    opacity: 0;

    animation:
        textIn 1s ease 1.2s forwards;
}


@keyframes logoIn {

    from {
        opacity: 0;
        transform: scale(.7);
    }

    to {
        opacity: 1;
        transform: scale(1);
    }
}


@keyframes africaIn {

    from {
        opacity: 0;
        transform: translateY(15px);
    }

    to {
        opacity: 1;
        transform: translateY(0);
    }
}


@keyframes lineIn {

    from {
        width: 0;
    }

    to {
        width: 180px;
    }
}


@keyframes textIn {

    from {
        opacity: 0;
    }

    to {
        opacity: 1;
    }
}


/* =========================================================
   DARK BLUE TOP BAR
   ========================================================= */

.topbar {

    position: sticky;

    top: 0;

    z-index: 1000;

    background:
        #071a3d;

    border-bottom:
        1px solid
        rgba(255,255,255,.12);

    box-shadow:
        0 3px 15px
        rgba(0,0,0,.20);
}


.topbar-inner {

    max-width: 1250px;

    margin: auto;

    min-height: 74px;

    padding:
        12px 20px;

    display: flex;

    align-items: center;

    justify-content: space-between;

    gap: 15px;
}


/* =========================================================
   LOGO
   ========================================================= */

.logo {

    text-decoration: none;

    font-size: 31px;

    font-weight: 900;

    letter-spacing: 1px;

    color: white;
}


.logo .k {
    color: #42a5f5;
}

.logo .o {
    color: #66bb6a;
}

.logo .j {
    color: #ef5350;
}

.logo .a {
    color: #64b5f6;
}


.logo small {

    display: block;

    font-size: 8px;

    letter-spacing: 5px;

    color: #cbd5e1;

    text-align: center;

    margin-top: -2px;
}


/* =========================================================
   NAVIGATION
   ========================================================= */

.nav {

    display: flex;

    align-items: center;

    justify-content: flex-end;

    gap: 8px;

    flex-wrap: wrap;
}


.nav a {

    text-decoration: none;

    color: white;

    font-weight: 700;

    padding:
        10px 14px;

    border-radius: 8px;

    transition:
        .2s ease;
}


.nav a:hover {

    background:
        rgba(255,255,255,.10);
}


.nav .login-link {

    border:
        1px solid
        #60a5fa;

    color: #bfdbfe;
}


.nav .register-link {

    background:
        #1976d2;

    color: white;
}


.nav .register-link:hover {

    background:
        #1565c0;
}


/* =========================================================
   MAIN
   ========================================================= */

main {

    width: 100%;

    max-width: 1200px;

    margin: auto;

    padding:
        25px 18px 50px;
}


.hero,
.card {

    background: white;

    border-radius: 16px;

    padding: 25px;

    margin-bottom: 20px;

    box-shadow:
        0 8px 30px
        rgba(15,23,42,.06);
}


.hero {

    text-align: center;

    padding:
        65px 25px;
}


.hero h1 {

    font-size:
        clamp(
            35px,
            7vw,
            64px
        );

    margin:
        0 0 12px;
}


.hero p {

    max-width: 780px;

    margin:
        12px auto;

    line-height: 1.8;

    color: #475569;
}


.hero-actions {

    margin-top: 25px;
}


.btn,
button {

    display: inline-block;

    border: none;

    background:
        #1976d2;

    color: white;

    padding:
        12px 19px;

    border-radius: 9px;

    text-decoration: none;

    font-weight: 700;

    cursor: pointer;

    margin:
        5px 4px;
}


.btn:hover,
button:hover {

    opacity: .92;
}


.btn.green {

    background:
        #2e7d32;
}


.btn.dark {

    background:
        #071a3d;
}


.btn.red {

    background:
        #b91c1c;
}


.grid {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(210px, 1fr)
        );

    gap: 18px;

    margin-bottom: 25px;
}


.feature {

    background: white;

    padding: 25px;

    border-radius: 15px;

    box-shadow:
        0 7px 25px
        rgba(15,23,42,.05);
}


.feature h3 {

    margin-top: 0;
}


.feature p {

    line-height: 1.7;

    color: #64748b;
}


/* =========================================================
   FORMS
   ========================================================= */

input,
textarea,
select {

    width: 100%;

    padding: 13px;

    margin:
        7px 0 16px;

    border:
        1px solid #d1d5db;

    border-radius: 9px;

    font: inherit;
}


textarea {

    min-height: 180px;

    resize: vertical;
}


label {

    display: block;

    font-weight: 700;

    margin-top: 8px;
}


/* =========================================================
   TABLE
   ========================================================= */

.table-wrap {

    overflow-x: auto;
}


table {

    width: 100%;

    border-collapse:
        collapse;
}


th,
td {

    padding: 12px;

    border-bottom:
        1px solid #e5e7eb;

    text-align: left;

    vertical-align: top;
}


/* =========================================================
   ALERT
   ========================================================= */

.alert {

    max-width: 1200px;

    margin:
        15px auto;

    padding:
        13px 18px;

    border-radius: 9px;

    background:
        #dbeafe;

    color:
        #1e3a8a;
}


.alert.error {

    background:
        #fee2e2;

    color:
        #991b1b;
}


.alert.success {

    background:
        #dcfce7;

    color:
        #166534;
}


/* =========================================================
   QUESTION / ANSWER
   ========================================================= */

.question,
.answer {

    white-space:
        pre-wrap;

    line-height:
        1.7;

    padding:
        18px;

    border-radius:
        10px;

    background:
        #f8fafc;
}


.answer {

    border-left:
        4px solid
        #1976d2;
}


.badge {

    display:
        inline-block;

    padding:
        5px 10px;

    border-radius:
        20px;

    font-size:
        12px;

    font-weight:
        bold;
}


.badge.answered {

    background:
        #dcfce7;

    color:
        #166534;
}


.badge.pending {

    background:
        #fef3c7;

    color:
        #92400e;
}


/* =========================================================
   FOOTER
   ========================================================= */

footer {

    text-align:
        center;

    padding:
        35px 20px;

    color:
        #64748b;
}


/* =========================================================
   MOBILE
   ========================================================= */

@media (max-width: 650px) {

    .topbar-inner {

        align-items:
            flex-start;

        flex-direction:
            column;
    }

    .nav {

        width: 100%;

        justify-content:
            flex-start;
    }

    .nav a {

        font-size:
            14px;

        padding:
            8px 10px;
    }

    .hero,
    .card {

        padding:
            20px;
    }
}

</style>

</head>


<body>


<!-- ========================================================
     OPENING ANIMATION
     ======================================================== -->

<div id="openingAnimation">

    <div class="opening-logo">

        <span class="k">K</span>
        <span class="o">O</span>
        <span class="j">J</span>
        <span class="a">A</span>

    </div>

    <div class="opening-africa">
        AFRICA
    </div>

    <div class="opening-line"></div>

    <div class="opening-text">
        Knowledge • Questions • Answers
    </div>

</div>


<!-- ========================================================
     HEADER
     ======================================================== -->

<header class="topbar">

<div class="topbar-inner">


<a class="logo"
   href="{{ url_for('home') }}">

    <span class="k">k</span>
    <span class="o">o</span>
    <span class="j">j</span>
    <span class="a">a</span>

    <small>AFRICA</small>

</a>


<nav class="nav">


{% if session.get("user_id") %}


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

        <a href="{{ url_for('admin_users') }}">
            Users
        </a>

        <a href="{{ url_for('admin_logs') }}">
            Logs
        </a>

        <a href="{{ url_for('logout') }}">
            Logout
        </a>

    {% else %}

        <a href="{{ url_for('student_dashboard') }}">
            Dashboard
        </a>

        <a href="{{ url_for('ask_question') }}">
            Ask
        </a>

        <a href="{{ url_for('my_questions') }}">
            My Questions
        </a>

        <a href="{{ url_for('logout') }}">
            Logout
        </a>

    {% endif %}


{% else %}

    <!--
        PUBLIC USERS SEE ONLY THESE TWO LINKS.
        NO USERS.
        NO ANSWERS.
        NO QUESTIONS.
        NO LOGS.
        NO ADMIN.
    -->

    <a class="login-link"
       href="{{ url_for('login') }}">
        Log In
    </a>

    <a class="register-link"
       href="{{ url_for('register') }}">
        Create Account
    </a>

{% endif %}


</nav>

</div>

</header>


<!-- ========================================================
     FLASH MESSAGES
     ======================================================== -->

{% with messages =
        get_flashed_messages(
            with_categories=true
        )
%}

    {% for category, message in messages %}

        <div class="alert {{ category }}">
            {{ message }}
        </div>

    {% endfor %}

{% endwith %}


<!-- ========================================================
     CONTENT
     ======================================================== -->

<main>

    {{ content|safe }}

</main>


<!-- ========================================================
     FOOTER
     ======================================================== -->

<footer>

    <strong>
        KOJA AFRICA
    </strong>

    <br>

    Knowledge • Questions • Answers

    <br><br>

    Academic Questions • Assignments • Research

</footer>


<!-- ========================================================
     OPENING ANIMATION SCRIPT
     ======================================================== -->

<script>

(function () {

    const animation =
        document.getElementById(
            "openingAnimation"
        );

    if (!animation) {
        return;
    }


    let alreadyPlayed = false;


    try {

        alreadyPlayed =
            sessionStorage.getItem(
                "koja_opening_played"
            ) === "1";

    } catch (error) {

        alreadyPlayed = false;

    }


    if (alreadyPlayed) {

        animation.classList.add(
            "hide"
        );

        return;

    }


    try {

        sessionStorage.setItem(
            "koja_opening_played",
            "1"
        );

    } catch (error) {
        // Continue normally.
    }


    setTimeout(
        function () {

            animation.classList.add(
                "hide"
            );

        },
        3500
    );

})();

</script>


</body>

</html>
"""


# ============================================================
# RENDER HELPER
# ============================================================

def render_page(
    content,
    title="Home"
):

    return render_template_string(
        HTML,
        content=content,
        title=title,
        site_description=SITE_DESCRIPTION
    )


# ============================================================
# PUBLIC HOME
# ============================================================

@app.route("/")
def home():

    # IMPORTANT:
    # The public homepage does NOT retrieve or display
    # registered users, private questions or answers.

    content = """
    <section class="hero">

        <h1>
            KOJA AFRICA
        </h1>

        <p>
            Knowledge • Questions • Answers
        </p>

        <p>
            A digital academic platform for
            assignments, questions, research
            and learning.
        </p>

        <div class="hero-actions">

            <a class="btn"
               href="/login">
                Log In
            </a>

            <a class="btn green"
               href="/register">
                Create Account
            </a>

        </div>

    </section>


    <section class="grid">

        <div class="feature">

            <h3>
                Academic Questions
            </h3>

            <p>
                Submit your academic question
                privately and receive an answer
                through your KOJA account.
            </p>

        </div>


        <div class="feature">

            <h3>
                Assignments
            </h3>

            <p>
                Upload assignment questions
                and supporting documents
                securely.
            </p>

        </div>


        <div class="feature">

            <h3>
                Research
            </h3>

            <p>
                Use KOJA as a learning and
                academic research platform.
            </p>

        </div>


        <div class="feature">

            <h3>
                Private Answers
            </h3>

            <p>
                Your submitted questions and
                answers are associated with
                your account.
            </p>

        </div>

    </section>
    """

    return render_page(
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
            "confirm_password",
            ""
        )

        if not name:
            flash(
                "Enter your name.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if not email:
            flash(
                "Enter your email.",
                "error"
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 8:
            flash(
                "Password must contain at least 8 characters.",
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

        users = get_users()

        for user in users:

            if user.get("email") == email:

                flash(
                    "An account with that email already exists.",
                    "error"
                )

                return redirect(
                    url_for("register")
                )


        user = {

            "id":
                str(uuid.uuid4()),

            "name":
                name,

            "email":
                email,

            "password":
                hash_password(
                    password
                ),

            "role":
                "student",

            "created_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "active":
                True
        }


        users.append(
            user
        )

        save_users(
            users
        )


        log_event(
            "New Student Account Created",
            "Authentication",
            "INFO",
            email
        )


        flash(
            "Account created successfully. You can now log in.",
            "success"
        )

        return redirect(
            url_for("login")
        )


    content = """

    <section class="card">

        <h1>Create Account</h1>

        <p class="muted">
            Create your private KOJA Africa
            student account.
        </p>

        <form method="POST">

            <label>
                Full Name
            </label>

            <input
                type="text"
                name="name"
                required
            >


            <label>
                Email Address
            </label>

            <input
                type="email"
                name="email"
                required
            >


            <label>
                Password
            </label>

            <input
                type="password"
                name="password"
                minlength="8"
                required
            >


            <label>
                Confirm Password
            </label>

            <input
                type="password"
                name="confirm_password"
                minlength="8"
                required
            >


            <button type="submit">
                Create Account
            </button>

        </form>

    </section>

    """

    return render_page(
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

        users = get_users()

        user_found = None

        for user in users:

            if (
                user.get("email")
                == email
                and
                user.get("active", True)
            ):

                user_found = user
                break


        if (
            not user_found
            or
            not verify_password(
                password,
                user_found.get(
                    "password",
                    ""
                )
            )
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

        session["user_id"] = \
            user_found["id"]

        session["email"] = \
            user_found["email"]

        session["role"] = \
            user_found["role"]

        session["name"] = \
            user_found["name"]


        log_event(
            "Successful Login",
            "Authentication",
            "INFO",
            email
        )


        if user_found["role"] == "admin":

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

    <section class="card">

        <h1>Log In</h1>

        <p class="muted">
            Access your private KOJA account.
        </p>

        <form method="POST">

            <label>
                Email Address
            </label>

            <input
                type="email"
                name="email"
                required
            >


            <label>
                Password
            </label>

            <input
                type="password"
                name="password"
                required
            >


            <button type="submit">
                Log In
            </button>

        </form>

    </section>

    """

    return render_page(
        content,
        "Log In"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    if session.get("user_id"):

        log_event(
            "Logout",
            "Authentication",
            "INFO"
        )

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# STUDENT DASHBOARD
# ============================================================

@app.route(
    "/student/dashboard"
)
@login_required
def student_dashboard():

    if is_admin_session():

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )


    user_id = session.get(
        "user_id"
    )

    questions = [

        q for q in get_questions()

        if q.get("student_id")
        == user_id

    ]


    answered = sum(
        1
        for q in questions
        if q.get("answer")
    )


    content = f"""

    <section class="hero">

        <h1>
            Welcome, {session.get("name")}
        </h1>

        <p>
            Your KOJA Africa academic workspace.
        </p>

        <a class="btn"
           href="/student/ask">
            Ask a Question
        </a>

        <a class="btn dark"
           href="/student/questions">
            My Questions
        </a>

    </section>


    <section class="grid">

        <div class="feature">

            <h3>
                My Questions
            </h3>

            <h2>
                {len(questions)}
            </h2>

        </div>


        <div class="feature">

            <h3>
                Answered
            </h3>

            <h2>
                {answered}
            </h2>

        </div>


        <div class="feature">

            <h3>
                Pending
            </h3>

            <h2>
                {len(questions) - answered}
            </h2>

        </div>

    </section>

    """

    return render_page(
        content,
        "Student Dashboard"
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

    if is_admin_session():

        abort(403)


    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        question_text = request.form.get(
            "question",
            ""
        ).strip()


        if not subject:

            flash(
                "Enter the subject.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )


        if not question_text:

            flash(
                "Enter your question.",
                "error"
            )

            return redirect(
                url_for("ask_question")
            )


        question_id = str(
            uuid.uuid4()
        )


        attachments = []


        uploaded = request.files.getlist(
            "files"
        )


        for file in uploaded:

            if not file:
                continue

            if not file.filename:
                continue

            if not allowed_file(
                file.filename
            ):

                flash(
                    "One of the uploaded files is not allowed.",
                    "error"
                )

                return redirect(
                    url_for("ask_question")
                )


            original_name = \
                secure_filename(
                    file.filename
                )


            stored_name = (
                question_id
                + "_"
                + str(uuid.uuid4())
                + "_"
                + original_name
            )


            file.save(
                os.path.join(
                    STUDENT_UPLOAD_DIR,
                    stored_name
                )
            )


            attachments.append({

                "original_name":
                    original_name,

                "stored_name":
                    stored_name

            })


        question = {

            "id":
                question_id,

            "student_id":
                session.get(
                    "user_id"
                ),

            "subject":
                subject,

            "question":
                question_text,

            "attachments":
                attachments,

            "answer":
                "",

            "answer_attachments":
                [],

            "status":
                "Pending",

            "created_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "answered_at":
                None
        }


        questions = get_questions()

        questions.append(
            question
        )

        save_questions(
            questions
        )


        log_event(
            "Question Submitted",
            "Questions",
            "INFO",
            question_id
        )


        flash(
            "Your question has been submitted privately.",
            "success"
        )


        return redirect(
            url_for(
                "my_questions"
            )
        )


    content = """

    <section class="card">

        <h1>
            Ask KOJA
        </h1>

        <p class="muted">
            Your question is private.
            It will not be displayed on the
            public homepage.
        </p>


        <form method="POST"
              enctype="multipart/form-data">


            <label>
                Subject
            </label>

            <input
                type="text"
                name="subject"
                placeholder="e.g. Chemistry"
                required
            >


            <label>
                Question / Assignment
            </label>

            <textarea
                name="question"
                placeholder="Write your question here..."
                required
            ></textarea>


            <label>
                Attachments
            </label>

            <input
                type="file"
                name="files"
                multiple
            >


            <button type="submit">
                Submit Question
            </button>

        </form>

    </section>

    """

    return render_page(
        content,
        "Ask Question"
    )


# ============================================================
# MY QUESTIONS
# ============================================================

@app.route(
    "/student/questions"
)
@login_required
def my_questions():

    if is_admin_session():

        abort(403)


    user_id = session.get(
        "user_id"
    )


    questions = [

        q for q in get_questions()

        if q.get("student_id")
        == user_id

    ]


    cards = ""


    for q in reversed(
        questions
    ):

        status = q.get(
            "status",
            "Pending"
        )


        status_class = (
            "answered"
            if q.get("answer")
            else "pending"
        )


        answer_html = ""


        if q.get("answer"):

            answer_html = f"""

            <div class="answer">

                <strong>
                    KOJA Answer
                </strong>

                <br><br>

                {q.get("answer")}

            </div>

            """


        attachment_html = ""


        for attachment in q.get(
            "attachments",
            []
        ):

            stored_name = \
                attachment.get(
                    "stored_name"
                )


            attachment_html += f"""

            <p>

                <a
                  href="/student/file/{q['id']}/student/{stored_name}"
                  target="_blank">

                    View Attachment

                </a>

            </p>

            """


        cards += f"""

        <div class="card">

            <span class="badge {status_class}">
                {status}
            </span>

            <h2>
                {q.get("subject")}
            </h2>

            <p>
                <strong>
                    Question
                </strong>
            </p>

            <div class="question">
                {q.get("question")}
            </div>

            {attachment_html}

            <br>

            {answer_html}

        </div>

        """


    if not cards:

        cards = """

        <section class="card">

            <h2>
                No questions yet.
            </h2>

            <p>
                Submit your first academic
                question to KOJA Africa.
            </p>

            <a class="btn"
               href="/student/ask">
                Ask a Question
            </a>

        </section>

        """


    content = f"""

    <h1>
        My Questions
    </h1>

    {cards}

    """


    return render_page(
        content,
        "My Questions"
    )


# ============================================================
# STUDENT PRIVATE FILE
# ============================================================

@app.route(
    "/student/file/<question_id>/<category>/<filename>"
)
@login_required
def student_file(
    question_id,
    category,
    filename
):

    if is_admin_session():

        return redirect(
            url_for(
                "admin_file",
                category=category,
                filename=filename
            )
        )


    question = find_question(
        question_id
    )


    if not question:

        abort(404)


    if (
        question.get("student_id")
        !=
        session.get("user_id")
    ):

        log_event(
            "Unauthorized File Access",
            "Security",
            "WARNING",
            question_id
        )

        abort(403)


    if category == "student":

        attachments = \
            question.get(
                "attachments",
                []
            )

        directory = \
            STUDENT_UPLOAD_DIR


    elif category == "admin":

        attachments = \
            question.get(
                "answer_attachments",
                []
            )

        directory = \
            ADMIN_UPLOAD_DIR


    else:

        abort(404)


    for attachment in attachments:

        if (
            attachment.get(
                "stored_name"
            )
            ==
            filename
        ):

            return send_from_directory(
                directory,
                filename
            )


    abort(404)


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route(
    "/admin"
)
@admin_required
def admin_dashboard():

    users = get_users()

    questions = get_questions()

    answered = sum(
        1
        for q in questions
        if q.get("answer")
    )


    content = f"""

    <section class="hero">

        <h1>
            KOJA ADMIN
        </h1>

        <p>
            Protected administration area.
        </p>

    </section>


    <section class="grid">

        <div class="feature">

            <h3>
                Registered Users
            </h3>

            <h2>
                {len(users)}
            </h2>

        </div>


        <div class="feature">

            <h3>
                Questions
            </h3>

            <h2>
                {len(questions)}
            </h2>

        </div>


        <div class="feature">

            <h3>
                Answered
            </h3>

            <h2>
                {answered}
            </h2>

        </div>


        <div class="feature">

            <h3>
                Pending
            </h3>

            <h2>
                {len(questions) - answered}
            </h2>

        </div>

    </section>

    """


    return render_page(
        content,
        "Admin Dashboard"
    )


# ============================================================
# ADMIN QUESTIONS
# ============================================================

@app.route(
    "/admin/questions"
)
@admin_required
def admin_questions():

    questions = get_questions()

    rows = ""


    for q in reversed(
        questions
    ):

        student = find_user(
            q.get("student_id")
        )


        student_name = (
            student.get("name")
            if student
            else "Unknown"
        )


        status = q.get(
            "status",
            "Pending"
        )


        rows += f"""

        <tr>

            <td>
                {student_name}
            </td>

            <td>
                {q.get("subject")}
            </td>

            <td>
                {q.get("question")[:120]}
            </td>

            <td>
                {status}
            </td>

            <td>

                <a class="btn small"
                   href="/admin/question/{q['id']}">

                    Open

                </a>

            </td>

        </tr>

        """


    content = f"""

    <section class="card">

        <h1>
            Student Questions
        </h1>

        <div class="table-wrap">

            <table>

                <thead>

                    <tr>

                        <th>
                            Student
                        </th>

                        <th>
                            Subject
                        </th>

                        <th>
                            Question
                        </th>

                        <th>
                            Status
                        </th>

                        <th>
                            Action
                        </th>

                    </tr>

                </thead>

                <tbody>

                    {rows}

                </tbody>

            </table>

        </div>

    </section>

    """


    return render_page(
        content,
        "Questions"
    )


# ============================================================
# ADMIN QUESTION
# ============================================================

@app.route(
    "/admin/question/<question_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_question(
    question_id
):

    questions = get_questions()

    question = None

    for q in questions:

        if q.get("id") == question_id:

            question = q
            break


    if not question:

        abort(404)


    if request.method == "POST":

        answer = request.form.get(
            "answer",
            ""
        ).strip()


        question["answer"] = \
            answer

        question["status"] = \
            "Answered" \
            if answer \
            else "Pending"


        question["answered_at"] = (
            datetime.now(
                timezone.utc
            ).isoformat()
            if answer
            else None
        )


        uploaded = request.files.getlist(
            "files"
        )


        answer_attachments = []


        for file in uploaded:

            if not file:
                continue

            if not file.filename:
                continue

            if not allowed_file(
                file.filename
            ):

                flash(
                    "Invalid answer attachment.",
                    "error"
                )

                return redirect(
                    url_for(
                        "admin_question",
                        question_id=question_id
                    )
                )


            original_name = \
                secure_filename(
                    file.filename
                )


            stored_name = (
                question_id
                + "_"
                + str(uuid.uuid4())
                + "_"
                + original_name
            )


            file.save(
                os.path.join(
                    ADMIN_UPLOAD_DIR,
                    stored_name
                )
            )


            answer_attachments.append({

                "original_name":
                    original_name,

                "stored_name":
                    stored_name

            })


        question[
            "answer_attachments"
        ] = answer_attachments


        save_questions(
            questions
        )


        log_event(
            "Question Answered",
            "Questions",
            "INFO",
            question_id
        )


        flash(
            "Answer saved successfully.",
            "success"
        )


        return redirect(
            url_for(
                "admin_question",
                question_id=question_id
            )
        )


    student = find_user(
        question.get(
            "student_id"
        )
    )


    student_name = (
        student.get("name")
        if student
        else "Unknown"
    )


    attachment_html = ""


    for attachment in question.get(
        "attachments",
        []
    ):

        filename = \
            attachment.get(
                "stored_name"
            )


        attachment_html += f"""

        <p>

            <a
              href="/admin/file/student/{filename}"
              target="_blank">

                View Student Attachment

            </a>

        </p>

        """


    content = f"""

    <section class="card">

        <h1>
            Question
        </h1>

        <p>
            <strong>
                Student:
            </strong>

            {student_name}
        </p>

        <p>
            <strong>
                Subject:
            </strong>

            {question.get("subject")}
        </p>


        <div class="question">

            {question.get("question")}

        </div>


        {attachment_html}

    </section>


    <section class="card">

        <h2>
            Answer
        </h2>


        <form method="POST"
              enctype="multipart/form-data">

            <textarea
                name="answer"
                placeholder="Write the academic answer..."
            >{question.get("answer", "")}</textarea>


            <label>
                Answer Attachments
            </label>

            <input
                type="file"
                name="files"
                multiple
            >


            <button type="submit">
                Save Answer
            </button>

        </form>

    </section>

    """


    return render_page(
        content,
        "Answer Question"
    )


# ============================================================
# ADMIN ANSWERS
# ============================================================

@app.route(
    "/admin/answers"
)
@admin_required
def admin_answers():

    questions = [

        q for q in get_questions()

        if q.get("answer")

    ]


    rows = ""


    for q in reversed(
        questions
    ):

        student = find_user(
            q.get("student_id")
        )


        name = (
            student.get("name")
            if student
            else "Unknown"
        )


        rows += f"""

        <tr>

            <td>
                {name}
            </td>

            <td>
                {q.get("subject")}
            </td>

            <td>
                {q.get("answer")[:150]}
            </td>

            <td>

                <a class="btn small"
                   href="/admin/question/{q['id']}">

                    Open

                </a>

            </td>

        </tr>

        """


    content = f"""

    <section class="card">

        <h1>
            Answers
        </h1>

        <div class="table-wrap">

            <table>

                <thead>

                    <tr>

                        <th>
                            Student
                        </th>

                        <th>
                            Subject
                        </th>

                        <th>
                            Answer
                        </th>

                        <th>
                            Action
                        </th>

                    </tr>

                </thead>

                <tbody>

                    {rows}

                </tbody>

            </table>

        </div>

    </section>

    """


    return render_page(
        content,
        "Answers"
    )


# ============================================================
# ADMIN USERS
# ============================================================

@app.route(
    "/admin/users"
)
@admin_required
def admin_users():

    users = get_users()

    rows = ""


    for user in users:

        rows += f"""

        <tr>

            <td>
                {user.get("name")}
            </td>

            <td>
                {user.get("email")}
            </td>

            <td>
                {user.get("role")}
            </td>

            <td>
                {"Active" if user.get("active") else "Disabled"}
            </td>

        </tr>

        """


    content = f"""

    <section class="card">

        <h1>
            Registered Users
        </h1>

        <div class="table-wrap">

            <table>

                <thead>

                    <tr>

                        <th>
                            Name
                        </th>

                        <th>
                            Email
                        </th>

                        <th>
                            Role
                        </th>

                        <th>
                            Status
                        </th>

                    </tr>

                </thead>

                <tbody>

                    {rows}

                </tbody>

            </table>

        </div>

    </section>

    """


    return render_page(
        content,
        "Users"
    )


# ============================================================
# ADMIN LOGS
# ============================================================

@app.route(
    "/admin/logs"
)
@admin_required
def admin_logs():

    logs = get_logs()

    rows = ""


    for log in reversed(
        logs[-300:]
    ):

        rows += f"""

        <tr>

            <td>
                {log.get("timestamp")}
            </td>

            <td>
                {log.get("level")}
            </td>

            <td>
                {log.get("event")}
            </td>

            <td>
                {log.get("category")}
            </td>

            <td>
                {log.get("details")}
            </td>

        </tr>

        """


    content = f"""

    <section class="card">

        <h1>
            KOJA System Logs
        </h1>

        <div class="table-wrap">

            <table>

                <thead>

                    <tr>

                        <th>
                            Time
                        </th>

                        <th>
                            Level
                        </th>

                        <th>
                            Event
                        </th>

                        <th>
                            Category
                        </th>

                        <th>
                            Details
                        </th>

                    </tr>

                </thead>

                <tbody>

                    {rows}

                </tbody>

            </table>

        </div>

    </section>

    """


    return render_page(
        content,
        "Logs"
    )


# ============================================================
# ADMIN FILE
# ============================================================

@app.route(
    "/admin/file/<category>/<filename>"
)
@admin_required
def admin_file(
    category,
    filename
):

    if category == "student":

        directory = \
            STUDENT_UPLOAD_DIR

    elif category == "admin":

        directory = \
            ADMIN_UPLOAD_DIR

    else:

        abort(404)


    log_event(
        "Admin File Viewed",
        "Storage",
        "INFO",
        f"{category}/{filename}"
    )


    return send_from_directory(
        directory,
        filename
    )


# ============================================================
# ERROR PAGES
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    content = """

    <section class="hero">

        <h1>
            403
        </h1>

        <p>
            Access denied.
        </p>

        <a class="btn"
           href="/">
            Return Home
        </a>

    </section>

    """

    return render_page(
        content,
        "Access Denied"
    ), 403


@app.errorhandler(404)
def not_found(error):

    content = """

    <section class="hero">

        <h1>
            404
        </h1>

        <p>
            The requested page was not found.
        </p>

        <a class="btn"
           href="/">
            Return Home
        </a>

    </section>

    """

    return render_page(
        content,
        "Page Not Found"
    ), 404


@app.errorhandler(413)
def file_too_large(error):

    flash(
        "The uploaded file is too large. Maximum size is 10 MB.",
        "error"
    )

    return redirect(
        request.referrer
        or
        url_for("home")
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

    response.headers[
        "Permissions-Policy"
    ] = (
        "geolocation=(), "
        "microphone=(), "
        "camera=()"
    )

    return response


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

    print(
        "KOJA AFRICA"
    )

    print(
        "Knowledge • Questions • Answers"
    )

    print(
        "Public Page: ENABLED"
    )

    print(
        "Public User List: HIDDEN"
    )

    print(
        "Public Questions: HIDDEN"
    )

    print(
        "Public Answers: HIDDEN"
    )

    print(
        "Student Questions: PRIVATE"
    )

    print(
        "Student Answers: PRIVATE"
    )

    print(
        "Admin Dashboard: PROTECTED"
    )

    print(
        "Admin Logs: PROTECTED"
    )

    print(
        "Dark Blue Header: ENABLED"
    )

    print(
        "Opening Animation: ENABLED"
    )

    print(
        "Port:",
        port
    )

    print("=" * 60)


    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
