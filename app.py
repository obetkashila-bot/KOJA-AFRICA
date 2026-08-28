import os
import io
import uuid
import secrets
import logging

from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote

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

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    secrets.token_hex(32)
)

app.config["MAX_CONTENT_LENGTH"] = (
    25 * 1024 * 1024
)

logging.basicConfig(
    level=logging.INFO
)


SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    ""
).rstrip("/")


SUPABASE_SERVICE_KEY = os.getenv(
    "SUPABASE_SERVICE_KEY",
    ""
)


ADMIN_USERNAME = os.getenv(
    "ADMIN_USERNAME",
    "admin"
)


ADMIN_PASSWORD = os.getenv(
    "ADMIN_PASSWORD",
    ""
)


STORAGE_BUCKET = os.getenv(
    "SUPABASE_STORAGE_BUCKET",
    "koja-assignments"
)


APP_NAME = "KOJA AFRICA"

APP_TAGLINE = (
    "Submit • Process • Receive"
)


STATUS_NEW = "New"

STATUS_PROCESSING = "Processing"

STATUS_COMPLETED = "Completed"


ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "jpg",
    "jpeg",
    "png",
    "webp",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "zip",
}


# ============================================================
# HELPERS
# ============================================================

def configuration_ok():

    return bool(
        SUPABASE_URL
        and SUPABASE_SERVICE_KEY
    )


def require_configuration():

    if not configuration_ok():

        raise RuntimeError(
            "SUPABASE_URL and "
            "SUPABASE_SERVICE_KEY "
            "are not configured."
        )


def now_iso():

    return datetime.now(
        timezone.utc
    ).isoformat()


def clean(value, maximum=5000):

    return (
        value or ""
    ).strip()[:maximum]


def allowed_file(filename):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = (
        filename
        .rsplit(".", 1)[1]
        .lower()
    )

    return (
        extension
        in ALLOWED_EXTENSIONS
    )


def safe_filename(filename):

    filename = os.path.basename(
        filename or "file"
    )

    filename = filename.replace(
        "\x00",
        ""
    )

    return filename[:180]


# ============================================================
# SUPABASE REST API
# ============================================================

def supabase_headers(
    prefer=None
):

    require_configuration()

    headers = {

        "apikey":
            SUPABASE_SERVICE_KEY,

        "Authorization":
            "Bearer "
            + SUPABASE_SERVICE_KEY,

        "Content-Type":
            "application/json",
    }

    if prefer:

        headers["Prefer"] = prefer

    return headers


def supabase_request(
    method,
    path,
    **kwargs
):

    require_configuration()

    url = (
        SUPABASE_URL
        + "/rest/v1/"
        + path
    )

    supplied_headers = (
        kwargs.pop(
            "headers",
            {}
        )
    )

    headers = supabase_headers()

    headers.update(
        supplied_headers
    )

    response = requests.request(
        method,
        url,
        headers=headers,
        timeout=30,
        **kwargs
    )

    if not response.ok:

        logging.error(
            "Supabase request failed: "
            "%s %s %s %s",
            method,
            path,
            response.status_code,
            response.text[:2000]
        )

        raise RuntimeError(
            "Supabase request failed "
            f"({response.status_code}): "
            f"{response.text[:700]}"
        )

    if not response.text:

        return None

    try:

        return response.json()

    except Exception:

        return response.text


def db_select(
    table,
    select="*",
    filters=None,
    order=None,
    limit=None
):

    params = {
        "select": select
    }

    if filters:

        params.update(filters)

    if order:

        params["order"] = order

    if limit:

        params["limit"] = str(
            limit
        )

    return supabase_request(
        "GET",
        table,
        params=params
    )


def db_insert(
    table,
    data,
    returning=True
):

    prefer = (
        "return=representation"
        if returning
        else
        "return=minimal"
    )

    return supabase_request(
        "POST",
        table,
        headers={
            "Prefer": prefer
        },
        json=data
    )


def db_update(
    table,
    filters,
    data,
    returning=True
):

    prefer = (
        "return=representation"
        if returning
        else
        "return=minimal"
    )

    return supabase_request(
        "PATCH",
        table,
        headers={
            "Prefer": prefer
        },
        params=dict(filters),
        json=data
    )


# ============================================================
# SUPABASE STORAGE
# ============================================================

def storage_upload(
    file_storage,
    folder="supporting"
):

    require_configuration()

    original_name = safe_filename(
        file_storage.filename
    )

    extension = ""

    if "." in original_name:

        extension = (
            original_name
            .rsplit(".", 1)[1]
            .lower()
        )

    unique_name = (
        uuid.uuid4().hex
        + (
            "."
            + extension
            if extension
            else ""
        )
    )

    storage_path = (
        folder
        + "/"
        + unique_name
    )

    content_type = (
        file_storage.mimetype
        or "application/octet-stream"
    )

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + quote(
            STORAGE_BUCKET,
            safe=""
        )
        + "/"
        + quote(
            storage_path,
            safe="/"
        )
    )

    headers = {

        "Authorization":
            "Bearer "
            + SUPABASE_SERVICE_KEY,

        "apikey":
            SUPABASE_SERVICE_KEY,

        "Content-Type":
            content_type,

        "x-upsert":
            "false",
    }

    file_storage.stream.seek(0)

    response = requests.post(
        url,
        headers=headers,
        data=file_storage.stream,
        timeout=90
    )

    if not response.ok:

        raise RuntimeError(
            "File upload failed "
            f"({response.status_code}): "
            f"{response.text[:700]}"
        )

    return {

        "path":
            storage_path,

        "file_name":
            original_name,

        "content_type":
            content_type,

        "size":
            request.content_length
            or 0,
    }


def storage_download(path):

    require_configuration()

    url = (
        SUPABASE_URL
        + "/storage/v1/object/"
        + quote(
            STORAGE_BUCKET,
            safe=""
        )
        + "/"
        + quote(
            path,
            safe="/"
        )
    )

    headers = {

        "Authorization":
            "Bearer "
            + SUPABASE_SERVICE_KEY,

        "apikey":
            SUPABASE_SERVICE_KEY,
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=90
    )

    if not response.ok:

        raise RuntimeError(
            "Storage download failed "
            f"({response.status_code}): "
            f"{response.text[:700]}"
        )

    return response


# ============================================================
# REQUEST NUMBER
# ============================================================

def generate_request_number():

    date_part = (
        datetime.now(
            timezone.utc
        ).strftime("%Y%m%d")
    )

    random_part = (
        secrets.token_hex(4)
        .upper()
    )

    return (
        "KOJA-"
        + date_part
        + "-"
        + random_part
    )


def create_unique_request_number():

    for _ in range(15):

        number = (
            generate_request_number()
        )

        existing = db_select(

            "koja_service_requests",

            select="id",

            filters={
                "request_number":
                    "eq."
                    + number
            },

            limit=1
        )

        if not existing:

            return number

    raise RuntimeError(
        "Could not generate "
        "a unique request number."
    )


# ============================================================
# AUTH DECORATORS
# ============================================================

def client_login_required(function):

    @wraps(function)
    def wrapper(
        *args,
        **kwargs
    ):

        if not session.get(
            "client_id"
        ):

            flash(
                "Please log in first."
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
    def wrapper(
        *args,
        **kwargs
    ):

        if not session.get(
            "admin_logged_in"
        ):

            flash(
                "Administrator login required."
            )

            return redirect(
                url_for("admin_login")
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# HTML
# ============================================================

BASE_HTML = """

<!doctype html>

<html lang="en">

<head>

<meta charset="utf-8">

<meta name="viewport"
content="width=device-width,initial-scale=1">

<title>
{{ title or "KOJA AFRICA" }}
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

    background: #101828;

    color: white;

    padding: 14px 18px;
}

.nav-inner {

    max-width: 1150px;

    margin: auto;

    display: flex;

    justify-content:
        space-between;

    align-items: center;

    gap: 15px;
}

.logo {

    color: white;

    text-decoration: none;

    font-size: 22px;

    font-weight: 800;
}

.nav-links {

    display: flex;

    gap: 7px;

    flex-wrap: wrap;
}

.nav-links a {

    color: white;

    text-decoration: none;

    padding: 8px 10px;

    border-radius: 7px;
}

.nav-links a:hover {

    background:
        rgba(255,255,255,.1);
}

.container {

    max-width: 1150px;

    margin: 25px auto;

    padding: 0 15px;
}

.hero {

    background: white;

    border-radius: 18px;

    padding: 30px;

    margin-bottom: 20px;

    box-shadow:
        0 5px 25px
        rgba(0,0,0,.06);
}

.hero h1 {

    margin-top: 0;

    font-size: 34px;
}

.hero p {

    color: #667085;

    line-height: 1.6;
}

.grid {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(220px,1fr)
        );

    gap: 16px;
}

.card {

    background: white;

    padding: 20px;

    border-radius: 15px;

    box-shadow:
        0 4px 18px
        rgba(0,0,0,.05);

    margin-bottom: 16px;
}

.form-card {

    max-width: 820px;

    margin: auto;

    background: white;

    padding: 25px;

    border-radius: 18px;

    box-shadow:
        0 5px 25px
        rgba(0,0,0,.06);
}

label {

    display: block;

    margin-top: 14px;

    margin-bottom: 6px;

    font-weight: 700;
}

input,
select,
textarea {

    width: 100%;

    padding: 12px;

    border:
        1px solid #d0d5dd;

    border-radius: 9px;

    font-size: 15px;

    background: white;
}

textarea {

    min-height: 120px;

    resize: vertical;
}

button,
.btn {

    display: inline-block;

    border: 0;

    background: #176bff;

    color: white;

    padding: 12px 17px;

    border-radius: 9px;

    text-decoration: none;

    cursor: pointer;

    font-weight: 700;

    margin-top: 16px;
}

.btn.secondary {
    background: #344054;
}

.btn.success {
    background: #039855;
}

.btn.warning {
    background: #f79009;
}

.flash {

    padding: 13px 15px;

    background: #eaf2ff;

    border-radius: 9px;

    margin-bottom: 15px;
}

.status {

    display: inline-block;

    padding: 6px 9px;

    border-radius: 20px;

    background: #eef2ff;

    font-size: 13px;

    font-weight: 700;
}

.status.completed {

    background: #dcfae6;

    color: #027a48;
}

.status.processing {

    background: #fef0c7;

    color: #b54708;
}

.status.new {

    background: #eaf2ff;

    color: #175cd3;
}

.detail {

    background: #f8fafc;

    border-radius: 10px;

    padding: 13px;

    margin-bottom: 10px;

    line-height: 1.6;
}

.small {

    color: #667085;

    font-size: 13px;
}

.section-title {

    border-top:
        1px solid #eaecf0;

    padding-top: 20px;

    margin-top: 25px;
}

table {

    width: 100%;

    border-collapse:
        collapse;

    background: white;
}

th,
td {

    padding: 11px;

    border-bottom:
        1px solid #eaecf0;

    text-align: left;

    vertical-align: top;
}

footer {

    margin-top: 50px;

    padding: 25px;

    background: #101828;

    color: white;

    text-align: center;
}

@media(max-width:650px) {

    .nav-inner {

        flex-direction: column;

        align-items:
            flex-start;
    }

    .hero h1 {

        font-size: 27px;
    }

    table {

        display: block;

        overflow-x: auto;
    }
}

</style>

</head>

<body>

<nav>

<div class="nav-inner">

<a class="logo"
href="{{ url_for('home') }}">
KOJA AFRICA
</a>

<div class="nav-links">

<a href="{{ url_for('home') }}">
Home
</a>

{% if session.get("client_id") %}

<a href="{{ url_for('dashboard') }}">
Dashboard
</a>

<a href="{{ url_for('new_request') }}">
New Request
</a>

<a href="{{ url_for('my_requests') }}">
My Requests
</a>

<a href="{{ url_for('notifications') }}">
Notifications
</a>

<a href="{{ url_for('profile') }}">
Profile
</a>

<a href="{{ url_for('logout') }}">
Logout
</a>

{% elif session.get("admin_logged_in") %}

<a href="{{ url_for('admin_dashboard') }}">
Admin
</a>

<a href="{{ url_for('admin_logout') }}">
Logout
</a>

{% else %}

<a href="{{ url_for('login') }}">
Client Login
</a>

<a href="{{ url_for('register') }}">
Register
</a>

<a href="{{ url_for('admin_login') }}">
Admin
</a>

{% endif %}

</div>

</div>

</nav>

<div class="container">

{% with messages =
get_flashed_messages() %}

{% for message in messages %}

<div class="flash">
{{ message }}
</div>

{% endfor %}

{% endwith %}

{{ body|safe }}

</div>

<footer>

<strong>
KOJA AFRICA
</strong>

<br>

{{ tagline }}

<br><br>

Client submits →
KOJA processes →
Client receives

</footer>

</body>

</html>
"""


def page(
    title,
    body_template,
    **context
):

    body = render_template_string(
        body_template,
        **context
    )

    return render_template_string(

        BASE_HTML,

        title=title,

        body=body,

        tagline=APP_TAGLINE
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    body = """

<div class="hero">

<h1>
KOJA AFRICA
</h1>

<p>
<strong>
Submit • Process • Receive
</strong>
</p>

<p>
Clients submit their work and supporting
documents. KOJA AFRICA processes the request
and returns the finished document through
the client's account.
</p>

{% if not session.get("client_id") %}

<a class="btn"
href="{{ url_for('register') }}">
Create Client Account
</a>

<a class="btn secondary"
href="{{ url_for('login') }}">
Client Login
</a>

{% else %}

<a class="btn"
href="{{ url_for('new_request') }}">
Submit New Request
</a>

{% endif %}

</div>


<div class="grid">

<div class="card">

<h3>
Assignments
</h3>

<p>
Submit academic work and supporting
documents for processing.
</p>

</div>


<div class="card">

<h3>
Result Verification & Certification
</h3>

<p>
Submit documents for verification
and certification services.
</p>

</div>


<div class="card">

<h3>
TPN Centre
</h3>

<p>
Submit TPN-related requests.
</p>

</div>


<div class="card">

<h3>
Farmer Registration
</h3>

<p>
Submit farmer registration requests.
</p>

</div>


<div class="card">

<h3>
Higher Education Applications
</h3>

<p>
Submit university and higher education
application requests.
</p>

</div>


<div class="card">

<h3>
Higher Education Materials
</h3>

<p>
Submit requests for higher education
materials and document services.
</p>

</div>

</div>

"""

    return page(
        "KOJA AFRICA",
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

    try:

        universities = db_select(
            "koja_universities",
            select="*",
            filters={
                "active": "eq.true"
            },
            order="name.asc"
        )

    except Exception as exc:

        logging.exception(
            "University loading failed"
        )

        universities = []

        flash(
            "University list could not "
            "be loaded: "
            + str(exc)[:250]
        )

    if request.method == "POST":

        name = clean(
            request.form.get("name"),
            150
        )

        email = clean(
            request.form.get("email"),
            180
        ).lower()

        phone = clean(
            request.form.get("phone"),
            60
        )

        password = request.form.get(
            "password",
            ""
        )

        university = clean(
            request.form.get(
                "university"
            ),
            200
        )

        mode_of_study = clean(
            request.form.get(
                "mode_of_study"
            ),
            80
        )

        school = clean(
            request.form.get("school"),
            200
        )

        programme = clean(
            request.form.get(
                "programme"
            ),
            250
        )

        academic_level = clean(
            request.form.get(
                "academic_level"
            ),
            100
        )

        year_of_study = clean(
            request.form.get(
                "year_of_study"
            ),
            80
        )

        student_number = clean(
            request.form.get(
                "student_number"
            ),
            100
        )

        if not name:

            flash(
                "Full name is required."
            )

            return redirect(
                url_for("register")
            )

        if not email:

            flash(
                "Email address is required."
            )

            return redirect(
                url_for("register")
            )

        if not phone:

            flash(
                "Phone/contact is required."
            )

            return redirect(
                url_for("register")
            )

        if len(password) < 6:

            flash(
                "Password must be at least "
                "6 characters."
            )

            return redirect(
                url_for("register")
            )

        try:

            existing = db_select(

                "koja_clients",

                select="id",

                filters={
                    "email":
                        "eq."
                        + email
                },

                limit=1
            )

            if existing:

                flash(
                    "An account with "
                    "that email already exists."
                )

                return redirect(
                    url_for("login")
                )

            result = db_insert(

                "koja_clients",

                {

                    "name":
                        name,

                    "email":
                        email,

                    "phone":
                        phone,

                    "university":
                        university,

                    "mode_of_study":
                        mode_of_study,

                    "school":
                        school,

                    "programme":
                        programme,

                    "academic_level":
                        academic_level,

                    "year_of_study":
                        year_of_study,

                    "student_number":
                        student_number,

                    "password_hash":
                        generate_password_hash(
                            password
                        ),

                    "created_at":
                        now_iso(),

                    "updated_at":
                        now_iso(),
                }
            )

            client = result[0]

            session.clear()

            session["client_id"] = (
                client["id"]
            )

            session["client_name"] = (
                client["name"]
            )

            session["client_email"] = (
                client["email"]
            )

            flash(
                "Account created successfully."
            )

            return redirect(
                url_for("dashboard")
            )

        except Exception as exc:

            logging.exception(
                "Registration failed"
            )

            flash(
                "Registration error: "
                + str(exc)[:350]
            )

    body = """

<div class="form-card">

<h2>
Create KOJA Client Account
</h2>

<p class="small">
Enter your personal and university information.
Your details can then be reused when submitting
KOJA requests.
</p>

<form method="post">

<label>
Full Name *
</label>

<input
name="name"
required
autocomplete="name"
>


<label>
Email Address *
</label>

<input
type="email"
name="email"
required
autocomplete="email"
>


<label>
Phone / Contact *
</label>

<input
name="phone"
required
placeholder="e.g. 097xxxxxxx"
>


<h3 class="section-title">
University / Student Information
</h3>


<label>
University in Zambia
</label>

<select name="university">

<option value="">
-- Select University --
</option>

{% for university in universities %}

<option value="{{ university.name }}">

{{ university.name }}

</option>

{% endfor %}

</select>


<label>
Mode of Study
</label>

<select name="mode_of_study">

<option value="">
-- Select Mode --
</option>

<option>
Full-Time
</option>

<option>
Part-Time
</option>

<option>
Distance Learning
</option>

<option>
Online
</option>

<option>
Evening
</option>

<option>
Weekend
</option>

<option>
Blended
</option>

<option>
Other
</option>

</select>


<label>
School / Faculty
</label>

<input
name="school"
placeholder="e.g. School of Natural Sciences"
>


<label>
Programme / Course
</label>

<input
name="programme"
placeholder="e.g. Bachelor of Science"
>


<label>
Academic Level
</label>

<select name="academic_level">

<option value="">
-- Select Level --
</option>

<option>
Certificate
</option>

<option>
Diploma
</option>

<option>
Undergraduate
</option>

<option>
Postgraduate
</option>

<option>
Masters
</option>

<option>
PhD
</option>

<option>
Other
</option>

</select>


<label>
Year of Study
</label>

<input
name="year_of_study"
placeholder="e.g. Year 2"
>


<label>
Student Number
</label>

<input
name="student_number"
placeholder="University student number"
>


<label>
Password *
</label>

<input
type="password"
name="password"
required
minlength="6"
autocomplete="new-password"
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
        body,
        universities=universities
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

        email = clean(
            request.form.get("email"),
            180
        ).lower()

        password = request.form.get(
            "password",
            ""
        )

        try:

            clients = db_select(

                "koja_clients",

                select="*",

                filters={
                    "email":
                        "eq."
                        + email
                },

                limit=1
            )

            if not clients:

                flash(
                    "Invalid email or password."
                )

                return redirect(
                    url_for("login")
                )

            client = clients[0]

            if not check_password_hash(

                client[
                    "password_hash"
                ],

                password

            ):

                flash(
                    "Invalid email or password."
                )

                return redirect(
                    url_for("login")
                )

            session.clear()

            session["client_id"] = (
                client["id"]
            )

            session["client_name"] = (
                client["name"]
            )

            session["client_email"] = (
                client["email"]
            )

            return redirect(
                url_for("dashboard")
            )

        except Exception as exc:

            logging.exception(
                "Login failed"
            )

            flash(
                "Login error: "
                + str(exc)[:350]
            )

    body = """

<div class="form-card">

<h2>
Client Login
</h2>

<form method="post">

<label>
Email
</label>

<input
type="email"
name="email"
required
autocomplete="email"
>


<label>
Password
</label>

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

<p>

No account?

<a href="{{ url_for('register') }}">
Create one
</a>

</p>

</div>

"""

    return page(
        "Client Login",
        body
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    flash(
        "You have been logged out."
    )

    return redirect(
        url_for("home")
    )


# ============================================================
# PROFILE
# ============================================================

@app.route(
    "/profile",
    methods=["GET", "POST"]
)
@client_login_required
def profile():

    rows = db_select(

        "koja_clients",

        select="*",

        filters={
            "id":
                "eq."
                + session[
                    "client_id"
                ]
        },

        limit=1
    )

    if not rows:

        session.clear()

        flash(
            "Client profile not found."
        )

        return redirect(
            url_for("register")
        )

    client = rows[0]

    if request.method == "POST":

        data = {

            "name":
                clean(
                    request.form.get(
                        "name"
                    ),
                    150
                ),

            "phone":
                clean(
                    request.form.get(
                        "phone"
                    ),
                    60
                ),

            "university":
                clean(
                    request.form.get(
                        "university"
                    ),
                    200
                ),

            "mode_of_study":
                clean(
                    request.form.get(
                        "mode_of_study"
                    ),
                    80
                ),

            "school":
                clean(
                    request.form.get(
                        "school"
                    ),
                    200
                ),

            "programme":
                clean(
                    request.form.get(
                        "programme"
                    ),
                    250
                ),

            "academic_level":
                clean(
                    request.form.get(
                        "academic_level"
                    ),
                    100
                ),

            "year_of_study":
                clean(
                    request.form.get(
                        "year_of_study"
                    ),
                    80
                ),

            "student_number":
                clean(
                    request.form.get(
                        "student_number"
                    ),
                    100
                ),

            "updated_at":
                now_iso(),
        }

        if not data["name"]:

            flash(
                "Name is required."
            )

            return redirect(
                url_for("profile")
            )

        try:

            db_update(

                "koja_clients",

                {
                    "id":
                        "eq."
                        + session[
                            "client_id"
                        ]
                },

                data,

                returning=False
            )

            session["client_name"] = (
                data["name"]
            )

            flash(
                "Profile updated successfully."
            )

            return redirect(
                url_for("profile")
            )

        except Exception as exc:

            logging.exception(
                "Profile update failed"
            )

            flash(
                "Profile update error: "
                + str(exc)[:350]
            )

    universities = db_select(

        "koja_universities",

        select="*",

        filters={
            "active":
                "eq.true"
        },

        order="name.asc"
    )

    modes = [
        "Full-Time",
        "Part-Time",
        "Distance Learning",
        "Online",
        "Evening",
        "Weekend",
        "Blended",
        "Other"
    ]

    levels = [
        "Certificate",
        "Diploma",
        "Undergraduate",
        "Postgraduate",
        "Masters",
        "PhD",
        "Other"
    ]

    body = """

<div class="form-card">

<h2>
My Profile
</h2>

<form method="post">

<label>
Full Name
</label>

<input
name="name"
value="{{ client.name or '' }}"
required
>


<label>
Email
</label>

<input
value="{{ client.email or '' }}"
disabled
>


<label>
Phone / Contact
</label>

<input
name="phone"
value="{{ client.phone or '' }}"
required
>


<h3 class="section-title">
University / Student Details
</h3>


<label>
University
</label>

<select name="university">

<option value="">
-- Select University --
</option>

{% for u in universities %}

<option
value="{{ u.name }}"
{% if client.university == u.name %}
selected
{% endif %}
>

{{ u.name }}

</option>

{% endfor %}

</select>


<label>
Mode of Study
</label>

<select name="mode_of_study">

{% for m in modes %}

<option
value="{{ m }}"
{% if client.mode_of_study == m %}
selected
{% endif %}
>

{{ m }}

</option>

{% endfor %}

</select>


<label>
School / Faculty
</label>

<input
name="school"
value="{{ client.school or '' }}"
>


<label>
Programme / Course
</label>

<input
name="programme"
value="{{ client.programme or '' }}"
>


<label>
Academic Level
</label>

<select name="academic_level">

<option value="">
-- Select Level --
</option>

{% for level in levels %}

<option
value="{{ level }}"
{% if client.academic_level == level %}
selected
{% endif %}
>

{{ level }}

</option>

{% endfor %}

</select>


<label>
Year of Study
</label>

<input
name="year_of_study"
value="{{ client.year_of_study or '' }}"
>


<label>
Student Number
</label>

<input
name="student_number"
value="{{ client.student_number or '' }}"
>


<button type="submit">

Save Profile

</button>

</form>

</div>

"""

    return page(

        "My Profile",

        body,

        client=client,

        universities=universities,

        modes=modes,

        levels=levels
    )


# ============================================================
# CLIENT DASHBOARD
# ============================================================

@app.route("/dashboard")
@client_login_required
def dashboard():

    email = session[
        "client_email"
    ]

    requests_data = db_select(

        "koja_service_requests",

        select="*",

        filters={
            "client_email":
                "eq."
                + email
        },

        order="created_at.desc",

        limit=100
    )

    unread = db_select(

        "koja_notifications",

        select="id",

        filters={

            "client_email":
                "eq."
                + email,

            "is_read":
                "eq.false"
        },

        limit=100
    )

    body = """

<div class="hero">

<h1>
Welcome,
{{ session.get("client_name") }}
</h1>

<p>
Manage your KOJA AFRICA requests,
messages, supporting documents and
completed files.
</p>

<a class="btn"
href="{{ url_for('new_request') }}">
Submit New Request
</a>

<a class="btn secondary"
href="{{ url_for('profile') }}">
My Profile
</a>

</div>


<div class="grid">

<div class="card">

<h3>
Total Requests
</h3>

<h2>
{{ requests_data|length }}
</h2>

</div>


<div class="card">

<h3>
Unread Notifications
</h3>

<h2>
{{ unread|length }}
</h2>

</div>


<div class="card">

<h3>
Completed
</h3>

<h2>

{{ requests_data
|selectattr(
    'status',
    'equalto',
    'Completed'
)
|list
|length }}

</h2>

</div>

</div>


<div class="card">

<h2>
Recent Requests
</h2>

{% if requests_data %}

{% for r in requests_data %}

<div class="detail">

<strong>
{{ r.request_number }}
</strong>

<br>

{{ r.service_type }}

<br>

<span class="status

{% if r.status == 'Completed' %}
completed

{% elif r.status == 'Processing' %}
processing

{% else %}
new
{% endif %}
">

{{ r.status }}

</span>

<br>

<a href="{{ url_for(
    'request_detail',
    request_id=r.id
) }}">

View Request

</a>

</div>

{% endfor %}

{% else %}

<p>
You have not submitted any requests yet.
</p>

{% endif %}

</div>

"""

    return page(

        "Dashboard",

        body,

        requests_data=requests_data,

        unread=unread
    )


# ============================================================
# NEW REQUEST
# ============================================================

@app.route(
    "/request/new",
    methods=["GET", "POST"]
)
@client_login_required
def new_request():

    services = db_select(

        "koja_services",

        select="*",

        filters={
            "active":
                "eq.true"
        },

        order="name.asc"
    )

    universities = db_select(

        "koja_universities",

        select="*",

        filters={
            "active":
                "eq.true"
        },

        order="name.asc"
    )

    clients = db_select(

        "koja_clients",

        select="*",

        filters={
            "id":
                "eq."
                + session[
                    "client_id"
                ]
        },

        limit=1
    )

    client = (
        clients[0]
        if clients
        else {}
    )

    if request.method == "POST":

        service_type = clean(
            request.form.get(
                "service_type"
            ),
            200
        )

        description = clean(
            request.form.get(
                "description"
            ),
            10000
        )

        university = clean(
            request.form.get(
                "university"
            ),
            200
        )

        mode_of_study = clean(
            request.form.get(
                "mode_of_study"
            ),
            80
        )

        school = clean(
            request.form.get(
                "school"
            ),
            200
        )

        programme = clean(
            request.form.get(
                "programme"
            ),
            250
        )

        academic_level = clean(
            request.form.get(
                "academic_level"
            ),
            100
        )

        year_of_study = clean(
            request.form.get(
                "year_of_study"
            ),
            80
        )

        student_number = clean(
            request.form.get(
                "student_number"
            ),
            100
        )

        supporting_file = (
            request.files.get(
                "supporting_file"
            )
        )

        if not service_type:

            flash(
                "Please select a service."
            )

            return redirect(
                url_for("new_request")
            )

        if not description:

            flash(
                "Please describe "
                "the work."
            )

            return redirect(
                url_for("new_request")
            )

        if (
            supporting_file
            and
            supporting_file.filename
        ):

            if not allowed_file(
                supporting_file.filename
            ):

                flash(
                    "Unsupported file type."
                )

                return redirect(
                    url_for("new_request")
                )

        try:

            request_number = (
                create_unique_request_number()
            )

            created = db_insert(

                "koja_service_requests",

                {

                    "request_number":
                        request_number,

                    "client_id":
                        session[
                            "client_id"
                        ],

                    "client_name":
                        session[
                            "client_name"
                        ],

                    "client_email":
                        session[
                            "client_email"
                        ],

                    "client_phone":
                        client.get(
                            "phone",
                            ""
                        ),

                    "service_type":
                        service_type,

                    "description":
                        description,

                    "university":
                        university,

                    "mode_of_study":
                        mode_of_study,

                    "school":
                        school,

                    "programme":
                        programme,

                    "academic_level":
                        academic_level,

                    "year_of_study":
                        year_of_study,

                    "student_number":
                        student_number,

                    "status":
                        STATUS_NEW,

                    "admin_message":
                        "",

                    "created_at":
                        now_iso(),

                    "updated_at":
                        now_iso(),
                }
            )

            item = created[0]

            request_id = item["id"]


            # ------------------------------------------------
            # UPLOAD SUPPORTING FILE
            # ------------------------------------------------

            if (
                supporting_file
                and
                supporting_file.filename
            ):

                upload = storage_upload(

                    supporting_file,

                    folder=(
                        "supporting/"
                        + str(request_id)
                    )
                )

                db_insert(

                    "koja_request_files",

                    {

                        "request_id":
                            request_id,

                        "file_name":
                            upload[
                                "file_name"
                            ],

                        "file_url":
                            upload["path"],

                        "file_type":
                            upload[
                                "content_type"
                            ],

                        "file_size":
                            upload["size"],

                        "uploaded_by":
                            session[
                                "client_email"
                            ],

                        "created_at":
                            now_iso(),
                    },

                    returning=False
                )


            # ------------------------------------------------
            # HISTORY
            # ------------------------------------------------

            db_insert(

                "koja_request_history",

                {

                    "request_id":
                        request_id,

                    "old_status":
                        None,

                    "new_status":
                        STATUS_NEW,

                    "message":
                        "Request submitted by client.",

                    "changed_by":
                        session[
                            "client_email"
                        ],

                    "created_at":
                        now_iso(),
                },

                returning=False
            )


            # ------------------------------------------------
            # NOTIFICATION
            # ------------------------------------------------

            db_insert(

                "koja_notifications",

                {

                    "client_email":
                        session[
                            "client_email"
                        ],

                    "request_id":
                        request_id,

                    "title":
                        "Request Submitted",

                    "message":
                        (
                            "Your KOJA request "
                            + request_number
                            + " has been received."
                        ),

                    "is_read":
                        False,

                    "created_at":
                        now_iso(),
                },

                returning=False
            )


            flash(
                "Request submitted successfully. "
                "Reference: "
                + request_number
            )

            return redirect(

                url_for(

                    "request_detail",

                    request_id=request_id
                )
            )

        except Exception as exc:

            logging.exception(
                "Request submission failed"
            )

            flash(
                "Could not submit request: "
                + str(exc)[:400]
            )

    modes = [

        "Full-Time",
        "Part-Time",
        "Distance Learning",
        "Online",
        "Evening",
        "Weekend",
        "Blended",
        "Other"
    ]

    levels = [

        "Certificate",
        "Diploma",
        "Undergraduate",
        "Postgraduate",
        "Masters",
        "PhD",
        "Other"
    ]

    body = """

<div class="form-card">

<h2>
Submit New KOJA Request
</h2>

<p class="small">

Submit the work you want KOJA AFRICA
to process. Attach the source document
when necessary.

</p>


<form method="post"
enctype="multipart/form-data">


<label>
Service *
</label>

<select
name="service_type"
required
>

<option value="">
-- Select Service --
</option>

{% for service in services %}

<option
value="{{ service.name }}"
>

{{ service.name }}

</option>

{% endfor %}

</select>


<label>
Describe the Work / Request *
</label>

<textarea
name="description"
required
placeholder="Explain exactly what you want KOJA to process..."
></textarea>


<h3 class="section-title">
University Information
</h3>


<label>
University in Zambia
</label>

<select name="university">

<option value="">
-- Select University --
</option>

{% for university in universities %}

<option
value="{{ university.name }}"
{% if client.university == university.name %}
selected
{% endif %}
>

{{ university.name }}

</option>

{% endfor %}

</select>


<label>
Mode of Study
</label>

<select name="mode_of_study">

<option value="">
-- Select Mode --
</option>

{% for mode in modes %}

<option
value="{{ mode }}"
{% if client.mode_of_study == mode %}
selected
{% endif %}
>

{{ mode }}

</option>

{% endfor %}

</select>


<label>
School / Faculty
</label>

<input
name="school"
value="{{ client.school or '' }}"
placeholder="e.g. School of Natural Sciences"
>


<label>
Programme / Course
</label>

<input
name="programme"
value="{{ client.programme or '' }}"
placeholder="e.g. Bachelor of Science"
>


<label>
Academic Level
</label>

<select name="academic_level">

<option value="">
-- Select Level --
</option>

{% for level in levels %}

<option
value="{{ level }}"
{% if client.academic_level == level %}
selected
{% endif %}
>

{{ level }}

</option>

{% endfor %}

</select>


<label>
Year of Study
</label>

<input
name="year_of_study"
value="{{ client.year_of_study or '' }}"
>


<label>
Student Number
</label>

<input
name="student_number"
value="{{ client.student_number or '' }}"
>


<label>
Supporting Document
</label>

<input
type="file"
name="supporting_file"
>

<p class="small">

Maximum upload size: 25 MB.

</p>


<button type="submit">

Submit Request

</button>

</form>

</div>

"""

    return page(

        "New Request",

        body,

        services=services,

        universities=universities,

        client=client,

        modes=modes,

        levels=levels
    )


# ============================================================
# MY REQUESTS
# ============================================================

@app.route("/requests")
@client_login_required
def my_requests():

    requests_data = db_select(

        "koja_service_requests",

        select="*",

        filters={
            "client_email":
                "eq."
                + session[
                    "client_email"
                ]
        },

        order="created_at.desc"
    )

    body = """

<div class="card">

<h2>
My KOJA Requests
</h2>

{% if requests_data %}

<table>

<tr>

<th>
Reference
</th>

<th>
Service
</th>

<th>
Status
</th>

<th>
Date
</th>

<th>
</th>

</tr>


{% for r in requests_data %}

<tr>

<td>
<strong>
{{ r.request_number }}
</strong>
</td>

<td>
{{ r.service_type }}
</td>

<td>

<span class="status

{% if r.status == 'Completed' %}
completed

{% elif r.status == 'Processing' %}
processing

{% else %}
new
{% endif %}
">

{{ r.status }}

</span>

</td>

<td>
{{ r.created_at[:10] if r.created_at else '' }}
</td>

<td>

<a href="{{ url_for(
    'request_detail',
    request_id=r.id
) }}">

Open

</a>

</td>

</tr>

{% endfor %}

</table>

{% else %}

<p>
No requests found.
</p>

{% endif %}

</div>

"""

    return page(

        "My Requests",

        body,

        requests_data=requests_data
    )


# ============================================================
# REQUEST DETAIL
# ============================================================

@app.route(
    "/request/<request_id>"
)
@client_login_required
def request_detail(
    request_id
):

    rows = db_select(

        "koja_service_requests",

        select="*",

        filters={

            "id":
                "eq."
                + request_id,

            "client_email":
                "eq."
                + session[
                    "client_email"
                ]
        },

        limit=1
    )

    if not rows:

        abort(404)

    item = rows[0]

    files = db_select(

        "koja_request_files",

        select="*",

        filters={
            "request_id":
                "eq."
                + request_id
        },

        order="created_at.asc"
    )

    history = db_select(

        "koja_request_history",

        select="*",

        filters={
            "request_id":
                "eq."
                + request_id
        },

        order="created_at.desc"
    )

    body = """

<div class="card">

<h2>
{{ item.request_number }}
</h2>


<span class="status

{% if item.status == 'Completed' %}
completed

{% elif item.status == 'Processing' %}
processing

{% else %}
new
{% endif %}
">

{{ item.status }}

</span>


<h3 class="section-title">
Client Information
</h3>

<div class="detail">

<strong>
Name:
</strong>

{{ item.client_name }}

<br>

<strong>
Email:
</strong>

{{ item.client_email }}

<br>

<strong>
Phone:
</strong>

{{ item.client_phone }}

</div>


<h3>
Service
</h3>

<div class="detail">

<strong>
{{ item.service_type }}
</strong>

<br><br>

{{ item.description }}

</div>


<h3>
University Information
</h3>

<div class="detail">

<strong>
University:
</strong>

{{ item.university or 'Not provided' }}

<br>

<strong>
Mode of Study:
</strong>

{{ item.mode_of_study or 'Not provided' }}

<br>

<strong>
School:
</strong>

{{ item.school or 'Not provided' }}

<br>

<strong>
Programme:
</strong>

{{ item.programme or 'Not provided' }}

<br>

<strong>
Academic Level:
</strong>

{{ item.academic_level or 'Not provided' }}

<br>

<strong>
Year:
</strong>

{{ item.year_of_study or 'Not provided' }}

<br>

<strong>
Student Number:
</strong>

{{ item.student_number or 'Not provided' }}

</div>


<h3>
Supporting Documents
</h3>

{% if files %}

{% for f in files %}

<div class="detail">

<strong>
{{ f.file_name }}
</strong>

<br>

<a href="{{ url_for(
    'download_supporting_file',
    file_id=f.id
) }}">

Download Supporting Document

</a>

</div>

{% endfor %}

{% else %}

<p>
No supporting document uploaded.
</p>

{% endif %}


{% if item.admin_message %}

<h3>
KOJA Message
</h3>

<div class="detail">

{{ item.admin_message }}

</div>

{% endif %}


{% if item.status == 'Completed'
and item.completed_file_url %}

<h3>
Completed Document
</h3>

<div class="detail">

<strong>
{{ item.completed_file_name }}
</strong>

<br>

<a class="btn success"
href="{{ url_for(
    'download_completed_file',
    request_id=item.id
) }}">

Download Completed File

</a>

</div>

{% endif %}


<h3>
Request History
</h3>

{% for h in history %}

<div class="detail">

<strong>
{{ h.new_status }}
</strong>

<br>

{{ h.message or '' }}

<br>

<span class="small">

{{ h.created_at or '' }}

</span>

</div>

{% endfor %}

</div>

"""

    return page(

        "Request "
        + item[
            "request_number"
        ],

        body,

        item=item,

        files=files,

        history=history
    )


# ============================================================
# SUPPORTING FILE DOWNLOAD
# ============================================================

@app.route(
    "/file/supporting/<file_id>"
)
@client_login_required
def download_supporting_file(
    file_id
):

    files = db_select(

        "koja_request_files",

        select="*",

        filters={
            "id":
                "eq."
                + file_id
        },

        limit=1
    )

    if not files:

        abort(404)

    record = files[0]

    owned = db_select(

        "koja_service_requests",

        select="id",

        filters={

            "id":
                "eq."
                + record[
                    "request_id"
                ],

            "client_email":
                "eq."
                + session[
                    "client_email"
                ]
        },

        limit=1
    )

    if not owned:

        abort(403)

    response = storage_download(
        record["file_url"]
    )

    return send_file(

        io.BytesIO(
            response.content
        ),

        mimetype=(
            record.get(
                "file_type"
            )
            or
            "application/octet-stream"
        ),

        as_attachment=True,

        download_name=(
            record[
                "file_name"
            ]
        )
    )


# ============================================================
# COMPLETED FILE DOWNLOAD
# ============================================================

@app.route(
    "/request/<request_id>/download"
)
@client_login_required
def download_completed_file(
    request_id
):

    rows = db_select(

        "koja_service_requests",

        select="*",

        filters={

            "id":
                "eq."
                + request_id,

            "client_email":
                "eq."
                + session[
                    "client_email"
                ],

            "status":
                "eq."
                + STATUS_COMPLETED
        },

        limit=1
    )

    if not rows:

        abort(404)

    item = rows[0]

    if not item.get(
        "completed_file_url"
    ):

        abort(404)

    response = storage_download(

        item[
            "completed_file_url"
        ]
    )

    return send_file(

        io.BytesIO(
            response.content
        ),

        mimetype=(
            item.get(
                "completed_file_type"
            )
            or
            "application/octet-stream"
        ),

        as_attachment=True,

        download_name=(
            item.get(
                "completed_file_name"
            )
            or
            "KOJA-completed-document"
        )
    )


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/notifications")
@client_login_required
def notifications():

    data = db_select(

        "koja_notifications",

        select="*",

        filters={
            "client_email":
                "eq."
                + session[
                    "client_email"
                ]
        },

        order="created_at.desc",

        limit=100
    )

    try:

        db_update(

            "koja_notifications",

            {

                "client_email":
                    "eq."
                    + session[
                        "client_email"
                    ],

                "is_read":
                    "eq.false"
            },

            {

                "is_read":
                    True,

                "read_at":
                    now_iso()
            },

            returning=False
        )

    except Exception:

        logging.exception(
            "Notification update failed"
        )

    body = """

<div class="card">

<h2>
Notifications
</h2>

{% if data %}

{% for n in data %}

<div class="detail">

<strong>
{{ n.title }}
</strong>

<br><br>

{{ n.message }}

<br>

<span class="small">

{{ n.created_at or '' }}

</span>

</div>

{% endfor %}

{% else %}

<p>
No notifications.
</p>

{% endif %}

</div>

"""

    return page(

        "Notifications",

        body,

        data=data
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = clean(
            request.form.get(
                "username"
            ),
            100
        )

        password = request.form.get(
            "password",
            ""
        )

        if (

            username
            == ADMIN_USERNAME

            and ADMIN_PASSWORD

            and secrets.compare_digest(
                password,
                ADMIN_PASSWORD
            )
        ):

            session.clear()

            session[
                "admin_logged_in"
            ] = True

            session[
                "admin_username"
            ] = username

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        flash(
            "Invalid administrator credentials."
        )

    body = """

<div class="form-card">

<h2>
KOJA AFRICA Administrator
</h2>

<form method="post">

<label>
Username
</label>

<input
name="username"
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

Administrator Login

</button>

</form>

</div>

"""

    return page(
        "Admin Login",
        body
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for(
            "admin_login"
        )
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/admin")
@admin_required
def admin_dashboard():

    requests_data = db_select(

        "koja_service_requests",

        select="*",

        order="created_at.desc",

        limit=500
    )

    new_count = sum(

        1
        for r in requests_data

        if r.get("status")
        == STATUS_NEW
    )

    processing_count = sum(

        1
        for r in requests_data

        if r.get("status")
        == STATUS_PROCESSING
    )

    completed_count = sum(

        1
        for r in requests_data

        if r.get("status")
        == STATUS_COMPLETED
    )

    body = """

<div class="hero">

<h1>
KOJA AFRICA Admin Dashboard
</h1>

<p>

Manage client requests,
download submitted work,
process requests,
send messages and upload
completed documents.

</p>

</div>


<div class="grid">

<div class="card">

<h3>
New
</h3>

<h2>
{{ new_count }}
</h2>

</div>


<div class="card">

<h3>
Processing
</h3>

<h2>
{{ processing_count }}
</h2>

</div>


<div class="card">

<h3>
Completed
</h3>

<h2>
{{ completed_count }}
</h2>

</div>


<div class="card">

<h3>
Total
</h3>

<h2>
{{ requests_data|length }}
</h2>

</div>

</div>


<div class="card">

<h2>
Client Requests
</h2>

<table>

<tr>

<th>
Reference
</th>

<th>
Client
</th>

<th>
Service
</th>

<th>
Status
</th>

<th>
Date
</th>

<th>
</th>

</tr>


{% for r in requests_data %}

<tr>

<td>

<strong>
{{ r.request_number }}
</strong>

</td>


<td>

{{ r.client_name }}

<br>

<span class="small">

{{ r.client_email }}

<br>

{{ r.client_phone }}

</span>

</td>


<td>

{{ r.service_type }}

</td>


<td>

<span class="status

{% if r.status == 'Completed' %}
completed

{% elif r.status == 'Processing' %}
processing

{% else %}
new
{% endif %}

">

{{ r.status }}

</span>

</td>


<td>

{{ r.created_at[:10]
if r.created_at else '' }}

</td>


<td>

<a href="{{ url_for(
    'admin_request',
    request_id=r.id
) }}">

Open

</a>

</td>

</tr>

{% endfor %}

</table>

</div>

"""

    return page(

        "Admin Dashboard",

        body,

        requests_data=requests_data,

        new_count=new_count,

        processing_count=processing_count,

        completed_count=completed_count
    )


# ============================================================
# ADMIN REQUEST
# ============================================================

@app.route(
    "/admin/request/<request_id>",
    methods=["GET", "POST"]
)
@admin_required
def admin_request(
    request_id
):

    rows = db_select(

        "koja_service_requests",

        select="*",

        filters={
            "id":
                "eq."
                + request_id
        },

        limit=1
    )

    if not rows:

        abort(404)

    item = rows[0]

    files = db_select(

        "koja_request_files",

        select="*",

        filters={
            "request_id":
                "eq."
                + request_id
        },

        order="created_at.asc"
    )


    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        )

        message = clean(

            request.form.get(
                "admin_message"
            ),

            10000
        )


        # ====================================================
        # PROCESSING
        # ====================================================

        if action == "processing":

            old_status = item[
                "status"
            ]

            db_update(

                "koja_service_requests",

                {
                    "id":
                        "eq."
                        + request_id
                },

                {

                    "status":
                        STATUS_PROCESSING,

                    "admin_message":
                        message,

                    "updated_at":
                        now_iso()
                },

                returning=False
            )


            db_insert(

                "koja_request_history",

                {

                    "request_id":
                        request_id,

                    "old_status":
                        old_status,

                    "new_status":
                        STATUS_PROCESSING,

                    "message":
                        (
                            message
                            or
                            "Request is being processed."
                        ),

                    "changed_by":
                        session.get(
                            "admin_username",
                            "admin"
                        ),

                    "created_at":
                        now_iso()
                },

                returning=False
            )


            db_insert(

                "koja_notifications",

                {

                    "client_email":
                        item[
                            "client_email"
                        ],

                    "request_id":
                        request_id,

                    "title":
                        "Request Processing",

                    "message":
                        (
                            "Your request "
                            + item[
                                "request_number"
                            ]
                            + " is now "
                            "being processed."
                        ),

                    "is_read":
                        False,

                    "created_at":
                        now_iso()
                },

                returning=False
            )


            flash(
                "Request marked as Processing."
            )

            return redirect(

                url_for(

                    "admin_request",

                    request_id=request_id
                )
            )


        # ====================================================
        # MESSAGE
        # ====================================================

        if action == "message":

            if not message:

                flash(
                    "Enter a message first."
                )

                return redirect(

                    url_for(

                        "admin_request",

                        request_id=request_id
                    )
                )


            db_update(

                "koja_service_requests",

                {
                    "id":
                        "eq."
                        + request_id
                },

                {

                    "admin_message":
                        message,

                    "updated_at":
                        now_iso()
                },

                returning=False
            )


            db_insert(

                "koja_notifications",

                {

                    "client_email":
                        item[
                            "client_email"
                        ],

                    "request_id":
                        request_id,

                    "title":
                        "Message from KOJA",

                    "message":
                        message,

                    "is_read":
                        False,

                    "created_at":
                        now_iso()
                },

                returning=False
            )


            flash(
                "Message sent to client."
            )

            return redirect(

                url_for(

                    "admin_request",

                    request_id=request_id
                )
            )


        # ====================================================
        # COMPLETE
        # ====================================================

        if action == "complete":

            completed_file = (
                request.files.get(
                    "completed_file"
                )
            )


            if (
                not completed_file
                or
                not completed_file.filename
            ):

                flash(
                    "Please upload "
                    "the completed document."
                )

                return redirect(

                    url_for(

                        "admin_request",

                        request_id=request_id
                    )
                )


            if not allowed_file(
                completed_file.filename
            ):

                flash(
                    "Unsupported completed "
                    "file type."
                )

                return redirect(

                    url_for(

                        "admin_request",

                        request_id=request_id
                    )
                )


            try:

                upload = storage_upload(

                    completed_file,

                    folder=(
                        "completed/"
                        + str(request_id)
                    )
                )


                old_status = item[
                    "status"
                ]


                db_update(

                    "koja_service_requests",

                    {
                        "id":
                            "eq."
                            + request_id
                    },

                    {

                        "status":
                            STATUS_COMPLETED,

                        "admin_message":
                            message,

                        "completed_file_url":
                            upload[
                                "path"
                            ],

                        "completed_file_name":
                            upload[
                                "file_name"
                            ],

                        "completed_file_type":
                            upload[
                                "content_type"
                            ],

                        "completed_at":
                            now_iso(),

                        "updated_at":
                            now_iso()
                    },

                    returning=False
                )


                db_insert(

                    "koja_request_history",

                    {

                        "request_id":
                            request_id,

                        "old_status":
                            old_status,

                        "new_status":
                            STATUS_COMPLETED,

                        "message":
                            (
                                message
                                or
                                "Completed document uploaded."
                            ),

                        "changed_by":
                            session.get(
                                "admin_username",
                                "admin"
                            ),

                        "created_at":
                            now_iso()
                    },

                    returning=False
                )


                db_insert(

                    "koja_notifications",

                    {

                        "client_email":
                            item[
                                "client_email"
                            ],

                        "request_id":
                            request_id,

                        "title":
                            "Request Completed",

                        "message":
                            (
                                "Your KOJA request "
                                + item[
                                    "request_number"
                                ]
                                + " is completed. "
                                "Your finished document "
                                "is now available."
                            ),

                        "is_read":
                            False,

                        "created_at":
                            now_iso()
                    },

                    returning=False
                )


                flash(
                    "Request completed successfully."
                )

                return redirect(

                    url_for(

                        "admin_request",

                        request_id=request_id
                    )
                )


            except Exception as exc:

                logging.exception(
                    "Completion failed"
                )

                flash(
                    "Could not complete request: "
                    + str(exc)[:400]
                )

                return redirect(

                    url_for(

                        "admin_request",

                        request_id=request_id
                    )
                )


    body = """

<div class="card">

<h2>
{{ item.request_number }}
</h2>


<span class="status

{% if item.status == 'Completed' %}
completed

{% elif item.status == 'Processing' %}
processing

{% else %}
new
{% endif %}

">

{{ item.status }}

</span>


<h3 class="section-title">
Client Information
</h3>

<div class="detail">

<strong>
Name:
</strong>

{{ item.client_name }}

<br>

<strong>
Email:
</strong>

{{ item.client_email }}

<br>

<strong>
Phone:
</strong>

{{ item.client_phone }}

</div>


<h3>
Service
</h3>

<div class="detail">

<strong>
{{ item.service_type }}
</strong>

<br><br>

{{ item.description }}

</div>


<h3>
University Information
</h3>

<div class="detail">

<strong>
University:
</strong>

{{ item.university or 'Not provided' }}

<br>

<strong>
Mode of Study:
</strong>

{{ item.mode_of_study or 'Not provided' }}

<br>

<strong>
School:
</strong>

{{ item.school or 'Not provided' }}

<br>

<strong>
Programme:
</strong>

{{ item.programme or 'Not provided' }}

<br>

<strong>
Academic Level:
</strong>

{{ item.academic_level or 'Not provided' }}

<br>

<strong>
Year:
</strong>

{{ item.year_of_study or 'Not provided' }}

<br>

<strong>
Student Number:
</strong>

{{ item.student_number or 'Not provided' }}

</div>


<h3>
Supporting Documents
</h3>

{% if files %}

{% for f in files %}

<div class="detail">

<strong>
{{ f.file_name }}
</strong>

<br>

<span class="small">

{{ f.file_type or '' }}

</span>

<br>

<a href="{{ url_for(
    'admin_download_file',
    file_id=f.id
) }}">

Download Supporting Document

</a>

</div>

{% endfor %}

{% else %}

<p>
No supporting files.
</p>

{% endif %}


<p>

<a href="{{ url_for(
    'admin_history',
    request_id=item.id
) }}">

View Full Request History

</a>

</p>


<hr>


<h3>
Move to Processing
</h3>

<form method="post">

<input
type="hidden"
name="action"
value="processing"
>

<label>
Message to Client
</label>

<textarea
name="admin_message"
placeholder="Optional message..."
></textarea>

<button
class="btn warning"
type="submit"
>

Mark Processing

</button>

</form>


<hr>


<h3>
Send Message
</h3>

<form method="post">

<input
type="hidden"
name="action"
value="message"
>

<label>
Message
</label>

<textarea
name="admin_message"
required
placeholder="Write a message to the client..."
></textarea>

<button
type="submit"
>

Send Message

</button>

</form>


<hr>


<h3>
Complete Request
</h3>

<p class="small">

Upload the finished document
that the client should receive.

</p>


<form method="post"
enctype="multipart/form-data">

<input
type="hidden"
name="action"
value="complete"
>


<label>
Finished PDF / Word / Document *
</label>

<input
type="file"
name="completed_file"
required
>


<label>
Completion Message
</label>

<textarea
name="admin_message"
placeholder="Optional message to the client..."
></textarea>


<button
class="btn success"
type="submit"
>

Upload & Mark Completed

</button>

</form>


{% if item.status == 'Completed'
and item.completed_file_url %}

<hr>

<h3>
Current Completed File
</h3>

<div class="detail">

{{ item.completed_file_name }}

<br>

<a
class="btn success"
href="{{ url_for(
    'admin_download_completed',
    request_id=item.id
) }}"
>

Download Completed File

</a>

</div>

{% endif %}

</div>

"""

    return page(

        "Admin Request",

        body,

        item=item,

        files=files
    )


# ============================================================
# ADMIN SUPPORTING DOWNLOAD
# ============================================================

@app.route(
    "/admin/file/<file_id>"
)
@admin_required
def admin_download_file(
    file_id
):

    files = db_select(

        "koja_request_files",

        select="*",

        filters={
            "id":
                "eq."
                + file_id
        },

        limit=1
    )

    if not files:

        abort(404)

    record = files[0]

    response = storage_download(
        record["file_url"]
    )

    return send_file(

        io.BytesIO(
            response.content
        ),

        mimetype=(
            record.get(
                "file_type"
            )
            or
            "application/octet-stream"
        ),

        as_attachment=True,

        download_name=(
            record[
                "file_name"
            ]
        )
    )


# ============================================================
# ADMIN COMPLETED DOWNLOAD
# ============================================================

@app.route(
    "/admin/request/<request_id>/completed"
)
@admin_required
def admin_download_completed(
    request_id
):

    rows = db_select(

        "koja_service_requests",

        select="*",

        filters={
            "id":
                "eq."
                + request_id
        },

        limit=1
    )

    if not rows:

        abort(404)

    item = rows[0]

    if not item.get(
        "completed_file_url"
    ):

        abort(404)

    response = storage_download(

        item[
            "completed_file_url"
        ]
    )

    return send_file(

        io.BytesIO(
            response.content
        ),

        mimetype=(
            item.get(
                "completed_file_type"
            )
            or
            "application/octet-stream"
        ),

        as_attachment=True,

        download_name=(
            item.get(
                "completed_file_name"
            )
            or
            "completed-document"
        )
    )


# ============================================================
# ADMIN HISTORY
# ============================================================

@app.route(
    "/admin/request/<request_id>/history"
)
@admin_required
def admin_history(
    request_id
):

    history = db_select(

        "koja_request_history",

        select="*",

        filters={
            "request_id":
                "eq."
                + request_id
        },

        order="created_at.desc"
    )

    body = """

<div class="card">

<h2>
Request History
</h2>

{% if history %}

{% for h in history %}

<div class="detail">

<strong>
{{ h.new_status }}
</strong>

<br>

{{ h.message or '' }}

<br>

<span class="small">

By:
{{ h.changed_by or 'System' }}

<br>

{{ h.created_at or '' }}

</span>

</div>

{% endfor %}

{% else %}

<p>
No history found.
</p>

{% endif %}

</div>

"""

    return page(

        "Request History",

        body,

        history=history
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():

    return {

        "status":
            "ok",

        "app":
            APP_NAME,

        "supabase_configured":
            configuration_ok(),

        "time":
            now_iso()
    }


@app.route("/health/database")
def database_health():

    try:

        services = db_select(

            "koja_services",

            select="id,name",

            limit=1
        )

        universities = db_select(

            "koja_universities",

            select="id,name",

            limit=1
        )

        return {

            "status":
                "ok",

            "database":
                "connected",

            "services_table":
                True,

            "universities_table":
                True,

            "sample_services":
                len(
                    services or []
                ),

            "sample_universities":
                len(
                    universities or []
                )
        }

    except Exception as exc:

        return {

            "status":
                "error",

            "database":
                "failed",

            "error":
                str(exc)[:700]
        }, 500


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    flash(
        "File is too large. "
        "Maximum allowed size is 25 MB."
    )

    if session.get(
        "admin_logged_in"
    ):

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if session.get(
        "client_id"
    ):

        return redirect(
            url_for(
                "new_request"
            )
        )

    return redirect(
        url_for("home")
    )


@app.errorhandler(404)
def not_found(error):

    body = """

<div class="hero">

<h1>
404
</h1>

<p>
The requested page or document
was not found.
</p>

<a class="btn"
href="{{ url_for('home') }}">

Return Home

</a>

</div>

"""

    return page(
        "Not Found",
        body
    ), 404


@app.errorhandler(500)
def server_error(error):

    logging.exception(
        "Internal server error"
    )

    body = """

<div class="hero">

<h1>
Something went wrong
</h1>

<p>
KOJA AFRICA encountered an
internal error. Please try again.
</p>

<a class="btn"
href="{{ url_for('home') }}">

Return Home

</a>

</div>

"""

    return page(
        "Server Error",
        body
    ), 500


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    host = os.getenv(
        "HOST",
        "0.0.0.0"
    )

    logging.info(
        "Starting %s on %s:%s",
        APP_NAME,
        host,
        port
    )

    app.run(

        host=host,

        port=port,

        debug=False
    )
