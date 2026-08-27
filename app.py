import os
import io
import uuid
import secrets
import logging

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

from functools import wraps

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://YOUR-PROJECT.supabase.co"
).rstrip("/")

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
)

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    secrets.token_hex(32)
)

ADMIN_UUID = os.getenv(
    "ADMIN_UUID",
    "fea4ac9a-97a1-4fcf-b5cb-870843dc48dd"
)

# YOUR EXISTING SUPABASE BUCKET
STORAGE_BUCKET = os.getenv(
    "STORAGE_BUCKET",
    "koja-files"
)

MAX_FILE_SIZE = int(
    os.getenv(
        "MAX_FILE_SIZE",
        "10485760"
    )
)

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
}


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = SECRET_KEY

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("koja")


# ============================================================
# SUPABASE
# ============================================================

def supabase_headers():

    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": (
            f"Bearer {SUPABASE_SERVICE_KEY}"
        ),
        "Content-Type": "application/json",
    }


def storage_headers(content_type=None):

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": (
            f"Bearer {SUPABASE_SERVICE_KEY}"
        ),
    }

    if content_type:
        headers["Content-Type"] = content_type

    return headers


def supabase_get(table, params=None):

    return requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=supabase_headers(),
        params=params or {},
        timeout=30,
    )


def supabase_post(table, data):

    headers = supabase_headers()

    headers["Prefer"] = "return=representation"

    return requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        json=data,
        timeout=30,
    )


def supabase_patch(table, filters, data):

    params = {}

    for key, value in filters.items():

        params[key] = f"eq.{value}"

    headers = supabase_headers()

    headers["Prefer"] = "return=representation"

    return requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=params,
        json=data,
        timeout=30,
    )


def supabase_delete(table, filters):

    params = {}

    for key, value in filters.items():

        params[key] = f"eq.{value}"

    return requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=supabase_headers(),
        params=params,
        timeout=30,
    )


# ============================================================
# AUTH
# ============================================================

def auth_signup(email, password):

    return requests.post(
        f"{SUPABASE_URL}/auth/v1/signup",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
        },
        json={
            "email": email,
            "password": password,
        },
        timeout=30,
    )


def auth_login(email, password):

    return requests.post(
        f"{SUPABASE_URL}/auth/v1/token"
        "?grant_type=password",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
        },
        json={
            "email": email,
            "password": password,
        },
        timeout=30,
    )


def auth_user(access_token):

    return requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": (
                f"Bearer {access_token}"
            ),
        },
        timeout=30,
    )


# ============================================================
# USER
# ============================================================

def current_user():

    return session.get("user")


def is_logged_in():

    return current_user() is not None


def is_admin():

    user = current_user()

    if not user:
        return False

    return (
        str(user.get("id"))
        ==
        str(ADMIN_UUID)
    )


# ============================================================
# DECORATORS
# ============================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not is_logged_in():

            flash(
                "Please log in first.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        return function(*args, **kwargs)

    return wrapper


def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not is_logged_in():

            flash(
                "Please log in first.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        if not is_admin():

            abort(403)

        return function(*args, **kwargs)

    return wrapper


# ============================================================
# PROFILE
# ============================================================

def get_profile(user_id):

    response = supabase_get(
        "profiles",
        {
            "id": f"eq.{user_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if response.status_code != 200:
        return None

    rows = response.json()

    return rows[0] if rows else None


def ensure_profile(user_id, email):

    profile = get_profile(user_id)

    if profile:
        return profile

    role = (
        "admin"
        if str(user_id) == str(ADMIN_UUID)
        else "student"
    )

    response = supabase_post(
        "profiles",
        {
            "id": user_id,
            "name": email.split("@")[0],
            "email": email,
            "role": role,
        }
    )

    if response.status_code not in (200, 201):

        logger.error(
            "Profile creation failed: %s",
            response.text
        )

        return None

    rows = response.json()

    return rows[0] if rows else None


# ============================================================
# DOCUMENTS
# ============================================================

DOCUMENT_TYPES = [
    ("academic", "Academic"),
    ("assignment", "Assignment"),
    ("notes", "Notes"),
    ("past_paper", "Past Paper"),
    ("report", "Report"),
    ("answer", "Answer"),
    ("announcement", "Announcement"),
    ("other", "Other"),
]


def get_documents(search=""):

    response = supabase_get(
        "documents",
        {
            "select": "*",
            "is_active": "eq.true",
            "order": "created_at.desc",
        }
    )

    if response.status_code != 200:

        logger.error(
            "Documents error: %s",
            response.text
        )

        return []

    documents = response.json()

    search = search.strip().lower()

    if not search:
        return documents

    results = []

    for doc in documents:

        text = " ".join([
            str(doc.get("title", "")),
            str(doc.get("description", "")),
            str(doc.get("subject", "")),
            str(doc.get("course", "")),
            str(doc.get("class_level", "")),
            str(doc.get("document_type", "")),
        ]).lower()

        if search in text:
            results.append(doc)

    return results


def get_document(document_id):

    response = supabase_get(
        "documents",
        {
            "id": f"eq.{document_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if response.status_code != 200:
        return None

    rows = response.json()

    return rows[0] if rows else None


# ============================================================
# ACTIVITY
# ============================================================

def create_document_record(
    document_id,
    user_id,
    action
):

    try:

        ip_address = request.headers.get(
            "X-Forwarded-For",
            request.remote_addr
        )

        user_agent = request.headers.get(
            "User-Agent",
            ""
        )

        return supabase_post(
            "document_records",
            {
                "document_id": document_id,
                "user_id": user_id,
                "action": action,
                "ip_address": ip_address,
                "user_agent": user_agent,
            }
        )

    except Exception as exc:

        logger.warning(
            "Activity record failed: %s",
            exc
        )

        return None


# ============================================================
# STORAGE
# ============================================================

def upload_to_storage(file_storage):

    original_name = file_storage.filename

    if not original_name:
        raise ValueError(
            "No file selected."
        )

    extension = os.path.splitext(
        original_name
    )[1].lower()

    if extension not in ALLOWED_EXTENSIONS:

        raise ValueError(
            "Unsupported file type."
        )

    content = file_storage.read()

    if not content:
        raise ValueError(
            "The selected file is empty."
        )

    if len(content) > MAX_FILE_SIZE:

        raise ValueError(
            "File is larger than 10 MB."
        )

    safe_name = (
        uuid.uuid4().hex
        + extension
    )

    file_path = (
        f"documents/{safe_name}"
    )

    content_type = (
        file_storage.mimetype
        or "application/octet-stream"
    )

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{file_path}"
    )

    response = requests.post(
        url,
        headers=storage_headers(
            content_type
        ),
        data=content,
        timeout=120,
    )

    if response.status_code not in (
        200,
        201
    ):

        raise RuntimeError(
            "Storage upload failed: "
            + response.text
        )

    return {
        "file_path": file_path,
        "file_name": original_name,
        "file_size": len(content),
        "mime_type": content_type,
    }


def download_from_storage(file_path):

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{file_path}"
    )

    return requests.get(
        url,
        headers=storage_headers(),
        timeout=120,
    )


def delete_from_storage(file_path):

    url = (
        f"{SUPABASE_URL}"
        f"/storage/v1/object/"
        f"{STORAGE_BUCKET}/"
        f"{file_path}"
    )

    return requests.delete(
        url,
        headers=storage_headers(),
        timeout=60,
    )


# ============================================================
# COUNTERS
# ============================================================

def increment_document_counter(
    document_id,
    field
):

    if field not in (
        "view_count",
        "download_count",
    ):
        return

    document = get_document(
        document_id
    )

    if not document:
        return

    current = int(
        document.get(field, 0) or 0
    )

    supabase_patch(
        "documents",
        {"id": document_id},
        {
            field: current + 1
        }
    )


# ============================================================
# QUESTIONS
# ============================================================

def get_questions():

    response = supabase_get(
        "questions",
        {
            "select": "*",
            "order": "created_at.desc",
        }
    )

    if response.status_code != 200:

        logger.error(
            "Questions error: %s",
            response.text
        )

        return []

    questions = response.json()

    for question in questions:

        answer_response = supabase_get(
            "answers",
            {
                "question_id":
                    f"eq.{question['id']}",
                "select": "*",
                "order": "created_at.desc",
                "limit": "1",
            }
        )

        if answer_response.status_code == 200:

            answers = answer_response.json()

            question["answer"] = (
                answers[0]
                if answers
                else None
            )

        else:

            question["answer"] = None

    return questions


def get_question(question_id):

    response = supabase_get(
        "questions",
        {
            "id": f"eq.{question_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if response.status_code != 200:
        return None

    rows = response.json()

    if not rows:
        return None

    question = rows[0]

    answer_response = supabase_get(
        "answers",
        {
            "question_id":
                f"eq.{question_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": "1",
        }
    )

    if answer_response.status_code == 200:

        answers = answer_response.json()

        question["answer"] = (
            answers[0]
            if answers
            else None
        )

    else:

        question["answer"] = None

    return question


# ============================================================
# ASSIGNMENTS
# ============================================================

def get_assignments():

    response = supabase_get(
        "assignments",
        {
            "select": "*",
            "order": "created_at.desc",
        }
    )

    if response.status_code != 200:

        logger.error(
            "Assignments error: %s",
            response.text
        )

        return []

    return response.json()


# ============================================================
# MAIN TEMPLATE
# ============================================================

BASE_TEMPLATE = """
<!doctype html>

<html>

<head>

<meta charset="utf-8">

<meta name="viewport"
content="width=device-width,initial-scale=1">

<title>{{ title }} | KOJA AFRICA</title>

<style>

*{
    box-sizing:border-box;
}

body{
    margin:0;
    font-family:Arial,Helvetica,sans-serif;
    background:#f3f6fb;
    color:#172033;
}

nav{
    background:#0b3366;
    color:white;
    padding:15px 5%;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:18px;
    flex-wrap:wrap;
}

.logo{
    font-size:34px;
    font-weight:900;
    letter-spacing:-3px;
}

.logo span:nth-child(1){
    color:#1687ff;
}

.logo span:nth-child(2){
    color:#20c777;
}

.logo span:nth-child(3){
    color:#e73545;
}

.logo span:nth-child(4){
    color:#5b7fce;
}

.navlinks{
    display:flex;
    gap:15px;
    flex-wrap:wrap;
}

.navlinks a{
    color:white;
    text-decoration:none;
    font-weight:700;
    padding:8px;
}

.container{
    width:92%;
    max-width:1200px;
    margin:28px auto;
}

.hero{
    background:#0b3366;
    color:white;
    padding:42px;
    border-radius:22px;
    margin-bottom:24px;
}

.hero h1{
    font-size:38px;
    margin-top:0;
}

.card{
    background:white;
    padding:24px;
    border-radius:20px;
    margin-bottom:22px;
    box-shadow:0 5px 20px rgba(0,0,0,.07);
}

.grid{
    display:grid;
    grid-template-columns:
    repeat(auto-fit,minmax(260px,1fr));
    gap:20px;
}

.document{
    background:white;
    padding:22px;
    border-radius:18px;
    box-shadow:0 4px 15px rgba(0,0,0,.06);
}

.document h3{
    margin-top:8px;
}

.badge{
    display:inline-block;
    padding:6px 10px;
    border-radius:20px;
    background:#e8f1ff;
    color:#0b4f99;
    font-size:12px;
    font-weight:bold;
}

input,
textarea,
select{
    width:100%;
    padding:13px;
    border:1px solid #d4dce8;
    border-radius:10px;
    margin-top:7px;
    margin-bottom:16px;
    font-size:16px;
}

textarea{
    min-height:130px;
}

button,
.btn{
    display:inline-block;
    border:0;
    border-radius:10px;
    padding:12px 17px;
    background:#0b3366;
    color:white;
    text-decoration:none;
    font-weight:bold;
    cursor:pointer;
}

.btn.green{
    background:#168a55;
}

.btn.red{
    background:#c62828;
}

.btn.gray{
    background:#68758a;
}

.btn.orange{
    background:#d97706;
}

.actions{
    display:flex;
    gap:8px;
    flex-wrap:wrap;
}

.alert{
    padding:15px;
    border-radius:12px;
    margin-bottom:18px;
    background:#fff1d6;
    color:#704800;
}

.answer{
    background:#eefaf3;
    border-left:5px solid #168a55;
    padding:18px;
    border-radius:10px;
    margin-top:15px;
}

.question{
    background:#f8faff;
    padding:18px;
    border-radius:12px;
    border-left:5px solid #0b3366;
}

.stat{
    font-size:30px;
    font-weight:900;
}

.small{
    color:#68758a;
    font-size:14px;
}

.table-wrap{
    overflow-x:auto;
}

table{
    width:100%;
    border-collapse:collapse;
}

th,td{
    padding:12px;
    border-bottom:1px solid #e3e8ef;
    text-align:left;
}

footer{
    text-align:center;
    padding:35px;
    color:#68758a;
}

@media(max-width:600px){

    .hero{
        padding:28px;
    }

    .hero h1{
        font-size:29px;
    }

    .navlinks{
        width:100%;
    }

}

</style>

</head>

<body>

<nav>

<div class="logo">
<span>k</span><span>o</span><span>j</span><span>a</span>
</div>

<div class="navlinks">

<a href="{{ url_for('home') }}">
Home
</a>

{% if session.get('user') %}

<a href="{{ url_for('documents') }}">
Documents
</a>

<a href="{{ url_for('questions') }}">
Ask Question
</a>

<a href="{{ url_for('assignments') }}">
Assignments
</a>

{% if session.get('is_admin') %}

<a href="{{ url_for('admin') }}">
Admin
</a>

<a href="{{ url_for('upload_document') }}">
Upload
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

</nav>

<div class="container">

{% with messages =
get_flashed_messages(with_categories=true) %}

{% for category,message in messages %}

<div class="alert">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ content|safe }}

</div>

<footer>
KOJA AFRICA
<br>
Knowledge • Questions • Answers
<br>
Academic Documents & Learning Resources
</footer>

</body>

</html>
"""


def render_page(title, content, **context):

    return render_template_string(
        BASE_TEMPLATE,
        title=title,
        content=render_template_string(
            content,
            **context
        ),
        **context
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_page(
        "Home",
        """
        <div class="hero">

        <h1>KOJA AFRICA</h1>

        <p>
        Knowledge • Questions • Answers
        </p>

        <p>
        Ask academic questions, submit assignments,
        access notes, past papers and learning resources.
        </p>

        {% if not session.get('user') %}

        <div class="actions">

        <a class="btn"
        href="{{ url_for('login') }}">
        Login
        </a>

        <a class="btn green"
        href="{{ url_for('register') }}">
        Create Account
        </a>

        </div>

        {% else %}

        <div class="actions">

        <a class="btn"
        href="{{ url_for('questions') }}">
        Ask a Question
        </a>

        <a class="btn green"
        href="{{ url_for('assignments') }}">
        Assignments
        </a>

        <a class="btn orange"
        href="{{ url_for('documents') }}">
        Documents
        </a>

        </div>

        {% endif %}

        </div>
        """
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

        name = request.form.get(
            "name",
            ""
        ).strip()

        if not email or not password:

            flash(
                "Email and password are required.",
                "warning"
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
                "warning"
            )

            return redirect(
                url_for("register")
            )

        response = auth_signup(
            email,
            password
        )

        if response.status_code not in (
            200,
            201
        ):

            try:

                data = response.json()

                error = (
                    data.get("msg")
                    or data.get("message")
                    or data.get("error_description")
                    or response.text
                )

            except Exception:

                error = response.text

            flash(
                "Registration failed: "
                + str(error),
                "warning"
            )

            return redirect(
                url_for("register")
            )

        data = response.json()

        user = data.get("user")

        if not user:

            flash(
                "Account created. Check your email if confirmation is required.",
                "success"
            )

            return redirect(
                url_for("login")
            )

        user_id = user.get("id")

        profile_response = supabase_post(
            "profiles",
            {
                "id": user_id,
                "name": (
                    name
                    or email.split("@")[0]
                ),
                "email": email,
                "role": "student",
            }
        )

        if profile_response.status_code not in (
            200,
            201
        ):

            logger.warning(
                "Profile creation failed: %s",
                profile_response.text
            )

        flash(
            "Account created successfully.",
            "success"
        )

        return redirect(
            url_for("login")
        )

    return render_page(
        "Create Account",
        """
        <div class="card">

        <h1>Create Student Account</h1>

        <form method="post">

        <label>Name</label>

        <input
        name="name"
        required
        placeholder="Full name">

        <label>Email</label>

        <input
        type="email"
        name="email"
        required
        placeholder="Email">

        <label>Password</label>

        <input
        type="password"
        name="password"
        minlength="6"
        required
        placeholder="Minimum 6 characters">

        <button>
        Create Account
        </button>

        </form>

        </div>
        """
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

        response = auth_login(
            email,
            password
        )

        if response.status_code != 200:

            try:

                data = response.json()

                error = (
                    data.get(
                        "error_description"
                    )
                    or data.get("msg")
                    or data.get("message")
                    or response.text
                )

            except Exception:

                error = response.text

            flash(
                "Login failed: "
                + str(error),
                "warning"
            )

            return redirect(
                url_for("login")
            )

        data = response.json()

        access_token = data.get(
            "access_token"
        )

        user = data.get("user")

        if not user and access_token:

            user_response = auth_user(
                access_token
            )

            if user_response.status_code == 200:

                user = user_response.json()

        if not user:

            flash(
                "Could not retrieve user information.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        user_id = user.get("id")

        profile = ensure_profile(
            user_id,
            user.get("email", email)
        )

        session.clear()

        session["access_token"] = access_token

        session["user"] = {
            "id": user_id,
            "email": user.get(
                "email",
                email
            ),
            "name": (
                profile.get("name")
                if profile
                else email.split("@")[0]
            ),
        }

        session["is_admin"] = (
            str(user_id)
            ==
            str(ADMIN_UUID)
        )

        flash(
            "Welcome to KOJA AFRICA.",
            "success"
        )

        return redirect(
            url_for("documents")
        )

    return render_page(
        "Login",
        """
        <div class="card">

        <h1>Login</h1>

        <form method="post">

        <label>Email</label>

        <input
        type="email"
        name="email"
        required
        placeholder="Email">

        <label>Password</label>

        <input
        type="password"
        name="password"
        required
        placeholder="Password">

        <button>
        Login
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# DOCUMENTS
# ============================================================

@app.route("/documents")
@login_required
def documents():

    search = request.args.get(
        "search",
        ""
    )

    docs = get_documents(search)

    return render_page(
        "Documents",
        """
        <div class="card">

        <h1>Document Library</h1>

        <form method="get">

        <input
        name="search"
        value="{{ search }}"
        placeholder="Search documents...">

        <button>
        Search
        </button>

        </form>

        </div>

        <div class="grid">

        {% for doc in docs %}

        <div class="document">

        <span class="badge">
        {{ doc.document_type|replace('_',' ')|title }}
        </span>

        <h3>
        {{ doc.title }}
        </h3>

        <p>
        {{ doc.description or
        'No description available.' }}
        </p>

        {% if doc.subject %}

        <p>
        <b>Subject:</b>
        {{ doc.subject }}
        </p>

        {% endif %}

        {% if doc.class_level %}

        <p>
        <b>Class:</b>
        {{ doc.class_level }}
        </p>

        {% endif %}

        <p class="small">
        {{ doc.file_name }}
        </p>

        <div class="actions">

        <a class="btn"
        href="{{ url_for(
        'view_document',
        document_id=doc.id
        ) }}">
        View
        </a>

        <a class="btn green"
        href="{{ url_for(
        'download_document',
        document_id=doc.id
        ) }}">
        Download
        </a>

        </div>

        </div>

        {% else %}

        <div class="card">

        <h2>No documents found.</h2>

        </div>

        {% endfor %}

        </div>
        """,
        docs=docs,
        search=search
    )


# ============================================================
# VIEW DOCUMENT
# ============================================================

@app.route(
    "/documents/<document_id>/view"
)
@login_required
def view_document(document_id):

    document = get_document(
        document_id
    )

    if not document:
        abort(404)

    response = download_from_storage(
        document["file_path"]
    )

    if response.status_code != 200:

        flash(
            "Document could not be opened.",
            "warning"
        )

        return redirect(
            url_for("documents")
        )

    increment_document_counter(
        document_id,
        "view_count"
    )

    create_document_record(
        document_id,
        current_user()["id"],
        "viewed"
    )

    return send_file(
        io.BytesIO(response.content),
        mimetype=(
            document.get("mime_type")
            or "application/octet-stream"
        ),
        download_name=document[
            "file_name"
        ],
        as_attachment=False
    )


# ============================================================
# DOWNLOAD DOCUMENT
# ============================================================

@app.route(
    "/documents/<document_id>/download"
)
@login_required
def download_document(document_id):

    document = get_document(
        document_id
    )

    if not document:
        abort(404)

    response = download_from_storage(
        document["file_path"]
    )

    if response.status_code != 200:

        flash(
            "Download failed.",
            "warning"
        )

        return redirect(
            url_for("documents")
        )

    increment_document_counter(
        document_id,
        "download_count"
    )

    create_document_record(
        document_id,
        current_user()["id"],
        "downloaded"
    )

    return send_file(
        io.BytesIO(response.content),
        mimetype=(
            document.get("mime_type")
            or "application/octet-stream"
        ),
        download_name=document[
            "file_name"
        ],
        as_attachment=True
    )


# ============================================================
# ASK QUESTION
# ============================================================

@app.route(
    "/questions",
    methods=["GET", "POST"]
)
@login_required
def questions():

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        question_text = request.form.get(
            "question",
            ""
        ).strip()

        if not question_text:

            flash(
                "Please enter your question.",
                "warning"
            )

            return redirect(
                url_for("questions")
            )

        user = current_user()

        response = supabase_post(
            "questions",
            {
                "user_id": user["id"],
                "name": user.get("name"),
                "email": user.get("email"),
                "subject": subject,
                "question": question_text,
                "question_type": "question",
            }
        )

        if response.status_code not in (
            200,
            201
        ):

            flash(
                "Question could not be submitted: "
                + response.text,
                "warning"
            )

            return redirect(
                url_for("questions")
            )

        flash(
            "Your question has been submitted. The administrator can now answer it.",
            "success"
        )

        return redirect(
            url_for("questions")
        )

    all_questions = get_questions()

    # Students see their own questions.
    # Admin sees all questions.
    if not is_admin():

        user_id = current_user()["id"]

        all_questions = [
            q for q in all_questions
            if str(q.get("user_id"))
            == str(user_id)
        ]

    return render_page(
        "Questions",
        """
        <div class="card">

        <h1>Ask a Question</h1>

        <form method="post">

        <label>Subject</label>

        <input
        name="subject"
        placeholder="e.g. Chemistry">

        <label>Your Question</label>

        <textarea
        name="question"
        required
        placeholder="Type your academic question here..."></textarea>

        <button>
        Submit Question
        </button>

        </form>

        </div>

        <h2>
        {% if session.get('is_admin') %}
        Questions
        {% else %}
        My Questions
        {% endif %}
        </h2>

        {% for q in questions %}

        <div class="card">

        <span class="badge">
        {{ q.subject or 'General' }}
        </span>

        <h3>
        {{ q.question }}
        </h3>

        <p class="small">
        {{ q.created_at }}
        </p>

        {% if q.answer %}

        <div class="answer">

        <b>KOJA Admin Answer</b>

        <p>
        {{ q.answer.answer }}
        </p>

        </div>

        {% else %}

        <p class="small">
        Waiting for administrator answer.
        </p>

        {% endif %}

        {% if session.get('is_admin') %}

        <a class="btn"
        href="{{ url_for(
        'answer_question',
        question_id=q.id
        ) }}">
        Answer
        </a>

        {% endif %}

        </div>

        {% else %}

        <div class="card">
        No questions yet.
        </div>

        {% endfor %}
        """,
        questions=all_questions
    )


# ============================================================
# ADMIN ANSWER QUESTION
# ============================================================

@app.route(
    "/admin/questions/<question_id>/answer",
    methods=["GET", "POST"]
)
@admin_required
def answer_question(question_id):

    question = get_question(
        question_id
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
                "Answer cannot be empty.",
                "warning"
            )

            return redirect(
                url_for(
                    "answer_question",
                    question_id=question_id
                )
            )

        existing = question.get(
            "answer"
        )

        if existing:

            response = supabase_patch(
                "answers",
                {
                    "id": existing["id"]
                },
                {
                    "answer": answer,
                    "admin_id":
                        current_user()["id"],
                }
            )

        else:

            response = supabase_post(
                "answers",
                {
                    "question_id":
                        question_id,
                    "admin_id":
                        current_user()["id"],
                    "answer": answer,
                }
            )

        if response.status_code not in (
            200,
            201,
            204
        ):

            flash(
                "Answer could not be saved: "
                + response.text,
                "warning"
            )

            return redirect(
                url_for(
                    "answer_question",
                    question_id=question_id
                )
            )

        flash(
            "Answer saved successfully.",
            "success"
        )

        return redirect(
            url_for("admin")
        )

    return render_page(
        "Answer Question",
        """
        <div class="card">

        <h1>Answer Student Question</h1>

        <div class="question">

        <b>Student:</b>
        {{ question.name or 'Student' }}

        <br><br>

        <b>Subject:</b>
        {{ question.subject or 'General' }}

        <br><br>

        <b>Question:</b>

        <p>
        {{ question.question }}
        </p>

        </div>

        <br>

        <form method="post">

        <label>Administrator Answer</label>

        <textarea
        name="answer"
        required
        placeholder="Write the academic answer here...">{{ question.answer.answer if question.answer else '' }}</textarea>

        <button>
        Save Answer
        </button>

        </form>

        </div>
        """,
        question=question
    )


# ============================================================
# ASSIGNMENTS
# ============================================================

@app.route("/assignments")
@login_required
def assignments():

    data = get_assignments()

    if not is_admin():

        user_id = current_user()["id"]

        data = [
            item for item in data
            if str(item.get("user_id"))
            == str(user_id)
        ]

    return render_page(
        "Assignments",
        """
        <div class="hero">

        <h1>Assignments</h1>

        <p>
        Ask assignment questions or upload
        your assignment for KOJA processing.
        </p>

        <div class="actions">

        <a class="btn green"
        href="{{ url_for(
        'ask_assignment'
        ) }}">
        Ask Assignment
        </a>

        <a class="btn"
        href="{{ url_for(
        'upload_assignment'
        ) }}">
        Upload Assignment
        </a>

        </div>

        </div>

        <h2>
        {% if session.get('is_admin') %}
        Submitted Assignments
        {% else %}
        My Assignments
        {% endif %}
        </h2>

        {% for item in assignments %}

        <div class="card">

        <span class="badge">
        Assignment
        </span>

        <h2>
        {{ item.title }}
        </h2>

        {% if item.subject %}

        <p>
        <b>Subject:</b>
        {{ item.subject }}
        </p>

        {% endif %}

        {% if item.class_level %}

        <p>
        <b>Class:</b>
        {{ item.class_level }}
        </p>

        {% endif %}

        {% if item.description %}

        <p>
        {{ item.description }}
        </p>

        {% endif %}

        {% if item.question %}

        <div class="question">

        <b>Assignment Question:</b>

        <p>
        {{ item.question }}
        </p>

        </div>

        {% endif %}

        {% if item.file_name %}

        <p>
        <b>File:</b>
        {{ item.file_name }}
        </p>

        <a class="btn"
        href="{{ url_for(
        'download_assignment',
        assignment_id=item.id
        ) }}">
        Download Assignment
        </a>

        {% endif %}

        <p class="small">
        Submitted:
        {{ item.created_at }}
        </p>

        {% if session.get('is_admin') %}

        <a class="btn green"
        href="{{ url_for(
        'ask_assignment_answer',
        assignment_id=item.id
        ) }}">
        Respond
        </a>

        {% endif %}

        </div>

        {% else %}

        <div class="card">
        No assignments found.
        </div>

        {% endfor %}
        """,
        assignments=data
    )


# ============================================================
# ASK ASSIGNMENT
# ============================================================

@app.route(
    "/assignments/ask",
    methods=["GET", "POST"]
)
@login_required
def ask_assignment():

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        class_level = request.form.get(
            "class_level",
            ""
        ).strip()

        question = request.form.get(
            "question",
            ""
        ).strip()

        if not title or not question:

            flash(
                "Assignment title and question are required.",
                "warning"
            )

            return redirect(
                url_for("ask_assignment")
            )

        user = current_user()

        response = supabase_post(
            "assignments",
            {
                "user_id": user["id"],
                "name": user.get("name"),
                "email": user.get("email"),
                "title": title,
                "description": "",
                "subject": subject,
                "class_level": class_level,
                "question": question,
            }
        )

        if response.status_code not in (
            200,
            201
        ):

            flash(
                "Assignment question failed: "
                + response.text,
                "warning"
            )

            return redirect(
                url_for("ask_assignment")
            )

        flash(
            "Assignment question submitted successfully.",
            "success"
        )

        return redirect(
            url_for("assignments")
        )

    return render_page(
        "Ask Assignment",
        """
        <div class="card">

        <h1>Ask Assignment</h1>

        <form method="post">

        <label>Assignment Title</label>

        <input
        name="title"
        required
        placeholder="e.g. Rate of Chemical Reaction">

        <label>Subject</label>

        <input
        name="subject"
        placeholder="e.g. Chemistry">

        <label>Class Level</label>

        <input
        name="class_level"
        placeholder="e.g. Grade 12">

        <label>Assignment Question</label>

        <textarea
        name="question"
        required
        placeholder="Enter the assignment question..."></textarea>

        <button>
        Submit Assignment Question
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# UPLOAD ASSIGNMENT
# ============================================================

@app.route(
    "/assignments/upload",
    methods=["GET", "POST"]
)
@login_required
def upload_assignment():

    if request.method == "POST":

        title = request.form.get(
            "title",
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

        class_level = request.form.get(
            "class_level",
            ""
        ).strip()

        file = request.files.get(
            "file"
        )

        if not title:

            flash(
                "Assignment title is required.",
                "warning"
            )

            return redirect(
                url_for("upload_assignment")
            )

        if not file or not file.filename:

            flash(
                "Please select an assignment file.",
                "warning"
            )

            return redirect(
                url_for("upload_assignment")
            )

        try:

            storage = upload_to_storage(
                file
            )

            user = current_user()

            response = supabase_post(
                "assignments",
                {
                    "user_id": user["id"],
                    "name": user.get("name"),
                    "email": user.get("email"),
                    "title": title,
                    "description": description,
                    "subject": subject,
                    "class_level": class_level,
                    "file_name":
                        storage["file_name"],
                    "file_path":
                        storage["file_path"],
                    "file_size":
                        storage["file_size"],
                    "mime_type":
                        storage["mime_type"],
                    "question": "",
                }
            )

            if response.status_code not in (
                200,
                201
            ):

                delete_from_storage(
                    storage["file_path"]
                )

                flash(
                    "Assignment could not be saved: "
                    + response.text,
                    "warning"
                )

                return redirect(
                    url_for("upload_assignment")
                )

            flash(
                "Assignment uploaded successfully.",
                "success"
            )

            return redirect(
                url_for("assignments")
            )

        except Exception as exc:

            logger.exception(
                "Assignment upload error"
            )

            flash(
                "Upload failed: "
                + str(exc),
                "warning"
            )

            return redirect(
                url_for("upload_assignment")
            )

    return render_page(
        "Upload Assignment",
        """
        <div class="card">

        <h1>Upload Assignment</h1>

        <form
        method="post"
        enctype="multipart/form-data">

        <label>Assignment Title</label>

        <input
        name="title"
        required
        placeholder="Assignment title">

        <label>Description</label>

        <textarea
        name="description"
        placeholder="Describe the assignment..."></textarea>

        <label>Subject</label>

        <input
        name="subject"
        placeholder="Subject">

        <label>Class Level</label>

        <input
        name="class_level"
        placeholder="Class">

        <label>Assignment File</label>

        <input
        type="file"
        name="file"
        required>

        <p class="small">
        Maximum size: 10 MB.
        </p>

        <button>
        Upload Assignment
        </button>

        </form>

        </div>
        """
    )


# ============================================================
# DOWNLOAD ASSIGNMENT
# ============================================================

@app.route(
    "/assignments/<assignment_id>/download"
)
@login_required
def download_assignment(assignment_id):

    response = supabase_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if response.status_code != 200:
        abort(404)

    rows = response.json()

    if not rows:
        abort(404)

    assignment = rows[0]

    if not is_admin():

        if str(assignment.get("user_id")) != str(
            current_user()["id"]
        ):
            abort(403)

    file_path = assignment.get(
        "file_path"
    )

    if not file_path:
        abort(404)

    file_response = download_from_storage(
        file_path
    )

    if file_response.status_code != 200:

        flash(
            "Assignment file could not be downloaded.",
            "warning"
        )

        return redirect(
            url_for("assignments")
        )

    return send_file(
        io.BytesIO(file_response.content),
        mimetype=(
            assignment.get("mime_type")
            or "application/octet-stream"
        ),
        download_name=(
            assignment.get("file_name")
            or "assignment"
        ),
        as_attachment=True
    )


# ============================================================
# ADMIN ASSIGNMENT RESPONSE
# ============================================================

@app.route(
    "/admin/assignments/<assignment_id>/respond",
    methods=["GET", "POST"]
)
@admin_required
def ask_assignment_answer(assignment_id):

    response = supabase_get(
        "assignments",
        {
            "id": f"eq.{assignment_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if response.status_code != 200:
        abort(404)

    rows = response.json()

    if not rows:
        abort(404)

    assignment = rows[0]

    if request.method == "POST":

        answer = request.form.get(
            "answer",
            ""
        ).strip()

        if not answer:

            flash(
                "Response cannot be empty.",
                "warning"
            )

            return redirect(
                url_for(
                    "ask_assignment_answer",
                    assignment_id=assignment_id
                )
            )

        # Assignment answers are stored as
        # normal questions so students can
        # receive an academic response.
        question_response = supabase_post(
            "questions",
            {
                "user_id":
                    assignment.get("user_id"),
                "name":
                    assignment.get("name"),
                "email":
                    assignment.get("email"),
                "subject":
                    assignment.get("subject")
                    or "Assignment",
                "question":
                    assignment.get("question")
                    or assignment.get("title"),
                "question_type":
                    "assignment",
            }
        )

        if question_response.status_code not in (
            200,
            201
        ):

            flash(
                "Could not create assignment response: "
                + question_response.text,
                "warning"
            )

            return redirect(
                url_for("assignments")
            )

        q_rows = question_response.json()

        question_id = q_rows[0]["id"]

        answer_response = supabase_post(
            "answers",
            {
                "question_id": question_id,
                "admin_id":
                    current_user()["id"],
                "answer": answer,
            }
        )

        if answer_response.status_code not in (
            200,
            201
        ):

            flash(
                "Answer could not be saved: "
                + answer_response.text,
                "warning"
            )

            return redirect(
                url_for("assignments")
            )

        flash(
            "Assignment response saved.",
            "success"
        )

        return redirect(
            url_for("admin")
        )

    return render_page(
        "Respond to Assignment",
        """
        <div class="card">

        <h1>Respond to Assignment</h1>

        <div class="question">

        <b>Student:</b>
        {{ assignment.name or 'Student' }}

        <br><br>

        <b>Title:</b>
        {{ assignment.title }}

        <br><br>

        <b>Subject:</b>
        {{ assignment.subject or 'General' }}

        {% if assignment.question %}

        <br><br>

        <b>Question:</b>

        <p>
        {{ assignment.question }}
        </p>

        {% endif %}

        </div>

        <br>

        <form method="post">

        <label>Administrator Response</label>

        <textarea
        name="answer"
        required
        placeholder="Write your academic response..."></textarea>

        <button>
        Submit Response
        </button>

        </form>

        </div>
        """,
        assignment=assignment
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin():

    docs = get_documents()

    all_questions = get_questions()

    assignments_data = get_assignments()

    total_views = sum(
        int(d.get("view_count", 0) or 0)
        for d in docs
    )

    total_downloads = sum(
        int(d.get("download_count", 0) or 0)
        for d in docs
    )

    unanswered = [
        q for q in all_questions
        if not q.get("answer")
    ]

    records_response = supabase_get(
        "document_records",
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": "100",
        }
    )

    records = []

    if records_response.status_code == 200:
        records = records_response.json()

    return render_page(
        "Admin",
        """
        <div class="hero">

        <h1>KOJA ADMIN</h1>

        <p>
        Manage documents, questions and assignments.
        </p>

        <div class="actions">

        <a class="btn green"
        href="{{ url_for(
        'upload_document'
        ) }}">
        Upload Document
        </a>

        <a class="btn"
        href="{{ url_for(
        'questions'
        ) }}">
        Questions
        </a>

        <a class="btn orange"
        href="{{ url_for(
        'assignments'
        ) }}">
        Assignments
        </a>

        </div>

        </div>

        <div class="grid">

        <div class="card">

        <div class="small">
        Documents
        </div>

        <div class="stat">
        {{ docs|length }}
        </div>

        </div>

        <div class="card">

        <div class="small">
        Questions
        </div>

        <div class="stat">
        {{ questions|length }}
        </div>

        </div>

        <div class="card">

        <div class="small">
        Unanswered
        </div>

        <div class="stat">
        {{ unanswered|length }}
        </div>

        </div>

        <div class="card">

        <div class="small">
        Assignments
        </div>

        <div class="stat">
        {{ assignments|length }}
        </div>

        </div>

        </div>

        <div class="card">

        <h2>Student Questions</h2>

        {% for q in questions %}

        <div class="question">

        <b>
        {{ q.name or 'Student' }}
        </b>

        <p>
        <b>
        {{ q.subject or 'General' }}
        </b>
        </p>

        <p>
        {{ q.question }}
        </p>

        {% if q.answer %}

        <div class="answer">

        <b>Answered:</b>

        <p>
        {{ q.answer.answer }}
        </p>

        <a class="btn gray"
        href="{{ url_for(
        'answer_question',
        question_id=q.id
        ) }}">
        Edit Answer
        </a>

        </div>

        {% else %}

        <a class="btn"
        href="{{ url_for(
        'answer_question',
        question_id=q.id
        ) }}">
        Answer Question
        </a>

        {% endif %}

        </div>

        <br>

        {% else %}

        <p>No questions.</p>

        {% endfor %}

        </div>

        <div class="card">

        <h2>Submitted Assignments</h2>

        <div class="table-wrap">

        <table>

        <tr>

        <th>Student</th>
        <th>Title</th>
        <th>Subject</th>
        <th>File</th>
        <th>Action</th>

        </tr>

        {% for a in assignments %}

        <tr>

        <td>
        {{ a.name or a.email or 'Student' }}
        </td>

        <td>
        {{ a.title }}
        </td>

        <td>
        {{ a.subject }}
        </td>

        <td>
        {{ a.file_name or 'Question only' }}
        </td>

        <td>

        <div class="actions">

        {% if a.file_path %}

        <a class="btn gray"
        href="{{ url_for(
        'download_assignment',
        assignment_id=a.id
        ) }}">
        Download
        </a>

        {% endif %}

        <a class="btn green"
        href="{{ url_for(
        'ask_assignment_answer',
        assignment_id=a.id
        ) }}">
        Respond
        </a>

        </div>

        </td>

        </tr>

        {% endfor %}

        </table>

        </div>

        </div>

        <div class="card">

        <h2>Documents</h2>

        <div class="table-wrap">

        <table>

        <tr>

        <th>Title</th>
        <th>Type</th>
        <th>Views</th>
        <th>Downloads</th>
        <th>Actions</th>

        </tr>

        {% for doc in docs %}

        <tr>

        <td>
        {{ doc.title }}
        </td>

        <td>
        {{ doc.document_type }}
        </td>

        <td>
        {{ doc.view_count or 0 }}
        </td>

        <td>
        {{ doc.download_count or 0 }}
        </td>

        <td>

        <div class="actions">

        <a class="btn"
        href="{{ url_for(
        'view_document',
        document_id=doc.id
        ) }}">
        View
        </a>

        <a class="btn gray"
        href="{{ url_for(
        'edit_document',
        document_id=doc.id
        ) }}">
        Edit
        </a>

        <form method="post"
        action="{{ url_for(
        'delete_document',
        document_id=doc.id
        ) }}"
        onsubmit="return confirm('Delete this document?');">

        <button class="btn red">
        Delete
        </button>

        </form>

        </div>

        </td>

        </tr>

        {% endfor %}

        </table>

        </div>

        </div>

        <div class="card">

        <h2>Document Activity</h2>

        <div class="table-wrap">

        <table>

        <tr>

        <th>Document</th>
        <th>User</th>
        <th>Action</th>
        <th>Time</th>

        </tr>

        {% for record in records %}

        <tr>

        <td>
        {{ record.document_id }}
        </td>

        <td>
        {{ record.user_id or 'Unknown' }}
        </td>

        <td>
        {{ record.action }}
        </td>

        <td>
        {{ record.created_at }}
        </td>

        </tr>

        {% endfor %}

        </table>

        </div>

        </div>
        """,
        docs=docs,
        questions=all_questions,
        unanswered=unanswered,
        assignments=assignments_data,
        records=records,
        total_views=total_views,
        total_downloads=total_downloads
    )


# ============================================================
# UPLOAD DOCUMENT
# ============================================================

@app.route(
    "/admin/documents/upload",
    methods=["GET", "POST"]
)
@admin_required
def upload_document():

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        document_type = request.form.get(
            "document_type",
            "academic"
        )

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

        is_public = (
            request.form.get(
                "is_public"
            )
            == "on"
        )

        file = request.files.get(
            "file"
        )

        if not title:

            flash(
                "Document title is required.",
                "warning"
            )

            return redirect(
                url_for("upload_document")
            )

        if not file or not file.filename:

            flash(
                "Please select a document.",
                "warning"
            )

            return redirect(
                url_for("upload_document")
            )

        try:

            storage = upload_to_storage(
                file
            )

            response = supabase_post(
                "documents",
                {
                    "title": title,
                    "description":
                        description or None,
                    "document_type":
                        document_type,
                    "subject":
                        subject or None,
                    "course":
                        course or None,
                    "class_level":
                        class_level or None,
                    "file_name":
                        storage["file_name"],
                    "file_path":
                        storage["file_path"],
                    "file_url": None,
                    "file_size":
                        storage["file_size"],
                    "mime_type":
                        storage["mime_type"],
                    "uploaded_by":
                        current_user()["id"],
                    "is_public":
                        is_public,
                    "is_active": True,
                    "download_count": 0,
                    "view_count": 0,
                }
            )

            if response.status_code not in (
                200,
                201
            ):

                delete_from_storage(
                    storage["file_path"]
                )

                flash(
                    "Document database save failed: "
                    + response.text,
                    "warning"
                )

                return redirect(
                    url_for("upload_document")
                )

            rows = response.json()

            if rows:

                create_document_record(
                    rows[0]["id"],
                    current_user()["id"],
                    "uploaded"
                )

            flash(
                "Document uploaded successfully.",
                "success"
            )

            return redirect(
                url_for("admin")
            )

        except Exception as exc:

            logger.exception(
                "Document upload error"
            )

            flash(
                "Upload failed: "
                + str(exc),
                "warning"
            )

            return redirect(
                url_for("upload_document")
            )

    return render_page(
        "Upload Document",
        """
        <div class="card">

        <h1>Upload Academic Document</h1>

        <form
        method="post"
        enctype="multipart/form-data">

        <label>Document Title</label>

        <input
        name="title"
        required
        placeholder="e.g. Grade 12 Biology Notes">

        <label>Description</label>

        <textarea
        name="description"
        placeholder="Description"></textarea>

        <label>Document Type</label>

        <select name="document_type">

        {% for value,label in document_types %}

        <option value="{{ value }}">
        {{ label }}
        </option>

        {% endfor %}

        </select>

        <label>Subject</label>

        <input
        name="subject"
        placeholder="Biology">

        <label>Course</label>

        <input
        name="course"
        placeholder="Course">

        <label>Class Level</label>

        <input
        name="class_level"
        placeholder="Grade 12">

        <label>Document File</label>

        <input
        type="file"
        name="file"
        required>

        <p class="small">
        Maximum 10 MB.
        </p>

        <label>

        <input
        type="checkbox"
        name="is_public"
        style="width:auto;">

        Public document

        </label>

        <br><br>

        <button>
        Upload Document
        </button>

        </form>

        </div>
        """,
        document_types=DOCUMENT_TYPES
    )


# ============================================================
# EDIT DOCUMENT
# INCLUDING REPLACE EXISTING FILE
# ============================================================

@app.route(
    "/admin/documents/<document_id>/edit",
    methods=["GET", "POST"]
)
@admin_required
def edit_document(document_id):

    document = get_document(
        document_id
    )

    if not document:
        abort(404)

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        if not title:

            flash(
                "Title is required.",
                "warning"
            )

            return redirect(
                url_for(
                    "edit_document",
                    document_id=document_id
                )
            )

        data = {
            "title": title,

            "description":
                request.form.get(
                    "description",
                    ""
                ).strip() or None,

            "document_type":
                request.form.get(
                    "document_type",
                    "academic"
                ),

            "subject":
                request.form.get(
                    "subject",
                    ""
                ).strip() or None,

            "course":
                request.form.get(
                    "course",
                    ""
                ).strip() or None,

            "class_level":
                request.form.get(
                    "class_level",
                    ""
                ).strip() or None,

            "is_public":
                request.form.get(
                    "is_public"
                ) == "on",

            "is_active":
                request.form.get(
                    "is_active"
                ) == "on",
        }

        replacement_file = request.files.get(
            "file"
        )

        old_file_path = document.get(
            "file_path"
        )

        new_storage = None

        try:

            # =================================================
            # REPLACE ACTUAL FILE
            # =================================================

            if replacement_file and replacement_file.filename:

                new_storage = upload_to_storage(
                    replacement_file
                )

                data.update({
                    "file_name":
                        new_storage["file_name"],

                    "file_path":
                        new_storage["file_path"],

                    "file_size":
                        new_storage["file_size"],

                    "mime_type":
                        new_storage["mime_type"],

                    "file_url": None,
                })

            # =================================================
            # UPDATE DATABASE
            # =================================================

            response = supabase_patch(
                "documents",
                {
                    "id": document_id
                },
                data
            )

            if response.status_code not in (
                200,
                204
            ):

                # Database failed.
                # Remove newly uploaded file.
                if new_storage:

                    delete_from_storage(
                        new_storage["file_path"]
                    )

                flash(
                    "Document update failed: "
                    + response.text,
                    "warning"
                )

                return redirect(
                    url_for(
                        "edit_document",
                        document_id=document_id
                    )
                )

            # =================================================
            # DELETE OLD FILE ONLY AFTER DB UPDATE
            # =================================================

            if new_storage and old_file_path:

                old_response = (
                    delete_from_storage(
                        old_file_path
                    )
                )

                if old_response.status_code not in (
                    200,
                    204
                ):

                    logger.warning(
                        "Old storage file could not be deleted: %s",
                        old_response.text
                    )

            create_document_record(
                document_id,
                current_user()["id"],
                (
                    "file_replaced"
                    if new_storage
                    else "updated"
                )
            )

            flash(
                (
                    "Document and file updated successfully."
                    if new_storage
                    else
                    "Document updated successfully."
                ),
                "success"
            )

            return redirect(
                url_for("admin")
            )

        except Exception as exc:

            logger.exception(
                "Document update error"
            )

            if new_storage:

                delete_from_storage(
                    new_storage["file_path"]
                )

            flash(
                "Update failed: "
                + str(exc),
                "warning"
            )

            return redirect(
                url_for(
                    "edit_document",
                    document_id=document_id
                )
            )

    return render_page(
        "Edit Document",
        """
        <div class="card">

        <h1>Edit Document</h1>

        <p class="small">
        Current file:
        {{ document.file_name }}
        </p>

        <form
        method="post"
        enctype="multipart/form-data">

        <label>Title</label>

        <input
        name="title"
        required
        value="{{ document.title }}">

        <label>Description</label>

        <textarea
        name="description">{{ document.description or '' }}</textarea>

        <label>Document Type</label>

        <select name="document_type">

        {% for value,label in document_types %}

        <option
        value="{{ value }}"
        {% if document.document_type == value %}
        selected
        {% endif %}>
        {{ label }}
        </option>

        {% endfor %}

        </select>

        <label>Subject</label>

        <input
        name="subject"
        value="{{ document.subject or '' }}">

        <label>Course</label>

        <input
        name="course"
        value="{{ document.course or '' }}">

        <label>Class Level</label>

        <input
        name="class_level"
        value="{{ document.class_level or '' }}">

        <label>
        Replace Existing File
        </label>

        <input
        type="file"
        name="file">

        <p class="small">
        Leave this empty if you only want to change
        the document information.
        If you select a file, KOJA will replace
        the existing stored file.
        Maximum 10 MB.
        </p>

        <label>

        <input
        type="checkbox"
        name="is_public"
        style="width:auto;"
        {% if document.is_public %}
        checked
        {% endif %}>

        Public

        </label>

        <br>

        <label>

        <input
        type="checkbox"
        name="is_active"
        style="width:auto;"
        {% if document.is_active %}
        checked
        {% endif %}>

        Active

        </label>

        <br><br>

        <button>
        Save Changes
        </button>

        </form>

        </div>
        """,
        document=document,
        document_types=DOCUMENT_TYPES
    )


# ============================================================
# DELETE DOCUMENT
# ============================================================

@app.route(
    "/admin/documents/<document_id>/delete",
    methods=["POST"]
)
@admin_required
def delete_document(document_id):

    document = get_document(
        document_id
    )

    if not document:
        abort(404)

    file_path = document.get(
        "file_path"
    )

    if file_path:

        storage_response = (
            delete_from_storage(
                file_path
            )
        )

        if storage_response.status_code not in (
            200,
            204
        ):

            logger.warning(
                "Storage deletion failed: %s",
                storage_response.text
            )

    response = supabase_delete(
        "documents",
        {
            "id": document_id
        }
    )

    if response.status_code not in (
        200,
        204
    ):

        flash(
            "Document database deletion failed: "
            + response.text,
            "warning"
        )

        return redirect(
            url_for("admin")
        )

    flash(
        "Document deleted successfully.",
        "success"
    )

    return redirect(
        url_for("admin")
    )


# ============================================================
# ADMIN PDF REPORT
# ============================================================

@app.route(
    "/admin/documents/report.pdf"
)
@admin_required
def document_report():

    docs = get_documents()

    buffer = io.BytesIO()

    styles = getSampleStyleSheet()

    title_style = styles["Title"]

    title_style.alignment = TA_CENTER

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=35,
        leftMargin=35,
        topMargin=35,
        bottomMargin=35,
    )

    story = []

    story.append(
        Paragraph(
            "KOJA AFRICA",
            title_style
        )
    )

    story.append(
        Spacer(1, 10)
    )

    story.append(
        Paragraph(
            "Document Management Report",
            styles["Heading2"]
        )
    )

    story.append(
        Spacer(1, 15)
    )

    data = [
        [
            "Title",
            "Type",
            "Subject",
            "Views",
            "Downloads",
        ]
    ]

    for item in docs:

        data.append([
            str(
                item.get("title", "")
            )[:35],

            str(
                item.get(
                    "document_type",
                    ""
                )
            ),

            str(
                item.get(
                    "subject",
                    ""
                ) or ""
            ),

            str(
                item.get(
                    "view_count",
                    0
                )
            ),

            str(
                item.get(
                    "download_count",
                    0
                )
            ),
        ])

    table = Table(
        data,
        repeatRows=1
    )

    table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#0b3366")
            ),

            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),

            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold"
            ),

            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                7
            ),

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP"
            ),
        ])
    )

    story.append(table)

    story.append(
        Spacer(1, 20)
    )

    story.append(
        Paragraph(
            "Generated by KOJA AFRICA",
            styles["Normal"]
        )
    )

    pdf.build(story)

    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="koja-document-report.pdf"
    )


# ============================================================
# ERRORS
# ============================================================

@app.errorhandler(403)
def forbidden(error):

    return render_page(
        "Access Denied",
        """
        <div class="card">

        <h1>Access Denied</h1>

        <p>
        You do not have permission to access this page.
        </p>

        <a class="btn"
        href="{{ url_for('home') }}">
        Home
        </a>

        </div>
        """
    ), 403


@app.errorhandler(404)
def not_found(error):

    return render_page(
        "Not Found",
        """
        <div class="card">

        <h1>Page Not Found</h1>

        <a class="btn"
        href="{{ url_for('home') }}">
        Home
        </a>

        </div>
        """
    ), 404


@app.errorhandler(413)
def too_large(error):

    return render_page(
        "File Too Large",
        """
        <div class="card">

        <h1>File Too Large</h1>

        <p>
        Maximum allowed file size is 10 MB.
        </p>

        </div>
        """
    ), 413


@app.errorhandler(500)
def server_error(error):

    logger.exception(
        "Internal server error"
    )

    return render_page(
        "Server Error",
        """
        <div class="card">

        <h1>Server Error</h1>

        <p>
        Something went wrong. Please try again.
        </p>

        </div>
        """
    ), 500


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "application": "KOJA AFRICA",
        "storage_bucket": STORAGE_BUCKET,
        "questions": True,
        "answers": True,
        "assignments": True,
        "document_replacement": True,
    }


# ============================================================
# START
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
