import os
import uuid
import logging
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
    render_template_string,
    send_file,
)
from werkzeug.utils import secure_filename

load_dotenv()

# ============================================================
# KOJA AFRICA
# Foundation + Assignments
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "change-this-secret-key"
)

logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger("KOJA")

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
).rstrip("/")

SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
)

STORAGE_BUCKET = os.getenv(
    "KOJA_STORAGE_BUCKET",
    "koja-files"
)

MAX_FILE_SIZE = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "jpg",
    "jpeg",
    "png",
}


# ============================================================
# SUPABASE
# ============================================================

def check_config():
    if not SUPABASE_URL:
        raise RuntimeError(
            "SUPABASE_URL is missing."
        )

    if not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_SERVICE_KEY is missing."
        )


def supabase_headers(content_type=True):
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": (
            f"Bearer {SUPABASE_SERVICE_KEY}"
        ),
    }

    if content_type:
        headers["Content-Type"] = (
            "application/json"
        )

    return headers


def supabase_request(
    method,
    path,
    **kwargs
):
    check_config()

    url = f"{SUPABASE_URL}{path}"

    custom_headers = kwargs.pop(
        "headers",
        {}
    )

    headers = supabase_headers()

    headers.update(custom_headers)

    response = requests.request(
        method,
        url,
        headers=headers,
        timeout=40,
        **kwargs
    )

    return response


def response_error(response):
    try:
        data = response.json()

        return (
            data.get("message")
            or data.get("msg")
            or data.get("error_description")
            or data.get("error")
            or response.text
        )

    except Exception:
        return response.text


# ============================================================
# USER
# ============================================================

def current_user():
    return session.get("user")


def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not current_user():
            flash(
                "Please log in first.",
                "warning"
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
            flash(
                "Please log in first.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        if user.get("role") != "admin":

            flash(
                "Administrator access required.",
                "danger"
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
# PROFILE
# ============================================================

def get_profile(user_id):

    response = supabase_request(
        "GET",
        "/rest/v1/profiles",
        params={
            "id": f"eq.{user_id}",
            "select": "*",
            "limit": "1",
        }
    )

    if response.status_code != 200:

        logger.error(
            "Profile error: %s",
            response.text
        )

        return None

    data = response.json()

    return data[0] if data else None


def create_profile(
    user_id,
    full_name,
    email,
    phone=""
):

    payload = {
        "id": user_id,
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "role": "student",
    }

    response = supabase_request(
        "POST",
        "/rest/v1/profiles",
        json=payload,
        headers={
            "Prefer": "return=representation"
        }
    )

    if response.status_code not in (
        200,
        201
    ):

        logger.error(
            "Profile creation error: %s",
            response.text
        )

        return False

    return True


# ============================================================
# HTML
# ============================================================

BASE_HTML = """
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
    initial-scale=1.0"
>

<title>
    {{ title }} - KOJA AFRICA
</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #f4f7fb;
    color: #172033;
    font-family:
        Arial,
        Helvetica,
        sans-serif;
}

nav {
    background: #102a43;
    color: white;
    padding: 15px 20px;
    display: flex;
    justify-content:
        space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}

.brand {
    font-size: 21px;
    font-weight: bold;
}

nav a {
    color: white;
    text-decoration: none;
    margin-left: 12px;
}

.container {
    width: min(1100px, 94%);
    margin: 25px auto;
}

.card {
    background: white;
    padding: 22px;
    border-radius: 12px;
    margin-bottom: 18px;
    box-shadow:
        0 3px 15px
        rgba(0,0,0,.07);
}

.grid {
    display: grid;
    grid-template-columns:
        repeat(
            auto-fit,
            minmax(220px, 1fr)
        );
    gap: 16px;
}

.service {
    background: white;
    padding: 20px;
    border-radius: 12px;
    border: 1px solid #e1e7ef;
}

input,
textarea,
select {
    width: 100%;
    padding: 12px;
    margin-top: 6px;
    margin-bottom: 15px;
    border: 1px solid #ccd5df;
    border-radius: 8px;
    font-size: 16px;
}

textarea {
    min-height: 130px;
    resize: vertical;
}

button,
.button {
    display: inline-block;
    border: 0;
    border-radius: 8px;
    padding: 12px 18px;
    background: #1677ff;
    color: white;
    text-decoration: none;
    cursor: pointer;
    font-size: 15px;
}

.button.secondary {
    background: #52606d;
}

.button.success {
    background: #16803c;
}

.button.warning {
    background: #d97706;
}

.button.danger {
    background: #c53030;
}

.flash {
    padding: 13px 15px;
    border-radius: 8px;
    margin-bottom: 12px;
    background: #e8f1ff;
}

.flash.danger {
    background: #ffe5e5;
}

.flash.warning {
    background: #fff3cd;
}

.flash.success-message {
    background: #e2f7e8;
}

.status {
    display: inline-block;
    padding: 6px 10px;
    border-radius: 20px;
    background: #edf2f7;
    font-size: 13px;
    font-weight: bold;
}

.status.pending {
    background: #fff3cd;
}

.status.in_progress {
    background: #dbeafe;
}

.status.completed {
    background: #dcfce7;
}

.status.approved {
    background: #bbf7d0;
}

.status.rejected {
    background: #fee2e2;
}

.message {
    padding: 12px;
    border-radius: 10px;
    margin-bottom: 10px;
    background: #f1f5f9;
}

.message.mine {
    background: #e0edff;
}

.small {
    color: #64748b;
    font-size: 14px;
}

.file {
    padding: 12px;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin: 8px 0;
}

footer {
    text-align: center;
    color: #718096;
    padding: 30px;
}

</style>

</head>

<body>

<nav>

<div class="brand">
    KOJA AFRICA
</div>

<div>

{% if user %}

<a href="{{ url_for('dashboard') }}">
    Dashboard
</a>

<a href="{{ url_for('assignments') }}">
    Assignments
</a>

{% if user.get("role") == "admin" %}

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

</nav>

<div class="container">

{% with messages =
    get_flashed_messages(
        with_categories=true
    )
%}

{% for category, message in messages %}

<div class="flash {{ category }}">
    {{ message }}
</div>

{% endfor %}

{% endwith %}

{{ body|safe }}

</div>

<footer>

KOJA AFRICA

<br>

Knowledge • Questions • Answers

</footer>

</body>

</html>
"""


def page(
    title,
    body,
    **kwargs
):

    return render_template_string(
        BASE_HTML,
        title=title,
        body=render_template_string(
            body,
            **kwargs
        ),
        user=current_user()
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
A digital platform connecting people with
academic assistance, CV services, universities,
transport, delivery, farmers and professionals.
</p>

<a class="button"
   href="{{ url_for('register') }}">
Create Account
</a>

<a class="button secondary"
   href="{{ url_for('login') }}">
Login
</a>

</div>

<div class="grid">

<div class="service">

<h2>Assignments</h2>

<p>
Upload academic questions and receive
answers from KOJA.
</p>

</div>

<div class="service">

<h2>CV Services</h2>

<p>
Submit your CV requirements for processing.
</p>

</div>

<div class="service">

<h2>Universities</h2>

<p>
Research universities and application
requirements.
</p>

</div>

<div class="service">

<h2>Drivers & Delivery</h2>

<p>
Find nearby drivers and request rides
or deliveries.
</p>

</div>

<div class="service">

<h2>Farmers</h2>

<p>
Connect farmers and customers.
</p>

</div>

<div class="service">

<h2>Professionals</h2>

<p>
Find doctors, lawyers, teachers and
other professionals.
</p>

</div>

</div>

"""

    return page(
        "Home",
        body
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

        full_name = request.form.get(
            "full_name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not full_name:

            flash(
                "Full name is required.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        if not email:

            flash(
                "Email is required.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
                "danger"
            )

            return redirect(
                url_for("register")
            )

        payload = {
            "email": email,
            "password": password,
            "data": {
                "full_name": full_name,
                "phone": phone,
            }
        }

        try:

            response = supabase_request(
                "POST",
                "/auth/v1/signup",
                json=payload
            )

            if response.status_code not in (
                200,
                201
            ):

                error = response_error(
                    response
                )

                logger.error(
                    "Signup error: %s",
                    response.text
                )

                flash(
                    error,
                    "danger"
                )

                return redirect(
                    url_for("register")
                )

            data = response.json()

            user_data = data.get(
                "user"
            )

            if user_data:

                user_id = user_data.get(
                    "id"
                )

                # The database trigger should normally
                # create this profile automatically.
                #
                # We only create it here if it does
                # not already exist.

                existing = get_profile(
                    user_id
                )

                if not existing:

                    create_profile(
                        user_id,
                        full_name,
                        email,
                        phone
                    )

            flash(
                "Account created successfully. "
                "You can now log in.",
                "success-message"
            )

            return redirect(
                url_for("login")
            )

        except Exception as exc:

            logger.exception(
                "Registration exception"
            )

            flash(
                f"Registration error: {exc}",
                "danger"
            )

            return redirect(
                url_for("register")
            )

    body = """

<div class="card">

<h1>Create KOJA Account</h1>

<form method="POST">

<label>
Full Name
</label>

<input
    type="text"
    name="full_name"
    required
>

<label>
Email
</label>

<input
    type="email"
    name="email"
    required
>

<label>
Phone
</label>

<input
    type="tel"
    name="phone"
>

<label>
Password
</label>

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

<p>
Already have an account?

<a href="{{ url_for('login') }}">
Login
</a>

</p>

</div>

"""

    return page(
        "Register",
        body
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

        if not email or not password:

            flash(
                "Email and password are required.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        try:

            response = supabase_request(
                "POST",
                "/auth/v1/token?grant_type=password",
                json={
                    "email": email,
                    "password": password
                }
            )

            if response.status_code != 200:

                error = response_error(
                    response
                )

                logger.error(
                    "Login error: %s",
                    response.text
                )

                flash(
                    error,
                    "danger"
                )

                return redirect(
                    url_for("login")
                )

            data = response.json()

            user_data = data.get(
                "user"
            )

            if not user_data:

                flash(
                    "Unable to identify account.",
                    "danger"
                )

                return redirect(
                    url_for("login")
                )

            user_id = user_data.get(
                "id"
            )

            profile = get_profile(
                user_id
            )

            if not profile:

                metadata = user_data.get(
                    "user_metadata",
                    {}
                )

                create_profile(
                    user_id,
                    metadata.get(
                        "full_name",
                        ""
                    ),
                    email,
                    metadata.get(
                        "phone",
                        ""
                    )
                )

                profile = get_profile(
                    user_id
                )

            role = "student"

            full_name = ""

            if profile:

                role = profile.get(
                    "role",
                    "student"
                )

                full_name = profile.get(
                    "full_name",
                    ""
                )

            session["user"] = {
                "id": user_id,
                "email": email,
                "role": role,
                "full_name": full_name
            }

            session["access_token"] = data.get(
                "access_token"
            )

            flash(
                "Login successful.",
                "success-message"
            )

            return redirect(
                url_for("dashboard")
            )

        except Exception as exc:

            logger.exception(
                "Login exception"
            )

            flash(
                f"Login error: {exc}",
                "danger"
            )

            return redirect(
                url_for("login")
            )

    body = """

<div class="card">

<h1>KOJA Login</h1>

<form method="POST">

<label>
Email
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
Login
</button>

</form>

<p>
Don't have an account?

<a href="{{ url_for('register') }}">
Create Account
</a>

</p>

</div>

"""

    return page(
        "Login",
        body
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():

    user = current_user()

    body = """

<div class="card">

<h1>
Welcome,
{{ user.full_name or user.email }}
</h1>

<p>
Your KOJA account is active.
</p>

<p class="small">
Email: {{ user.email }}
<br>
Role: {{ user.role }}
</p>

</div>

<div class="grid">

<div class="service">

<h2>Assignments</h2>

<p>
Submit academic questions and documents.
</p>

<a class="button"
   href="{{ url_for('assignments') }}">
Open Assignments
</a>

</div>

<div class="service">

<h2>CV</h2>

<p>
Submit CV requirements.
</p>

<span class="small">
Coming next
</span>

</div>

<div class="service">

<h2>Universities</h2>

<p>
Research universities and applications.
</p>

<span class="small">
Coming next
</span>

</div>

<div class="service">

<h2>Drivers & Delivery</h2>

<p>
Find nearby drivers and request services.
</p>

<span class="small">
Coming next
</span>

</div>

<div class="service">

<h2>Farmers</h2>

<p>
Register and manage farming information.
</p>

<span class="small">
Coming next
</span>

</div>

<div class="service">

<h2>Professionals</h2>

<p>
Doctors, lawyers, teachers and others.
</p>

<span class="small">
Coming next
</span>

</div>

</div>

"""

    return page(
        "Dashboard",
        body,
        user=user
    )


# ============================================================
# ASSIGNMENT LIST
# ============================================================

@app.route("/assignments")
@login_required
def assignments():

    user = current_user()

    response = supabase_request(
        "GET",
        "/rest/v1/assignments",
        params={
            "student_id": (
                f"eq.{user['id']}"
            ),
            "select": "*",
            "order": "created_at.desc"
        }
    )

    if response.status_code != 200:

        logger.error(
            "Assignment list error: %s",
            response.text
        )

        items = []

        flash(
            "Unable to load assignments.",
            "danger"
        )

    else:

        items = response.json()

    body = """

<div class="card">

<h1>My Assignments</h1>

<a class="button"
   href="{{ url_for('new_assignment') }}">
+ New Assignment
</a>

</div>

{% if items %}

{% for item in items %}

<div class="card">

<h2>
{{ item.title }}
</h2>

<p>
Subject:
{{ item.subject or "Not specified" }}
</p>

<p>

Status:

<span class="status {{ item.status }}">
{{ item.status.replace("_", " ") }}
</span>

</p>

<p class="small">
Submitted:
{{ item.created_at }}
</p>

<a class="button"
   href="{{ url_for(
       'assignment_detail',
       assignment_id=item.id
   ) }}">
Open
</a>

</div>

{% endfor %}

{% else %}

<div class="card">

<h2>
No assignments yet
</h2>

<p>
Submit your first academic question.
</p>

</div>

{% endif %}

"""

    return page(
        "Assignments",
        body,
        items=items
    )


# ============================================================
# NEW ASSIGNMENT
# ============================================================

@app.route(
    "/assignments/new",
    methods=["GET", "POST"]
)
@login_required
def new_assignment():

    if request.method == "POST":

        user = current_user()

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

        if not title:

            flash(
                "Assignment title is required.",
                "danger"
            )

            return redirect(
                url_for("new_assignment")
            )

        if not description and not request.files.get(
            "question_file"
        ):

            flash(
                "Type a question or upload a question file.",
                "danger"
            )

            return redirect(
                url_for("new_assignment")
            )

        payload = {
            "student_id": user["id"],
            "title": title,
            "subject": subject,
            "description": description,
            "status": "pending"
        }

        response = supabase_request(
            "POST",
            "/rest/v1/assignments",
            json=payload,
            headers={
                "Prefer": "return=representation"
            }
        )

        if response.status_code not in (
            200,
            201
        ):

            logger.error(
                "Assignment creation error: %s",
                response.text
            )

            flash(
                response_error(response),
                "danger"
            )

            return redirect(
                url_for("new_assignment")
            )

        data = response.json()

        if not data:

            flash(
                "Assignment ID was not returned.",
                "danger"
            )

            return redirect(
                url_for("assignments")
            )

        assignment_id = data[0]["id"]

        uploaded_file = request.files.get(
            "question_file"
        )

        if uploaded_file and uploaded_file.filename:

            success = upload_assignment_file(
                assignment_id,
                uploaded_file,
                user["id"],
                "question"
            )

            if not success:

                # Remove assignment if its only
                # purpose was an invalid upload.
                supabase_request(
                    "DELETE",
                    "/rest/v1/assignments",
                    params={
                        "id":
                            f"eq.{assignment_id}"
                    }
                )

                return redirect(
                    url_for("new_assignment")
                )

        flash(
            "Assignment submitted successfully.",
            "success-message"
        )

        return redirect(
            url_for(
                "assignment_detail",
                assignment_id=assignment_id
            )
        )

    body = """

<div class="card">

<h1>New Assignment</h1>

<form
    method="POST"
    enctype="multipart/form-data"
>

<label>
Title
</label>

<input
    type="text"
    name="title"
    placeholder="Example: Biology Assignment"
    required
>

<label>
Subject
</label>

<input
    type="text"
    name="subject"
    placeholder="Example: Biology"
>

<label>
Question
</label>

<textarea
    name="description"
    placeholder="Type your question here..."
></textarea>

<label>
Upload Question
</label>

<input
    type="file"
    name="question_file"
    accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
>

<p class="small">
Maximum file size: 10 MB.
<br>
Supported: PDF, Word and images.
</p>

<button type="submit">
Submit Assignment
</button>

</form>

</div>

"""

    return page(
        "New Assignment",
        body
    )


# ============================================================
# UPLOAD FILE
# ============================================================

def upload_assignment_file(
    assignment_id,
    uploaded_file,
    user_id,
    file_type
):

    filename = secure_filename(
        uploaded_file.filename
    )

    if not filename:

        flash(
            "Invalid file name.",
            "danger"
        )

        return False

    extension = ""

    if "." in filename:

        extension = filename.rsplit(
            ".",
            1
        )[1].lower()

    if extension not in ALLOWED_EXTENSIONS:

        flash(
            "Unsupported file type.",
            "danger"
        )

        return False

    file_bytes = uploaded_file.read()

    if len(file_bytes) > MAX_FILE_SIZE:

        flash(
            "File is larger than 10 MB.",
            "danger"
        )

        return False

    storage_path = (
        f"assignments/"
        f"{assignment_id}/"
        f"{file_type}/"
        f"{uuid.uuid4()}-{filename}"
    )

    response = supabase_request(
        "POST",
        (
            "/storage/v1/object/"
            f"{STORAGE_BUCKET}/"
            f"{storage_path}"
        ),
        data=file_bytes,
        headers={
            "Content-Type":
                uploaded_file.mimetype
                or "application/octet-stream"
        }
    )

    if response.status_code not in (
        200,
        201
    ):

        logger.error(
            "Storage upload error: %s",
            response.text
        )

        flash(
            "File upload failed: "
            + response_error(response),
            "danger"
        )

        return False

    metadata = {
        "assignment_id": assignment_id,
        "uploaded_by": user_id,
        "file_name": filename,
        "file_path": storage_path,
        "mime_type":
            uploaded_file.mimetype
            or "application/octet-stream",
        "file_size": len(file_bytes),
        "file_type": file_type,
        "storage_bucket": STORAGE_BUCKET
    }

    db_response = supabase_request(
        "POST",
        "/rest/v1/assignment_files",
        json=metadata,
        headers={
            "Prefer": "return=minimal"
        }
    )

    if db_response.status_code not in (
        200,
        201
    ):

        logger.error(
            "File metadata error: %s",
            db_response.text
        )

        # Attempt to remove orphaned storage file.
        supabase_request(
            "DELETE",
            (
                "/storage/v1/object/"
                f"{STORAGE_BUCKET}/"
                f"{storage_path}"
            )
        )

        flash(
            "File database record failed.",
            "danger"
        )

        return False

    return True


# ============================================================
# ASSIGNMENT DETAIL
# ============================================================

@app.route(
    "/assignments/<assignment_id>"
)
@login_required
def assignment_detail(
    assignment_id
):

    user = current_user()

    response = supabase_request(
        "GET",
        "/rest/v1/assignments",
        params={
            "id":
                f"eq.{assignment_id}",
            "select": "*",
            "limit": "1"
        }
    )

    if response.status_code != 200:

        flash(
            "Unable to load assignment.",
            "danger"
        )

        return redirect(
            url_for("assignments")
        )

    data = response.json()

    if not data:

        flash(
            "Assignment not found.",
            "danger"
        )

        return redirect(
            url_for("assignments")
        )

    assignment = data[0]

    if (
        assignment["student_id"]
        != user["id"]
        and user.get("role")
        != "admin"
    ):

        flash(
            "You cannot access this assignment.",
            "danger"
        )

        return redirect(
            url_for("assignments")
        )

    files_response = supabase_request(
        "GET",
        "/rest/v1/assignment_files",
        params={
            "assignment_id":
                f"eq.{assignment_id}",
            "select": "*",
            "order": "created_at.asc"
        }
    )

    files = []

    if files_response.status_code == 200:

        files = files_response.json()

    messages_response = supabase_request(
        "GET",
        "/rest/v1/assignment_messages",
        params={
            "assignment_id":
                f"eq.{assignment_id}",
            "select": "*",
            "order": "created_at.asc"
        }
    )

    messages = []

    if messages_response.status_code == 200:

        messages = messages_response.json()

    body = """

<div class="card">

<h1>
{{ assignment.title }}
</h1>

<p>
<strong>Subject:</strong>
{{ assignment.subject or "Not specified" }}
</p>

<p>

<strong>Status:</strong>

<span class="status {{ assignment.status }}">
{{ assignment.status.replace("_", " ") }}
</span>

</p>

<p class="small">
Created:
{{ assignment.created_at }}
</p>

</div>


<div class="card">

<h2>Question</h2>

{% if assignment.description %}

<p>
{{ assignment.description }}
</p>

{% else %}

<p class="small">
No typed question.
See uploaded files below.
</p>

{% endif %}

</div>


<div class="card">

<h2>Files</h2>

{% for file in files %}

<div class="file">

<strong>
{{ file.file_name }}
</strong>

<br>

<span class="small">
{{ file.file_type }}
•
{{ file.file_size }} bytes
</span>

<br><br>

<a class="button secondary"
   href="{{ url_for(
       'download_assignment_file',
       file_id=file.id
   ) }}">
Download
</a>

</div>

{% else %}

<p class="small">
No files attached.
</p>

{% endfor %}

</div>


{% if assignment.answer_text %}

<div class="card">

<h2>KOJA Answer</h2>

<p>
{{ assignment.answer_text }}
</p>

</div>

{% endif %}


<div class="card">

<h2>Chat</h2>

{% for message in messages %}

<div class="message
{% if message.sender_id == user.id %}
mine
{% endif %}
">

<p>
{{ message.message }}
</p>

<span class="small">
{{ message.created_at }}
</span>

</div>

{% else %}

<p class="small">
No messages yet.
</p>

{% endfor %}

<form method="POST"
      action="{{ url_for(
          'assignment_message',
          assignment_id=assignment.id
      ) }}">

<textarea
    name="message"
    placeholder="Write a message..."
    required
></textarea>

<button type="submit">
Send Message
</button>

</form>

</div>


{% if assignment.status == "approved" %}

<div class="card">

<h2>
Answer Ready
</h2>

<p>
Your assignment has been approved.
</p>

{% for file in files %}

{% if file.file_type == "answer" %}

<a class="button success"
   href="{{ url_for(
       'download_assignment_file',
       file_id=file.id
   ) }}">
Download Answer
</a>

{% endif %}

{% endfor %}

</div>

{% endif %}

"""

    return page(
        "Assignment",
        body,
        assignment=assignment,
        files=files,
        messages=messages,
        user=user
    )


# ============================================================
# ASSIGNMENT CHAT
# ============================================================

@app.route(
    "/assignments/<assignment_id>/message",
    methods=["POST"]
)
@login_required
def assignment_message(
    assignment_id
):

    user = current_user()

    message = request.form.get(
        "message",
        ""
    ).strip()

    if not message:

        flash(
            "Message cannot be empty.",
            "danger"
        )

        return redirect(
            url_for(
                "assignment_detail",
                assignment_id=assignment_id
            )
        )

    response = supabase_request(
        "GET",
        "/rest/v1/assignments",
        params={
            "id":
                f"eq.{assignment_id}",
            "select":
                "id,student_id",
            "limit": "1"
        }
    )

    if response.status_code != 200:

        flash(
            "Assignment could not be found.",
            "danger"
        )

        return redirect(
            url_for("assignments")
        )

    data = response.json()

    if not data:

        flash(
            "Assignment not found.",
            "danger"
        )

        return redirect(
            url_for("assignments")
        )

    assignment = data[0]

    if (
        assignment["student_id"]
        != user["id"]
        and user.get("role")
        != "admin"
    ):

        flash(
            "You cannot message this assignment.",
            "danger"
        )

        return redirect(
            url_for("assignments")
        )

    payload = {
        "assignment_id": assignment_id,
        "sender_id": user["id"],
        "message": message
    }

    response = supabase_request(
        "POST",
        "/rest/v1/assignment_messages",
        json=payload,
        headers={
            "Prefer": "return=minimal"
        }
    )

    if response.status_code not in (
        200,
        201
    ):

        logger.error(
            "Message error: %s",
            response.text
        )

        flash(
            "Message could not be sent.",
            "danger"
        )

    else:

        flash(
            "Message sent.",
            "success-message"
        )

    return redirect(
        url_for(
            "assignment_detail",
            assignment_id=assignment_id
        )
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    response = supabase_request(
        "GET",
        "/rest/v1/assignments",
        params={
            "select": "*",
            "order": "created_at.desc"
        }
    )

    if response.status_code != 200:

        assignments_data = []

        flash(
            "Unable to load assignments.",
            "danger"
        )

    else:

        assignments_data = response.json()

    body = """

<div class="card">

<h1>
KOJA AFRICA ADMIN
</h1>

<p>
Assignment management centre.
</p>

</div>


<div class="grid">

<div class="service">

<h2>
Pending
</h2>

<strong>
{{ counts.pending }}
</strong>

</div>

<div class="service">

<h2>
In Progress
</h2>

<strong>
{{ counts.in_progress }}
</strong>

</div>

<div class="service">

<h2>
Completed
</h2>

<strong>
{{ counts.completed }}
</strong>

</div>

<div class="service">

<h2>
Approved
</h2>

<strong>
{{ counts.approved }}
</strong>

</div>

</div>


{% for item in assignments_data %}

<div class="card">

<h2>
{{ item.title }}
</h2>

<p>
Subject:
{{ item.subject or "Not specified" }}
</p>

<p>
Student:
{{ item.student_id }}
</p>

<p>

<span class="status {{ item.status }}">
{{ item.status.replace("_", " ") }}
</span>

</p>

<a class="button"
   href="{{ url_for(
       'admin_assignment',
       assignment_id=item.id
   ) }}">
Manage Assignment
</a>

</div>

{% else %}

<div class="card">

<h2>
No assignments
</h2>

</div>

{% endfor %}

"""

    counts = {
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "approved": 0,
        "rejected": 0
    }

    for item in assignments_data:

        status = item.get(
            "status"
        )

        if status in counts:

            counts[status] += 1

    return page(
        "Admin",
        body,
        assignments_data=assignments_data,
        counts=counts
    )


# ============================================================
# ADMIN ASSIGNMENT
# ============================================================

@app.route(
    "/admin/assignments/<assignment_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_assignment(
    assignment_id
):

    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        )

        answer_text = request.form.get(
            "answer_text",
            ""
        ).strip()

        if action == "update":

            status = request.form.get(
                "status",
                "pending"
            )

            allowed_statuses = {
                "pending",
                "in_progress",
                "completed",
                "approved",
                "rejected"
            }

            if status not in allowed_statuses:

                flash(
                    "Invalid assignment status.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "admin_assignment",
                        assignment_id=assignment_id
                    )
                )

            payload = {
                "status": status
            }

            if answer_text:

                payload["answer_text"] = (
                    answer_text
                )

            response = supabase_request(
                "PATCH",
                "/rest/v1/assignments",
                params={
                    "id":
                        f"eq.{assignment_id}"
                },
                json=payload
            )

            if response.status_code not in (
                200,
                204
            ):

                logger.error(
                    "Admin update error: %s",
                    response.text
                )

                flash(
                    "Assignment update failed.",
                    "danger"
                )

            else:

                flash(
                    "Assignment updated.",
                    "success-message"
                )

        elif action == "upload_answer":

            uploaded_file = request.files.get(
                "answer_file"
            )

            if not uploaded_file or not uploaded_file.filename:

                flash(
                    "Select an answer file.",
                    "danger"
                )

            else:

                success = upload_assignment_file(
                    assignment_id,
                    uploaded_file,
                    current_user()["id"],
                    "answer"
                )

                if success:

                    flash(
                        "Answer file uploaded.",
                        "success-message"
                    )

        return redirect(
            url_for(
                "admin_assignment",
                assignment_id=assignment_id
            )
        )

    response = supabase_request(
        "GET",
        "/rest/v1/assignments",
        params={
            "id":
                f"eq.{assignment_id}",
            "select": "*",
            "limit": "1"
        }
    )

    if response.status_code != 200:

        flash(
            "Unable to load assignment.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    data = response.json()

    if not data:

        flash(
            "Assignment not found.",
            "danger"
        )

        return redirect(
            url_for("admin_dashboard")
        )

    assignment = data[0]

    files_response = supabase_request(
        "GET",
        "/rest/v1/assignment_files",
        params={
            "assignment_id":
                f"eq.{assignment_id}",
            "select": "*",
            "order": "created_at.asc"
        }
    )

    files = []

    if files_response.status_code == 200:

        files = files_response.json()

    messages_response = supabase_request(
        "GET",
        "/rest/v1/assignment_messages",
        params={
            "assignment_id":
                f"eq.{assignment_id}",
            "select": "*",
            "order": "created_at.asc"
        }
    )

    messages = []

    if messages_response.status_code == 200:

        messages = messages_response.json()

    body = """

<div class="card">

<h1>
Manage Assignment
</h1>

<h2>
{{ assignment.title }}
</h2>

<p>
Subject:
{{ assignment.subject or "Not specified" }}
</p>

<p>
Student:
{{ assignment.student_id }}
</p>

<p>
Status:

<span class="status {{ assignment.status }}">
{{ assignment.status.replace("_", " ") }}
</span>

</p>

</div>


<div class="card">

<h2>
Question
</h2>

<p>
{{ assignment.description or
   "No typed question." }}
</p>

<h3>
Files
</h3>

{% for file in files %}

<div class="file">

<strong>
{{ file.file_name }}
</strong>

<br>

<span class="small">
{{ file.file_type }}
</span>

<br><br>

<a class="button secondary"
   href="{{ url_for(
       'download_assignment_file',
       file_id=file.id
   ) }}">
Open / Download
</a>

</div>

{% endfor %}

</div>


<div class="card">

<h2>
Process Assignment
</h2>

<form method="POST">

<input
    type="hidden"
    name="action"
    value="update"
>

<label>
Status
</label>

<select name="status">

<option
{% if assignment.status == "pending" %}
selected
{% endif %}
value="pending">
Pending
</option>

<option
{% if assignment.status == "in_progress" %}
selected
{% endif %}
value="in_progress">
In Progress
</option>

<option
{% if assignment.status == "completed" %}
selected
{% endif %}
value="completed">
Completed
</option>

<option
{% if assignment.status == "approved" %}
selected
{% endif %}
value="approved">
Approved
</option>

<option
{% if assignment.status == "rejected" %}
selected
{% endif %}
value="rejected">
Rejected
</option>

</select>

<label>
Written Answer
</label>

<textarea
    name="answer_text"
    placeholder="Write the answer here..."
>{{ assignment.answer_text or "" }}</textarea>

<button type="submit">
Save / Update
</button>

</form>

</div>


<div class="card">

<h2>
Upload Answer
</h2>

<form
    method="POST"
    enctype="multipart/form-data"
>

<input
    type="hidden"
    name="action"
    value="upload_answer"
>

<input
    type="file"
    name="answer_file"
    accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
    required
>

<button type="submit">
Upload Answer
</button>

</form>

</div>


<div class="card">

<h2>
Chat
</h2>

{% for message in messages %}

<div class="message">

<p>
{{ message.message }}
</p>

<span class="small">
{{ message.created_at }}
</span>

</div>

{% else %}

<p class="small">
No messages yet.
</p>

{% endfor %}

<form
    method="POST"
    action="{{ url_for(
        'assignment_message',
        assignment_id=assignment.id
    ) }}"
>

<textarea
    name="message"
    placeholder="Message the student..."
    required
></textarea>

<button type="submit">
Send Message
</button>

</form>

</div>

"""

    return page(
        "Manage Assignment",
        body,
        assignment=assignment,
        files=files,
        messages=messages
    )


# ============================================================
# SECURE FILE DOWNLOAD
# ============================================================

@app.route(
    "/assignment-files/<file_id>/download"
)
@login_required
def download_assignment_file(
    file_id
):

    user = current_user()

    response = supabase_request(
        "GET",
        "/rest/v1/assignment_files",
        params={
            "id":
                f"eq.{file_id}",
            "select": "*",
            "limit": "1"
        }
    )

    if response.status_code != 200:

        flash(
            "Unable to find file.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    data = response.json()

    if not data:

        flash(
            "File not found.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    file_record = data[0]

    assignment_id = file_record[
        "assignment_id"
    ]

    assignment_response = supabase_request(
        "GET",
        "/rest/v1/assignments",
        params={
            "id":
                f"eq.{assignment_id}",
            "select":
                "id,student_id,status",
            "limit": "1"
        }
    )

    if assignment_response.status_code != 200:

        flash(
            "Unable to verify file access.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    assignments_data = (
        assignment_response.json()
    )

    if not assignments_data:

        flash(
            "Assignment not found.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    assignment = assignments_data[0]

    authorized = (
        assignment["student_id"]
        == user["id"]
        or user.get("role")
        == "admin"
    )

    if not authorized:

        flash(
            "You are not authorized to download this file.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    # --------------------------------------------------------
    # Generate a short-lived signed URL
    # --------------------------------------------------------

    bucket = file_record.get(
        "storage_bucket"
    ) or STORAGE_BUCKET

    path = file_record[
        "file_path"
    ]

    signed_response = supabase_request(
        "POST",
        (
            "/storage/v1/object/sign/"
            f"{bucket}/{path}"
        ),
        json={
            "expiresIn": 300
        }
    )

    if signed_response.status_code != 200:

        logger.error(
            "Signed URL error: %s",
            signed_response.text
        )

        # Fallback to direct authenticated download.
        download_response = supabase_request(
            "GET",
            (
                "/storage/v1/object/"
                f"{bucket}/{path}"
            ),
            headers={}
        )

        if download_response.status_code != 200:

            flash(
                "File download failed.",
                "danger"
            )

            return redirect(
                url_for(
                    "assignment_detail",
                    assignment_id=assignment_id
                )
            )

        from io import BytesIO

        return send_file(
            BytesIO(
                download_response.content
            ),
            mimetype=(
                file_record.get(
                    "mime_type"
                )
                or "application/octet-stream"
            ),
            as_attachment=True,
            download_name=file_record[
                "file_name"
            ]
        )

    signed_data = signed_response.json()

    signed_url = (
        signed_data.get("signedURL")
        or signed_data.get("signedUrl")
    )

    if not signed_url:

        flash(
            "Secure download URL was not generated.",
            "danger"
        )

        return redirect(
            url_for(
                "assignment_detail",
                assignment_id=assignment_id
            )
        )

    if signed_url.startswith("/"):

        signed_url = (
            f"{SUPABASE_URL}/storage/v1"
            f"{signed_url}"
        )

    file_response = requests.get(
        signed_url,
        timeout=40
    )

    if file_response.status_code != 200:

        flash(
            "Unable to download file.",
            "danger"
        )

        return redirect(
            url_for(
                "assignment_detail",
                assignment_id=assignment_id
            )
        )

    from io import BytesIO

    return send_file(
        BytesIO(
            file_response.content
        ),
        mimetype=(
            file_record.get(
                "mime_type"
            )
            or "application/octet-stream"
        ),
        as_attachment=True,
        download_name=file_record[
            "file_name"
        ]
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out.",
        "success-message"
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "application": "KOJA AFRICA",
        "version": "2.0"
    }


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return page(
        "Not Found",
        """
<div class="card">

<h1>
Page Not Found
</h1>

<p>
The requested page does not exist.
</p>

<a class="button"
   href="/">
Return Home
</a>

</div>
"""
    ), 404


@app.errorhandler(500)
def server_error(error):

    logger.exception(
        "Internal server error"
    )

    return page(
        "Server Error",
        """
<div class="card">

<h1>
KOJA Server Error
</h1>

<p>
An unexpected server error occurred.
</p>

<p class="small">
Check the Render logs for the exact
technical error.
</p>

<a class="button"
   href="/">
Return Home
</a>

</div>
"""
    ), 500


# ============================================================
# RUN
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
